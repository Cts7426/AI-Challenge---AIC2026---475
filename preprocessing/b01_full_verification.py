import argparse
import collections
import gc
import multiprocessing
import os
import sys
import time
from pathlib import Path

import cv2
import pandas as pd
import numpy as np

import subprocess

def get_free_memory_gb():
    try:
        vm = subprocess.check_output(['vm_stat']).decode()
        pagesize_out = subprocess.check_output(['sysctl', '-n', 'hw.pagesize']).decode()
        pagesize = int(pagesize_out.strip())
        
        free_pages = 0
        inactive_pages = 0
        for line in vm.split('\n'):
            if 'Pages free:' in line:
                free_pages = int(line.split(':')[1].strip().strip('.'))
            elif 'Pages inactive:' in line:
                inactive_pages = int(line.split(':')[1].strip().strip('.'))
        return (free_pages + inactive_pages) * pagesize / (1024**3)
    except Exception:
        return 10.0

DATA_DIR = Path("data")
RAW_DIR = DATA_DIR / "raw"
VIDEOS_DIR = RAW_DIR / "videos"
DERIVED_DIR = DATA_DIR / "derived"
FRAME_MAP_PATH = DERIVED_DIR / "frame_map.parquet"
VIDEO_INFO_PATH = DERIVED_DIR / "video_info.parquet"
PARTS_DIR = DERIVED_DIR / "full_verification_parts"

def find_btc_keyframe_path(video_id, kf_ord):
    prefix = video_id[:3]
    candidates = [
        RAW_DIR / "btc" / "keyframes" / f"Keyframes_{prefix}" / video_id,
        RAW_DIR / "btc" / "keyframes" / prefix / video_id,
        RAW_DIR / "btc" / "keyframes" / f"keyframes_{prefix}" / video_id,
    ]
    kf_dir = None
    for cand in candidates:
        if cand.exists():
            kf_dir = cand
            break
            
    if kf_dir is None:
        return None
        
    for pad in [3, 4, 1]:
        cand = kf_dir / f"{kf_ord:0{pad}d}.jpg"
        if cand.exists(): return cand
    return None

