"""Cấu hình hypotheses Q&A để cache/portfolio có thể replay mà không hardcode."""

from __future__ import annotations

import os
import unicodedata
from pathlib import Path


ANSWER_MODES = (
    "visual_count",
    "visual_read",
    "ocr",
    "asr",
    "metadata",
    "visual_attribute",
)

# Tăng version khi prompt/schema planner hoặc prompt suy luận đổi nghĩa.
QA_PLANNER_PROMPT_VERSION = "qa-planner-v2"
QA_INFERENCE_PROMPT_VERSION = "qa-evidence-v2"
QA_HYPOTHESIS_CACHE_SCHEMA_VERSION = 1

# Canonical của mọi hypothesis luôn đi trước; sau đó mỗi hypothesis chỉ chiếm
# tối đa một frame thay thế trước khi phần đuôi phủ candidate retrieval mới.
QA_HYPOTHESIS_ALTERNATIVES_PER_HYPOTHESIS = 1

# Sentinel không mang bằng chứng trả lời; normalize case/whitespace ở caller.
QA_SENTINEL_ANSWERS = frozenset({
    "không đủ căn cứ",
    "không có thông tin",
    "không đủ thông tin",
    "insufficient evidence",
    "no information",
    "not enough information",
})

# Chỉ reject prefix khi token kế tiếp là một continuation mang nghĩa "không có
# evidence". Nhờ vậy answer thật như "No Information Technology" hay
# "Không có thông tin liên lạc" không bị loại chỉ vì cùng tiền tố.
QA_SENTINEL_PREFIX_CONTINUATIONS = frozenset({
    "để", "trong", "từ", "về", "được", "có", "nhằm",
    "is", "was", "to", "in", "from", "about", "available", "provided",
})

# Câu từ chối có vô hạn biến thể nên không thể chỉ dựa vào danh sách sentinel.
# Matcher production chỉ xét answer BẮT ĐẦU bằng phủ định rồi nhắc tới khả năng
# xác định/bằng chứng. Hai surface thị giác bên dưới là dữ liệu đã quan sát thật;
# giữ exact để không loại nhầm đáp án phủ định hợp lệ như "Không có người trong ảnh".
QA_REFUSAL_PREFIXES = frozenset({
    "không", "chưa", "chẳng",
    "no", "not", "cannot", "unable", "insufficient",
})

QA_REFUSAL_SUBJECT_PREFIXES = frozenset({"tôi", "mình", "i", "we"})

QA_REFUSAL_EVIDENCE_PHRASES = frozenset({
    "xác định", "bằng chứng", "căn cứ", "đọc được", "nhận diện",
    "determine", "evidence", "identify", "legible", "discern",
})

QA_REFUSAL_EXACT_ANSWERS = frozenset({
    "không có cân hiển thị trong hình ảnh",
    "không thấy cân hoặc số trên cân trong hình",
})

QA_REFUSAL_SHORT_ANSWERS = frozenset({
    "không biết", "không rõ", "chưa rõ",
    "not sure", "unclear", "don't know", "do not know",
    "i don't know", "i do not know",
})

QA_REFUSAL_MIN_WORDS = 2


def _normalize_answer(answer_text: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(answer_text))
    normalized = " ".join(normalized.casefold().split())
    while normalized and unicodedata.category(normalized[0]).startswith("P"):
        normalized = normalized[1:].lstrip()
    while normalized and unicodedata.category(normalized[-1]).startswith("P"):
        normalized = normalized[:-1].rstrip()
    return normalized


def _la_cau_tu_choi(normalized: str) -> bool:
    """Nhận diện câu từ chối mà không loại nhầm đáp án phủ định có nội dung.

    Input là answer đã normalize; output True chỉ cho surface đo thật hoặc câu
    bắt đầu bằng phủ định rồi nói về khả năng xác định/bằng chứng. Invariant:
    cụm evidence nằm trong câu trích dẫn không đủ để làm answer bị loại.
    """
    if normalized in QA_REFUSAL_EXACT_ANSWERS or normalized in QA_REFUSAL_SHORT_ANSWERS:
        return True
    tokens = normalized.split()
    if tokens and tokens[0] in QA_REFUSAL_SUBJECT_PREFIXES:
        tokens = tokens[1:]
    candidate = " ".join(tokens)
    if candidate in QA_REFUSAL_SHORT_ANSWERS:
        return True
    if len(tokens) < QA_REFUSAL_MIN_WORDS or tokens[0] not in QA_REFUSAL_PREFIXES:
        return False
    return any(phrase in candidate for phrase in QA_REFUSAL_EVIDENCE_PHRASES)


def is_valid_qa_answer(answer_text: str | None) -> bool:
    """Từ chối answer rỗng/sentinel trước khi nó trở thành hypothesis/CSV."""
    if answer_text is None:
        return False
    normalized = _normalize_answer(answer_text)
    if not normalized or normalized in QA_SENTINEL_ANSWERS:
        return False
    for prefix in QA_SENTINEL_ANSWERS:
        marker = prefix + " "
        if not normalized.startswith(marker):
            continue
        suffix = normalized[len(marker):]
        first_token = suffix.split(" ", 1)[0]
        first_token = _normalize_answer(first_token)
        if first_token in QA_SENTINEL_PREFIX_CONTINUATIONS:
            return False
    return not _la_cau_tu_choi(normalized)


def qa_hypothesis_cache_dir() -> Path:
    """Đường cache có thể đổi bằng env cho test/job; caller không tự ghép path."""
    configured = os.environ.get("QA_HYPOTHESIS_CACHE_DIR", "").strip()
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[2] / "data" / "cache" / "qa_hypotheses"


def qa_hypothesis_config_snapshot() -> dict[str, object]:
    """Snapshot JSON-safe của knobs ảnh hưởng identity và thứ tự portfolio."""
    return {
        "answer_modes": list(ANSWER_MODES),
        "planner_prompt_version": QA_PLANNER_PROMPT_VERSION,
        "inference_prompt_version": QA_INFERENCE_PROMPT_VERSION,
        "cache_schema_version": QA_HYPOTHESIS_CACHE_SCHEMA_VERSION,
        "alternatives_per_hypothesis": QA_HYPOTHESIS_ALTERNATIVES_PER_HYPOTHESIS,
        "sentinel_answers": sorted(QA_SENTINEL_ANSWERS),
        "sentinel_prefix_continuations": sorted(QA_SENTINEL_PREFIX_CONTINUATIONS),
        "refusal_prefixes": sorted(QA_REFUSAL_PREFIXES),
        "refusal_subject_prefixes": sorted(QA_REFUSAL_SUBJECT_PREFIXES),
        "refusal_evidence_phrases": sorted(QA_REFUSAL_EVIDENCE_PHRASES),
        "refusal_exact_answers": sorted(QA_REFUSAL_EXACT_ANSWERS),
        "refusal_short_answers": sorted(QA_REFUSAL_SHORT_ANSWERS),
        "refusal_min_words": QA_REFUSAL_MIN_WORDS,
    }
