"""Chụp bằng chứng chỉ đọc; không import pipeline, gọi LLM hay thay dữ liệu lịch sử."""
from __future__ import annotations

import ast
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from datetime import datetime, timezone
import zipfile

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
CAPTURE = OUT / "baseline_capture"


def digest(path: Path) -> str:
    """Đọc file theo khối và trả SHA-256; không đổi bytes nguồn."""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def git(*args: str) -> str:
    """Đọc Git không refresh index; timeout hữu hạn để không treo audit."""
    result = subprocess.run(
        ["git", "--no-optional-locks", *args], cwd=ROOT, capture_output=True,
        encoding="utf-8", errors="replace", timeout=30,
    )
    if result.returncode:
        raise RuntimeError(result.stderr)
    return result.stdout


def file_record(path: Path) -> dict:
    """Input file thật; output identity bytes, không suy provenance từ timestamp."""
    return {"path": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size,
            "sha256": digest(path)}


def main() -> None:
    """Chỉ ghi một snapshot mới; cấm chạy đè baseline đã đóng băng."""
    CAPTURE.mkdir(exist_ok=False)
    for name, args in {
        "git_status.txt": ("status", "--porcelain=v1", "--untracked-files=all"),
        "git_diff.patch": ("diff", "--binary", "--", ".claude/launch.json", "scripts/txt_to_run_queries.py"),
        "git_staged.patch": ("diff", "--cached", "--binary"),
        "git_log.txt": ("log", "-30", "--format=%H %aI %s"),
    }.items():
        (CAPTURE / name).write_text(git(*args), encoding="utf-8")
    tracked = git("ls-files", "-z").split("\0")
    untracked = git("ls-files", "--others", "--exclude-standard", "-z").split("\0")
    roots = {"backend", "data/config", "dev_set/tools", "dev_set/tests", "dev_set/queries",
             "dev_set/ground_truth", "dev_set/manifests", "scripts", "tests", "preprocessing", "app"}
    root_files = {"AGENTS.md", "BUILD_TASKS.md", "ARCHITECTURE.md", "README.md", "CLAUDE.md",
                  "run.py", "run_minimal.py", "pytest.ini", "docker-compose.yml", ".gitattributes", ".gitignore",
                  ".claude/launch.json", "embedEtcd.yaml"}
    source_paths = []
    for name in sorted(set(tracked + untracked)):
        path = ROOT / name
        if not name or not path.is_file() or path.is_symlink():
            continue
        if name in root_files or any(name.startswith(prefix + "/") for prefix in roots):
            if path.suffix.lower() in {".py", ".json", ".jsonl", ".yaml", ".yml", ".md", ".txt", ".ini", ".toml", ".ps1", ".sh"} or name in root_files:
                if ".env" not in path.name and path.stat().st_size < 20_000_000:
                    source_paths.append(path)
    sources = [file_record(p) for p in source_paths]
    with zipfile.ZipFile(CAPTURE / "source_snapshot.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for path in source_paths:
            archive.write(path, path.relative_to(ROOT).as_posix())
    historical = []
    for dirname in ("reports/internal_reporting_audit_20260909", "reports/technical_report_draft_20260910"):
        historical.extend(p for p in (ROOT / dirname).rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    report_pdf = ROOT / "output/pdf/ThanhNghe_TechnicalReport.pdf"
    if report_pdf.is_file():
        historical.append(report_pdf)
    with zipfile.ZipFile(CAPTURE / "historical_report_v1_and_audits.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(historical):
            archive.write(path, path.relative_to(ROOT).as_posix())
    data_paths = sorted(p for p in (ROOT / "data/derived").glob("*")
                        if p.is_file() and (p.suffix == ".parquet" or p.name.endswith(".meta.json")))
    data_paths += sorted((ROOT / "data/manifests").rglob("*.json")) if (ROOT / "data/manifests").exists() else []
    data_paths += [ROOT / "reports/BATCH1_OPERATIONAL_MANIFEST_20260821.json"]
    configs = {}
    for path in sorted((ROOT / "data/config").glob("*.py")):
        code = path.read_text(encoding="utf-8-sig")
        configs[path.relative_to(ROOT).as_posix()] = [ast.get_source_segment(code, n)
            for n in ast.parse(code).body if isinstance(n, (ast.Assign, ast.AnnAssign))]
    env_names = ("LLM_BACKEND", "LLM_API_MODEL", "LLM_GEMINI_MODEL", "LLM_LOCAL_MODEL",
                 "QA_INFERENCE_MODE", "VECTOR_BACKEND", "LLM_CACHE_DIR", "LLM_NO_CACHE",
                 "KEYFRAMES_DIR", "DERIVED_KEYFRAMES_DIR")
    runtime = {"executable": sys.executable, "version": sys.version,
               "platform": platform.platform(), "machine": platform.machine(),
               "packages": sorted(({"name": d.metadata["Name"], "version": d.version}
                   for d in importlib.metadata.distributions()), key=lambda r: r["name"].lower())}
    manifest = {
        "schema_version": 1, "baseline_id": "PP-B0-20260911",
        "label": "POST-PRELIMINARY / POST-COMPETITION INTERNAL EVALUATION",
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "repo": str(ROOT), "commit": git("rev-parse", "HEAD").strip(),
        "branch": git("branch", "--show-current").strip(),
        "tree": git("rev-parse", "HEAD^{tree}").strip(),
        "baseline_kind": "commit_plus_dirty_working_tree_source_snapshot",
        "source_files": sources, "historical_files": [file_record(p) for p in sorted(historical)],
        "data_files": [file_record(p) for p in data_paths], "configuration_assignments": configs,
        "capture_runtime": runtime, "process_configuration": {k: os.environ.get(k) for k in env_names},
        "secret_presence_only": {k: bool(os.environ.get(k)) for k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY")},
        "explicit_exclusions": ["Không sao chép .env hoặc secret", "Không backup live ES/Milvus",
            "Raw archive/pixel/model weights/cache lớn chỉ định danh qua audit và inventory; chưa có immutable backup",
            "Source snapshot là các đường dẫn source/config/test/evaluation liệt kê; Git commit giữ tham chiếu phần còn lại"],
        "competition_score_attribution": {"round1": "8.6/13", "round2": "13.6/15", "round3": "11.8/17",
            "scope": "FINAL COMPETITION WORKFLOW có retrieval nội bộ, người kiểm/xếp hạng/tìm thủ công và ChatGPT/Claude bên ngoài tùy query",
            "not_an_autonomous_benchmark": True},
    }
    (CAPTURE / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    checksums = [file_record(p) for p in sorted(CAPTURE.iterdir()) if p.is_file()]
    (CAPTURE / "checksums.json").write_text(json.dumps(checksums, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"baseline": manifest["baseline_id"], "commit": manifest["commit"],
                      "source_files": len(sources), "historical_files": len(historical),
                      "data_files": len(data_paths), "manifest": str(CAPTURE / "manifest.json")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
