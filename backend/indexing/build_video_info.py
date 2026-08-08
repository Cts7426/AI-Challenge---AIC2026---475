import os
import glob
import subprocess
import pandas as pd
from pathlib import Path
from tqdm import tqdm
from fractions import Fraction

def get_video_info(mp4_path: str):
    """
    Sử dụng ffprobe để bóc tách thông tin video.
    BẮT BUỘC dùng -count_frames để đếm THẬT từng frame vật lý, không đọc qua metadata header.
    Lý do đếm thật: Các video H.264 đôi khi bị drop frame hoặc header ghi sai số lượng frame.
    """
    cmd = [
        "ffprobe", 
        "-v", "error", 
        "-select_streams", "v:0",
        "-count_frames", # Đếm từng frame thực tế thay vì lấy header
        "-show_entries", "stream=r_frame_rate,nb_read_frames,duration,width,height",
        "-of", "csv=p=0", 
        mp4_path
    ]
    
    try:
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True).strip()
        # Output format: width,height,r_frame_rate,duration,nb_read_frames
        # Ví dụ: 1280,720,30000/1001,120.45,3612
        parts = output.split(",")
        if len(parts) >= 5:
            width = int(parts[0])
            height = int(parts[1])
            fps_str = parts[2]
            duration_s = float(parts[3])
            n_frames = int(parts[4])
            
            # Xử lý fps_num, fps_den
            if "/" in fps_str:
                fps_num, fps_den = map(int, fps_str.split("/"))
            else:
                fps_num = int(float(fps_str))
                fps_den = 1
                
            return {
                "fps_num": fps_num,
                "fps_den": fps_den,
                "n_frames": n_frames,
                "duration_s": duration_s,
                "width": width,
                "height": height
            }
    except Exception as e:
        print(f"Lỗi đọc {mp4_path}: {e}")
    return None

def build_video_info(video_dir: Path, out_path: Path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    mp4_files = list(video_dir.rglob("*.mp4"))
    if not mp4_files:
        print(f"Không tìm thấy file .mp4 nào trong {video_dir}")
        return
        
    records = []
    print(f"Đang phân tích {len(mp4_files)} video (Sẽ hơi chậm vì đếm khung hình vật lý)...")
    for p in tqdm(mp4_files):
        vid = p.stem
        info = get_video_info(str(p))
        if info:
            info["video_id"] = vid
            records.append(info)
            
    df = pd.DataFrame(records)
    # Sắp xếp các cột theo yêu cầu B0.1a
    df = df[["video_id", "fps_num", "fps_den", "n_frames", "duration_s", "width", "height"]]
    df.to_parquet(out_path, index=False)
    print(f"✅ Đã ghi thông tin {len(df)} video vào {out_path}")

if __name__ == "__main__":
    video_dir = Path("data/raw/videos/video")
    out_parquet = Path("data/derived/video_info.parquet")
    build_video_info(video_dir, out_parquet)
