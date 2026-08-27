"""Encode câu truy vấn bằng ĐÚNG model SigLIP2 đã dùng để index.

Bất biến sống còn (CLAUDE.md mục 12.2): index và query phải cùng một không gian
vector. Nếu lệch model, Milvus vẫn trả top-k với cosine 0.2–0.3 — đúng khoảng
"bình thường" của CLIP — nên kết quả sai mà không có gì báo lỗi. Vì vậy file này
đọc tên model từ cùng một config mà loader dùng, và assert số chiều.

Model giữ ở mức module (singleton): nạp mất vài giây và vài trăm MB, chỉ trả
giá một lần ở truy vấn đầu.
"""
from __future__ import annotations

import numpy as np

from data.config.siglip2_model import (
    SIGLIP2_EMBEDDING_DIM,
    SIGLIP2_MODEL_NAME,
    SIGLIP2_PRETRAINED,
    SIGLIP2_USE_HALF,
)

_model = None
_tokenizer = None
_device = None


def _get_model():
    global _model, _tokenizer, _device
    if _model is None:
        import open_clip
        import torch

        _model, _, _ = open_clip.create_model_and_transforms(
            SIGLIP2_MODEL_NAME, pretrained=SIGLIP2_PRETRAINED
        )
        _device = "mps" if torch.backends.mps.is_available() else "cpu"
        _model = _model.eval().to(_device)
        # fp16 chỉ dùng khi index cũng encode bằng fp16 — đã kiểm cosine 0,9995
        # với fp32 và top-10 không đổi thứ hạng.
        if SIGLIP2_USE_HALF and _device == "mps":
            _model = _model.half()
        _tokenizer = open_clip.get_tokenizer(SIGLIP2_MODEL_NAME)
    return _model, _tokenizer, _device


def encode_text(text_en: str) -> np.ndarray:
    """Câu tiếng Anh -> vector SigLIP2 chuẩn hoá L2, shape (dim,)."""
    import torch

    model, tokenizer, device = _get_model()
    tokens = tokenizer([text_en]).to(device)
    with torch.no_grad():          # suy luận thuần, an toàn ở mọi thread
        features = model.encode_text(tokens)
        features = features / features.norm(dim=-1, keepdim=True)   # khớp COSINE
    vec = features[0].float().cpu().numpy().astype(np.float32)
    assert vec.shape == (SIGLIP2_EMBEDDING_DIM,), (
        f"model trả dim {vec.shape[0]} nhưng config ghi {SIGLIP2_EMBEDDING_DIM} — "
        "sửa SIGLIP2_EMBEDDING_DIM trong data/config/siglip2_model.py cho khớp"
    )
    return vec
