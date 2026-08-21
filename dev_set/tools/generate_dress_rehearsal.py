# dev_set/tools/generate_dress_rehearsal.py — sinh bộ đề 25 câu (mô phỏng 1 buổi
# thi thật: ~19 KIS, 5 QA, 1 TRAKE) để chạy thử TOÀN BỘ hệ thống hiện tại và đo
# điểm thật — theo yêu cầu trực tiếp của Công Lý đêm 20/08.
#
# ⚠️ CAVEAT bắt buộc đọc trước khi tin số đo: câu KIS/TRAKE ở đây do VLM tự mô tả
# ĐÚNG khung hình đã chọn — dễ hơn câu thi thật do người viết (người viết có thể
# mô tả mơ hồ, dùng từ đồng nghĩa, bỏ sót chi tiết mà CLIP cần). Số đo ra là CẬN
# TRÊN lạc quan, không phải dự đoán điểm thi thật. Câu QA dùng đúng bằng chứng
# ASR thật (không bịa) nên đáng tin hơn phần KIS/TRAKE.
#
# Chọn shot TRẢI ĐỀU nhiều batch (L21-L30), tránh dồn vào L26 (498/873 video của
# corpus) như bộ synthetic TRAKE trước — để không lặp lại đúng một phong cách.
#
# Chạy: python -m dev_set.tools.generate_dress_rehearsal

from __future__ import annotations

import json
import random
from pathlib import Path

import pandas as pd

from backend.llm.adapter import llm

REPO_ROOT = Path(__file__).resolve().parents[2]
DERIVED = REPO_ROOT / "data" / "derived"
OUT_Q_DIR = REPO_ROOT / "dev_set" / "queries"
OUT_GT_DIR = REPO_ROOT / "dev_set" / "ground_truth"

SPLIT = "dress25"
N_KIS = 19
N_QA = 5
N_TRAKE_EVENTS = 3
SEED = 20260821

