# backend/indexing/load_ocr.py — Task 4.1: nạp kết quả OCR vào ES index `ocr`
#
# Input: file JSONL từ preprocessing/ocr_job.py (chạy trên Colab/Kaggle),
# mỗi dòng {"keyframe_id", "video_id", "text", "raw_text"}.
#
# Index dùng CHUNG bộ analyzer vi_folded với metadata (es_client.py):
# query không dấu vẫn match, có dấu được boost — một trải nghiệm thống nhất
# trên mọi nguồn text tiếng Việt.
#
# Nạp xong là nguồn `ocr` trong search fusion (Task 2.2) TỰ BẬT —
# search.py đã chờ sẵn index này, không phải sửa gì.
#
# Chạy:
#     python -m backend.indexing.load_ocr                      # nạp data mẫu + search thử
#     python -m backend.indexing.load_ocr --file data/ocr/ocr_results.jsonl
#     python -m backend.indexing.load_ocr --search "tỉ số 2-1"
#     python -m backend.indexing.load_ocr --recreate

import argparse
import json
from pathlib import Path

from elasticsearch import Elasticsearch, helpers

from backend.indexing.es_client import VI_FOLDED_ANALYSIS, connect, searchable_text

INDEX_NAME = "ocr"

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_FILE = REPO_ROOT / "data" / "sample" / "ocr_results.jsonl"

INDEX_BODY = {
    "settings": VI_FOLDED_ANALYSIS,
    "mappings": {
        "properties": {
            "keyframe_id": {"type": "keyword"},
            "video_id": {"type": "keyword"},
            "text": searchable_text(),          # bản đã sửa — field search chính
            "raw_text": {"type": "text", "index": False},  # chỉ lưu đối chiếu, không search
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
    records = []
    for line in data_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("text", "").strip():  # frame không chữ — khỏi nạp
            records.append(r)

    actions = (
        {"_index": INDEX_NAME, "_id": r["keyframe_id"], "_source": r} for r in records
    )
    ok, _ = helpers.bulk(es, actions)
    es.indices.refresh(index=INDEX_NAME)
    print(f"Đã nạp {ok}/{len(records)} bản ghi OCR từ {data_file.name}.")
    return ok


def search(es: Elasticsearch, query: str, size: int = 5) -> list[dict]:
    hits = es.search(
        index=INDEX_NAME,
        query={"multi_match": {"query": query, "fields": ["text.vi^2", "text"]}},
        size=size,
    )["hits"]["hits"]
    return [
        {
            "keyframe_id": h["_source"]["keyframe_id"],
            "text": h["_source"]["text"],
            "score": round(h["_score"], 2),
        }
        for h in hits
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Nạp kết quả OCR vào Elasticsearch")
    parser.add_argument("--file", type=Path, default=DEFAULT_DATA_FILE, help="file JSONL OCR")
    parser.add_argument("--recreate", action="store_true")
    parser.add_argument("--search", metavar="QUERY", help="chỉ search thử, không nạp")
    args = parser.parse_args()

    es = connect()

    if args.search is None:
        create_index(es, recreate=args.recreate)
        load(es, args.file)
        demo = "ti so 2-1"  # không dấu — chứng minh vi_folded hoạt động trên OCR
    else:
        demo = args.search

    print(f'\nKết quả search OCR "{demo}":')
    results = search(es, demo)
    if not results:
        print("  (không có kết quả)")
    for r in results:
        print(f"  {r['score']:>6}  {r['keyframe_id']}  “{r['text']}”")


if __name__ == "__main__":
    main()
