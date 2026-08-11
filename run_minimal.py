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


def _chia_slot(ket_qua: list[dict], fmap: dict[str, int]) -> list[tuple[str, int, str]]:
    """Kết quả search → list (video_id, frame_id, keyframe_id) đã lọc, giữ thứ hạng.

    Ba việc, đúng thứ tự:
      1. tra frame_map: keyframe_id → frame index TRONG VIDEO (bất biến #5 —
         nộp số thứ tự keyframe là 0 điểm dù đúng video);
      2. bỏ trùng (video_id, frame_id) — hai slot trùng nội dung tiêu hai cơ hội
         mà chỉ mua một;
      3. chặn trần mỗi video.
    """
    da_co: set[tuple[str, int]] = set()
    dem_video: dict[str, int] = defaultdict(int)
    ra: list[tuple[str, int, str]] = []

    for r in ket_qua:
        kf = r["keyframe_id"]
        video_id = r["video_id"]
        if kf not in fmap:
            continue  # keyframe lạ (index lệch phiên bản) — bỏ, đừng đoán frame
        frame_id = int(fmap[kf])
        if (video_id, frame_id) in da_co or dem_video[video_id] >= MAX_PER_VIDEO:
            continue
        # frame phải nằm trong video — validator sẽ bắt, nhưng bắt ở đây thì
        # còn slot để thay thế, bắt ở validator thì cả file bị từ chối
        try:
            if not 0 <= frame_id < n_frames_of(video_id):
                continue
        except KeyError:
            continue  # video_id không có trong kiểm kê
        da_co.add((video_id, frame_id))
        dem_video[video_id] += 1
        ra.append((video_id, frame_id, kf))

    return ra


def _don_cho_du(
    da_chon: list[tuple[str, int, str]], can: int
) -> list[tuple[str, int, str]]:
    """Độn cho đủ `can` slot. Câu sai không bị trừ điểm → bỏ trống là lỗ thuần.

    Độn bằng frame 0 của các video CHƯA xuất hiện: gần như chắc sai, nhưng lấp
    slot mà không tiêu mất cơ hội của ứng viên thật nào, và không tạo dòng trùng.
    """
    if len(da_chon) >= can:
        return da_chon[:can]

    da_dung = {v for v, _, _ in da_chon}
    ra = list(da_chon)
    for video_id in all_video_ids():
        if len(ra) >= can:
            break
        if video_id in da_dung:
            continue
        ra.append((video_id, 0, f"{video_id}#pad"))
    return ra[:can]


def _dung_answers(
    slot: list[tuple[str, int, str]], task_type: str, n_frames: int,
    answer_text: str | None = None,
) -> list[Answer]:
    """slot → Answer. TRAKE cần N frame tăng dần ngặt trên CÙNG một video."""
    if task_type != "TRAKE":
        # Q&A bắt buộc answer khác rỗng (export._check_shape): answer sai/rỗng
        # thì frame đúng cũng 0 điểm. Sinh answer là việc của C3.1 (Thi) — ở đây
        # chỉ lấy sẵn từ file truy vấn, không có thì độn chỗ để pipeline chạy hết
        # đường, KHÔNG phải để nộp thật.
        txt = (answer_text or "CHUA_CO_ANSWER") if task_type == "QA" else None
        return [
            Answer(video_id=v, frame_ids=(f,), answer_text=txt, keyframe_id=kf)
            for v, f, kf in slot
        ]

    # TRAKE tối giản: mỏ neo là frame tìm được, các mốc còn lại giãn đều về sau.
    # Đây là FALLBACK cố ý ngây thơ (C4.4), không phải lời giải — C4.1 mới làm DP.
    ra: list[Answer] = []
    for v, f, kf in slot:
        het = n_frames_of(v)
        buoc = max(1, min(60, (het - f) // max(1, n_frames)))
        moc = tuple(min(f + i * buoc, het - 1) for i in range(n_frames))
        if len(set(moc)) != n_frames:  # đụng cuối video, không tăng dần ngặt được
            moc = tuple(range(max(0, het - n_frames), het))
        ra.append(Answer(video_id=v, frame_ids=moc, keyframe_id=kf))
    return ra


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
        try:
            ket_qua = search(
                q["query_vi"], query_en=q.get("query_en"),
                top_k=args.answers * CANDIDATE_FACTOR,
            )
        except Exception as e:
            print(f"  {qid:<10} SEARCH HỎNG: {e}")
            hong += 1
            continue

        slot = _chia_slot(ket_qua, fmap)
        tho = len(slot)
        tong_that += tho
        if tho == 0:
            rong.append(qid)
        if not args.no_pad:
            slot = _don_cho_du(slot, args.answers)
        slot = slot[: args.answers]

        answers = _dung_answers(slot, task_type, int(q.get("n_frames", 4)),
                                answer_text=q.get("answer"))
        if task_type == "QA" and not q.get("answer"):
            print(f"  {'':<10} [cảnh báo] {qid} là Q&A nhưng chưa có answer — "
                  "file sinh ra CHỈ để thông ống, không nộp được.")
        subs.append(QuerySubmission(query_id=qid, task_type=task_type,
                                    answers=tuple(answers)))
        so_video = len({v for v, _, _ in slot})
        don = len(slot) - tho
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
            f"\n⚠️  {len(rong)}/{len(subs)} truy vấn KHÔNG có ứng viên thật nào "
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
