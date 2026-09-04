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


def _import_milvus_client_without_env_side_effect():
    """Import symbol PyMilvus nhưng không cho dependency tự nạp `.env` vào process.

    `pymilvus.settings` gọi `load_dotenv()` vô điều kiện. Nếu để nguyên, chỉ một
    deep health check cũng có thể đổi model LLM sau khi `run.py` đã chụp runtime
    fingerprint, làm checkpoint vừa ghi xong bị coi là hết hạn ở lần resume.
    """
    env_before = dict(os.environ)
    try:
        from pymilvus import DataType as data_type
        from pymilvus import MilvusClient as client_type
    finally:
        for key in set(os.environ) - set(env_before):
            os.environ.pop(key, None)
        os.environ.update(env_before)
    return client_type, data_type


MilvusClient, DataType = _import_milvus_client_without_env_side_effect()

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
