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
import math
import re
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

def _branch_vector(query_en: str, limit: int, filter_video_id: str | None = None,
                   backend: str | None = None) -> list[dict]:
    """Milvus → [{keyframe_id, video_id, frame_idx, timestamp_ms}] theo hạng.

    `backend=None` (mặc định): encoder do `VECTOR_BACKEND` chọn — giữ nguyên
    hành vi cũ cho mọi chỗ gọi hiện có. Truyền 'clip'/'siglip2' để ép một encoder
    cụ thể, cần cho nhánh vector thứ hai (R3.K3) vì hai nhánh phải chạy CÙNG LÚC
    trong một lượt search nên không thể cùng đọc một biến môi trường.

    Encoder và collection LUÔN đi theo cặp — dùng text encoder này với index kia
    thì Milvus vẫn trả top-k điểm 0.2–0.3 trông bình thường mà sai toàn bộ, nên
    hai thứ được chọn cùng một chỗ, không tách rời được.
    """
    from data.config.siglip2_model import SIGLIP2_COLLECTION, use_siglip2

    dung_siglip2 = use_siglip2() if backend is None else (backend == "siglip2")
    if dung_siglip2:
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
            # Giữ COSINE THẬT (R3.K4). RRF cố tình vứt điểm đi và chỉ dùng thứ
            # hạng — đúng cho việc hợp nhất các thang điểm khác nhau. Nhưng tầng
            # rerank cần biết "hạng 1 này hơn hạng 2 nhiều hay chỉ nhỉnh một tí",
            # thông tin mà thứ hạng không mang. Chỉ mang ra ngoài, KHÔNG dùng để
            # sắp xếp ở đây và KHÔNG so với ngưỡng cứng (bất biến 5).
            "cos": h.get("distance"),
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


