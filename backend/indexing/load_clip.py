# backend/indexing/load_clip.py — A1.0a: nạp CLIP features BTC cấp vào Milvus
#
# ===== Nguồn dữ liệu =====
#   data/derived/clip_row_index.parquet  — bản đồ hàng .npy → keyframe (B0.1, Công Lý):
#       kf_id · video_id · npy_file · local_row · frame_idx
#   <features_dir>/<video_id>.npy        — vector BTC, hàng `local_row` là của kf đó
#   data/derived/video_info.parquet      — fps dạng PHÂN SỐ, để đổi frame → mili giây
#
# Không tự suy ra hàng nào ứng với keyframe nào: đó là việc của clip_row_index
# (đã xác thực bằng mắt ở B0.1c). Loader chỉ đọc bảng và nạp.
#
# ===== Ba thứ file này bảo vệ =====
# 1. CHUẨN HOÁ L2 cả hai phía (bất biến 1): vector BTC được chuẩn hoá lúc nạp,
#    query encoder cũng chuẩn hoá → cosine = dot product, metric Milvus = COSINE.
#    Sau khi nạp có phép kiểm chứng chạy được: lấy mẫu từ Milvus, norm phải ≈ 1.
# 2. `frame_idx` (thứ BTC CHẤM) được lưu thẳng trong collection, cạnh keyframe_id.
#    Tầng trên không phải tra ngược bảng nào nữa (bất biến 5).
# 3. `.meta.json` ghi model/dim/ngày/commit đã dùng để nạp; `assert_index_meta()`
#    so lại với config lúc query. Đổi model mà quên nạp lại → GÃY TO ngay,
#    thay vì âm thầm search trong không gian vector sai.
#
# ===== Chạy =====
#   docker compose up -d milvus
#   python -m backend.indexing.load_clip --features-dir D:\aic_data\clip-features-32
#   python -m backend.indexing.load_clip --recreate          # nạp lại từ đầu
#   python -m backend.indexing.load_clip --verify-only       # chỉ kiểm index đã có
#   (mặc định features-dir: $CLIP_FEATURES_DIR hoặc data/raw/clip-features-32)

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from pymilvus import DataType, MilvusClient

