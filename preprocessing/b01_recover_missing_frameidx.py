import pandas as pd
import numpy as np
import cv2
import glob
from pathlib import Path
import os
import tqdm

def get_mp4_path(vid):
    paths = glob.glob(f"data/raw/videos/videos_*/{vid}.mp4")
    return Path(paths[0]) if paths else None

def get_kf_path(vid, ord_idx):
    paths = glob.glob(f"data/raw/btc/keyframes/keyframes_*/{vid}/{ord_idx:04d}.jpg")
    if not paths:
        paths = glob.glob(f"data/raw/btc/keyframes/keyframes_*/{vid}/{ord_idx:03d}.jpg")
    return Path(paths[0]) if paths else None

def recover_video(vid, vid_df, mp4_path):
    """
    Recover missing frame indices for a single video.
    vid_df must contain 'frame_idx_raw' and 'frame_idx_corrected'
    """
    # Create copies of required columns if not exists
    if "frame_idx_recovered" not in vid_df.columns:
        vid_df["frame_idx_recovered"] = pd.NA
        vid_df["frame_idx_status"] = "ok"
        vid_df["match_run_length"] = pd.NA
        vid_df["recovery_confidence"] = pd.NA
        vid_df["cosine"] = pd.NA
        
    deltas = vid_df["frame_idx_raw"].diff().fillna(-1)
    err_indices = np.where(deltas == 0)[0]
    
    if len(err_indices) == 0:
        return vid_df, 0, 0, 0
        
    unverified_count = 0
    if not mp4_path:
        for ei in err_indices:
            vid_df.iat[ei, vid_df.columns.get_loc("frame_idx_status")] = "unverified"
            unverified_count += 1
        return vid_df, 0, 0, unverified_count
        
    cap = cv2.VideoCapture(str(mp4_path))
    n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    blocks = []
    curr_block = []
    for ei in err_indices:
        if not curr_block or ei == curr_block[-1] + 1:
            curr_block.append(ei)
        else:
            blocks.append(curr_block)
            curr_block = [ei]
    if curr_block:
        blocks.append(curr_block)
        
    recovered_count = 0
    unrecoverable_count = 0
    
    for block in blocks:
        first_err = block[0]
        last_err = block[-1]
        
        lo = 0
        if first_err > 0:
            lo_val = vid_df.iloc[first_err - 1]["frame_idx_corrected"]
            lo = lo_val if pd.notna(lo_val) else vid_df.iloc[first_err - 1]["frame_idx_raw"]
            
        hi = n_frames - 1
        if last_err < len(vid_df) - 1:
            hi_val = vid_df.iloc[last_err + 1]["frame_idx_corrected"]
            hi = hi_val if pd.notna(hi_val) else vid_df.iloc[last_err + 1]["frame_idx_raw"]
            
        start_f = int(lo) + 1
        end_f = int(hi) - 1
        
        if start_f > end_f:
            for ei in block:
                vid_df.iat[ei, vid_df.columns.get_loc("frame_idx_status")] = "unrecoverable"
                unrecoverable_count += 1
            continue
            
        frames = []
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_f)
        for i in range(start_f, end_f + 1):
            ret, frame = cap.read()
            if not ret: break
            frames.append((i, frame))
            
        curr_start_idx = 0
        for ei in block:
            ord_val = vid_df.iloc[ei]["btc_kf_ordinal"]
            kf_path = get_kf_path(vid, ord_val)
            if not kf_path:
                vid_df.iat[ei, vid_df.columns.get_loc("frame_idx_status")] = "unrecoverable"
                unrecoverable_count += 1
                continue
                
            kf_img = cv2.imread(str(kf_path))
            
            found_idx = -1
            best_mse = None
            match_run = 0
            in_run = False
            
            for fi in range(curr_start_idx, len(frames)):
                f_idx, frame = frames[fi]
                f_resized = cv2.resize(frame, (kf_img.shape[1], kf_img.shape[0]))
                mse = np.mean((f_resized.astype(np.float32) - kf_img.astype(np.float32)) ** 2)
                
                if mse < 20:
                    if not in_run:
                        found_idx = fi
                        best_mse = mse
                        match_run = 1
                        in_run = True
                    else:
                        match_run += 1
                else:
                    if in_run:
                        break
                        
            if found_idx != -1:
                vid_df.iat[ei, vid_df.columns.get_loc("frame_idx_recovered")] = frames[found_idx][0]
                vid_df.iat[ei, vid_df.columns.get_loc("frame_idx_status")] = "recovered"
                vid_df.iat[ei, vid_df.columns.get_loc("match_run_length")] = match_run
                
                conf = "high" if match_run <= 3 else "medium" if match_run <= 15 else "low"
                vid_df.iat[ei, vid_df.columns.get_loc("recovery_confidence")] = conf
                
                recovered_count += 1
                curr_start_idx = found_idx + 1
            else:
                vid_df.iat[ei, vid_df.columns.get_loc("frame_idx_status")] = "unrecoverable"
                unrecoverable_count += 1
                
    cap.release()
    
    # Update frame_idx_corrected
    rec_mask = vid_df["frame_idx_recovered"].notna()
    if rec_mask.any():
        vid_df.loc[rec_mask, "frame_idx_corrected"] = vid_df.loc[rec_mask, "frame_idx_recovered"]
        
    return vid_df, recovered_count, unrecoverable_count, unverified_count

