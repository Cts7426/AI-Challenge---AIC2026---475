# dev_set/tools/build_holdout_from_teammate.py — chuyển queries001.txt +
# queries002_frame.txt (bộ đề đồng đội cung cấp, 20/08, tối trước Đợt 1) →
# dev_set/queries/holdout_*.jsonl + dev_set/ground_truth/holdout_gt.jsonl.
#
# ⚠️ GT trong queries002_frame.txt gắn nhãn "confidence": "auto_bm25" — TỰ
# ĐỘNG sinh bằng BM25, KHÔNG phải người xác nhận tay như TR01/TR02. Dùng để
# kiểm tra toàn diện (nhiều video/câu hỏi thật hơn dev-set hiện có) chứ
# KHÔNG coi là chuẩn vàng tuyệt đối — nếu 1 câu chấm sai, có thể do GT tự
# động sai, không hẳn do pipeline sai (cần soi kỹ trước khi kết luận).
#
# ⚠️ TRAKE trong file GT chỉ có 1 cửa sổ frame_start/frame_end (không phải N
# cửa sổ khớp N sự kiện như schema thật yêu cầu — GroundTruthTRAKE.frames).
# KHÔNG ép vào rscore_trake (sẽ luôn cho 0 vì len(frames) != N nộp) — TRAKE
# ghi riêng 1 file thô (holdout_trake_single_window.jsonl) để đánh giá ĐỊNH
# TÍNH (đúng video + frame có nằm gần đoạn tham chiếu không), KHÔNG đưa vào
# holdout_trake.jsonl/holdout_gt.jsonl chính thức.
#
# Chạy:
#   python -m dev_set.tools.build_holdout_from_teammate

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
SRC_QUERIES = ROOT_DIR / "queries001.txt"
SRC_FRAMES = ROOT_DIR / "queries002_frame.txt"

OUT_KIS = ROOT_DIR / "dev_set/queries/holdout_kis.jsonl"
OUT_QA = ROOT_DIR / "dev_set/queries/holdout_qa.jsonl"
OUT_TRAKE = ROOT_DIR / "dev_set/queries/holdout_trake.jsonl"
OUT_GT = ROOT_DIR / "dev_set/ground_truth/holdout_gt.jsonl"
OUT_TRAKE_SINGLE = ROOT_DIR / "dev_set/queries/holdout_trake_single_window.jsonl"

_ANSWER_RE = re.compile(r"\(([^()]+)\)\s*$")


def _extract_answer(query_vi: str) -> tuple[str, str]:
    """query_vi có đáp án trong ngoặc cuối câu → (câu hỏi không ngoặc, đáp án)."""
    m = _ANSWER_RE.search(query_vi)
    if not m:
        raise ValueError(f"Không tìm thấy đáp án trong ngoặc: {query_vi!r}")
    answer = m.group(1).strip()
    question = query_vi[:m.start()].strip()
    return question, answer


def main() -> None:
    frames_by_id = {}
    with open(SRC_FRAMES, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            frames_by_id[d["query_id"]] = d

    kis_rows, qa_rows, trake_rows, trake_single_rows, gt_rows = [], [], [], [], []
    skipped = []

    with open(SRC_QUERIES, encoding="utf-8") as f:
        for line in f:
            q = json.loads(line)
            qid, qtype = q["query_id"], q["type"]
            fr = frames_by_id.get(qid)
            if fr is None or fr.get("frame_start") is None or fr.get("confidence") == "no_data":
                # "no_data" — công cụ tự động (auto_bm25) KHÔNG tìm được frame
                # nào cho câu này (video có thể chưa index/không đủ dữ liệu) —
                # không có gì để chấm, bỏ qua, KHÔNG đoán bừa frame_start/end.
                skipped.append(qid)
                continue

            if qtype == "KIS":
                kis_rows.append({
                    "query_id": qid, "task_type": "KIS", "query_vi": q["query_vi"],
                    "query_en": q.get("query_en"), "split": "holdout",
                })
                gt_rows.append({
                    "query_id": qid, "task_type": "KIS", "video_id": q["video_id"],
                    "frame_start": fr["frame_start"], "frame_end": fr["frame_end"],
                })
            elif qtype == "QA":
                try:
                    question_only, answer = _extract_answer(q["query_vi"])
                except ValueError:
                    skipped.append(qid)
                    continue
                qa_rows.append({
                    "query_id": qid, "task_type": "QA", "query_vi": q["query_vi"],
                    "query_en": q.get("query_en"), "split": "holdout",
                })
                gt_rows.append({
                    "query_id": qid, "task_type": "QA", "video_id": q["video_id"],
                    "frame_start": fr["frame_start"], "frame_end": fr["frame_end"],
                    "answer_text": answer,
                    # >=3 answer_variants bắt buộc theo schema — dùng lặp lại
                    # đáp án gốc (answer_matches() so khớp ngữ nghĩa qua
                    # majority_answer, không cần biến thể văn bản thủ công).
                    "answer_variants": [answer, answer, answer],
                })
            elif qtype == "TRAKE":
                # ⚠️ Đo thật: 28/30 câu dùng " . " (khoảng trắng 2 bên), 2 câu
                # (TRAKE_029/030) dùng ". " (không khoảng trắng trước dấu
                # chấm) — split cứng " . " bỏ sót 2 câu này. Dùng regex chấp
                # nhận cả hai, giống _HEURISTIC_DELIMITERS[0] trong trake.py.
                event_descs = [e.strip() for e in re.split(r"\s*\.\s+", q["query_vi"]) if e.strip()]
                n_events = len(event_descs)
                trake_rows.append({
                    "query_id": qid, "task_type": "TRAKE", "query_vi": q["query_vi"],
                    "split": "holdout", "n_events": n_events, "event_descs": event_descs,
                })
                trake_single_rows.append({
                    "query_id": qid, "video_id": q["video_id"], "n_events": n_events,
                    "frame_start": fr["frame_start"], "frame_end": fr["frame_end"],
                    "best_frame_idx": fr.get("best_frame_idx"),  # 1 dòng thiếu field này (TRAKE_028)
                })

    for path, rows in [(OUT_KIS, kis_rows), (OUT_QA, qa_rows), (OUT_TRAKE, trake_rows)]:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    OUT_GT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_GT, "w", encoding="utf-8") as f:
        for r in gt_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    with open(OUT_TRAKE_SINGLE, "w", encoding="utf-8") as f:
        for r in trake_single_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"KIS: {len(kis_rows)} · QA: {len(qa_rows)} · TRAKE: {len(trake_rows)}")
    if skipped:
        print(f"⚠️ Bỏ qua {len(skipped)} câu (không khớp GT/không trích được đáp án): {skipped}")
    print(f"Đã ghi: {OUT_KIS}, {OUT_QA}, {OUT_TRAKE}, {OUT_GT}, {OUT_TRAKE_SINGLE}")


if __name__ == "__main__":
    main()