def _branch_text_vi(query_vi: str, limit: int,
                    filter_video_id: str | None = None) -> list[dict]:
    """Vector NGỮ NGHĨA tiếng Việt trên đoạn ASR (R3.X4) → cùng dạng `_branch_asr`.

    Trả `[{video_id, start_ms, end_ms}]` để dùng lại y nguyên bộ máy quy-hạng
    theo thời gian của nhánh ASR — nhánh này khác nhánh ASR ở CÁCH khớp (nghĩa
    thay vì từ khoá), không khác ở đơn vị.

    Chưa có collection thì NÉM LỖI chứ không trả rỗng: `_an_toan()` sẽ bắt, in
    cảnh báo, và search vẫn chạy bằng các nhánh còn lại. Trả rỗng lặng lẽ thì
    người vận hành tưởng nhánh đang chạy mà chỉ là không tìm được gì.
    """
    from data.config.text_vi_vector import COLLECTION, EMBEDDING_DIM

    client = milvus_connect()
    if COLLECTION not in client.list_collections():
        raise RuntimeError(
            f"Nhánh text_vi được bật nhưng collection {COLLECTION!r} chưa tồn tại. "
            "Cần R3.X2 (encode đoạn ASR sang vector tiếng Việt) chạy xong trước. "
            "Tắt nhánh: data/config/text_vi_vector.ENABLED = False"
        )

    from backend.retrieval.text_vi_query import encode_text_vi

    vec = encode_text_vi(query_vi)
    if len(vec) != EMBEDDING_DIM:
        raise RuntimeError(
            f"Vector truy vấn {len(vec)} chiều nhưng config khai {EMBEDDING_DIM}. "
            "Model và index lệch nhau — dừng còn hơn trả top-k trông bình thường "
            "mà thuộc không gian khác."
        )
    kwargs: dict = {}
    if filter_video_id is not None:
        kwargs["filter"] = f'video_id == "{filter_video_id}"'
    hits = client.search(
        COLLECTION,
        data=[vec.tolist()],
        limit=limit,
        output_fields=["video_id", "start_ms", "end_ms"],
        search_params={"params": {"ef": max(128, limit)}},
        **kwargs,
    )
    return [
        {
            "video_id": h["entity"]["video_id"],
            "start_ms": h["entity"]["start_ms"],
            "end_ms": h["entity"]["end_ms"],
        }
        for h in hits[0]
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


# Các nhánh xếp hạng ở mức KEYFRAME (khác metadata mức video và asr mức thời
# gian). Gom thành một hằng số vì ba chỗ dưới đây phải dùng ĐÚNG cùng một danh
# sách: đề cử ứng viên, dựng bảng hạng, và cộng RRF. Thêm nhánh mà quên một chỗ
# thì nhánh đó vẫn chạy, vẫn tốn thời gian, nhưng KHÔNG góp phiếu — lỗi im lặng.
NHANH_MUC_KEYFRAME = ("vector", "vector_siglip2", "objects", "ocr", "ocr_probe")


def _search_core(
    query_vi: str,
    query_en: str | None = None,
    top_k: int = 10,
    branches: dict[str, bool] | None = None,
    filter_video_id: str | None = None,
    candidate_multiplier: int | None = None,
    video_prior_alpha: float | None = None,
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
    pool = top_k * (candidate_multiplier or CANDIDATE_MULTIPLIER)

    # Nhánh vector thứ hai luôn là encoder CÒN LẠI. Không hardcode 'siglip2':
    # người vận hành đổi VECTOR_BACKEND=siglip2 thì nhánh phụ phải thành 'clip',
    # nếu không hai nhánh cùng chạy một encoder và ta trả tiền hai lần cho đúng
    # một tín hiệu — mà không có gì báo lỗi.
    from data.config.siglip2_model import use_siglip2
    encoder_chinh = "siglip2" if use_siglip2() else "clip"
    encoder_phu = "clip" if encoder_chinh == "siglip2" else "siglip2"

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
    with ThreadPoolExecutor(max_workers=7) as pool_thread:
        f = {
            "vector": pool_thread.submit(
                _an_toan, "vector", _branch_vector, query_en, pool, filter_video_id,
                encoder_chinh
            ),
            "vector_siglip2": pool_thread.submit(
                _an_toan, "vector_siglip2", _branch_vector, query_en, pool,
                filter_video_id, encoder_phu
            ),
            "metadata": pool_thread.submit(_an_toan, "metadata", _branch_metadata, query_vi, pool),
            "objects": pool_thread.submit(
                _an_toan, "objects", _branch_objects, query_en, pool, filter_video_id
            ),
            "ocr": pool_thread.submit(_an_toan, "ocr", _branch_ocr, query_vi, pool, filter_video_id),
            "ocr_probe": pool_thread.submit(
                _an_toan, "ocr_probe", _branch_ocr_probe, query_vi, query_en, pool,
                filter_video_id,
            ),
            "asr": pool_thread.submit(_an_toan, "asr", _branch_asr, query_vi, pool, filter_video_id),
            "text_vi": pool_thread.submit(
                _an_toan, "text_vi", _branch_text_vi, query_vi, pool, filter_video_id
            ),
        }
    kq = {ten: fut.result() for ten, fut in f.items()}

    # --- ứng viên: mọi keyframe xuất hiện ở nhánh mức-keyframe.
    # metadata (mức video) KHÔNG tự đề cử: 1 video có cả nghìn keyframe, không
    # biết cái nào. ASR thì ĐƯỢC, vì nó trỏ được vào một khoảng thời gian hẹp.
    candidates: dict[str, dict] = {}
    for ten in NHANH_MUC_KEYFRAME:
        for r in kq[ten]:
            candidates.setdefault(r["keyframe_id"], {
                "video_id": r["video_id"],
                "frame_idx": r.get("frame_idx"),
                "timestamp_ms": r.get("timestamp_ms"),
            })
    # `text_vi` cũng được quyền đề cử, cùng lý do như `asr`: query thuần lời nói
    # ("bình luận viên hô...") có thể không có tín hiệu hình ảnh nào. Gộp hai
    # danh sách rồi đề cử MỘT lần — hai lần gọi là hai query Milvus cho cùng một
    # việc, mà đây là đường chạy online.
    doan_de_cu = list(kq["asr"]) + list(kq["text_vi"])
    if doan_de_cu:
        try:
            for r in _nominate_from_asr(doan_de_cu):
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
        for ten in NHANH_MUC_KEYFRAME
    }
    hang_video = {r["video_id"]: i for i, r in enumerate(kq["metadata"], 1)}

    # Cosine thật của từng nhánh vector (R3.K4). Tách khỏi `ranks` vì đây là
    # ĐIỂM chứ không phải hạng — trộn chung vào một dict là mời gọi chỗ khác
    # cộng nhầm hai đại lượng khác thang.
    cos_kf = {
        ten: {r["keyframe_id"]: r["cos"] for r in kq[ten] if r.get("cos") is not None}
        for ten in ("vector", "vector_siglip2")
    }

    def hang_theo_doan(doan: list[dict], video_id: str, ts: int | None) -> int | None:
        """Hạng của keyframe = hạng đoạn nói TỐT NHẤT chứa nó (±pad).

        Dùng chung cho `asr` (khớp từ khoá) và `text_vi` (khớp ngữ nghĩa) — hai
        nhánh khác CÁCH khớp nhưng cùng đơn vị "đoạn thời gian", nên cùng cách
        quy về hạng keyframe.
        """
        if ts is None:
            return None
        for i, s in enumerate(doan, 1):  # đã xếp hạng → gặp đầu tiên là tốt nhất
            if (s["video_id"] == video_id
                    and s["start_ms"] - ASR_TIME_PAD_MS <= ts <= s["end_ms"] + ASR_TIME_PAD_MS):
                return i
        return None

    # shot_id gắn LUÔN (nó là dữ liệu, không phải hệ quả của việc gom): UI cần
    # hiển thị, TRAKE cần định vị. gom_shot chỉ quyết định có LỌC bớt hay không.
    shots = _shot_map()
    ket_qua = []
    from data.config.search_weights import BRANCH_WEIGHTS

    # --- tiên nghiệm mức video (video_prior). Xem data/config/video_prior.py.
    # Cộng dồn bằng chứng của MỌI nhánh theo video, chặn ở VOTE_CAP dòng đầu mỗi
    # nhánh để video dài không thắng bằng số lượng. alpha=0 -> không đổi gì.
    from data.config.video_prior import ALPHA as VP_ALPHA, ENABLED as VP_ON, VOTE_CAP
    # Kiểm giá trị của CALLER trước, rồi mới áp cổng ENABLED: caller truyền 1.5
    # là một bug của caller dù tính năng đang bật hay tắt. Kiểm sau cổng thì bug
    # đó bị nuốt lặng và chỉ lộ ra vào ngày ai đó bật tính năng lên.
    if video_prior_alpha is not None and not 0.0 <= float(video_prior_alpha) <= 1.0:
        raise ValueError(
            f"video_prior_alpha phải trong [0,1], nhận {video_prior_alpha}"
        )
    alpha = VP_ALPHA if video_prior_alpha is None else float(video_prior_alpha)
    if not VP_ON:
        alpha = 0.0
    video_vote: dict[str, float] = {}
    if alpha > 0.0:
        # Hai tín hiệu mức video, đo hai thứ KHÁC NHAU:
        #   dong  — cộng dồn mọi dòng: thưởng video có NHIỀU bằng chứng
        #   dau   — chỉ lần xuất hiện ĐẦU TIÊN: thưởng video được một nhánh xếp
        #           hạng CAO, kể cả khi nó chỉ có vài keyframe trong pool
        # Video đúng của p1-19 đứng hạng 7 (siglip2) và 8 (clip) ở mức video
        # nhưng ít keyframe, nên tín hiệu "dong" một mình dìm nó xuống hạng 25.
        vote_dong: dict[str, float] = {}
        vote_dau: dict[str, float] = {}
        for ten, rows in kq.items():
            w = BRANCH_WEIGHTS.get(ten, 1.0)
            thay: dict[str, int] = {}
            for i, r in enumerate(rows[:VOTE_CAP], 1):
                vid = r.get("video_id")
                if not vid:
                    continue
                vote_dong[vid] = vote_dong.get(vid, 0.0) + w / (RRF_K + i)
                if vid not in thay:
                    thay[vid] = len(thay) + 1
                    vote_dau[vid] = vote_dau.get(vid, 0.0) + w / (RRF_K + thay[vid])

        def _chuan(d: dict[str, float]) -> dict[str, float]:
            m = max(d.values(), default=0.0) or 1.0
            return {k: v / m for k, v in d.items()}

        from data.config.video_prior import BEST_MIX
        vote_dong = _chuan(vote_dong)
        vote_dau = _chuan(vote_dau)
        for vid in set(vote_dong) | set(vote_dau):
            video_vote[vid] = (vote_dong.get(vid, 0.0)
                               + BEST_MIX * vote_dau.get(vid, 0.0))
        # Chuẩn hoá HAI tín hiệu RIÊNG rồi mới trộn.
        #
        # ⚠️ Đã thử cộng thẳng probe vào phiếu nhánh và ĐO ĐƯỢC LÀ VÔ TÁC DỤNG:
        # phiếu nhánh cộng dồn tới 100 dòng × 6 nhánh nên tổng cỡ vài đơn vị,
        # còn probe chỉ đóng góp ~0,2 — tín hiệu mạnh nhất bị số đông nuốt mất
        # (p1-22 đứng nguyên hạng 34). Hai đại lượng khác thang thì phải chuẩn
        # hoá trước, đúng như đã làm giữa rrf và vote.
        from data.config.token_probe import PROBE_MIX
        video_vote = _chuan(video_vote)
        # Cùng công tắc `ocr_probe` với nhánh mức-keyframe: nhánh và phiếu bầu là
        # MỘT tính năng (probe token hiếm), chỉ khác đơn vị đầu ra. Trước bản vá,
        # chỉ `token_probe.ENABLED` tắt được phiếu bầu, còn
        # `branches={'ocr_probe': False}` thì không — nên phép đo "bỏ probe ra thì
        # rớt bao nhiêu điểm" trả về số SAI mà không có gì báo.
        probe = (_probe_video_votes(query_vi, query_en)
                 if bat.get("ocr_probe", True) else {})
        if probe:
            max_probe = max(probe.values()) or 1.0
            for vid, diem in probe.items():
                video_vote[vid] = video_vote.get(vid, 0.0) + PROBE_MIX * (diem / max_probe)
    for kf, info in candidates.items():
        ranks: dict[str, int] = {}
        for ten in NHANH_MUC_KEYFRAME:
            if kf in hang_kf[ten]:
                ranks[ten] = hang_kf[ten][kf]
        if info["video_id"] in hang_video:
            ranks["metadata"] = hang_video[info["video_id"]]
        for ten_doan in ("asr", "text_vi"):
            r = hang_theo_doan(kq[ten_doan], info["video_id"], info.get("timestamp_ms"))
            if r is not None:
                ranks[ten_doan] = r

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
            # Cosine thật của từng nhánh vector — nguyên liệu cho rerank (R3.K4).
            # Thiếu nhánh nào thì khuyết key đó, KHÔNG điền 0: 0 là một giá trị
            # cosine hợp lệ, còn "không có mặt trong pool" là chuyện khác hẳn.
            "cos": {ten: c[kf] for ten, c in cos_kf.items() if kf in c},
        })

    # Phiếu bầu chỉ ĐÍNH KÈM, KHÔNG cộng vào score.
    #
    # ⚠️ Đã thử cộng thẳng `score = (1-α)·rrf + α·vote` và ĐO ĐƯỢC LÀ HỎNG:
    # mọi keyframe của video được bầu cao đều nhận cùng một khoản cộng, nên một
    # video ngập hết đầu bảng và video đúng bị đẩy RA KHỎI 100 dòng (p1-19: hạng
    # 85 -> mất hẳn, top-50 rơi 0,95 -> 0,70 ở α=0,6). Tiên nghiệm mức video là
    # tín hiệu để CHỌN VIDEO, không phải để chấm điểm từng khung hình.
    # Nó được dùng ở `_video_diverse_order()` sau khi đã gom shot.
    for r in ket_qua:
        r["video_vote"] = round(video_vote.get(r["video_id"], 0.0), 6)

    ket_qua.sort(key=lambda r: r["score"], reverse=True)

    return ket_qua, shots


