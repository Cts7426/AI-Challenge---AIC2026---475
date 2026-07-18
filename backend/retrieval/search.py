# backend/retrieval/search.py — Task 2.2 + 4.2: search song song + hợp nhất điểm
#
# Đường đi một query:
#   query VI ──llm()──> query EN
#      ├─ (a) CLIP encode EN → Milvus vector search      (tín hiệu chính, mức KEYFRAME)
#      ├─ (b) ES full-text VI trên `metadata`            (mức VIDEO)
#      ├─ (c) ES match EN trên `objects.labels.txt`      (mức KEYFRAME)
#      ├─ (d) ES full-text VI trên `ocr`                 (mức KEYFRAME)
#      └─ (e) ES full-text VI trên `asr`                 (mức ĐOẠN THỜI GIAN)
#   → hợp nhất: chuẩn hoá điểm từng nguồn về (0,1] → weighted sum → top-K
#
# ASR đặc biệt ở 2 điểm (Task 4.2):
# 1. JOIN THEO THỜI GIAN: đoạn nói khớp query cộng điểm cho keyframe có
#    timestamp rơi TRONG đoạn đó (± pad — lời bình lệch hình vài giây là thường).
# 2. ĐỀ CỬ ứng viên: các đoạn khớp nhất được tra Milvus lấy keyframe nằm trong
#    khoảng thời gian đó — query thuần lời nói ("bình luận viên hô vào...")
#    vẫn ra ứng viên dù vector/objects không bắt được gì.
#
# Vì sao query metadata/ocr/asr bằng TIẾNG VIỆT còn objects bằng TIẾNG ANH?
# → mỗi nguồn search bằng đúng ngôn ngữ dữ liệu của nó thì BM25 mới match.
#
# Vì sao chuẩn hoá CHIA-CHO-MAX từng nguồn trước khi cộng?
# → thang điểm khác nhau (COSINE [-1,1], BM25 không chặn trên) — cộng thẳng là
#   nguồn BM25 nuốt hết. Chia-cho-max giữ tỉ lệ nội bộ, không ép hit yếu về 0
#   như min-max (bài học từ lúc test Task 2.2).
#
# Mỗi nguồn bọc try/except trả rỗng: 1 service chết → search "cà nhắc" chạy tiếp.
#
# Chạy thử (cần docker compose up -d; nạp đủ loader):
#     python -m backend.retrieval.search "thủ môn cản phá penalty" --en "goalkeeper saves penalty"
#     python -m backend.retrieval.search "máy bay ở sân bay" --en "an airplane at the airport"
#   (--en = bản dịch thủ công khi chưa set ANTHROPIC_API_KEY)

import argparse
from concurrent.futures import ThreadPoolExecutor

from backend.indexing.es_client import connect as es_connect
from backend.indexing.load_clip import COLLECTION_NAME, connect as milvus_connect
from backend.indexing.load_metadata import INDEX_NAME as METADATA_INDEX
from backend.indexing.load_objects import INDEX_NAME as OBJECTS_INDEX
from data.config.search_weights import (
    ASR_NOMINATE_SEGMENTS,
    ASR_TIME_PAD_MS,
    CANDIDATE_MULTIPLIER,
    FUSION_WEIGHTS,
)

OCR_INDEX = "ocr"  # tạo bởi load_ocr (4.1); chưa có → nguồn tự tắt
ASR_INDEX = "asr"  # tạo bởi load_asr (4.2); chưa có → nguồn tự tắt


# ---------------------------------------------------------------- từng nguồn

def _search_vector(query_en: str, limit: int) -> dict[str, dict]:
    """Milvus CLIP search → {keyframe_id: {score, video_id, timestamp_ms}}."""
    # Import lười: encode_text kéo theo torch (~vài giây import + RAM)
    from backend.retrieval.text_query import encode_text

    client = milvus_connect()
    hits = client.search(
        COLLECTION_NAME,
        data=[encode_text(query_en).tolist()],
        limit=limit,
        output_fields=["video_id", "timestamp_ms"],
        search_params={"params": {"ef": 128}},
    )
    return {
        h["id"]: {
            "score": h["distance"],
            "video_id": h["entity"]["video_id"],
            "timestamp_ms": h["entity"]["timestamp_ms"],
        }
        for h in hits[0]
    }


def _search_metadata(query_vi: str, limit: int) -> dict[str, float]:
    """ES metadata (mức VIDEO) → {video_id: score}. Query tiếng Việt."""
    es = es_connect()
    hits = es.search(
        index=METADATA_INDEX,
        query={
            "multi_match": {
                "query": query_vi,
                "fields": ["title.vi^4", "title^3", "keywords.vi^3", "keywords^2",
                           "description.vi^2", "description"],
            }
        },
        size=limit,
    )["hits"]["hits"]
    return {h["_source"]["video_id"]: h["_score"] for h in hits}


