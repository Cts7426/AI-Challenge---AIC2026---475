"""Cấu hình encoder SigLIP2 — điểm tháo lắp duy nhất để bật/tắt và quay đầu.

Vì sao có file này thay vì sửa thẳng clip_model.py: đổi encoder là đổi cả không
gian vector. Nếu ghi đè cấu hình CLIP mà kết quả tệ hơn thì không còn đường lùi,
và lỗi loại này KHÔNG crash — nó trả kết quả sai với điểm cosine trông bình
thường (CLAUDE.md mục 12). Giữ hai cấu hình song song thì A/B được và quay đầu
bằng một biến môi trường.

Bằng chứng chọn model (đo trên hồ 44 video, cùng anchor, cùng tập keyframe):
    CLIP ViT-B/32   Final 0.5976 · top-5 10/17 · mất 1 câu
    SigLIP2 ViT-L/16 Final 0.7153 · top-5 15/17 · mất 0 câu
SO400M mạnh hơn L/16 (428M vs 316M tham số) nên chọn SO400M; hai bậc trên nó
(SO400M-384, gopt-384) cần ~90 và ~300 giờ encode trên máy hiện tại nên loại.

Bật/tắt lúc chạy:
    VECTOR_BACKEND=siglip2   -> nhánh vector dùng collection SigLIP2
    VECTOR_BACKEND=clip      -> (mặc định) giữ nguyên hành vi cũ
"""
from __future__ import annotations

import os
from pathlib import Path

SIGLIP2_MODEL_NAME = "ViT-SO400M-16-SigLIP2-256"
SIGLIP2_PRETRAINED = "webli"
SIGLIP2_EMBEDDING_DIM = 1152
SIGLIP2_METRIC = "COSINE"
SIGLIP2_COLLECTION = "keyframes_siglip2"

# fp16 lúc encode: đo được nhanh gấp 2,81 lần trên MPS, cosine với fp32 là
# 0,9995 và top-10 xếp hạng không đổi -> an toàn cho cả index lẫn query.
SIGLIP2_USE_HALF = True


def siglip2_emb_dir() -> Path:
    """Thư mục .npy tách theo model: vector L/16 là 1024 chiều còn SO400M là
    1152, trộn hai loại thì lỗi chỉ lộ ra lúc nạp Milvus hoặc không lộ ra."""
    repo = Path(__file__).resolve().parents[2]
    return repo / "data/derived" / f"emb_{SIGLIP2_MODEL_NAME}"


def vector_backend() -> str:
    """'siglip2' hoặc 'clip'. Mặc định 'clip' để không đổi hành vi ngoài ý muốn."""
    return os.environ.get("VECTOR_BACKEND", "clip").strip().lower()


def use_siglip2() -> bool:
    return vector_backend() == "siglip2"
