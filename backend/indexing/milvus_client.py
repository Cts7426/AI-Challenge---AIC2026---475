# backend/indexing/milvus_client.py — kết nối Milvus dùng chung
#
# Đối xứng với es_client.py: mọi nơi cần Milvus (load_clip khi nạp,
# retrieval/search.py khi truy vấn) đều lấy kết nối + tên collection từ đây.
# Đổi địa chỉ/tên collection chỉ sửa 1 file — đúng tinh thần adapter llm().
#
# Ghi chú cho dev không dùng Docker (Linux/macOS): MilvusClient nhận luôn
# đường dẫn file .db làm uri để chạy Milvus Lite in-process —
# MILVUS_URL=./milvus.db là chạy được, không sửa code.

import os

from pymilvus import MilvusClient

# Không hardcode địa chỉ (CLAUDE.md mục 7) — đổi máy/port chỉ cần set env
MILVUS_URL = os.environ.get("MILVUS_URL", "http://localhost:19530")

# Tên collection keyframe — khóa join keyframe_id nối Milvus ↔ ES (Bất biến 2)
COLLECTION_NAME = "keyframes"


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
