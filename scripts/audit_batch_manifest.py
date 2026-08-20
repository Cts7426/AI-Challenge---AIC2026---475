# scripts/audit_batch_manifest.py — kiểm kê archive BTC mà không tự tải/giải nén.
#
# CSV BTC chỉ là danh sách URL, không phải dữ liệu. Script tạo một báo cáo có
# thể lặp lại về file nào đã tải, kích thước, SHA-256 và trạng thái giải nén;
# tuyệt đối không sửa parquet/index khi chỉ đang kiểm kê.

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class ManifestEntry:
    """Một URL BTC và trạng thái local có thể kiểm chứng của nó."""

    filename: str
    url: str
    category: str
    archive_path: str
    download_status: str
    size_bytes: int | None
    sha256: str | None
    extracted_status: str
    extracted_files: int | None


def _category(filename: str) -> str:
    """Tên archive → nhóm dữ liệu; không phụ thuộc thứ tự dòng trong CSV."""
    lower = filename.lower()
    for prefix, category in (
        ("keyframes", "keyframes"),
        ("videos", "videos"),
        ("clip", "clip_features"),
        ("map", "frame_maps"),
        ("media", "metadata"),
        ("object", "objects"),
    ):
        if lower.startswith(prefix):
            return category
    return "other"


def load_manifest(path: Path) -> list[tuple[str, str]]:
    """CSV BTC → list `(filename, url)` đã loại dòng rỗng và URL sai.

    Invariant: tên file phải khớp basename URL; lệch tên là lỗi manifest vì có
    thể khiến kiểm kê một archive nhưng tải archive khác.
    """
    rows: list[tuple[str, str]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            filename = (row.get("Filenames") or "").strip()
            url = (row.get("Download link") or "").strip()
            if not filename and not url:
                continue
            if not filename or not url:
                raise ValueError(f"dòng manifest thiếu filename hoặc URL: {row}")
            if urlparse(url).scheme not in {"http", "https"}:
                raise ValueError(f"URL không hợp lệ cho {filename}: {url}")
            if Path(urlparse(url).path).name != filename:
                raise ValueError(
                    f"filename {filename!r} không khớp basename URL {url!r}"
                )
            rows.append((filename, url))
    if not rows:
        raise ValueError(f"manifest {path} không có dòng dữ liệu")
    duplicates = sorted({name for name, _ in rows if sum(n == name for n, _ in rows) > 1})
    if duplicates:
        raise ValueError(f"manifest có filename trùng: {duplicates}")
    return rows


def _sha256(path: Path) -> str:
    """File archive → SHA-256 theo luồng, không nạp file nhiều GB vào RAM."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _extracted_candidates(root: Path, filename: str) -> list[Path]:
    """Các thư mục thường có sau khi giải nén archive BTC."""
    stem = Path(filename).stem
    lower = stem.lower()
    candidates = [
        root / stem,
        root / stem.replace("Keyframes_", "keyframes_"),
        root / "keyframes" / stem,
        root / "keyframes" / stem.replace("Keyframes_", "keyframes_"),
    ]
    if lower.startswith("keyframes_"):
        part = stem.split("_", 1)[1].split("_", 1)[0]
        for base in (root, root / "keyframes"):
            if base.is_dir():
                candidates.extend(path for path in base.glob(f"{part}_V*") if path.is_dir())
    return list(dict.fromkeys(candidates))


def audit_manifest(
    manifest_path: Path,
    archives_dir: Path,
    extracted_root: Path | None = None,
    *,
    calculate_hash: bool = False,
    count_extracted: bool = False,
) -> list[ManifestEntry]:
    """Manifest + local roots → báo cáo thuần đọc, một record mỗi URL.

    Invariant: không tải, giải nén, đổi tên hay sửa dữ liệu. Đếm extracted chỉ
    chạy khi yêu cầu vì rglob hàng trăm nghìn ảnh có thể mất nhiều phút.
    """
    report: list[ManifestEntry] = []
    for filename, url in load_manifest(manifest_path):
        archive = archives_dir / filename
        exists = archive.is_file()
        size = archive.stat().st_size if exists else None
        digest = _sha256(archive) if exists and calculate_hash else None

        extracted_status = "not_checked"
        extracted_files = None
        if extracted_root is not None:
            candidates = [p for p in _extracted_candidates(extracted_root, filename) if p.exists()]
            if not candidates:
                extracted_status = "missing"
            elif count_extracted:
                extracted_files = sum(
                    1 for root in candidates for path in root.rglob("*") if path.is_file()
                )
                extracted_status = "present" if extracted_files else "empty"
            else:
                extracted_status = "present_unscanned"

        report.append(ManifestEntry(
            filename=filename,
            url=url,
            category=_category(filename),
            archive_path=str(archive),
            download_status="present" if exists else "missing",
            size_bytes=size,
            sha256=digest,
            extracted_status=extracted_status,
            extracted_files=extracted_files,
        ))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit manifest dữ liệu BTC (chỉ đọc).")
    parser.add_argument("manifest", type=Path, help="CSV BTC có Filenames và Download link")
    parser.add_argument("--archives-dir", type=Path, default=Path.home() / "Downloads")
    parser.add_argument("--extracted-root", type=Path)
    parser.add_argument("--hash", action="store_true", help="tính SHA-256 archive đã tải")
    parser.add_argument("--count-extracted", action="store_true")
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()

    report = audit_manifest(
        args.manifest,
        args.archives_dir,
        args.extracted_root,
        calculate_hash=args.hash,
        count_extracted=args.count_extracted,
    )
    payload = {
        "manifest": str(args.manifest),
        "archives_dir": str(args.archives_dir),
        "total": len(report),
        "present": sum(entry.download_status == "present" for entry in report),
        "missing": sum(entry.download_status == "missing" for entry in report),
        "entries": [asdict(entry) for entry in report],
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if payload["missing"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
