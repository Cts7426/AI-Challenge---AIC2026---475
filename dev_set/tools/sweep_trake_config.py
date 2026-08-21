# dev_set/tools/sweep_trake_config.py — quét tham số/công thức TRAKE trên bộ
# đề mở rộng (2 câu người viết TR01/TR02 + 6 câu tổng hợp STR01-06), CHỌN
# cấu hình tốt nhất đo được. Xem kế hoạch: reports/trake_hardening.md.
#
# ===== Thiết kế: 1 lần fetch, nhiều lần đo cục bộ =====
# search() (mạng + DB) chỉ tốn ở bước fetch top-K RAW mỗi sự kiện — không phụ
# thuộc candidates_per_event/min_gap/công thức điểm. Fetch MỘT LẦN với pool
# rộng (TRAKE_EVENT_SEARCH_POOL), cache trong RAM, rồi quét cấu hình hoàn
# toàn CỤC BỘ (chỉ gọi lại _topk_per_video/_align_events_in_video — hàm
# thuần, không I/O) — nhanh, không tốn thêm 1 request nào cho mỗi tổ hợp.
#
# Tái dùng NGUYÊN VẸN _topk_per_video (đã nhận k) và _align_events_in_video
# (đã nhận min_gap) từ backend/tasks/trake.py — KHÔNG sửa file đó trong lúc
# quét. Công thức tổng hợp điểm (sum/min-blend/geomean) tính TỪ `chain` (đã
# có sẵn từng điểm mỗi vị trí) ngay trong script này — chỉ khi có kết quả rõ
# ràng mới áp dụng lại vào backend/tasks/trake.py::_localize_in_video.
#
# Chạy (cần Docker ES+Milvus sống + ANTHROPIC_API_KEY):
#   python -m dev_set.tools.sweep_trake_config

from __future__ import annotations

import json
import statistics
from itertools import product
from pathlib import Path

from backend.tasks.trake import _align_events_in_video, _topk_per_video
from backend.retrieval.search import search
from data.config.search_weights import TRAKE_EVENT_SEARCH_POOL
from dev_set.tools.scoring import K_THRESHOLDS, rscore_trake
from dev_set.tools.schema import GroundTruthTRAKE


def _recall_at_k(rscores: list[float], k: int) -> float:
    """R@k = R-Score CAO NHẤT trong k dòng đầu — CÙNG định nghĩa với
    dev_set/tools/scoring.py::recall_at_k, viết lại cục bộ vì hàm gốc nhận
    list[Answer] (dựng Answer chỉ để gọi lại là phí — sweep này đã có sẵn
    rscores dạng float từ rscore_trake())."""
    return max(rscores[:k], default=0.0)


def _final_score(rscores: list[float]) -> float:
    """Final = trung bình 5 R@k — CÙNG công thức dev_set/tools/scoring.py::final_score."""
    return sum(_recall_at_k(rscores, k) for k in K_THRESHOLDS) / len(K_THRESHOLDS)

ROOT_DIR = Path(__file__).resolve().parents[2]

# ------------------------------------------------------------- đọc bộ đề

def _load_trake_queries() -> list[dict]:
    """TR01/TR02 (gốc, dev_set/queries/tune_trake.jsonl — nay đã KHÔI PHỤC về
    đúng 2 câu người viết) + STR01-06 (tổng hợp) — đọc từ 2 nguồn riêng, gắn
    field `source` (chỉ dùng trong sweep, không cần trong JSON nộp cho
    run_evaluation.py, xem generate_trake_synthetic.py)."""
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
    for fname in ["dev_set/ground_truth/tune_gt.jsonl", "dev_set/ground_truth/synth_gt.jsonl"]:
        with open(ROOT_DIR / fname, encoding="utf-8") as f:
            for line in f:
                d = json.loads(line)
                if d.get("task_type") != "TRAKE":
                    continue
                row = {k: v for k, v in d.items() if k != "task_type"}
                out[d["query_id"]] = GroundTruthTRAKE(**row)
    return out


# --------------------------------------------------------- fetch 1 lần

def _fetch_raw_hits(queries: list[dict]) -> dict[str, list[list[dict]]]:
    """query_id → [hits sự kiện 0, hits sự kiện 1, ...] — raw, top-K rộng,
    CHƯA cắt theo candidates_per_event (cắt đó là bước cục bộ trong sweep)."""
    out = {}
    for q in queries:
        events = q["event_descs"]
        print(f"  fetch {q['query_id']} ({len(events)} sự kiện)...")
        per_event = [search(e, top_k=TRAKE_EVENT_SEARCH_POOL, group_by_shot=True) for e in events]
        out[q["query_id"]] = per_event
    return out


