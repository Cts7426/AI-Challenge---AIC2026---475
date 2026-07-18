# backend/indexing/load_clip.py — Task 1.4: nạp CLIP features vào Milvus
#
# Collection `keyframes`: keyframe_id (PK), video_id, timestamp_ms, embedding.
# Chiều vector đọc từ data/config/clip_model.py — thứ CHƯA chốt (CLAUDE.md mục 7),
# BTC xác nhận model CLIP thì chỉ sửa file config đó, code này không đổi.
#
# Vì sao metric COSINE?
# → CLIP so khớp ảnh-text bằng cosine similarity. Milvus COSINE trả score
#   trong [-1, 1], càng gần 1 càng giống — đọc kết quả là hiểu ngay.
#
# Vì sao index HNSW?
# → Nhanh nhất cho search real-time (cuộc thi TRỪ ĐIỂM THEO THỜI GIAN),
#   đổi lại tốn RAM hơn IVF. Với ~vài trăm nghìn vector 512d (~nửa GB) máy
#   16GB chịu được. M=16, efConstruction=200 là điểm cân bằng chuẩn.
#
# Vì sao upsert thay vì insert?
# → Chạy lại loader không sinh bản ghi trùng (idempotent) — cùng lý do
#   dùng _id trong các loader Elasticsearch.
#
# Format dữ liệu vào (theo cấu trúc data mẫu, chờ BTC chốt format thật):
#   - keyframes.json: [{keyframe_id, video_id, frame_index, timestamp_ms}]
#   - clip_features/<video_id>.npy: hàng i = vector của keyframe thứ i của video đó
#
# Chạy (từ thư mục gốc repo, sau khi `docker compose up -d milvus`):
#     python data/sample/generate_clip_features.py     # sinh features giả lập (1 lần)
#     python -m backend.indexing.load_clip             # tạo collection + nạp + search thử
#     python -m backend.indexing.load_clip --recreate  # xoá collection cũ, nạp lại

import argparse
import json
import os
from pathlib import Path

import numpy as np
from pymilvus import DataType, MilvusClient

from data.config.clip_model import CLIP_EMBEDDING_DIM

# Không hardcode địa chỉ (CLAUDE.md mục 7)
MILVUS_URL = os.environ.get("MILVUS_URL", "http://localhost:19530")
COLLECTION_NAME = "keyframes"

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_KEYFRAMES_FILE = REPO_ROOT / "data" / "sample" / "keyframes.json"
DEFAULT_FEATURES_DIR = REPO_ROOT / "data" / "sample" / "clip_features"


def connect() -> MilvusClient:
    try:
        client = MilvusClient(uri=MILVUS_URL)
        client.list_collections()  # ép 1 request thật để biết server sống hay chết
        return client
    except Exception as e:
        raise ConnectionError(
            f"Không kết nối được Milvus tại {MILVUS_URL}. "
            "Đã chạy `docker compose up -d milvus` chưa? (Milvus cần ~60-90s để lên)"
        ) from e


def create_collection(client: MilvusClient, recreate: bool = False) -> None:
    if client.has_collection(COLLECTION_NAME):
        if not recreate:
            return
        client.drop_collection(COLLECTION_NAME)
        print(f"Đã xoá collection cũ '{COLLECTION_NAME}'.")

    schema = MilvusClient.create_schema(auto_id=False)
    schema.add_field("keyframe_id", DataType.VARCHAR, is_primary=True, max_length=64)
    schema.add_field("video_id", DataType.VARCHAR, max_length=32)
    schema.add_field("timestamp_ms", DataType.INT64)
    schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=CLIP_EMBEDDING_DIM)

    index_params = MilvusClient.prepare_index_params()
    index_params.add_index(
        field_name="embedding",
        index_type="HNSW",
        metric_type="COSINE",
        params={"M": 16, "efConstruction": 200},
    )

    client.create_collection(COLLECTION_NAME, schema=schema, index_params=index_params)
    print(f"Đã tạo collection '{COLLECTION_NAME}' (dim={CLIP_EMBEDDING_DIM}, HNSW/COSINE).")


