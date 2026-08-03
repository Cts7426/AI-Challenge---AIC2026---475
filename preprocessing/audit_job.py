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

def main():
    DERIVED_DIR.mkdir(parents=True, exist_ok=True)
    
    print("==================================================")
    print(" PHASE 1: Tạo video_info.parquet")
    print("==================================================")
    
    mp4_files = list((RAW_DIR / "videos").rglob("*.mp4"))
    print(f"Tìm thấy {len(mp4_files)} file MP4. Bắt đầu dùng ffprobe quét từng file...")
    
    video_info_data = []
    # Quét nhanh 20 file đầu tiên để tiết kiệm thời gian chờ nếu có nhiều (đây là kiểm tra gác cổng)
    sample_mp4s = mp4_files[:20] 
    
    for mp4 in tqdm(sample_mp4s, desc="ffprobe counting"):
        vid = mp4.stem
        fps_num, fps_den, n_frames = get_video_info(mp4)
        video_info_data.append({
            "video_id": vid,
            "fps_num": fps_num,
            "fps_den": fps_den,
            "n_frames": n_frames,
            "path": str(mp4)
        })
        
    df_info = pd.DataFrame(video_info_data)
    info_parquet_path = DERIVED_DIR / "video_info.parquet"
    df_info.to_parquet(info_parquet_path, index=False)
    print(f"Đã lưu {len(df_info)} bản ghi vào {info_parquet_path}\n")
    
    print("==================================================")
    print(" PHASE 2: Ánh xạ frame_map.parquet")
    print("==================================================")
    
    map_dir = RAW_DIR / "btc" / "metadata" / "media-info" / "map-keyframes"
    map_csvs = list(map_dir.glob("*.csv"))
    
    map_data = []
    for csv_file in map_csvs:
        vid = csv_file.stem
        # Chỉ map những video chúng ta đã có thông tin (trong df_info)
        if vid not in df_info['video_id'].values:
            continue
            
        df_csv = pd.read_csv(csv_file)
        # Các cột: n, pts_time, fps, frame_idx
        for _, row in df_csv.iterrows():
            map_data.append({
                "video_id": vid,
                "btc_kf_ordinal": int(row['n']),
                "frame_idx": int(row['frame_idx']),
                "pts_time": float(row['pts_time'])
            })
            
    df_map = pd.DataFrame(map_data)
    map_parquet_path = DERIVED_DIR / "frame_map.parquet"
    df_map.to_parquet(map_parquet_path, index=False)
    print(f"Đã map {len(df_map)} keyframes. Lưu tại {map_parquet_path}\n")
    
    print("==================================================")
    print(" PHASE 3: Trích xuất xác thực bằng mắt (Visual Verify)")
    print("==================================================")
    
    verify_dir = DERIVED_DIR / "verify_frames"
    if verify_dir.exists():
        shutil.rmtree(verify_dir)
    verify_dir.mkdir(parents=True)
    
    if len(df_map) == 0:
        print("Không có dữ liệu mapping hợp lệ.")
        return
        
    sample_size = min(20, len(df_map))
    samples = df_map.sample(n=sample_size, random_state=42)
    
    report_lines = ["# Báo cáo Xác thực Frame Mapping (Gác cổng G1)\n"]
    report_lines.append("Vui lòng mở thư mục `data/derived/verify_frames/` và kiểm tra bằng mắt cặp ảnh:\n")
    report_lines.append("Nếu ảnh `_btc` và `_extracted` khớp nhau hoàn toàn -> XANH!\n\n")
    report_lines.append("| STT | Video ID | BTC Ordinal | Frame IDX thực | Trạng thái |\n")
    report_lines.append("|---|---|---|---|---|\n")
    
    idx = 1
    for _, row in tqdm(samples.iterrows(), total=sample_size, desc="Extracting frames"):
        vid = row['video_id']
        ordinal = row['btc_kf_ordinal']
        f_idx = row['frame_idx']
        
        mp4_path = df_info[df_info['video_id'] == vid].iloc[0]['path']
        btc_img_path = find_btc_keyframe_path(vid, ordinal)
        
        if not btc_img_path:
            status = "LỖI: Không tìm thấy ảnh BTC"
            report_lines.append(f"| {idx} | {vid} | {ordinal} | {f_idx} | {status} |\n")
            idx += 1
            continue
            
        # 1. Copy ảnh BTC
        btc_dest = verify_dir / f"{idx:02d}_{vid}_f{f_idx:07d}_btc.jpg"
        shutil.copy2(btc_img_path, btc_dest)
        
        # 2. Extract frame thật bằng FFmpeg (select theo filter frame_idx chính xác tuyệt đối)
        ext_dest = verify_dir / f"{idx:02d}_{vid}_f{f_idx:07d}_extracted.jpg"
        cmd = [
            "ffmpeg", "-v", "error", "-y",
            "-i", str(mp4_path),
            "-vf", f"select=eq(n\,{f_idx})",
            "-vframes", "1",
            "-q:v", "2",
            str(ext_dest)
        ]
        subprocess.run(cmd, check=True)
        
        report_lines.append(f"| {idx} | {vid} | {ordinal} | {f_idx} | OK |\n")
        idx += 1
        
    report_path = verify_dir / "verify_report.md"
    with open(report_path, "w", encoding='utf-8') as f:
        f.writelines(report_lines)
        
    print(f"\n[HOÀN THÀNH] Mời bạn mở file báo cáo: {report_path}")
    print(f"Kiểm tra 20 cặp ảnh tại: {verify_dir}")

if __name__ == "__main__":
    main()
