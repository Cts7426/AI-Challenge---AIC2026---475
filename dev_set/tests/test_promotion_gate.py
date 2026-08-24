"""Promotion gate phải fail-closed trước khi chạm retrieval hay suy điểm."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path

import pytest

from dev_set.tools.promotion_gate import assess_promotion, main
from data.config.release_gate import PROMOTION_SCORER_CONTRACT


REPO_ROOT = Path(__file__).resolve().parents[2]
QUERY_FIELDS = (
    "query_id", "task_type", "query_vi", "query_en", "event_descs", "n_events",
)


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


def _canonical_sha(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _query_sha(row: dict) -> str:
    return _canonical_sha({name: row.get(name) for name in QUERY_FIELDS})


def _query_set_sha(rows: list[dict]) -> str:
    identities = [{
        "query_id": row["query_id"],
        "task_type": row["task_type"],
        "query_sha256": row.get("query_sha256") or _query_sha(row),
    } for row in sorted(rows, key=lambda item: item["query_id"])]
    return _canonical_sha(identities)


def _score(query_id: str, task_type: str, final: float, **extra) -> dict:
    return {
        "query_id": query_id,
        "task_type": task_type,
        "final": final,
        "status": "success",
        **extra,
    }


def _eligible_payloads():
    holdout = json.loads(
        (REPO_ROOT / "dev_set/manifests/batch1_holdout13.json").read_text(encoding="utf-8")
    )
    regression = json.loads(
        (REPO_ROOT / "dev_set/manifests/batch1_round1_queries.json").read_text(encoding="utf-8")
    )
    holdout_queries = []
    for path in (
        REPO_ROOT / "dev_set/queries/holdout_kis.jsonl",
        REPO_ROOT / "dev_set/queries/holdout_qa.jsonl",
    ):
        holdout_queries.extend(
            json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    query_by_id = {row["query_id"]: row for row in holdout_queries}
    holdout_entries = holdout["entries"]
    for row in holdout_entries:
        row.update(_verified_entry(row["query_id"], row["task_type"]))
        row["query_sha256"] = _query_sha(query_by_id[row["query_id"]])
        row["ground_truth_sha256"] = _canonical_sha({"gt": row["query_id"]})
    regression_queries = regression["queries"]
    for row in regression_queries:
        row.update(_verified_entry(row["query_id"], row["task_type"]))
        row["ground_truth_sha256"] = _canonical_sha({"gt": row["query_id"]})

    holdout_gt = {row["query_id"]: row["ground_truth_sha256"] for row in holdout_entries}
    regression_gt = {
        row["query_id"]: row["ground_truth_sha256"] for row in regression_queries
    }
    holdout_scores = [
        _score(row["query_id"], row["task_type"], 0.84 if row["task_type"] == "KIS" else 0.80)
        for row in holdout_entries
    ]
    baseline = [_score(q["query_id"], q["task_type"], 0.60) for q in regression_queries]
    current = [_score(q["query_id"], q["task_type"], 0.62) for q in regression_queries]
    artefacts = (
        (holdout_scores := {"per_query": holdout_scores}, holdout_entries, holdout_gt),
        (baseline := {"per_query": baseline}, regression_queries, regression_gt),
        (current := {"per_query": current}, regression_queries, regression_gt),
    )
    scorer_sha = hashlib.sha256(
        (REPO_ROOT / "dev_set/tools/scoring.py").read_bytes()
    ).hexdigest()
    for artifact, rows, gt_map in artefacts:
        artifact["scorer_contract"] = PROMOTION_SCORER_CONTRACT
        artifact["runtime_fingerprint"] = "a" * 64
        artifact["promotion_ready"] = True
        artifact["verified_query_ids"] = sorted(gt_map)
        artifact["query_set_sha256"] = _query_set_sha(rows)
        artifact["ground_truth_by_query_sha256"] = dict(gt_map)
        artifact["ground_truth_set_sha256"] = _canonical_sha(gt_map)
        artifact["scorer_policy"] = "semantic"
        artifact["scorer_source_sha256"] = scorer_sha
    baseline["runtime_fingerprint"] = "b" * 64
    return (
        holdout,
        regression,
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
        (lambda h: h["entries"][12].update(query_id="TR_013", task_type="TRAKE"),
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
    query_ids = [row["query_id"] for row in regression["queries"]]
    assert by_id[query_ids[2]]["delta"] == pytest.approx(-0.20)
    assert by_id[query_ids[3]]["new_failure"] is True


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
    regression["queries"][0]["verification_status"] = "unknown"
    result = assess_promotion(
        holdout_manifest=holdout,
        regression_manifest=regression,
        holdout_scores=holdout_scores,
        regression_baseline=baseline,
        regression_current=current,
    )
    assert result.status == "BLOCKED"
    assert regression["queries"][0]["query_id"] in result.unverified_query_ids
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


@pytest.mark.parametrize("which", ["holdout", "regression"])
def test_replacement_13_hoac_25_khong_duoc_nhan_du_manifest_id_va_count(which):
    holdout, regression, holdout_scores, baseline, current = _eligible_payloads()
    if which == "holdout":
        rows, artefacts = holdout["entries"], [holdout_scores]
    else:
        rows, artefacts = regression["queries"], [baseline, current]
    old_id = rows[0]["query_id"]
    rows[0]["query_id"] = f"replacement-{which}"
    rows[0]["query_sha256"] = "f" * 64
    rows[0]["ground_truth_sha256"] = "e" * 64
    for artifact in artefacts:
        record = next(row for row in artifact["per_query"] if row["query_id"] == old_id)
        record["query_id"] = rows[0]["query_id"]
        gt_map = artifact["ground_truth_by_query_sha256"]
        gt_map[rows[0]["query_id"]] = gt_map.pop(old_id)
        artifact["verified_query_ids"] = sorted(gt_map)
        artifact["query_set_sha256"] = _query_set_sha(rows)
        artifact["ground_truth_set_sha256"] = _canonical_sha(gt_map)
    result = assess_promotion(
        holdout_manifest=holdout, regression_manifest=regression,
        holdout_scores=holdout_scores, regression_baseline=baseline,
        regression_current=current,
    )
    assert result.eligible is False
    assert "frozen_query_set" in {reason["code"] for reason in result.reasons}


def test_regression_giu_nguyen_id_nhung_sua_noi_dung_van_bi_chan():
    holdout, regression, holdout_scores, baseline, current = _eligible_payloads()
    regression["queries"][0]["query_vi"] += " chi tiết bị sửa"

    result = assess_promotion(
        holdout_manifest=holdout, regression_manifest=regression,
        holdout_scores=holdout_scores, regression_baseline=baseline,
        regression_current=current,
    )

    assert result.eligible is False
    assert "frozen_query_set" in {reason["code"] for reason in result.reasons}


def test_score_legacy_hoac_gt_hash_khong_khop_manifest_bi_chan():
    holdout, regression, holdout_scores, baseline, current = _eligible_payloads()
    del holdout_scores["promotion_ready"]
    result = assess_promotion(
        holdout_manifest=holdout, regression_manifest=regression,
        holdout_scores=holdout_scores, regression_baseline=baseline,
        regression_current=current,
    )
    assert result.status == "BLOCKED"
    assert "malformed_artifact" in {reason["code"] for reason in result.reasons}

    holdout, regression, holdout_scores, baseline, current = _eligible_payloads()
    query_id = holdout["entries"][0]["query_id"]
    holdout_scores["ground_truth_by_query_sha256"][query_id] = "0" * 64
    result = assess_promotion(
        holdout_manifest=holdout, regression_manifest=regression,
        holdout_scores=holdout_scores, regression_baseline=baseline,
        regression_current=current,
    )
    assert result.eligible is False
    assert "ground_truth_provenance" in {reason["code"] for reason in result.reasons}


def test_audit_bind_runtime_scorer_policy_va_source():
    args = _eligible_payloads()
    result = assess_promotion(
        holdout_manifest=args[0], regression_manifest=args[1], holdout_scores=args[2],
        regression_baseline=args[3], regression_current=args[4],
    )
    payload = result.to_dict()
    assert payload["current_runtime_fingerprint"] == "a" * 64
    assert payload["scorer_policy"] == "semantic"
    assert payload["scorer_source_sha256"] == args[4]["scorer_source_sha256"]


def test_cli_missing_manifest_tra_json_blocked_khong_traceback(tmp_path, capsys):
    output = tmp_path / "blocked.json"
    code = main([
        "--holdout-manifest", str(tmp_path / "does-not-exist.json"),
        "--output", str(output),
    ])
    captured = capsys.readouterr()
    assert code == 1
    assert "Traceback" not in captured.err + captured.out
    audit = json.loads(output.read_text(encoding="utf-8"))
    assert audit["status"] == "BLOCKED"
    assert audit["eligible"] is False
    assert audit["input_sha256"]["holdout_manifest"] in {"missing", "read_error"}


def test_cli_manifest_top_level_sai_schema_van_tra_json_blocked(tmp_path, capsys):
    malformed = tmp_path / "malformed.json"
    malformed.write_text('[{"not":"a manifest"}]', encoding="utf-8")
    output = tmp_path / "blocked.json"

    code = main(["--holdout-manifest", str(malformed), "--output", str(output)])

    captured = capsys.readouterr()
    assert code == 1
    assert "Traceback" not in captured.err + captured.out
    audit = json.loads(output.read_text(encoding="utf-8"))
    assert audit["status"] == "BLOCKED"
    assert audit["reasons"][0]["code"] == "malformed_manifest"
