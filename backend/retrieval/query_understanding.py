# backend/retrieval/query_understanding.py — C1.1: hiểu truy vấn v1
#
# Nhận mô tả tiếng Việt của người thao tác, trả về thứ CLIP dùng được:
#     {caption_main, captions_expanded[4], constraints}
#
# ===== Ba prompt, ba việc khác nhau =====
#   dịch      → 1 caption EN ngắn, giọng CHÚ THÍCH ẢNH (CLIP học từ caption ảnh,
#               không học từ câu hội thoại — "a man wearing a conical hat"
#               hoạt động tốt hơn "there is a man who is wearing a hat")
#   mở rộng   → 4 caption EN KHÁC NHAU cho cùng một cảnh, để đánh nhiều mũi
#   ràng buộc → {scene, objects, colors, count, time, text_seen} cho tầng lọc
#
# ⚠️ Prompt mở rộng CẤM thêm chi tiết không có trong query gốc (bất biến 6).
# Thêm "màu đỏ" hay "hai người" mà đề không nói = tự thu hẹp sai chỗ → trượt.
#
# ⚠️ Giới hạn 77 token của CLIP: mỗi caption phải ≤ MAX_CAPTION_TOKENS, và
# ĐẾM BẰNG TOKENIZER TRONG CODE, không ước lượng bằng mắt. Câu dài hơn bị CLIP
# cắt cụt lặng lẽ — phần đuôi bị vứt mà không ai báo.
#
# ===== Vì sao ba prompt chạy SONG SONG =====
# Chúng độc lập (cả ba đều đọc query gốc tiếng Việt), nên độ trễ = câu chậm
# nhất chứ không phải tổng ba câu. Mở rộng cũng dịch thẳng từ tiếng Việt chứ
# không dịch lại từ caption EN — dịch chồng dịch thì sai lệch cộng dồn.
#
# ===== Chạy thử =====
#   python -m backend.retrieval.query_understanding "thủ môn cản phá quả phạt đền"
#   (cần ANTHROPIC_API_KEY, hoặc LLM_BACKEND=local + ollama serve)

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

from backend.llm.adapter import llm
from data.config.clip_model import CLIP_MODEL_NAME

# Ngân sách token cho một caption. CLIP chặn cứng ở 77 (gồm cả token mở/đóng);
# 60 chừa biên an toàn để không bao giờ chạm ngưỡng cắt cụt.
MAX_CAPTION_TOKENS = 60
N_EXPANDED = 4

_tokenizer_cache = None


def _tokenizer():
    global _tokenizer_cache
    if _tokenizer_cache is None:
        import open_clip

        _tokenizer_cache = open_clip.get_tokenizer(CLIP_MODEL_NAME)
    return _tokenizer_cache


def count_clip_tokens(text: str) -> int:
    """Đếm token THẬT bằng tokenizer của chính model CLIP đang dùng.

    Trả về 77 nghĩa là câu đã chạm trần và bị cắt — coi như quá dài.
    """
    ids = _tokenizer()([text])[0]
    return int((ids != 0).sum())


def _cat_cho_vua(text: str, gioi_han: int = MAX_CAPTION_TOKENS) -> str:
    """Cắt bớt từ cuối câu cho tới khi vừa ngân sách token.

    Chỉ dùng làm lưới an toàn cuối cùng (sau khi đã hỏi lại LLM một lần):
    thà mất vài từ cuối còn hơn để CLIP tự cắt ở giữa từ.
    """
    tu = text.split()
    while tu and count_clip_tokens(" ".join(tu)) > gioi_han:
        tu.pop()
    return " ".join(tu)


def _ep_do_dai(caption: str, lam_lai) -> str:
    """Bảo đảm caption ≤ MAX_CAPTION_TOKENS: hỏi lại 1 lần, rồi mới cắt tay."""
    if count_clip_tokens(caption) <= MAX_CAPTION_TOKENS:
        return caption
    ngan_hon = lam_lai()
    if count_clip_tokens(ngan_hon) <= MAX_CAPTION_TOKENS:
        return ngan_hon
    return _cat_cho_vua(ngan_hon)


# ------------------------------------------------------------------ ba prompt

def translate(query_vi: str) -> str:
    """Query tiếng Việt → 1 caption tiếng Anh ngắn, giọng chú thích ảnh."""

    def hoi(them: str = "") -> str:
        return llm(
            "Translate this Vietnamese description of a video moment into ONE short "
            "English image caption for a CLIP retrieval engine.\n"
            "Rules: describe only what is VISIBLE; concrete nouns and actions; no "
            "narrative words like 'video shows' or 'scene of'; no invented details; "
            f"under {MAX_CAPTION_TOKENS} tokens.{them}\n"
            "Reply with ONLY the caption, no quotes, no explanation.\n\n"
            f"Vietnamese: {query_vi}"
        ).strip().strip('"')

    return _ep_do_dai(hoi(), lambda: hoi(" Make it noticeably SHORTER than before."))


EXPAND_SCHEMA = {
    "type": "object",
    "properties": {"captions": {"type": "array", "items": {"type": "string"}}},
    "required": ["captions"],
    "additionalProperties": False,
}


