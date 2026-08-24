"""Knob vận hành cho KIS multi-anchor, tách khỏi caller để replay được."""

ENABLED = True
MAX_ANCHORS = 3
MAX_CLIP_TOKENS = 60
RRF_K = 7
TEMPORAL_BONUS = 1.25
PER_ANCHOR_POOL = 100

# Query ngắn và không có dấu hiệu chuyển sự kiện phải giữ đường search hiện tại.
SHORT_QUERY_MAX_WORDS = 18
COMPLEX_MARKER_MIN = 1
COMPLEX_MARKERS = (
    "rồi",
    "sau đó",
    "trước khi",
    "sau khi",
    "tiếp theo",
    ";",
    "→",
)
ORDER_MARKERS = (
    "rồi",
    "sau đó",
    "trước khi",
    "sau khi",
    "tiếp theo",
    "kế tiếp",
    "→",
)
ORDER_MARKER_PAIRS = (
    ("đầu tiên", "sau đó"),
    ("đầu tiên", "cuối cùng"),
)

# Quantifier có thể mang nghĩa khác theo head noun ("hai giờ" != "hai người"),
# nên validator buộc cụm local quantifier + head xuất hiện nguyên dạng trong query.
QUANTIFIER_TERMS = (
    "không", "một", "hai", "ba", "bốn", "tư", "năm", "sáu", "bảy",
    "tám", "chín", "mười", "chục", "trăm", "nghìn", "vài", "nhiều", "ít",
    "duy nhất", "nhóm", "đám", "hàng loạt",
)
COUNT_CLASSIFIERS = (
    "chiếc", "cái", "con", "tấm", "quả", "bộ", "đôi", "cặp", "chùm",
)
COLOR_MARKER = "màu"
