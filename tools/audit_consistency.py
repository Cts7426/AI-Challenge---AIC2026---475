import json
from pathlib import Path
import pandas as pd
from backend.indexing.frame_map import load_frame_map

ROOT = Path(r"C:\dev\aic2026")
KF_DIR = ROOT / "data" / "derived" / "keyframes"

shots = pd.read_parquet(ROOT / "data/derived/shots.parquet")

fm = load_frame_map()
frame_map = {}
for k, v in fm.items():
    vid = k[:8]
    frame_map.setdefault(vid, []).append(v)
for v in frame_map.values():
    v.sort()

# 1) frame_map vs disk: how many keys do NOT contain the actual file?
on_disk = {p.parent.name: {int(f.stem[1:]) for f in p.parent.glob("f*.jpg")} 
           for p in KF_DIR.glob("*/f*.jpg")}

missing_by_video = {}
for vid, frames in frame_map.items(): 
    have = on_disk.get(vid, set()) 
    miss = [f for f in frames if f not in have] 
    if miss: 
        missing_by_video[vid] = (len(miss), len(frames))
        
print(f"[1] video has missing frame_map: {len(missing_by_video)}/{len(frame_map)}")
for vid, (m, t) in list(missing_by_video.items())[:10]: 
    print(f"  {vid}: missing {m}/{t}")

#2) shots.parquet vs frame_map
vids_shots = set(shots["video_id"].unique())
vids_map = set(frame_map.keys())
print(f"\n[2] videos are in frame_map but NOT shots: {sorted(vids_map - vids_shots)[:10]}")
print(f" videos are in shots but NOT in frame_map: {sorted(vids_shots - vids_map)[:10]}")

#3) What frame is outside each shot of the video itself?
orphan = {}
for vid in sorted(vids_map & vids_shots): 
    s = shots[shots["video_id"] == vid] 
    lo, hi = s["start_frame"].values, s["end_frame"].values 
    out = [f for f in frame_map[vid] if not ((lo <= f) & (f <= hi)).any()] 
    if out: 
        orphan[vid] = (len(out), out[:5])
        
print(f"\n[3] video has frame to watch (no shots included): {len(orphan)}")
for vid, (n, sample) in list(orphan.items())[:10]: 
    print(f"  {vid}: {n} frame, eg {sample}")
