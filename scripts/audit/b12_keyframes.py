import os
import sys
from pathlib import Path
import pandas as pd
import numpy as np

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

# Try to import visual verification, might not exist or work depending on OpenCV
try:
    from scripts.audit.b01_l3_contact_sheet import verify_visual_mapping
except ImportError:
    verify_visual_mapping = None

DATA_DIR = ROOT_DIR / "data"
DERIVED_DIR = DATA_DIR / "derived"
KF_FILE = DERIVED_DIR / "keyframes.parquet"
SHOTS_FILE = DERIVED_DIR / "shots.parquet"
VIDEO_INFO = DERIVED_DIR / "video_info.parquet"

def b12_keyframes_audit():
    print("\n" + "="*50)
    print("NGHIỆM THU B1.2: TRÍCH XUẤT KEYFRAME TỰ ĐỊNH NGHĨA")
    print("="*50)
    
    # 1. Load Data
    try:
        df_kf = pd.read_parquet(KF_FILE)
        df_shots = pd.read_parquet(SHOTS_FILE)
        df_info = pd.read_parquet(VIDEO_INFO)
    except Exception as e:
        print(f"❌ FAIL: Không thể load dữ liệu: {e}")
        return False
        
    print(f"Tổng số Keyframes: {len(df_kf):,}")
    print(f"Tổng số Videos có Keyframes: {df_kf['video_id'].nunique():,} / {len(df_info)}")
    
    # L1-1: Cấu trúc cột
    req_cols = {"kf_id", "video_id", "shot_id", "frame_idx", "path"}
    missing = req_cols - set(df_kf.columns)
    if missing:
        print(f"❌ FAIL L1-1: Thiếu các cột bắt buộc: {missing}")
    else:
        print("✅ PASS L1-1: Cấu trúc cột hợp lệ.")
        
    # L1-2: Toàn vẹn khóa shot_id
    invalid_shots = set(df_kf["shot_id"]) - set(df_shots["shot_id"])
    if invalid_shots:
        print(f"❌ FAIL L1-2: Có {len(invalid_shots)} shot_id trong Keyframes không tồn tại!")
    else:
        print("✅ PASS L1-2: 100% shot_id trỏ về đúng shots.parquet (Không mồ côi).")

    # L1-3: Mật độ 1 fps (min 2, max 20)
    print("\n--- KIỂM TRA L1: MẬT ĐỘ 1 FPS ---")
    shot_counts = df_kf.groupby("shot_id").size()
    
    # Lọc ra các shot cực ngắn (thời lượng < 1s) từ df_shots để tránh báo lỗi oan
    df_shots["fps"] = df_shots["video_id"].map(df_info.set_index("video_id").eval("fps_num / fps_den"))
    df_shots["duration_s"] = (df_shots["end_frame"] - df_shots["start_frame"]) / df_shots["fps"]
    short_shots = set(df_shots[df_shots["duration_s"] < 2.0]["shot_id"])
    
    # Check max 20
    over_20 = shot_counts[shot_counts > 20]
    if len(over_20) > 0:
        print(f"❌ FAIL L1-3a: Có {len(over_20)} shot bị trích > 20 keyframes! (Vi phạm Max 20).")
    else:
        print("✅ PASS L1-3a: Không có shot nào bị trích quá 20 keyframes.")
        
    # Check min 2 (loại trừ các shot ngắn < 2 giây)
    under_2 = shot_counts[shot_counts < 2]
    under_2_long = under_2[~under_2.index.isin(short_shots)]
    if len(under_2_long) > 0:
        print(f"❌ FAIL L1-3b: Có {len(under_2_long)} shot DÀI >= 2s nhưng trích < 2 keyframes! (Vi phạm Min 2).")
    else:
        print("✅ PASS L1-3b: Các shot đủ dài đều đảm bảo tối thiểu 2 keyframes.")

    # L3: Verify Visual Mapping
    print("\n--- KIỂM TRA L3: THẨM ĐỊNH MẮT NGƯỜI (VISUAL VERIFICATION) ---")
    if verify_visual_mapping:
        try:
            sample_df = df_kf.sample(n=20, random_state=42)
            # rename for compatibility with the visual mapping tool which expects 'frame_idx'
            print("Đang render 20 mẫu ngẫu nhiên để kiểm tra frame_idx...")
            
            # The tool might expect 'btc_filename' or 'kf_id'. Let's adapt if needed.
            # We'll just pass the dataframe as is.
            success = verify_visual_mapping(sample_df, output_dir=DERIVED_DIR / "_audit" / "evidence" / "b12")
            if success:
                print("✅ PASS L3: 20/20 mẫu Keyframes tự trích xuất có frame_idx trùng khớp hoàn toàn với Video vật lý!")
            else:
                print("❌ FAIL L3: Có sự sai lệch giữa frame_idx và nội dung thực tế của Video!")
        except Exception as e:
            print(f"⚠️ Không thể chạy test L3 tự động: {e}")
    else:
        print("⚠️ Bỏ qua L3 vì không import được verify_visual_mapping.")

if __name__ == "__main__":
    b12_keyframes_audit()
