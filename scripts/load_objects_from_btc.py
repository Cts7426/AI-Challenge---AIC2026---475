# scripts/load_objects_from_btc.py — nạp objects THẬT của BTC vào ES (data/raw/btc/objects)
#
# backend/indexing/load_objects.py chỉ đọc ĐÚNG 1 file JSON (mảng record) —
# dữ liệu BTC thật lại là 177.321 file rời, mỗi file 1 keyframe
# (data/raw/btc/objects/<video_id>/<ordinal>.json). Script này chỉ lo phần
# CHUYỂN ĐỊNH DẠNG + nạp hàng loạt; index/mapping vẫn tái dùng NGUYÊN VẸN
# create_index() của load_objects.py — một schema ES objects DUY NHẤT.
#
# ===== keyframe_id suy ra từ tên file — ĐÃ ĐỐI CHIẾU frame_map.parquet =====
# `data/raw/btc/objects/L25_V064/001.json` ↔ frame_map.parquet: kf_id
# "L25_V064#k0001", btc_ordinal=1 — ordinal trong tên file (3 chữ số) khớp
# đúng btc_ordinal, kf_id = "{video_id}#k{ordinal:04d}" (4 chữ số, có "#k").
# Đây là khoá join DUY NHẤT (CLAUDE.md bất biến 2) — sai định dạng ở đây thì
# nhánh `objects` không bao giờ khớp được với Milvus/OCR dù chạy không lỗi.
#
# Field `detection_class_entities` dùng làm label (tên người đọc được, tiếng
# Anh, kiểu "Man"/"Clothing") — KHÔNG dùng detection_class_names (mã /m/xxx
# của Google Knowledge Graph, không phải nhãn text tìm kiếm được).
#
# Chạy (cần Docker ES sống):
#   python scripts/load_objects_from_btc.py                  # nạp toàn bộ
#   python scripts/load_objects_from_btc.py --limit 500       # nạp thử 500 keyframe
#   python scripts/load_objects_from_btc.py --recreate

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from elasticsearch import helpers

from backend.indexing.es_client import connect
from backend.indexing.load_objects import INDEX_NAME, create_index

REPO_ROOT = Path(__file__).resolve().parents[1]
OBJECTS_RAW_DIR = REPO_ROOT / "data" / "raw" / "btc" / "objects"
BATCH_SIZE = 2000


def _records(limit: int | None) -> "collections.abc.Iterator[dict]":
    n = 0
    for video_dir in sorted(OBJECTS_RAW_DIR.iterdir()):
        if not video_dir.is_dir():
            continue
        video_id = video_dir.name
        for f in sorted(video_dir.glob("*.json")):
            if limit is not None and n >= limit:
                return
            ordinal = int(f.stem)  # "001.json" → 1 — khớp btc_ordinal của frame_map
            keyframe_id = f"{video_id}#k{ordinal:04d}"
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"  [cảnh báo] bỏ qua {f} — JSON hỏng: {e}")
                continue
            entities = d.get("detection_class_entities", [])
            scores = d.get("detection_scores", [])
            detections = [
                {"label": ent, "score": float(sc)}
                for ent, sc in zip(entities, scores)
            ]
            yield {
                "keyframe_id": keyframe_id,
                "video_id": video_id,
                "detections": detections,
                "labels": [dd["label"] for dd in detections],
            }
            n += 1


def main() -> None:
    ap = argparse.ArgumentParser(description="Nạp objects THẬT của BTC (raw JSON) vào ES")
    ap.add_argument("--recreate", action="store_true")
    ap.add_argument("--limit", type=int, default=None, help="chỉ nạp N keyframe đầu (test nhanh)")
    args = ap.parse_args()

    if not OBJECTS_RAW_DIR.exists():
        raise SystemExit(f"Không tìm thấy {OBJECTS_RAW_DIR} — cần tải data/raw/btc/objects trước.")

    es = connect()
    create_index(es, recreate=args.recreate)  # mapping DUY NHẤT, tái dùng nguyên vẹn

    def _actions():
        for r in _records(args.limit):
            yield {"_index": INDEX_NAME, "_id": r["keyframe_id"], "_source": r}

    t0 = time.perf_counter()
    ok, errors = helpers.bulk(es, _actions(), chunk_size=BATCH_SIZE, raise_on_error=False)
    es.indices.refresh(index=INDEX_NAME)
    ms = (time.perf_counter() - t0) * 1000
    n_err = len(errors) if isinstance(errors, list) else errors
    print(f"Đã nạp {ok} keyframe vào index '{INDEX_NAME}' ({ms:.0f} ms, {n_err} lỗi).")


if __name__ == "__main__":
    main()
