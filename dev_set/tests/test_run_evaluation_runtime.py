"""Fingerprint của evaluation phải deterministic và chặn resume trộn Q&A mode."""

from __future__ import annotations

import builtins
import json

import pytest

from backend.tasks.runner import runtime_fingerprint as query_runtime_fingerprint
from dev_set.tools.run_evaluation import (
    RUN_SNAPSHOT_SCHEMA_VERSION,
    _hash_json,
    _runtime_snapshot,
    _validate_resume_snapshot,
)


def test_hash_json_khong_phu_thuoc_thu_tu_key():
    assert _hash_json({"a": 1, "b": 2}) == _hash_json({"b": 2, "a": 1})


def test_runtime_fingerprint_khoa_qa_mode_va_model_env_da_chon(monkeypatch):
    monkeypatch.setenv("QA_INFERENCE_MODE", "legacy")
    monkeypatch.setenv("LLM_API_MODEL", "sonnet-manual-a")
    legacy_a, configs_a, provenance_a = _runtime_snapshot("tune")

    monkeypatch.setenv("LLM_API_MODEL", "sonnet-manual-b")
    legacy_b, configs_b, provenance_b = _runtime_snapshot("tune")
    assert configs_a == configs_b
    assert provenance_a != provenance_b
    assert _hash_json(legacy_a) != _hash_json(legacy_b)

    monkeypatch.setenv("QA_INFERENCE_MODE", "two_stage")
    two_stage, _, _ = _runtime_snapshot("tune")
    assert _hash_json(two_stage) != _hash_json(legacy_a)


def test_query_fingerprint_dung_runner_va_khong_doi_theo_split():
    """Bắt lỗi evaluator truyền artifact hash chứa split vào solve_query."""
    tune, _, _ = _runtime_snapshot("tune")
    holdout, _, _ = _runtime_snapshot("holdout")
    expected = query_runtime_fingerprint()

    assert tune.get("query_runtime_fingerprint") == expected
    assert holdout.get("query_runtime_fingerprint") == expected
    assert _hash_json(tune) != _hash_json(holdout), "artifact vẫn phải phân biệt split"


def test_resume_snapshot_chi_nhan_dung_fingerprint():
    fingerprint = "abc123"
    snapshot = {
        "schema_version": RUN_SNAPSHOT_SCHEMA_VERSION,
        "run_id": "run-1",
        "runtime_fingerprint": fingerprint,
    }
    assert _validate_resume_snapshot(snapshot, fingerprint) == "run-1"
    with pytest.raises(RuntimeError, match="khác run cũ"):
        _validate_resume_snapshot(snapshot, "different")
    with pytest.raises(RuntimeError, match="schema v2"):
        _validate_resume_snapshot({"runtime_fingerprint": fingerprint}, fingerprint)


def test_run_evaluation_restore_env_khi_exception_sau_khi_setup(
    monkeypatch, tmp_path,
):
    """Bắt leak env khiến lần run sau nhận nhầm run/query/evidence path cũ."""
    import dev_set.tools.run_evaluation as evaluation

    monkeypatch.setenv("LLM_RUN_ID", "before-run")
    monkeypatch.setenv("LLM_QUERY_ID", "before-query")
    monkeypatch.setenv("QA_EVIDENCE_LOG_PATH", "before-evidence")
    monkeypatch.setattr(evaluation.sys, "argv", [
        "run_evaluation.py", "--split", "tune", "--resume", str(tmp_path),
    ])
    monkeypatch.setattr(evaluation, "load_jsonl", lambda path: (
        [{
            "query_id": "q1", "task_type": "KIS", "query_vi": "một người",
            "split": "tune",
        }]
        if path.name == "tune_kis.jsonl"
        else [{
            "query_id": "q1", "task_type": "KIS", "video_id": "L01_V001",
            "frame_start": 1, "frame_end": 2,
        }]
        if path.name == "tune_gt.jsonl" else []
    ))
    monkeypatch.setattr(evaluation, "es_connect", lambda: None)
    monkeypatch.setattr(evaluation, "milvus_connect", lambda: None)
    monkeypatch.setattr(evaluation, "load_frame_map", lambda: {})
    monkeypatch.setattr(evaluation, "_validate_resume_snapshot", lambda *a: "resume-run")
    (tmp_path / "config_snapshot.json").write_text(
        json.dumps({"schema_version": RUN_SNAPSHOT_SCHEMA_VERSION}), encoding="utf-8"
    )

    def fail_after_env_setup(*args, **kwargs):
        raise RuntimeError("forced after env setup")

    monkeypatch.setattr(builtins, "open", fail_after_env_setup)
    with pytest.raises(RuntimeError, match="forced after env setup"):
        evaluation.run_evaluation()

    assert evaluation.os.environ["LLM_RUN_ID"] == "before-run"
    assert evaluation.os.environ["LLM_QUERY_ID"] == "before-query"
    assert evaluation.os.environ["QA_EVIDENCE_LOG_PATH"] == "before-evidence"
