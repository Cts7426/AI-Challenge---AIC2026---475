# backend/indexing/load_clip_local.py — nạp CLIP cho keyframe TỰ TRÍCH (1fps)
#
# ===== Vì sao script này tồn tại =====
# `load_clip.py` (A1.0a) chỉ nạp vector BTC cấp — sparse, I-frame (~307
# keyframe/video, xem `data/raw/btc/clip-features-32/<video>.npy`). Team CÒN
# tự trích keyframe riêng dày hơn nhiều (1fps, `data/derived/keyframes.parquet`,
# 371.702 dòng toàn corpus, ẢNH ĐÃ CÓ SẴN TRÊN ĐĨA) nhưng CHƯA TỪNG encode CLIP
# cho bộ này — search hiện tại chỉ "nhìn thấy" phần video mà BTC tình cờ đặt
# I-frame vào. Đo 20/08: trung vị mỗi video chỉ 47.7% được nạp vector, 6/23 câu
# KIS dev-set không tìm thấy đúng shot ở BẤT KỲ ĐÂU trong top-100 (không phải
# lỗi xếp hạng — lỗi RỖNG, đúng shot chưa từng được embed).
#
# ===== Vì sao AN TOÀN =====
# Cộng thêm (additive) — KHÔNG xoá/sửa 177.321 vector BTC hiện có
# (`load_clip.py` vẫn là nguồn của bộ đó). `client.upsert()` khoá theo
# `keyframe_id` (primary key) nên chạy lại/dừng giữa chừng không tạo trùng.
#
# Đã kiểm chứng KHÔNG gian vector khớp BTC (bất biến 2, CLAUDE.md mục 12):
# encode cục bộ đúng ảnh BTC gốc (`data/raw/btc/keyframes/keyframes_L21/
# L21_V001/001.jpg`...) bằng CLIP_MODEL_NAME/CLIP_PRETRAINED hiện tại → so
# cosine với vector BTC cấp cho CHÍNH ảnh đó: 1.0001–1.0004 (sai số làm tròn
# float32). Cùng model, cùng preprocessing — an toàn trộn chung một collection.
#
# ===== keyframe_id dùng `kf_id` (KHÔNG phải dạng "#kNNNN" của BTC) =====
# `data/derived/clip_kf_map.parquet` đã map sẵn `kf_id` (dạng
# "L21_V001_0000090") → `shot_id` cho ĐỦ 371.702 dòng — và
# `backend/retrieval/search.py::_shot_map()` đã đọc CẢ HAI dạng ID. Nạp vector
# bằng đúng `kf_id` có sẵn trong `keyframes.parquet` thì gom-theo-shot chạy
# đúng ngay lập tức — không sửa một dòng nào ở search.py/qa.py/trake.py.
#
# ===== Không tốn LLM/API — CLIP là model thị giác cục bộ =====
# Chạy được dù tài khoản Anthropic hết tiền. `open_clip` đã cài sẵn (dùng cho
# encode_text() ở text_query.py) — không cài thêm gì.
#
# ===== Chạy =====
#   docker compose up -d milvus
#   python -m backend.indexing.load_clip_local --limit-videos 3   # thử trước
#   python -m backend.indexing.load_clip_local                     # full, ~30-70 phút
#   python -m backend.indexing.load_clip_local --verify-only

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from backend.indexing.load_clip import (
    BATCH,
    _normalize_rows,
    create_collection,
    verify_norms,
)
from backend.indexing.milvus_client import COLLECTION_NAME, connect
from data.config.clip_model import CLIP_MODEL_NAME, CLIP_PRETRAINED, CLIP_EMBEDDING_DIM

REPO_ROOT = Path(__file__).resolve().parents[2]
DERIVED = REPO_ROOT / "data" / "derived"
KEYFRAMES_PARQUET = DERIVED / "keyframes.parquet"
VIDEO_INFO = DERIVED / "video_info.parquet"
PROGRESS_PATH = REPO_ROOT / "data" / "manifests" / "clip_local_progress.json"

IMG_BATCH = 128  # ảnh/lô đọc-đĩa + encode — cân RAM/tốc độ, không phải lô ghi Milvus (BATCH)

_model = None
_preprocess = None


def _get_model():
    """Lazy-singleton — cùng pattern với text_query.py::_get_model()."""
    global _model, _preprocess
    if _model is None:
        import open_clip
        import torch

        device = "mps" if torch.backends.mps.is_available() else "cpu"
        _model, _, _preprocess = open_clip.create_model_and_transforms(
            CLIP_MODEL_NAME, pretrained=CLIP_PRETRAINED
        )
        _model.eval().to(device)
        _model._device = device  # type: ignore[attr-defined]
    return _model, _preprocess


def _timestamp_map() -> dict[str, tuple[int, int]]:
    """video_id → (fps_num, fps_den). Giống hệt load_clip.py::_timestamp_map()."""
    if not VIDEO_INFO.exists():
        return {}
    df = pd.read_parquet(VIDEO_INFO)
    return {str(r.video_id): (int(r.fps_num), int(r.fps_den)) for r in df.itertuples()}


