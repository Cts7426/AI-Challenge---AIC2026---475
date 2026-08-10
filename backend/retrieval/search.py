# backend/retrieval/search.py — A2.1 + A2.2: search nhiều nhánh + hợp nhất RRF
#
# ===== Đường đi một truy vấn =====
#   query VI ──llm()──> query EN
#      ├─ vector   : CLIP encode EN → Milvus            (mức KEYFRAME)
#      ├─ metadata : BM25 VI trên `metadata`            (mức VIDEO)
#      ├─ objects  : match EN trên `objects.labels.txt` (mức KEYFRAME)
#      ├─ ocr      : BM25 VI trên `ocr`                 (mức KEYFRAME)
#      └─ asr      : BM25 VI trên `asr`                 (mức ĐOẠN THỜI GIAN)
#   → mỗi nhánh trả một BẢNG XẾP HẠNG → RRF → gom về shot → top-K
#
# ===== Vì sao RRF thay vì cộng điểm có trọng số =====
# Điểm các nhánh khác thang nhau (COSINE [-1,1] vs BM25 không chặn trên), cộng
# thẳng là nhánh BM25 nuốt hết. RRF chỉ cộng THỨ HẠNG:
#       score(d) = Σ_nhánh 1 / (K + rank_nhánh(d))
# → không cần chuẩn hoá, không cần tune trọng số (xem data/config/search_weights.py).
#
# ===== Vì sao mỗi kết quả phải mang theo thứ hạng từng nhánh =====
# BẮT BUỘC (CLAUDE.md bất biến 7). Khi một câu trượt, cần biết ngay "vector xếp
# nó thứ 400 nhưng ocr xếp thứ 2" — không có số này thì phân tích lỗi thành đoán
# mò, mà tuần sau chỉ có 7 ngày để sửa. Mỗi kết quả trả kèm `ranks` + `contrib`.
#
# ===== Quy về hạng cho nhánh không ở mức keyframe =====
#   metadata (mức video) : mọi keyframe của video đó nhận hạng của video
#   asr (mức đoạn)       : keyframe nhận hạng của đoạn nói tốt nhất chứa nó (±pad)
# Không có nhánh nào bị loại vì "sai đơn vị" — chỉ khác cách quy chiếu.
#
# ⚠️ KHÔNG đặt ngưỡng điểm cứng ở bất cứ đâu (bất biến 5): cosine CLIP thực tế
# chỉ quanh 0.2–0.3, mọi ngưỡng kiểu `score > 0.5` sẽ lọc sạch kết quả đúng.
# Cắt danh sách CHỈ bằng top-K.
#
# ===== Chạy =====
#   python -m backend.retrieval.search "mô tả" --en "english" --top-k 10
#   python -m backend.retrieval.search "..." --en "..." --branches vector,ocr
#   python -m backend.retrieval.search "..." --en "..." --no-group-shot

from __future__ import annotations

import argparse
import time
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path

from backend.indexing.es_client import connect as es_connect
from backend.indexing.load_clip import assert_index_meta
from backend.indexing.load_metadata import INDEX_NAME as METADATA_INDEX
from backend.indexing.load_objects import INDEX_NAME as OBJECTS_INDEX
from backend.indexing.milvus_client import COLLECTION_NAME, connect as milvus_connect
from data.config.search_weights import (
    ASR_NOMINATE_SEGMENTS,
    ASR_TIME_PAD_MS,
    BRANCHES,
    CANDIDATE_MULTIPLIER,
    GROUP_BY_SHOT,
    RRF_K,
)

OCR_INDEX = "ocr"
ASR_INDEX = "asr"

REPO_ROOT = Path(__file__).resolve().parents[2]
CLIP_KF_MAP = REPO_ROOT / "data" / "derived" / "clip_kf_map.parquet"


