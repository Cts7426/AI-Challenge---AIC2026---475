# backend/common/answer_match.py — so khớp câu trả lời Q&A, dùng CHUNG cho chấm
# điểm (dev_set/tools/scoring.py) VÀ suy luận production (backend/tasks/qa.py).
#
# Vì sao tách ra khỏi dev_set/tools/scoring.py (chỗ nó được viết đầu tiên)?
# Nếu qa.py tự viết một bộ chuẩn hoá riêng cho majority voting (self-consistency),
# hai bộ "thế nào là 2 câu trả lời giống nhau" sẽ trôi dần khác nhau theo thời
# gian — dev_set chấm một kiểu, production vote một kiểu khác, benchmark nội bộ
# hết còn phản ánh đúng hệ thống thật. Một nguồn sự thật duy nhất cho việc này.
#
# BỐN tầng khớp, từ chặt tới lỏng — dừng ở tầng đầu tiên khớp được:
#   1. Chuẩn hoá (dấu câu → khoảng trắng, hoa/thường, Unicode NFKC)
#   2. Quy đổi số 1-5 ↔ chữ số đếm tiếng Việt ("5" ↔ "năm")
#   3. Chứa nhau theo TẬP TỪ ("5" ⊂ "5 người")            ← thêm 16/08
#   4. Fuzzy (difflib ratio >= 0.85) — bắt lỗi chính tả / thiếu dấu
#
# ⚠️ Số tầng trả về ở `answer_matches()[1]` ĐÃ ĐỔI: fuzzy từ 3 thành 4.
# `app/labels.py::_answer_tier` chỉ so sánh tầng nào NHỎ HƠN (khớp chặt hơn thì
# thắng) chứ không so với hằng số nào, nên không phải sửa theo.

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
    """Tầng 1: bỏ dấu câu, khoảng trắng, lowercase, chuẩn hoá Unicode.

    ⚠️ SỬA 16/08 — dấu câu thay bằng KHOẢNG TRẮNG, không xoá trắng.

    Bản trước dùng `re.sub(r"[^\\w\\s]", "", s)`, tức DÍNH hai bên dấu câu lại:

        "2-1"   -> "21"          "1-2"   -> "12"
        "21/08" -> "2108"        "10-0"  -> "100"

    Hỏng theo CẢ HAI CHIỀU, và `CLAUDE.md` §5.2 liệt kê "số/tỉ số → OCR" là một
    dạng Q&A chính:
      · bỏ sót  — đáp án "2-1" không khớp biến thể "2 - 1"
      · nhận nhầm — `answer_matches("2-1", "21")` trả (True, tầng 1): tỉ số 2-1
        bị chấm ĐÚNG cho đáp án "21". Đây là chấm điểm sai, không phải bỏ sót.

    Thay bằng khoảng trắng rồi `" ".join(split())` gộp lại nên không sinh khoảng
    trắng thừa: "  Năm,   người!  " vẫn ra "năm người" y như trước (test
    `test_normalize_bo_dau_cau_khoang_trang` không đổi kết quả).
    """
    if not s:
        return ""
    s = s.lower()
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"[^\w\s]", " ", s)
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
        if _contains_match(eq_pred, t):
            return True, 3

    for t in eq_targets:
        if _fuzzy_match(eq_pred, t, FUZZY_MATCH_RATIO):
            return True, 4

    return False, 0


def _thuan_so(s: str) -> bool:
    """Chuỗi đã chuẩn hoá có phải chỉ gồm các token SỐ không?

    "100" · "10 0" · "2 1" → True.  "5 người" · "highlands coffee" → False.
    Rỗng → False (để `_fuzzy_match` không tự chặn nhầm chuỗi rỗng ở đây; việc
    chặn rỗng đã làm ở `_contains_match`).
    """
    toks = s.split()
    return bool(toks) and all(t.isdigit() for t in toks)


# Từ ĐỆM — có mặt hay không cũng không đổi nghĩa câu trả lời.
#
# Đây là danh sách CÓ CHỦ ĐÍCH HẸP, không phải stopword list đầy đủ. Mỗi từ thêm
# vào đây là một cách để hai câu trả lời KHÁC NHAU bị chấm là giống nhau — chỉ
# thêm khi thật sự chỉ là lời dẫn hoặc lượng từ.
_FILLER_WORDS = frozenset({
    # ước lượng
    "khoảng", "chừng", "tầm", "độ", "gần", "hơn", "xấp", "xỉ",
    "about", "around", "approximately", "roughly", "nearly",
    # lời dẫn / hệ từ
    "có", "là", "gồm", "cả", "những", "các", "thì", "ạ", "nhé",
    "the", "a", "an", "is", "are", "there",
    # lượng từ + danh từ loại chung
    "một", "người", "cái", "chiếc", "con", "chú", "bạn", "ông", "bà", "anh", "chị",
    "person", "people", "persons",
    # tiền tố địa danh / thuộc tính chung
    "thành", "phố", "tỉnh", "quận", "huyện", "xã", "phường", "màu", "color",
})


