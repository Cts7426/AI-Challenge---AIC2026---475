# backend/retrieval/text_vi_query.py — R3.X4: encode truy vấn tiếng Việt
#
# Cặp với `data/config/text_vi_vector.py`. Dùng cho nhánh tìm kiếm NGỮ NGHĨA
# tiếng Việt trên đoạn ASR — thứ mà bốn nhánh BM25 hiện có không làm được
# (chúng khớp TỪ, không khớp NGHĨA).
#
# ⚠️ HAI CÁI BẪY IM LẶNG, cả hai đều không crash:
#
# 1. Model họ PhoBERT (dangvantuan/vietnamese-embedding) được huấn luyện trên
#    văn bản ĐÃ TÁCH TỪ ("người_đàn_ông" chứ không phải "người đàn ông"). Bỏ
#    bước `ViTokenizer.tokenize()` thì model vẫn chạy, vector vẫn norm = 1,
#    Milvus vẫn trả top-k — chỉ chất lượng tụt mà KHÔNG có gì báo.
#    Encode TÀI LIỆU và encode TRUY VẤN phải qua ĐÚNG CÙNG một bước tiền xử lý;
#    lệch nhau là hai không gian khác nhau.
#
# 2. Chuẩn hoá L2 (bất biến 1). Index dùng inner product, quên normalize thì
#    kết quả nghiêng về đoạn văn dài chứ không phải đoạn hợp nghĩa nhất.
#
# ===== Chạy thử =====
#   python -m backend.retrieval.text_vi_query "người đàn ông chèo thuyền"

from __future__ import annotations

import numpy as np

from data.config.text_vi_vector import CAN_TACH_TU, EMBEDDING_DIM, MODEL_NAME

_model = None


def _tach_tu(text: str) -> str:
    """Tách từ tiếng Việt cho model họ PhoBERT. Không cần thì trả nguyên văn.

    `pyvi` chưa cài mà config đòi tách từ → NÉM LỖI. Lặng lẽ bỏ qua bước này là
    tạo ra đúng bẫy #1 ở đầu file: chạy được, không ai biết là đang kém đi.
    """
    if not CAN_TACH_TU:
        return text
    try:
        from pyvi import ViTokenizer
    except ImportError as e:
        raise RuntimeError(
            f"Model {MODEL_NAME} cần tách từ (CAN_TACH_TU=True) nhưng chưa có "
            f"`pyvi`. Cài: pip install pyvi. Bỏ qua bước này thì chất lượng tụt "
            f"mà không có cảnh báo nào."
        ) from e
    return ViTokenizer.tokenize(text)


def _load():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(MODEL_NAME)
    return _model


def encode_text_vi(query_vi: str) -> np.ndarray:
    """Truy vấn tiếng Việt → vector ĐÃ chuẩn hoá L2, đúng số chiều trong config."""
    vec = _load().encode(
        [_tach_tu(query_vi)],
        normalize_embeddings=True,   # bất biến 1: metric là inner product
        show_progress_bar=False,
    )[0].astype(np.float32)

    if vec.shape[0] != EMBEDDING_DIM:
        raise RuntimeError(
            f"{MODEL_NAME} trả {vec.shape[0]} chiều nhưng config khai "
            f"{EMBEDDING_DIM}. Sửa data/config/text_vi_vector.py cho khớp TRƯỚC "
            f"khi encode index, không thì index và truy vấn ở hai không gian."
        )
    n = float(np.linalg.norm(vec))
    if abs(n - 1.0) > 1e-3:
        raise RuntimeError(f"Vector chưa chuẩn hoá (norm={n:.6f}) — xem bất biến 1.")
    return vec


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("query", help="truy vấn tiếng Việt")
    a = ap.parse_args()
    v = encode_text_vi(a.query)
    print(f"model      : {MODEL_NAME}")
    print(f"tách từ    : {CAN_TACH_TU} → {_tach_tu(a.query)!r}")
    print(f"vector     : {v.shape[0]} chiều · norm={float(np.linalg.norm(v)):.6f}")
    print(f"5 phần tử  : {v[:5]}")
