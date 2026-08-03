import pandas as pd
from pathlib import Path

DATA_DIR = Path("data")
FRAME_MAP = DATA_DIR / "derived/frame_map.parquet"
VERIF_RES = DATA_DIR / "derived/full_verification.parquet"

def update_frame_map():
    df_map = pd.read_parquet(FRAME_MAP)
    df_verif = pd.read_parquet(VERIF_RES)
    
    # Check if frame_idx_raw exists
    col = "frame_idx_raw" if "frame_idx_raw" in df_map.columns else "frame_idx"
    if col == "frame_idx":
        df_map = df_map.rename(columns={"frame_idx": "frame_idx_raw"})
        
    # Merge verification results
    df_verif = df_verif[["video_id", "btc_kf_ordinal", "best_offset", "verdict", "is_after_jump"]]
    
    # To determine dominant offset for static_ambiguous
    dominant_offsets = df_verif[df_verif["verdict"] != "static_ambiguous"].groupby("video_id")["best_offset"].agg(lambda x: x.mode()[0] if not x.empty else 0).to_dict()
    
    # Fallback to 0 if no clear mode
    
    df_merge = df_map.merge(df_verif, on=["video_id", "btc_kf_ordinal"], how="left")
    
    def calculate_kf_offset(row):
        verdict = row["verdict"]
        if pd.isna(verdict) or verdict == "skipped_due_to_jump":
            return 0
        if verdict == "static_ambiguous":
            return dominant_offsets.get(row["video_id"], 0)
        return int(row["best_offset"])
        
    df_merge["kf_offset"] = df_merge.apply(calculate_kf_offset, axis=1)
    df_merge["offset_verified"] = ~df_merge["verdict"].isna()
    df_merge["frame_idx_corrected"] = df_merge["frame_idx_raw"] + df_merge["kf_offset"]
    
    # Assert monotonic
    df_merge = df_merge.sort_values(["video_id", "btc_kf_ordinal"])
    df_merge["prev_corrected"] = df_merge.groupby("video_id")["frame_idx_corrected"].shift(1)
    
    bad = df_merge[df_merge["frame_idx_corrected"] < df_merge["prev_corrected"]]
    if len(bad) > 0:
        print("WARNING: frame_idx_corrected is NOT monotonic for the following:")
        print(bad[["video_id", "btc_kf_ordinal", "frame_idx_raw", "frame_idx_corrected", "prev_corrected", "kf_offset"]].head(20))
    else:
        print("SUCCESS: frame_idx_corrected is strictly monotonic across all videos.")
        
    # Clean up temporary merge columns
    df_merge = df_merge.drop(columns=["best_offset", "verdict", "is_after_jump", "prev_corrected"])
    
    df_merge.to_parquet(FRAME_MAP, index=False)
    print("frame_map.parquet updated successfully.")

if __name__ == "__main__":
    update_frame_map()