def _search_objects(query_en: str, limit: int) -> dict[str, dict]:
    """ES objects (mức KEYFRAME) → {keyframe_id: {score, video_id}}. Query tiếng Anh."""
    es = es_connect()
    hits = es.search(
        index=OBJECTS_INDEX,
        query={"match": {"labels.txt": query_en}},
        size=limit,
    )["hits"]["hits"]
    return {
        h["_source"]["keyframe_id"]: {"score": h["_score"], "video_id": h["_source"]["video_id"]}
        for h in hits
    }


def _search_ocr(query_vi: str, limit: int) -> dict[str, dict]:
    """ES ocr (mức KEYFRAME) → {keyframe_id: {score, video_id}}."""
    es = es_connect()
    if not es.indices.exists(index=OCR_INDEX):
        return {}
    hits = es.search(
        index=OCR_INDEX,
        # .vi (đúng dấu) boost gấp đôi — cùng scheme với metadata
        query={"multi_match": {"query": query_vi, "fields": ["text.vi^2", "text"]}},
        size=limit,
    )["hits"]["hits"]
    return {
        h["_source"]["keyframe_id"]: {"score": h["_score"], "video_id": h["_source"]["video_id"]}
        for h in hits
    }


def _search_asr(query_vi: str, limit: int) -> list[dict]:
    """ES asr (mức ĐOẠN) → [{video_id, start_ms, end_ms, score}]."""
    es = es_connect()
    if not es.indices.exists(index=ASR_INDEX):
        return []
    hits = es.search(
        index=ASR_INDEX,
        query={"multi_match": {"query": query_vi, "fields": ["text.vi^2", "text"]}},
        size=limit,
    )["hits"]["hits"]
    return [
        {
            "video_id": h["_source"]["video_id"],
            "start_ms": h["_source"]["start_ms"],
            "end_ms": h["_source"]["end_ms"],
            "score": h["_score"],
        }
        for h in hits
    ]


# ------------------------------------------------------------------- hợp nhất

def _normalize(scores: dict) -> dict[str, float]:
    """Chuẩn hoá score một nguồn về (0,1] bằng cách CHIA CHO MAX (giữ tỉ lệ,
    không ép hit yếu nhất về 0 như min-max). Score âm → dịch lên trước."""
    if not scores:
        return {}
    raw = {k: (v["score"] if isinstance(v, dict) else v) for k, v in scores.items()}
    lo = min(raw.values())
    if lo < 0:
        raw = {k: v - lo for k, v in raw.items()}
    hi = max(raw.values())
    if hi < 1e-9:
        return {k: 1.0 for k in raw}
    return {k: v / hi for k, v in raw.items()}


def _nominate_from_asr(segments: list[dict]) -> dict[str, dict]:
    """Đoạn ASR khớp nhất → tra Milvus lấy keyframe trong khoảng thời gian đó.

    Gộp mọi khoảng vào MỘT filter or-chain → 1 round-trip duy nhất.
    Trả {keyframe_id: {video_id, timestamp_ms}}. Milvus chết → rỗng (đã có try
    ngoài); ASR khi đó vẫn cộng điểm cho ứng viên từ nguồn khác qua temporal join.
    """
    top = segments[:ASR_NOMINATE_SEGMENTS]
    if not top:
        return {}
    clauses = " or ".join(
        f'(video_id == "{s["video_id"]}" and timestamp_ms >= {s["start_ms"] - ASR_TIME_PAD_MS} '
        f'and timestamp_ms <= {s["end_ms"] + ASR_TIME_PAD_MS})'
        for s in top
    )
    client = milvus_connect()
    rows = client.query(COLLECTION_NAME, filter=clauses,
                        output_fields=["video_id", "timestamp_ms"])
    return {
        r["keyframe_id"]: {"video_id": r["video_id"], "timestamp_ms": r["timestamp_ms"]}
        for r in rows
    }


def _fill_timestamps(candidates: dict[str, dict]) -> None:
    """Điền video_id/timestamp cho ứng viên vào từ ES (1 query Milvus cho cả lô).

    Timestamp cần TRƯỚC khi tính điểm — temporal join của ASR phụ thuộc nó
    (khác Task 2.2 cũ: điền sau khi xếp hạng chỉ để hiển thị).
    """
    missing = [kf for kf, info in candidates.items() if info["timestamp_ms"] is None]
    if not missing:
        return
    ids = ", ".join(f'"{k}"' for k in missing)
    client = milvus_connect()
    rows = client.query(COLLECTION_NAME, filter=f"keyframe_id in [{ids}]",
                        output_fields=["timestamp_ms"])
    ts_map = {r["keyframe_id"]: r["timestamp_ms"] for r in rows}
    for kf in missing:
        if kf in ts_map:
            candidates[kf]["timestamp_ms"] = ts_map[kf]


