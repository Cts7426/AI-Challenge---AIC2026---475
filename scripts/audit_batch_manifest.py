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
import re
import shutil
import subprocess
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse


REPO_ROOT = Path(__file__).resolve().parents[1]
ROUND1_REQUIRED = "required_round1"
ROUND1_DEFERRED = "deferred_not_required_round1"
ROUND1_REQUIRED_CATEGORIES = frozenset({
    "keyframes",
    "clip_features",
    "frame_maps",
    "metadata",
    "objects",
})
_VIDEO_ID = re.compile(r"^L\d+_V\d+$", re.IGNORECASE)
_RAW_LAYOUTS = {
    "keyframes": Path("keyframes"),
    "clip_features": Path("clip-features-32"),
    "frame_maps": Path("metadata") / "map-keyframes",
    "metadata": Path("metadata") / "media-info",
    "objects": Path("objects"),
    "videos": Path("videos"),
}
_ASSET_SUFFIXES = {
    "keyframes": {".jpg", ".jpeg"},
    "clip_features": {".npy"},
    "frame_maps": {".csv"},
    "metadata": {".json"},
    "objects": {".json"},
    "videos": {".mp4"},
}


@dataclass(frozen=True)
class ManifestEntry:
    """Một URL BTC và trạng thái local có thể kiểm chứng của nó."""

    filename: str
    url: str
    category: str
    round1_requirement: str
    archive_path: str
    download_status: str
    size_bytes: int | None
    sha256: str | None
    archive_member_files: int | None
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


def _round1_requirement(category: str) -> str:
    """Nhóm dữ liệu → mức bắt buộc của pipeline nộp lô đợt 1.

    Video gốc chưa nằm trên đường KIS/Q&A/TRAKE hiện hành: frame nộp tra từ
    frame_map, còn bằng chứng ảnh dùng raw keyframe. Vẫn giữ từng URL video
    trong audit, nhưng không biến việc chưa tải chúng thành lỗi sẵn sàng đợt 1.
    Nhóm lạ được coi là bắt buộc để manifest mới không bị bỏ qua im lặng.
    """
    if category in ROUND1_REQUIRED_CATEGORIES:
        return ROUND1_REQUIRED
    if category == "videos":
        return ROUND1_DEFERRED
    return ROUND1_REQUIRED


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


def _archive_asset_key(category: str, member_name: str) -> Path | None:
    """Tên member ZIP → vị trí tương đối trong raw layout chuẩn.

    Archive keyframe/objects có thể có một hoặc nhiều lớp thư mục bọc. Chỉ lấy
    phần từ `video_id` để các part như L26-a…e được đối chiếu độc lập với cùng
    thư mục raw đã hợp nhất. Core archive được BTC phát theo một file mỗi video,
    nên basename là khóa đủ và không phụ thuộc lớp bọc trong ZIP.
    """
    member = PurePosixPath(member_name.replace("\\", "/"))
    suffixes = _ASSET_SUFFIXES.get(category)
    if not suffixes or member.suffix.lower() not in suffixes:
        return None
    if category in {"keyframes", "objects"}:
        parts = list(member.parts)
        for index, part in enumerate(parts):
            if _VIDEO_ID.fullmatch(part):
                return Path(*parts[index:])
        return None
    return Path(member.name)


def _archive_extraction_count(
    archive: Path,
    extracted_root: Path,
    category: str,
) -> tuple[int, int, str]:
    """Đếm asset của đúng một ZIP và số member đã có trong raw.

    Không đếm cả thư mục dùng chung theo tên batch. Nhờ vậy năm part L26/L28
    không còn lặp lại cùng một số tổng hợp và có thể phát hiện part giải nén dở.
    """
    base = extracted_root / _RAW_LAYOUTS[category]
    with zipfile.ZipFile(archive) as handle:
        keys = [
            key
            for info in handle.infolist()
            if not info.is_dir()
            if (key := _archive_asset_key(category, info.filename)) is not None
        ]
    extracted = sum((base / key).is_file() for key in keys)
    if not keys:
        status = "archive_has_no_assets"
    elif extracted == len(keys):
        status = "present"
    elif extracted:
        status = "partial"
    else:
        status = "missing"
    return len(keys), extracted, status


