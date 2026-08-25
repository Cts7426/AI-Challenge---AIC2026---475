"""
B2.1 — VLM Scene Graph Job (Mac M-series MLX Edition)

Script này được tối ưu hóa TUYỆT ĐỐI cho kiến trúc Apple Silicon (M-series) 
bằng framework `mlx-vlm`. Tốc độ xử lý có thể nhanh gấp 2-3 lần so với PyTorch.

Dành riêng cho Mac 16GB RAM: 
- Model khuyên dùng: Llama-3.2-11B-Vision-Instruct-4bit (Mô hình SOTA mạnh nhất hiện nay).
- Khuyến nghị: Để Mac chạy 100% (num-shards=1) kho video để giữ đồng nhất dữ liệu.
"""

import argparse
import hashlib
import json
import time
from pathlib import Path

import pandas as pd
import yaml
import mlx.core as mx
from mlx_vlm import load, generate
from mlx_vlm.prompt_utils import get_message_profile
from mlx_vlm.utils import load_config as load_mlx_config

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT_DIR / "data" / "config" / "config.yaml"
DERIVED_DIR = ROOT_DIR / "data" / "derived"
KEYFRAMES_DIR = DERIVED_DIR / "keyframes"
SCENE_GRAPH_PARTS_DIR = DERIVED_DIR / "vlm_scene_graph_parts"

def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def get_video_shard(video_id: str, num_shards: int) -> int:
    return int(hashlib.md5(video_id.encode("utf-8")).hexdigest(), 16) % num_shards

def process_single_video(video_id: str, model, processor, model_path: str, parts_dir: Path):
    video_dir = KEYFRAMES_DIR / video_id
    if not video_dir.exists():
        return None
    
    images = sorted(video_dir.glob("f*.jpg"))
    if not images:
        return None

    PROMPT = (
        "Describe the visual details of this scene. List objects, colors, actions, and settings. "
        "DO NOT count objects or read text. Return in strictly formatted JSON: "
        "{\"objects\": [\"red shirt\", \"broken glass\"], \"actions\": [\"running\"], \"setting\": \"indoor\"}"
    )

    results = []
    config = load_mlx_config(model_path)
    
    for img_path in images:
        frame_idx = int(img_path.stem[1:])
        
        # MLX-VLM format
        messages = [{"role": "user", "content": [{"type": "text", "text": PROMPT}]}]
        formatter = get_message_profile(config["model_type"])
        prompt = formatter(messages)
        
        # Generate
        output = generate(
            model,
            processor,
            prompt=prompt,
            image=[str(img_path)],
            verbose=False,
            max_tokens=128
        )

        results.append({
            "kf_id": f"{video_id}_{frame_idx:07d}",
            "video_id": video_id,
            "frame_idx": frame_idx,
            "scene_graph_raw": output
        })
    
    df = pd.DataFrame(results)
    parts_dir.mkdir(parents=True, exist_ok=True)
    df.to_parquet(parts_dir / f"{video_id}.parquet", index=False)
    return len(results)

def main():
    ap = argparse.ArgumentParser(description="B2.1 VLM Scene Graph Extraction (MLX Mac)")
    ap.add_argument("--shard", type=int, default=0) # Mac xử lý 100%
    ap.add_argument("--num-shards", type=int, default=1) 
    # Dùng Llama 3.2 11B 4-bit (Đẳng cấp nhất cho 16GB Mac)
    ap.add_argument("--model", type=str, default="mlx-community/Llama-3.2-11B-Vision-Instruct-4bit")
    args = ap.parse_args()

    SCENE_GRAPH_PARTS_DIR.mkdir(parents=True, exist_ok=True)
    videos = sorted([d.name for d in KEYFRAMES_DIR.iterdir() if d.is_dir()])

    todo = [vid for vid in videos if get_video_shard(vid, args.num_shards) == args.shard 
            and not (SCENE_GRAPH_PARTS_DIR / f"{vid}.parquet").exists()]

    print(f"Mac M5 Shard {args.shard}/{args.num_shards}: Có {len(todo)} video cần xử lý.")
    if not todo:
        return

    print(f"Khởi tạo MLX VLM: {args.model}...")
    model, processor = load(args.model)
    print("✅ Tải model siêu tốc độ qua MLX thành công.")
    
    for i, vid in enumerate(todo, 1):
        t0 = time.perf_counter()
        print(f"[{i}/{len(todo)}] Đang chạy {vid}...")
        try:
            n_frames = process_single_video(vid, model, processor, args.model, SCENE_GRAPH_PARTS_DIR)
            elapsed = time.perf_counter() - t0
            print(f"  ✅ Xong {vid}: {n_frames} frames trong {elapsed:.1f}s")
        except Exception as e:
            print(f"  ❌ Lỗi {vid}: {e}")

if __name__ == "__main__":
    main()