# --------------------------------------------------- công thức tổng hợp điểm

def _score_sum(position_scores: list[float], bonus: float) -> float:
    """Baseline hiện tại: tổng điểm × bonus."""
    return sum(position_scores) * bonus


def _score_min_blend(lam: float):
    def f(position_scores: list[float], bonus: float) -> float:
        return (sum(position_scores) + lam * min(position_scores)) * bonus
    return f


def _score_geomean(position_scores: list[float], bonus: float) -> float:
    """Trung bình nhân — phạt vị trí yếu mạnh hơn tổng/trung bình cộng."""
    n = len(position_scores)
    prod = 1.0
    for s in position_scores:
        prod *= max(s, 1e-9)  # điểm RRF luôn > 0 thực tế, chặn dưới phòng log(0)
    return (prod ** (1.0 / n)) * bonus * n  # ×n để cùng thang bậc với sum×bonus


SCORE_FORMULAS = {
    "sum (baseline)": _score_sum,
    "min_blend_0.5": _score_min_blend(0.5),
    "min_blend_1.0": _score_min_blend(1.0),
    "min_blend_2.0": _score_min_blend(2.0),
    "geomean": _score_geomean,
}


# ------------------------------------------------------- 1 tổ hợp cấu hình

def _localize_with_config(vid: str, per_event_hits: list[list[dict]],
                           candidates_per_event: int, min_gap: int,
                           bonus: float, formula) -> tuple[float, tuple[int, ...]]:
    """Bản THAM SỐ HOÁ của backend.tasks.trake._localize_in_video, chỉ dùng
    trong sweep — KHÔNG thay backend/tasks/trake.py. Trả (score, frame_ids)
    cho MỘT video, MỘT tổ hợp cấu hình."""
    from backend.tasks.trake import _fill_missing, _repair_strictly_increasing
    from backend.export import n_frames_of

    n = len(per_event_hits)
    topk = [_topk_per_video(hits, candidates_per_event) for hits in per_event_hits]
    candidates_by_position = [t.get(vid, []) for t in topk]
    chain, _ = _align_events_in_video(candidates_by_position, min_gap=min_gap)
    has_full_order = len(chain) == n

    if has_full_order:
        position_scores = [s for _, _, _, s in chain]
        frame_ids = [f for _, f, _, _ in chain]
        score = formula(position_scores, bonus)
    else:
        frame_or_none: list[int | None] = [None] * n
        chain_positions = {j for j, _, _, _ in chain}
        position_scores_partial: list[float] = []
        for j, f, _, s in chain:
            frame_or_none[j] = f
            position_scores_partial.append(s)
        for j, cands in enumerate(candidates_by_position):
            if not cands or j in chain_positions:
                continue
            position_scores_partial.append(max(c["score"] for c in cands))
        # nhánh không-bonus: giữ nguyên Ý ĐỒ log-sum gốc (không nhân bonus),
        # nhưng vẫn dùng CÙNG công thức tổng hợp để so sánh nhất quán giữa
        # các biến thể (bonus=1.0 ở đây, không phải TRAKE_ORDER_BONUS)
        score = formula(position_scores_partial, 1.0) if position_scores_partial else 0.0
        frame_ids = _fill_missing(frame_or_none)

    frame_ids = _repair_strictly_increasing(frame_ids, n_frames_of(vid))
    return score, tuple(frame_ids)


def _evaluate_config(queries: list[dict], gts: dict[str, GroundTruthTRAKE],
                      raw_hits: dict[str, list[list[dict]]],
                      candidates_per_event: int, min_gap: int, bonus: float,
                      formula_name: str) -> dict[str, dict]:
    """1 tổ hợp cấu hình → {query_id: {final, r_at_1, ...}}."""
    formula = SCORE_FORMULAS[formula_name]
    out = {}
    for q in queries:
        qid = q["query_id"]
        per_event_hits = raw_hits[qid]
        topk = [_topk_per_video(hits, candidates_per_event) for hits in per_event_hits]
        all_videos: set[str] = set()
        for t in topk:
            all_videos.update(t)
        if not all_videos:
            out[qid] = {"final": 0.0, "r_at_1": 0.0}
            continue

        scored = [
            (vid, *_localize_with_config(vid, per_event_hits, candidates_per_event,
                                          min_gap, bonus, formula))
            for vid in all_videos
        ]
        scored.sort(key=lambda t: t[1], reverse=True)
        top100 = scored[:100]

        gt = gts[qid]
        rscores = [rscore_trake(vid, frames, gt) for vid, _, frames in top100]
        out[qid] = {
            "final": _final_score(rscores),
            "r_at_1": _recall_at_k(rscores, 1),
        }
    return out


