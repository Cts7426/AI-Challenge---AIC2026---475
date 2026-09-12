"""PP-H01: đóng identity trước output và đo qua đúng runner/exporter production.

Chạy từ gốc repo bằng `python -m scripts.run_reproducible_baseline --help`.
Manifest mới không có nghĩa là baseline đã được promotion; mọi gap vẫn hiện rõ.
"""
from __future__ import annotations

import argparse
from contextlib import nullcontext
from dataclasses import asdict
from datetime import datetime, timezone
from functools import lru_cache
import json
from pathlib import Path
import time

from backend.common.resource_identity import (capture_manifest, cache_identity, file_identity, manifest_id,
                                             reproducibility_gaps, require_reproducible,
                                             stable_resource_id, validate_resume_identity)

ROOT = Path(__file__).resolve().parents[1]


def _write_json(path: Path, value: dict) -> None:
    from backend.tasks.runner import _json_safe
    path.write_text(json.dumps(_json_safe(value), ensure_ascii=False, indent=2,
                               allow_nan=False), encoding="utf-8")


def query_identity(query: dict) -> str:
    """Hash toàn input, kể cả anchors của Q&A; không bỏ field ảnh hưởng output."""
    return manifest_id(query)


def create_run_directory(path: Path) -> None:
    """Không được ghi đè output/checkpoint của run trước."""
    path.mkdir(parents=True, exist_ok=False)


def read_checkpoint(out: Path, queries: list[dict], runtime_id: str, *, current_cache: dict | None = None) -> dict[str, dict]:
    """Đọc append log, kiểm query/identity/CSV trước khi skip; không tự sửa log hỏng."""
    expected = {query["query_id"]: query_identity(query) for query in queries}
    records = {}
    path = out / "queries.jsonl"
    if not path.exists():
        return records
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            query_id = row["input"]["query_id"]
            if (row["query_sha256"] != expected.get(query_id)
                    or row["runtime_manifest_id"] != runtime_id):
                raise ValueError("checkpoint query/identity khác run đã khóa")
            if current_cache is not None:
                if "cache_after" not in row or row.get("cache_after_id") != manifest_id(row["cache_after"]):
                    raise ValueError("checkpoint thiếu hoặc sai hash cache sau query")
                validate_resume_identity({"cache": row["cache_after"]}, {"cache": current_cache})
            if row["export_status"] == "written":
                files = row.get("export_files", {})
                if not files:
                    raise ValueError("checkpoint thiếu identity CSV")
                for name, identity in files.items():
                    if Path(name).name != name or file_identity(out / "submission" / name) != identity:
                        raise ValueError("CSV trong checkpoint đã đổi hoặc mất")
            records[query_id] = row
        except (KeyError, TypeError, json.JSONDecodeError) as error:
            raise ValueError("checkpoint bị hỏng; giữ nguyên để điều tra") from error
    return records


@lru_cache(maxsize=1)
def _keyframe_videos() -> dict[str, str]:
    """Video của khóa lấy từ parquet, alias dựng từ frame_map, không suy frame từ tên."""
    import pandas as pd
    from backend.indexing.frame_map import FRAME_MAP_PATH
    df = pd.read_parquet(FRAME_MAP_PATH, columns=["kf_id", "video_id", "frame_idx"])
    result = {}
    for key, video, frame in df.itertuples(index=False, name=None):
        result[key] = str(video)
        result[f"{video}_{int(frame):07d}"] = str(video)
    return result


def audit_mapping(answers: list) -> tuple[list[dict], int]:
    """Đối chiếu keyframe với map thật; frame không có reference phải ghi riêng.

    Không suy hậu tố, không gán provenance cho frame allocator rải/nội suy.
    Bounds/format của mọi frame được exporter kiểm độc lập.
    """
    from backend.indexing.frame_map import load_frame_map
    mapping = load_frame_map()
    videos = _keyframe_videos()
    rows, violations = [], 0
    for rank, answer in enumerate(answers, 1):
        key = answer.keyframe_id
        mapped = mapping.get(key) if key else None
        if not key:
            status = "no_keyframe_reference"
        elif mapped is None:
            status = "missing_keyframe"
            violations += 1
        elif videos.get(key) != answer.video_id:
            status = "video_mismatch"
            violations += 1
        elif mapped not in answer.frame_ids:
            status = "mismatch"
            violations += 1
        else:
            status = "matched"
        rows.append({"rank": rank, "video_id": answer.video_id, "frame_ids": list(answer.frame_ids),
                     "keyframe_id": key, "mapped_frame": mapped, "status": status})
    return rows, violations


def audit_candidate_mapping(task_output: dict) -> tuple[list[dict], int]:
    """Đối chiếu từng vị trí sự kiện TRAKE; chỉ ghi nhận, không sửa nội suy/đáp án."""
    from data.config.submit_format import Answer
    if task_output.get("task_type") != "TRAKE":
        return [], 0
    records, violations = [], 0
    for rank, candidate in enumerate(task_output.get("search_rows", []), 1):
        keys, frames = candidate.get("keyframe_ids", []), candidate.get("frame_ids", [])
        if len(keys) != len(frames):
            records.append({"candidate_rank": rank, "status": "event_count_mismatch"})
            violations += 1
            continue
        for index, (key, frame) in enumerate(zip(keys, frames)):
            rows, errors = audit_mapping([Answer(candidate["video_id"], (frame,), keyframe_id=key)])
            records.append({**rows[0], "candidate_rank": rank, "event_index": index})
            violations += errors
    return records, violations


