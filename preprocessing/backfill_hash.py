import hashlib
from pathlib import Path
import pandas as pd
from shot_job import load_config

PARTS_DIR = Path("data/derived/shots_parts")

def main():
    cfg = load_config()
    sc = cfg["shot_detection"]
    
    # Tính lại config_hash hiện tại
    thr = float(sc.get("content_threshold", 27.0))
    ds = int(sc.get("downscale_factor", 2))
    min_shot_frames = max(1, round(float(sc.get("min_shot_seconds", 0.5)) * 30))
    msl = int(sc.get("detector_min_scene_len_frames", 0)) or max(2, int(min_shot_frames * 0.4))
    min_s = float(sc.get("min_shot_seconds", 0.5))
    max_s = float(sc.get("max_shot_seconds", 60.0))
    force_s = float(sc.get("force_split_seconds", 30.0))
    
    hash_str = f"pyav|{ds}|{thr}|{msl}|{min_s}|{max_s}|{force_s}"
    config_hash = hashlib.sha256(hash_str.encode()).hexdigest()[:12]
    
    parts = list(PARTS_DIR.glob("*.parquet"))
    print(f"Đang đính kèm config_hash [{config_hash}] vào {len(parts)} file parquet...")
    
    count = 0
    for p in parts:
        df = pd.read_parquet(p)
        if "config_hash" not in df.columns or (df["config_hash"] != config_hash).any():
            df["config_hash"] = config_hash
            df.to_parquet(p, index=False)
            count += 1
            
    print(f"✅ Đã backfill xong {count}/{len(parts)} file!")

if __name__ == "__main__":
    main()
