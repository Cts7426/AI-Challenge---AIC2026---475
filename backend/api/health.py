# backend/api/health.py — W0.3: /health thành DEEP CHECK
#
# ===== Vì sao đổi =====
# `{"status": "ok"}` chỉ chứng minh MỘT điều: tiến trình FastAPI còn sống. Nó
# vẫn trả "ok" khi Milvus chết, khi index rỗng, khi frame_map chưa nạp — tức là
# đúng lúc hệ thống không trả được kết quả nào. Đó là báo xanh giả, và lúc thi
# nó đắt: người vận hành thấy xanh nên đi tìm lỗi ở chỗ khác.
#
# Deep check phải trả lời được câu hỏi thật: "BÂY GIỜ gõ một truy vấn thì hệ này
# có trả ra kết quả có nghĩa không?" — nên nó ping từng thành phần trên đường
# chạy của /search, kèm độ trễ, và nói rõ cái nào chết.
#
# ===== Phân loại: CRITICAL vs cảnh báo =====
# HTTP 503 chỉ khi có thành phần CRITICAL chết — thứ mà thiếu nó thì mọi kết quả
# đều sai hoặc rỗng:
#   elasticsearch · milvus (kể cả khi collection RỖNG) · không gian vector · frame_map
# Các thứ còn lại (index ocr/asr chưa nạp, chưa có ảnh keyframe, CLIP chưa
# preload) chỉ hạ trạng thái xuống "degraded" + HTTP 200: search vẫn chạy bằng
# các nguồn còn lại, đúng quy ước "1 service chết thì search chạy tiếp".
#
# ⚠️ Milvus có collection nhưng row_count = 0 được tính là CHẾT. Đây là ca lỗi
# im lặng kinh điển của dự án này: mọi thứ "lên" bình thường, search vẫn trả
# HTTP 200, chỉ là nhánh vector luôn rỗng và bảng xếp hạng thành vô nghĩa.
#
# ===== Ba luật của chính hàm check =====
# 1. KHÔNG BAO GIỜ ném lỗi ra ngoài — endpoint /health mà 500 thì vô dụng.
# 2. KHÔNG tự nạp model CLIP: nạp mất ~16s. Health check chỉ BÁO CÁO model đã
#    preload hay chưa, không tự gây ra độ trễ đó (và không để một cú curl vô
#    tình chiếm RAM giữa lúc thi).
# 3. Mọi check có TRẦN THỜI GIAN. DB treo (khác với DB chết) là ca tệ nhất:
#    không có trần thì /health treo theo, đúng lúc cần nó nhất.

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from pathlib import Path

# Trần thời gian cho MỘT check. 5s vì check nặng nhất (frame_map, ~1,9s đọc
# parquet lần đầu) phải lọt, còn DB treo thì bị cắt sớm.
CHECK_TIMEOUT_S = 5.0

# Timeout riêng cho các lệnh gọi DB — ngắn hơn trần trên để lỗi mạng hiện ra
# dưới dạng "down: timeout" của chính check đó, không phải của lớp ngoài.
DB_TIMEOUT_S = 3.0

OK, WARN, DOWN = "ok", "warn", "down"


@dataclass(frozen=True)
class Check:
    """Kết quả kiểm tra MỘT thành phần."""

    name: str
    status: str          # ok | warn | down
    latency_ms: float
    detail: str = ""
    critical: bool = False
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {
            "name": self.name,
            "status": self.status,
            "latency_ms": round(self.latency_ms, 1),
            "critical": self.critical,
        }
        if self.detail:
            d["detail"] = self.detail
        if self.extra:
            d.update(self.extra)
        return d


def _do(name: str, critical: bool, fn) -> Check:
    """Chạy một check, tự đo thời gian, tự nuốt mọi lỗi thành trạng thái `down`.

    Lỗi kết nối là THÔNG TIN cần báo cáo, không phải sự cố của /health. Nuốt ở
    đây để chỗ gọi không phải bọc try/except quanh từng cái.
    """
    t0 = time.perf_counter()
    try:
        status, detail, extra = fn()
    except Exception as e:
        return Check(name, DOWN, (time.perf_counter() - t0) * 1000,
                     f"{type(e).__name__}: {e}", critical)
    return Check(name, status, (time.perf_counter() - t0) * 1000, detail, critical, extra)


# ------------------------------------------------------------------ từng check

