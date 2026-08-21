# dev_set/tools/sweep_trake_asr_bonus.py — quét TRAKE_ASR_CONTEXT_BONUS_WEIGHT
# (backend/tasks/trake.py::_apply_asr_context_bonus). Xem reports/trake_hardening.md §6.
#
# Khác sweep_trake_config.py (không reimplement công thức song song): script
# này gọi THẲNG trake_search() thật, chỉ mock search() (đã fetch sẵn, tái
# dùng qua nhiều lần gọi) + monkeypatch TRAKE_ASR_CONTEXT_BONUS_WEIGHT mỗi
# vòng quét — đo đúng 100% hành vi code thật, không có rủi ro lệch giữa bản
# quét song song và bản production như cách cũ.
#
# Cố định candidates_per_event=20, min_gap=30 (đã chốt vòng quét trước) —
# CHỈ quét thêm chiều mới: trọng số bonus ASR.
#
# Đo trên 2 nguồn:
#   1. Bộ 8 câu TRAKE hiện có (2 người viết + 6 tổng hợp) — đảm bảo KHÔNG hồi
#      quy khi bật bonus mới.
#   2. Câu tai nạn giao thông thật (L21_V024) do người dùng cung cấp — không
#      có GT frame chính xác (chỉ có cửa sổ ASR gần đúng), nên đánh giá ĐỊNH
#      TÍNH: hạng của L21_V024 có tăng không, frame vị trí 4 có rời khỏi đoạn
#      tin sai (Phú Yên, ~frame 14500-15200) và về gần đoạn ASR đúng
#      (~11691-13343) không.
#
# Chạy (cần Docker ES+Milvus sống + ANTHROPIC_API_KEY):
#   python -m dev_set.tools.sweep_trake_asr_bonus

from __future__ import annotations

import json
import statistics
from pathlib import Path
from unittest.mock import patch

import backend.tasks.trake as trake_mod
from backend.retrieval.search import search as real_search
from dev_set.tools.scoring import K_THRESHOLDS, rscore_trake
from dev_set.tools.schema import GroundTruthTRAKE

ROOT_DIR = Path(__file__).resolve().parents[2]

# ⚠️ 20/08 22:xx — RRF_K vừa đổi 60→7 (đo thật, xem data/config/search_weights.py).
# c["score"] từ search() giờ LỚN HƠN NHIỀU (1/(K+rank) với K nhỏ) — MIN_BLEND_LAMBDA
# và ASR_CONTEXT_BONUS_WEIGHT (tune khi K=60) cần quét LẠI trên thang điểm mới,
# không thể giữ nguyên giá trị cũ. Quét ĐỒNG THỜI cả 2 tham số.
LAMBDA_SWEEP = [0.0, 0.5, 1.0, 2.0, 3.0, 5.0]
WEIGHT_SWEEP = [0.0, 0.5, 1.0, 2.0, 3.0, 5.0]

# Đoạn ASR ĐÚNG (đã xác nhận khớp gần nguyên văn 4 sự kiện — xem §6.1) và
# đoạn SAI (tin Phú Yên không liên quan) của câu tai nạn giao thông thật.
ACCIDENT_QUERY = {
    "video_id": "L21_V024",
    "events": [
        "Một nam thanh niên điều khiển xe máy lưu thông trên đường",
        "Bất ngờ chiếc xe máy va chạm mạnh với một chiếc xe ba gác chạy hướng ngược lại",
        "Người đàn ông ngồi trên xe ba gác ngã văng xuống đường",
        "Lực lượng chức năng có mặt tại hiện trường để điều tiết giao thông.",
    ],
}
ACCIDENT_CORRECT_WINDOW = (11691, 13343)  # đoạn ASR đúng (§6.1)
ACCIDENT_WRONG_WINDOW = (14552, 15111)    # đoạn ASR tin Phú Yên (§6.1)


def _recall_at_k(rscores: list[float], k: int) -> float:
    return max(rscores[:k], default=0.0)


def _final_score(rscores: list[float]) -> float:
    return sum(_recall_at_k(rscores, k) for k in K_THRESHOLDS) / len(K_THRESHOLDS)


