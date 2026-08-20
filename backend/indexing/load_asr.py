# backend/indexing/load_asr.py — Task 4.2: nạp transcript ASR vào ES index `asr`
#
# Input: `data/derived/asr.parquet` do Data Factory (B-series) giao —
# cột: video_id · seg_id · start_s · end_s · start_frame · end_frame · text_vi.
# (ES lưu mili giây, loader tự đổi start_s/end_s → start_ms/end_ms.)
#
# ⚠️ SỬA 19/08: y hệt lỗi của load_ocr.py — mặc định trỏ file JSONL mẫu cũ trong
# khi load() đã đổi sang đọc PARQUET, nên chạy không tham số là gặp
# `ArrowInvalid: Parquet magic bytes not found`. _kiem_file() nói thẳng nguyên nhân.
#
# Khác các index trước: đơn vị là ĐOẠN THỜI GIAN của video, không phải keyframe.
# Fusion (search.py) sẽ join theo thời gian: keyframe có timestamp nằm trong
# đoạn khớp query thì được cộng điểm.
#
# Chạy:
#     python -m backend.indexing.load_asr                    # nạp data/derived/asr.parquet
#     python -m backend.indexing.load_asr --file duong/dan/khac.parquet
#     python -m backend.indexing.load_asr --search "can pha penalty"
#     python -m backend.indexing.load_asr --recreate

import argparse
import json
from pathlib import Path

from elasticsearch import Elasticsearch, helpers

from backend.indexing.es_client import VI_FOLDED_ANALYSIS, connect, searchable_text

INDEX_NAME = "asr"

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_FILE = REPO_ROOT / "data" / "derived" / "asr.parquet"

# Cột BẮT BUỘC của asr.parquet — thiếu là hỏng to ngay, không nạp index rỗng
# rồi để search âm thầm mất nguồn ASR.
COT_BAT_BUOC = ("video_id", "start_s", "end_s", "text_vi")

INDEX_BODY = {
    "settings": VI_FOLDED_ANALYSIS,   # cùng bộ analyzer VI với metadata/ocr
    "mappings": {
        "properties": {
            "video_id": {"type": "keyword"},
            "start_ms": {"type": "long"},
            "end_ms": {"type": "long"},
            "text": searchable_text(),
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


def _kiem_file(data_file: Path) -> None:
    """Kiểm ĐÚNG LOẠI FILE trước khi đưa cho pyarrow — xem ghi chú đầu file."""
    if not data_file.exists():
        raise SystemExit(
            f"Không thấy {data_file}.\n"
            "  Data Factory giao file này ở data/derived/asr.parquet — chưa có thì "
            "chạy job ASR (preprocessing/asr_job.py, Colab/Kaggle) trước."
        )
    if data_file.suffix.lower() != ".parquet":
        raise SystemExit(
            f"{data_file} không phải .parquet — loader này đọc PARQUET, không đọc JSONL.\n"
            f"  Dùng: python -m backend.indexing.load_asr --file {DEFAULT_DATA_FILE}"
        )


def load(es: Elasticsearch, data_file: Path) -> int:
    import pandas as pd
    _kiem_file(data_file)
    df = pd.read_parquet(data_file)
    thieu = [c for c in COT_BAT_BUOC if c not in df.columns]
    if thieu:
        raise SystemExit(
            f"{data_file} thiếu cột {thieu} (đang có: {list(df.columns)}).\n"
            "  Data Factory đổi tên cột thì sửa COT_BAT_BUOC + hàm load() cho khớp."
        )
    records = df.to_dict(orient="records")
    
    actions = []
    for r in records:
        text = str(r.get("text_vi", "")).strip()
        if not text:
            continue
        # Convert start_s and end_s to milliseconds for ES
        start_ms = int(r["start_s"] * 1000)
        end_ms = int(r["end_s"] * 1000)
        
        doc = {
            "video_id": r["video_id"],
            "start_ms": start_ms,
            "end_ms": end_ms,
            "text": text
        }
        actions.append({
            "_index": INDEX_NAME,
            "_id": f'{r["video_id"]}_{start_ms}',
            "_source": doc,
        })
        
    ok, _ = helpers.bulk(es, actions)
    es.indices.refresh(index=INDEX_NAME)
    print(f"Đã nạp {ok}/{len(records)} đoạn ASR từ {data_file.name}.")
    return ok


def search(es: Elasticsearch, query: str, size: int = 5) -> list[dict]:
    hits = es.search(
        index=INDEX_NAME,
        query={"multi_match": {"query": query, "fields": ["text.vi^2", "text"]}},
        size=size,
    )["hits"]["hits"]
    return [
        {
            "video_id": h["_source"]["video_id"],
            "start_ms": h["_source"]["start_ms"],
            "end_ms": h["_source"]["end_ms"],
            "text": h["_source"]["text"],
            "score": round(h["_score"], 2),
        }
        for h in hits
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Nạp transcript ASR vào Elasticsearch")
    parser.add_argument("--file", type=Path, default=DEFAULT_DATA_FILE, help="file parquet ASR (mặc định data/derived/asr.parquet)")
    parser.add_argument("--recreate", action="store_true")
    parser.add_argument("--search", metavar="QUERY", help="chỉ search thử, không nạp")
    args = parser.parse_args()

    es = connect()

    if args.search is None:
        create_index(es, recreate=args.recreate)
        load(es, args.file)
        demo = "can pha penalty"  # không dấu — vi_folded phải match "cản phá penalty"
    else:
        demo = args.search

    print(f'\nKết quả search ASR "{demo}":')
    results = search(es, demo)
    if not results:
        print("  (không có kết quả)")
    for r in results:
        print(f"  {r['score']:>6}  {r['video_id']} [{r['start_ms']}–{r['end_ms']}ms]  “{r['text']}”")


if __name__ == "__main__":
    main()
