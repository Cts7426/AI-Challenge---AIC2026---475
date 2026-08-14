import os
import json
import pandas as pd
import subprocess
from pathlib import Path
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
DERIVED_DIR = DATA_DIR / "derived"
INFO_PATH = DERIVED_DIR / "video_info.parquet"
VIDEOS_DIR = RAW_DIR / "videos"

def get_real_metadata(video_id, mp4_path):
    try:
        cmd = [
            "ffprobe", "-v", "error", 
            "-show_format", "-show_streams", 
            "-print_format", "json", str(mp4_path)
        ]
        
        output = subprocess.check_output(cmd, text=True)
        data = json.loads(output)
        
        format_info = data.get("format", {})
        v_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
        a_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), {})
        
        duration_sec = float(format_info.get("duration", v_stream.get("duration", 0.0)))
        r_frame_rate = v_stream.get("r_frame_rate", "0/1")
        avg_frame_rate = v_stream.get("avg_frame_rate", "0/1")
        is_vfr = (r_frame_rate != avg_frame_rate)
        has_audio = bool(a_stream)
        
        return {
            "duration_sec": duration_sec,
            "is_vfr": is_vfr,
            "has_audio": has_audio
        }, None
        
    except Exception as e:
        return None, f"Lỗi lấy dữ liệu {video_id}: {e}"

def main():
    if not INFO_PATH.exists():
        print("❌ Không tìm thấy video_info.parquet")
        return
        
    df = pd.read_parquet(INFO_PATH)
    
    # Chuẩn hoá tên cột
    if 'n_frames' in df.columns:
        df = df.rename(columns={'n_frames': 'nb_frames_decoded'})
        
    print(f"Đang xử lý {len(df)} video...")
    
    temp_json = DERIVED_DIR / "real_metadata_temp.json"
    results = {}
    if temp_json.exists():
        with open(temp_json, "r") as f:
            results = json.load(f)
            
    vids_to_fetch = [vid for vid in df["video_id"] if vid not in results]
    print(f"Cần trích xuất thật từ file mp4: {len(vids_to_fetch)} video.")
    
    if vids_to_fetch:
        workers = 8
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {}
            for vid in vids_to_fetch:
                mp4_paths = list(VIDEOS_DIR.rglob(f"{vid}.mp4"))
                if mp4_paths:
                    futures[pool.submit(get_real_metadata, vid, mp4_paths[0])] = vid
                else:
                    print(f"⚠️ Không tìm thấy file {vid}.mp4 trên đĩa!")
                            
            for fut in tqdm(as_completed(futures), total=len(futures), desc="Extracting true metadata"):
                vid = futures[fut]
                res, err = fut.result()
                if res:
                    results[vid] = res
                    # Ghi liên tục để chống đứt đoạn
                    with open(temp_json, "w") as f:
                        json.dump(results, f)
                elif err:
                    print(err)
                    
    # Cập nhật DataFrame
    durations, is_vfrs, has_audios = [], [], []
    for vid in df["video_id"]:
        r = results.get(vid, {})
        durations.append(r.get("duration_sec", 0.0))
        is_vfrs.append(r.get("is_vfr", False))
        has_audios.append(r.get("has_audio", False))
        
    df["duration_sec"] = durations
    df["is_vfr"] = is_vfrs
    df["has_audio"] = has_audios
    
    df.to_parquet(INFO_PATH, index=False)
    print("✅ Đã ghi dữ liệu metadata TRUNG THỰC từ ffprobe vào video_info.parquet!")
    print("\n--- SCHEMA MỚI ---")
    print(df.columns.tolist())

if __name__ == '__main__':
    main()