# ------------------------------------------------------- từng nhánh: trả THỨ HẠNG
# Quy ước chung: mỗi hàm trả list ĐÃ XẾP HẠNG (phần tử 0 = hạng 1).
# Không hàm nào trả điểm thô ra ngoài — điểm chỉ dùng để sắp xếp bên trong nhánh.

def _branch_vector(query_en: str, limit: int) -> list[dict]:
    """Milvus CLIP → [{keyframe_id, video_id, frame_idx, timestamp_ms}] theo hạng."""
    from backend.retrieval.text_query import encode_text

    # Index và query encoder phải CÙNG không gian vector, nếu không Milvus vẫn
    # trả top-k với điểm 0.2–0.3 trông rất bình thường mà sai toàn bộ (A1.0a).
    assert_index_meta(strict=False)

    client = milvus_connect()
    hits = client.search(
        COLLECTION_NAME,
        data=[encode_text(query_en).tolist()],
        limit=limit,
        output_fields=["video_id", "frame_idx", "timestamp_ms"],
        search_params={"params": {"ef": 128}},
    )
    return [
        {
            "keyframe_id": h["id"],
            "video_id": h["entity"]["video_id"],
            "frame_idx": h["entity"].get("frame_idx"),
            "timestamp_ms": h["entity"].get("timestamp_ms"),
        }
        for h in hits[0]
    ]


def _branch_metadata(query_vi: str, limit: int) -> list[dict]:
    """ES metadata (mức VIDEO) → [{video_id}] theo hạng. Query tiếng Việt."""
    es = es_connect()
    hits = es.search(
        index=METADATA_INDEX,
        query={
            "multi_match": {
                "query": query_vi,
                # .vi = bản giữ dấu, được boost cao hơn bản bỏ dấu
                "fields": ["title.vi^4", "title^3", "keywords.vi^3", "keywords^2",
                           "description.vi^2", "description"],
            }
        },
        size=limit,
    )["hits"]["hits"]
    return [{"video_id": h["_source"]["video_id"]} for h in hits]


def _branch_objects(query_en: str, limit: int) -> list[dict]:
    """ES objects (mức KEYFRAME) → [{keyframe_id, video_id}]. Query tiếng Anh
    vì nhãn OpenImages là tiếng Anh."""
    es = es_connect()
    hits = es.search(
        index=OBJECTS_INDEX,
        query={"match": {"labels.txt": query_en}},
        size=limit,
    )["hits"]["hits"]
    return [
        {"keyframe_id": h["_source"]["keyframe_id"], "video_id": h["_source"]["video_id"]}
        for h in hits
    ]


def _branch_ocr(query_vi: str, limit: int) -> list[dict]:
    """ES ocr (mức KEYFRAME) → [{keyframe_id, video_id}]. Index chưa có → rỗng."""
    es = es_connect()
    if not es.indices.exists(index=OCR_INDEX):
        return []
    hits = es.search(
        index=OCR_INDEX,
        query={"multi_match": {"query": query_vi, "fields": ["text.vi^2", "text"]}},
        size=limit,
    )["hits"]["hits"]
    return [
        {"keyframe_id": h["_source"]["keyframe_id"], "video_id": h["_source"]["video_id"]}
        for h in hits
    ]


def _branch_asr(query_vi: str, limit: int) -> list[dict]:
    """ES asr (mức ĐOẠN) → [{video_id, start_ms, end_ms}] theo hạng."""
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
        }
        for h in hits
    ]


# --------------------------------------------------------------- dữ liệu bổ trợ