def process_video(video_id, df_kfs, n_frames_total):
    mp4_path = list(VIDEOS_DIR.rglob(f"{video_id}.mp4"))
    if not mp4_path:
        return [], False
    mp4_path = mp4_path[0]
    
    df_kfs = df_kfs.sort_values("frame_idx_raw").copy()
    target_kfs = df_kfs.to_dict('records')
    if not target_kfs:
        return [], False
        
    cap = cv2.VideoCapture(str(mp4_path))
    frame_count = 0
    kf_idx = 0
    
    q = collections.deque(maxlen=7)
    results = []
    
    min_frame = target_kfs[0]["frame_idx_raw"]
    if min_frame > 0:
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, min_frame - 60))
        frame_count = int(cap.get(cv2.CAP_PROP_POS_FRAMES))

    frames_since_jump = 999
    consecutive_fails = 0
    skipped_frames_total = 0
    
    duplicate_frames_count = 0
    total_valid_frames = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            consecutive_fails += 1
            if consecutive_fails > 30 or frame_count >= n_frames_total:
                break
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_count + 1)
            frame_count += 1
            frames_since_jump = 0
            skipped_frames_total += 1
            
            # Read 30 dummy frames to let decoder stabilize
            for _ in range(30):
                ret2, _ = cap.read()
                frame_count += 1
                if not ret2:
                    break
            
            continue
            
        consecutive_fails = 0
        frames_since_jump += 1
        total_valid_frames += 1
            
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        h, w = frame_rgb.shape[:2]
        new_w = 320
        new_h = int(h * (new_w / w))
        frame_320 = cv2.resize(frame_rgb, (new_w, new_h))
        
        # Check duplicate frame (MSE < 1.0)
        if len(q) >= 1:
            prev_f = q[-1][1]
            if prev_f.shape == frame_320.shape:
                mse_adj = np.mean((prev_f.astype(float) - frame_320.astype(float)) ** 2)
                if mse_adj < 1.0:
                    duplicate_frames_count += 1
        
        q.append((frame_count, frame_320, frame_rgb))
        
        while kf_idx < len(target_kfs) and frame_count == target_kfs[kf_idx]["frame_idx_raw"] + 3:
            target_idx = target_kfs[kf_idx]["frame_idx_raw"]
            ord_val = target_kfs[kf_idx]["btc_kf_ordinal"]
            
            img_path = find_btc_keyframe_path(video_id, ord_val)
            if img_path:
                btc_img = cv2.imread(str(img_path))
                if btc_img is not None:
                    btc_img_rgb = cv2.cvtColor(btc_img, cv2.COLOR_BGR2RGB)
                    btc_320 = cv2.resize(btc_img_rgb, (new_w, new_h))
                    
                    mses_320 = {}
                    for f_idx, f_320, _ in q:
                        if f_320.shape != btc_320.shape:
                            f_resized = cv2.resize(f_320, (btc_320.shape[1], btc_320.shape[0]))
                        else:
                            f_resized = f_320
                        mse = np.mean((btc_320.astype(float) - f_resized.astype(float)) ** 2)
                        mses_320[f_idx - target_idx] = mse
                        
                    for offset in range(-3, 4):
                        if offset not in mses_320:
                            mses_320[offset] = float('inf')
                    
                    best_offset = min(mses_320, key=mses_320.get)
                    mse_best = mses_320[best_offset]
                    
                    runner_ups = [mses_320[off] for off in mses_320 if off != best_offset]
                    mse_second = min(runner_ups) if runner_ups else float('inf')
                    ratio = (mse_second / mse_best) if mse_best > 0 else float('inf')
                    
                    if mse_best >= 50:
                        verdict = "no_match"
                    elif ratio > 10:
                        verdict = "match" if best_offset == 0 else "shifted"
                    elif ratio > 3:
                        verdict = "weak_match" if best_offset == 0 else "weak_shifted"
                    else:
                        verdict = "static_ambiguous"
                        
                    mse_best_fullres = None
                    best_offset_fullres = None
                    
                    if verdict == "no_match" or verdict.startswith("weak_"):
                        mses_full = {}
                        for f_idx, _, f_full in q:
                            if f_full.shape != btc_img_rgb.shape:
                                f_resized = cv2.resize(f_full, (btc_img_rgb.shape[1], btc_img_rgb.shape[0]))
                            else:
                                f_resized = f_full
                            mse = np.mean((btc_img_rgb.astype(float) - f_resized.astype(float)) ** 2)
                            mses_full[f_idx - target_idx] = mse
                            
                        for offset in range(-3, 4):
                            if offset not in mses_full:
                                mses_full[offset] = float('inf')
                                
                        best_offset_fullres = min(mses_full, key=mses_full.get)
                        mse_best_fullres = mses_full[best_offset_fullres]
                        
                    is_after_jump = frames_since_jump <= 30
                        
                    results.append({
                        "kf_id": f"{video_id}#k{ord_val:04d}",
                        "video_id": video_id,
                        "btc_kf_ordinal": ord_val,
                        "frame_idx_raw": target_idx,
                        "frame_idx_used": target_idx + best_offset,
                        "mse_at_minus3": mses_320[-3],
                        "mse_at_minus2": mses_320[-2],
                        "mse_at_minus1": mses_320[-1],
                        "mse_at_0": mses_320[0],
                        "mse_at_plus1": mses_320[1],
                        "mse_at_plus2": mses_320[2],
                        "mse_at_plus3": mses_320[3],
                        "best_offset": best_offset,
                        "mse_best": mse_best,
                        "mse_ratio": ratio,
                        "verdict": verdict,
                        "best_offset_fullres": best_offset_fullres,
                        "mse_best_fullres": mse_best_fullres,
                        "is_after_jump": is_after_jump,
                        "skipped_frames_total": skipped_frames_total
                    })
                    del btc_img, btc_img_rgb, btc_320
            kf_idx += 1
            
        # Catch up if frame_count went way past (e.g., after jump + 30 skip)
        while kf_idx < len(target_kfs) and frame_count > target_kfs[kf_idx]["frame_idx_raw"] + 3:
            ord_val = target_kfs[kf_idx]["btc_kf_ordinal"]
            target_idx = target_kfs[kf_idx]["frame_idx_raw"]
            results.append({
                "kf_id": f"{video_id}#k{ord_val:04d}",
                "video_id": video_id,
                "btc_kf_ordinal": ord_val,
                "frame_idx_raw": target_idx,
                "frame_idx_used": -1,
                "best_offset": 0,
                "mse_best": float('inf'),
                "mse_ratio": 1.0,
                "verdict": "skipped_due_to_jump",
                "is_after_jump": True,
                "skipped_frames_total": skipped_frames_total
            })
            kf_idx += 1
            
        if kf_idx >= len(target_kfs):
            break
            
        frame_count += 1
        
    cap.release()
    del q
    gc.collect()
    
    has_duplicate_frames = False
    if total_valid_frames > 0:
        if (duplicate_frames_count / total_valid_frames) > 0.3:
            has_duplicate_frames = True
    
    return results, has_duplicate_frames