def expand(query_vi: str, n: int = N_EXPANDED) -> list[str]:
    """Query tiếng Việt → n caption EN khác nhau MÔ TẢ CÙNG MỘT cảnh.

    Vì sao nhiều caption ngắn thay vì một câu dài: CLIP chặn 77 token, và mỗi
    caption được encode RIÊNG rồi hợp nhất — nối dài thành một đoạn là tự cắt
    mất thông tin (bất biến 6).
    """
    raw = llm(
        f"Write {n} DIFFERENT English image captions for the same video moment "
        "described below, for a CLIP retrieval engine.\n"
        "Vary the wording, viewpoint and level of detail across captions.\n"
        "HARD RULE: do NOT add any detail that is not in the original description — "
        "no invented colors, counts, places, times, emotions or objects. If the "
        "description does not mention a color, no caption may mention a color.\n"
        f"Each caption must be under {MAX_CAPTION_TOKENS} tokens and read like an "
        "image caption, not a sentence about a video.\n\n"
        f"Vietnamese description: {query_vi}",
        json_schema=EXPAND_SCHEMA,
    )
    caps = [c.strip() for c in json.loads(raw)["captions"] if c and c.strip()]

    # Model có thể trả thiếu/thừa — chuẩn hoá về đúng n, không để chỗ gọi phải lo
    caps = [_ep_do_dai(c, lambda c=c: _cat_cho_vua(c)) for c in caps[:n]]
    while len(caps) < n and caps:
        caps.append(caps[len(caps) % max(1, len(caps))])
    return caps


CONSTRAINTS_SCHEMA = {
    "type": "object",
    "properties": {
        "scene": {"type": "string"},                                  # "" nếu không rõ
        "objects": {"type": "array", "items": {"type": "string"}},    # nhãn EN, khớp OpenImages
        "colors": {"type": "array", "items": {"type": "string"}},
        "count": {"anyOf": [{"type": "integer"}, {"type": "null"}]},  # số lượng nếu đề nói rõ
        "time": {"type": "string"},                                   # "day"/"night"/"" ...
        "text_seen": {"type": "array", "items": {"type": "string"}},  # chữ nhìn thấy trên hình
    },
    "required": ["scene", "objects", "colors", "count", "time", "text_seen"],
    "additionalProperties": False,
}


def extract_constraints(query_vi: str) -> dict:
    """Query tiếng Việt → ràng buộc có cấu trúc cho tầng lọc/rerank.

    `objects` để tiếng Anh vì nhãn detector (OpenImages) là tiếng Anh;
    `text_seen` giữ nguyên tiếng Việt vì đó là chữ OCR đọc được trên hình.
    """
    raw = llm(
        "Extract search constraints from this Vietnamese description of a video "
        "moment. Return JSON only.\n"
        "- scene: short English scene type (e.g. 'stadium', 'news studio'), \"\" if unclear\n"
        "- objects: English object nouns actually mentioned (detector-label style)\n"
        "- colors: colors actually mentioned\n"
        "- count: integer ONLY if the description states a number, else null\n"
        "- time: 'day' | 'night' | '' if not stated\n"
        "- text_seen: text that would be VISIBLE on screen, keep original Vietnamese\n"
        "HARD RULE: extract only what is stated. Never guess or infer. Empty is "
        "a correct answer.\n\n"
        f"Vietnamese description: {query_vi}",
        json_schema=CONSTRAINTS_SCHEMA,
    )
    return json.loads(raw)


# ------------------------------------------------------------------- API chính

@lru_cache(maxsize=256)
def understand(query_vi: str) -> str:
    """Chạy cả ba prompt SONG SONG, trả JSON string (cache theo hash query).

    Trả str để `lru_cache` an toàn (dict không hashable và có thể bị sửa nhầm
    bởi chỗ gọi). Dùng understand_dict() nếu muốn object.
    """
    with ThreadPoolExecutor(max_workers=3) as pool:
        f_main = pool.submit(translate, query_vi)
        f_exp = pool.submit(expand, query_vi)
        f_con = pool.submit(extract_constraints, query_vi)

        def _an_toan(fut, ten, mac_dinh):
            """Một prompt hỏng không được kéo sập cả bước hiểu truy vấn."""
            try:
                return fut.result()
            except Exception as e:
                print(f"  [cảnh báo] prompt {ten} lỗi, dùng giá trị rỗng: {e}")
                return mac_dinh

        caption_main = _an_toan(f_main, "dịch", "")
        captions_expanded = _an_toan(f_exp, "mở rộng", [])
        constraints = _an_toan(f_con, "ràng buộc", {
            "scene": "", "objects": [], "colors": [],
            "count": None, "time": "", "text_seen": [],
        })

    # Dịch hỏng mà mở rộng chạy được → lấy tạm caption đầu làm caption chính,
    # còn hơn trả rỗng cho tầng search
    if not caption_main and captions_expanded:
        caption_main = captions_expanded[0]

    return json.dumps({
        "query_vi": query_vi,
        "caption_main": caption_main,
        "captions_expanded": captions_expanded,
        "constraints": constraints,
    }, ensure_ascii=False)


def understand_dict(query_vi: str) -> dict:
    return json.loads(understand(query_vi))


def main() -> None:
    ap = argparse.ArgumentParser(description="Hiểu truy vấn tiếng Việt (C1.1)")
    ap.add_argument("query", help="mô tả khoảnh khắc bằng tiếng Việt")
    args = ap.parse_args()

    import time

    t0 = time.perf_counter()
    kq = understand_dict(args.query)
    ms = (time.perf_counter() - t0) * 1000

    print(f'\nQuery: "{kq["query_vi"]}"   ({ms:.0f} ms)\n')
    print(f'caption chính ({count_clip_tokens(kq["caption_main"])} token):')
    print(f'   {kq["caption_main"]}')
    print("\ncaption mở rộng:")
    for i, c in enumerate(kq["captions_expanded"], 1):
        print(f'  {i}. [{count_clip_tokens(c):>2} token] {c}')
    print("\nràng buộc:")
    print(json.dumps(kq["constraints"], ensure_ascii=False, indent=2))

    from backend.llm.adapter import print_usage
    print()
    print_usage()


if __name__ == "__main__":
    main()
