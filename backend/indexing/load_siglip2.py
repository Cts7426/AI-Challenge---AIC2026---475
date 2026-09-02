"""Nạp vector SigLIP2 đã encode vào một collection Milvus RIÊNG.

Vì sao collection riêng chứ không ghi đè `keyframes`: đổi encoder là đổi cả
không gian vector. Nếu ghi đè mà kết quả tệ hơn thì không còn đường lùi, và
lỗi kiểu này không crash — nó chỉ trả kết quả sai với điểm cosine trông rất
bình thường (CLAUDE.md mục 12). Có hai collection thì A/B được và quay đầu
bằng một dòng config.

Đầu vào là các file `.npy` do `scripts/encode_siglip2.py` sinh ra; script này
KHÔNG encode gì cả, chỉ nạp — nên nó chạy được ngay cả khi job encode vẫn đang
chạy dở (nạp phần đã xong, lần sau nạp tiếp phần mới).

Chạy:
    .venv/bin/python3.14 -m backend.indexing.load_siglip2            # nạp phần đã có
    .venv/bin/python3.14 -m backend.indexing.load_siglip2 --recreate # dựng lại từ đầu
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from pymilvus import DataType, MilvusClient

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.indexing.milvus_client import connect  # noqa: E402
from data.config.siglip2_model import (  # noqa: E402
    SIGLIP2_COLLECTION,
    SIGLIP2_EMBEDDING_DIM,
    SIGLIP2_METRIC,
    SIGLIP2_MODEL_NAME,
    SIGLIP2_PRETRAINED,
    siglip2_emb_dir,
)

VIDEO_INFO = REPO / "data/derived/video_info.parquet"
META_PATH = REPO / "data/derived/siglip2_index.meta.json"
BATCH = 1000


def assert_siglip2_index_meta(strict: bool = True) -> dict | None:
    """So `siglip2_index.meta.json` với config hiện tại. Lệch → RuntimeError.

    ⚠️ Vì sao BẮT BUỘC có hàm này (R3.K2b): `search._branch_vector()` gọi
    `assert_index_meta(strict=False)` CHỈ cho nhánh CLIP; nhánh SigLIP2 trước
    đây không có assert nào. Đó là lỗ hổng đúng loại lỗi im lặng mà `AGENTS.md`
    bất biến 8 sinh ra để chặn: đổi `SIGLIP2_MODEL_NAME` trong config mà quên
    encode lại thì Milvus VẪN trả top-k với cosine trông bình thường, và không
    có gì báo rằng index thuộc một không gian vector khác.

    Thà mất nguồn vector còn hơn tin số sai — nên gãy to thay vì cảnh báo.

    strict=False: chưa có meta (chưa nạp SigLIP2 bao giờ) thì chỉ trả None, để
    máy chưa dựng index vẫn chạy được nhánh CLIP bình thường.
    """
    if not META_PATH.exists():
        if strict:
            raise RuntimeError(
                f"Chưa có {META_PATH.name} — index SigLIP2 chưa được nạp. "
                "Chạy: python -m backend.indexing.load_siglip2"
            )
        return None

    meta = json.loads(META_PATH.read_text(encoding="utf-8"))
    lech = [
        f"{khoa}: index={meta.get(khoa)!r} vs config={dang_dung!r}"
        for khoa, dang_dung in (
            ("model_name", SIGLIP2_MODEL_NAME),
            ("pretrained", SIGLIP2_PRETRAINED),
            ("embedding_dim", SIGLIP2_EMBEDDING_DIM),
            ("metric", SIGLIP2_METRIC),
            ("collection", SIGLIP2_COLLECTION),
        )
        if meta.get(khoa) != dang_dung
    ]
    if lech:
        raise RuntimeError(
            "INDEX SigLIP2 VÀ CONFIG KHÔNG CÙNG KHÔNG GIAN VECTOR — kết quả search "
            "sẽ SAI mà không báo lỗi.\n  " + "\n  ".join(lech)
            + "\nNạp lại: python -m backend.indexing.load_siglip2 --recreate\n"
            f"(index nạp lúc {meta.get('built_at')}, commit {meta.get('git_commit')})"
        )
    return meta


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _git_commit() -> str:
    """Commit đang dựng index. 'unknown' khi chạy ngoài git — không làm sập job
    nạp chỉ vì thiếu một trường provenance."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"


def _timestamp_map() -> dict[str, tuple[int, int]]:
    """video_id → (fps_num, fps_den). fps giữ dạng PHÂN SỐ: 29.97 = 30000/1001,
    làm tròn thành 30 thì sau 10 phút lệch ~18 frame (CLAUDE.md mục 4)."""
    if not VIDEO_INFO.exists():
        return {}
    df = pd.read_parquet(VIDEO_INFO)
    return {str(r.video_id): (int(r.fps_num), int(r.fps_den)) for r in df.itertuples()}