def raw_asset_snapshot(root: Path, *, count_files: bool) -> dict[str, object]:
    """Raw root → snapshot tách riêng khỏi số member theo từng archive."""
    categories: dict[str, object] = {}
    for category, relative in _RAW_LAYOUTS.items():
        path = root / relative
        suffixes = _ASSET_SUFFIXES[category]
        files = None
        size_bytes = None
        video_directories = None
        if count_files and path.is_dir():
            files = 0
            size_bytes = 0
            for item in path.rglob("*"):
                if item.is_file() and item.suffix.lower() in suffixes:
                    files += 1
                    size_bytes += item.stat().st_size
            if category == "keyframes":
                video_directories = sum(
                    item.is_dir() and bool(_VIDEO_ID.fullmatch(item.name))
                    for item in path.iterdir()
                )
        categories[category] = {
            "path": str(path),
            "exists": path.is_dir(),
            "count_status": (
                "missing" if not path.is_dir()
                else "counted" if count_files
                else "not_requested"
            ),
            "files": files,
            "size_bytes": size_bytes,
            "size_gib": round(size_bytes / (1024 ** 3), 3)
            if size_bytes is not None else None,
            "video_directories": video_directories,
        }
    return {"root": str(root), "categories": categories}


def _derived_metadata_snapshot() -> dict[str, object]:
    """Đọc meta artefact hiện có; không mở parquet hay kết nối database."""
    names = (
        "video_info.parquet.meta.json",
        "frame_map.parquet.meta.json",
        "shots.parquet.meta.json",
        "keyframes.parquet.meta.json",
        "clip_kf_map.parquet.meta.json",
        "docs_bm25.parquet.meta.json",
        "clip_index.meta.json",
    )
    artifacts: dict[str, object] = {}
    for name in names:
        path = REPO_ROOT / "data" / "derived" / name
        if not path.is_file():
            artifacts[name] = {"status": "missing", "path": str(path)}
            continue
        try:
            metadata = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            artifacts[name] = {
                "status": "unreadable",
                "path": str(path),
                "error": str(exc),
            }
            continue
        artifacts[name] = {
            "status": "present",
            "path": str(path),
            "row_count": metadata.get("row_count"),
            "n_vectors": metadata.get("n_vectors"),
            "metric": metadata.get("metric"),
            "normalized": metadata.get("normalized"),
            "built_at": metadata.get("built_at"),
        }
    return {
        "scope": "artifact_metadata_only_not_live_database",
        "artifacts": artifacts,
    }


def _git_provenance() -> dict[str, object]:
    """Commit + dirty flag để manifest có thể truy ngược đúng worktree."""
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = bool(subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip())
        return {"commit": commit, "dirty": dirty}
    except (OSError, subprocess.CalledProcessError) as exc:
        return {"commit": None, "dirty": None, "error": str(exc)}


