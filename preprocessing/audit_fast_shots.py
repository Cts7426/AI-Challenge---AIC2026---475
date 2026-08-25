"""
B0.5 — Audit Fast Shots & Densification (Dành riêng cho Windows 3050)

Quét các shot ngắn (<1.5s) hoặc có độ biến thiên cao (dự định nâng cấp sau).
Do 1fps có thể bỏ lỡ khoảnh khắc quan trọng trong các shot giật cục (fast action),
script này sẽ gọi ffmpeg trích xuất thêm khung hình ở mức 5fps cho riêng các shot đó.

Đầu ra:
- data/derived/extra_keyframes/<video_id>/e<frame_idx:07d>.jpg
- data/derived/extra_frames_parts/<video_id>.parquet
Các file này sẽ làm đầu vào cho `incremental_load_clip.py` và VLM.
"""

import argparse
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import psutil
import yaml
import numpy as np

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT_DIR / "data" / "config" / "config.yaml"
DERIVED_DIR = ROOT_DIR / "data" / "derived"
VIDEOS_DIR = ROOT_DIR / "data" / "raw" / "videos"
EXTRA_KEYFRAMES_DIR = DERIVED_DIR / "extra_keyframes"
EXTRA_PARTS_DIR = DERIVED_DIR / "extra_frames_parts"

def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def _extract_chunk(video_path: str, frame_idxs: list[int], tmp_dir: Path,
                   long_edge_px: int, chunk_no: int) -> dict[int, Path]:
    select_expr = "+".join(f"eq(n\\,{i})" for i in frame_idxs)
    scale_expr = f"if(gt(iw\\,ih)\\,{long_edge_px}\\,-2):if(gt(iw\\,ih)\\,-2\\,{long_edge_px})"
    out_pattern = str(tmp_dir / f"c{chunk_no:03d}_%08d.png")

    cmd = [
        "ffmpeg", "-y", "-nostdin", "-loglevel", "error",
        "-i", video_path,
        "-vf", f"select='{select_expr}',scale={scale_expr}",
        "-vsync", "0",
        out_pattern,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    outputs = sorted(tmp_dir.glob(f"c{chunk_no:03d}_*.png"))
    if len(outputs) != len(frame_idxs):
        raise RuntimeError(f"Lỗi ffmpeg trích xuất batch {chunk_no} cho {video_path}: {r.stderr[-500:]}")
    return dict(zip(frame_idxs, outputs))

def resize_and_save_jpeg(png_path: Path, dest_path: Path, quality: int):
    from PIL import Image
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(png_path) as im:
        im.convert("RGB").save(dest_path, "JPEG", quality=quality)

def process_single_video(video_id: str, video_path: str, fps: float, n_frames: int,
                         shots_video: pd.DataFrame, cfg: dict):
    kc = cfg["keyframe_extraction"]
    quality = int(kc["jpeg_quality"])
    long_edge = int(kc["long_edge_px"])

    # Chỉ lấy các shot có độ dài < 1.5s
    fast_shots = shots_video[(shots_video['end_frame'] - shots_video['start_frame']) / fps < 1.5]
    if fast_shots.empty:
        return pd.DataFrame(), 0

    targets = []
    # Khai thác 5fps cho các fast shots
    step_5fps = max(1, int(round(fps / 5)))
    
    for row in fast_shots.itertuples():
        start, end = int(row.start_frame), int(row.end_frame)
        idxs = list(range(start, end + 1, step_5fps))
        for idx in idxs:
            idx = min(max(idx, 0), n_frames - 1)
            targets.append(idx)
            
    targets = sorted(list(set(targets))) # Remove duplicates
    
    video_dir = EXTRA_KEYFRAMES_DIR / video_id
    missing = [idx for idx in targets if not (video_dir / f"e{idx:07d}.jpg").exists()]

    if missing:
        tmp_dir = video_dir.parent / f".tmp_{video_id}"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        try:
            for i in range(0, len(missing), 90):
                batch = missing[i:i+90]
                png_by_idx = _extract_chunk(video_path, batch, tmp_dir, long_edge, i//90)
                for idx in batch:
                    resize_and_save_jpeg(png_by_idx[idx], video_dir / f"e{idx:07d}.jpg", quality)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    rows = [{
        "video_id": video_id,
        "frame_idx": idx,
        "path": f"extra_keyframes/{video_id}/e{idx:07d}.jpg"
    } for idx in targets]
    
    df = pd.DataFrame(rows)
    EXTRA_PARTS_DIR.mkdir(parents=True, exist_ok=True)
    if not df.empty:
        df.to_parquet(EXTRA_PARTS_DIR / f"{video_id}.parquet", index=False)
        
    return df, len(missing)

def main():
    EXTRA_PARTS_DIR.mkdir(parents=True, exist_ok=True)
    EXTRA_KEYFRAMES_DIR.mkdir(parents=True, exist_ok=True)
    
    cfg = load_config()
    df_vi = pd.read_parquet(DERIVED_DIR / "video_info.parquet")
    info = {r["video_id"]: r for r in df_vi.to_dict("records")}

    df_shots = pd.read_parquet(DERIVED_DIR / "shots.parquet")
    shots_by_video = {vid: g for vid, g in df_shots.groupby("video_id")}

    files = {p.stem: p for p in VIDEOS_DIR.rglob("*.mp4")}
    videos = sorted(files.keys())

    print(f"Bắt đầu quét {len(videos)} video tìm cảnh quay nhanh (<1.5s)...")
    
    total_extra = 0
    total_new = 0
    
    for i, vid in enumerate(videos, 1):
        if (EXTRA_PARTS_DIR / f"{vid}.parquet").exists():
            continue
            
        row = info.get(vid)
        if not row or int(row.get("n_frames", 0)) <= 0:
            continue
            
        shots_video = shots_by_video.get(vid)
        if shots_video is None or shots_video.empty:
            continue
            
        fps = float(row["fps_num"]) / float(row["fps_den"])
        n_frames = int(row["n_frames"])
        
        try:
            df, n_new = process_single_video(vid, str(files[vid]), fps, n_frames, shots_video, cfg)
            if not df.empty:
                print(f"[{i}/{len(videos)}] {vid}: Phát hiện {len(df)} extra frames (Trích xuất mới: {n_new})")
                total_extra += len(df)
                total_new += n_new
        except Exception as e:
            print(f"❌ Lỗi {vid}: {e}", file=sys.stderr)

    print(f"\n✅ HOÀN THÀNH. Tổng extra frames toàn tập: {total_extra} (Trích mới: {total_new})")

if __name__ == "__main__":
    main()
