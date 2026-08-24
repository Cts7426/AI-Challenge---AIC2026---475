"""Promotion gate phải fail-closed trước khi chạm retrieval hay suy điểm."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dev_set.tools.promotion_gate import assess_promotion, main
from data.config.release_gate import PROMOTION_SCORER_CONTRACT


def _manifest(entries: list[dict], *, manifest_id: str) -> dict:
    return {"manifest_id": manifest_id, "entries": entries}


def _verified_entry(query_id: str, task_type: str) -> dict:
    return {
        "query_id": query_id,
        "task_type": task_type,
        "verification_status": "verified",
        "provenance": "human-review://batch1",
        "verified_by": "operator",
        "verified_at": "2026-08-24T00:00:00Z",
    }


def _score(query_id: str, task_type: str, final: float, **extra) -> dict:
    return {
        "query_id": query_id,
        "task_type": task_type,
        "final": final,
        "status": "success",
        **extra,
    }


def _eligible_payloads():
    holdout_entries = [
        *[_verified_entry(f"KIS_{i:03d}", "KIS") for i in range(1, 11)],
        *[_verified_entry(f"QA_{i:03d}", "QA") for i in range(11, 14)],
    ]
    regression_queries = [
        _verified_entry(f"R{i:02d}", "QA" if i > 21 else "KIS")
        for i in range(1, 26)
    ]
    holdout_scores = [
        *[_score(f"KIS_{i:03d}", "KIS", 0.84) for i in range(1, 11)],
        *[_score(f"QA_{i:03d}", "QA", 0.80) for i in range(11, 14)],
    ]
    baseline = [_score(q["query_id"], q["task_type"], 0.60) for q in regression_queries]
    current = [_score(q["query_id"], q["task_type"], 0.62) for q in regression_queries]
    for artifact in (holdout_scores := {"per_query": holdout_scores},
                     baseline := {"per_query": baseline},
                     current := {"per_query": current}):
        artifact["scorer_contract"] = PROMOTION_SCORER_CONTRACT
        artifact["runtime_fingerprint"] = "runtime-current"
    baseline["runtime_fingerprint"] = "runtime-baseline"
    return (
        _manifest(holdout_entries, manifest_id="batch1_holdout13"),
        _manifest(regression_queries, manifest_id="batch1_round1_queries"),
        holdout_scores,
        baseline,
        current,
    )


def test_unknown_gt_chan_truoc_khi_doc_score():
    holdout, regression, holdout_scores, baseline, current = _eligible_payloads()
    holdout["entries"][0]["verification_status"] = "unknown"
    holdout["entries"][0]["verified_by"] = None

    class ExplodingScores(dict):
        def get(self, *args, **kwargs):
            pytest.fail("GT unknown phải chặn trước khi đọc score")

    result = assess_promotion(
        holdout_manifest=holdout,
        regression_manifest=regression,
        holdout_scores=ExplodingScores(holdout_scores),
        regression_baseline=baseline,
        regression_current=current,
    )

    assert result.status == "BLOCKED"
    assert result.eligible is False
    assert "KIS_001" in result.unverified_query_ids
    assert result.metrics == {}


@pytest.mark.parametrize(
    ("mutate", "reason_code"),
    [
        (lambda h: h["entries"].pop(), "holdout_query_ids"),
        (lambda h: h["entries"].__setitem__(12, _verified_entry("TR_013", "TRAKE")),
         "holdout_composition"),
    ],
)
def test_holdout_thieu_id_hoac_sai_composition_bi_chan(mutate, reason_code):
    holdout, regression, holdout_scores, baseline, current = _eligible_payloads()
    mutate(holdout)
    result = assess_promotion(
        holdout_manifest=holdout,
        regression_manifest=regression,
        holdout_scores=holdout_scores,
        regression_baseline=baseline,
        regression_current=current,
    )
    assert result.status == "NOT_ELIGIBLE"
    assert reason_code in {reason["code"] for reason in result.reasons}


def test_threshold_qa_thap_bi_chan_va_public_khong_duoc_doc():
    holdout, regression, holdout_scores, baseline, current = _eligible_payloads()
    for row in holdout_scores["per_query"]:
        if row["task_type"] == "QA":
            row["final"] = 0.70
    holdout_scores["public_score"] = 1.0

    result = assess_promotion(
        holdout_manifest=holdout,
        regression_manifest=regression,
        holdout_scores=holdout_scores,
        regression_baseline=baseline,
        regression_current=current,
    )

    assert result.status == "NOT_ELIGIBLE"
    assert result.metrics["holdout_qa"] == pytest.approx(0.70)
    assert "holdout_qa_threshold" in {reason["code"] for reason in result.reasons}
    assert result.to_dict()["public_score_used"] is False
    assert "public_score" not in result.metrics


def test_regression_decrease_va_failure_moi_bi_chan_query_level():
    holdout, regression, holdout_scores, baseline, current = _eligible_payloads()
    current["per_query"][2]["final"] = 0.40
    current["per_query"][3]["status"] = "failed"
    current["per_query"][3]["failure_class"] = "retrieval_miss"

    result = assess_promotion(
        holdout_manifest=holdout,
        regression_manifest=regression,
        holdout_scores=holdout_scores,
        regression_baseline=baseline,
        regression_current=current,
    )

    assert result.status == "NOT_ELIGIBLE"
    by_id = {row["query_id"]: row for row in result.query_level_diff}
    assert by_id["R03"]["delta"] == pytest.approx(-0.20)
    assert by_id["R04"]["new_failure"] is True


def test_zero_crash_bat_buoc_cho_holdout():
    holdout, regression, holdout_scores, baseline, current = _eligible_payloads()
    holdout_scores["per_query"][0]["status"] = "failed"
    result = assess_promotion(
        holdout_manifest=holdout,
        regression_manifest=regression,
        holdout_scores=holdout_scores,
        regression_baseline=baseline,
        regression_current=current,
    )
    assert result.status == "NOT_ELIGIBLE"
    assert "zero_crash" in {reason["code"] for reason in result.reasons}


def test_gate_thanh_cong_co_audit_deterministic():
    args = _eligible_payloads()
    first = assess_promotion(
        holdout_manifest=args[0], regression_manifest=args[1], holdout_scores=args[2],
        regression_baseline=args[3], regression_current=args[4],
    )
    second = assess_promotion(
        holdout_manifest=args[0], regression_manifest=args[1], holdout_scores=args[2],
        regression_baseline=args[3], regression_current=args[4],
    )
    assert first.status == "ELIGIBLE"
    assert first.eligible is True
    assert first.to_dict() == second.to_dict()
    assert first.metrics == {
        "holdout_overall": pytest.approx((10 * 0.84 + 3 * 0.80) / 13),
        "holdout_kis": pytest.approx(0.84),
        "holdout_qa": pytest.approx(0.80),
        "regression_baseline": pytest.approx(0.60),
        "regression_current": pytest.approx(0.62),
    }


def test_malformed_score_fail_closed_khong_suy_zero():
    holdout, regression, holdout_scores, baseline, current = _eligible_payloads()
    del holdout_scores["per_query"][0]["final"]
    result = assess_promotion(
        holdout_manifest=holdout,
        regression_manifest=regression,
        holdout_scores=holdout_scores,
        regression_baseline=baseline,
        regression_current=current,
    )
    assert result.status == "BLOCKED"
    assert result.metrics == {}
    assert "malformed_artifact" in {reason["code"] for reason in result.reasons}


def test_regression_gt_unverified_chan_truoc_score():
    holdout, regression, holdout_scores, baseline, current = _eligible_payloads()
    regression["entries"][0]["verification_status"] = "unknown"
    result = assess_promotion(
        holdout_manifest=holdout,
        regression_manifest=regression,
        holdout_scores=holdout_scores,
        regression_baseline=baseline,
        regression_current=current,
    )
    assert result.status == "BLOCKED"
    assert "R01" in result.unverified_query_ids
    assert result.metrics == {}


def test_score_task_type_phai_khop_manifest():
    holdout, regression, holdout_scores, baseline, current = _eligible_payloads()
    holdout_scores["per_query"][0]["task_type"] = "QA"
    result = assess_promotion(
        holdout_manifest=holdout,
        regression_manifest=regression,
        holdout_scores=holdout_scores,
        regression_baseline=baseline,
        regression_current=current,
    )
    assert result.status == "NOT_ELIGIBLE"
    assert "score_task_type" in {reason["code"] for reason in result.reasons}


def test_cli_audit_bam_du_nam_input_va_checksum_duoc_release_xac_minh(tmp_path):
    from backend.export.release_rehearsal import promotion_audit_is_valid

    holdout, regression, holdout_scores, baseline, current = _eligible_payloads()
    values = {
        "holdout-manifest": holdout,
        "regression-manifest": regression,
        "holdout-scores": holdout_scores,
        "regression-baseline": baseline,
        "regression-current": current,
    }
    argv: list[str] = []
    for flag, value in values.items():
        path = tmp_path / f"{flag}.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        argv.extend([f"--{flag}", str(path)])
    output = tmp_path / "audit.json"
    assert main([*argv, "--output", str(output)]) == 0
    audit = json.loads(output.read_text(encoding="utf-8"))
    assert set(audit["input_sha256"]) == {
        "holdout_manifest", "regression_manifest", "holdout_scores",
        "regression_baseline", "regression_current",
    }
    assert promotion_audit_is_valid(audit) is True
