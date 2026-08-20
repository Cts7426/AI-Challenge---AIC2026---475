# backend/indexing/load_ocr.py — Task 4.1: nạp kết quả OCR vào ES index `ocr`
#
# Input: `data/derived/ocr.parquet` do Data Factory (B-series) giao —
# cột: kf_id · video_id · frame_idx · text_raw · text_clean · n_boxes · avg_conf.
#
# ⚠️ SỬA 19/08: mặc định TRỎ NHẦM `data/sample/ocr_results.jsonl` (file mẫu cũ,
# schema cũ `keyframe_id`/`text`) trong khi load() đã đổi sang đọc PARQUET. Chạy
# `python -m backend.indexing.load_ocr` không tham số là gặp:
#     ArrowInvalid: Parquet magic bytes not found in footer
# — thông báo của pyarrow không hề nhắc tới việc mình đang đọc nhầm file, nên
# _kiem_file() dưới đây kiểm trước và nói thẳng nguyên nhân.
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
DEFAULT_DATA_FILE = REPO_ROOT / "data" / "derived" / "ocr.parquet"

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


# Cột BẮT BUỘC của ocr.parquet. Thiếu cột nào thì hỏng to ngay, đừng nạp một
# index rỗng rồi để search âm thầm mất một nguồn.
COT_BAT_BUOC = ("kf_id", "video_id", "text_clean")


def _kiem_file(data_file: Path) -> None:
    """Kiểm ĐÚNG LOẠI FILE trước khi đưa cho pyarrow.

    Vì sao cần: pyarrow báo "Parquet magic bytes not found in footer. Either the
    file is corrupted or this is not a parquet file" — câu đó đẩy người đọc đi
    tìm file hỏng, trong khi nguyên nhân thật là ĐƯA NHẦM FILE. Lúc thi mỗi phút
    đều đắt; chẩn đoán sai hướng còn tệ hơn không chẩn đoán.
    """
    if not data_file.exists():
        raise SystemExit(
            f"Không thấy {data_file}.\n"
            "  Data Factory giao file này ở data/derived/ocr.parquet — chưa có thì "
            "chạy job OCR (preprocessing/ocr_job.py, Colab/Kaggle) trước."
        )
    if data_file.suffix.lower() != ".parquet":
        raise SystemExit(
            f"{data_file} không phải .parquet — loader này đọc PARQUET, không đọc JSONL.\n"
            f"  Dùng: python -m backend.indexing.load_ocr --file {DEFAULT_DATA_FILE}"
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
        text = str(r.get("text_clean", "")).strip()
        if not text:
            continue
            
        doc = {
            "keyframe_id": r["kf_id"],
            "video_id": r["video_id"],
            "text": text,
            "raw_text": str(r.get("text_raw", ""))
        }
        actions.append({
            "_index": INDEX_NAME, 
            "_id": r["kf_id"], 
            "_source": doc
        })
        
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
    parser.add_argument("--file", type=Path, default=DEFAULT_DATA_FILE, help="file parquet OCR (mặc định data/derived/ocr.parquet)")
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
