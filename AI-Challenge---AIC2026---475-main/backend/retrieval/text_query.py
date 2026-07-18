# backend/retrieval/text_query.py — Task 2.1: query tiếng Việt → CLIP embedding
#
# Đường đi: query VI → llm() dịch sang câu EN ngắn gọn → CLIP text encoder
# → vector chuẩn hoá L2 (sẵn sàng search COSINE trong Milvus).
#
# Vì sao phải dịch? CLIP của OpenAI huấn luyện trên caption TIẾNG ANH —
# đưa thẳng tiếng Việt vào tokenizer là ra vector rác.
#
# ⚠️ NHẮC (CLAUDE.md mục 3): version CLIP trong data/config/clip_model.py đang là
# GIẢ ĐỊNH (ViT-B/32 openai) vì BTC chưa công bố. Trước khi tin kết quả search
# trên data thật, PHẢI đối chiếu với BTC. Sai model → khác không gian vector.
#
# Chạy thử (từ thư mục gốc repo):
#     python -m backend.retrieval.text_query "người đàn ông đội nón lá"
#     python -m backend.retrieval.text_query --no-translate "a man wearing a conical hat"
#       (--no-translate: bỏ qua llm(), dùng khi chưa set ANTHROPIC_API_KEY
#        hoặc query đã là tiếng Anh)

import argparse

import numpy as np

from backend.llm.adapter import llm
from data.config.clip_model import CLIP_MODEL_NAME, CLIP_PRETRAINED, CLIP_EMBEDDING_DIM

# Model CLIP giữ ở mức module (singleton): load mất vài giây + vài trăm MB RAM,
# chỉ trả giá 1 lần lúc request đầu, các query sau encode trong ~chục ms.
_model = None
_tokenizer = None


def _get_model():
    global _model, _tokenizer
    if _model is None:
        # Import lười: các module khác (loader, API) import file này sẽ không
        # phải trả giá import torch/open_clip nếu không encode gì
        import open_clip
        import torch

        _model, _, _ = open_clip.create_model_and_transforms(
            CLIP_MODEL_NAME, pretrained=CLIP_PRETRAINED
        )
        _model.eval()  # tắt dropout/batchnorm-update — chỉ suy luận, không train
        _tokenizer = open_clip.get_tokenizer(CLIP_MODEL_NAME)
        torch.set_grad_enabled(False)  # không train → khỏi tốn RAM giữ gradient
    return _model, _tokenizer


def translate_to_english(query_vi: str) -> str:
    """Dịch mô tả khoảnh khắc sang câu tiếng Anh ngắn, hợp khẩu vị CLIP.

    Prompt ép trả về CHỈ câu dịch — không lời dẫn, không giải thích —
    vì output đưa thẳng vào tokenizer, thừa chữ nào nhiễu chữ đó.
    """
    prompt = (
        "Translate this Vietnamese description of a video moment into ONE short "
        "English phrase for a CLIP image search engine. Keep it visual and concrete. "
        "Reply with ONLY the English phrase, nothing else.\n\n"
        f"Vietnamese: {query_vi}"
    )
    return llm(prompt).strip().strip('"')


def encode_text(text_en: str) -> np.ndarray:
    """Encode câu tiếng Anh thành vector CLIP chuẩn hoá L2, shape (dim,)."""
    model, tokenizer = _get_model()
    tokens = tokenizer([text_en])
    features = model.encode_text(tokens)
    features = features / features.norm(dim=-1, keepdim=True)  # L2 — khớp COSINE bên Milvus
    vec = features[0].cpu().numpy().astype(np.float32)
    assert vec.shape == (CLIP_EMBEDDING_DIM,), (
        f"Model trả dim {vec.shape[0]} nhưng config ghi {CLIP_EMBEDDING_DIM} — "
        "sửa CLIP_EMBEDDING_DIM trong data/config/clip_model.py cho khớp."
    )
    return vec


def text_to_embedding(query: str, translate: bool = True) -> tuple[str, np.ndarray]:
    """API chính cho Task 2.2: query (VI hoặc EN) → (câu EN đã dùng, embedding)."""
    text_en = translate_to_english(query) if translate else query
    return text_en, encode_text(text_en)


def main() -> None:
    parser = argparse.ArgumentParser(description="Query tiếng Việt → CLIP embedding")
    parser.add_argument("query", help="mô tả khoảnh khắc (tiếng Việt, hoặc EN nếu --no-translate)")
    parser.add_argument("--no-translate", action="store_true",
                        help="bỏ qua bước dịch llm() — dùng query trực tiếp")
    args = parser.parse_args()

    text_en, vec = text_to_embedding(args.query, translate=not args.no_translate)

    print(f'Query gốc : {args.query}')
    print(f'Đưa vào CLIP: "{text_en}"')
    print(f"Embedding : shape={vec.shape}, dtype={vec.dtype}, L2-norm={np.linalg.norm(vec):.4f}")
    print(f"5 chiều đầu: {np.round(vec[:5], 4).tolist()}")
    print("\n⚠️ Version CLIP đang là GIẢ ĐỊNH (ViT-B/32 openai) — đối chiếu BTC "
          "trước khi tin kết quả search trên features thật.")


if __name__ == "__main__":
    main()
