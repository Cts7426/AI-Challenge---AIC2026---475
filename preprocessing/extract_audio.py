import subprocess
import argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import pandas as pd

def extract_one(vid, mp4_path, out_dir):
    out_path = out_dir / f"{vid}.wav"
    if out_path.exists():
        return (vid, "skipped")
        
    # Thử check xem có audio không
    cmd_check = [
        "ffprobe", "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=codec_name", "-of", "default=noprint_wrappers=1:nokey=1",
        str(mp4_path)
    ]
    try:
        has_audio = subprocess.check_output(cmd_check, text=True).strip() != ""
    except Exception:
        has_audio = False
        
    if not has_audio:
        return (vid, "no_audio")
        
    # Trích xuất
    cmd = [
        "ffmpeg", "-y", "-v", "quiet",
        "-i", str(mp4_path),
        "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
        str(out_path)
    ]
    subprocess.run(cmd)
    return (vid, "done")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    
    VIDEOS_DIR = Path("data/raw/videos")
    AUDIO_DIR = Path("data/derived/audio")
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    
    # Lấy toàn bộ video đang có đuôi .mp4 trên ổ cứng
    mp4_files = list(VIDEOS_DIR.rglob("*.mp4"))
    vids = [p.stem for p in mp4_files]
    vid_to_path = {p.stem: p for p in mp4_files}
    print(f"Bắt đầu trích xuất audio cho {len(vids)} video...")
    
    results = {"done": 0, "no_audio": 0, "skipped": 0}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = []
        for vid in vids:
            mp4_path = vid_to_path[vid]
            futures.append(pool.submit(extract_one, vid, mp4_path, AUDIO_DIR))
                
        for fut in futures:
            vid, status = fut.result()
            results[status] += 1
            
    print("\n=== HOÀN THÀNH ===")
    print(f"Trích xuất thành công: {results['done']}")
    print(f"Bỏ qua (không có audio stream): {results['no_audio']}")
    print(f"Bỏ qua (đã tồn tại): {results['skipped']}")

if __name__ == "__main__":
    main()
