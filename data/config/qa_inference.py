"""Cấu hình suy luận Q&A: tách sàng lọc rẻ và xác nhận self-consistency.

Vì sao ở file config: cần rollback `legacy` trong vài giây nếu replay holdout
phát hiện hồi quy; không sửa logic production ngay sát giờ nộp.
"""

import os

# `two_stage`: n=1 sàng lọc, chỉ candidate đủ bằng chứng mới gọi thêm n=2.
# `legacy`: mỗi shot gọi thẳng n=3 như trước 21/08. Mode phải resolve ở runtime:
# test, runner resume và API worker có thể đổi env sau khi module đã import.
QA_INFERENCE_MODE_DEFAULT = "legacy"
QA_INFERENCE_MODES = frozenset({"legacy", "two_stage"})

# Screen và confirm là ba mẫu của CÙNG cohort self-consistency. Khác effort hay
# max_tokens sẽ biến chúng thành hai phép thử khác nhau nhưng vẫn bị vote chung.
QA_COHORT_EFFORT = "high"
QA_COHORT_MAX_TOKENS = 768
QA_SCREEN_EFFORT = QA_COHORT_EFFORT
QA_SCREEN_MAX_TOKENS = QA_COHORT_MAX_TOKENS
QA_SCREEN_CONFIRM_MIN_CONFIDENCE = 0.50

QA_CONFIRM_EFFORT = QA_COHORT_EFFORT
QA_CONFIRM_ADDITIONAL_N = 2
QA_CONFIRM_MAX_TOKENS = QA_COHORT_MAX_TOKENS

# Đây là đúng trần rollback trước khi thêm two-stage; không giảm ngầm quality của
# baseline legacy chỉ để tối ưu thử nghiệm mới.
QA_LEGACY_MAX_TOKENS = 2048

# Trần chỉ tính generation suy luận Q&A (screen/confirm), không tính parse/dịch/
# query expansion. Với bể hiện tại tối đa 5 text + 5 main + 3*3 expansion, 42
# generation chặn fan-out nhưng vẫn cho tối đa 14 cohort đầy đủ n=3.
QA_TWO_STAGE_MAX_GENERATIONS = 42


def qa_inference_mode() -> str:
    """Trả mode hiện hành từ env và từ chối typo thay vì âm thầm dùng default."""
    mode = os.environ.get("QA_INFERENCE_MODE", QA_INFERENCE_MODE_DEFAULT).strip().lower()
    if mode not in QA_INFERENCE_MODES:
        raise ValueError(
            f"QA_INFERENCE_MODE={mode!r} không hợp lệ; dùng "
            f"{sorted(QA_INFERENCE_MODES)}"
        )
    return mode


def qa_runtime_config() -> dict[str, object]:
    """Snapshot JSON-safe của mọi knob làm thay đổi suy luận/cost Q&A."""
    if QA_SCREEN_EFFORT != QA_CONFIRM_EFFORT:
        raise ValueError("screen/confirm phải dùng cùng effort để tạo một cohort")
    if QA_SCREEN_MAX_TOKENS != QA_CONFIRM_MAX_TOKENS:
        raise ValueError("screen/confirm phải dùng cùng max_tokens để tạo một cohort")
    if QA_CONFIRM_ADDITIONAL_N != 2:
        raise ValueError("two-stage đã khóa cohort n=1+n=2")
    if not 1 <= QA_TWO_STAGE_MAX_GENERATIONS <= 42:
        raise ValueError("QA_TWO_STAGE_MAX_GENERATIONS phải nằm trong [1, 42]")
    return {
        "mode": qa_inference_mode(),
        "screen_n": 1,
        "confirm_additional_n": QA_CONFIRM_ADDITIONAL_N,
        "cohort_effort": QA_COHORT_EFFORT,
        "cohort_max_tokens": QA_COHORT_MAX_TOKENS,
        "screen_confirm_min_confidence": QA_SCREEN_CONFIRM_MIN_CONFIDENCE,
        "legacy_n": 3,
        "legacy_max_tokens": QA_LEGACY_MAX_TOKENS,
        "two_stage_max_generations": QA_TWO_STAGE_MAX_GENERATIONS,
    }
