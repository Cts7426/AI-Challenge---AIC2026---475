# dev_set/tools/eval_kis_only.py — đo KIS RIÊNG, KHÔNG TỐN 1 ĐỒNG LLM NÀO.
#
# Vì sao cần script riêng thay vì dùng lại run_evaluation.py:
#   run_evaluation.py --split X đọc CẢ BA file {X}_kis/{X}_qa/{X}_trake.jsonl
#   trong một lượt. QA luôn gọi llm() (qa_pipeline), TRAKE gọi llm() khi
#   event_descs không có sẵn (parse_events) — 20/08 tài khoản Anthropic ĐÃ HẾT
#   TIỀN giữa buổi, nên bất kỳ đường chạy nào chạm llm() đều crash. KIS không
#   cần llm() MỘT CHÚT NÀO khi query_en đã có sẵn trong file (search() chỉ tự
#   dịch qua llm() lúc query_en=None) — script này CHỈ đi qua search()+
#   allocate()+scoring, y hệt nhánh KIS thật của run_evaluation.py (dòng
#   ~277-280), để đo được ngay cả khi llm() chết hoàn toàn.
#
# KHÔNG tính vào hạn mức 5 lần holdout (dev_set/holdout_log.md) — đây là công
# cụ CHẨN ĐOÁN trên tập `tune` để lặp lại thoải mái không sợ overfit holdout.
# Muốn đo `--split holdout` vẫn PHẢI qua run_evaluation.py để hạn mức ghi
# nhận đúng — script này CHẶN thẳng split "holdout" để không ai lỡ tay né hạn
# mức bằng đường tắt.
#
# Chạy: python -m dev_set.tools.eval_kis_only --split tune

from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.indexing.es_client import connect as es_connect
from backend.indexing.frame_map import load_frame_map
from backend.indexing.milvus_client import connect as milvus_connect
from backend.retrieval.search import search
from backend.slot.allocator import ShotHit, allocate

