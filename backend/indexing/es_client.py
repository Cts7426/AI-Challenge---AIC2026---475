# backend/indexing/es_client.py — kết nối Elasticsearch dùng chung
#
# Vì sao tách riêng? Mọi loader (metadata, objects, sau này ocr/asr) đều cần
# kết nối y hệt nhau. Gom về 1 chỗ → đổi địa chỉ/timeout chỉ sửa 1 file,
# đúng tinh thần adapter như llm() (CLAUDE.md mục 2).

import os

from elasticsearch import Elasticsearch

# Không hardcode địa chỉ (CLAUDE.md mục 7) — đổi máy/port chỉ cần set env ES_URL
# Fix cho Mac: Dùng 127.0.0.1 thay vì localhost để tránh lỗi IPv6 ::1 của urllib3
ES_URL = os.environ.get("ES_URL", "http://127.0.0.1:9200")

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
    """Kết nối ES, và khi hỏng thì nói ĐÚNG nguyên nhân.

    ⚠️ SỬA 16/08. Bản trước mọi lỗi đều ra một câu "Đã chạy `docker compose up -d`
    chưa?". Đo thật hôm nay: container ES **đang chạy hoàn toàn bình thường**
    (8.13.4, trả JSON qua curl), nhưng client cài nhầm major 9.5.0 nên ES từ chối
    header:

        media_type_header_exception — Accept version must be either version 8 or 7,
        but found 9

    `es.ping()` nuốt lỗi này thành `False`, rồi thông báo đẩy người vận hành đi
    khởi động lại docker — thứ đã chạy sẵn. Lúc thi mỗi câu chỉ có 6 phút; đuổi
    người ta sai hướng còn tệ hơn không báo gì.

    `backend/requirements.txt` ghi đúng `elasticsearch>=8.13,<9`; môi trường lệch
    là do venv được nâng cấp sau, không phải do file requirements sai.
    """
    es = Elasticsearch(ES_URL, request_timeout=30)
    if es.ping():
        return es

    chi_tiet = ""
    try:
        es.info()
    except Exception as e:
        chi_tiet = f"{type(e).__name__}: {e}"

    # Server sống nhưng từ chối client → lệch major, KHÔNG phải chưa bật docker
    if "media_type_header_exception" in chi_tiet or "Accept version must be" in chi_tiet:
        import elasticsearch as _es_pkg

        raise ConnectionError(
            f"Elasticsearch tại {ES_URL} ĐANG CHẠY nhưng từ chối client: lệch phiên bản.\n"
            f"  client python : {'.'.join(map(str, _es_pkg.__version__))}\n"
            f"  server yêu cầu: major 7 hoặc 8 (docker-compose.yml dùng 8.13.4)\n"
            "  Sửa: pip install 'elasticsearch>=8.13,<9'   "
            "(backend/requirements.txt đã ghi đúng ràng buộc này)\n"
            f"  Chi tiết: {chi_tiet}"
        )

    raise ConnectionError(
        f"Không kết nối được Elasticsearch tại {ES_URL}. "
        "Đã chạy `docker compose up -d` chưa? (container cần ~30s để lên)"
        + (f"\n  Chi tiết: {chi_tiet}" if chi_tiet else "")
    )