_PROBE_TACH = re.compile(r"[0-9A-Za-zÀ-ỹ]+")


def _ung_vien_probe(query_vi: str, query_en: str | None) -> list[str]:
    """Rút token ứng viên để probe, KHÔNG dùng từ điển và KHÔNG gọi LLM.

    Ưu tiên cụm trong ngoặc (đề hay đặt tên riêng/chữ trên màn hình trong nháy),
    rồi tới token đủ dài. Giữ nguyên thứ tự xuất hiện để kết quả tái lập được;
    lọc độ hiếm là việc của `_probe_video_votes`, không phải của hàm này.
    """
    from data.config.token_probe import MIN_TOKEN_LEN

    ra: list[str] = []
    for nguon in (query_vi, query_en or ""):
        for cum in re.findall(r"['\"“”‘’]([^'\"“”‘’]{2,40})['\"“”‘’]", nguon):
            cum = cum.strip()
            if cum and cum not in ra:
                ra.append(cum)
        for tok in _PROBE_TACH.findall(nguon):
            if len(tok) >= MIN_TOKEN_LEN and tok.lower() not in [x.lower() for x in ra]:
                ra.append(tok)
    return ra


def _branch_ocr_probe(query_vi: str, query_en: str | None, limit: int,
                      filter_video_id: str | None = None) -> list[dict]:
    """Nhánh OCR theo TỪNG TOKEN HIẾM, mức keyframe. Xem data/config/token_probe.py.

    Khác `_branch_ocr` ở chỗ nó KHÔNG ném cả câu vào BM25. Đo được trên p1:
    ném cả câu thì video đúng của p1-22 đứng hạng 52 và p1-12 hạng 57; ném riêng
    token hiếm ('remember', 'mazut') thì hạng 2 và hạng 1.

    Trả về mức KEYFRAME (không phải mức video) để tín hiệu này vừa chọn đúng
    video vừa trỏ đúng khung hình — OCR hit vốn đã gắn sẵn `keyframe_id`, dùng
    thẳng nó thì không phải nhờ CLIP tìm lại frame bên trong video.

    Token nào khớp quá nhiều dòng thì bị loại: nó là từ thường, không phân biệt
    được gì. Ngưỡng tự đo, không cần từ điển tiếng Việt.

    ⚠️ `filter_video_id` LỌC HÀNG TRẢ VỀ, KHÔNG lọc lệnh đo độ hiếm.
    Lệnh `_branch_ocr(tok, MAX_HITS + 1)` bên dưới không phải để lấy kết quả —
    nó là phép đo "token này khớp bao nhiêu dòng trong TOÀN KHO OCR". Ném filter
    vào đó thì mọi token đều khớp vài dòng (vì chỉ còn một video) nên từ thường
    nào cũng lọt cửa hiếm, và probe biến thành nhiễu mà KHÔNG báo lỗi gì. Vậy
    nên: đo hiếm toàn cục, rồi mới bỏ những hàng ngoài video cần tìm. Cách này
    cũng không tốn thêm truy vấn ES nào.
    """
    from data.config.token_probe import ENABLED, MAX_HITS, MAX_PROBES

    if not ENABLED:
        return []
    diem: dict[str, float] = {}
    thong_tin: dict[str, dict] = {}
    for tok in _ung_vien_probe(query_vi, query_en)[:MAX_PROBES]:
        try:
            rows = _branch_ocr(tok, MAX_HITS + 1)  # KHÔNG truyền filter — xem docstring
        except Exception:
            continue
        if not rows or len(rows) > MAX_HITS:
            continue
        # Token càng hiếm càng đáng tin -> nhân thêm 1/log(số dòng khớp).
        hiem = 1.0 / (1.0 + math.log(len(rows) + 1.0))
        for i, r in enumerate(rows, 1):
            # Giữ hạng `i` của danh sách TOÀN CỤC, không đánh số lại sau khi lọc:
            # một hàng đứng hạng 200 toàn kho không được vì lọc mà thành hạng 1.
            # Thứ tự tương đối trong video giữ nguyên, nên bảng xếp không đổi.
            if filter_video_id is not None and r["video_id"] != filter_video_id:
                continue
            kf = r["keyframe_id"]
            diem[kf] = diem.get(kf, 0.0) + hiem / (RRF_K + i)
            thong_tin.setdefault(kf, r)
    xep = sorted(diem, key=lambda k: -diem[k])[:limit]
    return [thong_tin[k] for k in xep]


