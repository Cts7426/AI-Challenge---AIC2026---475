"""Instrumentation phải giữ kết quả thật và phân biệt các trạng thái nhánh."""
import importlib

import pytest


def test_search_trace_preserves_output_and_branch_states(monkeypatch):
    trace = importlib.import_module("backend.common.retrieval_trace")
    search = importlib.import_module("backend.retrieval.search")
    row = {"keyframe_id": "V#k1", "video_id": "V", "frame_idx": 12,
           "timestamp_ms": 400, "cos": .7}
    monkeypatch.setattr(search, "_branch_vector", lambda *a: [dict(row)])
    monkeypatch.setattr(search, "_branch_metadata", lambda *a: [])
    def fail(*args):
        raise ConnectionError("offline fixture")
    monkeypatch.setattr(search, "_branch_ocr", fail)
    monkeypatch.setattr(search, "_fill_from_milvus", lambda rows: None)
    monkeypatch.setattr(search, "_shot_map", lambda: {})
    branches = {name: name in ("vector", "metadata", "ocr") for name in search.BRANCHES}
    plain = search.search("câu gốc", "actual english", branches=branches, group_by_shot=False)
    with trace.capture_retrieval() as calls:
        observed = search.search("câu gốc", "actual english", branches=branches, group_by_shot=False)
    assert observed == plain
    assert len(observed) == 1
    call = calls[0]
    assert call["executed_query"]["query_en"] == "actual english"
    assert call["branches"]["vector"]["status"] == "success"
    assert call["branches"]["metadata"]["status"] == "zero_hits"
    assert call["branches"]["ocr"]["status"] == "failed"
    assert call["branches"]["objects"]["status"] == "disabled"
    assert call["branches"]["vector"]["candidates"] == [row]
    assert call["fused_ranking"][0]["keyframe_id"] == "V#k1"
    assert call["reranked_ranking"] == call["final_ranking"]
    observed[0]["score"] = -99
    assert call["final_ranking"][0]["score"] > 0


def test_trace_keeps_invalid_query_failure_without_swallowing():
    trace = importlib.import_module("backend.common.retrieval_trace")
    search = importlib.import_module("backend.retrieval.search")
    with trace.capture_retrieval() as calls:
        with pytest.raises(ValueError):
            search.search("q", video_prior_alpha=2)
    assert calls[0]["error"]["type"] == "ValueError"
    assert calls[0]["status"] == "failed"


def test_ocr_probe_errors_are_not_reported_as_zero_hits(monkeypatch):
    trace = importlib.import_module("backend.common.retrieval_trace")
    search = importlib.import_module("backend.retrieval.search")
    monkeypatch.setattr(importlib.import_module("data.config.token_probe"), "ENABLED", True)
    def fail(*args, **kwargs):
        raise ConnectionError("probe unavailable")
    monkeypatch.setattr(search, "_branch_ocr", fail)
    branches = {name: name == "ocr_probe" for name in search.BRANCHES}
    with trace.capture_retrieval() as calls:
        assert search.search("remember", "remember", branches=branches) == []
    assert calls[0]["branches"]["ocr_probe"]["status"] == "failed"


def test_trake_searches_in_workers_retain_query_trace(monkeypatch):
    trace = importlib.import_module("backend.common.retrieval_trace")
    trake = importlib.import_module("backend.tasks.trake")
    @trace.traced_search
    def fake_search(query_vi, **kwargs):
        return []
    monkeypatch.setattr(trake, "search", fake_search)
    monkeypatch.setattr(trake, "TRAKE_ASR_CONTEXT_BONUS_WEIGHT", 0)
    with trace.capture_retrieval() as calls:
        assert trake.trake_search(["event one", "event two"]) == []
    actual = {row["input"]["query_vi"] for row in calls}
    assert {"event one", "event two"} <= actual