def _load_progress() -> set[str]:
    if not PROGRESS_PATH.exists():
        return set()
    try:
        return set(json.loads(PROGRESS_PATH.read_text(encoding="utf-8")).get("done_videos", []))
    except Exception:
        return set()


def _save_progress(done: set[str]) -> None:
    PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS_PATH.write_text(
        json.dumps({"done_videos": sorted(done)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _encode_batch(paths: list[Path]) -> tuple[np.ndarray, list[int]]:
    """Đọc + encode một lô ảnh. Trả (vector chuẩn hoá Nxdim, index ảnh lỗi trong lô)."""
    import torch
    from PIL import Image

    model, preprocess = _get_model()
    device = model._device  # type: ignore[attr-defined]

    tensors, loi = [], []
    for i, p in enumerate(paths):
        try:
            img = Image.open(p).convert("RGB")
            tensors.append(preprocess(img))
        except Exception:
            loi.append(i)

    if not tensors:
        return np.zeros((0, CLIP_EMBEDDING_DIM), dtype=np.float32), loi

    batch = torch.stack(tensors).to(device)
    with torch.no_grad():
        feats = model.encode_image(batch).cpu().numpy().astype(np.float32)
    feats, _ = _normalize_rows(feats)
    return feats, loi


def load(client, limit_videos: int | None = None) -> dict:
    """Đọc keyframes.parquet theo VIDEO → encode cục bộ → upsert Milvus.

    Checkpoint theo video (PROGRESS_PATH): dừng giữa chừng chạy lại không mã
    hoá lại video đã xong. Trả thống kê để write_meta()-style báo cáo.
    """
    if not KEYFRAMES_PARQUET.exists():
        raise FileNotFoundError(f"Thiếu {KEYFRAMES_PARQUET} — chưa trích keyframe (B1.2).")

    kf = pd.read_parquet(KEYFRAMES_PARQUET, columns=["kf_id", "video_id", "frame_idx", "path"])
    fps = _timestamp_map()
    done = _load_progress()

    video_ids = sorted(kf["video_id"].unique())
    if limit_videos:
        video_ids = [v for v in video_ids if v not in done][:limit_videos]

    tong_vector, tong_loi, n_video_moi = 0, 0, 0

    for vi, video_id in enumerate(video_ids, 1):
        if video_id in done:
            continue
        rows = kf[kf["video_id"] == video_id].reset_index(drop=True)
        num, den = fps.get(video_id, (0, 1))

        buffer: list[dict] = []
        for start in range(0, len(rows), IMG_BATCH):
            chunk = rows.iloc[start:start + IMG_BATCH]
            paths = [DERIVED / p for p in chunk["path"]]
            feats, loi_idx = _encode_batch(paths)
            tong_loi += len(loi_idx)

            ok_rows = [r for i, r in enumerate(chunk.itertuples()) if i not in loi_idx]
            for r, v in zip(ok_rows, feats):
                ts = int(r.frame_idx * 1000 * den / num) if num else 0
                buffer.append({
                    "keyframe_id": r.kf_id,
                    "video_id": r.video_id,
                    "frame_idx": int(r.frame_idx),
                    "timestamp_ms": ts,
                    "embedding": v.tolist(),
                })

            if len(buffer) >= BATCH:
                client.upsert(COLLECTION_NAME, buffer)
                tong_vector += len(buffer)
                buffer.clear()

        if buffer:
            client.upsert(COLLECTION_NAME, buffer)
            tong_vector += len(buffer)

        done.add(video_id)
        n_video_moi += 1
        if vi % 20 == 0 or vi == len(video_ids):
            _save_progress(done)  # checkpoint định kỳ, không phải mỗi video (đỡ I/O)
            print(f"  {vi}/{len(video_ids)} video · đã nạp {tong_vector} vector "
                  f"({tong_loi} ảnh lỗi, bỏ qua)")

    _save_progress(done)
    client.flush(COLLECTION_NAME)
    return {"n_video_moi": n_video_moi, "n_vectors": tong_vector, "n_loi_doc_anh": tong_loi}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit-videos", type=int, help="chỉ nạp N video CHƯA xong (để thử)")
    ap.add_argument("--verify-only", action="store_true", help="chỉ kiểm index, không nạp")
    ap.add_argument("--reset-progress", action="store_true",
                     help="xoá checkpoint, coi như chưa video nào xong (KHÔNG xoá vector Milvus)")
    args = ap.parse_args()

    client = connect()

    if args.verify_only:
        return 0 if verify_norms(client) else 1

    if args.reset_progress and PROGRESS_PATH.exists():
        PROGRESS_PATH.unlink()
        print(f"Đã xoá {PROGRESS_PATH} — lần chạy này coi như chưa video nào xong.")

    create_collection(client, recreate=False)  # schema đã có (load_clip.py tạo) — không recreate
    stats = load(client, limit_videos=args.limit_videos)
    print(f"\nXong: {stats}")

    print("\n--- kiểm chứng sau khi nạp ---")
    ok = verify_norms(client)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