def _probe_video_votes(query_vi: str, query_en: str | None) -> dict[str, float]:
    """Phiếu bầu MỨC VIDEO từ các token hiếm. Xem data/config/token_probe.py.

    Một token được tính là bằng chứng khi nó khớp ÍT dòng OCR — độ hiếm tự đo,
    không cần biết token đó là tiếng gì. Trả {video_id: điểm}; lỗi ES thì trả
    rỗng chứ không ném, vì đây là tín hiệu BỔ SUNG, không được kéo sập search.
    """
    from data.config.token_probe import (
        ENABLED, MAX_HITS, MAX_PROBES, PROBE_WEIGHT,
    )

    if not ENABLED:
        return {}
    votes: dict[str, float] = {}
    for tok in _ung_vien_probe(query_vi, query_en)[:MAX_PROBES]:
        try:
            rows = _branch_ocr(tok, MAX_HITS + 1)
        except Exception:
            continue
        # Khớp quá nhiều = từ thường, không phân biệt được gì. Khớp 0 = không có.
        if not rows or len(rows) > MAX_HITS:
            continue
        seen: dict[str, int] = {}
        for r in rows:
            seen.setdefault(r["video_id"], len(seen) + 1)
        for vid, hang in seen.items():
            votes[vid] = votes.get(vid, 0.0) + PROBE_WEIGHT / (RRF_K + hang)
    return votes


