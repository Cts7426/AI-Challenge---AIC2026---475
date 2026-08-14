"""
Audit L1 & L2 cho Task B1.1: Shot Segmentation
Mục tiêu: Đảm bảo bảng shots.parquet đúng cấu trúc và tuân thủ luật cắt cưỡng bức shot > 60s.
"""

import sys
from pathlib import Path
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT_DIR / "data"
SHOTS_FILE = DATA_DIR / "derived" / "shots.parquet"
VIDEO_INFO = DATA_DIR / "derived" / "video_info.parquet"

def b11_shots_audit():
    if not SHOTS_FILE.exists():
        print(f"❌ FAIL: Không tìm thấy {SHOTS_FILE}")
        sys.exit(1)
        
    df_shots = pd.read_parquet(SHOTS_FILE)
    df_info = pd.read_parquet(VIDEO_INFO)
    
    # 1. Kiểm tra Schema
    required_cols = {"shot_id", "video_id", "start_frame", "end_frame", "rep_kf_id"}
    missing_cols = required_cols - set(df_shots.columns)
    if missing_cols:
        print(f"❌ FAIL: Thiếu các cột bắt buộc trong shots.parquet: {missing_cols}")
        sys.exit(1)
    else:
        print("✅ PASS L1-1: Cấu trúc cột hợp lệ.")

    # Join với video_info để lấy fps
    df = df_shots.merge(df_info[["video_id", "fps_num", "fps_den"]], on="video_id", how="left")
    df["fps"] = df["fps_num"] / df["fps_den"]
    df["duration_s"] = (df["end_frame"] - df["start_frame"]) / df["fps"]

    # 2. Kiểm tra cắt cưỡng bức 60s
    long_shots = df[df["duration_s"] > 60.5] # 60.5 cho phép sai số nhỏ do làm tròn frame
    if len(long_shots) > 0:
        print(f"❌ FAIL L1-2: Có {len(long_shots)} shot dài hơn 60s chưa được cắt cưỡng bức!")
        print(long_shots[["shot_id", "start_frame", "end_frame", "duration_s"]].head(10))
        sys.exit(1)
    else:
        print("✅ PASS L1-2: Không có shot nào dài quá 60s. Luật cắt cưỡng bức hoạt động tốt.")

    # 3. Kiểm tra Rep Keyframe (L1-8 tới L1-10)
    print("\n--- KIỂM TRA L1: GÁN KEYFRAME ĐẠI DIỆN ---")
    
    # L1-8: rep_source != 'none' ⟹ start_frame <= rep_frame_idx <= end_frame
    if "rep_kf_id" in df.columns:
        valid_reps = df[df["rep_source"] != "none"]
        # Lấy rep_frame_idx từ rep_offset: rep_offset = rep_frame_idx - mid
        # => rep_frame_idx = rep_offset + mid
        mids = (valid_reps["start_frame"] + valid_reps["end_frame"]) // 2
        rep_frame_idx = valid_reps["rep_offset"] + mids
        
        out_of_bounds = valid_reps[
            (rep_frame_idx < valid_reps["start_frame"]) | 
            (rep_frame_idx > valid_reps["end_frame"])
        ]
        if len(out_of_bounds) > 0:
            print(f"❌ FAIL L1-8: Có {len(out_of_bounds)} shot gán rep_kf_id nằm NGOÀI biên shot!")
            sys.exit(1)
        else:
            print("✅ PASS L1-8: 100% rep_kf_id đều nằm TRONG biên của shot.")
            
        # L1-9: Zero orphan (Mọi rep_kf_id không null đều tồn tại trong frame_map hoặc keyframes)
        df_btc = pd.read_parquet(ROOT_DIR / "data/derived/frame_map.parquet")
        valid_kfs = set(df_btc["kf_id"])
        kf_path = ROOT_DIR / "data/derived/keyframes.parquet"
        if kf_path.exists():
            df_own = pd.read_parquet(kf_path)
            valid_kfs.update(df_own["kf_id"])
            
        orphans = valid_reps[~valid_reps["rep_kf_id"].isin(valid_kfs)]
        if len(orphans) > 0:
            print(f"❌ FAIL L1-9: Có {len(orphans)} rep_kf_id bị orphan (không tồn tại trong file gốc)!")
            sys.exit(1)
        else:
            print("✅ PASS L1-9: 100% rep_kf_id tồn tại trong kho (Zero orphan).")

        # L1-10: Số shot dùng chung một rep_kf_id = 0
        dupes = valid_reps["rep_kf_id"].duplicated().sum()
        if dupes > 0:
            print(f"❌ FAIL L1-10: Có {dupes} shot dùng chung rep_kf_id với shot khác!")
            sys.exit(1)
        else:
            print("✅ PASS L1-10: Không có shot nào chia sẻ rep_kf_id (Unique 100%).")

    # 4. Phân phối L2
    print("\n--- BÁO CÁO PHÂN PHỐI L2 ---")
    print(f"Tổng số shot: {len(df):,}")
    print(f"Thời lượng trung bình mỗi shot: {df['duration_s'].mean():.2f} giây")
    
    if "rep_source" in df.columns:
        print("\n[L2-6] Tỉ lệ rep_source:")
        counts = df["rep_source"].value_counts(normalize=True) * 100
        for k, v in counts.items():
            print(f"  - {k}: {v:.2f}%")
            
        valid_offsets = df.loc[df["rep_source"] != "none", "rep_offset"].abs()
        if not valid_offsets.empty:
            print(f"[L2-6] Phân bố rep_offset (abs): p50={valid_offsets.median():.0f} frames, p95={valid_offsets.quantile(0.95):.0f} frames")
            
        # L2-7
        none_pct = counts.get("none", 0)
        if none_pct > 2.0:
            print(f"⚠️ CẢNH BÁO L2-7: Tỉ lệ none = {none_pct:.2f}% > 2%!")
            print("  ➤ Cần kiểm tra lại content detector threshold (khả năng bị over-segmentation).")
        else:
            print(f"✅ PASS L2-7: Tỉ lệ none = {none_pct:.2f}% (Tốt).")

if __name__ == "__main__":
    b11_shots_audit()
