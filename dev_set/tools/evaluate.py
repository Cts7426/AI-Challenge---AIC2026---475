import json
import argparse
from pathlib import Path
from collections import defaultdict
from dev_set.tools.stats import noise_threshold, paired_bootstrap

def load_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def print_qa_exact_summary(per_query: list[dict]) -> None:
    """In bảng Q&A theo luật chuỗi tuyệt đối khi run đã lưu metric song song.

    Input: `scores.json` per_query. Output: stdout. Invariant: run cũ không có
    trường mới thì im lặng, không làm hỏng báo cáo semantic đang dùng.
    """
    exact_rows = [
        q["score_by_qa_policy"]["exact"]
        for q in per_query
        if q.get("task_type") == "QA"
        and "exact" in q.get("score_by_qa_policy", {})
    ]
    if not exact_rows:
        return

    count = len(exact_rows)
    print("\n=== Q&A — GIẢ THUYẾT SO CHUỖI CHÍNH XÁC ===")
    print(f"N={count:<4} | "
          f"R@1={sum(q['r_at_1'] for q in exact_rows) / count:.4f} | "
          f"R@5={sum(q['r_at_5'] for q in exact_rows) / count:.4f} | "
          f"R@20={sum(q['r_at_20'] for q in exact_rows) / count:.4f} | "
          f"R@50={sum(q['r_at_50'] for q in exact_rows) / count:.4f} | "
          f"R@100={sum(q['r_at_100'] for q in exact_rows) / count:.4f} | "
          f"FINAL={sum(q['final'] for q in exact_rows) / count:.4f}")


def run_evaluate():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, help="Thư mục chứa kết quả của một run (vd: dev_set/results/run_20260818_2000)")
    parser.add_argument("--compare-dir", help="Run khác để so sánh CHUẨN theo cặp (vd: trước/sau một thay đổi)")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    scores_file = run_dir / "scores.json"
    if not scores_file.exists():
        print(f"LỖI: Không tìm thấy file {scores_file}")
        return

    scores_data = load_json(scores_file)
    per_query = scores_data.get("per_query", [])
    
    n_queries = len(per_query)
    
    # --- 1. NGƯỠNG NHIỄU (DÒNG ĐẦU TIÊN) ---
    se, margin = noise_threshold(n_queries, 0.5)
    print(f"n={n_queries} · sai số chuẩn {se:.3f} · chênh dưới {margin:.3f} là nhiễu, không kết luận")
    print("(Ước lượng nhanh, giả định 2 mẫu ĐỘC LẬP — dùng --compare-dir để so sánh CHUẨN theo cặp)\n")
    
    # --- 2. BẢNG CHÍNH ---
    # Aggregate by task type
    agg = defaultdict(lambda: {"count": 0, "r1": 0.0, "r5": 0.0, "r20": 0.0, "r50": 0.0, "r100": 0.0, "fin": 0.0})
    for q in per_query:
        tt = q["task_type"]
        agg[tt]["count"] += 1
        agg[tt]["r1"] += q["r_at_1"]
        agg[tt]["r5"] += q["r_at_5"]
        agg[tt]["r20"] += q["r_at_20"]
        agg[tt]["r50"] += q["r_at_50"]
        agg[tt]["r100"] += q["r_at_100"]
        agg[tt]["fin"] += q["final"]
        
        # Add to total
        agg["TOTAL"]["count"] += 1
        agg["TOTAL"]["r1"] += q["r_at_1"]
        agg["TOTAL"]["r5"] += q["r_at_5"]
        agg["TOTAL"]["r20"] += q["r_at_20"]
        agg["TOTAL"]["r50"] += q["r_at_50"]
        agg["TOTAL"]["r100"] += q["r_at_100"]
        agg["TOTAL"]["fin"] += q["final"]
        
    print("=== BẢNG CHÍNH ===")
    print(f"{'Loại':<10} | {'N':<4} | {'R@1':<6} | {'R@5':<6} | {'R@20':<6} | {'R@50':<6} | {'R@100':<6} | {'FINAL':<6}")
    print("-" * 70)
    for k in ["KIS", "QA", "TRAKE", "TOTAL"]:
        if k in agg and agg[k]["count"] > 0:
            c = agg[k]["count"]
            print(f"{k:<10} | {c:<4} | {agg[k]['r1']/c:.4f} | {agg[k]['r5']/c:.4f} | {agg[k]['r20']/c:.4f} | {agg[k]['r50']/c:.4f} | {agg[k]['r100']/c:.4f} | {agg[k]['fin']/c:.4f}")

    print_qa_exact_summary(per_query)

    # --- 3. BẢNG PHÂN LOẠI THẤT BẠI & RANKS TỪNG NHÁNH ---
    print("\n=== CÁC CÂU THẤT BẠI (R@100 = 0) ===")
    failed = [q for q in per_query if q["r_at_100"] == 0]
    if not failed:
        print("Tuyệt vời! Không có câu nào trượt R@100.")
    else:
        for q in failed:
            fc = q.get("failure_class", "UNKNOWN")
            ranks = q.get("ranks", {})
            ranks_str = ", ".join(f"{k}: {v}" for k, v in ranks.items()) if ranks else "Không tìm thấy trong top K (100x)"
            print(f"[{q['task_type']}] {q['query_id']} - Lớp lỗi: {fc}")
            print(f"   Thứ hạng đúng ở các nhánh search: {ranks_str}")

    # --- 4. SO SÁNH VỚI RUN KHÁC (paired bootstrap — #6) ---
    if args.compare_dir:
        other_file = Path(args.compare_dir) / "scores.json"
        if not other_file.exists():
            print(f"\nLỖI: Không tìm thấy {other_file}")
            return
        other_per_query = load_json(other_file).get("per_query", [])
        other_by_id = {q["query_id"]: q["final"] for q in other_per_query}
        by_id = {q["query_id"]: q["final"] for q in per_query}

        paired_ids = [qid for qid in by_id if qid in other_by_id]
        if len(paired_ids) < 2:
            print(f"\nCẢNH BÁO: chỉ {len(paired_ids)} query_id trùng giữa 2 run — không đủ để so sánh.")
        else:
            a = [by_id[qid] for qid in paired_ids]
            b = [other_by_id[qid] for qid in paired_ids]
            diff, lo, hi, p, se_b = paired_bootstrap(a, b)
            print(f"\n=== SO SÁNH VỚI {args.compare_dir} ({len(paired_ids)} query chung) ===")
            print(f"Δfinal (run_dir - compare_dir) = {diff:+.4f}  CI95% [{lo:+.4f}, {hi:+.4f}]  p={p:.4f}")
            if lo <= 0 <= hi:
                print("=> KHOẢNG TIN CẬY CHỨA 0: chênh lệch KHÔNG có ý nghĩa thống kê.")
            else:
                print("=> Chênh lệch có ý nghĩa thống kê ở mức 95%.")

if __name__ == "__main__":
    run_evaluate()
