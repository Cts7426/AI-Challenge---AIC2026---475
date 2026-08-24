"""Release rehearsal chỉ tạo ZIP/receipt sau mọi gate fail-closed."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import backend.export.release_rehearsal as release_rehearsal
from backend.export import Issue, QuerySubmission
from backend.export.release_rehearsal import (
    ReleaseBlocked,
    assess_release_batch,
    build_evidence_cache_manifest,
    create_release_package,
)
from data.config.submit_format import Answer


FP = "a" * 64
SCORER_SHA = "6" * 64


@pytest.fixture(autouse=True)
def fixed_release_context(monkeypatch):
    monkeypatch.setattr(release_rehearsal, "runtime_fingerprint", lambda: FP, raising=False)
    monkeypatch.setattr(
        release_rehearsal,
        "_current_scorer_source_sha256",
        lambda: SCORER_SHA,
        raising=False,
    )


def _hypothesis() -> dict:
    return {
        "answer_text": "đỏ",
        "video_id": "L01_V001",
        "shot_id": "L01_V001_S0001",
        "keyframe_id": "L01_V001_000001",
        "evidence_frame_idx": 10,
        "confidence": 0.9,
        "evidence_hash": "b" * 64,
        "provenance": "visual",
        "evidence_type": "visual",
        "answer_mode": "visual_attribute",
    }


def _queries() -> list[dict]:
    return [
        {"query_id": "q-kis", "task_type": "KIS", "query_vi": "a"},
        {"query_id": "q-qa", "task_type": "QA", "query_vi": "màu gì"},
    ]


def _traces() -> list[dict]:
    hypothesis = _hypothesis()
    return [
        {
            "query_id": "q-kis", "task_type": "KIS", "status": "success",
            "retryable": False, "runtime_fingerprint": FP, "qa_hypotheses": [],
        },
        {
            "query_id": "q-qa", "task_type": "QA", "status": "success",
            "retryable": False, "runtime_fingerprint": FP,
            "query_plan": {"query_vi": "màu gì", "question_vi": "màu gì"},
            "qa_hypotheses": [hypothesis],
            "answers": [{
                "video_id": hypothesis["video_id"],
                "frame_ids": [hypothesis["evidence_frame_idx"]],
                "answer_text": hypothesis["answer_text"],
                "keyframe_id": hypothesis["keyframe_id"],
            }],
        },
    ]


def _cache_manifest() -> dict:
    return {"entries": [{
        "path": "cache/a.json",
        "parse_status": "valid",
        "evidence_digest": "b" * 64,
        "runtime_fingerprint": FP,
        "query_sha256": hashlib.sha256("màu gì".encode("utf-8")).hexdigest(),
        "full_query_sha256": hashlib.sha256("màu gì".encode("utf-8")).hexdigest(),
    }]}


def _promotion_audit(
    *, runtime_fingerprint: str = FP, scorer_policy: str = "semantic",
    scorer_source_sha256: str = SCORER_SHA,
) -> dict:
    payload = {
        "status": "ELIGIBLE", "eligible": True,
        "scorer_contract": "btc-final-score-v1",
        "current_runtime_fingerprint": runtime_fingerprint,
        "scorer_policy": scorer_policy,
        "scorer_source_sha256": scorer_source_sha256,
        "input_sha256": {
            "holdout_manifest": "1" * 64,
            "regression_manifest": "2" * 64,
            "holdout_scores": "3" * 64,
            "regression_baseline": "4" * 64,
            "regression_current": "5" * 64,
        },
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {**payload, "audit_sha256": hashlib.sha256(canonical.encode()).hexdigest()}


def _write_trace(path: Path, traces: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in traces) + "\n",
        encoding="utf-8",
    )


def _subs() -> list[QuerySubmission]:
    h = _hypothesis()
    return [
        QuerySubmission("q-kis", "KIS", (Answer("L01_V001", (1,), keyframe_id="kf"),)),
        QuerySubmission("q-qa", "QA", (Answer(
            h["video_id"], (h["evidence_frame_idx"],), h["answer_text"], h["keyframe_id"]
        ),)),
    ]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda traces: traces[0].update(status="failed"),
        lambda traces: traces[0].update(retryable=True),
        lambda traces: traces[1].update(qa_hypotheses=[]),
        lambda traces: traces[1]["qa_hypotheses"][0].update(evidence_hash=""),
        lambda traces: traces[1]["qa_hypotheses"][0].update(keyframe_id=""),
        lambda traces: traces[1]["qa_hypotheses"][0].update(evidence_frame_idx=-1),
        lambda traces: traces[1].update(runtime_fingerprint="c" * 64),
    ],
)
def test_batch_failed_retryable_qa_evidence_va_mixed_fingerprint_bi_chan(mutate):
    traces = _traces()
    mutate(traces)
    result = assess_release_batch(
        queries=_queries(), traces=traces, validator_issues=[],
        trace_path=Path("trace.jsonl"), cache_manifest=_cache_manifest(),
    )
    assert result.eligible is False


def test_validator_failure_chan_batch():
    result = assess_release_batch(
        queries=_queries(), traces=_traces(),
        validator_issues=[Issue("bad", "no")],
        trace_path=Path("trace.jsonl"), cache_manifest=_cache_manifest(),
    )
    assert result.eligible is False
    assert "validator_failure" in {reason["code"] for reason in result.reasons}


def test_trace_hoac_cache_artifact_thieu_bi_chan(tmp_path):
    result = assess_release_batch(
        queries=_queries(), traces=_traces(), validator_issues=[],
        trace_path=tmp_path / "missing.jsonl", cache_manifest={"entries": []},
    )
    assert result.eligible is False
    assert {reason["code"] for reason in result.reasons} >= {
        "trace_missing", "evidence_cache_missing",
    }


def test_no_partial_zip_call_khi_gate_hong(tmp_path):
    called = []
    traces = _traces()
    traces[1]["qa_hypotheses"] = []
    trace_path = tmp_path / "trace.jsonl"
    _write_trace(trace_path, traces)
    cache_path = tmp_path / "cache.json"
    cache_path.write_text(json.dumps(_cache_manifest()), encoding="utf-8")
    queries_path = tmp_path / "queries.json"
    queries_path.write_text(json.dumps(_queries()), encoding="utf-8")

    with pytest.raises(ReleaseBlocked):
        create_release_package(
            queries=_queries(), traces=traces, submissions=_subs(), out_dir=tmp_path,
            trace_path=trace_path, evidence_cache_manifest_path=cache_path,
            evidence_cache_manifest=_cache_manifest(),
            validator_issues=[], promotion_audit=_promotion_audit(),
            query_manifest_path=queries_path, gt_manifest_path=None,
            scorer_policy="semantic", submission_policy="robust",
            reproduction_command="python run.py --release-rehearsal",
            write_zip=lambda *args, **kwargs: called.append(1),
        )
    assert called == []
    assert not list(tmp_path.glob("*.zip"))
    assert not list(tmp_path.glob("*.receipt.json"))


def test_evidence_cache_manifest_hash_va_runtime(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    identity = {
        "query_sha256": hashlib.sha256("màu gì".encode()).hexdigest(),
        "full_query_sha256": hashlib.sha256("màu gì".encode()).hexdigest(),
        "evidence_digest": "b" * 64,
        "runtime_fingerprint": FP,
    }
    (cache / "b.json").write_text(json.dumps({"identity": identity}), encoding="utf-8")
    manifest = build_evidence_cache_manifest(cache)
    assert manifest["entries"][0]["sha256"] == hashlib.sha256(
        (cache / "b.json").read_bytes()
    ).hexdigest()
    assert manifest["entries"][0]["runtime_fingerprint"] == FP


def test_receipt_checksum_config_trace_cache_reproduce_va_atomic(tmp_path, monkeypatch):
    queries_path = tmp_path / "queries.json"
    queries_path.write_text(json.dumps(_queries()), encoding="utf-8")
    trace_path = tmp_path / "trace.jsonl"
    _write_trace(trace_path, _traces())
    cache_manifest_path = tmp_path / "evidence_cache_manifest.json"
    cache_manifest = {"schema_version": 1, **_cache_manifest()}
    cache_manifest_path.write_text(json.dumps(cache_manifest), encoding="utf-8")
    promotion = _promotion_audit()

    def fake_writer(subs, out_dir, **kwargs):
        path = Path(out_dir) / kwargs["zip_name"]
        path.write_bytes(b"valid zip bytes")
        return path, []

    monkeypatch.setattr(
        "backend.export.release_rehearsal.capture_config_snapshot",
        lambda: {"schema_version": 1, "files": {"data/config/x.py": "X = 1\n"}},
    )
    receipt_path = create_release_package(
        queries=_queries(), traces=_traces(), submissions=_subs(), out_dir=tmp_path,
        trace_path=trace_path, evidence_cache_manifest_path=cache_manifest_path,
        evidence_cache_manifest=cache_manifest, validator_issues=[], promotion_audit=promotion,
        query_manifest_path=queries_path, gt_manifest_path=None,
        scorer_policy="semantic", submission_policy="robust",
        reproduction_command="python run.py --zip --release-rehearsal",
        write_zip=fake_writer, zip_name="submission.zip",
    )

    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    zip_path = tmp_path / "submission.zip"
    assert receipt["zip"]["sha256"] == hashlib.sha256(zip_path.read_bytes()).hexdigest()
    assert receipt["trace"]["sha256"] == hashlib.sha256(trace_path.read_bytes()).hexdigest()
    assert receipt["evidence_cache_manifest"]["sha256"] == hashlib.sha256(
        cache_manifest_path.read_bytes()
    ).hexdigest()
    assert receipt["config_snapshot"]["sha256"]
    assert receipt["runtime_fingerprint"] == FP
    assert receipt["gt_manifest"] == {"status": "not_applicable"}
    assert receipt["validator"] == {"status": "valid", "issues": []}
    assert receipt["reproduction_command"] == "python run.py --zip --release-rehearsal"
    assert not list(tmp_path.glob("*.tmp"))


def test_writer_tra_ve_validator_failure_thi_khong_co_receipt(tmp_path):
    trace_path = tmp_path / "trace.jsonl"
    _write_trace(trace_path, _traces())
    cache_path = tmp_path / "cache.json"
    cache_path.write_text(json.dumps(_cache_manifest()), encoding="utf-8")
    queries_path = tmp_path / "queries.json"
    queries_path.write_text(json.dumps(_queries()), encoding="utf-8")
    calls = []

    def bad_writer(subs, out_dir, **kwargs):
        calls.append(1)
        path = Path(out_dir) / "submission.zip"
        path.write_bytes(b"not usable")
        return path, [Issue("zip_corrupt", "bad")]

    with pytest.raises(ReleaseBlocked):
        create_release_package(
            queries=_queries(), traces=_traces(), submissions=_subs(), out_dir=tmp_path,
            trace_path=trace_path, evidence_cache_manifest_path=cache_path,
            evidence_cache_manifest=_cache_manifest(), validator_issues=[],
            promotion_audit=_promotion_audit(),
            query_manifest_path=queries_path, gt_manifest_path=None,
            scorer_policy="semantic", submission_policy="robust",
            reproduction_command="reproduce", write_zip=bad_writer,
        )
    assert calls == [1]
    assert not list(tmp_path.glob("*.receipt.json"))


def test_cache_planner_only_hoac_runtime_khac_khong_du_evidence(tmp_path):
    trace = tmp_path / "trace.jsonl"
    _write_trace(trace, _traces())
    for manifest in (
        {"entries": [{"parse_status": "valid", "runtime_fingerprint": FP}]},
        {"entries": [{
            "parse_status": "valid", "evidence_digest": "b" * 64,
            "runtime_fingerprint": "c" * 64,
        }]},
    ):
        result = assess_release_batch(
            queries=_queries(), traces=_traces(), validator_issues=[],
            trace_path=trace, cache_manifest=manifest,
        )
        assert result.eligible is False
        assert "qa_evidence_cache_mismatch" in {
            reason["code"] for reason in result.reasons
        }


def test_receipt_tu_choi_commit_unknown_va_audit_thieu_contract(tmp_path, monkeypatch):
    trace_path = tmp_path / "trace.jsonl"
    _write_trace(trace_path, _traces())
    cache_path = tmp_path / "cache.json"
    cache_path.write_text(json.dumps(_cache_manifest()), encoding="utf-8")
    queries_path = tmp_path / "queries.json"
    queries_path.write_text(json.dumps(_queries()), encoding="utf-8")
    called = []

    with pytest.raises(ReleaseBlocked):
        create_release_package(
            queries=_queries(), traces=_traces(), submissions=_subs(), out_dir=tmp_path,
            trace_path=trace_path, evidence_cache_manifest_path=cache_path,
            evidence_cache_manifest=_cache_manifest(), validator_issues=[],
            promotion_audit={
                "status": "ELIGIBLE", "eligible": True, "audit_sha256": "d" * 64,
            },
            query_manifest_path=queries_path, gt_manifest_path=None,
            scorer_policy="semantic", submission_policy="robust",
            reproduction_command="reproduce", write_zip=lambda *a, **kw: called.append(1),
        )
    assert called == []

    monkeypatch.setattr("backend.export.release_rehearsal._git_commit", lambda: "unknown")
    with pytest.raises(ReleaseBlocked, match="commit"):
        create_release_package(
            queries=_queries(), traces=_traces(), submissions=_subs(), out_dir=tmp_path,
            trace_path=trace_path, evidence_cache_manifest_path=cache_path,
            evidence_cache_manifest=_cache_manifest(), validator_issues=[],
            promotion_audit=_promotion_audit(),
            query_manifest_path=queries_path, gt_manifest_path=None,
            scorer_policy="semantic", submission_policy="robust",
            reproduction_command="reproduce", write_zip=lambda *a, **kw: called.append(1),
        )
    assert called == []


def test_submission_thieu_query_hoac_cache_manifest_lech_file_chan_writer(tmp_path):
    trace_path = tmp_path / "trace.jsonl"
    _write_trace(trace_path, _traces())
    cache_path = tmp_path / "cache.json"
    cache_path.write_text(json.dumps(_cache_manifest()), encoding="utf-8")
    queries_path = tmp_path / "queries.json"
    queries_path.write_text(json.dumps(_queries()), encoding="utf-8")
    called = []

    base = dict(
        queries=_queries(), traces=_traces(), out_dir=tmp_path,
        trace_path=trace_path, evidence_cache_manifest_path=cache_path,
        validator_issues=[], promotion_audit=_promotion_audit(),
        query_manifest_path=queries_path, gt_manifest_path=None,
        scorer_policy="semantic", submission_policy="robust",
        reproduction_command="reproduce",
        write_zip=lambda *a, **kw: (called.append(1) or (tmp_path / "x.zip", [])),
    )
    with pytest.raises(ReleaseBlocked, match="submission"):
        create_release_package(
            **base, submissions=_subs()[:1], evidence_cache_manifest=_cache_manifest(),
        )
    with pytest.raises(ReleaseBlocked, match="cache manifest"):
        create_release_package(
            **base, submissions=_subs(), evidence_cache_manifest={"entries": []},
        )
    assert called == []


@pytest.mark.parametrize("identity_field", ["query_sha256", "full_query_sha256"])
def test_cache_cung_evidence_nhung_khac_query_identity_bi_chan(
    tmp_path, identity_field,
):
    trace_path = tmp_path / "trace.jsonl"
    _write_trace(trace_path, _traces())
    manifest = _cache_manifest()
    manifest["entries"][0][identity_field] = hashlib.sha256(
        "câu hỏi khác".encode("utf-8")
    ).hexdigest()
    result = assess_release_batch(
        queries=_queries(), traces=_traces(), validator_issues=[],
        trace_path=trace_path, cache_manifest=manifest,
    )
    assert result.eligible is False
    assert "qa_evidence_cache_mismatch" in {
        reason["code"] for reason in result.reasons
    }


def test_trace_ram_khac_file_duoc_hash_thi_bi_chan(tmp_path):
    trace_path = tmp_path / "trace.jsonl"
    _write_trace(trace_path, _traces())
    ram_traces = _traces()
    ram_traces[0]["status"] = "failed"
    result = assess_release_batch(
        queries=_queries(), traces=ram_traces, validator_issues=[],
        trace_path=trace_path, cache_manifest=_cache_manifest(),
    )
    assert result.eligible is False
    assert "trace_content_mismatch" in {reason["code"] for reason in result.reasons}


def test_release_recompute_runtime_scorer_va_policy_phai_khop_audit(tmp_path):
    trace_path = tmp_path / "trace.jsonl"
    _write_trace(trace_path, _traces())
    cache_path = tmp_path / "cache.json"
    cache_path.write_text(json.dumps(_cache_manifest()), encoding="utf-8")
    queries_path = tmp_path / "queries.json"
    queries_path.write_text(json.dumps(_queries()), encoding="utf-8")
    called = []
    base = dict(
        queries=_queries(), traces=_traces(), submissions=_subs(), out_dir=tmp_path,
        trace_path=trace_path, evidence_cache_manifest_path=cache_path,
        evidence_cache_manifest=_cache_manifest(), validator_issues=[],
        query_manifest_path=queries_path, gt_manifest_path=None,
        scorer_policy="semantic", submission_policy="robust",
        reproduction_command="reproduce", write_zip=lambda *a, **kw: called.append(1),
    )
    for audit in (
        _promotion_audit(runtime_fingerprint="c" * 64),
        _promotion_audit(scorer_source_sha256="d" * 64),
    ):
        with pytest.raises(ReleaseBlocked, match="runtime|scorer"):
            create_release_package(**base, promotion_audit=audit)
    with pytest.raises(ReleaseBlocked, match="runtime|scorer"):
        create_release_package(
            **{**base, "scorer_policy": "exact"},
            promotion_audit=_promotion_audit(),
        )
    assert called == []
