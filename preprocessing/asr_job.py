# preprocessing/asr_job.py — Task 4.2: ASR tiếng Việt trên audio video
#
# ⚠️⚠️ JOB RẤT NẶNG — CHẠY TRÊN COLAB/KAGGLE (GPU free), KHÔNG CHẠY MÁY DEV 16GB.
# Whisper medium chiếm ~5GB, transcribe 1000h video trên CPU là bất khả thi.
#
# Cách chạy trên Colab (Runtime → GPU T4):
#   !git clone <repo_url> aic && %cd aic
#   !pip install faster-whisper
#   # mount/upload thư mục video (mỗi file <video_id>.mp4)
#   !python preprocessing/asr_job.py --videos /content/videos --out data/asr/asr_results.jsonl
#   # model tiếng Việt tốt hơn (PhoWhisper convert sang CT2) nếu có:
#   !python preprocessing/asr_job.py --videos ... --model <path-hoặc-repo-CT2>
#
# Vì sao faster-whisper (không phải openai-whisper gốc)?
# → Cùng model, chạy bằng CTranslate2 nhanh ~4x và ít VRAM hơn — quan trọng
#   khi GPU free có hạn ngạch. TODO: thử PhoWhisper (VinAI finetune tiếng Việt)
#   bản CT2 khi tìm được repo chuyển đổi tin cậy — chất lượng VI tốt hơn.
#
# Vì sao GỘP các segment Whisper (~2-8s) thành đoạn ~20s?
# → Segment quá ngắn thì BM25 gần như không có ngữ cảnh để match query dài;
#   đoạn quá dài thì định vị thời gian kém (nhảy tới đâu trong video?).
#   ~20s là điểm cân bằng: đủ chữ để match, đủ hẹp để nhảy đúng khoảnh khắc.
#   Chỉ gộp khi im lặng giữa 2 segment <= 2s — qua khoảng nghỉ dài là đoạn mới
#   (thường đổi chủ đề/cảnh).
#
# Resume THEO VIDEO: kết quả ghi trọn gói từng video + flush. Colab rớt giữa
# video nào chỉ mất video đó; chạy lại lệnh cũ tự bỏ qua video đã xong.
#
# Output mỗi dòng: {"video_id", "start_ms", "end_ms", "text"}

import argparse
import json
from pathlib import Path

MEDIA_EXTS = {".mp4", ".mkv", ".webm", ".avi", ".mov", ".m4a", ".mp3", ".wav"}
MERGE_TARGET_S = 20.0   # độ dài tối đa 1 đoạn sau khi gộp
MERGE_MAX_GAP_S = 2.0   # im lặng dài hơn ngưỡng này → cắt đoạn mới


def iter_videos(videos_dir: Path):
    """<videos_dir>/<video_id>.mp4 → (video_id, path). TODO: BTC — cấu trúc thật."""
    for p in sorted(videos_dir.rglob("*")):
        if p.suffix.lower() in MEDIA_EXTS:
            yield p.stem, p


def load_done(out_path: Path) -> set[str]:
    """Tập video_id đã transcribe xong (resume theo video)."""
    done = set()
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            try:
                done.add(json.loads(line)["video_id"])
            except (json.JSONDecodeError, KeyError):
                pass
    return done


def merge_segments(segments: list[dict],
                   target_s: float = MERGE_TARGET_S,
                   max_gap_s: float = MERGE_MAX_GAP_S) -> list[dict]:
    """Gộp segment Whisper liền kề thành đoạn ~target_s giây.

    segments: [{"start": s, "end": s, "text": str}] (giây, đã theo thứ tự).
    Hàm thuần — test được không cần model/GPU.
    """
    merged: list[dict] = []
    cur: dict | None = None
    for seg in segments:
        text = seg["text"].strip()
        if not text:
            # Segment trắng (rác VAD) — không được làm GÃY chuỗi gộp: nếu đang
            # gộp và liền kề thì nới end làm cầu nối thời gian, không thêm chữ
            if (cur is not None
                    and seg["start"] - cur["end"] <= max_gap_s
                    and seg["end"] - cur["start"] <= target_s):
                cur["end"] = seg["end"]
            continue
        can_join = (
            cur is not None
            and seg["start"] - cur["end"] <= max_gap_s   # không có khoảng lặng dài
            and seg["end"] - cur["start"] <= target_s    # gộp xong vẫn <= target
        )
        if can_join:
            cur["end"] = seg["end"]
            cur["text"] += " " + text
        else:
            if cur:
                merged.append(cur)
            cur = {"start": seg["start"], "end": seg["end"], "text": text}
    if cur:
        merged.append(cur)
    return merged


def make_model(model_name: str):
    """Khởi tạo faster-whisper. Import lười — máy không cài vẫn test được phần logic."""
    from faster_whisper import WhisperModel

    # device="auto": Colab có GPU thì dùng, không thì CPU (chậm — chỉ để thử 1 video)
    # compute_type int8_float16: giảm nửa VRAM trên T4, chất lượng gần như nguyên
    return WhisperModel(model_name, device="auto", compute_type="int8_float16")


def transcribe_video(model, path: Path) -> list[dict]:
    """1 video → list segment thô (giây). faster-whisper tự rút audio từ mp4."""
    segments, _info = model.transcribe(
        str(path),
        language="vi",
        vad_filter=True,   # bỏ đoạn im lặng/nhạc nền — nhanh hơn hẳn với video tin tức
        beam_size=5,
    )
    return [{"start": s.start, "end": s.end, "text": s.text} for s in segments]


def main() -> None:
    parser = argparse.ArgumentParser(description="ASR tiếng Việt theo đoạn (chạy Colab/Kaggle)")
    parser.add_argument("--videos", type=Path, required=True, help="thư mục file video/audio")
    parser.add_argument("--out", type=Path, default=Path("data/asr/asr_results.jsonl"))
    parser.add_argument("--model", default="medium",
                        help='model faster-whisper ("medium", "large-v3", hoặc path CT2 PhoWhisper)')
    args = parser.parse_args()

    done = load_done(args.out)
    todo = [(v, p) for v, p in iter_videos(args.videos) if v not in done]
    print(f"Video cần ASR: {len(todo)} (đã xong: {len(done)})")
    if not todo:
        return

    args.out.parent.mkdir(parents=True, exist_ok=True)
    model = make_model(args.model)

    with args.out.open("a", encoding="utf-8") as f:
        for idx, (video_id, path) in enumerate(todo, 1):
            print(f"[{idx}/{len(todo)}] {video_id} …")
            try:
                raw = transcribe_video(model, path)
            except Exception as e:
                # 1 file hỏng (codec lạ, tải thiếu) không được giết cả job qua đêm
                print(f"  [cảnh báo] bỏ qua {video_id}: {e}")
                continue
            for seg in merge_segments(raw):
                f.write(json.dumps({
                    "video_id": video_id,
                    "start_ms": int(seg["start"] * 1000),
                    "end_ms": int(seg["end"] * 1000),
                    "text": seg["text"],
                }, ensure_ascii=False) + "\n")
            f.flush()  # trọn gói từng video xuống đĩa — rớt Colab chỉ mất video dở dang

    print(f"Xong. Kết quả: {args.out} — nạp vào ES bằng:")
    print("  python -m backend.indexing.load_asr --file", args.out)


if __name__ == "__main__":
    main()
