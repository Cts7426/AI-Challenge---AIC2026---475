# dev_set/tools/eval_trake_qualitative.py — đánh giá ĐỊNH TÍNH 29 câu TRAKE
# từ bộ đề đồng đội (holdout_trake_single_window.jsonl) — GT chỉ có 1 cửa sổ
# frame_start/frame_end (không phải N cửa sổ khớp N sự kiện thật), nên KHÔNG
# tính rscore_trake chuẩn được (sẽ luôn ra 0 vì lệch số lượng frame). Đánh
# giá 2 tiêu chí quan trọng nhất theo docs/contest.md:
#   1. VIDEO đúng có lọt top-100/top-10 không, hạng bao nhiêu (sai video = 0
#      tuyệt đối — tiêu chí quan trọng NHẤT).
#   2. Với video đúng: có frame nào trong chuỗi N frame đã chọn nằm GẦN cửa
#      sổ tham chiếu (frame_start-500 .. frame_end+500, nới rộng vì cửa sổ
#      tham chiếu chỉ đại diện 1 điểm trong cả chuỗi N sự kiện) không.
#
# Chạy (cần Docker ES+Milvus sống + ANTHROPIC_API_KEY):
#   python -m dev_set.tools.eval_trake_qualitative

from __future__ import annotations

import json
import statistics
from pathlib import Path

from backend.tasks.trake import trake_search

ROOT_DIR = Path(__file__).resolve().parents[2]
TOLERANCE_FRAMES = 500  # nới rộng — cửa sổ tham chiếu chỉ là 1 điểm trong N sự kiện


def main() -> None:
    queries = {}
    with open(ROOT_DIR / "dev_set/queries/holdout_trake.jsonl", encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            queries[d["query_id"]] = d

    refs = {}
    with open(ROOT_DIR / "dev_set/queries/holdout_trake_single_window.jsonl", encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            refs[d["query_id"]] = d

    results = []
    for qid, q in queries.items():
        ref = refs.get(qid)
        if ref is None:
            continue
        try:
            candidates = trake_search(q["event_descs"], top_videos=100)
        except Exception as e:
            results.append({"query_id": qid, "error": str(e)})
            print(f"  ✗ {qid}: LỖI — {e}")
            continue

        video_rank = None
        near_ref = False
        chosen_frames = None
        for i, c in enumerate(candidates, 1):
            if c.video_id == ref["video_id"]:
                video_rank = i
                chosen_frames = c.frame_ids
                lo, hi = ref["frame_start"] - TOLERANCE_FRAMES, ref["frame_end"] + TOLERANCE_FRAMES
                near_ref = any(lo <= f <= hi for f in c.frame_ids)
                break

        row = {
            "query_id": qid, "video_id": ref["video_id"], "video_rank": video_rank,
            "near_ref_window": near_ref, "chosen_frames": chosen_frames,
        }
        results.append(row)
        flag = "✓" if video_rank is not None and video_rank <= 10 else ("~" if video_rank else "✗")
        print(f"  {flag} {qid}: hạng={video_rank} gần_tham_chiếu={near_ref} frames={chosen_frames}")

    ranks = [r["video_rank"] for r in results if r.get("video_rank") is not None]
    n_total = len(results)
    n_found = len(ranks)
    n_top10 = sum(1 for r in ranks if r <= 10)
    n_top1 = sum(1 for r in ranks if r == 1)
    n_near = sum(1 for r in results if r.get("near_ref_window"))

    print(f"\n{'='*70}")
    print(f"Tổng {n_total} câu TRAKE:")
    print(f"  Video ĐÚNG lọt top-100: {n_found}/{n_total} ({n_found/n_total*100:.0f}%)")
    print(f"  Video ĐÚNG lọt top-10:  {n_top10}/{n_total} ({n_top10/n_total*100:.0f}%)")
    print(f"  Video ĐÚNG hạng 1:      {n_top1}/{n_total} ({n_top1/n_total*100:.0f}%)")
    print(f"  Frame gần đúng cửa sổ tham chiếu (trong số tìm thấy video): {n_near}/{n_found}")
    if ranks:
        print(f"  Hạng trung bình (khi tìm thấy): {statistics.mean(ranks):.1f}")

    out_path = ROOT_DIR / "dev_set/results/holdout_trake_qualitative.json"
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n📦 Đã ghi: {out_path}")


if __name__ == "__main__":
    main()