@lru_cache(maxsize=1)
def _shot_map() -> dict[str, str]:
    """keyframe_id → shot_id, đọc clip_kf_map.parquet (B0.1 của Data Factory).

    Nhận CẢ HAI dạng id vì hai nguồn dùng hai cách đặt tên:
      `clip_kf_id` = "L21_V001#k0001" (keyframe BTC — thứ nằm trong Milvus/OCR)
      `kf_id`      = "L21_V001_0000090" (keyframe tự trích 1fps)
    Thiếu file → trả rỗng, gom-theo-shot tự tắt chứ không làm sập search.
    """
    if not CLIP_KF_MAP.exists():
        return {}
    try:
        import pandas as pd

        df = pd.read_parquet(CLIP_KF_MAP, columns=["kf_id", "clip_kf_id", "shot_id"])
    except Exception as e:
        print(f"  [cảnh báo] không đọc được clip_kf_map, bỏ gom shot: {e}")
        return {}

    m: dict[str, str] = {}
    for kf, ckf, shot in df.itertuples(index=False):
        if isinstance(kf, str):
            m[kf] = shot
        if isinstance(ckf, str):
            m[ckf] = shot
    return m


def _nominate_from_asr(segments: list[dict]) -> list[dict]:
    """Đoạn ASR khớp nhất → keyframe nằm trong khoảng thời gian đó (1 query Milvus).

    Vì sao ASR được quyền đề cử: query thuần lời nói ("bình luận viên hô...")
    có thể không có tín hiệu hình ảnh nào, vector/objects không bắt được gì.
    """
    top = segments[:ASR_NOMINATE_SEGMENTS]
    if not top:
        return []
    dieu_kien = " or ".join(
        f'(video_id == "{s["video_id"]}" and timestamp_ms >= {s["start_ms"] - ASR_TIME_PAD_MS} '
        f'and timestamp_ms <= {s["end_ms"] + ASR_TIME_PAD_MS})'
        for s in top
    )
    rows = milvus_connect().query(
        COLLECTION_NAME, filter=dieu_kien,
        output_fields=["video_id", "frame_idx", "timestamp_ms"],
    )
    return [
        {
            "keyframe_id": r["keyframe_id"],
            "video_id": r["video_id"],
            "frame_idx": r.get("frame_idx"),
            "timestamp_ms": r.get("timestamp_ms"),
        }
        for r in rows
    ]


def _fill_from_milvus(candidates: dict[str, dict]) -> None:
    """Điền frame_idx/timestamp_ms cho ứng viên vào từ ES (1 query cho cả lô).

    Cần TRƯỚC khi tính hạng ASR (join theo thời gian) chứ không phải lúc hiển thị.
    """
    thieu = [k for k, v in candidates.items() if v.get("timestamp_ms") is None]
    if not thieu:
        return
    ids = ", ".join(f'"{k}"' for k in thieu)
    rows = milvus_connect().query(
        COLLECTION_NAME, filter=f"keyframe_id in [{ids}]",
        output_fields=["frame_idx", "timestamp_ms"],
    )
    for r in rows:
        c = candidates.get(r["keyframe_id"])
        if c:
            c["frame_idx"] = r.get("frame_idx")
            c["timestamp_ms"] = r.get("timestamp_ms")


# -------------------------------------------------------------------------- RRF

def _rrf(rank: int) -> float:
    """Đóng góp của MỘT nhánh cho MỘT tài liệu. rank đếm từ 1."""
    return 1.0 / (RRF_K + rank)