def create_collection(client: MilvusClient, recreate: bool = False) -> None:
    if client.has_collection(SIGLIP2_COLLECTION):
        if not recreate:
            return
        client.drop_collection(SIGLIP2_COLLECTION)
        print(f"đã xoá collection cũ '{SIGLIP2_COLLECTION}'")

    schema = MilvusClient.create_schema(auto_id=False)
    # Khoá chính là "<video_id>#f<frame_idx>": SigLIP2 encode CẢ keyframe 1fps
    # lẫn keyframe BTC, mà hai nguồn có thể trỏ về cùng frame — lấy frame làm
    # khoá thì trùng tự khử, không sinh hai dòng cho một khoảnh khắc.
    schema.add_field("keyframe_id", DataType.VARCHAR, is_primary=True, max_length=64)
    schema.add_field("video_id", DataType.VARCHAR, max_length=32)
    schema.add_field("frame_idx", DataType.INT64)
    schema.add_field("timestamp_ms", DataType.INT64)
    schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=SIGLIP2_EMBEDDING_DIM)

    index_params = MilvusClient.prepare_index_params()
    index_params.add_index(
        field_name="embedding", index_type="HNSW", metric_type=SIGLIP2_METRIC,
        params={"M": 16, "efConstruction": 200},
    )
    client.create_collection(SIGLIP2_COLLECTION, schema=schema, index_params=index_params)
    print(f"đã tạo '{SIGLIP2_COLLECTION}' (dim={SIGLIP2_EMBEDDING_DIM}, HNSW/{SIGLIP2_METRIC})")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--recreate", action="store_true")
    ap.add_argument("--emb-dir", type=Path, default=None)
    args = ap.parse_args()

    emb_dir = args.emb_dir or siglip2_emb_dir()
    if not emb_dir.exists():
        print(f"chưa có thư mục vector {emb_dir} — chạy scripts/encode_siglip2.py trước")
        return 1

    client = connect()
    create_collection(client, recreate=args.recreate)
    fps = _timestamp_map()

    files = sorted(p for p in emb_dir.glob("*.npy") if not p.name.endswith(".frames.npy"))
    print(f"{len(files)} video có vector trong {emb_dir.name}")

    rows, total, skipped = [], 0, 0
    for p in files:
        video_id = p.stem
        fp = emb_dir / f"{video_id}.frames.npy"
        if not fp.exists():
            skipped += 1
            continue
        vecs = np.load(p)
        frames = np.load(fp)
        if len(vecs) != len(frames):
            skipped += 1
            print(f"  bỏ {video_id}: {len(vecs)} vector nhưng {len(frames)} frame")
            continue

        norms = np.linalg.norm(vecs, axis=1)
        if not np.allclose(norms, 1.0, atol=1e-2):   # bất biến #5, chặn trước khi vào index
            raise SystemExit(f"{video_id}: vector chưa chuẩn hoá L2 "
                             f"(min {norms.min():.4f} max {norms.max():.4f})")

        num, den = fps.get(video_id, (25, 1))
        seen: set[int] = set()
        for vec, f in zip(vecs, frames):
            f = int(f)
            if f in seen:                # hai nguồn ảnh trỏ cùng frame -> giữ một
                continue
            seen.add(f)
            rows.append({
                "keyframe_id": f"{video_id}#f{f:07d}",
                "video_id": video_id,
                "frame_idx": f,
                "timestamp_ms": int(f * den * 1000 / num),
                "embedding": vec.tolist(),
            })
        while len(rows) >= BATCH:
            client.upsert(SIGLIP2_COLLECTION, rows[:BATCH])
            total += BATCH
            rows = rows[BATCH:]
            print(f"  đã nạp {total:,}", flush=True)

    if rows:
        client.upsert(SIGLIP2_COLLECTION, rows)
        total += len(rows)

    stats = client.get_collection_stats(SIGLIP2_COLLECTION)
    meta = {
        "model_name": SIGLIP2_MODEL_NAME, "pretrained": SIGLIP2_PRETRAINED,
        "embedding_dim": SIGLIP2_EMBEDDING_DIM, "metric": SIGLIP2_METRIC,
        "collection": SIGLIP2_COLLECTION, "normalized": "l2",
        "n_videos": len(files) - skipped, "n_vectors": int(stats["row_count"]),
        "emb_dir": str(emb_dir),
        # Provenance (AGENTS.md bất biến 8): không có hai trường này thì lúc
        # assert phát hiện lệch, thông báo lỗi không nói được index dựng khi nào
        # và từ commit nào — mà đó đúng là hai thứ cần để truy nguyên.
        "built_at": _now_iso(),
        "git_commit": _git_commit(),
    }
    (REPO / "data/derived/siglip2_index.meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"XONG · nạp {total:,} vector · collection có {stats['row_count']:,} "
          f"· bỏ qua {skipped} video")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
