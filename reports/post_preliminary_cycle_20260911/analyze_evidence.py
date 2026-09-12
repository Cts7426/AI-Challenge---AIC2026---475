"""Tái tính thống kê từ ZIP đã chụp; không chạy engine, đổi scorer hoặc tạo GT."""
from __future__ import annotations

from collections import Counter
import csv
import io
import json
from pathlib import Path
import statistics
import zipfile

OUT = Path(__file__).resolve().parent


def main() -> None:
    """Input snapshot bất biến; output thống kê diagnostic có denominator rõ."""
    with zipfile.ZipFile(OUT / "evidence_and_cache_snapshot.zip") as evidence:
        def read_json(name: str):
            return json.loads(evidence.read(name).decode("utf-8-sig"))

        def read_jsonl(name: str):
            return [json.loads(line) for line in evidence.read(name).decode("utf-8-sig").splitlines() if line.strip()]

        result = {"label": "POST-PRELIMINARY / POST-COMPETITION INTERNAL EVALUATION",
                  "scope": "Phân tích lại artefact lịch sử; không phải accuracy run mới", "kis": {}}
        for part, suffix in (("p1", "llm"), ("p2", "holdout")):
            name = f"dev_set/results/run_20260903_merge_{part}_{suffix}.json"
            data = read_json(name)
            rows = data["per_query"]
            found = [row for row in rows if row.get("video_rank") is not None]
            result["kis"][part] = {
                "source": name, "n_queries": len(rows), "video_found": len(found),
                "video_missing": [r["query_id"] for r in rows if r.get("video_rank") is None],
                "video_below5": [r["query_id"] for r in found if r["video_rank"] > 5],
                "video_found_no_frame_pm40": [r["query_id"] for r in found if r["final_frame"]["40"] == 0],
                "video_found_no_frame_pm5": [r["query_id"] for r in found if r["final_frame"]["5"] == 0],
                "aggregate_recorded": data["aggregate"],
            }
        rows = read_jsonl("submissions/round3/trace.jsonl")
        result["round3"] = {}
        for task in ("KIS", "QA", "TRAKE"):
            group = [r for r in rows if r["task_type"] == task]
            times = [r["timings"]["total_seconds"] for r in group]
            result["round3"][task] = {
                "n_queries": len(group), "status_counts": dict(Counter(r["status"] for r in group)),
                "latency_median_s": statistics.median(times), "latency_min_s": min(times),
                "latency_max_s": max(times), "latency_total_s": sum(times),
            }
        qa = [r for r in rows if r["task_type"] == "QA"]
        placeholders = [r for r in qa if any(str(h.get("provenance", "")).startswith("placeholder:")
                                             for h in r["qa_hypotheses"])]
        result["round3"]["QA"]["placeholder_queries"] = [r["query_id"] for r in placeholders]
        csv_counts = []
        for row in placeholders:
            name = f"submissions/round3/submission/{row['query_id']}.csv"
            parsed = list(csv.reader(io.StringIO(evidence.read(name).decode("utf-8-sig"))))
            csv_counts.append({"path": name, "rows": len(parsed),
                               "todo_rows": sum(r[-1].strip() == "TODO" for r in parsed)})
        result["round3"]["QA"]["placeholder_csvs"] = csv_counts
        trake = []
        for row in (r for r in rows if r["task_type"] == "TRAKE"):
            candidates = row["task_metadata"]["candidates"]
            trake.append({"query_id": row["query_id"], "n_candidates": len(candidates),
                          "candidates_with_interpolation": sum(None in c["keyframe_ids"] for c in candidates),
                          "interpolated_positions": sum(k is None for c in candidates for k in c["keyframe_ids"]),
                          "total_positions": sum(len(c["keyframe_ids"]) for c in candidates),
                          "top20_with_interpolation": sum(None in c["keyframe_ids"] for c in candidates[:20])})
        result["round3"]["TRAKE"]["candidate_provenance"] = trake
        result["trake_fixed_hit_experiment"] = read_json("dev_set/results/r3t2_official_trake_20260903.json")["aggregate"]
        result["dress_single_anchor"] = read_json("dev_set/results/run_20260828_round2_single_anchor_final_01/scores.json")
        result["dress_multi_anchor"] = read_json("dev_set/results/run_20260827_kis19_multi_anchor_01/scores.json")
        dress = read_jsonl("dev_set/results/run_20260827_154710_27d970c1/candidates.jsonl")
        dress_qa = [r for r in dress if r["task_type"] == "QA"]
        result["dress_qa"] = {"n_queries": len(dress_qa),
                               "status_counts": dict(Counter(r["status"] for r in dress_qa)),
                               "total_seconds": sum(r["timings"]["total_seconds"] for r in dress_qa),
                               "median_seconds": statistics.median(r["timings"]["total_seconds"] for r in dress_qa)}
    path = OUT / "recomputed_diagnostics.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(path), "p2_video_found": result["kis"]["p2"]["video_found"],
                      "p2_found_no_frame_pm40": len(result["kis"]["p2"]["video_found_no_frame_pm40"]),
                      "round3_qa_placeholders": len(placeholders)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