def search(
    query_vi: str,
    query_en: str | None = None,
    top_k: int = 10,
    branches: dict[str, bool] | None = None,
    group_by_shot: bool | None = None,
) -> list[dict]:
    """Search hợp nhất bằng RRF. Trả top-K, mỗi phần tử kèm thứ hạng từng nhánh.

    Mỗi kết quả: {keyframe_id, video_id, frame_idx, timestamp_ms, shot_id,
                  score, ranks: {nhánh: hạng}, contrib: {nhánh: đóng góp RRF}}
    """
    if query_en is None:
        from backend.retrieval.text_query import translate_to_english
        query_en = translate_to_english(query_vi)

    bat = {**BRANCHES, **(branches or {})}
    gom_shot = GROUP_BY_SHOT if group_by_shot is None else group_by_shot
    pool = top_k * CANDIDATE_MULTIPLIER

    def _an_toan(ten: str, fn, *args) -> list[dict]:
        """Một nhánh chết KHÔNG được kéo sập search — thi thì không có thời gian debug."""
        if not bat.get(ten, True):
            return []
        try:
            return fn(*args)
        except Exception as e:
            print(f"  [cảnh báo] nhánh {ten} lỗi, bỏ qua: {e}")
            return []

    # Các nhánh độc lập → bắn cùng lúc, đợi cái chậm nhất thay vì cộng dồn
    with ThreadPoolExecutor(max_workers=5) as pool_thread:
        f = {
            "vector": pool_thread.submit(_an_toan, "vector", _branch_vector, query_en, pool),
            "metadata": pool_thread.submit(_an_toan, "metadata", _branch_metadata, query_vi, pool),
            "objects": pool_thread.submit(_an_toan, "objects", _branch_objects, query_en, pool),
            "ocr": pool_thread.submit(_an_toan, "ocr", _branch_ocr, query_vi, pool),
            "asr": pool_thread.submit(_an_toan, "asr", _branch_asr, query_vi, pool),
        }
    kq = {ten: fut.result() for ten, fut in f.items()}

    # --- ứng viên: mọi keyframe xuất hiện ở nhánh mức-keyframe.
    # metadata (mức video) KHÔNG tự đề cử: 1 video có cả nghìn keyframe, không
    # biết cái nào. ASR thì ĐƯỢC, vì nó trỏ được vào một khoảng thời gian hẹp.
    candidates: dict[str, dict] = {}
    for ten in ("vector", "objects", "ocr"):
        for r in kq[ten]:
            candidates.setdefault(r["keyframe_id"], {
                "video_id": r["video_id"],
                "frame_idx": r.get("frame_idx"),
                "timestamp_ms": r.get("timestamp_ms"),
            })
    if kq["asr"]:
        try:
            for r in _nominate_from_asr(kq["asr"]):
                candidates.setdefault(r["keyframe_id"], {
                    "video_id": r["video_id"],
                    "frame_idx": r.get("frame_idx"),
                    "timestamp_ms": r.get("timestamp_ms"),
                })
        except Exception as e:
            print(f"  [cảnh báo] ASR đề cử lỗi, bỏ qua: {e}")

    if not candidates:
        return []

    try:
        _fill_from_milvus(candidates)
    except Exception as e:
        print(f"  [cảnh báo] không điền được frame_idx/timestamp: {e}")

    # --- quy mọi nhánh về hạng theo keyframe
    hang_kf = {
        ten: {r["keyframe_id"]: i for i, r in enumerate(kq[ten], 1)}
        for ten in ("vector", "objects", "ocr")
    }
    hang_video = {r["video_id"]: i for i, r in enumerate(kq["metadata"], 1)}

    def hang_asr(video_id: str, ts: int | None) -> int | None:
        """Hạng ASR của một keyframe = hạng đoạn nói TỐT NHẤT chứa nó (±pad)."""
        if ts is None:
            return None
        for i, s in enumerate(kq["asr"], 1):  # đã xếp hạng → gặp đầu tiên là tốt nhất
            if (s["video_id"] == video_id
                    and s["start_ms"] - ASR_TIME_PAD_MS <= ts <= s["end_ms"] + ASR_TIME_PAD_MS):
                return i
        return None

    # shot_id gắn LUÔN (nó là dữ liệu, không phải hệ quả của việc gom): UI cần
    # hiển thị, TRAKE cần định vị. gom_shot chỉ quyết định có LỌC bớt hay không.
    shots = _shot_map()
    ket_qua = []
    for kf, info in candidates.items():
        ranks: dict[str, int] = {}
        for ten in ("vector", "objects", "ocr"):
            if kf in hang_kf[ten]:
                ranks[ten] = hang_kf[ten][kf]
        if info["video_id"] in hang_video:
            ranks["metadata"] = hang_video[info["video_id"]]
        r_asr = hang_asr(info["video_id"], info.get("timestamp_ms"))
        if r_asr is not None:
            ranks["asr"] = r_asr

        # Cộng giá trị THÔ rồi mới làm tròn: cộng các số đã tròn sẽ lệch ở chữ
        # số cuối, đủ để đảo thứ tự hai kết quả sát nhau và làm sai bảng xếp hạng.
        contrib_tho = {ten: _rrf(h) for ten, h in ranks.items()}
        contrib = {ten: round(v, 6) for ten, v in contrib_tho.items()}
        ket_qua.append({
            "keyframe_id": kf,
            "video_id": info["video_id"],
            "frame_idx": info.get("frame_idx"),
            "timestamp_ms": info.get("timestamp_ms"),
            "shot_id": shots.get(kf),
            # KHÔNG làm tròn score đem đi sắp xếp: làm tròn tạo ra các cặp bằng
            # nhau giả, thứ tự giữa chúng thành tuỳ ý — mà R@1 vs R@5 chênh 0.20 điểm.
            "score": sum(contrib_tho.values()),
            "ranks": ranks,        # ← bắt buộc: phân tích lỗi dựa vào đây
            "contrib": contrib,
        })

    ket_qua.sort(key=lambda r: r["score"], reverse=True)

    # --- gom về shot: mỗi shot giữ 1 keyframe điểm cao nhất (đã sort nên là cái gặp đầu)
    if gom_shot and shots:
        da_co: set[str] = set()
        gon = []
        for r in ket_qua:
            s = r["shot_id"]
            if s is not None:
                if s in da_co:
                    continue
                da_co.add(s)
            gon.append(r)          # keyframe không biết shot → giữ nguyên, không vứt
        ket_qua = gon

    return ket_qua[:top_k]


