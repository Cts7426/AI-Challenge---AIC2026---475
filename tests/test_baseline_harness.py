"""Harness đi qua production runner, không được biến lỗi thành baseline hợp lệ."""
import importlib
import json

import pytest


def test_mapping_mismatch_is_detected_and_unmapped_frame_is_explicit(monkeypatch):
    harness = importlib.import_module("scripts.run_reproducible_baseline")
    from data.config.submit_format import Answer
    monkeypatch.setattr(importlib.import_module("backend.indexing.frame_map"),
                        "load_frame_map", lambda: {"V#k1": 12})
    monkeypatch.setattr(harness, "_keyframe_videos", lambda: {"V#k1": "V"}, raising=False)
    rows, errors = harness.audit_mapping([Answer("V", (13,), keyframe_id="V#k1"), Answer("V", (14,))])
    assert errors == 1
    assert rows[0]["mapped_frame"] == 12
    assert rows[1]["status"] == "no_keyframe_reference"


def test_mapping_checks_video_and_trake_event_position(monkeypatch):
    harness = importlib.import_module("scripts.run_reproducible_baseline")
    from data.config.submit_format import Answer
    monkeypatch.setattr(importlib.import_module("backend.indexing.frame_map"),
                        "load_frame_map", lambda: {"V#k1": 12, "V#k2": 24})
    monkeypatch.setattr(harness, "_keyframe_videos", lambda: {"V#k1": "V", "V#k2": "V"}, raising=False)
    _, errors = harness.audit_mapping([Answer("OTHER", (12,), keyframe_id="V#k1")])
    assert errors == 1
    records, errors = harness.audit_candidate_mapping({"task_type": "TRAKE", "search_rows": [
        {"video_id": "V", "keyframe_ids": ["V#k1", "V#k2"], "frame_ids": [24, 12]}]})
    assert errors == 2
    assert [row["event_index"] for row in records] == [0, 1]


def test_failed_production_query_still_writes_trace(tmp_path, monkeypatch):
    harness = importlib.import_module("scripts.run_reproducible_baseline")
    runner = importlib.import_module("backend.tasks.runner")
    query = {"query_id": "failed", "task_type": "KIS", "query_vi": "q", "query_en": "q"}
    def fail(query, **kwargs):
        error = RuntimeError("no candidates")
        raise runner.SolveQueryError(str(error), runner.failure_trace(query, error, failure_class="retrieval_miss"))
    monkeypatch.setattr(runner, "solve_query", fail)
    record = harness.execute_query(query, tmp_path, "identity", instrumentation=True, qa_policy="robust")
    assert record["task_output"]["status"] == "failed"
    assert record["export_status"] == "not_exported"
    assert record["runtime_manifest_id"] == "identity"


def test_harness_does_not_accept_output_directory_reuse(tmp_path):
    harness = importlib.import_module("scripts.run_reproducible_baseline")
    with pytest.raises(FileExistsError):
        harness.create_run_directory(tmp_path)


def test_harness_freezes_query_identity_including_qa_anchors():
    harness = importlib.import_module("scripts.run_reproducible_baseline")
    query = {"query_id": "qa", "task_type": "QA", "query_vi": "q", "anchors": ["first"]}
    first = harness.query_identity(query)
    second = harness.query_identity({**query, "anchors": ["second"]})
    assert first != second


