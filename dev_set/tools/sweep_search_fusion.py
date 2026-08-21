# dev_set/tools/sweep_search_fusion.py — quét BRANCH_WEIGHTS/RRF_K của
# backend/retrieval/search.py trên bộ KIS holdout (36 câu, đồng đội cung cấp)
# + bộ KIS tune gốc (23 câu, dev-set cũ — kiểm hồi quy).
#
# ⚠️ Gọi THẲNG search() thật (không reimplement song song) — chấp nhận tốn
# thêm request mỗi tổ hợp, vì đây là tầng fusion LÕI dùng chung cho CẢ KIS,
# QA, TRAKE — sai lệch dù nhỏ giữa bản quét và bản thật sẽ lan ra khắp nơi.
# Đúng còn hơn nhanh ở đây.
#
# Phát hiện (đo thật 20/08, xem reports/): nhiều câu có 1 nhánh (ASR/OCR)
# xếp hạng RẤT TỐT (1-3) — đúng khớp văn bản — nhưng nhánh vector (CLIP) kém
# (hạng 20-250+), kéo tổng điểm RRF xuống thấp vì trọng số vector (1.0) >
# trọng số text (0.6) VÀ RRF_K=60 làm chênh lệch hạng 1 so với hạng 40 chỉ
# còn ~1.6 lần (không đủ áp đảo 1 đối thủ "khá đều cả hai nhánh").
#
# Chạy (cần Docker ES+Milvus sống + ANTHROPIC_API_KEY):
#   python -m dev_set.tools.sweep_search_fusion

from __future__ import annotations

import json
import statistics
from pathlib import Path
from unittest.mock import patch

import backend.retrieval.search as search_mod
import data.config.search_weights as sw_mod
from backend.retrieval.search import search
from dev_set.tools.scoring import K_THRESHOLDS, rscore_kis
from dev_set.tools.schema import GroundTruthKIS

ROOT_DIR = Path(__file__).resolve().parents[2]


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


CONFIGS = {
    "K=60 (baseline)": (dict(sw_mod.BRANCH_WEIGHTS), 60),
    "K=10": (dict(sw_mod.BRANCH_WEIGHTS), 10),
    "K=7": (dict(sw_mod.BRANCH_WEIGHTS), 7),
    "K=5": (dict(sw_mod.BRANCH_WEIGHTS), 5),
    "K=3": (dict(sw_mod.BRANCH_WEIGHTS), 3),
    "K=1": (dict(sw_mod.BRANCH_WEIGHTS), 1),
}


def _eval_set(rows: list[dict]) -> dict:
    finals, r1s = [], []
    for r in rows:
        res = search(r["query_vi"], query_en=r["query_en"], top_k=100, group_by_shot=True)
        rscores = [rscore_kis(x["video_id"], x["frame_idx"], r["gt"]) for x in res if x.get("frame_idx") is not None]
        finals.append(_final_score(rscores))
        r1s.append(_recall_at_k(rscores, 1))
    return {"final": statistics.mean(finals) if finals else 0.0,
            "r1": statistics.mean(r1s) if r1s else 0.0}


def main() -> None:
    holdout = _load_kis("dev_set/queries/holdout_kis.jsonl", "dev_set/ground_truth/holdout_gt.jsonl")
    tune = _load_kis("dev_set/queries/tune_kis.jsonl", "dev_set/ground_truth/tune_gt.jsonl")
    print(f"holdout KIS: {len(holdout)} câu · tune KIS (hồi quy): {len(tune)} câu")

    rows = []
    for name, (weights, k) in CONFIGS.items():
        with patch.object(sw_mod, "BRANCH_WEIGHTS", weights), \
             patch.object(search_mod, "RRF_K", k):
            hold_stats = _eval_set(holdout)
            tune_stats = _eval_set(tune)
        row = {"config": name, "holdout_final": hold_stats["final"], "holdout_r1": hold_stats["r1"],
               "tune_final": tune_stats["final"], "tune_r1": tune_stats["r1"]}
        rows.append(row)
        print(f"  {name:<38} | holdout final={row['holdout_final']:.3f} r1={row['holdout_r1']:.3f} "
              f"| tune(hồi quy) final={row['tune_final']:.3f} r1={row['tune_r1']:.3f}")

    out_path = ROOT_DIR / "dev_set/results/search_fusion_sweep.json"
    out_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n📦 Đã ghi: {out_path}")


if __name__ == "__main__":
    main()
