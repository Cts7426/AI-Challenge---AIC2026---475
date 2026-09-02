"""Knob vận hành cho KIS multi-anchor, tách khỏi caller để replay được."""

# ⚠️ TẮT cho Đợt 2 và Đợt 3 — quyết định dựa trên phép đo, không phải phỏng đoán.
# Sau khi sửa lỗi `maxItems`, multi-anchor CHẠY ĐÚNG (19/19 query, 0 planner_error)
# nhưng LÀM TỆ ĐI chất lượng KIS trên dress25:
#     single-anchor  Final 0.4000 · R@5 0.4211
#     multi-anchor   Final 0.3263 · R@5 0.2632
# Chi tiết: docs/evaluation/2026-08-28-multi-anchor-live-measurement.md.
# Bật lại chỉ khi có phép đo mới chứng minh ngược lại — đừng lật hằng này để
# "thử xem sao" ngay trước đợt thi.
ENABLED = False
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
    "duy nhất", "nhóm", "đám", "hàng loạt", "đôi", "cặp",
)
COUNT_CLASSIFIERS = (
    "chiếc", "cái", "con", "tấm", "quả", "bộ", "đôi", "cặp", "chùm",
)
COLOR_MARKER = "màu"
COMMON_COLOR_TERMS = (
    "xanh lá", "xanh dương", "xanh lam", "đỏ", "cam", "vàng", "xanh",
    "tím", "hồng", "nâu", "đen", "trắng", "xám", "ghi", "bạc", "be", "kem",
)
