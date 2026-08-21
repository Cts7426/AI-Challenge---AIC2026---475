"""Fingerprint của evaluation phải deterministic và chặn resume trộn Q&A mode."""

from __future__ import annotations

import pytest

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