# ------------------------------------------------------------------- main

def main() -> None:
    queries = _load_trake_queries()
    gts = _load_gt()
    print(f"{len(queries)} câu TRAKE ({sum(1 for q in queries if q['source']=='human')} người viết + "
          f"{sum(1 for q in queries if q['source']=='synthetic_vlm')} tổng hợp)")

    print("\nFetch raw hits (1 lần, tái dùng cho mọi tổ hợp)...")
    raw_hits = _fetch_raw_hits(queries)

    CANDIDATES_PER_EVENT_SWEEP = [6, 12, 20]
    MIN_GAP_SWEEP = [10, 20, 30]
    FORMULA_SWEEP = list(SCORE_FORMULAS.keys())
    from data.config.search_weights import TRAKE_ORDER_BONUS

    human_ids = {q["query_id"] for q in queries if q["source"] == "human"}
    results = []

    combos = list(product(CANDIDATES_PER_EVENT_SWEEP, MIN_GAP_SWEEP, FORMULA_SWEEP))
    print(f"\nQuét {len(combos)} tổ hợp...")
    for i, (k, gap, formula_name) in enumerate(combos, 1):
        per_q = _evaluate_config(queries, gts, raw_hits, k, gap, TRAKE_ORDER_BONUS, formula_name)
        finals = [v["final"] for v in per_q.values()]
        r1s = [v["r_at_1"] for v in per_q.values()]
        human_finals = [v["final"] for qid, v in per_q.items() if qid in human_ids]
        human_r1s = [v["r_at_1"] for qid, v in per_q.items() if qid in human_ids]
        row = {
            "candidates_per_event": k, "min_gap": gap, "formula": formula_name,
            "avg_final_all": statistics.mean(finals), "avg_r1_all": statistics.mean(r1s),
            "avg_final_human": statistics.mean(human_finals), "avg_r1_human": statistics.mean(human_r1s),
        }
        results.append(row)
        print(f"  [{i}/{len(combos)}] k={k:>2} gap={gap:>2} {formula_name:<16} "
              f"| ALL(8) final={row['avg_final_all']:.3f} r1={row['avg_r1_all']:.3f} "
              f"| HUMAN(2) final={row['avg_final_human']:.3f} r1={row['avg_r1_human']:.3f}")

    # Baseline = k=6, gap=30, sum — cấu hình hiện tại
    baseline = next(r for r in results
                     if r["candidates_per_event"] == 6 and r["min_gap"] == 30
                     and r["formula"] == "sum (baseline)")
    print(f"\n{'='*90}\nBASELINE (k=6, gap=30, sum): "
          f"ALL final={baseline['avg_final_all']:.3f} r1={baseline['avg_r1_all']:.3f} | "
          f"HUMAN final={baseline['avg_final_human']:.3f} r1={baseline['avg_r1_human']:.3f}")

    # Chọn tốt nhất: ưu tiên KHÔNG tệ hơn baseline trên tập HUMAN (rủi ro
    # overfit thấp nhất, n=2 nhưng là chuẩn vàng), rồi tối đa avg_final_all.
    candidates_ok = [r for r in results if r["avg_final_human"] >= baseline["avg_final_human"]]
    pool = candidates_ok if candidates_ok else results
    best = max(pool, key=lambda r: r["avg_final_all"])
    print(f"\nTỐT NHẤT (không tệ hơn baseline trên tập người viết): "
          f"k={best['candidates_per_event']} gap={best['min_gap']} formula={best['formula']}")
    print(f"  ALL final={best['avg_final_all']:.3f} r1={best['avg_r1_all']:.3f} | "
          f"HUMAN final={best['avg_final_human']:.3f} r1={best['avg_r1_human']:.3f}")

    out_path = ROOT_DIR / "dev_set/results/trake_sweep.json"
    out_path.write_text(json.dumps({"baseline": baseline, "best": best, "all_results": results},
                                    indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n📦 Đã ghi toàn bộ kết quả sweep: {out_path}")


if __name__ == "__main__":
    main()