KIS_SCHEMA = {
    "type": "object",
    "properties": {"query_vi": {"type": "string"}, "query_en": {"type": "string"}},
    "required": ["query_vi", "query_en"],
    "additionalProperties": False,
}
QA_SCHEMA = {
    "type": "object",
    "properties": {
        "question_vi": {"type": "string"},
        "answer_vi": {"type": "string"},
        "answer_variants": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["question_vi", "answer_vi", "answer_variants"],
    "additionalProperties": False,
}
EVENT_SCHEMA = {
    "type": "object",
    "properties": {"caption_vi": {"type": "string"}},
    "required": ["caption_vi"],
    "additionalProperties": False,
}


def _image_path_near(kf: pd.DataFrame, video_id: str, frame_idx: int) -> tuple[str, int] | None:
    sub = kf[kf["video_id"] == video_id]
    if sub.empty:
        return None
    row = sub.iloc[(sub["frame_idx"] - frame_idx).abs().argsort().iloc[0]]
    return str(DERIVED / row["path"]), int(row["frame_idx"])


def _kis_query(img_path: str) -> tuple[str, str]:
    raw = llm(
        "Đây là một khung hình từ video tin tức/đời sống Việt Nam. Viết một câu MÔ TẢ "
        "ngắn gọn, cụ thể, đúng những gì THẤY ĐƯỢC trong khung hình (không suy đoán "
        "ngữ cảnh ngoài khung hình) — văn phong giống câu truy vấn tìm khoảnh khắc "
        "video, ví dụ: 'Cảnh hiện trường vụ tai nạn giao thông giữa xe máy và xe ba "
        "gác trên đường, có người bị ngã xuống đường.' Kèm bản dịch tiếng Anh ngắn.",
        images=[img_path], json_schema=KIS_SCHEMA, max_tokens=384,
    )
    d = json.loads(raw)
    return d["query_vi"].strip(), d["query_en"].strip()


def _qa_pair(img_path: str, asr_text: str) -> tuple[str, str, str, list[str]]:
    """Trả (event_vi mô tả cảnh, question_vi, answer_vi, answer_variants) — answer
    LẤY THẲNG từ asr_text, KHÔNG bịa thêm chi tiết ngoài bằng chứng (bất biến
    CLAUDE.md #6). answer_variants >= 3 cách diễn đạt cùng đáp án (GroundTruthQA
    yêu cầu — xem dev_set/tools/schema.py) để answer_matches() so khớp linh hoạt."""
    raw = llm(
        "Đây là 1 khung hình + đoạn lời thoại (ASR) TẠI ĐÚNG khoảnh khắc đó của một "
        "video tin tức Việt Nam. Đặt MỘT câu hỏi Q&A mà câu trả lời PHẢI lấy được từ "
        "chính đoạn lời thoại này (một con số, tên riêng, địa danh, sự kiện...) — "
        "TUYỆT ĐỐI không bịa chi tiết ngoài đoạn lời thoại. answer_vi ngắn gọn nhất "
        "có thể (vd '5', '30m', 'Hà Nội'). answer_variants: >= 3 cách diễn đạt KHÁC "
        "nhau của CÙNG một đáp án đó (vd '30m', '30 mét', 'khoảng 30 mét').\n\n"
        f"Lời thoại: {asr_text}",
        images=[img_path], json_schema=QA_SCHEMA, max_tokens=512,
    )
    d = json.loads(raw)
    event_vi, _ = _kis_query(img_path)
    answer_vi = d["answer_vi"].strip()
    variants = [v.strip() for v in d.get("answer_variants", []) if v.strip()]
    # API không cho ép minItems trong json_schema — tự bù nếu model trả thiếu,
    # GroundTruthQA đòi >= 3 (dev_set/tools/schema.py).
    if answer_vi not in variants:
        variants.insert(0, answer_vi)
    while len(variants) < 3:
        variants.append(f"{answer_vi} ")  # biến thể khoảng trắng — answer_matches() tự chuẩn hoá
    return event_vi, d["question_vi"].strip(), answer_vi, variants


def _event_caption(img_path: str) -> str:
    raw = llm(
        "Một khung hình trong chuỗi nhiều bước của cùng một video. Viết một cụm từ "
        "NGẮN mô tả đúng hành động/cảnh trong khung hình này (5-10 từ), không suy "
        "đoán ngoài khung hình.",
        images=[img_path], json_schema=EVENT_SCHEMA, max_tokens=256,
    )
    return json.loads(raw)["caption_vi"].strip()


def main() -> None:
    rng = random.Random(SEED)
    shots = pd.read_parquet(DERIVED / "shots.parquet")
    kf = pd.read_parquet(DERIVED / "keyframes.parquet", columns=["video_id", "frame_idx", "path"])
    asr = pd.read_parquet(DERIVED / "asr.parquet")

    # Shot đủ dài (>= 30 frame, tránh chuyển cảnh chớp nhoáng), có rep_kf_id.
    shots = shots[(shots["end_frame"] - shots["start_frame"] >= 30) & shots["rep_kf_id"].notna()]

    import re
    shots = shots.assign(batch=shots["video_id"].str.extract(r"(L\d+)"))
    batches = sorted(shots["batch"].unique())

    kis_rows, gt_rows = [], []

    # ---- KIS: trải đều batch, 1 video/batch mỗi vòng, 1 shot ngẫu nhiên/video
    used_videos: set[str] = set()
    i = 0
    while len(kis_rows) < N_KIS:
        batch = batches[i % len(batches)]
        pool = shots[(shots["batch"] == batch) & (~shots["video_id"].isin(used_videos))]
        if pool.empty:
            i += 1
            continue
        video_id = rng.choice(sorted(pool["video_id"].unique()))
        used_videos.add(video_id)
        shot = pool[pool["video_id"] == video_id].sample(1, random_state=rng.randint(0, 10**6)).iloc[0]
        mid = (int(shot["start_frame"]) + int(shot["end_frame"])) // 2
        img = _image_path_near(kf, video_id, mid)
        if img is None:
            i += 1
            continue
        img_path, frame_idx = img
        try:
            q_vi, q_en = _kis_query(img_path)
        except Exception as e:
            print(f"  [bỏ qua] {video_id} lỗi sinh câu KIS: {e}")
            i += 1
            continue
        qid = f"DRESS_KIS_{len(kis_rows) + 1:02d}"
        kis_rows.append({"query_id": qid, "task_type": "KIS", "query_vi": q_vi,
                          "query_en": q_en, "split": SPLIT})
        gt_rows.append({"query_id": qid, "task_type": "KIS", "video_id": video_id,
                         "frame_start": int(shot["start_frame"]), "frame_end": int(shot["end_frame"])})
        print(f"  KIS {qid}: [{video_id}] {q_vi}")
        i += 1

    # ---- QA: chọn 5 đoạn ASR đủ dài (>=15 từ), video KHÁC nhau
    qa_rows = []
    long_asr = asr[asr["text_vi"].str.split().str.len() >= 15].sample(
        frac=1.0, random_state=SEED
    ).drop_duplicates(subset="video_id")
    for _, seg in long_asr.head(N_QA).iterrows():
        video_id = seg["video_id"]
        mid = (int(seg["start_frame"]) + int(seg["end_frame"])) // 2
        img = _image_path_near(kf, video_id, mid)
        if img is None:
            continue
        img_path, frame_idx = img
        try:
            event_vi, question_vi, answer_vi, variants = _qa_pair(img_path, seg["text_vi"])
        except Exception as e:
            print(f"  [bỏ qua] {video_id} lỗi sinh câu QA: {e}")
            continue
        qid = f"DRESS_QA_{len(qa_rows) + 1:02d}"
        full_q = f"{event_vi} {question_vi}"
        qa_rows.append({"query_id": qid, "task_type": "QA", "query_vi": full_q, "split": SPLIT})
        gt_rows.append({"query_id": qid, "task_type": "QA", "video_id": video_id,
                         "frame_start": int(seg["start_frame"]), "frame_end": int(seg["end_frame"]),
                         "answer_text": answer_vi, "answer_variants": variants})
        print(f"  QA {qid}: [{video_id}] {question_vi} -> {answer_vi}")

    # ---- TRAKE: 1 video, N_TRAKE_EVENTS shot liên tiếp cách đều
    trake_rows = []
    video_shot_counts = shots.groupby("video_id").size()
    candidates = video_shot_counts[video_shot_counts >= N_TRAKE_EVENTS * 3].index.tolist()
    trake_video = rng.choice(candidates)
    v_shots = shots[shots["video_id"] == trake_video].sort_values("start_frame").reset_index(drop=True)
    idxs = [int(i * (len(v_shots) - 1) / (N_TRAKE_EVENTS - 1)) for i in range(N_TRAKE_EVENTS)]
    event_descs, event_gt = [], []
    for idx in idxs:
        shot = v_shots.iloc[idx]
        mid = (int(shot["start_frame"]) + int(shot["end_frame"])) // 2
        img = _image_path_near(kf, trake_video, mid)
        if img is None:
            continue
        img_path, _ = img
        caption = _event_caption(img_path)
        event_descs.append(caption)
        event_gt.append({"start": int(shot["start_frame"]), "end": int(shot["end_frame"])})

    if len(event_descs) == N_TRAKE_EVENTS:
        qid = "DRESS_TRAKE_01"
        query_vi = " . ".join(event_descs)
        trake_rows.append({"query_id": qid, "task_type": "TRAKE", "query_vi": query_vi,
                            "n_events": N_TRAKE_EVENTS, "event_descs": event_descs, "split": SPLIT})
        gt_rows.append({"query_id": qid, "task_type": "TRAKE", "video_id": trake_video,
                         "frames": event_gt})
        print(f"  TRAKE {qid}: [{trake_video}] {query_vi}")

    OUT_Q_DIR.mkdir(parents=True, exist_ok=True)
    OUT_GT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_Q_DIR / f"{SPLIT}_kis.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in kis_rows), encoding="utf-8")
    (OUT_Q_DIR / f"{SPLIT}_qa.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in qa_rows), encoding="utf-8")
    (OUT_Q_DIR / f"{SPLIT}_trake.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in trake_rows), encoding="utf-8")
    (OUT_GT_DIR / f"{SPLIT}_gt.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in gt_rows), encoding="utf-8")

    print(f"\nXong: {len(kis_rows)} KIS, {len(qa_rows)} QA, {len(trake_rows)} TRAKE")
    print(f"Ghi vào dev_set/queries/{SPLIT}_*.jsonl + dev_set/ground_truth/{SPLIT}_gt.jsonl")


if __name__ == "__main__":
    main()
