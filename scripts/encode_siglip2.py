"""Encode toàn bộ keyframe BTC bằng SigLIP2 — job nặng, checkpoint/resume được.

Vì sao có script này: A/B trên hồ 44 video cho SigLIP2 L/16 hơn CLIP B/32
+0.118 Final và cứu được đúng các câu CLIP bó tay (p1-8/p1-14: hạng 13 -> 4).
Muốn dùng thật thì phải encode lại toàn kho.

Ba điều script này lo, vì AGENTS.md bắt buộc:
  - checkpoint/resume theo VIDEO (bất biến #8): tắt giữa chừng chạy lại không
    mất công, không encode trùng.
  - L2-normalize + kiểm norm ≈ 1 (bất biến #5) ngay khi ghi, không để lỗi
    im lặng lọt xuống index.
  - ghi .meta.json kèm model/pretrained/dim/commit để assert lúc load.

KHÔNG đụng tới collection CLIP đang chạy: script chỉ ghi .npy ra đĩa. Việc nạp
vào Milvus là bước riêng, sang collection riêng, để còn A/B và quay đầu được.

Nút cổ chai thật là đọc/giải mã JPEG chứ không phải GPU (đo được: 6-7 ảnh/s
tuần tự trong khi GPU làm được ~14). Nên ảnh được đọc song song bằng thread —
PIL nhả GIL lúc decode nên thread ăn thua thật.

Chạy:
    .venv/bin/python3.14 scripts/encode_siglip2.py --bench      # đo tốc độ rồi thoát
    .venv/bin/python3.14 scripts/encode_siglip2.py              # chạy thật, resume được
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from PIL import Image

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# Bản mạnh nhất còn chạy được trong thời gian thực tế trên máy này. Đo tại chỗ:
# L-16-256 14,9 ảnh/s burst / 5,0 bền vững; SO400M-16-256 11,2 burst -> ~40 giờ.
# SO400M-384 (~90 giờ) và gopt-384 (~300 giờ) không phải lựa chọn.
MODEL_NAME = "ViT-SO400M-16-SigLIP2-256"
PRETRAINED = "webli"
# Thư mục tách theo model: vector L/16 là 1024 chiều còn SO400M là 1152, trộn
# vào nhau thì lỗi chỉ lộ ra lúc nạp Milvus, hoặc tệ hơn là không lộ ra.
OUT_DIR = REPO / "data/derived" / f"emb_{MODEL_NAME.replace('/', '-')}"
PROGRESS = OUT_DIR / "progress.json"
KF_ROOT = REPO / "data/raw/btc/keyframes"


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    except Exception:
        return "unknown"


def build_index() -> dict[str, list[tuple[int, str]]]:
    """video_id -> [(frame_idx tuyệt đối, đường dẫn ảnh)].

    Gom CẢ HAI nguồn ảnh để index mới phủ bằng index CLIP đang chạy (549K):
      - derived 1fps (keyframes.parquet, 371.702) — dày theo thời gian, chính
        là thứ cần cho lỗi "đúng video, trật khoảnh khắc"
      - keyframe BTC (frame_map, 177.321) — thưa, theo I-frame

    frame_idx LUÔN lấy từ cột parquet, KHÔNG parse từ tên file (bất biến #4).
    """
    by_video: dict[str, list[tuple[int, str]]] = {}
    derived_root = REPO / "data/derived/keyframes"

    kf = pd.read_parquet(REPO / "data/derived/keyframes.parquet")
    for r in kf.itertuples():
        p = derived_root / str(r.path).split("keyframes/", 1)[-1]
        if p.exists():
            by_video.setdefault(str(r.video_id), []).append((int(r.frame_idx), str(p)))

    fm = pd.read_parquet(REPO / "data/derived/frame_map.parquet")
    dirs = {Path(p).name: p for p in glob.glob(str(KF_ROOT / "*/*"))}
    for r in fm.itertuples():
        d = dirs.get(str(r.video_id))
        if not d:
            continue
        p = os.path.join(d, f"{int(r.btc_ordinal):03d}.jpg")
        if os.path.exists(p):
            by_video.setdefault(str(r.video_id), []).append((int(r.frame_idx_corrected), p))
    return by_video


def load_progress() -> set[str]:
    if PROGRESS.exists():
        try:
            return set(json.loads(PROGRESS.read_text())["done"])
        except Exception:
            return set()
    return set()


def save_progress(done: set[str]) -> None:
    PROGRESS.write_text(json.dumps({"done": sorted(done)}, indent=0), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--batch", type=int, default=48)
    ap.add_argument("--workers", type=int, default=10, help="luồng đọc/giải mã ảnh")
    ap.add_argument("--bench", action="store_true", help="đo tốc độ trên 600 ảnh rồi thoát")
    args = ap.parse_args()

    import gc

    import open_clip

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Dựng danh sách TRƯỚC rồi mới nạp model: build_index() giữ hai DataFrame
    # 371K + 177K dòng, để chúng nằm cạnh model 1,2 GB trên máy 16 GB là đủ
    # đẩy vào swap. gc.collect() thả chúng ra trước khi model chiếm chỗ.
    print("dựng danh sách ảnh ...", flush=True)
    by_video = build_index()
    gc.collect()

    print(f"nạp {MODEL_NAME}/{PRETRAINED} ...", flush=True)
    model, _, preprocess = open_clip.create_model_and_transforms(MODEL_NAME, pretrained=PRETRAINED)
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    model = model.eval().to(device)
    dim = model.visual.output_dim if hasattr(model.visual, "output_dim") else None

    # fp16: đo được nhanh gấp 2,81 lần trên MPS (11,0 -> 31,1 ảnh/s), và ĐÃ KIỂM
    # không phá không gian vector — cosine với fp32 là 0,9995 (tb 1,000013),
    # norm vẫn ≈ 1,0, top-10 xếp hạng giống hệt. Vector vẫn ghi ra float32 vì
    # Milvus nhận float32.
    use_half = device == "mps"
    if use_half:
        model = model.half()
        print("  dùng fp16 (đã kiểm cosine 0,9995 vs fp32)", flush=True)

    done = load_progress()
    todo = [v for v in sorted(by_video) if v not in done]
    total_imgs = sum(len(by_video[v]) for v in todo)
    print(f"{len(by_video)} video · còn {len(todo)} video / {total_imgs:,} ảnh "
          f"· thiết bị {device} · batch {args.batch} · {args.workers} luồng đọc", flush=True)

    def load_one(item):
        idx, path = item
        try:
            return idx, preprocess(Image.open(path).convert("RGB"))
        except Exception:
            return None

    pool = ThreadPoolExecutor(max_workers=args.workers)
    t_start = time.time()
    n_done = 0

    if args.bench:
        sample = [it for v in todo[:6] for it in by_video[v]][:600]
        loaded = [x for x in pool.map(load_one, sample) if x]
        t0 = time.time()
        for i in range(0, len(loaded), args.batch):
            b = torch.stack([t for _, t in loaded[i:i + args.batch]]).to(device)
            with torch.no_grad():
                model.encode_image(b)
        torch.mps.synchronize() if device == "mps" else None
        dt = time.time() - t0
        print(f"[bench] {len(loaded)} ảnh · nạp+encode {time.time()-t_start:.0f}s "
              f"· riêng encode {dt:.0f}s → {len(loaded)/(time.time()-t_start):.1f} ảnh/s tổng thể")
        print(f"[bench] ước tính {total_imgs:,} ảnh ≈ {total_imgs/(len(loaded)/(time.time()-t_start))/3600:.1f} giờ")
        return 0

    # Đệm kép: nạp khối kế tiếp SONG SONG với lúc GPU encode khối hiện tại.
    # Nạp cả video một lúc thì tràn RAM (đã gặp: treo hẳn ở 11,7/13,3 GB); nạp
    # từng batch nhỏ rồi mới encode thì GPU đứng chờ đĩa (đo được: 5,7 ảnh/s).
    # Khối 256 ảnh ≈ 200 MB, hai khối cùng lúc vẫn thừa chỗ, mà IO che được GPU.
    CHUNK = args.batch * 8
    driver = ThreadPoolExecutor(max_workers=1)

    def load_chunk(chunk_items):
        return [x for x in pool.map(load_one, chunk_items) if x]

    for vi, video_id in enumerate(todo, 1):
        items = by_video[video_id]
        frames, vecs = [], []
        blocks = [items[i:i + CHUNK] for i in range(0, len(items), CHUNK)]
        pending = driver.submit(load_chunk, blocks[0]) if blocks else None

        for bi in range(len(blocks)):
            loaded_block = pending.result()
            pending = driver.submit(load_chunk, blocks[bi + 1]) if bi + 1 < len(blocks) else None
            for i in range(0, len(loaded_block), args.batch):
                chunk = loaded_block[i:i + args.batch]
                if not chunk:
                    continue
                batch = torch.stack([t for _, t in chunk]).to(device)
                if use_half:
                    batch = batch.half()
                with torch.no_grad():
                    e = model.encode_image(batch)
                    e = e / e.norm(dim=-1, keepdim=True)      # bất biến #5
                vecs.append(e.float().cpu().numpy().astype(np.float32))
                frames.extend(idx for idx, _ in chunk)
                del batch, e
            del loaded_block
        if not vecs:
            done.add(video_id); save_progress(done); continue

        arr = np.vstack(vecs)
        del vecs
        norms = np.linalg.norm(arr, axis=1)
        if not np.allclose(norms, 1.0, atol=1e-3):        # dừng ngay, không ghi rác
            raise SystemExit(f"{video_id}: norm lệch 1.0 (min {norms.min():.4f} max {norms.max():.4f})")

        np.save(OUT_DIR / f"{video_id}.npy", arr)
        np.save(OUT_DIR / f"{video_id}.frames.npy", np.array(frames, dtype=np.int64))
        done.add(video_id); save_progress(done)

        n_done += len(frames)
        el = time.time() - t_start
        rate = n_done / max(el, 1)
        left = (total_imgs - n_done) / max(rate, 0.1) / 3600
        print(f"[{vi}/{len(todo)}] {video_id} {len(frames):>4d} ảnh · "
              f"{rate:.1f} ảnh/s · còn ~{left:.1f}h", flush=True)

    (OUT_DIR / "siglip2.meta.json").write_text(json.dumps({
        "model_name": MODEL_NAME, "pretrained": PRETRAINED,
        "embedding_dim": int(arr.shape[1]) if n_done else dim,
        "normalized": "l2", "metric": "COSINE",
        "n_videos": len(done), "commit": _git_commit(),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "frame_source": "data/derived/frame_map.parquet:frame_idx_corrected",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"XONG · {len(done)} video · {time.time()-t_start:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
