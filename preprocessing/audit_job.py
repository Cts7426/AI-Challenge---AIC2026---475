import os
import sys
import subprocess
import json
import pandas as pd
import shutil
import random
from pathlib import Path
from tqdm import tqdm

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
DERIVED_DIR = DATA_DIR / "derived"

def get_video_info(mp4_path: Path):
    """
    Sử dụng ffprobe để lấy fps phân số và số lượng frame chính xác.
    ffprobe -count_frames ép giải mã toàn bộ video để đếm, chậm nhưng chính xác 100%.
    """
    cmd_fps = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=r_frame_rate",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(mp4_path)
    ]
    
    cmd_frames = [
        "ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
        "-show_entries", "stream=nb_read_frames",
        "-of", "default=nokey=1:noprint_wrappers=1",
        str(mp4_path)
    ]
    
    fps_str = subprocess.check_output(cmd_fps, text=True).strip()
    n_frames_str = subprocess.check_output(cmd_frames, text=True).strip()
    
    if '/' in fps_str:
        num, den = fps_str.split('/')
        fps_num, fps_den = int(num), int(den)
    else:
        fps_num, fps_den = int(float(fps_str)), 1
        
    n_frames = int(n_frames_str)
    
    return fps_num, fps_den, n_frames

def find_btc_keyframe_path(video_id: str, btc_ordinal: int):
    """
    Tìm đường dẫn tới ảnh keyframe gốc của BTC.
    Tên file thường là 001.jpg, 002.jpg hoặc 0001.jpg.
    """
    kf_dirs = list((RAW_DIR / "btc" / "keyframes").rglob(video_id))
    if not kf_dirs:
        return None
    kf_dir = kf_dirs[0]
    
    # Thử 3 chữ số
    f3 = kf_dir / f"{btc_ordinal:03d}.jpg"
    if f3.exists(): return f3
    # Thử 4 chữ số
    f4 = kf_dir / f"{btc_ordinal:04d}.jpg"
    if f4.exists(): return f4
    
    return None

import argparse
from concurrent.futures import ThreadPoolExecutor

def process_one_video(mp4: Path):
    vid = mp4.stem
    fps_num, fps_den, n_frames = get_video_info(mp4)
    return {
        "video_id": vid,
        "fps_num": fps_num,
        "fps_den": fps_den,
        "n_frames": n_frames,
        "path": str(mp4.relative_to(ROOT_DIR))
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=10)
    args = parser.parse_args()

    DERIVED_DIR.mkdir(parents=True, exist_ok=True)
    info_parquet_path = DERIVED_DIR / "video_info.parquet"
    
    existing_vids = set()
    existing_data = []
    if info_parquet_path.exists():
        df_old = pd.read_parquet(info_parquet_path)
        existing_vids = set(df_old["video_id"])
        existing_data = df_old.to_dict("records")
        print(f"Đã có {len(existing_data)} video trong video_info.parquet.")
    
    mp4_files = list((RAW_DIR / "videos").rglob("*.mp4"))
    
    to_process = [mp4 for mp4 in mp4_files if mp4.stem not in existing_vids]
    print(f"Tìm thấy {len(mp4_files)} file MP4. Cần chạy ffprobe cho {len(to_process)} file mới...")
    
    if not to_process:
        print("Không có file mới nào cần quét!")
        return

    new_data = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(process_one_video, mp4): mp4 for mp4 in to_process}
        for fut in tqdm(futures, total=len(to_process), desc="ffprobe counting"):
            try:
                res = fut.result()
                new_data.append(res)
            except Exception as e:
                print(f"Lỗi khi xử lý {futures[fut].stem}: {e}")
                
    if new_data:
        df_info = pd.DataFrame(existing_data + new_data)
        df_info.to_parquet(info_parquet_path, index=False)
        print(f"\nĐã gộp và lưu tổng cộng {len(df_info)} bản ghi vào {info_parquet_path}\n")

if __name__ == "__main__":
    main()
