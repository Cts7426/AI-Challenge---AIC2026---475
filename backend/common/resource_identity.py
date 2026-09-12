"""Snapshot có hash nội dung để phân biệt code, data, cache và DB của từng run."""
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

from data.config import experiment as config


def manifest_id(manifest: dict) -> str:
    """Input JSON manifest; output SHA-256 canonical, không phụ thuộc thứ tự key."""
    from backend.tasks.runner import _json_safe
    raw = json.dumps(_json_safe(manifest), ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def file_identity(path: Path) -> dict:
    """Hash streaming; file thiếu/lỗi phải giữ trạng thái, không giả hash rỗng."""
    try:
        before = path.stat()
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            return {"status": "changed_during_capture"}
        return {"status": "available", "size_bytes": after.st_size, "sha256": digest}
    except FileNotFoundError:
        return {"status": "missing"}
    except OSError as error:
        return {"status": "unavailable", "error_type": type(error).__name__}


def _files(root: Path, patterns: tuple[str, ...]) -> dict:
    paths = {path for pattern in patterns for path in root.glob(pattern) if path.is_file()}
    return {path.relative_to(root).as_posix(): file_identity(path) for path in sorted(paths)}


def cache_identity(root: Path) -> dict:
    """Chụp cache trước/sau run; không đưa timestamp/access time vào hash."""
    paths = [Path(os.environ.get("LLM_CACHE_DIR", root / config.CACHE_DIRS[0])),
             Path(os.environ.get("QA_HYPOTHESIS_CACHE_DIR", root / config.CACHE_DIRS[1]))]
    return {str(path): {"exists": path.is_dir(), "files": _files(path, ("**/*.json",))}
            for path in paths}


def asset_identity(roots: list[Path], *, content_digests: bool) -> dict:
    """Hash pixel asset khi được yêu cầu; chưa hash phải thành gap, không giả đủ."""
    if not content_digests:
        return {"status": "not_hashed", "roots": [str(root) for root in roots]}
    entries = {str(root): _files(root, ("**/*.jpg", "**/*.jpeg", "**/*.png", "**/*.mp4"))
               for root in roots}
    complete = any(entries.values()) and all(
        item["status"] == "available" for files in entries.values() for item in files.values())
    return {"status": "available" if complete else "incomplete", "files": entries}


def reproducibility_gaps(manifest: dict) -> list[str]:
    """Các thiếu sót chặn nhận identity cho paired run, độc lập với hash bằng nhau."""
    gaps = []
    env = manifest.get("environment", {})
    vector = str(env.get("VECTOR_BACKEND") or "clip").strip().lower()
    if vector not in ("clip", "siglip2"):
        gaps.append("runtime:invalid_vector_backend")
    # H01 chỉ thu được weights CLIP hiện hành. Encoder khác phải có collector
    # riêng trước khi nhận baseline; có file CLIP không chứng minh SigLIP2.
    if vector not in manifest.get("model_weights_encoders", []):
        gaps.append(f"model_weights:{vector}:not_captured")
    if "siglip2" in manifest.get("required_vector_encoders", []) and "siglip2" not in manifest.get("model_weights_encoders", []):
        gaps.append("model_weights:siglip2:secondary_encoder_not_captured")
    model_key = {"api": "LLM_API_MODEL", "gemini": "LLM_GEMINI_MODEL", "local": "LLM_LOCAL_MODEL"}.get(env.get("LLM_BACKEND"))
    if model_key is None or not str(env.get(model_key) or "").strip():
        gaps.append("runtime:model_not_selected")
    if manifest.get("frame_map", {}).get("status") != "available":
        gaps.append("frame_map:unavailable")
    for section in ("source", "config", "data", "scorer", "model_weights"):
        files = manifest.get(section, {})
        if not files or any(item.get("status") != "available" for item in files.values()):
            gaps.append(f"{section}:incomplete")
    if manifest.get("assets", {}).get("status") != "available":
        gaps.append("assets:content_digest_missing")
    indexes = manifest.get("indexes", {})
    es = indexes.get("elasticsearch", {})
    if es.get("status") != "available":
        gaps.append("elasticsearch:unavailable")
    for name in config.ES_INDEXES:
        item = es.get("indexes", {}).get(name, {})
        if item.get("status") != "available" or item.get("count", 0) <= 0:
            gaps.append(f"elasticsearch:{name}:missing_or_empty")
        if not item.get("content_sha256") or item.get("hashed_count") != item.get("count"):
            gaps.append(f"elasticsearch:{name}:content_digest_incomplete")
    milvus = indexes.get("milvus", {})
    if milvus.get("status") != "available":
        gaps.append("milvus:unavailable")
    from data.config.siglip2_model import SIGLIP2_COLLECTION
    name = SIGLIP2_COLLECTION if vector == "siglip2" else "keyframes"
    item = milvus.get("collections", {}).get(name, {})
    count = int(item.get("stats", {}).get("row_count", 0))
    if item.get("status") != "available" or count <= 0:
        gaps.append(f"milvus:{name}:missing_or_empty")
    if not item.get("content_sha256") or item.get("hashed_count") != count:
        gaps.append(f"milvus:{name}:content_digest_incomplete")
    return gaps


def require_reproducible(manifest: dict) -> None:
    """Không cho hai manifest thiếu giống nhau vượt cổng chỉ vì hash bằng nhau."""
    if gaps := reproducibility_gaps(manifest):
        raise ValueError("identity chưa đủ để chạy baseline: " + "; ".join(gaps))


def stable_resource_id(manifest: dict) -> str:
    """Identity không gồm cache có thể append trong run; cache vẫn được hash riêng."""
    return manifest_id({key: value for key, value in manifest.items() if key != "cache"})


def validate_resume_identity(before: dict, current: dict) -> None:
    """Resume chỉ nhận nguyên tài nguyên và cache append; không đổi evidence cũ."""
    if stable_resource_id(before) != stable_resource_id(current):
        raise ValueError("resource/code/model khác run đã khóa")
    for root, entry in before.get("cache", {}).items():
        now = current.get("cache", {}).get(root, {}).get("files", {})
        for name, identity in entry.get("files", {}).items():
            if now.get(name) != identity:
                raise ValueError(f"cache cũ đã đổi hoặc mất: {root}/{name}")


def _function_hashes(root: Path, files: dict) -> dict:
    """Hash từng hàm cả prompt literal; hash toàn file vẫn khóa imports/constants."""
    hashes = {}
    for name in files:
        if not name.endswith(".py"):
            continue
        source = (root / name).read_text(encoding="utf-8-sig")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                body = ast.get_source_segment(source, node) or ""
                hashes[f"{name}:{node.lineno}:{node.name}"] = hashlib.sha256(body.encode()).hexdigest()
    return hashes


def index_identity(*, content_digests: bool = False) -> dict:
    """Đọc DB qua connect tập trung; digest tùy chọn đọc toàn bộ nội dung không sửa index."""
    from backend.tasks.runner import _json_safe
    result = {"elasticsearch": {}, "milvus": {}}
    try:
        from backend.indexing.es_client import connect
        es = connect()
        try:
            result["elasticsearch"]["server"] = dict(es.info())
            indexes = {}
            result["elasticsearch"]["indexes"] = indexes
            for name in config.ES_INDEXES:
                if not es.indices.exists(index=name):
                    indexes[name] = {"status": "missing"}
                    continue
                entry = {"status": "available", "metadata": dict(es.indices.get(index=name)),
                         "count": es.count(index=name)["count"]}
                indexes[name] = entry
                if content_digests:
                    from elasticsearch.helpers import scan
                    hashes = [manifest_id({"id": row["_id"], "source": row["_source"]})
                              for row in scan(es, index=name, query={"query": {"match_all": {}}}, size=1000)]
                    entry["content_sha256"] = manifest_id({"documents": sorted(hashes)})
                    entry["hashed_count"] = len(hashes)
            result["elasticsearch"]["status"] = "available"
        finally:
            es.close()
    except Exception as error:
        result["elasticsearch"].update(status="unavailable", error_type=type(error).__name__)
    try:
        from backend.indexing.milvus_client import connect
        client = connect()
        try:
            collections = {}
            result["milvus"]["collections"] = collections
            for name in sorted(client.list_collections()):
                entry = {"status": "available", "schema": client.describe_collection(name),
                         "stats": client.get_collection_stats(name),
                         "indexes": {}}
                collections[name] = entry
                for index in client.list_indexes(name):
                    entry["indexes"][index] = client.describe_index(name, index)
                if content_digests:
                    iterator = client.query_iterator(name, batch_size=1000, output_fields=["*"])
                    hashes = []
                    try:
                        while rows := iterator.next():
                            hashes.extend(manifest_id(row) for row in rows)
                    finally:
                        iterator.close()
                    entry["content_sha256"] = manifest_id({"entities": sorted(hashes)})
                    entry["hashed_count"] = len(hashes)
            result["milvus"]["status"] = "available"
        finally:
            client.close()
    except Exception as error:
        result["milvus"].update(status="unavailable", error_type=type(error).__name__)
    return _json_safe(result)


def capture_manifest(root: Path, live: bool, *, content_digests: bool = False) -> dict:
    """Input repo root và chế độ read-only DB; output identity không chứa credential.

    Không tự chọn model, tải weight, rebuild hay reindex. Thiếu thành phần được
    ghi rõ; caller không được xem missing/not_probed như tài nguyên đã khóa.
    """
    from backend.tasks.runner import runtime_manifest
    from data.config.frame_assets import RAW_KEYFRAMES_DIR, DERIVED_KEYFRAMES_DIR
    from data.config.search_weights import BRANCHES
    from data.config.siglip2_model import vector_backend
    from backend.tasks.runner import KIS_BRANCH_OVERRIDE
    primary_encoder = vector_backend()
    required_encoders = [primary_encoder]
    if BRANCHES.get("vector_siglip2") or KIS_BRANCH_OVERRIDE.get("vector_siglip2"):
        required_encoders.append("clip" if primary_encoder == "siglip2" else "siglip2")
    source = _files(root, config.SOURCE_GLOBS)
    def git(*args):
        try:
            completed = subprocess.run(["git", "--no-optional-locks", *args], cwd=root,
                                       capture_output=True, text=True, timeout=30)
            return completed.stdout.strip() if completed.returncode == 0 else "unavailable"
        except (OSError, subprocess.TimeoutExpired):
            return "unavailable"
    return {
        "schema_version": 1,
        "git": {"commit": git("rev-parse", "HEAD"), "tree": git("rev-parse", "HEAD^{tree}")},
        "source": source, "functions": _function_hashes(root, source),
        "config": _files(root, config.CONFIG_GLOBS),
        "data": _files(root, config.DATA_GLOBS),
        "frame_map": file_identity(root / "data/derived/frame_map.parquet"),
        "assets": asset_identity([RAW_KEYFRAMES_DIR, DERIVED_KEYFRAMES_DIR], content_digests=content_digests),
        "model_weights": _files(Path.home(), config.MODEL_GLOBS),
        "model_weights_encoders": ["clip"],
        "required_vector_encoders": required_encoders,
        "runtime": {"executable": sys.executable, "python": sys.version,
                    "platform": platform.platform(), "machine": platform.machine(),
                    "dependencies": dict(sorted((d.metadata["Name"], d.version)
                                                for d in importlib.metadata.distributions() if d.metadata["Name"]))},
        "environment": {key: os.environ.get(key) for key in config.RUNTIME_ENV_KEYS},
        "production_runtime": runtime_manifest(),
        "scorer": _files(root, ("dev_set/tools/scorer*.py", "data/config/scoring.py", "data/config/qa_evaluation.py")),
        "cache": cache_identity(root),
        "indexes": index_identity(content_digests=content_digests) if live else {"status": "not_probed"},
    }
