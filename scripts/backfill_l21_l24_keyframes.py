import os
import sys
from pathlib import Path
import pandas as pd
import numpy as np
from PIL import Image
from tqdm import tqdm

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
DERIVED_DIR = DATA_DIR / "derived"
RAW_BTC_KF_DIR = DATA_DIR / "raw" / "btc" / "keyframes"
KEYFRAMES_OUT_DIR = DERIVED_DIR / "keyframes"

# Pre-index all BTC keyframe files once for O(1) instant lookup!
def build_btc_file_index():
    print("Indexing BTC keyframe files...")
    file_map = {}
    for p in RAW_BTC_KF_DIR.rglob("*.jpg"):
        vid = p.parent.name
        try:
            ord_idx = int(p.stem)
            file_map[(vid, ord_idx)] = p
        except ValueError:
            pass
    print(f"Indexed {len(file_map):,} BTC keyframe files.")
    return file_map

def resize_and_save(img_path: Path, out_path: Path, max_edge: int = 448, quality: int = 90):
    """Resize cạnh dài nhất về 448px và lưu ảnh JPEG quality 90."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.open(img_path).convert("RGB")
    w, h = img.size
    if max(w, h) > max_edge:
        if w > h:
            new_w = max_edge
            new_h = int(h * max_edge / w)
        else:
            new_h = max_edge
            new_w = int(w * max_edge / h)
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    img.save(out_path, format="JPEG", quality=quality)

def process_missing_video_fast(vid: str, df_shots_vid: pd.DataFrame, df_fm_vid: pd.DataFrame, file_map: dict):
    """Xử lý siêu tốc 1 FPS keyframes dùng BTC keyframe files + frame_map."""
    out_vid_dir = KEYFRAMES_OUT_DIR / vid
    if df_fm_vid is None or df_fm_vid.empty:
        return 0

    df_fm_vid = df_fm_vid.sort_values("frame_idx")
    fm_frames = df_fm_vid["frame_idx"].values
    fm_ords = df_fm_vid["btc_ordinal"].values
    fps = df_fm_vid["fps"].iloc[0] if "fps" in df_fm_vid.columns else 25.0

    saved_count = 0
    for row in df_shots_vid.itertuples():
        start_f = row.start_frame
        end_f = row.end_frame
        length_f = end_f - start_f
        num_seconds = length_f / fps
        num_samples = max(2, min(20, int(round(num_seconds))))

        if num_samples <= 2:
            samples = [start_f + int(length_f * 0.25), start_f + int(length_f * 0.75)]
        else:
            step = length_f / num_samples
            samples = [start_f + int(step * (i + 0.5)) for i in range(num_samples)]

        for target_f in samples:
            # Tìm BTC frame gần nhất trong frame_map
            idx = np.argmin(np.abs(fm_frames - target_f))
            btc_ord = fm_ords[idx]
            actual_f = fm_frames[idx]

            btc_img_path = file_map.get((vid, btc_ord))
            if btc_img_path and btc_img_path.exists():
                out_path = out_vid_dir / f"f{actual_f:07d}.jpg"
                if not out_path.exists():
                    resize_and_save(btc_img_path, out_path)
                    saved_count += 1
    return saved_count

def main():
    print("==================================================")
    print("BẮT ĐẦU SIÊU TỐC BACKFILL KEYFRAMES DÙNG BTC FILES")
    print("==================================================")

    df_info = pd.read_parquet(DERIVED_DIR / "video_info.parquet")
    df_shots = pd.read_parquet(DERIVED_DIR / "shots.parquet")
    df_fm = pd.read_parquet(DERIVED_DIR / "frame_map.parquet")

    existing_dirs = {d.name for d in KEYFRAMES_OUT_DIR.iterdir() if d.is_dir()} if KEYFRAMES_OUT_DIR.exists() else set()
    all_vids = set(df_info["video_id"])
    missing_vids = sorted(list(all_vids - existing_dirs))

    print(f"Tổng số video trong video_info: {len(all_vids)}")
    print(f"Số video đã có keyframes: {len(existing_dirs)}")
    print(f"Số video BỊ THIẾU cần bổ sung: {len(missing_vids)}")

    if not missing_vids:
        print("✅ Tất cả 873 video đã có keyframes! Không cần backfill.")
        return

    file_map = build_btc_file_index()

    total_new_imgs = 0
    shots_gb = df_shots.groupby("video_id")
    fm_gb = df_fm.groupby("video_id")

    for vid in tqdm(missing_vids, desc="Fast Backfill Keyframes"):
        df_shots_vid = shots_gb.get_group(vid) if vid in shots_gb.groups else pd.DataFrame()
        df_fm_vid = fm_gb.get_group(vid) if vid in fm_gb.groups else pd.DataFrame()

        if df_shots_vid.empty:
            continue

        saved = process_missing_video_fast(vid, df_shots_vid, df_fm_vid, file_map)
        total_new_imgs += saved

    print(f"\n✅ Hoàn tất siêu tốc! Đã tạo bổ sung {total_new_imgs:,} ảnh keyframe mới.")
    num_dirs = len([d for d in KEYFRAMES_OUT_DIR.iterdir() if d.is_dir()])
    print(f"Thư mục keyframes hiện có: {num_dirs}/873 video")

if __name__ == "__main__":
    main()