def _check_elasticsearch() -> tuple[str, str, dict]:
    """Ping ES thật (es.info()), báo version + trạng thái cluster.

    Dùng es_client.connect() chứ không tự dựng Elasticsearch() (bất biến 2) —
    và nhờ vậy được luôn phần chẩn đoán lệch phiên bản client/server của nó,
    thứ mà một cú ping thô sẽ chỉ báo là "False".
    """
    from backend.indexing.es_client import ES_URL, connect

    es = connect()
    try:
        es = es.options(request_timeout=DB_TIMEOUT_S)
    except AttributeError:
        pass  # client cũ không có .options() — vẫn dùng timeout mặc định
    info = es.info()
    return OK, f"{ES_URL} · ES {info['version']['number']}", {}


def _check_es_indices() -> tuple[str, str, dict]:
    """Đếm document từng index. Index thiếu/rỗng = MẤT MỘT NHÁNH search.

    Không critical: search bọc từng nguồn trong try/except và chạy tiếp bằng các
    nguồn còn lại. Nhưng phải nói ra — "search vẫn trả kết quả" và "search dùng
    đủ 5 nguồn" là hai chuyện khác nhau, và chênh lệch đó là điểm số.
    """
    from backend.indexing.es_client import connect
    from backend.indexing.load_asr import INDEX_NAME as ASR
    from backend.indexing.load_metadata import INDEX_NAME as METADATA
    from backend.indexing.load_objects import INDEX_NAME as OBJECTS
    from backend.indexing.load_ocr import INDEX_NAME as OCR

    es = connect()
    dem: dict[str, int | None] = {}
    for ten in (METADATA, OBJECTS, OCR, ASR):
        try:
            dem[ten] = (int(es.count(index=ten)["count"])
                        if es.indices.exists(index=ten) else None)
        except Exception:
            dem[ten] = None

    thieu = [k for k, v in dem.items() if not v]        # None (chưa có) hoặc 0 doc
    status = OK if not thieu else WARN
    detail = " · ".join(
        f"{k}={'chưa có' if v is None else v}" for k, v in dem.items()
    )
    if thieu:
        detail += f"  → mất nhánh: {', '.join(thieu)}"
    return status, detail, {"doc_counts": dem}


def _check_milvus() -> tuple[str, str, dict]:
    """Ping Milvus + đếm vector trong collection keyframes.

    row_count = 0 là CHẾT, không phải "ok mà rỗng": nhánh vector là nguồn chính
    của toàn bộ pipeline (KIS, Q&A, TRAKE đều bắt đầu từ nó). Không có vector
    thì mọi thứ phía sau chỉ còn BM25 — vẫn trả 100 dòng, vẫn qua validator,
    và gần như chắc chắn sai. Báo xanh cho trạng thái đó là có hại.
    """
    from backend.indexing.milvus_client import COLLECTION_NAME, MILVUS_URL, connect

    client = connect()
    if not client.has_collection(COLLECTION_NAME):
        return DOWN, (
            f"{MILVUS_URL} sống nhưng CHƯA CÓ collection '{COLLECTION_NAME}' — "
            "chạy: python -m backend.indexing.load_clip"
        ), {"row_count": 0}

    rows = int(client.get_collection_stats(COLLECTION_NAME).get("row_count", 0))
    if rows == 0:
        return DOWN, (
            f"collection '{COLLECTION_NAME}' RỖNG (0 vector) — search vector luôn "
            "trả rỗng, kết quả chỉ còn BM25. Nạp: python -m backend.indexing.load_clip"
        ), {"row_count": 0}
    return OK, f"{MILVUS_URL} · {rows:,} vector", {"row_count": rows}


def _check_vector_space() -> tuple[str, str, dict]:
    """Index và config có CÙNG không gian vector không (bất biến 1).

    Đây là check quan trọng nhất mà không ai nhìn thấy bằng mắt: nạp index bằng
    model A rồi query bằng model B thì Milvus vẫn trả top-k với cosine 0.2–0.3
    trông y hệt kết quả đúng. assert_index_meta() so .meta.json với config và
    ném lỗi khi lệch — ở đây chỉ cần gọi nó và dịch kết quả sang trạng thái.
    """
    from backend.indexing.load_clip import assert_index_meta

    meta = assert_index_meta(strict=False)
    if meta is None:
        return WARN, "chưa có clip_index.meta.json — index CLIP chưa nạp lần nào", {}
    # Meta khớp config nhưng nạp từ 0 file features: model/dim/metric ĐÚNG, chỉ
    # là chưa có gì trong đó. Báo OK ở đây là đúng về mặt "cùng không gian vector"
    # nhưng dễ đọc nhầm thành "index sẵn sàng" — nên hạ xuống cảnh báo.
    if not meta.get("n_vectors"):
        return WARN, (
            f"meta khớp config nhưng index nạp từ 0 vector "
            f"({meta.get('missing_files', '?')} file .npy không tìm thấy lúc nạp lúc "
            f"{meta.get('built_at')}) — kiểm CLIP_FEATURES_DIR rồi nạp lại"
        ), {"n_vectors_indexed": 0}
    return OK, (
        f"{meta.get('model_open_clip')}/{meta.get('pretrained')} · dim "
        f"{meta.get('dim')} · {meta.get('metric')} · nạp {meta.get('built_at')}"
    ), {"n_vectors_indexed": meta.get("n_vectors")}


