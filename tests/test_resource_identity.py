"""Identity phải phản ánh nội dung, không dùng timestamp hoặc chỉ số lượng file."""
import importlib


def test_file_identity_changes_when_bytes_change_without_size_change(tmp_path):
    identity = importlib.import_module("backend.common.resource_identity")
    path = tmp_path / "frame_map.parquet"
    path.write_bytes(b"old-map")
    before = identity.file_identity(path)
    path.write_bytes(b"new-map")
    after = identity.file_identity(path)
    assert before["sha256"] != after["sha256"]
    assert before["size_bytes"] == after["size_bytes"]


def test_manifest_hash_is_canonical_but_detects_resource_change():
    identity = importlib.import_module("backend.common.resource_identity")
    assert identity.manifest_id({"b": 2, "a": 1}) == identity.manifest_id({"a": 1, "b": 2})
    assert identity.manifest_id({"uuid": "old"}) != identity.manifest_id({"uuid": "new"})


def test_missing_resource_is_explicit(tmp_path):
    identity = importlib.import_module("backend.common.resource_identity")
    assert identity.file_identity(tmp_path / "missing")["status"] == "missing"


def test_capture_offline_has_no_credential_and_hashes_prompt(tmp_path, monkeypatch):
    identity = importlib.import_module("backend.common.resource_identity")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-appear")
    monkeypatch.setenv("LLM_BACKEND", "api")
    monkeypatch.setenv("LLM_API_MODEL", "operator-model")
    path = tmp_path / "backend" / "llm" / "adapter.py"
    path.parent.mkdir(parents=True)
    path.write_text('def llm(): return "prompt-one"', encoding="utf-8")
    first = identity.capture_manifest(tmp_path, live=False)
    path.write_text('def llm(): return "prompt-two"', encoding="utf-8")
    second = identity.capture_manifest(tmp_path, live=False)
    assert first["source"] != second["source"]
    assert "must-not-appear" not in str(first)
    assert first["indexes"]["status"] == "not_probed"


def test_unavailable_indexes_cannot_be_accepted_as_equal_resources():
    identity = importlib.import_module("backend.common.resource_identity")
    with __import__("pytest").raises(ValueError, match="identity"):
        identity.require_reproducible({"indexes": {"status": "not_probed"}})


def test_schema_and_count_without_content_digest_are_not_paired_identity():
    identity = importlib.import_module("backend.common.resource_identity")
    manifest = {
        "environment": {"LLM_BACKEND": "api", "LLM_API_MODEL": "operator"},
        "frame_map": {"status": "available", "sha256": "map"},
        "source": {"source": {}}, "config": {"config": {}}, "scorer": {"scorer": {}},
        "data": {"data": {}}, "model_weights": {"weight": {"status": "available"}},
        "indexes": {
            "elasticsearch": {"status": "available", "indexes": {
                name: {"status": "available", "count": 1, "metadata": {"uuid": "id"}}
                for name in ("metadata", "objects", "ocr", "asr")}},
            "milvus": {"status": "available", "collections": {
                "keyframes": {"status": "available", "stats": {"row_count": 1}, "schema": {"collection_id": 1}}}},
        },
    }
    gaps = identity.reproducibility_gaps(manifest)
    assert any("content_digest" in gap for gap in gaps)


def test_cache_identity_uses_production_qa_override(tmp_path, monkeypatch):
    identity = importlib.import_module("backend.common.resource_identity")
    cache = tmp_path / "custom_qa"
    cache.mkdir()
    (cache / "one.json").write_text('{"output":"one"}', encoding="utf-8")
    monkeypatch.setenv("QA_HYPOTHESIS_CACHE_DIR", str(cache))
    assert "one.json" in identity.cache_identity(tmp_path)[str(cache)]["files"]


def test_asset_identity_detects_changed_pixels(tmp_path):
    identity = importlib.import_module("backend.common.resource_identity")
    image = tmp_path / "001.jpg"
    image.write_bytes(b"old-pixels")
    before = identity.asset_identity([tmp_path], content_digests=True)
    image.write_bytes(b"new-pixels")
    after = identity.asset_identity([tmp_path], content_digests=True)
    assert before != after


def test_resume_allows_cache_append_but_rejects_replaced_evidence():
    identity = importlib.import_module("backend.common.resource_identity")
    before = {"data": {"map": "fixed"}, "cache": {"cache": {"files": {"a.json": {"sha256": "a"}}}}}
    appended = {"data": {"map": "fixed"}, "cache": {"cache": {"files": {"a.json": {"sha256": "a"}, "b.json": {"sha256": "b"}}}}}
    identity.validate_resume_identity(before, appended)
    appended["cache"]["cache"]["files"]["a.json"]["sha256"] = "changed"
    with __import__("pytest").raises(ValueError, match="cache"):
        identity.validate_resume_identity(before, appended)


def test_siglip_cannot_use_clip_weights_for_completeness():
    identity = importlib.import_module("backend.common.resource_identity")
    gaps = identity.reproducibility_gaps({
        "environment": {"VECTOR_BACKEND": "siglip2"},
        "model_weights": {".cache/clip/ViT-B-32.pt": {"status": "available", "sha256": "clip"}},
    })
    assert any("siglip2" in gap and "weights" in gap for gap in gaps)
