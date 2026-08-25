"""
B0.6 — Incremental CLIP Load (Dành riêng cho Windows 3050)

Script này quét các ảnh mới được trích xuất từ `audit_fast_shots.py` 
(trong thư mục extra_keyframes/), nhúng chúng qua model CLIP 
và nạp thẳng vào cơ sở dữ liệu vector Milvus.

Vì chạy trên Windows 3050, script tự động kích hoạt CUDA để đảm bảo tốc độ cực cao.
"""

import argparse
import sys
import time
from pathlib import Path
from datetime import datetime

import pandas as pd
import torch
from PIL import Image
import open_clip
from pymilvus import MilvusClient

# Cần add PYTHONPATH tới repo gốc nếu chạy ngoài thư mục
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

from backend.indexing.milvus_client import COLLECTION_NAME, connect
from data.config.clip_model import (
    CLIP_MODEL_NAME,
    CLIP_PRETRAINED,
)

DERIVED_DIR = ROOT_DIR / "data" / "derived"
VIDEO_INFO = DERIVED_DIR / "video_info.parquet"
EXTRA_KEYFRAMES_DIR = DERIVED_DIR / "extra_keyframes"
EXTRA_PARTS_DIR = DERIVED_DIR / "extra_frames_parts"

def _timestamp_map() -> dict[str, tuple[int, int]]:
    if not VIDEO_INFO.exists():
        return {}
    df = pd.read_parquet(VIDEO_INFO)
    return {
        str(r.video_id): (int(r.fps_num), int(r.fps_den))
        for r in df.itertuples()
    }

def main():
    ap = argparse.ArgumentParser(description="Incremental CLIP nạp các khung hình Densify.")
    args = ap.parse_args()

    if not EXTRA_KEYFRAMES_DIR.exists():
        print("Thư mục extra_keyframes/ chưa tồn tại. Vui lòng chạy audit_fast_shots.py trước.")
        return

    client = connect()
    if not client.has_collection(COLLECTION_NAME):
        print(f"Collection {COLLECTION_NAME} chưa tồn tại. Vui lòng chạy load_clip.py gốc trước.")
        return

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Đang tải CLIP model '{CLIP_MODEL_NAME}' lên {device}...")
    model, _, preprocess = open_clip.create_model_and_transforms(
        CLIP_MODEL_NAME, pretrained=CLIP_PRETRAINED
    )
    model = model.to(device)
    model.eval()

    fps_map = _timestamp_map()

    # Quét tất cả các parquet trong extra_frames_parts/
    part_files = sorted(EXTRA_PARTS_DIR.glob("*.parquet"))
    if not part_files:
        print("Không có file extra_frames_parts nào để xử lý.")
        return

    print(f"Bắt đầu xử lý CLIP embedding cho {len(part_files)} video...")

    batch_size = 256 # Batch size cho Milvus upsert
    buffer = []
    total_upserted = 0

    def flush():
        nonlocal total_upserted
        if buffer:
            client.upsert(COLLECTION_NAME, buffer)
            total_upserted += len(buffer)
            buffer.clear()

    with torch.no_grad():
        for i, part in enumerate(part_files, 1):
            df = pd.read_parquet(part)
            if df.empty:
                continue

            vid = df.iloc[0]["video_id"]
            num, den = fps_map.get(vid, (0, 1))

            images_tensor = []
            valid_rows = []

            for _, row in df.iterrows():
                idx = int(row["frame_idx"])
                img_path = EXTRA_KEYFRAMES_DIR / vid / f"e{idx:07d}.jpg"
                if not img_path.exists():
                    continue
                
                try:
                    img = Image.open(img_path).convert("RGB")
                    tensor = preprocess(img)
                    images_tensor.append(tensor)
                    valid_rows.append(row)
                except Exception as e:
                    print(f"Lỗi đọc ảnh {img_path}: {e}")

            if not images_tensor:
                continue

            # Tính vector hàng loạt (bằng GPU)
            inputs = torch.stack(images_tensor).to(device)
            features = model.encode_image(inputs)
            features /= features.norm(dim=-1, keepdim=True) # L2 Normalize (Bất biến 1)
            features = features.cpu().numpy()

            for row, feat in zip(valid_rows, features):
                idx = int(row["frame_idx"])
                ts = int(idx * 1000 * den / num) if num else 0
                
                buffer.append({
                    "keyframe_id": f"{vid}#e{idx:07d}", # Dùng #e để tách biệt với #k gốc
                    "video_id": vid,
                    "frame_idx": idx,
                    "timestamp_ms": ts,
                    "embedding": feat.tolist(),
                })

                if len(buffer) >= batch_size:
                    flush()
            
            print(f"[{i}/{len(part_files)}] Đã encode CLIP cho {vid} ({len(features)} ảnh)")

    flush()
    client.flush(COLLECTION_NAME)
    print(f"\n✅ HOÀN THÀNH. Đã bắn tổng cộng {total_upserted} vector mới vào Milvus.")

if __name__ == "__main__":
    main()
