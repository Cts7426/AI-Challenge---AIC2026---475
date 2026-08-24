"""Gate promotion thuần JSON: thiếu provenance/artefact thì chặn, không search.

Module cố ý không import retrieval, client hay model. Nó chỉ so manifest đã
đóng băng với score artefact replay được; Public score không phải input của gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from data.config.release_gate import (
    HOLDOUT_EXPECTED_TASK_COUNTS,
    HOLDOUT_KIS_MIN,
    HOLDOUT_MANIFEST_ID,
    HOLDOUT_OVERALL_MIN,
    HOLDOUT_QA_MIN,
    PROMOTION_GATE_SCHEMA_VERSION,
    PROMOTION_SCORER_CONTRACT,
    REGRESSION_EXPECTED_COUNT,
    REGRESSION_MANIFEST_ID,
    REGRESSION_SCORE_EPSILON,
)


GateStatus = str


@dataclass(frozen=True)
class PromotionGateResult:
    """Audit deterministic; `BLOCKED` là thiếu evidence, không phải điểm thấp."""

    status: GateStatus
    eligible: bool
    reasons: tuple[dict[str, Any], ...] = ()
    metrics: dict[str, float] = field(default_factory=dict)
    query_level_diff: tuple[dict[str, Any], ...] = ()
    unverified_query_ids: tuple[str, ...] = ()
    missing_query_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PROMOTION_GATE_SCHEMA_VERSION,
            "status": self.status,
            "eligible": self.eligible,
            "reasons": [dict(reason) for reason in self.reasons],
            "metrics": dict(self.metrics),
            "query_level_diff": [dict(row) for row in self.query_level_diff],
            "unverified_query_ids": list(self.unverified_query_ids),
            "missing_query_ids": list(self.missing_query_ids),
            "public_score_used": False,
            "scorer_contract": PROMOTION_SCORER_CONTRACT,
        }


def _reason(code: str, message: str, **details: Any) -> dict[str, Any]:
    return {"code": code, "message": message, **details}


def _manifest_rows(manifest: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows = manifest.get("entries", manifest.get("queries"))
    if not isinstance(rows, list) or not all(isinstance(row, Mapping) for row in rows):
        raise ValueError("manifest phải có list entries/queries")
    return list(rows)


def _audit_verified(rows: Sequence[Mapping[str, Any]]) -> tuple[list[str], list[str]]:
    unverified: list[str] = []
    malformed: list[str] = []
    for row in rows:
        query_id = str(row.get("query_id") or "<missing>")
        if row.get("verification_status") != "verified":
            unverified.append(query_id)
            continue
        required = ("provenance", "verified_by", "verified_at")
        if any(not isinstance(row.get(name), str) or not str(row[name]).strip()
               for name in required):
            malformed.append(query_id)
    return unverified, malformed


def _validate_manifest_identity(
    manifest: Mapping[str, Any],
    *,
    expected_id: str,
    expected_count: int,
) -> tuple[list[Mapping[str, Any]], list[dict[str, Any]]]:
    rows = _manifest_rows(manifest)
    reasons: list[dict[str, Any]] = []
    if manifest.get("manifest_id") != expected_id:
        reasons.append(_reason(
            "manifest_id", f"manifest_id phải là {expected_id}",
            actual=manifest.get("manifest_id"),
        ))
    ids = [str(row.get("query_id") or "") for row in rows]
    if len(rows) != expected_count or len(set(ids)) != expected_count or any(not qid for qid in ids):
        reasons.append(_reason(
            "holdout_query_ids" if expected_id == HOLDOUT_MANIFEST_ID else "regression_query_ids",
            f"manifest phải có đúng {expected_count} query_id duy nhất, không rỗng",
            actual_count=len(rows), unique_count=len(set(ids)),
        ))
    return rows, reasons


def _parse_scores(
    artifact: Mapping[str, Any] | None,
    *,
    label: str,
    expected_ids: Sequence[str],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    if not isinstance(artifact, Mapping):
        raise ValueError(f"{label} thiếu hoặc không phải JSON object")
    rows = artifact.get("per_query")
    if not isinstance(rows, list):
        raise ValueError(f"{label}.per_query phải là list")
    if artifact.get("scorer_contract") != PROMOTION_SCORER_CONTRACT:
        raise ValueError(
            f"{label}.scorer_contract phải là {PROMOTION_SCORER_CONTRACT}"
        )
    fingerprint = artifact.get("runtime_fingerprint")
    if not isinstance(fingerprint, str) or not fingerprint.strip():
        raise ValueError(f"{label} thiếu runtime_fingerprint")

    parsed: dict[str, dict[str, Any]] = {}
    for raw in rows:
        if not isinstance(raw, Mapping):
            raise ValueError(f"{label}.per_query có record không phải object")
        query_id = raw.get("query_id")
        task_type = raw.get("task_type")
        final = raw.get("final")
        status = raw.get("status")
        if (
            not isinstance(query_id, str) or not query_id
            or task_type not in ("KIS", "QA", "TRAKE")
            or isinstance(final, bool) or not isinstance(final, (int, float))
            or not math.isfinite(float(final)) or not 0.0 <= float(final) <= 1.0
            or status not in ("success", "failed")
        ):
            raise ValueError(f"{label} record sai schema: {query_id!r}")
        if query_id in parsed:
            raise ValueError(f"{label} trùng query_id {query_id}")
        parsed[query_id] = {
            "query_id": query_id,
            "task_type": task_type,
            "final": float(final),
            "status": status,
            "failure_class": raw.get("failure_class"),
        }

    expected = set(expected_ids)
    actual = set(parsed)
    reasons: list[dict[str, Any]] = []
    if actual != expected:
        reasons.append(_reason(
            "score_query_ids", f"{label} không khớp query IDs manifest",
            artifact=label,
            missing=sorted(expected - actual), unexpected=sorted(actual - expected),
        ))
    return parsed, reasons


def _mean(rows: Sequence[dict[str, Any]]) -> float:
    return sum(row["final"] for row in rows) / len(rows)


def assess_promotion(
    *,
    holdout_manifest: Mapping[str, Any],
    regression_manifest: Mapping[str, Any],
    holdout_scores: Mapping[str, Any] | None,
    regression_baseline: Mapping[str, Any] | None,
    regression_current: Mapping[str, Any] | None,
) -> PromotionGateResult:
    """Đánh giá promotion, luôn kiểm provenance trước mọi score artefact.

    Input là object JSON đã đọc. Output không có timestamp/path nên cùng input
    luôn cho cùng audit. Invariant: thiếu/malformed không được suy thành điểm 0.
    """
    try:
        holdout_rows = _manifest_rows(holdout_manifest)
    except (TypeError, ValueError) as error:
        return PromotionGateResult(
            status="BLOCKED", eligible=False,
            reasons=(_reason("malformed_manifest", str(error)),),
        )

    try:
        regression_rows_for_audit = _manifest_rows(regression_manifest)
    except (TypeError, ValueError) as error:
        return PromotionGateResult(
            status="BLOCKED", eligible=False,
            reasons=(_reason("malformed_manifest", str(error)),),
        )
    unverified, malformed_verified = _audit_verified(holdout_rows)
    regression_unverified, regression_malformed = _audit_verified(regression_rows_for_audit)
    all_unverified = sorted([*unverified, *regression_unverified])
    all_malformed = sorted([*malformed_verified, *regression_malformed])
    if all_unverified or all_malformed:
        reasons = []
        if all_unverified:
            reasons.append(_reason(
                "ground_truth_unverified", "holdout/regression còn nhãn chưa verified",
                query_ids=all_unverified,
            ))
        if all_malformed:
            reasons.append(_reason(
                "ground_truth_audit_trail", "GT verified thiếu audit trail",
                query_ids=all_malformed,
            ))
        return PromotionGateResult(
            status="BLOCKED", eligible=False, reasons=tuple(reasons),
            unverified_query_ids=tuple(all_unverified),
        )

    try:
        holdout_rows, reasons = _validate_manifest_identity(
            holdout_manifest, expected_id=HOLDOUT_MANIFEST_ID,
            expected_count=sum(HOLDOUT_EXPECTED_TASK_COUNTS.values()),
        )
        regression_rows, regression_manifest_reasons = _validate_manifest_identity(
            regression_manifest, expected_id=REGRESSION_MANIFEST_ID,
            expected_count=REGRESSION_EXPECTED_COUNT,
        )
        reasons.extend(regression_manifest_reasons)

        task_counts = {
            task: sum(1 for row in holdout_rows if row.get("task_type") == task)
            for task in HOLDOUT_EXPECTED_TASK_COUNTS
        }
        unexpected_tasks = sorted({str(row.get("task_type")) for row in holdout_rows}
                                  - set(HOLDOUT_EXPECTED_TASK_COUNTS))
        if task_counts != HOLDOUT_EXPECTED_TASK_COUNTS or unexpected_tasks:
            reasons.append(_reason(
                "holdout_composition", "holdout phải có đúng 10 KIS + 3 QA",
                expected=HOLDOUT_EXPECTED_TASK_COUNTS, actual=task_counts,
                unexpected_tasks=unexpected_tasks,
            ))

        holdout_ids = [str(row["query_id"]) for row in holdout_rows]
        regression_ids = [str(row["query_id"]) for row in regression_rows]
        holdout, score_reasons = _parse_scores(
            holdout_scores, label="holdout_scores", expected_ids=holdout_ids,
        )
        reasons.extend(score_reasons)
        baseline, score_reasons = _parse_scores(
            regression_baseline, label="regression_baseline",
            expected_ids=regression_ids,
        )
        reasons.extend(score_reasons)
        current, score_reasons = _parse_scores(
            regression_current, label="regression_current",
            expected_ids=regression_ids,
        )
        reasons.extend(score_reasons)

        holdout_task_of = {
            str(row["query_id"]): str(row.get("task_type")) for row in holdout_rows
        }
        regression_task_of = {
            str(row["query_id"]): str(row.get("task_type")) for row in regression_rows
        }
        task_mismatches = []
        for label, parsed, expected_task_of in (
            ("holdout_scores", holdout, holdout_task_of),
            ("regression_baseline", baseline, regression_task_of),
            ("regression_current", current, regression_task_of),
        ):
            for query_id in sorted(set(parsed) & set(expected_task_of)):
                if parsed[query_id]["task_type"] != expected_task_of[query_id]:
                    task_mismatches.append({
                        "artifact": label,
                        "query_id": query_id,
                        "expected": expected_task_of[query_id],
                        "actual": parsed[query_id]["task_type"],
                    })
        if task_mismatches:
            reasons.append(_reason(
                "score_task_type", "task_type trong score không khớp manifest",
                mismatches=task_mismatches,
            ))

        current_fp = str(regression_current["runtime_fingerprint"])
        if str(holdout_scores["runtime_fingerprint"]) != current_fp:
            reasons.append(_reason(
                "current_runtime_mismatch",
                "holdout và regression current phải cùng runtime fingerprint",
            ))
    except (KeyError, TypeError, ValueError) as error:
        return PromotionGateResult(
            status="BLOCKED", eligible=False,
            reasons=(_reason("malformed_artifact", str(error)),),
        )

    # Sai ID/composition không được tính mean trên một tập khác manifest.
    if reasons:
        return PromotionGateResult(
            status="NOT_ELIGIBLE", eligible=False, reasons=tuple(reasons),
        )

    holdout_ordered = [holdout[qid] for qid in holdout_ids]
    holdout_kis = [row for row in holdout_ordered if row["task_type"] == "KIS"]
    holdout_qa = [row for row in holdout_ordered if row["task_type"] == "QA"]
    baseline_ordered = [baseline[qid] for qid in regression_ids]
    current_ordered = [current[qid] for qid in regression_ids]
    metrics = {
        "holdout_overall": _mean(holdout_ordered),
        "holdout_kis": _mean(holdout_kis),
        "holdout_qa": _mean(holdout_qa),
        "regression_baseline": _mean(baseline_ordered),
        "regression_current": _mean(current_ordered),
    }

    gate_reasons: list[dict[str, Any]] = []
    failed_holdout = sorted(row["query_id"] for row in holdout_ordered
                            if row["status"] != "success")
    failed_current = sorted(row["query_id"] for row in current_ordered
                            if row["status"] != "success")
    if failed_holdout or failed_current:
        gate_reasons.append(_reason(
            "zero_crash", "holdout/regression current có query failed",
            holdout_query_ids=failed_holdout,
            regression_query_ids=failed_current,
        ))

    diffs: list[dict[str, Any]] = []
    for query_id in regression_ids:
        before = baseline[query_id]
        after = current[query_id]
        delta = after["final"] - before["final"]
        new_failure = before["status"] == "success" and after["status"] != "success"
        diffs.append({
            "query_id": query_id,
            "task_type": after["task_type"],
            "baseline": before["final"],
            "current": after["final"],
            "delta": delta,
            "new_failure": new_failure,
        })
    decreased = [row["query_id"] for row in diffs
                 if row["delta"] < -REGRESSION_SCORE_EPSILON]
    new_failures = [row["query_id"] for row in diffs if row["new_failure"]]
    if decreased or new_failures or (
        metrics["regression_current"]
        < metrics["regression_baseline"] - REGRESSION_SCORE_EPSILON
    ):
        gate_reasons.append(_reason(
            "regression_non_decrease", "regression 25 câu bị giảm hoặc có failure mới",
            decreased_query_ids=decreased, new_failure_query_ids=new_failures,
        ))

    for code, metric_name, threshold in (
        ("holdout_overall_threshold", "holdout_overall", HOLDOUT_OVERALL_MIN),
        ("holdout_kis_threshold", "holdout_kis", HOLDOUT_KIS_MIN),
        ("holdout_qa_threshold", "holdout_qa", HOLDOUT_QA_MIN),
    ):
        if metrics[metric_name] + REGRESSION_SCORE_EPSILON < threshold:
            gate_reasons.append(_reason(
                code, f"{metric_name} thấp hơn ngưỡng {threshold}",
                actual=metrics[metric_name], threshold=threshold,
            ))

    eligible = not gate_reasons
    return PromotionGateResult(
        status="ELIGIBLE" if eligible else "NOT_ELIGIBLE",
        eligible=eligible,
        reasons=tuple(gate_reasons),
        metrics=metrics,
        query_level_diff=tuple(diffs),
    )


def _load_json(path: Path | None) -> Mapping[str, Any] | None:
    if path is None:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _input_sha256(path: Path | None) -> str:
    if path is None:
        return "not_provided"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gate promotion Batch 1 không gọi retrieval")
    parser.add_argument(
        "--holdout-manifest", type=Path,
        default=Path("dev_set/manifests/batch1_holdout13.json"),
    )
    parser.add_argument(
        "--regression-manifest", type=Path,
        default=Path("dev_set/manifests/batch1_round1_queries.json"),
    )
    parser.add_argument("--holdout-scores", type=Path)
    parser.add_argument("--regression-baseline", type=Path)
    parser.add_argument("--regression-current", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    try:
        result = assess_promotion(
            holdout_manifest=_load_json(args.holdout_manifest) or {},
            regression_manifest=_load_json(args.regression_manifest) or {},
            holdout_scores=_load_json(args.holdout_scores),
            regression_baseline=_load_json(args.regression_baseline),
            regression_current=_load_json(args.regression_current),
        )
    except (OSError, json.JSONDecodeError) as error:
        result = PromotionGateResult(
            status="BLOCKED", eligible=False,
            reasons=(_reason("input_read_error", str(error)),),
        )

    payload = result.to_dict()
    payload["input_sha256"] = {
        "holdout_manifest": _input_sha256(args.holdout_manifest),
        "regression_manifest": _input_sha256(args.regression_manifest),
        "holdout_scores": _input_sha256(args.holdout_scores),
        "regression_baseline": _input_sha256(args.regression_baseline),
        "regression_current": _input_sha256(args.regression_current),
    }
    canonical_without_hash = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    payload["audit_sha256"] = hashlib.sha256(
        canonical_without_hash.encode("utf-8")
    ).hexdigest()
    output = _canonical_json(payload)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temp = args.output.with_name(f".{args.output.name}.tmp")
        temp.write_text(output, encoding="utf-8")
        temp.replace(args.output)
    print(output, end="")
    return 0 if result.eligible else 1


if __name__ == "__main__":
    raise SystemExit(main())
