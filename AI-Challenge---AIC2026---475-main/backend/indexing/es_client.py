# backend/indexing/es_client.py — kết nối Elasticsearch dùng chung
#
# Vì sao tách riêng? Mọi loader (metadata, objects, sau này ocr/asr) đều cần
# kết nối y hệt nhau. Gom về 1 chỗ → đổi địa chỉ/timeout chỉ sửa 1 file,
# đúng tinh thần adapter như llm() (CLAUDE.md mục 2).

import os

from elasticsearch import Elasticsearch

# Không hardcode địa chỉ (CLAUDE.md mục 7) — đổi máy/port chỉ cần set env ES_URL
ES_URL = os.environ.get("ES_URL", "http://localhost:9200")


def connect() -> Elasticsearch:
    es = Elasticsearch(ES_URL, request_timeout=30)
    if not es.ping():
        raise ConnectionError(
            f"Không kết nối được Elasticsearch tại {ES_URL}. "
            "Đã chạy `docker compose up -d` chưa? (container cần ~30s để lên)"
        )
    return es
