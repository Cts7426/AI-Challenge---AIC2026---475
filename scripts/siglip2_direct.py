"""Tìm kiếm SigLIP2 trực tiếp từ file .npy, KHÔNG qua Milvus.

Vì sao bỏ qua Milvus: nó sập lặp khi phải giữ đồng thời hai không gian vector
(CLIP 512 chiều + SigLIP2 1152 chiều) và ngốn hàng giờ để ổn định. Nhưng phép
tìm này vốn không cần cơ sở dữ liệu: 549K vector × 1152 chiều ở float16 chỉ
1,26 GB, một phép nhân ma trận numpy quét toàn bộ trong dưới một giây — nhanh
hơn cả HNSW, và không có gì để sập.

Milvus vẫn đáng giữ cho vận hành lâu dài (nạp tăng dần, lọc theo video, chia
tải), nhưng để TRẢ LỜI CÂU HỎI "SigLIP2 có hơn CLIP không" thì nó chỉ là chướng
ngại.

Chạy:
    python scripts/siglip2_direct.py --text "a white lion on poles" --top 10
    python scripts/siglip2_direct.py --queries plan.json --out kq.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from data.config.siglip2_model import siglip2_emb_dir  # noqa: E402

CACHE = REPO / "data/derived/siglip2_flat.npz"


def build_cache() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Gộp mọi .npy thành một mảng phẳng float16 + bảng tra (video, frame).

    float16 đủ chính xác: vector đã chuẩn hoá L2 nên mọi thành phần trong
    [-1, 1], sai số float16 ~1e-3 — nhỏ hơn nhiều khoảng cách giữa các ứng viên.
    Đổi lại tiết kiệm một nửa RAM (1,26 GB thay vì 2,5 GB).
    """
    d = siglip2_emb_dir()
    files = sorted(p for p in d.glob("*.npy") if not p.name.endswith(".frames.npy"))
    vecs, vids, frames = [], [], []
    for p in files:
        fp = d / f"{p.stem}.frames.npy"
        if not fp.exists():
            continue
        v = np.load(p).astype(np.float16)
        f = np.load(fp).astype(np.int64)
        if len(v) != len(f):
            continue
        vecs.append(v)
        frames.append(f)
        vids.append(np.full(len(f), p.stem, dtype="<U16"))
    V = np.vstack(vecs)
    F = np.concatenate(frames)
    I = np.concatenate(vids)
    np.savez(CACHE, V=V, F=F, I=I)
    print(f"đã dựng cache: {V.shape} ({V.nbytes/1e9:.2f} GB) từ {len(files)} video")
    return V, F, I


def load_cache() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if CACHE.exists():
        z = np.load(CACHE, allow_pickle=False)
        return z["V"], z["F"], z["I"]
    return build_cache()


_model = None
def encode(texts: list[str]) -> np.ndarray:
    global _model
    import torch
    import open_clip
    from data.config.siglip2_model import SIGLIP2_MODEL_NAME, SIGLIP2_PRETRAINED

    if _model is None:
        m, _, _ = open_clip.create_model_and_transforms(SIGLIP2_MODEL_NAME, pretrained=SIGLIP2_PRETRAINED)
        dev = "mps" if torch.backends.mps.is_available() else "cpu"
        _model = (m.eval().to(dev).half(), open_clip.get_tokenizer(SIGLIP2_MODEL_NAME), dev)
    model, tok, dev = _model
    with torch.no_grad():
        e = model.encode_text(tok(texts).to(dev))
        e = e / e.norm(dim=-1, keepdim=True)
    return e.float().cpu().numpy().astype(np.float16)


def search(text: str, V, F, I, top: int = 100, per_video: int = 3) -> list[tuple[str, int, float]]:
    """Top ứng viên, giới hạn số frame mỗi video để không bị một video chiếm hết."""
    q = encode([text])[0]
    scores = (V.astype(np.float32) @ q.astype(np.float32))
    order = np.argsort(-scores)[: top * 30]
    out, count = [], {}
    for j in order:
        v = str(I[j])
        if count.get(v, 0) >= per_video:
            continue
        count[v] = count.get(v, 0) + 1
        out.append((v, int(F[j]), float(scores[j])))
        if len(out) >= top:
            break
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--text")
    ap.add_argument("--queries", type=Path, help="JSON {qid: [anchor, ...]}")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--per-video", type=int, default=3)
    ap.add_argument("--rebuild", action="store_true")
    args = ap.parse_args()

    t0 = time.time()
    if args.rebuild and CACHE.exists():
        CACHE.unlink()
    V, F, I = load_cache()
    print(f"nạp {V.shape[0]:,} vector trong {time.time()-t0:.0f}s")

    if args.text:
        t0 = time.time()
        for i, (v, f, s) in enumerate(search(args.text, V, F, I, args.top, args.per_video), 1):
            print(f"{i:3d}. {v}:{f:<8d} {s:.4f}")
        print(f"({time.time()-t0:.2f}s)")
        return 0

    if args.queries:
        plans = json.loads(args.queries.read_text(encoding="utf-8"))
        res = {}
        for qid, anchors in plans.items():
            rows = []
            for a in anchors:
                rows += [(v, f) for v, f, _ in search(a, V, F, I, args.top, args.per_video)]
            res[qid] = rows
            print(f"  {qid}: {len(rows)} ứng viên")
        if args.out:
            args.out.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
            print(f"-> {args.out}")
        return 0

    ap.error("cần --text hoặc --queries")


if __name__ == "__main__":
    raise SystemExit(main())
