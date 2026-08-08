import os
import sys
from pathlib import Path
import pandas as pd
import numpy as np

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
DERIVED_DIR = DATA_DIR / "derived"

def main():
    print("==================================================")
    print("XÂY DỰNG BẢNG ÁNH XẠ CLIP VECTOR WITH TOLERANCE")
    print("==================================================")
    
    df_kf = pd.read_parquet(DERIVED_DIR / "keyframes.parquet")
    df_clip = pd.read_parquet(DERIVED_DIR / "clip_row_index.parquet")
    
    print(f"Tổng số Keyframes (1 FPS):         {len(df_kf):,}")
    print(f"Tổng số CLIP entries (BTC format): {len(df_clip):,}")
    
    df_kf["video_id"] = df_kf["video_id"].astype(str)
    df_clip["video_id"] = df_clip["video_id"].astype(str)
    
    # 1. Thử Inner Join chính xác 100% theo (video_id, frame_idx)
    exact_merged = df_kf.merge(
        df_clip[["video_id", "frame_idx", "kf_id"]].rename(columns={"kf_id": "clip_kf_id"}),
        on=["video_id", "frame_idx"],
        how="inner"
    )
    print(f"Khớp chính xác (Exact match):       {len(exact_merged):,} keyframes")
    
    # 2. Với các keyframe chưa khớp chính xác -> merge_asof theo nearest frame với tolerance <= 25 frames (~1s)
    df_kf_sorted = df_kf.sort_values("frame_idx").reset_index(drop=True)
    df_clip_sorted = df_clip[["video_id", "frame_idx", "kf_id"]].rename(columns={"kf_id": "clip_kf_id", "frame_idx": "clip_frame_idx"}).sort_values("clip_frame_idx").reset_index(drop=True)
    
    df_mapped = pd.merge_asof(
        df_kf_sorted,
        df_clip_sorted,
        left_on="frame_idx",
        right_on="clip_frame_idx",
        by="video_id",
        direction="nearest",
        tolerance=25
    )
    
    matched_count = df_mapped["clip_kf_id"].notna().sum()
    print(f"Khớp qua Nearest Neighbor (<=25f): {matched_count:,} / {len(df_kf):,} keyframes ({matched_count/len(df_kf)*100:.1f}%)")
    
    # Đóng gói file clip_kf_map.parquet
    df_out = df_mapped[["kf_id", "video_id", "frame_idx", "shot_id", "row_id", "clip_kf_id", "clip_frame_idx"]]
    df_out["frame_drift"] = (df_out["frame_idx"] - df_out["clip_frame_idx"]).abs()
    
    out_path = DERIVED_DIR / "clip_kf_map.parquet"
    df_out.to_parquet(out_path, index=False)
    print(f"\n✅ Đã tạo bảng ánh xạ clip_kf_map.parquet tại {out_path}!")

if __name__ == "__main__":
    main()