def _check_clip_model() -> tuple[str, str, dict]:
    """CLIP đã preload chưa — và nếu rồi thì ENCODE THẬT một câu để kiểm chứng.

    KHÔNG tự nạp model (luật 2 đầu file): chưa preload thì chỉ cảnh báo. Đã
    preload thì phép kiểm chứng rẻ (~chục ms) và đáng: encode một câu cố định
    rồi kiểm |v| ≈ 1 và số chiều khớp config. L2-norm sai là bất biến 1 bị vỡ —
    cosine trong Milvus lúc đó không còn là cosine nữa.
    """
    import backend.retrieval.text_query as tq
    from data.config.clip_model import CLIP_EMBEDDING_DIM

    if tq._model is None:
        return WARN, ("model CLIP chưa preload — truy vấn đầu tiên sẽ chịu ~16s "
                      "nạp model (server khởi động qua lifespan thì đã preload sẵn)"), {}

    import numpy as np

    v = tq.encode_text("a photo of a cat")
    norm = float(np.linalg.norm(v))
    if v.shape[0] != CLIP_EMBEDDING_DIM:
        return DOWN, (f"encoder trả dim {v.shape[0]} nhưng config ghi "
                      f"{CLIP_EMBEDDING_DIM} — sai model"), {}
    if abs(norm - 1.0) > 1e-3:
        return DOWN, (f"vector query KHÔNG chuẩn hoá L2 (|v| = {norm:.4f}) — "
                      "metric COSINE của Milvus không còn đúng (bất biến 1)"), {}
    return OK, f"đã preload · dim {v.shape[0]} · |v| = {norm:.4f}", {}


def _check_frame_map() -> tuple[str, str, dict]:
    """frame_map có nạp được không. Thiếu nó = nộp sai frame = 0 điểm (bất biến 5).

    Đây là critical dù nó không phải "service": tên file keyframe là SỐ THỨ TỰ,
    BTC chấm theo FRAME INDEX trong video. Không tra được bảng này thì bài nộp
    sai toàn bộ dù tìm đúng video lẫn đúng cảnh.
    """
    from backend.indexing.frame_map import load_frame_map

    m = load_frame_map()
    if not m:
        return DOWN, "frame_map RỖNG — mọi frame_id nộp ra sẽ sai (bất biến 5)", {}
    return OK, f"{len(m):,} khoá", {"n_keys": len(m)}


def _check_keyframes_dir() -> tuple[str, str, dict]:
    """Có ảnh keyframe trên đĩa không — UI cần để hiển thị, Q&A cần để hỏi VLM."""
    from data.config.frame_assets import DERIVED_KEYFRAMES_DIR, RAW_KEYFRAMES_DIR

    for root in (RAW_KEYFRAMES_DIR, DERIVED_KEYFRAMES_DIR):
        if not Path(root).is_dir():
            continue
        try:
            sample = next(Path(root).rglob("*.jpg"), None)
        except OSError:
            sample = None
        if sample is not None:
            return OK, f"{root} · ví dụ {sample.name}", {"root": str(root)}
    return WARN, (
        "chưa có JPG raw/derived (đặt KEYFRAMES_DIR hoặc "
        "DERIVED_KEYFRAMES_DIR) — Q&A visual sẽ thiếu bằng chứng"
    ), {}


# ------------------------------------------------------------------ API chính

CHECKS: tuple[tuple[str, bool, object], ...] = (
    # (tên, critical, hàm)
    ("elasticsearch", True, _check_elasticsearch),
    ("milvus", True, _check_milvus),
    ("vector_space", True, _check_vector_space),
    ("frame_map", True, _check_frame_map),
    ("es_indices", False, _check_es_indices),
    ("clip_model", False, _check_clip_model),
    ("keyframes_dir", False, _check_keyframes_dir),
)