from backend.indexing.milvus_client import COLLECTION_NAME, connect
from data.config.clip_model import (
    CLIP_BTC_MODEL_NAME,
    CLIP_EMBEDDING_DIM,
    CLIP_MODEL_NAME,
    CLIP_PRETRAINED,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DERIVED = REPO_ROOT / "data" / "derived"
CLIP_ROW_INDEX = DERIVED / "clip_row_index.parquet"
VIDEO_INFO = DERIVED / "video_info.parquet"
META_PATH = DERIVED / "clip_index.meta.json"

METRIC = "COSINE"
BATCH = 5000          # 1 request gRPC tối đa ~64MB; 5000×512 float ≈ 10MB
NORM_TOL = 1e-3       # sai số cho phép của |v| sau chuẩn hoá


def _features_dir(arg: str | None) -> Path:
    """Thư mục .npy của BTC. Ưu tiên --features-dir > $CLIP_FEATURES_DIR > data/raw/..."""
    if arg:
        return Path(arg)
    if os.environ.get("CLIP_FEATURES_DIR"):
        return Path(os.environ["CLIP_FEATURES_DIR"])
    return REPO_ROOT / "data" / "raw" / "clip-features-32"


def _git_commit() -> str:
    """Commit đang dùng — để sau này truy được index này sinh từ code nào."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


# ------------------------------------------------------------------- collection

def create_collection(client: MilvusClient, recreate: bool = False) -> None:
    """Tạo collection `keyframes`.

    HNSW + COSINE: HNSW nhanh nhất khi search (đổi lại tốn RAM hơn IVF);
    COSINE là metric tự nhiên của CLIP, score đọc ra hiểu ngay.
    """
    if client.has_collection(COLLECTION_NAME):
        if not recreate:
            return
        client.drop_collection(COLLECTION_NAME)
        print(f"Đã xoá collection cũ '{COLLECTION_NAME}'.")

    schema = MilvusClient.create_schema(auto_id=False)
    # kf_id BTC dạng "L21_V001#k0001" — 64 ký tự dư sức
    schema.add_field("keyframe_id", DataType.VARCHAR, is_primary=True, max_length=64)
    schema.add_field("video_id", DataType.VARCHAR, max_length=32)
    schema.add_field("frame_idx", DataType.INT64)      # ← thứ BTC chấm
    schema.add_field("timestamp_ms", DataType.INT64)   # cho join ASR + UI
    schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=CLIP_EMBEDDING_DIM)

    index_params = MilvusClient.prepare_index_params()
    index_params.add_index(
        field_name="embedding",
        index_type="HNSW",
        metric_type=METRIC,
        params={"M": 16, "efConstruction": 200},
    )
    client.create_collection(COLLECTION_NAME, schema=schema, index_params=index_params)
    print(f"Đã tạo collection '{COLLECTION_NAME}' (dim={CLIP_EMBEDDING_DIM}, HNSW/{METRIC}).")


# ------------------------------------------------------------------------- nạp

def _timestamp_map() -> dict[str, tuple[int, int]]:
    """video_id → (fps_num, fps_den).

    ⚠️ fps phải giữ dạng PHÂN SỐ: 29.97 = 30000/1001. Làm tròn thành 30 thì sau
    10 phút lệch ~18 frame — đủ trượt mọi cửa sổ đáp án (CLAUDE.md mục 4).
    """
    import pandas as pd

    if not VIDEO_INFO.exists():
        return {}
    df = pd.read_parquet(VIDEO_INFO)
    return {
        str(r.video_id): (int(r.fps_num), int(r.fps_den))
        for r in df.itertuples()
    }


def _normalize_rows(vecs: np.ndarray) -> tuple[np.ndarray, int]:
    """Chuẩn hoá L2 từng hàng. Trả (vector đã chuẩn hoá, số hàng vector-không).

    Vector 0 không có hướng → cosine với nó vô nghĩa. Không tự ý thay bằng gì cả,
    chỉ đếm và báo lên để người nạp biết data nguồn có vấn đề.
    """
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    so_hong = int((norms.squeeze(-1) == 0).sum())
    an_toan = np.where(norms == 0, 1.0, norms)
    return (vecs / an_toan).astype(np.float32), so_hong


def load(
    client: MilvusClient,
    features_dir: Path,
    limit_videos: int | None = None,
) -> dict:
    """Đọc .npy theo clip_row_index → chuẩn hoá L2 → upsert Milvus. Trả thống kê."""
    import pandas as pd

    if not CLIP_ROW_INDEX.exists():
        raise FileNotFoundError(
            f"Thiếu {CLIP_ROW_INDEX} — cần clip_row_index.parquet (B0.1) để biết "
            "hàng nào của .npy ứng với keyframe nào. Không được tự suy ra."
        )
    if not features_dir.is_dir():
        raise FileNotFoundError(
            f"Không thấy thư mục .npy: {features_dir}\n"
            "Chỉ định bằng --features-dir hoặc đặt env CLIP_FEATURES_DIR."
        )

    df = pd.read_parquet(CLIP_ROW_INDEX)
    fps = _timestamp_map()

    files = sorted(df["npy_file"].unique())
    if limit_videos:
        files = files[:limit_videos]

    tong, thieu_file, vector_hong = 0, [], 0
    buffer: list[dict] = []

    def xa():
        nonlocal tong
        if buffer:
            client.upsert(COLLECTION_NAME, buffer)
            tong += len(buffer)
            buffer.clear()

    for i, npy_name in enumerate(files, 1):
        path = features_dir / npy_name
        if not path.exists():
            thieu_file.append(npy_name)
            continue

        vecs = np.load(path)
        if vecs.ndim != 2 or vecs.shape[1] != CLIP_EMBEDDING_DIM:
            raise ValueError(
                f"{npy_name}: shape {vecs.shape} — chờ (n, {CLIP_EMBEDDING_DIM}). "
                "Sai chiều = sai model. Kiểm tra data/config/clip_model.py."
            )

        hang = df[df["npy_file"] == npy_name]
        if int(hang["local_row"].max()) >= len(vecs):
            raise ValueError(
                f"{npy_name}: clip_row_index trỏ tới hàng {int(hang['local_row'].max())} "
                f"nhưng file chỉ có {len(vecs)} hàng — bảng và features lệch nhau."
            )

        chon = vecs[hang["local_row"].to_numpy()]
        chon, hong = _normalize_rows(chon.astype(np.float32))
        vector_hong += hong

        for (_, r), v in zip(hang.iterrows(), chon):
            num, den = fps.get(r["video_id"], (0, 1))
            ts = int(r["frame_idx"] * 1000 * den / num) if num else 0
            buffer.append({
                "keyframe_id": r["kf_id"],
                "video_id": r["video_id"],
                "frame_idx": int(r["frame_idx"]),
                "timestamp_ms": ts,
                "embedding": v.tolist(),
            })
            if len(buffer) >= BATCH:
                xa()

        if i % 50 == 0:
            print(f"  {i}/{len(files)} file · đã nạp {tong + len(buffer)} vector")

    xa()
    # Milvus mặc định consistency "Bounded": không flush thì query ngay sau đó
    # có thể chưa thấy dữ liệu vừa ghi (tương tự indices.refresh của ES).
    client.flush(COLLECTION_NAME)

    if thieu_file:
        print(f"[cảnh báo] thiếu {len(thieu_file)} file .npy, vd: {thieu_file[:3]}")
    if vector_hong:
        print(f"[cảnh báo] {vector_hong} vector có norm = 0 (không có hướng) — "
              "kiểm tra lại data nguồn.")

    print(f"Đã nạp {tong} vector vào '{COLLECTION_NAME}'.")
    return {"n_vectors": tong, "n_files": len(files) - len(thieu_file),
            "missing_files": len(thieu_file), "zero_vectors": vector_hong}


# ------------------------------------------------------------------ meta + assert

def write_meta(stats: dict, features_dir: Path) -> Path:
    """Ghi .meta.json cạnh dữ liệu dẫn xuất — dấu vân tay của index vừa nạp."""
    meta = {
        "collection": COLLECTION_NAME,
        "model_btc": CLIP_BTC_MODEL_NAME,
        "model_open_clip": CLIP_MODEL_NAME,
        "pretrained": CLIP_PRETRAINED,
        "dim": CLIP_EMBEDDING_DIM,
        "metric": METRIC,
        "normalized": True,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": _git_commit(),
        "features_dir": str(features_dir),
        "row_index": str(CLIP_ROW_INDEX.relative_to(REPO_ROOT)),
        **stats,
    }
    META_PATH.parent.mkdir(parents=True, exist_ok=True)
    META_PATH.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Đã ghi {META_PATH.relative_to(REPO_ROOT)}")
    return META_PATH


def assert_index_meta(strict: bool = True) -> dict | None:
    """So .meta.json với config hiện tại. Lệch → RuntimeError.

    Gọi ở đường query (search.py) trước khi tin bất kỳ kết quả vector nào.
    Vì sao gãy to thay vì cảnh báo: index nạp bằng model A mà query encode bằng
    model B thì Milvus VẪN trả top-k, điểm vẫn 0.2–0.3 như bình thường — không
    có cách nào nhận ra bằng mắt. Thà mất nguồn vector còn hơn tin số sai.

    strict=False: chưa có meta (chưa nạp features thật) thì chỉ trả None.
    """
    if not META_PATH.exists():
        if strict:
            raise RuntimeError(
                f"Chưa có {META_PATH.name} — index chưa nạp bằng loader A1.0a. "
                "Chạy: python -m backend.indexing.load_clip"
            )
        return None

    meta = json.loads(META_PATH.read_text(encoding="utf-8"))
    lech = []
    for khoa, dang_dung in (
        ("model_open_clip", CLIP_MODEL_NAME),
        ("pretrained", CLIP_PRETRAINED),
        ("dim", CLIP_EMBEDDING_DIM),
        ("metric", METRIC),
    ):
        if meta.get(khoa) != dang_dung:
            lech.append(f"{khoa}: index={meta.get(khoa)!r} vs config={dang_dung!r}")

    if lech:
        raise RuntimeError(
            "INDEX VÀ CONFIG KHÔNG CÙNG KHÔNG GIAN VECTOR — kết quả search sẽ SAI "
            "mà không báo lỗi.\n  " + "\n  ".join(lech)
            + f"\nNạp lại: python -m backend.indexing.load_clip --recreate\n"
            f"(index nạp lúc {meta.get('built_at')}, commit {meta.get('git_commit')})"
        )
    return meta


def verify_norms(client: MilvusClient, n: int = 20) -> bool:
    """Kiểm chứng CHẠY ĐƯỢC: lấy mẫu vector từ Milvus, |v| phải ≈ 1 (bất biến 1)."""
    rows = client.query(
        COLLECTION_NAME, filter="", limit=n, output_fields=["keyframe_id", "embedding"]
    )
    if not rows:
        print("Collection rỗng — chưa có gì để kiểm.")
        return False

    norms = [float(np.linalg.norm(np.asarray(r["embedding"], dtype=np.float32))) for r in rows]
    xau = [(r["keyframe_id"], n_) for r, n_ in zip(rows, norms) if abs(n_ - 1.0) > NORM_TOL]
    print(f"Kiểm norm trên {len(rows)} mẫu: min={min(norms):.6f} max={max(norms):.6f}")
    if xau:
        print(f"  ✗ {len(xau)} vector chưa chuẩn hoá, vd: {xau[:3]}")
        return False
    print(f"  ✓ mọi vector có |v| ≈ 1 (sai số ≤ {NORM_TOL}) — cùng thang với query encoder")
    return True


# ------------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description="Nạp CLIP features BTC vào Milvus (A1.0a)")
    ap.add_argument("--features-dir", help="thư mục .npy của BTC")
    ap.add_argument("--recreate", action="store_true", help="xoá collection cũ rồi nạp lại")
    ap.add_argument("--limit-videos", type=int, help="chỉ nạp N file .npy đầu (để thử)")
    ap.add_argument("--verify-only", action="store_true", help="chỉ kiểm index đã có, không nạp")
    args = ap.parse_args()

    client = connect()

    if args.verify_only:
        meta = assert_index_meta(strict=False)
        print(f"meta: {meta if meta else '(chưa có — index chưa nạp bằng loader này)'}")
        return 0 if verify_norms(client) else 1

    features_dir = _features_dir(args.features_dir)
    print(f"features: {features_dir}")

    create_collection(client, recreate=args.recreate)
    stats = load(client, features_dir, limit_videos=args.limit_videos)
    write_meta(stats, features_dir)

    print("\n--- kiểm chứng sau khi nạp ---")
    ok = verify_norms(client)
    assert_index_meta()  # meta vừa ghi phải khớp config — bắt lỗi ghi sai ngay
    print("assert_index_meta: ✓ index khớp data/config/clip_model.py")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