from dev_set.tools.run_evaluation import _to_shot_hits, load_jsonl
from dev_set.tools.schema import GroundTruthKIS, Query
from dev_set.tools.scoring import final_score, recall_at_k, rscore_kis

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_zero_llm_queries(q_path: Path, fallback_path: Path) -> list[Query]:
    """Nạp KIS và bảo đảm `query_en` cố định trước khi chạm DB/search.

    `tune_kis.jsonl` là nguồn query chính. Khi một dòng thiếu bản dịch, chỉ điền
    theo đúng `query_id` từ `tune_all.json`; không tự dịch và không đoán từ câu VI.
    Trả list Query có `query_en` không rỗng, hoặc fail closed.
    """
    primary_rows = [row for row in load_jsonl(q_path) if row.get("task_type") == "KIS"]

    fallback_rows = []
    if fallback_path.is_file():
        try:
            raw = json.loads(fallback_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            raise RuntimeError(f"không đọc được fallback query_en {fallback_path}: {e}") from e
        if not isinstance(raw, list):
            raise RuntimeError(f"{fallback_path} phải là JSON array")
        fallback_rows = [row for row in raw if isinstance(row, dict) and row.get("task_type") == "KIS"]

    fallback_by_id: dict[str, str] = {}
    for row in fallback_rows:
        query_id = str(row.get("query_id", "")).strip()
        query_en = str(row.get("query_en") or "").strip()
        if not query_id or not query_en:
            continue
        previous = fallback_by_id.get(query_id)
        if previous is not None and previous != query_en:
            raise RuntimeError(f"tune_all.json có hai query_en mâu thuẫn cho {query_id}")
        fallback_by_id[query_id] = query_en

    queries: list[Query] = []
    for row in primary_rows:
        merged = dict(row)
        query_en = str(merged.get("query_en") or "").strip()
        if not query_en:
            query_en = fallback_by_id.get(str(merged.get("query_id", "")), "")
        merged["query_en"] = query_en or None
        queries.append(Query(**merged))

    missing_en = [q.query_id for q in queries if not (q.query_en or "").strip()]
    if missing_en:
        raise RuntimeError(
            "không thể chạy KIS 0-LLM: thiếu query_en trong tune_kis.jsonl và "
            f"tune_all.json cho {missing_en}"
        )
    return queries


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--split", choices=["tune"], default="tune",
                     help="CHỈ nhận 'tune' — đo 'holdout' phải qua run_evaluation.py để giữ đúng hạn mức 5 lần")
    args = ap.parse_args()

    q_path = REPO_ROOT / "dev_set" / "queries" / f"{args.split}_kis.jsonl"
    fallback_path = REPO_ROOT / "dev_set" / "queries" / "tune_all.json"
    gt_path = REPO_ROOT / "dev_set" / "ground_truth" / f"{args.split}_gt.jsonl"

    try:
        queries = load_zero_llm_queries(q_path, fallback_path)
    except RuntimeError as e:
        ap.error(str(e))

    gts = {}
    for row in load_jsonl(gt_path):
        if row.get("query_id") in {q.query_id for q in queries}:
            gts[row["query_id"]] = GroundTruthKIS(**{k: v for k, v in row.items() if k != "task_type"})

    print("Kết nối database...")
    es_connect()
    milvus_connect()
    fmap = load_frame_map()

    rows = []
    for q in queries:
        gt = gts.get(q.query_id)
        if gt is None:
            print(f"[BỎ QUA] {q.query_id} không có Ground Truth.")
            continue

        # load_zero_llm_queries() đã chặn None/rỗng: search không thể rơi vào
        # nhánh translate_to_english() gọi llm().
        res = search(q.query_vi, query_en=q.query_en, top_k=100, group_by_shot=True)
        hits = _to_shot_hits(res)
        ans = allocate(hits, "KIS", answer_text=None)

        r1 = recall_at_k(ans, gt, "KIS", 1)
        r5 = recall_at_k(ans, gt, "KIS", 5)
        r20 = recall_at_k(ans, gt, "KIS", 20)
        r50 = recall_at_k(ans, gt, "KIS", 50)
        r100 = recall_at_k(ans, gt, "KIS", 100)
        fin = final_score(ans, gt, "KIS")

        # Hạng THẬT của câu đúng trong kết quả search() thô (trước allocate()),
        # để phân biệt "retrieval tìm được nhưng allocate() xếp lệch" với
        # "retrieval không tìm được luôn" — hai nguyên nhân cần fix khác hẳn nhau.
        raw_rank = None
        for i, row in enumerate(res, 1):
            kf = row.get("keyframe_id")
            if kf not in fmap:
                continue
            if rscore_kis(row["video_id"], fmap[kf], gt) > 0:
                raw_rank = i
                break

        rows.append({
            "query_id": q.query_id, "query_vi": q.query_vi,
            "r1": r1, "r5": r5, "r20": r20, "r50": r50, "r100": r100, "final": fin,
            "raw_rank": raw_rank,
        })

    n = len(rows)
    print(f"\n=== KIS — {args.split} — {n} câu (0 lượt gọi llm()) ===\n")
    for r in rows:
        tick = "✅" if r["r1"] >= 1.0 else ("🟡" if r["r100"] >= 1.0 else "❌")
        print(f"  {tick} {r['query_id']:8s} R@1={r['r1']:.2f} R@5={r['r5']:.2f} "
              f"R@20={r['r20']:.2f} R@50={r['r50']:.2f} R@100={r['r100']:.2f} "
              f"Final={r['final']:.3f} hạng_thô={r['raw_rank']}  — {r['query_vi'][:60]}")

    if n:
        avg = lambda k: sum(r[k] for r in rows) / n
        n_r1 = sum(1 for r in rows if r["r1"] >= 1.0)
        n_r100 = sum(1 for r in rows if r["r100"] >= 1.0)
        print(f"\nTrung bình: R@1={avg('r1'):.3f} R@5={avg('r5'):.3f} R@20={avg('r20'):.3f} "
              f"R@50={avg('r50'):.3f} R@100={avg('r100'):.3f} Final={avg('final'):.3f}")
        print(f"Đúng NGAY HẠNG 1: {n_r1}/{n} ({100*n_r1/n:.0f}%)")
        print(f"Lọt top-100 (ít nhất còn cơ hội): {n_r100}/{n} ({100*n_r100/n:.0f}%)")

    out_path = REPO_ROOT / "dev_set" / "results" / f"kis_only_{args.split}.json"
    out_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nGhi chi tiết: {out_path}")


if __name__ == "__main__":
    main()
