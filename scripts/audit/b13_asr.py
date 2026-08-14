import os
import sys
from pathlib import Path
import pandas as pd
import numpy as np

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

DATA_DIR = ROOT_DIR / "data"
DERIVED_DIR = DATA_DIR / "derived"
ASR_FILE = DERIVED_DIR / "asr.parquet"
VIDEO_INFO = DERIVED_DIR / "video_info.parquet"

def b13_asr_audit():
    print("\n" + "="*50)
    print("NGHIỆM THU B1.3: TRÍCH XUẤT AUDIO & ASR")
    print("="*50)
    
    # 1. Load Data
    try:
        df_asr = pd.read_parquet(ASR_FILE)
        df_info = pd.read_parquet(VIDEO_INFO)
    except Exception as e:
        print(f"❌ FAIL: Không thể load dữ liệu: {e}")
        return False
        
    print(f"Tổng số Segments ASR: {len(df_asr):,}")
    print(f"Tổng số Videos có ASR: {df_asr['video_id'].nunique():,} / {len(df_info)}")
    
    # L1-1: Cấu trúc cột
    req_cols = {"video_id", "seg_id", "start_s", "end_s", "start_frame", "end_frame", "text_vi"}
    missing = req_cols - set(df_asr.columns)
    if missing:
        print(f"❌ FAIL L1-1: Thiếu các cột bắt buộc: {missing}")
    else:
        print("✅ PASS L1-1: Cấu trúc cột hợp lệ.")
        
    # Chuẩn bị dữ liệu cho L1-2
    df = df_asr.merge(df_info[["video_id", "fps_num", "fps_den", "nb_frames_decoded", "has_audio"]], on="video_id", how="left")
    df["fps"] = df["fps_num"] / df["fps_den"]
    
    # L1-2: Tính toán Frame quy đổi
    print("\n--- KIỂM TRA L1: TÍNH TOÁN FRAME QUY ĐỔI ---")
    
    # Tính lại frame chuẩn bằng float nhân, rồi làm tròn round() hoặc int()
    # Tùy thuật toán asr_job.py, thường là round()
    expected_start = np.round(df["start_s"] * df["fps"]).astype(int)
    expected_end = np.round(df["end_s"] * df["fps"]).astype(int)
    
    # Cho phép sai số 1 frame do làm tròn
    start_diff = np.abs(df["start_frame"] - expected_start)
    end_diff = np.abs(df["end_frame"] - expected_end)
    
    bad_starts = start_diff[start_diff > 1]
    bad_ends = end_diff[end_diff > 1]
    
    if len(bad_starts) > 0 or len(bad_ends) > 0:
        print(f"❌ FAIL L1-2a: Phát hiện {len(bad_starts)} start_frame và {len(bad_ends)} end_frame bị quy đổi sai công thức (lệch > 1 frame).")
    else:
        print("✅ PASS L1-2a: Công thức quy đổi Frame từ Giây (s) hoàn toàn chính xác.")
        
    # L1-2b: Logic biên
    invalid_bounds = df[df["start_frame"] > df["end_frame"]]
    out_of_bounds = df[df["end_frame"] > df["nb_frames_decoded"]]
    
    if len(invalid_bounds) > 0:
        print(f"❌ FAIL L1-2b: Có {len(invalid_bounds)} segment bị ngược start/end frame!")
    elif len(out_of_bounds) > 0:
        print(f"❌ FAIL L1-2b: Có {len(out_of_bounds)} segment có end_frame vượt qua độ dài video!")
    else:
        print("✅ PASS L1-2b: Không có segment nào bị lỗi biên hoặc vượt quá số frame thực tế của video.")

    # L2: Thống kê Video bị skip
    print("\n--- BÁO CÁO PHÂN PHỐI L2 ---")
    valid_vids = set(df_info["video_id"])
    asr_vids = set(df_asr["video_id"])
    missing_vids = valid_vids - asr_vids
    
    # Lọc các video có has_audio = False
    missing_no_audio = set(df_info[df_info["has_audio"] == False]["video_id"])
    missing_but_has_audio = missing_vids - missing_no_audio
    
    if missing_but_has_audio:
        print(f"⚠️ CẢNH BÁO L2: Có {len(missing_but_has_audio)} video CÓ AUDIO nhưng không có dữ liệu ASR!")
        print("   -> Nguyên nhân: Có thể file video là audio câm (silent) nên Whisper không sinh ra segment, hoặc job bị rớt.")
    else:
        print(f"✅ PASS L2: Không có video nào bị sót một cách bất thường (Tổng video không có tiếng: {len(missing_no_audio)}).")

if __name__ == "__main__":
    b13_asr_audit()
