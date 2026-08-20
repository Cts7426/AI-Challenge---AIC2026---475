from __future__ import annotations
import json
import random
from pathlib import Path
import pandas as pd
from backend.llm.adapter import llm

REPO_ROOT = Path(__file__).resolve().parent
DERIVED = REPO_ROOT / "data" / "derived"
OUT_Q_DIR = REPO_ROOT / "dev_set" / "queries"
OUT_GT_DIR = REPO_ROOT / "dev_set" / "ground_truth"

SPLIT = "tune"
N_QA = 10
N_TRAKE = 10
N_TRAKE_EVENTS = 3
SEED = 2026082102

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
KIS_SCHEMA = {
    "type": "object",
    "properties": {"query_vi": {"type": "string"}, "query_en": {"type": "string"}},
    "required": ["query_vi", "query_en"],
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
        "video. Kèm bản dịch tiếng Anh ngắn.",
        images=[img_path], json_schema=KIS_SCHEMA,
    )
    d = json.loads(raw)
    return d["query_vi"].strip(), d["query_en"].strip()

def _qa_pair(img_path: str, asr_text: str) -> tuple[str, str, str, list[str]]:
    raw = llm(
        "Đây là 1 khung hình + đoạn lời thoại (ASR) TẠI ĐÚNG khoảnh khắc đó của một "
        "video tin tức Việt Nam. Đặt MỘT câu hỏi Q&A mà câu trả lời PHẢI lấy được từ "
        "chính đoạn lời thoại này (một con số, tên riêng, địa danh, sự kiện...) — "
        "TUYỆT ĐỐI không bịa chi tiết ngoài đoạn lời thoại. answer_vi ngắn gọn nhất "
        "có thể. answer_variants: >= 3 cách diễn đạt KHÁC nhau của CÙNG một đáp án đó.\n\n"
        f"Lời thoại: {asr_text}",
        images=[img_path], json_schema=QA_SCHEMA,
    )
    d = json.loads(raw)
    event_vi, _ = _kis_query(img_path)
    answer_vi = d["answer_vi"].strip()
    variants = [v.strip() for v in d.get("answer_variants", []) if v.strip()]
    if answer_vi not in variants:
        variants.insert(0, answer_vi)
    while len(variants) < 3:
        variants.append(f"{answer_vi} ")
    return event_vi, d["question_vi"].strip(), answer_vi, variants

def _event_caption(img_path: str) -> str:
    raw = llm(
        "Một khung hình trong chuỗi nhiều bước của cùng một video. Viết một cụm từ "
        "NGẮN mô tả đúng hành động/cảnh trong khung hình này (5-10 từ), không suy "
        "đoán ngoài khung hình.",
        images=[img_path], json_schema=EVENT_SCHEMA,
    )
    return json.loads(raw)["caption_vi"].strip()

def main() -> None:
    print("Loading data...")
    rng = random.Random(SEED)
    shots = pd.read_parquet(DERIVED / "shots.parquet")
    kf = pd.read_parquet(DERIVED / "keyframes.parquet", columns=["video_id", "frame_idx", "path"])
    asr = pd.read_parquet(DERIVED / "asr.parquet")

    shots = shots[(shots["end_frame"] - shots["start_frame"] >= 30) & shots["rep_kf_id"].notna()]
    qa_rows, trake_rows, gt_rows = [], [], []

    print(f"Generating {N_QA} QA queries...")
    long_asr = asr[asr["text_vi"].str.split().str.len() >= 15].sample(frac=1.0, random_state=SEED).drop_duplicates(subset="video_id")
    for _, seg in long_asr.iterrows():
        if len(qa_rows) >= N_QA:
            break
        video_id = seg["video_id"]
        mid = (int(seg["start_frame"]) + int(seg["end_frame"])) // 2
        img = _image_path_near(kf, video_id, mid)
        if img is None: continue
        try:
            event_vi, question_vi, answer_vi, variants = _qa_pair(img[0], seg["text_vi"])
        except Exception as e:
            continue
        qid = f"GEN_QA_{len(qa_rows) + 1:02d}"
        qa_rows.append({"query_id": qid, "task_type": "QA", "query_vi": f"{event_vi} {question_vi}", "split": SPLIT})
        gt_rows.append({"query_id": qid, "task_type": "QA", "video_id": video_id,
                         "frame_start": int(seg["start_frame"]), "frame_end": int(seg["end_frame"]),
                         "answer_text": answer_vi, "answer_variants": variants})
        print(f"✅ QA {qid}: {question_vi} -> {answer_vi}")

    print(f"\nGenerating {N_TRAKE} TRAKE queries...")
    video_shot_counts = shots.groupby("video_id").size()
    candidates = video_shot_counts[video_shot_counts >= N_TRAKE_EVENTS * 3].index.tolist()
    rng.shuffle(candidates)
    
    for trake_video in candidates:
        if len(trake_rows) >= N_TRAKE:
            break
        v_shots = shots[shots["video_id"] == trake_video].sort_values("start_frame").reset_index(drop=True)
        idxs = [int(i * (len(v_shots) - 1) / (N_TRAKE_EVENTS - 1)) for i in range(N_TRAKE_EVENTS)]
        event_descs, event_gt = [], []
        for idx in idxs:
            shot = v_shots.iloc[idx]
            mid = (int(shot["start_frame"]) + int(shot["end_frame"])) // 2
            img = _image_path_near(kf, trake_video, mid)
            if img is None: continue
            try:
                caption = _event_caption(img[0])
                event_descs.append(caption)
                event_gt.append({"start": int(shot["start_frame"]), "end": int(shot["end_frame"])})
            except Exception:
                pass
                
        if len(event_descs) == N_TRAKE_EVENTS:
            qid = f"GEN_TRAKE_{len(trake_rows) + 1:02d}"
            query_vi = " . ".join(event_descs)
            trake_rows.append({"query_id": qid, "task_type": "TRAKE", "query_vi": query_vi,
                                "n_events": N_TRAKE_EVENTS, "event_descs": event_descs, "split": SPLIT})
            gt_rows.append({"query_id": qid, "task_type": "TRAKE", "video_id": trake_video,
                             "frames": event_gt})
            print(f"✅ TRAKE {qid}: {query_vi}")

    (OUT_Q_DIR / "gen10_qa.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in qa_rows), encoding="utf-8")
    (OUT_Q_DIR / "gen10_trake.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in trake_rows), encoding="utf-8")
    (OUT_GT_DIR / "gen10_gt.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in gt_rows), encoding="utf-8")
    print("\nDone generating.")

if __name__ == "__main__":
    main()
