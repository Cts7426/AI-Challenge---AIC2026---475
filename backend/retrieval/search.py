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
#   python -m backend.retrieval.search "..." --en "..." --filter-video-id L21_V001
#
# ===== filter_video_id (C4.4 — TRAKE fallback) =====
# Ép search chỉ trả kết quả TRONG MỘT video đã biết (dùng khi đã chốt video ở
# TRAKE giai đoạn 1, giờ chỉ cần định vị N khoảnh khắc trong video đó).
# Mặc định None → KIS pipeline hiện có không đổi hành vi một chút nào — filter
# chỉ thêm 1 điều kiện AND vào 4 nhánh mức-keyframe (vector/objects/ocr/asr),
# không đổi contract trả về của search(). Nhánh `metadata` (mức video, xem
# "quy về hạng" ở trên) không có gì để lọc — chỉ 1 video khớp exact — chỗ gọi
# nên tự tắt nhánh này qua `branches={"metadata": False}` để đỡ tốn 1 query ES
# vô ích, search() không tự tắt hộ vì đó là quyết định của người gọi.

from __future__ import annotations

import argparse
import time
from bisect import bisect_right
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

def _branch_vector(query_en: str, limit: int, filter_video_id: str | None = None) -> list[dict]:
    """Milvus → [{keyframe_id, video_id, frame_idx, timestamp_ms}] theo hạng.

    Encoder do `VECTOR_BACKEND` chọn: 'clip' (mặc định, giữ nguyên hành vi cũ)
    hoặc 'siglip2'. Encoder và collection LUÔN đi theo cặp — dùng text encoder
    này với index kia thì Milvus vẫn trả top-k điểm 0.2–0.3 trông bình thường
    mà sai toàn bộ, nên hai thứ được chọn cùng một chỗ, không tách rời được.
    """
    from data.config.siglip2_model import SIGLIP2_COLLECTION, use_siglip2

    if use_siglip2():
        from backend.indexing.load_siglip2 import assert_siglip2_index_meta
        from backend.retrieval.siglip2_query import encode_text
        collection = SIGLIP2_COLLECTION
        # ⚠️ SỬA (R3.K2b) — bản cũ ghi "index SigLIP2 đã assert dim lúc
        # encode_text" rồi bỏ qua hẳn phép kiểm meta. Assert dim KHÔNG ĐỦ: hai
        # model khác nhau cùng 1152 chiều (hoặc cùng model khác `pretrained`)
        # lọt qua trơn tru, Milvus vẫn trả top-k với cosine trông bình thường,
        # và không gì báo rằng index thuộc không gian khác. Giờ kiểm đủ
        # model/pretrained/dim/metric/collection như nhánh CLIP vẫn làm.
        assert_siglip2_index_meta(strict=False)
    else:
        from backend.retrieval.text_query import encode_text
        collection = COLLECTION_NAME
        assert_index_meta(strict=False)

    client = milvus_connect()
    kwargs: dict = {}
    if filter_video_id is not None:
        kwargs["filter"] = f'video_id == "{filter_video_id}"'
    hits = client.search(
        collection,
        data=[encode_text(query_en).tolist()],
        limit=limit,
        output_fields=["video_id", "frame_idx", "timestamp_ms"],
        # HNSW đòi ef >= k (Milvus báo lỗi "ef should be larger than k" chứ
        # không tự nới hộ) — 128 chỉ đủ cho top_k nhỏ (KIS thường limit<26 sau
        # nhân CANDIDATE_MULTIPLIER). C3.2 (TRAKE stage 1) xin pool tới 1000 để
        # gộp điểm video → phải nới ef theo limit, không hardcode. Đo thật
        # (14/08): limit=1000 mà ef=128 → toàn bộ nhánh vector chết, search()
        # vẫn chạy tiếp bằng 4 nhánh còn lại (an toàn) nhưng mất tín hiệu mạnh
        # nhất — lỗi im lặng kiểu "chạy được nhưng kém đi" mà không ai để ý.
        search_params={"params": {"ef": max(128, limit)}},
        **kwargs,
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


def _with_video_filter(query: dict, filter_video_id: str | None) -> dict:
    """Bọc 1 query ES bằng bool.filter video_id — dùng chung cho 3 nhánh ES.

    `filter` (không phải `must`) vì đây là điều kiện lọc CỨNG, không tham gia
    tính _score — giữ nguyên thứ hạng theo độ khớp text, chỉ thu hẹp tập kết quả.
    """
    if filter_video_id is None:
        return query
    return {"bool": {"must": [query], "filter": [{"term": {"video_id": filter_video_id}}]}}


def _branch_objects(query_en: str, limit: int, filter_video_id: str | None = None) -> list[dict]:
    """ES objects (mức KEYFRAME) → [{keyframe_id, video_id}]. Query tiếng Anh
    vì nhãn OpenImages là tiếng Anh."""
    es = es_connect()
    hits = es.search(
        index=OBJECTS_INDEX,
        query=_with_video_filter({"match": {"labels.txt": query_en}}, filter_video_id),
        size=limit,
    )["hits"]["hits"]
    return [
        {"keyframe_id": h["_source"]["keyframe_id"], "video_id": h["_source"]["video_id"]}
        for h in hits
    ]


def _branch_ocr(query_vi: str, limit: int, filter_video_id: str | None = None) -> list[dict]:
    """ES ocr (mức KEYFRAME) → [{keyframe_id, video_id}]. Index chưa có → rỗng."""
    es = es_connect()
    if not es.indices.exists(index=OCR_INDEX):
        return []
    hits = es.search(
        index=OCR_INDEX,
        query=_with_video_filter(
            {"multi_match": {"query": query_vi, "fields": ["text.vi^2", "text"]}}, filter_video_id
        ),
        size=limit,
    )["hits"]["hits"]
    return [
        {"keyframe_id": h["_source"]["keyframe_id"], "video_id": h["_source"]["video_id"]}
        for h in hits
    ]


def _branch_asr(query_vi: str, limit: int, filter_video_id: str | None = None) -> list[dict]:
    """ES asr (mức ĐOẠN) → [{video_id, start_ms, end_ms}] theo hạng."""
    es = es_connect()
    if not es.indices.exists(index=ASR_INDEX):
        return []
    hits = es.search(
        index=ASR_INDEX,
        query=_with_video_filter(
            {"multi_match": {"query": query_vi, "fields": ["text.vi^2", "text"]}}, filter_video_id
        ),
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


@lru_cache(maxsize=1)
def _shot_ranges() -> dict[str, tuple[list[int], list[int], list[str]]]:
    """video_id → (start_frame đã sắp xếp, end_frame, shot_id) để tra theo FRAME.

    Vì sao cần thêm cách tra này bên cạnh `_shot_map()`: map kia tra theo tên
    keyframe, mà tên chỉ khớp với hai cách đặt tên của CLIP. Encoder mới đặt tên
    khác ("L26_V102#f0002432") nên tra tên trả None cho MỌI dòng, và bước gom
    shot lặng lẽ loại sạch kết quả — search trả rỗng mà không báo lỗi gì.

    Một shot vốn LÀ một khoảng frame, nên tra theo frame đúng với mọi cách đặt
    tên và không phụ thuộc encoder nào.
    """
    path = Path(__file__).resolve().parents[2] / "data/derived/shots.parquet"
    if not path.exists():
        return {}
    try:
        import pandas as pd

        df = pd.read_parquet(path, columns=["video_id", "start_frame", "end_frame", "shot_id"])
    except Exception as e:
        print(f"  [cảnh báo] không đọc được shots.parquet, bỏ tra shot theo frame: {e}")
        return {}

    out: dict[str, tuple[list[int], list[int], list[str]]] = {}
    for video_id, g in df.sort_values("start_frame").groupby("video_id", sort=False):
        out[str(video_id)] = (
            g["start_frame"].astype(int).tolist(),
            g["end_frame"].astype(int).tolist(),
            g["shot_id"].astype(str).tolist(),
        )
    return out


def _shot_of_frame(video_id: str, frame_idx: int | None) -> str | None:
    """Shot chứa frame này, hoặc None nếu frame nằm ngoài mọi shot."""
    if frame_idx is None:
        return None
    ranges = _shot_ranges().get(video_id)
    if not ranges:
        return None
    starts, ends, ids = ranges
    i = bisect_right(starts, int(frame_idx)) - 1
    if i < 0:
        return None
    return ids[i] if int(frame_idx) <= ends[i] else None


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
        # keyframe_id là PK — Milvus thường tự trả, nhưng khai báo tường minh
        # để không phụ thuộc hành vi ngầm (đổi version Milvus có thể thay đổi).
        output_fields=["keyframe_id", "video_id", "frame_idx", "timestamp_ms"],
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


def _search_core(
    query_vi: str,
    query_en: str | None = None,
    top_k: int = 10,
    branches: dict[str, bool] | None = None,
    filter_video_id: str | None = None,
) -> tuple[list[dict], dict]:
    """Phần tính RRF thô: CHƯA gom shot, CHƯA cắt top_k, KHÔNG rerank.

    Trả `(ket_qua đã sort theo score giảm dần, shot_map)`. Đây là ranh giới
    DUY NHẤT cho hậu xử lý xem toàn bộ candidate pool trước khi bị cắt (vd:
    VLM rerank thử nghiệm ở CLI `search.py --rerank`) — hàm này KHÔNG public,
    `search()` công khai bên dưới không có tham số rerank, nên `solve_query()`
    và mọi caller production không bao giờ với tới VLM qua đây (bất biến #9
    AGENTS.md: VLM/local nặng không nằm trong đường chạy online, trừ Q&A qua
    `llm()` adapter).
    """
    if query_en is None:
        from backend.retrieval.text_query import translate_to_english
        try:
            query_en = translate_to_english(query_vi)
        except Exception as e:
            # LLM chết (hết credit/mất mạng/429) KHÔNG được kéo sập cả truy vấn.
            # Trước bản vá này, bước dịch nằm NGOÀI _an_toan() nên một lỗi ở đây
            # là 0 điểm cho MỌI dạng bài, kể cả KIS vốn không cần LLM để chấm.
            # Rơi về query gốc: nhánh vector/objects yếu hẳn (CLIP là model tiếng
            # Anh), nhưng metadata/OCR/ASR vẫn chạy đúng trên tiếng Việt — điểm
            # giảm chứ không mất trắng.
            print(f"  [cảnh báo] dịch VI→EN lỗi ({e}) — dùng nguyên query tiếng Việt")
            query_en = query_vi

    bat = {**BRANCHES, **(branches or {})}
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
            "vector": pool_thread.submit(
                _an_toan, "vector", _branch_vector, query_en, pool, filter_video_id
            ),
            "metadata": pool_thread.submit(_an_toan, "metadata", _branch_metadata, query_vi, pool),
            "objects": pool_thread.submit(
                _an_toan, "objects", _branch_objects, query_en, pool, filter_video_id
            ),
            "ocr": pool_thread.submit(_an_toan, "ocr", _branch_ocr, query_vi, pool, filter_video_id),
            "asr": pool_thread.submit(_an_toan, "asr", _branch_asr, query_vi, pool, filter_video_id),
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
        return [], {}

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
    from data.config.search_weights import BRANCH_WEIGHTS
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

        # Cộng giá trị THÔ (đã nhân trọng số) rồi mới làm tròn
        contrib_tho = {ten: BRANCH_WEIGHTS.get(ten, 1.0) * (1.0 / (RRF_K + h)) for ten, h in ranks.items()}
        contrib = {ten: round(v, 6) for ten, v in contrib_tho.items()}
        ket_qua.append({
            "keyframe_id": kf,
            "video_id": info["video_id"],
            "frame_idx": info.get("frame_idx"),
            "timestamp_ms": info.get("timestamp_ms"),
            # Tra theo tên keyframe trước (giữ nguyên hành vi cũ), không có thì
            # tra theo khoảng frame — encoder mới đặt tên khác nên tra tên trả
            # None cho mọi dòng và bước gom shot sẽ loại sạch kết quả.
            "shot_id": shots.get(kf) or _shot_of_frame(info["video_id"], info.get("frame_idx")),
            # KHÔNG làm tròn score đem đi sắp xếp: làm tròn tạo ra các cặp bằng
            # nhau giả, thứ tự giữa chúng thành tuỳ ý — mà R@1 vs R@5 chênh 0.20 điểm.
            "score": sum(contrib_tho.values()),
            "ranks": ranks,        # ← bắt buộc: phân tích lỗi dựa vào đây
            "contrib": contrib,
        })

    ket_qua.sort(key=lambda r: r["score"], reverse=True)

    return ket_qua, shots


def _finalize(
    ket_qua: list[dict], shots: dict, top_k: int, group_by_shot: bool | None,
) -> list[dict]:
    """Gom về shot (mỗi shot giữ 1 keyframe điểm cao nhất) rồi cắt top_k."""
    gom_shot = GROUP_BY_SHOT if group_by_shot is None else group_by_shot
    if gom_shot and shots:
        da_co: set[str] = set()
        gon = []
        for r in ket_qua:
            s = r["shot_id"]
            if s is None:
                continue  # Bỏ qua frame mồ côi (không map được vào shot nào)
            if s in da_co:
                continue
            da_co.add(s)
            gon.append(r)
        ket_qua = gon
    return ket_qua[:top_k]


def search(
    query_vi: str,
    query_en: str | None = None,
    top_k: int = 10,
    branches: dict[str, bool] | None = None,
    group_by_shot: bool | None = None,
    filter_video_id: str | None = None,
) -> list[dict]:
    """Search hợp nhất bằng RRF. Trả top-K, mỗi phần tử kèm thứ hạng từng nhánh.

    Mỗi kết quả: {keyframe_id, video_id, frame_idx, timestamp_ms, shot_id,
                  score, ranks: {nhánh: hạng}, contrib: {nhánh: đóng góp RRF}}

    filter_video_id: ép mọi nhánh mức-keyframe chỉ tìm TRONG video này (C4.4 —
    TRAKE fallback, khi giai đoạn 1 đã chốt video). None (mặc định) = KIS pipeline
    y hệt trước khi có tham số này — không nhánh nào đổi hành vi.

    KHÔNG có tham số rerank: đây là hàm production duy nhất `solve_query()`
    gọi, VLM không được phép nằm trong đường chạy này (xem `_search_core`).
    """
    ket_qua, shots = _search_core(query_vi, query_en, top_k, branches, filter_video_id)
    return _finalize(ket_qua, shots, top_k, group_by_shot)


# ------------------------------------------------------------------------- CLI

def main() -> None:
    ap = argparse.ArgumentParser(description="Search nhiều nhánh + hợp nhất RRF")
    ap.add_argument("query", help="mô tả khoảnh khắc (tiếng Việt)")
    ap.add_argument("--en", metavar="TEXT", help="bản dịch EN thủ công (bỏ qua llm())")
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--branches", help="chỉ bật các nhánh này, vd: vector,ocr")
    ap.add_argument("--no-group-shot", action="store_true", help="không gom theo shot")
    ap.add_argument("--filter-video-id", metavar="VIDEO_ID", help="chỉ tìm trong 1 video (C4.4)")
    ap.add_argument("--rerank", action="store_true", help="bật Agentic VLM Reranker (chấm điểm ảnh bằng VLM)")
    args = ap.parse_args()

    branches = None
    if args.branches:
        chon = {b.strip() for b in args.branches.split(",")}
        la = chon - set(BRANCHES)
        if la:
            ap.error(f"nhánh không tồn tại: {sorted(la)}. Có: {sorted(BRANCHES)}")
        branches = {b: (b in chon) for b in BRANCHES}

    t0 = time.perf_counter()
    if args.rerank:
        # Agentic VLM rerank CHỈ tồn tại ở CLI này — cố ý không đi qua search()
        # công khai (xem docstring `_search_core`), nên rerank cần tự gọi
        # _search_core() để thấy TOÀN BỘ candidate pool trước khi bị cắt
        # top_k/gom shot, giống hành vi cũ.
        from backend.retrieval.agentic_reranker import VLMReranker
        ket_qua, shots = _search_core(
            args.query, query_en=args.en, top_k=args.top_k,
            branches=branches, filter_video_id=args.filter_video_id,
        )
        reranker = VLMReranker()  # Mặc định gọi Llama 3.2 11B Vision (chỉ MLX/Apple Silicon)
        ket_qua = reranker.rerank(args.query, ket_qua, top_k_to_rerank=50)
        kq = _finalize(ket_qua, shots, args.top_k, not args.no_group_shot)
    else:
        kq = search(args.query, query_en=args.en, top_k=args.top_k,
                    branches=branches, group_by_shot=not args.no_group_shot,
                    filter_video_id=args.filter_video_id)
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
