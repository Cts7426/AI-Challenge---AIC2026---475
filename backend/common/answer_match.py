# backend/common/answer_match.py — so khớp câu trả lời Q&A, dùng CHUNG cho chấm
# điểm (dev_set/tools/scoring.py) VÀ suy luận production (backend/tasks/qa.py).
#
# Vì sao tách ra khỏi dev_set/tools/scoring.py (chỗ nó được viết đầu tiên)?
# Nếu qa.py tự viết một bộ chuẩn hoá riêng cho majority voting (self-consistency),
# hai bộ "thế nào là 2 câu trả lời giống nhau" sẽ trôi dần khác nhau theo thời
# gian — dev_set chấm một kiểu, production vote một kiểu khác, benchmark nội bộ
# hết còn phản ánh đúng hệ thống thật. Một nguồn sự thật duy nhất cho việc này.
#
# Ba tầng khớp, từ chặt tới lỏng — dừng ở tầng đầu tiên khớp được:
#   1. Chuẩn hoá (bỏ dấu câu, khoảng trắng thừa, hoa/thường, Unicode NFKC)
#   2. Quy đổi số 1-5 ↔ chữ số đếm tiếng Việt ("5" ↔ "năm")
#   3. Fuzzy (difflib ratio >= 0.85) — bắt các biến thể diễn đạt gần giống

from __future__ import annotations

import difflib
import re
import unicodedata

# Ngưỡng fuzzy tầng 3. Không phải "ngưỡng điểm cứng" kiểu bất biến 5 (đó là cho
# cosine CLIP) — đây là ngưỡng KHỚP VĂN BẢN, một phạm trù khác, đo trên difflib
# ratio (đã có sẵn từ dev_set/tools/scoring.py, không đổi để không lệch kết quả
# chấm dev_set cũ).
FUZZY_MATCH_RATIO = 0.85

# Chặn input dài bất thường trước khi vào difflib.SequenceMatcher (tầng 3):
# SequenceMatcher có thể chậm bậc hai trên chuỗi bệnh lý — answer_text hợp lệ
# không bao giờ dài cỡ này, cắt sớm không mất tính đúng đắn.
MAX_ANSWER_LEN = 500

# Quy đổi số 1-5 ↔ chữ tiếng Việt. Giữ nguyên bảng nhỏ như bản gốc dev_set —
# mở rộng (yaml, số > 5) là việc của người sau khi có nhu cầu thật.
_DIGIT_TO_WORD = {"1": "một", "2": "hai", "3": "ba", "4": "bốn", "5": "năm"}


def normalize_text(s: str) -> str:
    """Tầng 1: bỏ dấu câu, khoảng trắng, lowercase, chuẩn hoá Unicode."""
    if not s:
        return ""
    s = s.lower()
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"[^\w\s]", "", s)
    s = " ".join(s.split())
    return s


def equivalent_text(s: str) -> str:
    """Tầng 2: quy đổi số 1-5 sang chữ, để '5' và 'năm' rơi về cùng một dạng."""
    for digit, word in _DIGIT_TO_WORD.items():
        s = re.sub(rf"\b{digit}\b", word, s)
    return s


def answer_matches(pred: str, gt_text: str, variants: list[str]) -> tuple[bool, int]:
    """Ba tầng khớp Q&A. Trả về (is_match, tier [1/2/3/0]), 0 = không khớp tầng nào."""
    if pred is None:
        return False, 0
    if len(pred) > MAX_ANSWER_LEN:
        pred = pred[:MAX_ANSWER_LEN]

    targets = [gt_text] + list(variants)

    norm_pred = normalize_text(pred)
    norm_targets = [normalize_text(t) for t in targets]
    if norm_pred in norm_targets:
        return True, 1

    eq_pred = equivalent_text(norm_pred)
    eq_targets = [equivalent_text(t) for t in norm_targets]
    if eq_pred in eq_targets:
        return True, 2

    for t in eq_targets:
        if difflib.SequenceMatcher(None, eq_pred, t).ratio() >= FUZZY_MATCH_RATIO:
            return True, 3

    return False, 0


def majority_answer(candidates: list[str]) -> tuple[str, int]:
    """Self-consistency: n câu trả lời cùng một câu hỏi → (câu thắng, số phiếu).

    Vì sao không so sánh chuỗi y hệt: `temperature` bị adapter bỏ qua ở backend
    api (xem backend/llm/adapter.py) — 3 lần sinh khác nhau về DIỄN ĐẠT
    ("5" vs "5 người" vs "khoảng 5") nhiều hơn là khác về NỘI DUNG, so bằng
    `==` sẽ chia phiếu ảo và không bao giờ có đa số. Gom nhóm bằng đúng luật
    khớp answer_matches() dùng lúc chấm điểm — nhất quán với cách BTC/dev_set
    coi hai câu trả lời là "giống nhau".

    Trả về ứng viên NGẮN NHẤT trong nhóm thắng làm đại diện (BUILD_TASKS C3.1:
    "answer ngắn nhất mà vẫn đủ" — "5" không phải "khoảng 5 người").
    """
    if not candidates:
        raise ValueError("majority_answer() cần ít nhất 1 câu trả lời")

    groups: list[list[str]] = []
    for c in candidates:
        for g in groups:
            # đại diện nhóm = phần tử đầu tiên rơi vào nhóm đó
            if answer_matches(c, g[0], g[1:])[0]:
                g.append(c)
                break
        else:
            groups.append([c])

    best = max(groups, key=len)
    winner = min(best, key=len)
    return winner, len(best)