def recover_missing_frameidx():
    
    df = pd.read_parquet("data/derived/frame_map.parquet")
    if "frame_idx_raw" not in df.columns:
        df.rename(columns={"frame_idx": "frame_idx_raw"}, inplace=True)
        
    df = df.sort_values(["video_id", "btc_kf_ordinal"]).reset_index(drop=True)
    
    if "frame_idx_recovered" not in df.columns:
        df["frame_idx_recovered"] = pd.NA
        df["frame_idx_status"] = "ok"
        df["match_run_length"] = pd.NA
        df["recovery_confidence"] = pd.NA
        df["cosine"] = pd.NA
        
    df["frame_idx_corrected"] = df["frame_idx_raw"]
    if "kf_offset" in df.columns:
        offset_mask = df["kf_offset"].notna()
        df.loc[offset_mask, "frame_idx_corrected"] = df.loc[offset_mask, "frame_idx_raw"] + df.loc[offset_mask, "kf_offset"]
        
    vids = df["video_id"].unique()
    
    recovered_count = 0
    unrecoverable_count = 0
    unverified_count = 0
    
    print("Scanning videos for recovery...")
    dfs = []
    
    for vid in tqdm.tqdm(vids):
        mask = df["video_id"] == vid
        vid_df = df.loc[mask].copy()
        
        mp4_path = get_mp4_path(vid)
        vid_df, rc, uc, uv = recover_video(vid, vid_df, mp4_path)
        
        recovered_count += rc
        unrecoverable_count += uc
        unverified_count += uv
        dfs.append(vid_df)
        
    df = pd.concat(dfs).sort_values(["video_id", "btc_kf_ordinal"]).reset_index(drop=True)
        
    print(f"\nResults: Recovered: {recovered_count}, Unrecoverable: {unrecoverable_count}, Unverified: {unverified_count}")
    
    # Assert monotonic
    df = df.sort_values(["video_id", "btc_kf_ordinal"]).reset_index(drop=True)
    df["delta_corr"] = df.groupby("video_id")["frame_idx_corrected"].diff()
    violators = df[(df["delta_corr"] <= 0) & (df["frame_idx_status"] != "unverified")]
    
    if len(violators) > 0:
        print("WARNING: Monotonicity violated in frame_idx_corrected for verified videos!")
        print(violators[["video_id", "btc_kf_ordinal", "frame_idx_raw", "frame_idx_corrected", "delta_corr", "frame_idx_status"]].to_string())
    else:
        print("SUCCESS: Monotonicity holds for all verified videos.")
        
    print("\nRecovery confidence distribution:")
    print(df["recovery_confidence"].value_counts(dropna=False).to_string())
        
    df.drop(columns=["delta_corr"], inplace=True)
    df.to_parquet("data/derived/frame_map.parquet")
    print("Updated data/derived/frame_map.parquet")

if __name__ == '__main__':
    recover_missing_frameidx()
