"""Harness chẩn đoán KIS dress25; không sửa query, GT hay config nguồn."""

from __future__ import annotations

import hashlib
import json
import math
import os
import statistics
import subprocess
import time
from collections import Counter
from pathlib import Path

from backend.export import n_frames_of
from backend.indexing.es_client import connect as es_connect
from backend.indexing.frame_map import load_frame_map
from backend.indexing.milvus_client import connect as milvus_connect
from backend.tasks.runner import SolveQueryError, runtime_fingerprint, runtime_manifest, solve_query
from dev_set.tools.promotion_provenance import query_set_sha256
from dev_set.tools.run_evaluation import _runtime_snapshot, load_jsonl
from dev_set.tools.schema import GroundTruthKIS, Query
from dev_set.tools.scorer_contract import scorer_contract_sha256
from dev_set.tools.scoring import final_score, recall_at_k


REPO_ROOT = Path(__file__).resolve().parents[3]
RUN_DIR = Path(__file__).resolve().parent
QUERY_PATH = REPO_ROOT / "dev_set/queries/dress25_kis.jsonl"
GT_PATH = REPO_ROOT / "dev_set/ground_truth/dress25_gt.jsonl"
EXPECTED_IDS = [f"DRESS_KIS_{index:02d}" for index in range(1, 20)]
THRESHOLDS = (1, 5, 20, 50, 100)


