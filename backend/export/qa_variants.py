# backend/export/qa_variants.py — tạo portfolio answer Q&A trước khi ghi CSV.
#
# BTC đang có hai mô tả mâu thuẫn về chấm answer. Module này chỉ thay ANSWER của
# những dòng Q&A đã có frame thật từ allocator, không đụng frame_id, thứ hạng KIS
# hay TRAKE, và cũng không biết/không tự ghi CSV. Nhờ vậy thay chiến thuật không
# thể tái sinh lỗi frame index ở tầng format.

from __future__ import annotations

import re
from dataclasses import replace

from data.config.qa_evaluation import (
    QA_EXACT_VARIANT_FRAMES,
    QA_MAX_SURFACE_FORMS,
    QA_ROBUST_VARIANT_FRAMES,
    QA_SUBMISSION_POLICIES,
)
from data.config.submit_format import Answer


_NUMBER_WORDS = {"1": "một", "2": "hai", "3": "ba", "4": "bốn", "5": "năm"}
_UNIT_FORMS = {
    "g": ("g", "gram"),
    "gram": ("g", "gram"),
    "gam": ("g", "gram"),
    "kg": ("kg", "kilogram"),
    "kilogram": ("kg", "kilogram"),
    "kilogam": ("kg", "kilogram"),
    "m": ("m", "mét"),
    "mét": ("m", "mét"),
    "met": ("m", "mét"),
    "meter": ("m", "mét"),
    "metre": ("m", "mét"),
}
_NUMBER_WITH_UNIT = re.compile(
    r"^(\d+(?:[.,]\d+)*)(?:\s*)(g|gram|gam|kg|kilogram|kilogam|m|mét|met|meter|metre)$",
    re.IGNORECASE,
)


def answer_surface_forms(answer_text: str, limit: int = QA_MAX_SURFACE_FORMS) -> list[str]:
    """Một fact Q&A -> các dạng bề mặt an toàn để hedge strict string.

    Input: answer ngắn do pipeline sinh và số form tối đa. Output: list không
    trùng, phần tử đầu luôn là nguyên văn. Invariant: không tự trim, làm tròn,
    dịch nghĩa hay thêm fact; answer có whitespace đầu/cuối giữ nguyên để
    validator phát hiện thay vì che giấu lỗi nhập liệu.
    """
    if limit < 1:
        raise ValueError(f"limit phải >= 1, nhận {limit}")

    forms = [answer_text]
    if answer_text != answer_text.strip():
        return forms

    match = _NUMBER_WITH_UNIT.fullmatch(answer_text)
    if match:
        number, raw_unit = match.groups()
        compact_unit, word_unit = _UNIT_FORMS[raw_unit.lower()]
        forms.extend((f"{number}{compact_unit}", f"{number} {compact_unit}",
                      f"{number} {word_unit}"))
    elif answer_text in _NUMBER_WORDS:
        forms.append(_NUMBER_WORDS[answer_text])
    elif answer_text.lower() != answer_text:
        # Case là biến thể bề mặt duy nhất an toàn cho text tự do. Không title-case
        # vì có thể làm sai tên riêng, và không đổi dấu vì có thể đổi nghĩa.
        forms.append(answer_text.lower())

    unique: list[str] = []
    for form in forms:
        if form not in unique:
            unique.append(form)
        if len(unique) >= limit:
            break
    return unique


def apply_qa_submission_policy(answers: list[Answer], policy: str) -> list[Answer]:
    """Các Answer Q&A -> portfolio cùng độ dài cho một chính sách nộp.

    Input: list Q&A đã xếp hạng và semantic/exact/robust. Output: list cùng độ
    dài. Invariant: mỗi output chỉ là bản sao một input với answer_text đổi dạng;
    video_id, frame_ids, keyframe_id và số slot không đổi. `exact` nhân form ở
    10 frame đầu, `robust` chỉ ở frame đầu, còn `semantic` không đổi gì.
    """
    if policy not in QA_SUBMISSION_POLICIES:
        raise ValueError(f"policy phải là một trong {QA_SUBMISSION_POLICIES}, nhận {policy!r}")
    if not answers or policy == "semantic":
        return list(answers)

    variant_frames = (
        QA_EXACT_VARIANT_FRAMES if policy == "exact" else QA_ROBUST_VARIANT_FRAMES
    )
    output: list[Answer] = []
    for index, answer in enumerate(answers):
        forms = answer_surface_forms(answer.answer_text or "") if index < variant_frames else [
            answer.answer_text or ""
        ]
        for form in forms:
            output.append(replace(answer, answer_text=form))
            if len(output) == len(answers):
                return output

    # `output` luôn đủ vì mỗi input sinh ít nhất chính nó; nhánh này chỉ giúp
    # mypy và biến lỗi cấu trúc tương lai thành lỗi rõ thay vì file nộp thiếu dòng.
    raise RuntimeError("portfolio Q&A thiếu answer dù input không rỗng")
