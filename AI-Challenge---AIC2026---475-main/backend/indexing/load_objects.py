# backend/indexing/load_objects.py — Task 1.3: nạp Objects vào Elasticsearch
#
# Data BTC: FasterRCNN + InceptionResNetV2, nhãn OpenImages V4 (tiếng Anh),
# tối đa 100 object / 600 loại mỗi keyframe (CLAUDE.md mục 3).
#
# Vì sao lưu SONG SONG 2 dạng cho cùng một thông tin?
# 1. `labels` (mảng keyword phẳng): truy vấn "keyframe nào có airplane?" chỉ là
#    1 term query — rẻ nhất có thể, dùng làm bộ lọc nhanh khi fusion (Task 2.2).
# 2. `detections` (nested {label, score}): khi cần chất lượng, lọc được
#    "airplane VỚI score >= 0.8". Không dùng nested thì ES trộn 2 mảng
#    labels/scores rời nhau → không biết score nào thuộc label nào.
# Trả giá: index to hơn chút — chấp nhận, vì tốc độ truy vấn quan trọng hơn
# (cuộc thi trừ điểm theo thời gian).
#
# Vì sao normalizer lowercase cho label?
# → Người dùng gõ "airplane", data BTC ghi "Airplane" — normalizer đưa cả hai
#   về chữ thường lúc index lẫn lúc query → match không phân biệt hoa thường.
#
# Chạy (từ thư mục gốc repo, sau khi `docker compose up -d`):
#     python -m backend.indexing.load_objects                    # nạp + query thử "airplane"
#     python -m backend.indexing.load_objects --find airplane    # tìm keyframe theo object
#     python -m backend.indexing.load_objects --find airplane --min-score 0.9
#     python -m backend.indexing.load_objects --recreate         # xoá index cũ, nạp lại

import argparse
import json
from pathlib import Path

from elasticsearch import Elasticsearch, helpers

from backend.indexing.es_client import connect

INDEX_NAME = "objects"

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_FILE = REPO_ROOT / "data" / "sample" / "objects.json"

INDEX_BODY = {
    "mappings": {
        "properties": {
            "keyframe_id": {"type": "keyword"},
            "video_id": {"type": "keyword"},
            # Dạng 1: mảng phẳng — lọc nhanh "có object X hay không"
            "labels": {"type": "keyword", "normalizer": "lowercase"},
            # Dạng 2: nested — giữ đúng cặp (label, score) để lọc theo ngưỡng
            "detections": {
                "type": "nested",
                "properties": {
                    "label": {"type": "keyword", "normalizer": "lowercase"},
                    "score": {"type": "float"},
                },
            },
        }
    }
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
    # `labels` suy ra từ `detections` ngay lúc nạp — file nguồn không phải
    # lặp lại thông tin, tránh 2 dạng lệch nhau
    actions = (
        {
            "_index": INDEX_NAME,
            "_id": r["keyframe_id"],  # idempotent: chạy lại là ghi đè, không trùng
            "_source": {**r, "labels": [d["label"] for d in r["detections"]]},
        }
        for r in records
    )
    ok, _ = helpers.bulk(es, actions)
    es.indices.refresh(index=INDEX_NAME)
    print(f"Đã nạp {ok}/{len(records)} keyframe từ {data_file.name}.")
    return ok


def find_by_object(
    es: Elasticsearch, label: str, min_score: float = 0.0, size: int = 10
) -> list[dict]:
    """Tìm keyframe chứa object `label` (score >= min_score), xếp theo score giảm dần.

    Dùng nested query để score trong kết quả là score CỦA ĐÚNG object đó
    (score_mode=max), không phải điểm text-match vô nghĩa.
    """
    body = {
        "query": {
            "nested": {
                "path": "detections",
                "query": {
                    "bool": {
                        "filter": [
                            {"term": {"detections.label": label}},
                            {"range": {"detections.score": {"gte": min_score}}},
                        ],
                        # function_score lấy chính detection score làm điểm xếp hạng
                        "must": [
                            {
                                "function_score": {
                                    "field_value_factor": {"field": "detections.score"},
                                    "boost_mode": "replace",
                                }
                            }
                        ],
                    }
                },
                "score_mode": "max",
            }
        },
        "size": size,
    }
    hits = es.search(index=INDEX_NAME, **body)["hits"]["hits"]
    return [
        {
            "keyframe_id": h["_source"]["keyframe_id"],
            "video_id": h["_source"]["video_id"],
            "score": round(h["_score"], 3),
        }
        for h in hits
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Nạp object detections vào Elasticsearch")
    parser.add_argument("--file", type=Path, default=DEFAULT_DATA_FILE, help="file JSON objects")
    parser.add_argument("--recreate", action="store_true", help="xoá index cũ trước khi nạp")
    parser.add_argument("--find", metavar="LABEL", help="chỉ tìm theo object, không nạp lại data")
    parser.add_argument("--min-score", type=float, default=0.0, help="ngưỡng score tối thiểu")
    args = parser.parse_args()

    es = connect()

    if args.find is None:
        create_index(es, recreate=args.recreate)
        load(es, args.file)
        label = "airplane"  # query thử theo yêu cầu Task 1.3
    else:
        label = args.find

    print(f'\nKeyframe có object "{label}" (min_score={args.min_score}):')
    results = find_by_object(es, label, min_score=args.min_score)
    if not results:
        print("  (không có kết quả)")
    for r in results:
        print(f"  {r['score']:>6}  {r['keyframe_id']}  (video {r['video_id']})")


if __name__ == "__main__":
    main()