def _load_trake_queries() -> list[dict]:
    out = []
    with open(ROOT_DIR / "dev_set/queries/tune_trake.jsonl", encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            d["source"] = "human"
            out.append(d)
    with open(ROOT_DIR / "dev_set/queries/synth_trake.jsonl", encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            d["source"] = "synthetic_vlm"
            out.append(d)
    return out


def _load_gt() -> dict[str, GroundTruthTRAKE]:
    out = {}
    with open(ROOT_DIR / "dev_set/ground_truth/tune_gt.jsonl", encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            if d.get("task_type") != "TRAKE":
                continue
            row = {k: v for k, v in d.items() if k != "task_type"}
            out[d["query_id"]] = GroundTruthTRAKE(**row)
    with open(ROOT_DIR / "dev_set/ground_truth/synth_gt.jsonl", encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            row = {k: v for k, v in d.items() if k != "task_type"}
            out[d["query_id"]] = GroundTruthTRAKE(**row)
    return out


def _fetch_and_cache(events: list[str]) -> dict[str, list[dict]]:
    """event_vi → raw hits (fetch 1 lần, top_k=TRAKE_EVENT_SEARCH_POOL)."""
    from data.config.search_weights import TRAKE_EVENT_SEARCH_POOL
    out = {}
    for e in events:
        out[e] = real_search(e, top_k=TRAKE_EVENT_SEARCH_POOL, group_by_shot=True)
    return out


def _mock_search_from_cache(cache: dict[str, list[dict]]):
    def _fake(query_vi, top_k=None, group_by_shot=None, **kw):
        return cache.get(query_vi, [])
    return _fake


def main() -> None:
    queries = _load_trake_queries()
    gts = _load_gt()
    print(f"{len(queries)} câu TRAKE dev-set + 1 câu tai nạn giao thông thật (định tính)")

    print("\nFetch raw hits (1 lần/câu, tái dùng cho mọi trọng số)...")
    per_query_cache: dict[str, dict[str, list[dict]]] = {}
    for q in queries:
        per_query_cache[q["query_id"]] = _fetch_and_cache(q["event_descs"])
    accident_cache = _fetch_and_cache(ACCIDENT_QUERY["events"])

    print("\nQuét (MIN_BLEND_LAMBDA, ASR_CONTEXT_BONUS_WEIGHT)...")
    human_ids = {q["query_id"] for q in queries if q["source"] == "human"}
    rows = []
    for lam in LAMBDA_SWEEP:
      for w in WEIGHT_SWEEP:
        with patch.object(trake_mod, "TRAKE_ASR_CONTEXT_BONUS_WEIGHT", w), \
             patch.object(trake_mod, "TRAKE_MIN_BLEND_LAMBDA", lam):
            # --- 8 câu dev-set: đo hồi quy ---
            finals, r1s, human_finals = [], [], []
            for q in queries:
                qid = q["query_id"]
                with patch.object(trake_mod, "search", side_effect=_mock_search_from_cache(per_query_cache[qid])):
                    candidates = trake_mod.trake_search(q["event_descs"], top_videos=100)
                gt = gts[qid]
                rscores = [rscore_trake(c.video_id, c.frame_ids, gt) for c in candidates]
                final = _final_score(rscores)
                finals.append(final)
                r1s.append(_recall_at_k(rscores, 1))
                if qid in human_ids:
                    human_finals.append(final)

            # --- câu tai nạn giao thông thật: đo định tính ---
            with patch.object(trake_mod, "search", side_effect=_mock_search_from_cache(accident_cache)):
                acc_candidates = trake_mod.trake_search(ACCIDENT_QUERY["events"], top_videos=100)
            acc_rank = next((i for i, c in enumerate(acc_candidates, 1)
                              if c.video_id == ACCIDENT_QUERY["video_id"]), None)
            acc_frame4 = None
            if acc_rank is not None:
                cand = next(c for c in acc_candidates if c.video_id == ACCIDENT_QUERY["video_id"])
                acc_frame4 = cand.frame_ids[3] if len(cand.frame_ids) == 4 else None
            frame4_correct = (acc_frame4 is not None and
                               ACCIDENT_CORRECT_WINDOW[0] - 200 <= acc_frame4 <= ACCIDENT_CORRECT_WINDOW[1] + 200)
            frame4_wrong_story = (acc_frame4 is not None and
                                   ACCIDENT_WRONG_WINDOW[0] - 200 <= acc_frame4 <= ACCIDENT_WRONG_WINDOW[1] + 200)

        row = {
            "lambda": lam, "weight": w,
            "avg_final_all8": statistics.mean(finals),
            "avg_r1_all8": statistics.mean(r1s),
            "avg_final_human2": statistics.mean(human_finals),
            "accident_rank": acc_rank,
            "accident_frame4": acc_frame4,
            "accident_frame4_correct_window": frame4_correct,
            "accident_frame4_wrong_story": frame4_wrong_story,
        }
        rows.append(row)
        print(f"  λ={lam:<4} w={w:<4} | 8-câu: final={row['avg_final_all8']:.3f} r1={row['avg_r1_all8']:.3f} "
              f"| người-viết(2): final={row['avg_final_human2']:.3f} "
              f"| tai_nạn: hạng={acc_rank} frame4={acc_frame4} "
              f"đúng_đoạn={frame4_correct} còn_sai_tin={frame4_wrong_story}")

    out_path = ROOT_DIR / "dev_set/results/trake_asr_bonus_sweep.json"
    out_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n📦 Đã ghi: {out_path}")


if __name__ == "__main__":
    main()
