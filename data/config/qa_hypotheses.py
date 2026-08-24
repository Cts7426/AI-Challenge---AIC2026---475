"""Cấu hình hypotheses Q&A để cache/portfolio có thể replay mà không hardcode."""

from __future__ import annotations

import os
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
    }
