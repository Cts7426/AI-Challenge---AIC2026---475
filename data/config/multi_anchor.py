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
    " rồi ",
    " sau đó ",
    " trước khi ",
    " sau khi ",
    " tiếp theo ",
    ";",
    "→",
)
ORDER_MARKERS = (
    " rồi ",
    " sau đó ",
    " trước khi ",
    " sau khi ",
    " tiếp theo ",
    " kế tiếp ",
    " đầu tiên ",
    " cuối cùng ",
    "→",
)

# Validator chỉ được chấp nhận màu/số lượng đã xuất hiện trong query gốc.
COLOR_TERMS = (
    "xanh lá", "xanh dương", "xanh lam", "đỏ", "cam", "vàng", "xanh", "tím",
    "hồng", "nâu", "đen", "trắng", "xám", "ghi", "bạc", "be", "kem",
)
COUNT_TERMS = (
    "không", "một", "hai", "ba", "bốn", "tư", "năm", "sáu", "bảy",
    "tám", "chín", "mười", "chục", "trăm", "nghìn", "đôi", "cặp",
    "vài", "nhiều", "ít",
)