# ------------------------------------------------------------------------- CLI

def main() -> None:
    ap = argparse.ArgumentParser(description="Search nhiều nhánh + hợp nhất RRF")
    ap.add_argument("query", help="mô tả khoảnh khắc (tiếng Việt)")
    ap.add_argument("--en", metavar="TEXT", help="bản dịch EN thủ công (bỏ qua llm())")
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--branches", help="chỉ bật các nhánh này, vd: vector,ocr")
    ap.add_argument("--no-group-shot", action="store_true", help="không gom theo shot")
    args = ap.parse_args()

    branches = None
    if args.branches:
        chon = {b.strip() for b in args.branches.split(",")}
        la = chon - set(BRANCHES)
        if la:
            ap.error(f"nhánh không tồn tại: {sorted(la)}. Có: {sorted(BRANCHES)}")
        branches = {b: (b in chon) for b in BRANCHES}

    t0 = time.perf_counter()
    kq = search(args.query, query_en=args.en, top_k=args.top_k,
                branches=branches, group_by_shot=not args.no_group_shot)
    ms = (time.perf_counter() - t0) * 1000

    print(f'\nTop {len(kq)} cho: "{args.query}"' + (f'  (EN: "{args.en}")' if args.en else ""))
    print(f"RRF k={RRF_K} · nhánh bật: {sorted(k for k, v in {**BRANCHES, **(branches or {})}.items() if v)} "
          f"· {ms:.0f} ms")
    print(f"\n{'#':>3}  {'score':>8}  {'keyframe':<22} {'frame':>7}  {'shot':<16} thứ hạng từng nhánh")
    print("-" * 104)
    for i, r in enumerate(kq, 1):
        hang = " ".join(f"{ten}={h}" for ten, h in sorted(r["ranks"].items())) or "(không nhánh nào)"
        fi = r["frame_idx"] if r["frame_idx"] is not None else "?"
        print(f"{i:>3}  {r['score']:>8.5f}  {r['keyframe_id']:<22} {fi:>7}  "
              f"{(r['shot_id'] or '-'):<16} {hang}")


if __name__ == "__main__":
    main()
