# run_minimal.py — A6.2-early: orchestrator TỐI GIẢN (gác cổng G2)
#
# ===== Vai trò =====
# Ghép ống một lần cho hết đường: file truy vấn → search → chia slot → export
# → file nộp hợp lệ. Chỉ CLIP + BM25 + slot. KHÔNG rerank, KHÔNG VLM, KHÔNG agent.
#
# Hai lý do nó tồn tại:
#   1. Chứng minh G2 (09/08): có file nộp sinh từ pipeline THẬT, không phải fixture.
#   2. Là KỊCH BẢN DỰ PHÒNG ngày nộp. Khi thứ gì đó tinh vi hơn hỏng lúc 2h sáng,
#      đây là đường chạy đủ đơn giản để tin tưởng.
# Vì thế: giữ nó ngắn và đọc hiểu được trong một lượt. Mọi cám dỗ thêm tính năng
# vào đây đều làm hỏng lý do #2.
#
# ===== Chia slot: vì sao luôn nộp ĐỦ 100 =====
# Sơ tuyển chấm R@k theo lô và KHÔNG trừ điểm câu sai (docs/contest.md). Nên slot
# thứ 100 dù chỉ đúng 1% vẫn là kỳ vọng dương — bỏ trống là vứt điểm. Script này
# LUÔN xuất đúng ANSWERS_PER_QUERY dòng, thiếu thì độn thêm.
#
# ===== Đa dạng video: vì sao chặn số slot mỗi video =====
# Search thô hay trả 60–70 keyframe cùng một video (các frame kề nhau trong cùng
# cảnh). Nếu video đó sai, mất sạch 70 slot cho một phán đoán duy nhất. Chặn
# MAX_PER_VIDEO là mua bảo hiểm: đổi vài slot lấy việc phủ được nhiều video hơn.
#
# ===== Chạy =====
#   docker compose up -d                    # Milvus + ES (Milvus cần ~90s)
#   python -m backend.indexing.load_clip    # và các loader khác
#   python run_minimal.py --queries data/queries/so_tuyen.json
#   python run_minimal.py --queries ... --out submissions/lan_1
#
# File truy vấn (JSON, một list):
#   [{"query_id": "q001", "task_type": "KIS",
#     "query_vi": "thủ môn cản phá penalty", "query_en": "goalkeeper saves penalty"},
#    {"query_id": "q002", "task_type": "TRAKE", "query_vi": "...", "n_frames": 4}]
#   query_en tuỳ chọn — thiếu thì gọi llm() dịch (cần ANTHROPIC_API_KEY).
#
# Exit code: 0 = ghi đủ file hợp lệ · 1 = có truy vấn hỏng · 2 = sai đầu vào.

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.export import (  # noqa: E402
    ANSWERS_PER_QUERY,
    QuerySubmission,
    all_video_ids,
    n_frames_of,
    write_submissions,
)
from backend.indexing.frame_map import load_frame_map  # noqa: E402
from data.config.submit_format import Answer  # noqa: E402

# Trần slot cho một video. 12 = đủ chỗ cho vài cảnh trong cùng video mà vẫn
# buộc kết quả phủ ≥ 9 video khác nhau. Con số này nên chỉnh theo số liệu eval
# của D4.1 tuần W3 — hiện là phán đoán có chủ đích, chưa phải kết luận đo được.
MAX_PER_VIDEO = 12

# Lấy dư ứng viên rồi mới lọc: sau khi bỏ trùng frame và chặn trần mỗi video,
# 100 ứng viên thô thường chỉ còn 40–60.
CANDIDATE_FACTOR = 6