def test_real_kis_runner_allocation_export_has_same_output_with_trace(tmp_path, monkeypatch):
    harness = importlib.import_module("scripts.run_reproducible_baseline")
    search = importlib.import_module("backend.retrieval.search")
    runner = importlib.import_module("backend.tasks.runner")
    from backend.indexing.frame_map import load_frame_map
    key, frame = next(iter(load_frame_map().items()))
    video = key.split("#")[0]
    row = {"keyframe_id": key, "video_id": video, "frame_idx": frame, "timestamp_ms": 1000, "cos": .7}
    monkeypatch.setattr(search, "_branch_vector", lambda *args: [dict(row)])
    monkeypatch.setattr(search, "_fill_from_milvus", lambda rows: None)
    monkeypatch.setattr(search, "BRANCHES", {name: name == "vector" for name in search.BRANCHES})
    monkeypatch.setattr(runner, "KIS_BRANCH_OVERRIDE", {})
    query = {"query_id": "fixture", "task_type": "KIS", "query_vi": "xe máy", "query_en": "motorcycle"}
    plain = harness.execute_query(query, tmp_path / "off", "fixture-identity", instrumentation=False, qa_policy="robust")
    traced = harness.execute_query(query, tmp_path / "on", "fixture-identity", instrumentation=True, qa_policy="robust")
    assert plain["task_output"]["status"] == traced["task_output"]["status"] == "success"
    assert traced["export_status"] == "written"
    assert plain["export_ranking"] == traced["export_ranking"]
    assert len(traced["export_ranking"]) == 100
    assert traced["mapping_violations"] == traced["export_violations"] == 0
    assert len(traced["search_calls"]) == 1
    # Artefact fixture dùng để soi trace; không được gọi là live accuracy baseline.
    (tmp_path / "instrumentation_fixture.json").write_text(json.dumps(traced, ensure_ascii=False), encoding="utf-8")


def test_resume_keeps_completed_query_but_rejects_changed_input(tmp_path):
    harness = importlib.import_module("scripts.run_reproducible_baseline")
    query = {"query_id": "q", "task_type": "KIS", "query_vi": "original"}
    record = {"input": query, "query_sha256": harness.query_identity(query), "runtime_manifest_id": "id",
              "task_output": {"status": "failed"}, "export_status": "not_exported"}
    (tmp_path / "queries.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
    assert harness.read_checkpoint(tmp_path, [query], "id")["q"] == record
    with pytest.raises(ValueError, match="query"):
        harness.read_checkpoint(tmp_path, [{**query, "query_vi": "changed"}], "id")


def test_resume_rejects_changed_csv(tmp_path):
    harness = importlib.import_module("scripts.run_reproducible_baseline")
    from backend.common.resource_identity import file_identity
    (tmp_path / "submission").mkdir()
    csv = tmp_path / "submission/q.csv"
    csv.write_text("original", encoding="utf-8")
    query = {"query_id": "q"}
    record = {"input": query, "query_sha256": harness.query_identity(query), "runtime_manifest_id": "id",
              "task_output": {"status": "success"}, "export_status": "written", "export_files": {"q.csv": file_identity(csv)}}
    (tmp_path / "queries.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
    csv.write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="CSV"):
        harness.read_checkpoint(tmp_path, [query], "id")


def test_resume_rejects_corrupt_checkpoint_without_rewriting_it(tmp_path):
    harness = importlib.import_module("scripts.run_reproducible_baseline")
    path = tmp_path / "queries.jsonl"
    path.write_text('{"partial":', encoding="utf-8")
    with pytest.raises(ValueError, match="checkpoint"):
        harness.read_checkpoint(tmp_path, [], "id")
    assert path.read_text(encoding="utf-8") == '{"partial":'


def test_resume_protects_cache_generated_after_first_query(tmp_path):
    harness = importlib.import_module("scripts.run_reproducible_baseline")
    from backend.common.resource_identity import manifest_id
    query = {"query_id": "q"}
    cache = {"cache": {"files": {"generated.json": {"sha256": "original"}}}}
    record = {"input": query, "query_sha256": harness.query_identity(query), "runtime_manifest_id": "id",
              "task_output": {"status": "failed"}, "export_status": "not_exported",
              "cache_after": cache, "cache_after_id": manifest_id(cache)}
    (tmp_path / "queries.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
    changed = {"cache": {"files": {"generated.json": {"sha256": "replaced"}}}}
    with pytest.raises(ValueError, match="cache"):
        harness.read_checkpoint(tmp_path, [query], "id", current_cache=changed)
