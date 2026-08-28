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

# Chỉ reject prefix khi token kế tiếp là một continuation mang nghĩa "không có
# evidence". Nhờ vậy answer thật như "No Information Technology" hay
# "Không có thông tin liên lạc" không bị loại chỉ vì cùng tiền tố.
QA_SENTINEL_PREFIX_CONTINUATIONS = frozenset({
    "để", "trong", "từ", "về", "được", "có", "nhằm",
    "is", "was", "to", "in", "from", "about", "available", "provided",
})

# ---------------------------------------------------------------- dò TỪ CHỐI
# Danh sách chuỗi ở trên là danh sách ĐÓNG, mà LLM đẻ biến thể vô hạn. Đo thật
# (28/08, đề đợt 1): 6 chuỗi trên chỉ bắt được 1/5 câu từ chối thực tế —
# "Không thể xác định từ bằng chứng", "Không có cân hiển thị trong hình ảnh",
# "Không thấy cân hoặc số trên cân", "Không đủ bằng chứng" đều lọt vì sai một
# chữ. Nên chuyển sang dò HÌNH DẠNG: phủ định + từ nói về việc thiếu bằng chứng.
QA_REFUSAL_NEGATIONS = frozenset({
    "không", "chưa", "chẳng",
    "no", "not", "cannot", "unable", "insufficient",
})

# CỐ Ý không có "thông tin"/"information"/"dữ liệu": chúng xuất hiện trong đáp
# án THẬT ("Không có thông tin liên lạc", "No Information Technology") nên dò
# theo chúng là loại nhầm. Chỉ giữ từ nói về việc NHÌN/ĐỌC được bằng chứng —
# những từ này chỉ xuất hiện khi model đang từ chối, không xuất hiện trong đáp
# án thật. Các chuỗi "không có thông tin ..." vẫn do QA_SENTINEL_ANSWERS bắt.
QA_REFUSAL_EVIDENCE_WORDS = frozenset({
    "xác định", "thấy", "đọc được", "nhận ra", "nhận diện",
    "hiển thị", "quan sát", "bằng chứng", "căn cứ",
    "trong hình", "trong ảnh", "trong khung hình",
    "determine", "identify", "visible", "legible", "discern",
    "evidence", "shown in", "in the image",
})

# Chỉ dò khi answer đủ dài. "Không" (câu có/không) và "0" (câu đếm) là đáp án
# THẬT — luật dài >= 3 từ giữ chúng lại.
QA_REFUSAL_MIN_WORDS = 3

# ------------------------------------------------- kiểu đáp án theo answer_mode
# Đáp án phải đúng DẠNG mà câu hỏi đòi. Đo thật: p1-17 hỏi "tên con đèo là gì"
# mà hạng 1 là "Chồn Hương" (tên con vật) trong khi "Đèo Bạch Mã" nằm hạng 2 —
# hai bên hoà confidence 0.62, không có gì phá hoà theo đúng kiểu câu hỏi.
#   digit  = bắt buộc chứa chữ số
#   short  = cụm danh từ ngắn, không quá số từ cho phép
QA_ANSWER_MODE_RULES: dict[str, dict[str, object]] = {
    "visual_count": {"digit": True, "max_words": 4},
    "visual_read": {"digit": False, "max_words": 8},
    "ocr": {"digit": False, "max_words": 8},
    "asr": {"digit": False, "max_words": 12},
    "metadata": {"digit": False, "max_words": 8},
    "visual_attribute": {"digit": False, "max_words": 8},
}

# ------------------------------------------------------- phạt theo hạng retrieval
# Q&A có HAI cửa tử độc lập: sai video = 0 dù answer đúng. Đo thật: winner của
# p1-3 là shot hạng 104 và p1-15 là hạng 105 — chọn thuần theo confidence tự
# khai, mà confidence lại bị ĐẢO NGƯỢC (câu từ chối "không thấy cân" được 0.60
# vì "không thấy gì" là quan sát dễ, còn đọc số mờ thật thì model chỉ dám 0.30).
# Phạt theo log10 hạng: hạng 1 -> 0, hạng 10 -> -0.15, hạng 100 -> -0.30.
QA_WINNER_RANK_PENALTY = 0.15

# Khi KHÔNG shot nào trả lời được: nộp bấy nhiêu VIDEO đầu bảng retrieval, mỗi
# video một dòng, xếp đúng thứ tự retrieval. Đáp án lúc đó vô nghĩa nên tín hiệu
# duy nhất còn giá trị là "đào video nào trước" — 10 video vừa đủ để người soi
# lướt trong ngân sách vài phút mà không bỏ sót video đúng.
QA_PLACEHOLDER_VIDEOS = 10


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
        "refusal_negations": sorted(QA_REFUSAL_NEGATIONS),
        "refusal_evidence_words": sorted(QA_REFUSAL_EVIDENCE_WORDS),
        "refusal_min_words": QA_REFUSAL_MIN_WORDS,
        "answer_mode_rules": {k: dict(v) for k, v in sorted(QA_ANSWER_MODE_RULES.items())},
        "winner_rank_penalty": QA_WINNER_RANK_PENALTY,
    }
