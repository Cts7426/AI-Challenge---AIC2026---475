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

def process_single_video(video_id: str, model, processor, parts_dir: Path):
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
    
    for i, img_path in enumerate(images):
        frame_idx = int(img_path.stem[1:])
        
        # MLX sẽ mất khoảng 1-2 phút để "Compile Graph" (Làm nóng) cho bức ảnh ĐẦU TIÊN
        if i == 0:
            print(f"    ⏳ Đang làm nóng GPU (Warmup / JIT Compile) cho bức ảnh đầu tiên (Sẽ mất 1-2 phút, VUI LÒNG KHÔNG BẤM HUỶ)...")
        else:
            print(f"    📸 Xử lý Frame {frame_idx:07d}...")

        # `<|image|>` là token ảnh RIÊNG của Llama-3.2-Vision, không phải chuẩn
        # chung — Qwen2-VL dùng token khác (`<|vision_start|>...`). Model khác
        # Llama-3.2 sẽ ra caption bịa mà KHÔNG báo lỗi (bị chặn ở main()).
        prompt = f"<|image|>{PROMPT}"
        
        # Bật verbose=True để gõ chữ ra màn hình
        output = generate(
            model,
            processor,
            prompt=prompt,
            image=[str(img_path)],
            verbose=True,
            max_tokens=128
        )
        print("\n") # Xuống dòng sau khi in text

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

    # Prompt token ảnh trong process_single_video() hardcode riêng cho
    # Llama-3.2 (xem comment ở đó). Model khác thì ra caption bịa, không lỗi —
    # chặn sớm ở đây thay vì để lỗi im lặng lan xuống scene graph đã lưu.
    if "llama-3.2" not in args.model.lower():
        ap.error(
            f"--model={args.model!r}: prompt hiện chỉ đúng định dạng cho "
            "Llama-3.2-Vision. Cần thêm formatter riêng trước khi dùng model khác."
        )

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
    
    # Sửa lỗi thư viện MLX tự ném lỗi nếu processor không có chat_template
    if not hasattr(processor, "chat_template") or processor.chat_template is None:
        # Template đơn giản để lách qua hàm check của MLX, ta đã ghép sẵn <|image|> vào prompt ở trên rồi.
        processor.chat_template = "{% for message in messages %}{{ message['content'] }}{% endfor %}"

    for i, vid in enumerate(todo, 1):
        t0 = time.perf_counter()
        print(f"[{i}/{len(todo)}] Đang chạy {vid}...")
        try:
            n_frames = process_single_video(vid, model, processor, SCENE_GRAPH_PARTS_DIR)
            elapsed = time.perf_counter() - t0
            print(f"  ✅ Xong {vid}: {n_frames} frames trong {elapsed:.1f}s")
        except Exception as e:
            print(f"  ❌ Lỗi {vid}: {e}")

if __name__ == "__main__":
    main()