def execute_query(query: dict, out: Path, runtime_id: str, *, instrumentation: bool, qa_policy: str) -> dict:
    """Runner/export thật; lỗi vẫn trả trace và không được tính là baseline thành công."""
    from backend.common.retrieval_trace import capture_retrieval
    from backend.export.exporter import QuerySubmission, validate_submission, write_submissions
    from backend.export.qa_variants import apply_qa_submission_policy
    from backend.llm.adapter import usage_report
    from backend.tasks import runner
    before_usage = usage_report()
    started = time.perf_counter()
    with capture_retrieval() if instrumentation else nullcontext([]) as calls:
        try:
            result = runner.solve_query(query, total=100, runtime_fingerprint=runtime_id)
        except runner.SolveQueryError as error:
            result = error.query_run
    record = {"input": query, "query_sha256": query_identity(query), "runtime_manifest_id": runtime_id,
              "task_output": result.to_trace_dict(), "search_calls": calls,
              "instrumentation": instrumentation, "qa_submission_policy": qa_policy,
              "export_status": "not_exported", "export_ranking": [], "frame_mapping": [],
              "mapping_violations": None, "export_violations": None, "errors": [],
              "usage_delta": {k: usage_report()[k] - v for k, v in before_usage.items()}}
    if misses := record["usage_delta"].get("cache_only_misses", 0):
        # Caller có thể bắt lỗi dịch/suy luận để fallback; không nhận output đó
        # thành baseline đầy đủ evidence khi operator chỉ cho replay cache.
        record["export_status"] = "blocked_cache_miss"
        record["errors"] = [{"stage": "llm_cache_only", "missing_calls": misses}]
        record["seconds"] = time.perf_counter() - started
        return runner._json_safe(record)
    if result.status == "success":
        answers = (apply_qa_submission_policy(result.answers, qa_policy)
                   if result.task_type == "QA" else result.answers)
        record["export_ranking"] = [asdict(answer) for answer in answers]
        try:
            record["frame_mapping"], record["mapping_violations"] = audit_mapping(answers)
            record["candidate_mapping"], candidate_errors = audit_candidate_mapping(record["task_output"])
            record["mapping_violations"] += candidate_errors
            sub = QuerySubmission(result.query_id, result.task_type, tuple(answers))
            issues = validate_submission(sub, expected_n=result.n_trake)
            record["export_violations"] = len(issues)
            record["errors"] = [asdict(issue) for issue in issues]
            if not issues:
                files, issues = write_submissions([sub], out / "submission", expected_n={result.query_id: result.n_trake})
                record["export_status"] = "written" if not issues else "invalid"
                record["export_violations"] += len(issues)
                record["errors"].extend(asdict(issue) for issue in issues)
                record["export_files"] = {path.name: file_identity(path) for path in files}
        except Exception as error:
            record["errors"].append({"stage": "mapping_export", "type": type(error).__name__, "message": str(error)})
            record["export_status"] = "failed"
    record["seconds"] = time.perf_counter() - started
    return runner._json_safe(record)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--queries", type=Path)
    parser.add_argument("--capture-only", action="store_true")
    parser.add_argument("--offline", action="store_true", help="chỉ chụp identity, không nhận baseline")
    parser.add_argument("--content-digests", action="store_true", help="hash mọi document/entity live, chỉ đọc")
    parser.add_argument("--instrumentation", choices=("on", "off"), default="on")
    parser.add_argument("--qa-submission-policy", choices=("semantic", "exact", "robust"), required=True)
    parser.add_argument("--baseline-label", choices=("PP-B0", "PP-B0-RESTORED"), required=True)
    parser.add_argument("--expected-resource-manifest", type=Path)
    parser.add_argument("--resume", action="store_true", help="tiếp tục đúng run; kiểm source/model/data/cache và CSV trước khi skip")
    args = parser.parse_args()
    if args.resume and args.capture_only:
        parser.error("--resume chỉ dùng cho run, không ghi đè capture-only")
    queries = []
    if not args.capture_only:
        from backend.llm.adapter import selected_runtime
        from run import _doc_queries, _llm_runtime_errors
        selected_runtime()  # trước imports DB, đọc cache hoặc sinh output
        if args.queries is None or args.offline:
            parser.error("run thật cần --queries và không dùng --offline")
        queries = _doc_queries(args.queries)
        errors = _llm_runtime_errors(queries)
        if errors:
            raise ValueError("; ".join(errors))
    if not args.resume:
        create_run_directory(args.out)
    elif not (args.out / "runtime_manifest.json").is_file():
        parser.error("--resume cần runtime_manifest.json của run trước")
    identity = capture_manifest(ROOT, live=not args.offline, content_digests=args.content_digests)
    identity_id = manifest_id(identity)
    manifest = {"manifest_id": identity_id, "identity": identity,
                "captured_at": datetime.now(timezone.utc).isoformat(), "baseline_label": args.baseline_label,
                "promotion": "not_evaluated", "instrumentation": args.instrumentation,
                "qa_submission_policy": args.qa_submission_policy,
                "reproducibility_gaps": reproducibility_gaps(identity)}
    if not args.resume:
        _write_json(args.out / "runtime_manifest.json", manifest)
    if args.capture_only:
        print(f"identity={identity_id}; capture_only")
        return 0
    require_reproducible(identity)
    # Dataset diagnostic đã dùng trước đây; GT/sealed mới không được tự suy ra.
    query_manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(), "role": "diagnostic_regression",
        "source": str(args.queries), "source_identity": file_identity(args.queries),
        "queries": [{"input": query, "sha256": query_identity(query)} for query in queries],
        "independent_accuracy_claim": False}
    if args.resume:
        prior = json.loads((args.out / "runtime_manifest.json").read_text(encoding="utf-8"))
        if prior["manifest_id"] != manifest_id(prior["identity"]):
            raise ValueError("runtime manifest không khớp checksum")
        require_reproducible(prior["identity"])
        validate_resume_identity(prior["identity"], identity)
        for key in ("instrumentation", "qa_submission_policy", "baseline_label"):
            if prior[key] != manifest[key]:
                raise ValueError(f"resume đổi {key}")
        frozen = json.loads((args.out / "query_manifest.json").read_text(encoding="utf-8"))
        if frozen["queries"] != query_manifest["queries"]:
            raise ValueError("query manifest khác run đã khóa")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        _write_json(args.out / f"resume_{stamp}.json", manifest)
        identity_id = prior["manifest_id"]
    else:
        _write_json(args.out / "query_manifest.json", query_manifest)
    if args.expected_resource_manifest:
        expected = json.loads(args.expected_resource_manifest.read_text(encoding="utf-8"))["identity"]
        require_reproducible(expected)
        # Cache/model/source cũng phải giống; warm cache không được giả làm paired lạnh.
        if manifest_id(expected) != identity_id:
            raise ValueError("Identity khác manifest đã khóa; chưa được chạy cặp")
    records_by_id = read_checkpoint(args.out, queries, identity_id, current_cache=identity["cache"]) if args.resume else {}
    with (args.out / "queries.jsonl").open("a" if args.resume else "x", encoding="utf-8") as stream:
        for query in queries:
            previous = records_by_id.get(query["query_id"])
            if (previous and previous["task_output"]["status"] == "success"
                    and previous["export_status"] == "written"
                    and previous.get("mapping_violations") == 0 and previous.get("export_violations") == 0):
                print(f"{query['query_id']}: checkpoint đã kiểm, skip", flush=True)
                continue
            record = execute_query(query, args.out, identity_id,
                                   instrumentation=args.instrumentation == "on", qa_policy=args.qa_submission_policy)
            # Cache sinh bởi query cũng phải được bảo vệ ở mọi lần resume sau.
            # Ghi cùng dòng checkpoint để không thể có success mà thiếu snapshot.
            cache_started = time.perf_counter()
            record["cache_after"] = cache_identity(ROOT)
            record["cache_after_id"] = manifest_id(record["cache_after"])
            record["cache_snapshot_seconds"] = time.perf_counter() - cache_started
            stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
            stream.flush()
            records_by_id[query["query_id"]] = record
            print(f"{query['query_id']}: {record['task_output']['status']} {record['seconds']:.3f}s", flush=True)
    after = capture_manifest(ROOT, live=True, content_digests=args.content_digests)
    _write_json(args.out / "runtime_after.json", {"manifest_id": manifest_id(after), "identity": after})
    records = [records_by_id[query["query_id"]] for query in queries]
    failures = sum(row["task_output"]["status"] != "success" or row["export_status"] != "written" for row in records)
    resource_changed = stable_resource_id(identity) != stable_resource_id(after)
    cache_changed = False
    try:
        validate_resume_identity(identity, after)
        for row in records:
            validate_resume_identity({"cache": row["cache_after"]}, {"cache": after["cache"]})
    except ValueError:
        cache_changed = True
    summary = {"queries": len(records), "failures": failures,
               "mapping_violations": sum(row["mapping_violations"] or 0 for row in records),
               "export_violations": sum(row["export_violations"] or 0 for row in records),
               "unknown_mapping_checks": sum(row["mapping_violations"] is None for row in records),
               "identity_before": identity_id, "identity_after": manifest_id(after),
               "stable_resource_changed": resource_changed,
               "cache_integrity_changed": cache_changed,
               "reproducibility_gaps_after": reproducibility_gaps(after),
               "promotion": "requires_evidence_review", "independent_accuracy_claim": False}
    _write_json(args.out / "measurements.json", summary)
    return int(bool(failures or summary["mapping_violations"] or summary["export_violations"]
                    or resource_changed or cache_changed or summary["reproducibility_gaps_after"]))


if __name__ == "__main__":
    raise SystemExit(main())