def search(query_vi: str, query_en: str | None = None, top_k: int = 10) -> list[dict]:
    """Search hợp nhất 5 nguồn, trả top-K keyframe kèm breakdown điểm để debug."""
    if query_en is None:
        from backend.retrieval.text_query import translate_to_english
        query_en = translate_to_english(query_vi)

    pool_size = top_k * CANDIDATE_MULTIPLIER

    def _safe(fn, *args):
        try:
            return fn(*args)
        except Exception as e:
            print(f"  [cảnh báo] nguồn {fn.__name__} lỗi, bỏ qua: {e}")
            return {} if fn is not _search_asr else []

    # 5 nguồn độc lập → bắn cùng lúc, đợi cái chậm nhất thay vì tổng
    with ThreadPoolExecutor(max_workers=5) as pool:
        f_vec = pool.submit(_safe, _search_vector, query_en, pool_size)
        f_meta = pool.submit(_safe, _search_metadata, query_vi, pool_size)
        f_obj = pool.submit(_safe, _search_objects, query_en, pool_size)
        f_ocr = pool.submit(_safe, _search_ocr, query_vi, pool_size)
        f_asr = pool.submit(_safe, _search_asr, query_vi, pool_size)
    vec, meta, obj, ocr = f_vec.result(), f_meta.result(), f_obj.result(), f_ocr.result()
    asr_segs = f_asr.result()

    # ---- Gom ứng viên (mức keyframe). metadata mức video KHÔNG tự đề cử
    # (1 video cả nghìn keyframe); ASR ĐƯỢC đề cử vì trỏ được vào khoảng hẹp.
    candidates: dict[str, dict] = {}
    for src in (vec, obj, ocr):
        for kf, info in src.items():
            candidates.setdefault(
                kf, {"video_id": info["video_id"], "timestamp_ms": info.get("timestamp_ms")}
            )
    try:
        for kf, info in _nominate_from_asr(asr_segs).items():
            candidates.setdefault(kf, info)
    except Exception as e:
        print(f"  [cảnh báo] ASR đề cử lỗi, bỏ qua: {e}")

    try:
        _fill_timestamps(candidates)
    except Exception as e:
        print(f"  [cảnh báo] không điền được timestamp: {e}")

    # ---- Chuẩn hoá từng nguồn
    n_vec, n_meta, n_obj, n_ocr = map(_normalize, (vec, meta, obj, ocr))
    seg_norm = _normalize({i: s["score"] for i, s in enumerate(asr_segs)})

    def asr_score(video_id: str, ts: int | None) -> float:
        """Điểm ASR của 1 keyframe = max các đoạn CÙNG VIDEO chứa ts (± pad)."""
        if ts is None:
            return 0.0
        return max(
            (
                seg_norm[i]
                for i, s in enumerate(asr_segs)
                if s["video_id"] == video_id
                and s["start_ms"] - ASR_TIME_PAD_MS <= ts <= s["end_ms"] + ASR_TIME_PAD_MS
            ),
            default=0.0,
        )

    # ---- Weighted sum
    w = FUSION_WEIGHTS
    results = []
    for kf, info in candidates.items():
        breakdown = {
            "vector": w["vector"] * n_vec.get(kf, 0.0),
            "objects": w["objects"] * n_obj.get(kf, 0.0),
            "ocr": w["ocr"] * n_ocr.get(kf, 0.0),
            "asr": w["asr"] * asr_score(info["video_id"], info["timestamp_ms"]),
            "metadata": w["metadata"] * n_meta.get(info["video_id"], 0.0),
        }
        results.append({
            "keyframe_id": kf,
            "video_id": info["video_id"],
            "timestamp_ms": info["timestamp_ms"],
            "score": round(sum(breakdown.values()), 4),
            "breakdown": {k: round(v, 4) for k, v in breakdown.items()},
        })

    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:top_k]


def main() -> None:
    parser = argparse.ArgumentParser(description="Search hợp nhất vector + text + ocr + asr")
    parser.add_argument("query", help="mô tả khoảnh khắc (tiếng Việt)")
    parser.add_argument("--en", metavar="TEXT",
                        help="bản dịch tiếng Anh thủ công (bỏ qua llm() — dùng khi chưa có API key)")
    parser.add_argument("--top-k", type=int, default=10)
    args = parser.parse_args()

    results = search(args.query, query_en=args.en, top_k=args.top_k)

    print(f'\nTop {len(results)} cho: "{args.query}"' + (f'  (EN: "{args.en}")' if args.en else ""))
    for i, r in enumerate(results, 1):
        b = r["breakdown"]
        detail = ", ".join(f"{k}={v}" for k, v in b.items() if v > 0)
        ts = f"{r['timestamp_ms']}ms" if r["timestamp_ms"] is not None else "?ms"
        print(f"{i:>3}. {r['score']:.4f}  {r['keyframe_id']}  ({r['video_id']}, t={ts})  [{detail}]")


if __name__ == "__main__":
    main()