def sha256_file(path: Path) -> str:
    """Trả SHA-256 file nguồn để chứng minh input không đổi trong run."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def append_jsonl(path: Path, record: dict) -> None:
    """Checkpoint một record và fsync để crash không làm mất query đã xong."""
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def load_inputs() -> tuple[list[Query], dict[str, GroundTruthKIS]]:
    """Nạp đúng 19 KIS dress25 và GT tương ứng, fail closed nếu ID lệch."""
    queries = [Query(**row) for row in load_jsonl(QUERY_PATH)]
    if [query.query_id for query in queries] != EXPECTED_IDS:
        raise RuntimeError("dress25 KIS không còn đúng 19 ID DRESS_KIS_01..19")
    if any(query.task_type != "KIS" or query.split != "dress25" for query in queries):
        raise RuntimeError("diagnostic input chứa task/split ngoài KIS dress25")

    query_ids = set(EXPECTED_IDS)
    gts: dict[str, GroundTruthKIS] = {}
    for row in load_jsonl(GT_PATH):
        if row.get("query_id") not in query_ids:
            continue
        clean = {key: value for key, value in row.items() if key != "task_type"}
        gts[row["query_id"]] = GroundTruthKIS(**clean)
    if set(gts) != query_ids:
        raise RuntimeError("GT dress25 thiếu ID KIS cần chấm")
    return queries, gts


def freeze_before_run(queries: list[Query]) -> dict:
    """Ghi snapshot trước khi kết nối DB hoặc gọi provider."""
    evaluation_manifest, configs, llm_provenance = _runtime_snapshot(
        "dress25_kis19",
        evaluation_paths=[QUERY_PATH, GT_PATH],
    )
    snapshot = {
        "schema_version": 1,
        "scope": "diagnostic_only_not_promotion",
        "head_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip(),
        "runtime_fingerprint": runtime_fingerprint(),
        "runtime_manifest": runtime_manifest(),
        "llm_backend": os.environ.get("LLM_BACKEND"),
        "llm_api_model": os.environ.get("LLM_API_MODEL"),
        "llm_no_cache": os.environ.get("LLM_NO_CACHE", "<unset>"),
        "config_snapshot": configs,
        "config_sources_sha256": evaluation_manifest["config_sources_sha256"],
        "scorer_source_digest": scorer_contract_sha256(),
        "scorer_file_sha256": sha256_file(
            REPO_ROOT / "dev_set/tools/scoring.py"
        ),
        "query_set_identity": {
            "count": len(queries),
            "ids": EXPECTED_IDS,
            "query_set_sha256": query_set_sha256(queries),
            "source_path": QUERY_PATH.relative_to(REPO_ROOT).as_posix(),
            "source_sha256": sha256_file(QUERY_PATH),
        },
        "ground_truth_source": {
            "path": GT_PATH.relative_to(REPO_ROOT).as_posix(),
            "sha256": sha256_file(GT_PATH),
            "verification": "legacy/unverified; diagnostic only",
        },
        "evaluation_artifact_manifest": evaluation_manifest,
        "llm_provenance": llm_provenance,
    }
    (RUN_DIR / "config_snapshot.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return snapshot


def mapping_violations(answers: list, fmap: dict[str, int]) -> list[str]:
    """Kiểm frame trong biên video và keyframe có khai báo phải khớp frame_map."""
    violations: list[str] = []
    for row_index, answer in enumerate(answers):
        if len(answer.frame_ids) != 1:
            violations.append(f"row {row_index}: frame_ids={answer.frame_ids!r}")
            continue
        frame_id = answer.frame_ids[0]
        n_frames = n_frames_of(answer.video_id)
        if not isinstance(frame_id, int) or frame_id < 0 or frame_id >= n_frames:
            violations.append(
                f"row {row_index}: {answer.video_id} frame={frame_id}, n_frames={n_frames}"
            )
        if answer.keyframe_id is not None:
            mapped = fmap.get(answer.keyframe_id)
            if mapped is None or int(mapped) != int(frame_id):
                violations.append(
                    f"row {row_index}: keyframe={answer.keyframe_id}, "
                    f"mapped={mapped}, output={frame_id}"
                )
    return violations


def percentile_inclusive(values: list[float], percentile: float) -> float:
    """Nội suy percentile inclusive, ổn định cho mẫu nhỏ 19 query."""
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = percentile * (len(ordered) - 1)
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def main() -> None:
    """Chạy đúng production KIS path và ghi artefact checkpoint từng query."""
    if os.environ.get("LLM_BACKEND") != "api":
        raise RuntimeError("LLM_BACKEND phải được pin thủ công là api")
    if os.environ.get("LLM_API_MODEL") != "claude-sonnet-5":
        raise RuntimeError("LLM_API_MODEL phải được pin thủ công là claude-sonnet-5")
    if os.environ.get("LLM_NO_CACHE"):
        raise RuntimeError("Diagnostic phải dùng cache semantics mặc định của evaluator 27/08")

    queries, gts = load_inputs()
    snapshot = freeze_before_run(queries)
    frozen_runtime = snapshot["runtime_fingerprint"]
    frozen_query_sha = snapshot["query_set_identity"]["source_sha256"]
    frozen_gt_sha = snapshot["ground_truth_source"]["sha256"]

    os.environ["LLM_RUN_ID"] = RUN_DIR.name
    es_connect()
    milvus_connect()
    fmap = load_frame_map()

    records_path = RUN_DIR / "records.jsonl"
    answers_path = RUN_DIR / "answers.jsonl"
    traces_path = RUN_DIR / "candidates.jsonl"
    records: list[dict] = []

    for query in queries:
        os.environ["LLM_QUERY_ID"] = query.query_id
        started = time.perf_counter()
        try:
            query_run = solve_query(
                query,
                total=100,
                runtime_fingerprint=frozen_runtime,
            )
            latency = time.perf_counter() - started
            answers = query_run.answers
            gt = gts[query.query_id]
            metrics = {
                f"r_at_{threshold}": recall_at_k(
                    answers, gt, "KIS", threshold
                )
                for threshold in THRESHOLDS
            }
            metrics["final"] = final_score(answers, gt, "KIS")
            if metrics["final"] >= 1.0:
                failure_class = None
            elif any(row.get("video_id") == gt.video_id for row in query_run.search_rows):
                failure_class = "wrong_frame"
            else:
                failure_class = "retrieval_miss"

            plan = query_run.query_plan
            anchors = plan.get("anchors") or []
            violations = mapping_violations(answers, fmap)
            record = {
                "query_id": query.query_id,
                "task_type": "KIS",
                **metrics,
                "status": "success",
                "failure_class": failure_class,
                "strategy": plan.get("strategy"),
                "fallback_reason": plan.get("fallback_reason"),
                "anchor_count": len(anchors),
                "anchor_clip_tokens": [anchor.get("clip_tokens") for anchor in anchors],
                "output_rows": len(answers),
                "search_rows": len(query_run.search_rows),
                "frame_mapping_violations": violations,
                "latency_seconds": round(latency, 6),
                "runtime_fingerprint": query_run.runtime_fingerprint,
                "error": None,
            }
            append_jsonl(
                answers_path,
                {
                    "query_id": query.query_id,
                    "task_type": "KIS",
                    "answers": [
                        {
                            "video_id": answer.video_id,
                            "frame_ids": list(answer.frame_ids),
                            "keyframe_id": answer.keyframe_id,
                        }
                        for answer in answers
                    ],
                },
            )
            trace = query_run.to_trace_dict()
            trace["frame_mapping_violations"] = violations
            append_jsonl(traces_path, trace)
        except Exception as error:
            latency = time.perf_counter() - started
            failed_run = error.query_run if isinstance(error, SolveQueryError) else None
            record = {
                "query_id": query.query_id,
                "task_type": "KIS",
                **{f"r_at_{threshold}": 0.0 for threshold in THRESHOLDS},
                "final": 0.0,
                "status": "failed",
                "failure_class": (
                    failed_run.failure_class if failed_run is not None else "retrieval_miss"
                ),
                "strategy": (
                    failed_run.query_plan.get("strategy") if failed_run is not None else None
                ),
                "fallback_reason": (
                    failed_run.query_plan.get("fallback_reason")
                    if failed_run is not None else None
                ),
                "anchor_count": None,
                "anchor_clip_tokens": None,
                "output_rows": 0,
                "search_rows": 0,
                "frame_mapping_violations": [],
                "latency_seconds": round(latency, 6),
                "runtime_fingerprint": frozen_runtime,
                "error": f"{type(error).__name__}: {error}",
            }
            if failed_run is not None:
                append_jsonl(traces_path, failed_run.to_trace_dict())
        records.append(record)
        append_jsonl(records_path, record)
        print("KIS_RECORD=" + json.dumps(record, ensure_ascii=False), flush=True)

    if sha256_file(QUERY_PATH) != frozen_query_sha or sha256_file(GT_PATH) != frozen_gt_sha:
        raise RuntimeError("query/GT source đổi trong lúc diagnostic đang chạy")
    if runtime_fingerprint() != frozen_runtime:
        raise RuntimeError("runtime fingerprint đổi trong lúc diagnostic đang chạy")

    latencies = [record["latency_seconds"] for record in records]
    strategy_counts = Counter(record["strategy"] for record in records)
    fallback_counts = Counter(
        "null" if record["fallback_reason"] is None else record["fallback_reason"]
        for record in records
    )
    anchor_counts = Counter(record["anchor_count"] for record in records)
    summary = {
        "scope": "diagnostic_only_not_promotion",
        "query_count": len(records),
        "runtime_fingerprint": frozen_runtime,
        "strategy_counts": dict(sorted(strategy_counts.items(), key=lambda item: str(item[0]))),
        "fallback_reason_histogram": dict(sorted(fallback_counts.items())),
        "planner_error_count": fallback_counts.get("planner_error", 0),
        "anchor_count_histogram": {
            str(key): value for key, value in sorted(anchor_counts.items(), key=lambda item: str(item[0]))
        },
        "metrics": {
            "final": statistics.fmean(record["final"] for record in records),
            **{
                f"r_at_{threshold}": statistics.fmean(
                    record[f"r_at_{threshold}"] for record in records
                )
                for threshold in THRESHOLDS
            },
        },
        "latency_seconds": {
            "median": statistics.median(latencies),
            "p95_inclusive": percentile_inclusive(latencies, 0.95),
            "max": max(latencies),
        },
        "crash_count": sum(record["status"] != "success" for record in records),
        "mapping_violation_count": sum(
            len(record["frame_mapping_violations"]) for record in records
        ),
        "output_row_violation_count": sum(record["output_rows"] != 100 for record in records),
        "records": records,
    }
    (RUN_DIR / "scores.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("KIS_SUMMARY=" + json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