def load(client: MilvusClient, keyframes_file: Path, features_dir: Path) -> int:
    keyframes = json.loads(keyframes_file.read_text(encoding="utf-8"))

    # Gom theo video GIỮ THỨ TỰ file — hàng i của .npy = keyframe thứ i của video
    by_video: dict[str, list[dict]] = {}
    for kf in keyframes:
        by_video.setdefault(kf["video_id"], []).append(kf)

    rows: list[dict] = []
    for video_id, kfs in by_video.items():
        npy_path = features_dir / f"{video_id}.npy"
        if not npy_path.exists():
            print(f"BỎ QUA {video_id}: thiếu {npy_path.name} "
                  "(chạy python data/sample/generate_clip_features.py chưa?)")
            continue
        vectors = np.load(npy_path)
        if vectors.shape != (len(kfs), CLIP_EMBEDDING_DIM):
            raise ValueError(
                f"{npy_path.name} shape {vectors.shape} không khớp "
                f"({len(kfs)} keyframe, dim {CLIP_EMBEDDING_DIM}). "
                "Kiểm tra lại CLIP_EMBEDDING_DIM trong data/config/clip_model.py."
            )
        rows.extend(
            {
                "keyframe_id": kf["keyframe_id"],
                "video_id": video_id,
                "timestamp_ms": kf["timestamp_ms"],
                "embedding": vec.tolist(),
            }
            for kf, vec in zip(kfs, vectors)
        )

    # Với data thật (hàng trăm nghìn vector) phải chia batch để không phình RAM
    # và không vượt giới hạn 1 request gRPC (~64MB)
    BATCH = 5000
    total = 0
    for i in range(0, len(rows), BATCH):
        client.upsert(COLLECTION_NAME, rows[i : i + BATCH])
        total += len(rows[i : i + BATCH])
    # Milvus mặc định consistency "Bounded": bản ghi vừa ghi có thể chưa nhìn
    # thấy ngay khi query. flush ép dữ liệu hiện hình để search được liền —
    # tương tự indices.refresh() bên Elasticsearch.
    client.flush(COLLECTION_NAME)
    print(f"Đã nạp {total} vector vào '{COLLECTION_NAME}'.")
    return total


def search_similar(client: MilvusClient, keyframe_id: str, top_k: int = 4) -> list[dict]:
    """Smoke test: lấy vector của 1 keyframe có sẵn, tìm hàng xóm gần nhất.

    Chưa có query encoder (Task 2.1) nên đây là cách kiểm chứng không cần model:
    kết quả ĐÚNG phải có (1) chính nó đứng đầu với score ≈ 1.0,
    (2) các hạng kế tiếp là keyframe cùng video (data giả lập sinh chúng gần nhau).
    """
    hit = client.query(
        COLLECTION_NAME,
        filter=f'keyframe_id == "{keyframe_id}"',
        output_fields=["embedding"],
    )
    if not hit:
        raise ValueError(f"Không tìm thấy keyframe {keyframe_id} trong collection.")

    results = client.search(
        COLLECTION_NAME,
        data=[hit[0]["embedding"]],
        limit=top_k,
        output_fields=["video_id", "timestamp_ms"],
        search_params={"params": {"ef": 64}},
    )
    return [
        {
            "keyframe_id": r["id"],
            "video_id": r["entity"]["video_id"],
            "timestamp_ms": r["entity"]["timestamp_ms"],
            "score": round(r["distance"], 3),
        }
        for r in results[0]
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Nạp CLIP features vào Milvus")
    parser.add_argument("--keyframes", type=Path, default=DEFAULT_KEYFRAMES_FILE)
    parser.add_argument("--features-dir", type=Path, default=DEFAULT_FEATURES_DIR)
    parser.add_argument("--recreate", action="store_true", help="xoá collection cũ trước khi nạp")
    parser.add_argument("--similar", metavar="KEYFRAME_ID",
                        help="chỉ search hàng xóm của keyframe này, không nạp lại")
    args = parser.parse_args()

    client = connect()

    if args.similar is None:
        create_collection(client, recreate=args.recreate)
        load(client, args.keyframes, args.features_dir)
        probe = "L03_V001_0007"  # keyframe máy bay — kỳ vọng hàng xóm cùng video
    else:
        probe = args.similar

    print(f"\nHàng xóm gần nhất của {probe} (COSINE, càng gần 1 càng giống):")
    for r in search_similar(client, probe):
        marker = " ← chính nó" if r["keyframe_id"] == probe else ""
        print(f"  {r['score']:>6}  {r['keyframe_id']}  (video {r['video_id']}, "
              f"t={r['timestamp_ms']}ms){marker}")


if __name__ == "__main__":
    main()