def _doc_queries(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"Không thấy file truy vấn: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit(f"{path} phải chứa một LIST các truy vấn.")
    for i, q in enumerate(data):
        for khoa in ("query_id", "task_type", "query_vi"):
            if khoa not in q:
                raise SystemExit(f"truy vấn thứ {i + 1} thiếu khoá '{khoa}'")
    return data





from backend.slot.allocator import allocate

def main() -> int:
    ap = argparse.ArgumentParser(description="Orchestrator tối giản → file nộp (G2)")
    ap.add_argument("--queries", required=True, help="file JSON chứa list truy vấn")
    ap.add_argument("--out", default="submissions/minimal", help="thư mục ghi file nộp")
    ap.add_argument("--answers", type=int, default=ANSWERS_PER_QUERY)
    ap.add_argument("--no-pad", action="store_true",
                    help="KHÔNG độn cho đủ 100 (chỉ dùng khi soi chất lượng search)")
    args = ap.parse_args()

    from backend.retrieval.search import search  # import muộn: chưa có docker thì lỗi rõ ràng

    queries = _doc_queries(Path(args.queries))
    fmap = load_frame_map()
    print(f"frame_map: {len(fmap)} khoá · {len(queries)} truy vấn · đích {args.answers} slot/truy vấn\n")

    subs: list[QuerySubmission] = []
    hong = 0
    rong = []          # truy vấn KHÔNG có ứng viên thật nào — toàn dòng độn
    tong_that = 0

    for q in queries:
        qid, task_type = q["query_id"], q["task_type"]
        answer_text = q.get("answer")

        # TRAKE đi đường RIÊNG hoàn toàn — KHÔNG qua allocate()/ShotHit như
        # KIS/QA. Từ 16/08, trake_search() đã tự định vị đúng N frame_ids mỗi
        # video ứng viên bằng DP (backend/tasks/trake.py); đẩy nó qua allocate()
        # sẽ làm mất hết bằng chứng đó — allocator chỉ biết carve đều 1 shot đại
        # diện thành N đoạn giả (đúng bug đã sửa, xem đầu backend/tasks/trake.py).
        if task_type == "TRAKE":
            try:
                from backend.tasks.trake import pad_answers, parse_events, to_answers, trake_search
                events = parse_events(q["query_vi"])
                candidates = trake_search(events, top_videos=args.answers)
                if not candidates:
                    raise RuntimeError("trake_search() không tìm được video ứng viên nào")
                # Truyền `args.answers` tường minh: từ 21/08 `to_answers()` sinh
                # thêm dòng PHƯƠNG ÁN THAY THẾ cho tới đủ `total` (mặc định 100),
                # nên không truyền thì `--answers 50` sẽ ra 100 dòng và validator
                # từ chối cả file. Lúc thi luôn là 100 nên mặc định vẫn đúng.
                answers = to_answers(candidates, args.answers)
                if len(answers) < args.answers:
                    answers = pad_answers(candidates, args.answers)
            except Exception as e:
                print(f"  {qid:<10} PIPELINE HỎNG: {e}")
                hong += 1
                rong.append(qid)
                continue
        else:
            ket_qua = []
            try:
                from backend.slot.allocator import ShotHit
                if task_type == "QA":
                    from backend.tasks.qa import qa_pipeline
                    ket_qua, ans_txt = qa_pipeline(q["query_vi"], top_k_shots=args.answers * CANDIDATE_FACTOR, query_en=q.get("query_en"))
                    if ans_txt: answer_text = ans_txt
                else:
                    ket_qua = search(
                        q["query_vi"], query_en=q.get("query_en"),
                        top_k=args.answers * CANDIDATE_FACTOR,
                    )

                hits = [
                    h if isinstance(h, ShotHit) 
                    else ShotHit(
                        shot_id=h.get("shot_id") or "unknown", 
                        score=h.get("score", 0.0), 
                        best_keyframe_id=h.get("keyframe_id")
                    ) 
                    for h in ket_qua
                ]
            except Exception as e:
                import os, traceback
                print(f"  {qid:<10} PIPELINE HỎNG: {e}")
                if os.getenv("DEBUG") == "1":
                    traceback.print_exc()
                hong += 1
                rong.append(qid)
                continue

            try:
                answers = allocate(hits, task_type, answer_text=answer_text, total=args.answers)
            except Exception as e:
                print(f"  {qid:<10} ALLOCATE HỎNG: {e}")
                hong += 1
                rong.append(qid)
                continue
        
        # "Thật" = có keyframe_id (bằng chứng thật: best_keyframe của shot ở
        # KIS/QA, hoặc vị trí không bị nội suy/dịch-đệm ở TRAKE) — "#pad" không
        # còn (và chưa từng) là marker được gán ở đâu, so với chuỗi rỗng luôn
        # đúng "chứa" nên đếm SAI mọi dòng là "thật"; None còn làm TypeError.
        tho = len([a for a in answers if a.keyframe_id is not None])
        tong_that += tho
        if tho == 0:
            rong.append(qid)

        if args.no_pad:
            answers = [a for a in answers if a.keyframe_id is not None]
        if task_type == "QA" and not q.get("answer"):
            print(f"  {'':<10} [cảnh báo] {qid} là Q&A nhưng chưa có answer — "
                  "file sinh ra CHỈ để thông ống, không nộp được.")
        subs.append(QuerySubmission(query_id=qid, task_type=task_type,
                                    answers=tuple(answers)))
        so_video = len({a.video_id for a in answers})
        don = len(answers) - tho
        print(f"  {qid:<10} {task_type:<6} {tho:>3} thật"
              + (f" + {don} độn" if don > 0 else "")
              + f" · {so_video} video khác nhau")

    if not subs:
        print("\nKhông dựng được bài nộp nào.", file=sys.stderr)
        return 1

    # --no-pad sinh ra số dòng không đủ 100 → validator ngữ nghĩa chắc chắn từ
    # chối (đúng như thiết kế). Chế độ đó chỉ để SOI chất lượng search, nên tắt
    # validate và nói rõ file không nộp được — thay vì nới lỏng luật của validator.
    try:
        if args.no_pad:
            print("\n[--no-pad] BỎ QUA validator — file sinh ra KHÔNG nộp được.")
            da_ghi, loi_file = write_submissions(subs, args.out, validate=False)
            loi_file = []
        else:
            da_ghi, loi_file = write_submissions(subs, args.out,
                                                 expect_answers=args.answers)
    except ValueError as e:
        print(f"\nVALIDATOR TỪ CHỐI — không ghi file nào:\n{e}", file=sys.stderr)
        return 1

    print(f"\nĐã ghi {len(da_ghi)} file vào {args.out}/")
    if loi_file:
        print("Lỗi khi đọc lại file đã ghi:", file=sys.stderr)
        for i in loi_file[:10]:
            print(f"  {i}", file=sys.stderr)
        return 1

    # ⚠️ File HỢP LỆ chưa chắc CÓ NGHĨA: nếu mọi nhánh search chết (quên bật
    # docker, index chưa nạp) thì phần độn vẫn lấp đủ 100 dòng và validator vẫn
    # cho qua — trông y hệt một lần chạy thành công. Đó là báo xanh giả nguy
    # hiểm nhất của script này, nên phải nói to và trả exit code khác 0.
    print(f"Tổng ứng viên THẬT: {tong_that} · độn: {len(subs) * args.answers - tong_that}")
    if rong:
        print(
            f"\n⚠️  {len(rong)}/{len(queries)} truy vấn KHÔNG có ứng viên thật nào "
            f"({', '.join(rong[:5])}{'...' if len(rong) > 5 else ''}) — file chỉ toàn dòng độn.\n"
            "    Nguyên nhân hay gặp: chưa `docker compose up -d`, chưa nạp index, "
            "hoặc keyframe_id trong index không có trong frame_map.\n"
            "    KHÔNG nộp file này.",
            file=sys.stderr,
        )
        return 1

    print("Tất cả file qua validator. G2: có file nộp hợp lệ từ pipeline thật.")
    return 1 if hong else 0


if __name__ == "__main__":
    raise SystemExit(main())
