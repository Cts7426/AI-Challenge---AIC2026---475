"""Frozen manifest phải đi qua evaluator thật rồi mới được promotion gate nhận."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from backend.tasks.runner import QueryRun
from data.config.submit_format import Answer
from dev_set.tools.promotion_gate import assess_promotion
from dev_set.tools.promotion_provenance import ground_truth_record_sha256
from dev_set.tools.schema import GroundTruthKIS, GroundTruthQA, GroundTruthTRAKE


REPO_ROOT = Path(__file__).resolve().parents[2]


def _jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def _verified_manifests_and_gt(tmp_path: Path):
    holdout = json.loads((
        REPO_ROOT / "dev_set/manifests/batch1_holdout13.json"
    ).read_text(encoding="utf-8"))
    regression = json.loads((
        REPO_ROOT / "dev_set/manifests/batch1_round1_queries.json"
    ).read_text(encoding="utf-8"))
    verification = {
        "verification_status": "verified",
        "provenance": "human-review://integration-fixture",
        "verified_by": "operator",
        "verified_at": "2026-08-24T00:00:00Z",
    }
    gt_by_id = {}

    def add_ground_truth(row: dict) -> dict:
        common = {
            "query_id": row["query_id"], "video_id": "L21_V001", **verification,
        }
        if row["task_type"] == "QA":
            gt = GroundTruthQA(
                **common, frame_start=10, frame_end=10, answer_text="đỏ",
                answer_variants=["đỏ", "màu đỏ", "red"],
            )
        elif row["task_type"] == "TRAKE":
            n = int(row.get("n_events") or len(row.get("event_descs") or []) or 2)
            gt = GroundTruthTRAKE(
                **common,
                frames=[{"start": 10 + i * 10, "end": 10 + i * 10, "desc": str(i)}
                        for i in range(n)],
            )
        else:
            gt = GroundTruthKIS(**common, frame_start=10, frame_end=10)
        gt_by_id[row["query_id"]] = gt
        gt_row = {**asdict(gt), "task_type": row["task_type"]}
        row.update(verification)
        row["ground_truth_sha256"] = ground_truth_record_sha256(gt)
        return gt_row

    holdout_gt = [add_ground_truth(row) for row in holdout["entries"]]
    regression_gt = [add_ground_truth(row) for row in regression["queries"]]
    holdout_path = tmp_path / "holdout-manifest.json"
    regression_path = tmp_path / "regression-manifest.json"
    holdout_gt_path = tmp_path / "holdout-gt.jsonl"
    regression_gt_path = tmp_path / "regression-gt.jsonl"
    holdout_path.write_text(json.dumps(holdout, ensure_ascii=False), encoding="utf-8")
    regression_path.write_text(json.dumps(regression, ensure_ascii=False), encoding="utf-8")
    _jsonl(holdout_gt_path, holdout_gt)
    _jsonl(regression_gt_path, regression_gt)
    return holdout, regression, gt_by_id, (
        holdout_path, holdout_gt_path, regression_path, regression_gt_path,
    )


def test_batch1_holdout13_manifest_loads_against_production_ground_truth():
    """Manifest thật + GT thật phải tự nạp được, không chỉ fixture giả lập.

    Trước khi có test này, `batch1_holdout13.json` thiếu `ground_truth_sha256`
    nên `_load_frozen_inputs()` crash ngay ở câu đầu — bug này không bị bắt vì
    integration test phía dưới tự sinh GT tạm, không đọc file thật.
    """
    from dev_set.tools.run_evaluation import _load_frozen_inputs

    manifest_id, queries, gts, paths = _load_frozen_inputs(
        REPO_ROOT / "dev_set/manifests/batch1_holdout13.json", None,
    )
    assert manifest_id == "batch1_holdout13"
    assert len(queries) == 13
    assert set(gts) == {q.query_id for q in queries}
    for gt in gts.values():
        assert gt.verification_status in ("unknown", "verified")


def test_evaluator_frozen_artifact_di_thang_den_promotion_eligible(
    monkeypatch, tmp_path,
):
    """Bỏ lọc manifest/hash GT ở producer sẽ làm gate cuối không còn ELIGIBLE."""
    from dev_set.tools import run_evaluation as evaluation

    holdout, regression, gt_by_id, paths = _verified_manifests_and_gt(tmp_path)
    holdout_manifest, holdout_gt, regression_manifest, regression_gt = paths
    monkeypatch.setattr(evaluation, "es_connect", lambda: None)
    monkeypatch.setattr(evaluation, "milvus_connect", lambda: None)
    monkeypatch.setattr(evaluation, "load_frame_map", lambda: {})
    monkeypatch.setattr(evaluation, "validate_evidence_capture", lambda *a, **kw: {
        "evidence_records": 1, "inference_records": 1,
    })
    monkeypatch.setattr(evaluation, "write_submissions", lambda *a, **kw: ([], []))
    monkeypatch.setattr(evaluation, "tqdm", lambda rows: rows)
    monkeypatch.setattr("builtins.input", lambda _: "y")

    def solve(query, *, total, query_runtime_fingerprint):
        gt = gt_by_id[query.query_id]
        if query.task_type == "QA":
            answers = [Answer(gt.video_id, (10,), "đỏ", "kf")]
        elif query.task_type == "TRAKE":
            answers = [Answer(gt.video_id, tuple(frame["start"] for frame in gt.frames), keyframe_id="kf")]
        else:
            answers = [Answer(gt.video_id, (10,), keyframe_id="kf")]
        return QueryRun(
            query_id=query.query_id, task_type=query.task_type, answers=answers,
            query_plan={"query_vi": query.query_vi},
            runtime_fingerprint=query_runtime_fingerprint,
        )

    monkeypatch.setattr(evaluation, "_solve_for_evaluation", solve)

    def produce(out: Path, manifest: Path, gt: Path) -> dict:
        evaluation.run_evaluation([
            "--manifest", str(manifest), "--ground-truth", str(gt),
            "--promotion", "--out", str(out),
        ])
        return json.loads((out / "scores.json").read_text(encoding="utf-8"))

    holdout_scores = produce(tmp_path / "holdout-run", holdout_manifest, holdout_gt)
    baseline = produce(tmp_path / "baseline-run", regression_manifest, regression_gt)
    current = produce(tmp_path / "current-run", regression_manifest, regression_gt)

    result = assess_promotion(
        holdout_manifest=holdout, regression_manifest=regression,
        holdout_scores=holdout_scores, regression_baseline=baseline,
        regression_current=current,
    )
    assert result.eligible is True
    assert result.status == "ELIGIBLE"
