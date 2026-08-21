# dev_set/tools/sweep_candidate_multiplier.py — quét CANDIDATE_MULTIPLIER
# (pool = top_k * hệ số, lấy TRƯỚC RRF/gom-shot) trên KIS tune + holdout.
#
# Giả thuyết (20/08, đêm trước Đợt 1): pool=500 (top_k=100 * hệ số 5 mặc định)
# là RỔ TOÀN CỤC (không theo video) — với corpus ~549K vector sau khi vá CLIP,
# 500 chỉ là ~0.09% tổng kho. Câu nào có đúng keyframe xếp hạng thô > 500 (trước
# RRF) bị cắt trước khi RRF/gom-shot kịp thấy — KHÔNG LIÊN QUAN tới lỗ hổng
# coverage CLIP đang vá riêng (dev_set/tools/eval_kis_only.py).
#
# 0 lượt gọi llm() nếu mọi câu đã có query_en sẵn (holdout_kis.jsonl luôn có;
# tune_kis.jsonl một phần dựa cache cũ).
#
# Chạy: python -m dev_set.tools.sweep_candidate_multiplier

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path
from unittest.mock import patch

import backend.retrieval.search as search_mod
from backend.retrieval.search import search
from dev_set.tools.scoring import K_THRESHOLDS, rscore_kis
from dev_set.tools.schema import GroundTruthKIS

ROOT_DIR = Path(__file__).resolve().parents[2]
MULTIPLIERS = [5, 10, 20, 40]


def _recall_at_k(rscores, k):
    return max(rscores[:k], default=0.0)


def _final_score(rscores):
    return sum(_recall_at_k(rscores, k) for k in K_THRESHOLDS) / len(K_THRESHOLDS)


def _load_kis(query_path: str, gt_path: str) -> list[dict]:
    queries = {}
    with open(ROOT_DIR / query_path, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            queries[d["query_id"]] = d
    out = []
    with open(ROOT_DIR / gt_path, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            if d.get("task_type") != "KIS" or d["query_id"] not in queries:
                continue
            q = queries[d["query_id"]]
            out.append({"query_id": d["query_id"], "query_vi": q["query_vi"],
                        "query_en": q.get("query_en"), "gt": GroundTruthKIS(
                            query_id=d["query_id"], video_id=d["video_id"],
                            frame_start=d["frame_start"], frame_end=d["frame_end"])})
    return out


def _eval_set(rows: list[dict]) -> dict:
    finals, r1s, r100s, latencies = [], [], [], []
    for r in rows:
        t0 = time.time()
        res = search(r["query_vi"], query_en=r["query_en"], top_k=100, group_by_shot=True)
        latencies.append(time.time() - t0)
        rscores = [rscore_kis(x["video_id"], x["frame_idx"], r["gt"]) for x in res if x.get("frame_idx") is not None]
        finals.append(_final_score(rscores))
        r1s.append(_recall_at_k(rscores, 1))
        r100s.append(_recall_at_k(rscores, 100))
    return {"final": statistics.mean(finals) if finals else 0.0,
            "r1": statistics.mean(r1s) if r1s else 0.0,
            "r100": statistics.mean(r100s) if r100s else 0.0,
            "p50_latency_s": statistics.median(latencies) if latencies else 0.0,
            "max_latency_s": max(latencies) if latencies else 0.0}


def main() -> None:
    holdout = _load_kis("dev_set/queries/holdout_kis.jsonl", "dev_set/ground_truth/holdout_gt.jsonl")
    tune = _load_kis("dev_set/queries/tune_kis.jsonl", "dev_set/ground_truth/tune_gt.jsonl")
    print(f"holdout KIS: {len(holdout)} câu · tune KIS (hồi quy): {len(tune)} câu")

    rows = []
    for mult in MULTIPLIERS:
        with patch.object(search_mod, "CANDIDATE_MULTIPLIER", mult):
            hold_stats = _eval_set(holdout)
            tune_stats = _eval_set(tune)
        row = {"multiplier": mult, "pool": 100 * mult,
               "holdout_final": hold_stats["final"], "holdout_r1": hold_stats["r1"], "holdout_r100": hold_stats["r100"],
               "tune_final": tune_stats["final"], "tune_r1": tune_stats["r1"], "tune_r100": tune_stats["r100"],
               "holdout_p50_latency_s": hold_stats["p50_latency_s"], "holdout_max_latency_s": hold_stats["max_latency_s"]}
        rows.append(row)
        print(f"  pool={row['pool']:5d} (x{mult:2d}) | holdout final={row['holdout_final']:.3f} "
              f"r1={row['holdout_r1']:.3f} r100={row['holdout_r100']:.3f} "
              f"p50_lat={row['holdout_p50_latency_s']:.2f}s max={row['holdout_max_latency_s']:.2f}s "
              f"| tune final={row['tune_final']:.3f} r1={row['tune_r1']:.3f} r100={row['tune_r100']:.3f}")

    out_path = ROOT_DIR / "dev_set/results/candidate_multiplier_sweep.json"
    out_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n📦 Đã ghi: {out_path}")


if __name__ == "__main__":
    main()