def _contains_match(a: str, b: str) -> bool:
    """Tầng 3 — câu NGẮN nằm trọn trong câu DÀI, và phần THỪA chỉ là từ đệm.

    ⚠️ THÊM 16/08. Vì sao cần: `majority_answer()` hứa trong docstring của chính
    nó rằng gom được "5" / "5 người" / "khoảng 5". Đo thật thì KHÔNG:

        majority_answer(["5 người", "5", "khoảng 5"])  ->  phiếu = 1

    Tầng fuzzy đo ratio TOÀN CHUỖI, mà "năm" vs "năm người" chỉ ~0.5 < 0.85.
    Hệ quả dây chuyền ở `backend/tasks/qa.py`: `votes == 1` → `return None` → bỏ
    shot → thử hết 3 shot → `raise RuntimeError` → **câu Q&A 0 điểm**. Tức
    self-consistency đang hoạt động như bộ LOẠI BỎ mọi câu trả lời có diễn đạt
    hơi khác nhau — ngược hẳn mục đích.

    ⚠️ SIẾT lại cùng ngày, sau khi đo thấy bản đầu QUÁ RỘNG. Chỉ kiểm tập con
    thuần thì mọi câu trả lời BỊ CẮT CỤT đều được chấm đúng:

        "Nguyễn"    ⊂ "Nguyễn Văn An"     -> True   ← tên riêng cụt, phải TRƯỢT
        "Highlands" ⊂ "Highlands Coffee"  -> True   ← tên quán cụt, phải TRƯỢT
        "xe"        ⊂ "xe máy"            -> True   ← thiếu loại, phải TRƯỢT
        "người"     ⊂ "5 người"           -> True   ← thiếu con số, phải TRƯỢT

    Đúng cái mà phép kiểm từng-từ của `_fuzzy_match` sinh ra để chặn, và Q&A thì
    `CLAUDE.md` §5.2 nói rõ "tên/chức danh → OCR" là một dạng câu chính.

    Luật hiện tại: tập con **VÀ** mọi từ thừa đều nằm trong `_FILLER_WORDS`.

        "5"        vs "5 người"        thừa {người}      -> đệm      -> KHỚP
        "khoảng 5" vs "5"              thừa {khoảng}     -> đệm      -> KHỚP
        "Nguyễn"   vs "Nguyễn Văn An"  thừa {văn, an}    -> KHÔNG    -> trượt
        "người"    vs "5 người"        thừa {5}          -> KHÔNG    -> trượt

    Con số không bao giờ là từ đệm, nên "người" không thể thay cho "5 người".

    So theo TẬP TỪ chứ không phải substring: `"5" in "15 người"` là True về chuỗi
    nhưng sai về nghĩa. Tách từ thì "5" ⊄ {"15", "người"}.

    Đòi cả hai vế có ÍT NHẤT 1 từ: tập rỗng là tập con của mọi thứ, không chặn thì
    answer rỗng khớp với tất cả.
    """
    wa, wb = set(a.split()), set(b.split())
    if not wa or not wb:
        return False
    if wa == wb:
        return True
    ngan, dai = (wa, wb) if len(wa) < len(wb) else (wb, wa)
    if not ngan <= dai:
        return False
    return (dai - ngan) <= _FILLER_WORDS


def _fuzzy_match(a: str, b: str, threshold: float) -> bool:
    """Tầng 3 — so gần đúng AN TOÀN CHO TÊN RIÊNG.

    ⚠️ SỬA 15/08 (khắc phục L1): logic `all(...)` cũ quá khắt khe với tiếng Việt,
    sai 1 dấu là trượt cả câu. Logic mới: dùng ratio toàn chuỗi để dung túng typo.
    Chỉ khi CÙNG SỐ TỪ, ta chặn trường hợp "nguyễn văn a" vs "nguyễn văn b" bằng
    cách yêu cầu không cặp từ nào được phép sai lệch quá mức (ratio < 0.3).

    ⚠️ SỬA 16/08 — KHÔNG fuzzy khi đáp án THUẦN SỐ.

    Fuzzy sinh ra để dung túng lỗi CHÍNH TẢ và thiếu dấu trong CHỮ. Với số thì
    không có khái niệm "gần đúng": sai một chữ số là một đáp án khác hẳn. Để fuzzy
    chạm vào số thì nó rò ngay cả sau khi tầng 1 đã sửa:

        "10-0" -> "10 0"   vs   "100"   ->   ratio 0.857 >= 0.85   ->  KHỚP NHẦM

    Tỉ số 10-0 bị chấm đúng cho đáp án "100". Đúng loại lỗi mà `CLAUDE.md` §5.2
    nhắc riêng ("số/tỉ số → OCR", "đếm → detector"): các câu này đáp án phải khớp
    CHÍNH XÁC, và chúng đều rơi vào đây.

    Số vẫn khớp được qua tầng 1 (chuẩn hoá), tầng 2 (5 ↔ năm) và tầng 3 (chứa
    nhau) — chỉ mất đúng đường fuzzy, đường duy nhất không an toàn cho số.
    """
    import difflib

    if _thuan_so(a) or _thuan_so(b):
        return False

    overall_ratio = difflib.SequenceMatcher(None, a, b).ratio()
    if overall_ratio < threshold:
        return False

    wa, wb = a.split(), b.split()
    if len(wa) == len(wb):
        for x, y in zip(wa, wb):
            if difflib.SequenceMatcher(None, x, y).ratio() < 0.3:
                return False
                
    return True


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
