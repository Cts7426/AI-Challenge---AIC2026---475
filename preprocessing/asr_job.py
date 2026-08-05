# preprocessing/asr_job.py — Task B1.3: ASR tiếng Việt trên audio
#
# ⚠️⚠️ JOB RẤT NẶNG — CHẠY TRÊN COLAB/KAGGLE (GPU free), KHÔNG CHẠY MÁY DEV 16GB.
#
# Cách chạy trên Kaggle:
#   python preprocessing/asr_job.py --videos data/derived/audio --shard 0 --num-shards 5

import argparse
import os
import hashlib
from pathlib import Path
import pandas as pd
from tqdm import tqdm

MERGE_TARGET_S = 20.0   # độ dài tối đa 1 đoạn sau khi gộp
MERGE_MAX_GAP_S = 2.0   # im lặng dài hơn ngưỡng này → cắt đoạn mới

def get_video_fps_map(info_path: Path):
    if not info_path.exists():
        raise FileNotFoundError(f"Không tìm thấy {info_path}")
    df_info = pd.read_parquet(info_path)
    fps_map = {}
    for _, row in df_info.iterrows():
        vid = row['video_id']
        num = row['fps_num']
        den = row.get('fps_den', 1)
        fps_map[vid] = (num, den)
    return fps_map

def merge_segments(segments: list[dict], target_s: float = MERGE_TARGET_S, max_gap_s: float = MERGE_MAX_GAP_S) -> list[dict]:
    merged: list[dict] = []
    cur: dict | None = None
    for seg in segments:
        text = seg["text"].strip()
        if not text:
            if (cur is not None and seg["start"] - cur["end"] <= max_gap_s and seg["end"] - cur["start"] <= target_s):
                cur["end"] = seg["end"]
            continue
        can_join = (
            cur is not None
            and seg["start"] - cur["end"] <= max_gap_s
            and seg["end"] - cur["start"] <= target_s
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
    from faster_whisper import WhisperModel
    return WhisperModel(model_name, device="auto", compute_type="int8_float16")

def transcribe_video(model, path: Path) -> list[dict]:
    # YÊU CẦU 3: Ép language="vi"
    segments, _info = model.transcribe(
        str(path),
        language="vi",
        vad_filter=True,
        beam_size=5,
    )
    return [{"start": s.start, "end": s.end, "text": s.text} for s in segments]

def main() -> None:
    parser = argparse.ArgumentParser(description="ASR tiếng Việt theo đoạn (chạy Colab/Kaggle)")
    parser.add_argument("--videos", type=Path, default=Path("data/derived/audio"), help="thư mục file audio (.wav)")
    parser.add_argument("--out-dir", type=Path, default=Path("data/derived/asr_parts"), help="thư mục chứa asr_parts")
    parser.add_argument("--info-path", type=Path, default=Path("data/derived/video_info.parquet"))
    parser.add_argument("--model", default="medium", help="model faster-whisper")
    parser.add_argument("--shard", type=int, default=0, help="Shard ID hiện tại")
    parser.add_argument("--num-shards", type=int, default=5, help="Tổng số shards")
    parser.add_argument("--batch-size", type=int, default=10, help="Số video mỗi lô")
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    fps_map = get_video_fps_map(args.info_path)

    all_audio = sorted([p for p in args.videos.rglob("*") if p.suffix.lower() in {".wav", ".mp4", ".m4a"}])
    
    # Lọc theo shard
    shard_files = []
    for p in all_audio:
        vid = p.stem
        h = int(hashlib.md5(vid.encode()).hexdigest(), 16)
        if h % args.num_shards == args.shard:
            shard_files.append((vid, p))
            
    print(f"Shard {args.shard}: Có {len(shard_files)} video cần xử lý ASR.")
    if not shard_files:
        return

    # Khởi tạo model
    model = make_model(args.model)

    # Chia lô
    batches = [shard_files[i:i + args.batch_size] for i in range(0, len(shard_files), args.batch_size)]

    for batch_idx, batch_items in enumerate(batches):
        # YÊU CẦU 2: Ghi part riêng từng lô
        part_filename = f"shard{args.shard}_batch{batch_idx:04d}.parquet"
        part_path = args.out_dir / part_filename
        
        if part_path.exists():
            print(f"Bỏ qua lô {batch_idx+1}/{len(batches)}: Đã tồn tại {part_filename}")
            continue
            
        print(f"\n=> Xử lý lô {batch_idx+1}/{len(batches)} (gồm {len(batch_items)} video)")
        batch_results = []
        
        for vid, path in tqdm(batch_items, desc=f"Lô {batch_idx+1}"):
            if vid not in fps_map:
                print(f"  [cảnh báo] Bỏ qua {vid}: không có trong video_info.parquet")
                continue
                
            fps_num, fps_den = fps_map[vid]
            
            try:
                raw_segments = transcribe_video(model, path)
            except Exception as e:
                print(f"  [lỗi] {vid}: {e}")
                continue
                
            merged = merge_segments(raw_segments)
            for seg_id, seg in enumerate(merged):
                start_s = seg["start"]
                end_s = seg["end"]
                
                # YÊU CẦU 1: Quy đổi start_frame / end_frame bằng fps phân số
                start_frame = int(start_s * (fps_num / fps_den))
                end_frame = int(end_s * (fps_num / fps_den))
                
                batch_results.append({
                    "video_id": vid,
                    "seg_id": seg_id,
                    "start_s": round(start_s, 3),
                    "end_s": round(end_s, 3),
                    "start_frame": start_frame,
                    "end_frame": end_frame,
                    "text_vi": seg["text"].strip()
                })
                
        # Ghi lô ra file
        df_part = pd.DataFrame(batch_results)
        if df_part.empty:
            df_part = pd.DataFrame(columns=["video_id", "seg_id", "start_s", "end_s", "start_frame", "end_frame", "text_vi"])
        df_part.to_parquet(part_path, index=False)
        print(f"Đã lưu lô {batch_idx+1} vào {part_path} ({len(df_part)} dòng)")

    print(f"\n[OK] Shard {args.shard} hoàn tất!")

if __name__ == "__main__":
    main()
