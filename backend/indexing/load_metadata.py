# backend/indexing/load_metadata.py — Task 1.2: nạp Metadata vào Elasticsearch
#
# Vì sao dùng video_id làm _id của document?
# → Loader chạy lại bao nhiêu lần cũng không sinh bản ghi trùng (idempotent):
#   ES ghi đè document cũ cùng _id thay vì tạo mới.
#
# Vì sao có analyzer `vi_folded` (asciifolding)?
# → Lúc thi gõ vội thường thiếu dấu ("dien bien phu" thay vì "Điện Biên Phủ").
#   asciifolding đưa cả văn bản lẫn query về dạng không dấu → vẫn match.
#   Mỗi field text có thêm subfield `.vi` (standard analyzer, giữ nguyên dấu)
#   được boost cao hơn → query CÓ dấu sẽ xếp kết quả đúng dấu lên trước.
#
# Chạy (từ thư mục gốc repo, sau khi `docker compose up -d`):
#     python -m backend.indexing.load_metadata                # tạo index + nạp + search thử
#     python -m backend.indexing.load_metadata --search "bong da viet nam"
#     python -m backend.indexing.load_metadata --recreate     # xoá index cũ, nạp lại từ đầu

import argparse
import json
from pathlib import Path

from elasticsearch import Elasticsearch, helpers

from backend.indexing.es_client import VI_FOLDED_ANALYSIS, connect, searchable_text

INDEX_NAME = "metadata"

# parents[2] = thư mục gốc repo (indexing → backend → gốc)
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_FILE = REPO_ROOT / "data" / "sample" / "metadata.json"

# Analyzer + mapping text VI định nghĩa chung ở es_client.py (index ocr dùng cùng bộ)
INDEX_BODY = {
    "settings": VI_FOLDED_ANALYSIS,
    "mappings": {
        "properties": {
            "video_id": {"type": "keyword"},          # lọc chính xác, không phân tích
            "title": searchable_text(),
            "description": searchable_text(),
            "keywords": searchable_text(),            # ES tự hiểu mảng string
            "publish_date": {                          # field lọc theo ngày
                "type": "date",
                "format": "yyyy-MM-dd||dd/MM/yyyy||epoch_millis",  # phòng BTC đổi format
            },
            "length": {"type": "integer"},            # giây — lọc video dài/ngắn
            "author": {"type": "keyword"},
            "channel_id": {"type": "keyword"},
            "watch_url": {"type": "keyword", "index": False},  # chỉ lưu, không ai search URL
        }
    },
}


def create_index(es: Elasticsearch, recreate: bool = False) -> None:
    if es.indices.exists(index=INDEX_NAME):
        if not recreate:
            return
        es.indices.delete(index=INDEX_NAME)
        print(f"Đã xoá index cũ '{INDEX_NAME}'.")
    es.indices.create(index=INDEX_NAME, **INDEX_BODY)
    print(f"Đã tạo index '{INDEX_NAME}'.")


def load(es: Elasticsearch, data_file: Path) -> int:
    records = json.loads(data_file.read_text(encoding="utf-8"))
    # helpers.bulk: gộp mọi document vào 1 request thay vì N request lẻ —
    # với data thật (hàng nghìn video) nhanh hơn nhiều lần
    actions = (
        {"_index": INDEX_NAME, "_id": r["video_id"], "_source": r} for r in records
    )
    ok, _ = helpers.bulk(es, actions)
    es.indices.refresh(index=INDEX_NAME)  # ép ES cập nhật ngay để search thấy liền
    print(f"Đã nạp {ok}/{len(records)} document từ {data_file.name}.")
    return ok


def search(es: Elasticsearch, query: str, size: int = 5) -> list[dict]:
    """Full-text search trên title/keywords/description, có và không dấu đều được."""
    body = {
        "query": {
            "multi_match": {
                "query": query,
                # Boost: title > keywords > description; bản .vi (đúng dấu) > bản bỏ dấu
                "fields": [
                    "title.vi^4", "title^3",
                    "keywords.vi^3", "keywords^2",
                    "description.vi^2", "description",
                ],
            }
        },
        "size": size,
    }
    hits = es.search(index=INDEX_NAME, **body)["hits"]["hits"]
    return [
        {"video_id": h["_source"]["video_id"], "title": h["_source"]["title"], "score": round(h["_score"], 2)}
        for h in hits
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Nạp metadata video vào Elasticsearch")
    parser.add_argument("--file", type=Path, default=DEFAULT_DATA_FILE, help="file JSON metadata")
    parser.add_argument("--recreate", action="store_true", help="xoá index cũ trước khi nạp")
    parser.add_argument("--search", metavar="QUERY", help="chỉ search thử, không nạp lại data")
    args = parser.parse_args()

    es = connect()

    if args.search is None:
        create_index(es, recreate=args.recreate)
        load(es, args.file)
        demo_query = "dien bien phu"  # cố tình KHÔNG dấu để chứng minh asciifolding
    else:
        demo_query = args.search

    print(f'\nKết quả search "{demo_query}":')
    results = search(es, demo_query)
    if not results:
        print("  (không có kết quả)")
    for r in results:
        print(f"  {r['score']:>6}  {r['video_id']}  {r['title']}")


if __name__ == "__main__":
    main()