def _video_diverse_order(
    rows: list[dict], alpha: float, ghi_diem: bool = False, giu_dau: int = 0,
) -> list[dict]:
    """Xếp lại danh sách shot theo VÒNG TRÒN QUA VIDEO thay vì thuần theo điểm.

    Vì sao: BTC chấm `video_id` trước đã — sai video thì frame đúng cũng 0 điểm.
    Mà bảng thuần theo điểm để một video chiếm nhiều dòng liên tiếp, nên video
    đúng đứng hạng 7 ở tầng nhánh có thể rơi xuống dòng 85 (đo được: p1-19).
    Đúng luật "thứ tự nộp XEN KẼ theo shot, không gom" của CLAUDE.md mục 6.

    Cách xếp:
      1. Điểm mỗi video = (1-α)·rrf_tốt_nhất_chuẩn_hoá + α·phiếu_bầu_chuẩn_hoá
      2. Xếp video theo điểm đó
      3. Vòng 1: mỗi video góp shot tốt nhất, theo thứ tự trên
         Vòng 2: mỗi video góp shot tốt thứ hai... cho tới hết

    Nhờ vậy video hạng r xuất hiện ở đúng dòng r, không phụ thuộc video đó có
    bao nhiêu shot mạnh. alpha=0 vẫn xen kẽ nhưng xếp video thuần theo rrf.

    Invariant: KHÔNG thêm/bớt/sửa phần tử nào, chỉ đổi thứ tự. len(ra) == len(vào).
    """
    if not rows:
        return rows

    # GIỮ NGUYÊN `giu_dau` dòng đầu. Post-mortem đợt 1 mục 2.2a: đẩy một câu từ
    # hạng 1 xuống hạng 5 mất 0,20 điểm — đúng bằng lợi ích cứu một câu chết lên
    # top-20. Thiết kế duy nhất không bao giờ lỗ là giữ y nguyên đầu bảng và chỉ
    # dùng phần ĐUÔI để phủ thêm video. Đo được: xáo cả bảng thì top-10 tụt
    # 0,90 -> 0,75 dù top-50 vẫn 1,00.
    dau = rows[:giu_dau]
    con_lai = rows[giu_dau:]
    if not con_lai:
        return rows

    theo_video: dict[str, list[dict]] = {}
    for r in con_lai:
        theo_video.setdefault(r["video_id"], []).append(r)
    da_co_o_dau = {r["video_id"] for r in dau}

    max_rrf = max((r["score"] for r in con_lai), default=0.0) or 1.0
    diem_video = {
        vid: (1.0 - alpha) * (max(x["score"] for x in ds) / max_rrf)
             + alpha * ds[0].get("video_vote", 0.0)
        for vid, ds in theo_video.items()
    }
    # Video CHƯA xuất hiện ở đầu bảng đi trước: mục tiêu của phần đuôi là PHỦ
    # thêm video, không phải đào sâu video đã có mặt.
    thu_tu = sorted(theo_video, key=lambda v: (v in da_co_o_dau, -diem_video[v]))

    ra: list[dict] = list(dau)
    vong = 0
    while len(ra) < len(rows):
        them = False
        for vid in thu_tu:
            ds = theo_video[vid]
            if vong < len(ds):
                ra.append(ds[vong]); them = True
        if not them:
            break
        vong += 1

    # ⚠️ BẮT BUỘC khi đây là lần xếp CUỐI: `allocate()` và `rerank` đều TỰ SẮP
    # LẠI đầu vào theo `score` giảm dần, nên đổi thứ tự list mà không đổi `score`
    # thì thứ tự mới bị vứt ở bước sau và bật/tắt cho ra kết quả GIỐNG HỆT —
    # đúng lỗi im lặng đã xảy ra một lần với tầng rerank (báo cáo K1–K5 §5).
    if ghi_diem:
        for i, r in enumerate(ra):
            r["score_truoc_xen_ke"] = r["score"]
            r["score"] = float(len(ra) - i)
    return ra