def worker_init(df_map_dump, df_info_dump):
    global df_map
    global df_info
    df_map = df_map_dump
    df_info = df_info_dump

def worker(video_id):
    df_kfs = df_map[df_map["video_id"] == video_id]
    n_frames_total = df_info[df_info["video_id"] == video_id]["n_frames"].iloc[0] if video_id in df_info["video_id"].values else 999999
    
    results, has_dup = process_video(video_id, df_kfs, n_frames_total)
    
    if results:
        df_res = pd.DataFrame(results)
        df_res["has_duplicate_frames"] = has_dup
        part_path = PARTS_DIR / f"{video_id}.parquet"
        df_res.to_parquet(part_path, index=False)
        
    return video_id

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=1, help="Number of workers")
    args = parser.parse_args()
    
    if args.workers > 1:
        print(f"WARNING: Running with {args.workers} workers. Expected RAM usage: ~{args.workers * 400} MB.")
    if args.workers > 8:
        print("WARNING: Capping workers to 8.")
        args.workers = 8
        
    PARTS_DIR.mkdir(parents=True, exist_ok=True)
    
    df_map = pd.read_parquet(FRAME_MAP_PATH)
    if "frame_idx_raw" not in df_map.columns and "frame_idx" in df_map.columns:
        df_map = df_map.rename(columns={"frame_idx": "frame_idx_raw"})
        
    df_info = pd.read_parquet(VIDEO_INFO_PATH)
        
    all_videos = list(df_map["video_id"].unique())
    
    existing_parts = set([f.stem for f in PARTS_DIR.glob("*.parquet")])
    videos = [v for v in all_videos if v not in existing_parts]
    
    print(f"Found {len(existing_parts)} already processed parts. Starting verification for {len(videos)} videos...")
    
    start_time = time.time()
    processed = 0
    
    if args.workers > 1:
        with multiprocessing.Pool(processes=args.workers, initializer=worker_init, initargs=(df_map, df_info)) as pool:
            for i, vid in enumerate(pool.imap_unordered(worker, videos)):
                processed += 1
                elapsed = time.time() - start_time
                eta = (elapsed / processed) * (len(videos) - processed)
                free_gb = get_free_memory_gb()
                print(f"[{processed}/{len(videos)}] {vid} done. Elapsed: {elapsed:.1f}s, ETA: {eta:.1f}s, Free RAM: {free_gb:.1f}GB")
    else:
        worker_init(df_map, df_info)
        for i, vid in enumerate(videos):
            worker(vid)
            processed += 1
            elapsed = time.time() - start_time
            eta = (elapsed / processed) * (len(videos) - processed)
            free_gb = get_free_memory_gb()
            print(f"[{processed}/{len(videos)}] {vid} done. Elapsed: {elapsed:.1f}s, ETA: {eta:.1f}s, Free RAM: {free_gb:.1f}GB")

    print("All videos processed successfully.")
    print("Please run b01_merge_verification.py to merge all parts.")

if __name__ == "__main__":
    main()