def load_reusable_hashes(path: Path) -> dict[str, tuple[int, str]]:
    """Manifest audit cũ → hash cache kèm size để tránh hash lại archive lớn.

    Hash chỉ được tái sử dụng nếu tên file, kích thước hiện tại và SHA-256 64 ký
    tự đều hợp lệ. Mismatch không được bỏ qua: entry mới sẽ thiếu hash và cổng
    `round1_operational_audit_complete` sẽ không thể xanh.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    reusable: dict[str, tuple[int, str]] = {}
    for entry in payload.get("entries", []):
        filename = entry.get("filename")
        size = entry.get("size_bytes")
        digest = entry.get("sha256")
        if (
            isinstance(filename, str)
            and isinstance(size, int)
            and isinstance(digest, str)
            and re.fullmatch(r"[0-9a-f]{64}", digest)
        ):
            reusable[filename] = (size, digest)
    return reusable


def _extracted_candidates(root: Path, filename: str) -> list[Path]:
    """Các thư mục thật có sau khi giải nén từng loại archive BTC.

    Bốn gói lõi không giữ nguyên tên archive: chúng lần lượt nằm ở
    `clip-features-32`, `metadata/map-keyframes`, `metadata/media-info` và
    `objects`. Liệt kê tường minh để audit không báo thiếu dù raw asset đã có.
    """
    stem = Path(filename).stem
    lower = stem.lower()
    category = _category(filename)
    candidates = [
        root / stem,
        root / stem.replace("Keyframes_", "keyframes_"),
        root / "keyframes" / stem,
        root / "keyframes" / stem.replace("Keyframes_", "keyframes_"),
    ]
    candidates.extend({
        "clip_features": [root / "clip-features-32"],
        "frame_maps": [root / "metadata" / "map-keyframes"],
        "metadata": [root / "metadata" / "media-info"],
        "objects": [root / "objects"],
    }.get(category, []))
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
    reusable_hashes: dict[str, tuple[int, str]] | None = None,
) -> list[ManifestEntry]:
    """Manifest + local roots → báo cáo thuần đọc, một record mỗi URL.

    Invariant: không tải, giải nén, đổi tên hay sửa dữ liệu. Đếm extracted chỉ
    chạy khi yêu cầu vì rglob hàng trăm nghìn ảnh có thể mất nhiều phút.
    """
    report: list[ManifestEntry] = []
    for filename, url in load_manifest(manifest_path):
        category = _category(filename)
        archive = archives_dir / filename
        exists = archive.is_file()
        size = archive.stat().st_size if exists else None
        digest = _sha256(archive) if exists and calculate_hash else None
        if exists and not calculate_hash and reusable_hashes:
            cached = reusable_hashes.get(filename)
            if cached and cached[0] == size:
                digest = cached[1]

        archive_member_files = None
        extracted_status = "not_checked"
        extracted_files = None
        if extracted_root is not None:
            if count_extracted and exists and category in _RAW_LAYOUTS:
                try:
                    (
                        archive_member_files,
                        extracted_files,
                        extracted_status,
                    ) = _archive_extraction_count(
                        archive,
                        extracted_root,
                        category,
                    )
                except (OSError, zipfile.BadZipFile):
                    extracted_status = "archive_unreadable"
            else:
                candidates = [
                    path for path in _extracted_candidates(extracted_root, filename)
                    if path.exists()
                ]
                if not candidates:
                    extracted_status = "missing"
                elif count_extracted:
                    extracted_files = sum(
                        1
                        for root in candidates
                        for path in root.rglob("*")
                        if path.is_file()
                    )
                    extracted_status = "present" if extracted_files else "empty"
                else:
                    extracted_status = "present_unscanned"

        report.append(ManifestEntry(
            filename=filename,
            url=url,
            category=category,
            round1_requirement=_round1_requirement(category),
            archive_path=str(archive),
            download_status="present" if exists else "missing",
            size_bytes=size,
            sha256=digest,
            archive_member_files=archive_member_files,
            extracted_status=extracted_status,
            extracted_files=extracted_files,
        ))
    return report


def summarize_report(report: list[ManifestEntry]) -> dict[str, int | bool]:
    """Danh sách audit → số liệu factual và readiness riêng cho đợt 1.

    `missing` luôn phản ánh toàn manifest. `round1_download_ready` chỉ xác nhận
    đủ archive bắt buộc và bỏ qua đúng nhóm video đã gắn deferred; hash, raw
    count và index parity vẫn là các cổng riêng trước khi tick R1.1.
    """
    required = [
        entry for entry in report
        if entry.round1_requirement == ROUND1_REQUIRED
    ]
    missing_required = sum(
        entry.download_status != "present" for entry in required
    )
    hashes_complete = all(entry.sha256 is not None for entry in required)
    extraction_complete = all(
        entry.extracted_status == "present"
        and entry.archive_member_files is not None
        and entry.archive_member_files > 0
        and entry.extracted_files == entry.archive_member_files
        for entry in required
    )
    return {
        "total": len(report),
        "present": sum(entry.download_status == "present" for entry in report),
        "missing": sum(entry.download_status == "missing" for entry in report),
        "required_round1": len(required),
        "required_round1_present": sum(
            entry.download_status == "present" for entry in required
        ),
        "required_round1_missing": missing_required,
        "deferred_not_required_round1": sum(
            entry.round1_requirement == ROUND1_DEFERRED for entry in report
        ),
        "round1_download_ready": missing_required == 0,
        "required_round1_hashes_complete": hashes_complete,
        "required_round1_extraction_complete": extraction_complete,
        "required_round1_archive_member_files": sum(
            entry.archive_member_files or 0 for entry in required
        ),
        "required_round1_extracted_files": sum(
            entry.extracted_files or 0 for entry in required
        ),
        "round1_operational_audit_complete": (
            missing_required == 0 and hashes_complete and extraction_complete
        ),
    }


def build_payload(
    manifest_path: Path,
    archives_dir: Path,
    extracted_root: Path | None,
    report: list[ManifestEntry],
    *,
    calculate_hash: bool,
    count_extracted: bool,
    reuse_hashes_from: Path | None = None,
    reuse_hashes_source_sha256: str | None = None,
) -> dict[str, object]:
    """Kết quả audit → artefact có provenance và snapshot tách lớp dữ liệu."""
    generated_at = datetime.now(timezone.utc).isoformat()
    git = _git_provenance()
    disk_path = extracted_root if extracted_root and extracted_root.exists() else archives_dir
    disk = shutil.disk_usage(disk_path)
    summary = summarize_report(report)
    payload: dict[str, object] = {
        "schema_version": 2,
        "generated_at_utc": generated_at,
        "git_commit": git.get("commit"),
        "git_dirty": git.get("dirty"),
        "git_error": git.get("error"),
        "audit_script_sha256": _sha256(Path(__file__)),
        "manifest": str(manifest_path.resolve()),
        "manifest_sha256": _sha256(manifest_path),
        "archives_dir": str(archives_dir.resolve()),
        "extracted_root": str(extracted_root.resolve()) if extracted_root else None,
        "invocation": {
            "manifest": str(manifest_path.resolve()),
            "archives_dir": str(archives_dir.resolve()),
            "extracted_root": str(extracted_root.resolve()) if extracted_root else None,
            "calculate_hash": calculate_hash,
            "count_extracted": count_extracted,
            "reuse_hashes_from": str(reuse_hashes_from.resolve())
            if reuse_hashes_from else None,
            "reuse_hashes_source_sha256": reuse_hashes_source_sha256,
        },
        "disk_snapshot": {
            "captured_at_utc": generated_at,
            "path": str(disk_path.resolve()),
            "free_bytes": disk.free,
            "free_gib": round(disk.free / (1024 ** 3), 3),
            "total_bytes": disk.total,
            "total_gib": round(disk.total / (1024 ** 3), 3),
        },
        **summary,
        "summary": summary,
        "raw_snapshot": raw_asset_snapshot(
            extracted_root,
            count_files=count_extracted,
        ) if extracted_root else None,
        "derived_metadata_snapshot": _derived_metadata_snapshot(),
        "external_evidence_references": {
            "live_es_milvus_and_preflight": {
                "status": "not_embedded_run_command_to_refresh",
                "command": "python scripts/preflight_check.py --profile release",
                "reference": "reports/C31_C32_C44_TECHNICAL_REPORT.md",
            },
            "frame_map_pixel_parity": {
                "status": "partial_84_of_873_video_verified",
                "reference": "reports/data_audit.md",
            },
        },
        "entries": [asdict(entry) for entry in report],
    }
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit manifest dữ liệu BTC (chỉ đọc).")
    parser.add_argument("manifest", type=Path, help="CSV BTC có Filenames và Download link")
    parser.add_argument("--archives-dir", type=Path, default=Path.home() / "Downloads")
    parser.add_argument("--extracted-root", type=Path)
    parser.add_argument("--hash", action="store_true", help="tính SHA-256 archive đã tải")
    parser.add_argument(
        "--reuse-hashes-from",
        type=Path,
        help="tái dùng SHA-256 từ audit cũ nếu tên + kích thước archive còn khớp",
    )
    parser.add_argument("--count-extracted", action="store_true")
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    if args.hash and args.reuse_hashes_from:
        parser.error("--hash và --reuse-hashes-from loại trừ nhau")
    reuse_hashes_source_sha256 = (
        _sha256(args.reuse_hashes_from) if args.reuse_hashes_from else None
    )
    reusable_hashes = (
        load_reusable_hashes(args.reuse_hashes_from)
        if args.reuse_hashes_from else None
    )

    report = audit_manifest(
        args.manifest,
        args.archives_dir,
        args.extracted_root,
        calculate_hash=args.hash,
        count_extracted=args.count_extracted,
        reusable_hashes=reusable_hashes,
    )
    payload = build_payload(
        args.manifest,
        args.archives_dir,
        args.extracted_root,
        report,
        calculate_hash=args.hash,
        count_extracted=args.count_extracted,
        reuse_hashes_from=args.reuse_hashes_from,
        reuse_hashes_source_sha256=reuse_hashes_source_sha256,
    )
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if payload["round1_download_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
