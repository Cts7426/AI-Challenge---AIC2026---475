# backend/indexing/es_client.py — kết nối Elasticsearch dùng chung
#
# Vì sao tách riêng? Mọi loader (metadata, objects, sau này ocr/asr) đều cần
# kết nối y hệt nhau. Gom về 1 chỗ → đổi địa chỉ/timeout chỉ sửa 1 file,
# đúng tinh thần adapter như llm() (CLAUDE.md mục 2).

import os

from elasticsearch import Elasticsearch

# Không hardcode địa chỉ (CLAUDE.md mục 7) — đổi máy/port chỉ cần set env ES_URL
ES_URL = os.environ.get("ES_URL", "http://localhost:9200")

# Bộ phân tích tiếng Việt dùng chung cho mọi index có text VI (metadata, ocr):
# asciifolding đưa văn bản lẫn query về không dấu → gõ vội thiếu dấu vẫn match;
# subfield .vi giữ nguyên dấu, được boost cao hơn khi query CÓ dấu.
VI_FOLDED_ANALYSIS = {
    "analysis": {
        "analyzer": {
            "vi_folded": {
                "tokenizer": "standard",
                "filter": ["lowercase", "asciifolding"],
            }
        }
    }
}


def searchable_text() -> dict:
    """Mapping cho 1 field text tiếng Việt: bỏ dấu mặc định + subfield .vi giữ dấu."""
    return {
        "type": "text",
        "analyzer": "vi_folded",
        "fields": {"vi": {"type": "text", "analyzer": "standard"}},
    }


def connect() -> Elasticsearch:
    es = Elasticsearch(ES_URL, request_timeout=30)
    if not es.ping():
        raise ConnectionError(
            f"Không kết nối được Elasticsearch tại {ES_URL}. "
            "Đã chạy `docker compose up -d` chưa? (container cần ~30s để lên)"
        )
    return es