def _finalize(
    ket_qua: list[dict], shots: dict, top_k: int, group_by_shot: bool | None,
    video_prior_alpha: float | None = None,
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
    # Xen kẽ theo video TRƯỚC khi cắt top_k — cắt trước rồi xếp lại thì những
    # video bị cắt mất không bao giờ quay lại được.
    from data.config.video_prior import ALPHA as VP_ALPHA, ENABLED as VP_ON
    if VP_ON and video_prior_alpha != 0.0:
        a = VP_ALPHA if video_prior_alpha is None else float(video_prior_alpha)
        ket_qua = _video_diverse_order(ket_qua, a)
    return ket_qua[:top_k]


def search(
    query_vi: str,
    query_en: str | None = None,
    top_k: int = 10,
    branches: dict[str, bool] | None = None,
    group_by_shot: bool | None = None,
    filter_video_id: str | None = None,
    candidate_multiplier: int | None = None,
    rerank_top50: bool | None = None,
    video_prior_alpha: float | None = None,
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
    ket_qua, shots = _search_core(
        query_vi, query_en, top_k, branches, filter_video_id, candidate_multiplier,
        video_prior_alpha,
    )
    kq = _finalize(ket_qua, shots, top_k, group_by_shot, video_prior_alpha)

    # Rerank chạy SAU khi gom shot và cắt top_k — nó xếp lại đúng những dòng sẽ
    # được nộp, không phải cả pool. Mặc định đọc config (đang TẮT, chờ cổng
    # R3.K4), nên Q&A/TRAKE không đổi hành vi một chút nào.
    from backend.retrieval.rerank_top50 import rerank as _rerank_top50

    kq = _rerank_top50(kq, enabled=rerank_top50)

    # Xếp xen kẽ theo video LẦN CUỐI, sau rerank: rerank chọn KHUNG HÌNH tốt
    # trong mỗi shot (việc của nó), còn thứ tự nộp phải bảo đảm mỗi video được
    # thử một lần trước khi thử video nào hai lần — sai video là 0 điểm tuyệt
    # đối, nên phủ video luôn đi trước đào sâu.
    from data.config.video_prior import ALPHA as _A, ENABLED as _ON
    if _ON and video_prior_alpha != 0.0:
        a = _A if video_prior_alpha is None else float(video_prior_alpha)
        if a > 0.0:
            from data.config.video_prior import GIU_DAU
            kq = _video_diverse_order(kq, a, ghi_diem=True, giu_dau=GIU_DAU)
    return kq


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