def _warm_imports() -> float:
    """Nạp trước mọi module nặng, TRONG THREAD GỌI. Trả số ms đã tốn.

    Vì sao bắt buộc: các check chạy song song, nhưng `import pandas` /
    `import pymilvus` lần đầu chiếm KHOÁ IMPORT của Python — mọi thread còn lại
    đứng chờ. Đo lần đầu (trước khi có hàm này) cho kết quả vô nghĩa: check chỉ
    kiểm tra một thư mục cũng báo 2.940 ms, y hệt check đang thật sự chờ Milvus.
    Một deep check báo sai latency thì mất đúng thứ nó sinh ra để cung cấp.
    Nạp trước ở đây → con số của từng check là I/O THẬT của service đó.
    """
    t0 = time.perf_counter()
    for mod in (
        "backend.indexing.es_client", "backend.indexing.milvus_client",
        "backend.indexing.frame_map", "backend.indexing.load_clip",
        "backend.indexing.load_asr", "backend.indexing.load_metadata",
        "backend.indexing.load_objects", "backend.indexing.load_ocr",
        "backend.retrieval.text_query", "backend.api.main",
    ):
        try:
            __import__(mod)
        except Exception:
            pass  # module hỏng sẽ hiện ra ở chính check của nó, với thông báo đúng
    return (time.perf_counter() - t0) * 1000


def deep_check(timeout_s: float = CHECK_TIMEOUT_S) -> dict:
    """Ping mọi thành phần trên đường chạy /search. KHÔNG BAO GIỜ ném lỗi.

    Output: {status, checks[], latency_ms}
      status = "ok"        — mọi thứ xanh
             = "degraded"  — có cảnh báo, search vẫn chạy nhưng thiếu nguồn
             = "down"      — có thành phần CRITICAL chết → chỗ gọi trả HTTP 503

    Các check độc lập nhau → chạy song song, tổng độ trễ = check chậm nhất.
    Check nào quá `timeout_s` bị cắt và ghi "down: quá Xs" — DB TREO nguy hiểm
    hơn DB chết, vì nó kéo theo cả thứ đang hỏi thăm nó.
    """
    t0 = time.perf_counter()
    import_ms = _warm_imports()
    pool = ThreadPoolExecutor(max_workers=len(CHECKS))
    try:
        futs = [(ten, critical, pool.submit(_do, ten, critical, fn))
                for ten, critical, fn in CHECKS]
        ket_qua: list[Check] = []
        for ten, critical, fut in futs:
            try:
                ket_qua.append(fut.result(timeout=timeout_s))
            except FutureTimeout:
                ket_qua.append(Check(
                    ten, DOWN, timeout_s * 1000,
                    f"quá {timeout_s}s không trả lời — service treo (khác với chết)",
                    critical,
                ))
    finally:
        # wait=False: check bị timeout vẫn đang chạy trong thread của nó; đợi nó
        # xong là đánh mất đúng cái timeout vừa đặt ra.
        pool.shutdown(wait=False, cancel_futures=True)

    if any(c.critical and c.status == DOWN for c in ket_qua):
        tong = DOWN
    elif any(c.status in (WARN, DOWN) for c in ket_qua):
        tong = "degraded"
    else:
        tong = OK

    return {
        "status": tong,
        "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
        # Tách riêng thời gian nạp module: lần gọi đầu của một tiến trình mới tốn
        # ~2s cho nó, các lần sau ~0. Không tách thì người đọc tưởng DB chậm.
        "import_ms": round(import_ms, 1),
        "checks": [c.to_dict() for c in ket_qua],
    }


def format_report(kq: dict) -> str:
    """Bản in cho người đọc — dùng ở CLI, không dùng trong response HTTP."""
    bieu_tuong = {OK: "OK  ", WARN: "WARN", DOWN: "DOWN"}
    dong = [f"trạng thái chung: {kq['status'].upper()}  ({kq['latency_ms']:.0f} ms)"]
    for c in kq["checks"]:
        sao = "*" if c["critical"] else " "
        dong.append(f"  {bieu_tuong.get(c['status'], '?')}{sao} {c['name']:<15} "
                    f"{c['latency_ms']:>7.1f} ms  {c.get('detail', '')}")
    dong.append("  (* = critical — chết cái nào thì /health trả HTTP 503)")
    return "\n".join(dong)


if __name__ == "__main__":
    # Chạy deep check mà KHÔNG cần dựng server:  python -m backend.api.health
    import sys

    kq = deep_check()
    print(format_report(kq))
    sys.exit(0 if kq["status"] != DOWN else 1)
