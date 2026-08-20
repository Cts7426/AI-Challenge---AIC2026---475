# data/config/debug_ui.py — tham số của UI debug và bộ nhãn dev set.
#
# Tách khỏi app/ vì đây là chỗ đổi nhiều lần: đường dẫn ảnh khác nhau theo máy, cửa
# sổ ASR sẽ phải chỉnh khi soi dữ liệu thật. Không thứ nào ở đây nằm trên đường chạy
# lúc thi — UI debug sản xuất ra bộ nhãn, còn E4.2 và D3.5 mới là nơi tiêu thụ.

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Nhãn được commit lên git (là công sức người), mỗi người một file để không conflict:
# dev_set/labels.<labeler>.jsonl. `load_labels()` đọc gộp tất cả.
DEV_SET_DIR = REPO_ROOT / "dev_set"

# Tên người chấm, vào tên file — hai người dùng chung một máy vẫn tách được nhãn.
LABELER = os.environ.get("AIC_LABELER", "unknown")

# correct = trong khoảng đáp án · wrong = đã soi, không phải · unsure = chưa dám kết
# luận (giữ để soi lại, KHÔNG tính điểm).
VALID_LABELS = ("correct", "wrong", "unsure")

# Thư mục ảnh keyframe BTC. Chưa có ảnh → UI vẽ thẻ xám.
# Dùng CHUNG tên biến với backend/api/main.py: ba tên cho một thư mục là cách chắc
# chắn để có người set nhầm cái không ai đọc.
#
# ⚠️ SỬA 19/08 — cùng tên biến mà HAI GIÁ TRỊ MẶC ĐỊNH KHÁC NHAU, đúng cái lỗi mà
# dòng chú thích trên vừa cảnh báo:
#     backend/api/main.py  → data/raw/btc/keyframes   (ĐÚNG chỗ ảnh nằm)
#     file này (bản cũ)    → data/keyframes           (thư mục KHÔNG TỒN TẠI)
#
# Hậu quả: UI debug vẽ THẺ XÁM cho mọi kết quả, không hiện được tấm ảnh nào — mà
# `_draw_image()` coi "không có ảnh" là chuyện bình thường nên không báo lỗi gì.
# Người chấm không nhìn thấy gì thì không chấm được, và đó nhiều khả năng là lý do
# thật vì sao tới 19/08 cả dev set chỉ có 12 nhãn trên đúng 1 truy vấn —
# `reports/E42_TECHNICAL_REPORT.md §7.4.2` quy cho "chưa có ảnh keyframe", nhưng
# ảnh ĐÃ CÓ trên đĩa từ trước, chỉ là trỏ sai chỗ.
#
# Bố cục thư mục nào cũng được: `app/evidence.py::_video_dir()` nhận cả
# `<gốc>/L21_V001/` lẫn `<gốc>/keyframes_L21/L21_V001/` (bộ tải theo lô của BTC).
KEYFRAMES_DIR = Path(os.environ.get(
    "KEYFRAMES_DIR", str(REPO_ROOT / "data" / "raw" / "btc" / "keyframes")))

# Cửa sổ gán đoạn ASR cho một frame, tính bằng giây (BUILD_TASKS B1.7).
ASR_PAD_S = 3.0

# Số kết quả mặc định mỗi lần search. Không để 100: duyệt nhãn thực tế chỉ nhìn vài
# chục cái đầu, mà 100 thẻ có ảnh là trang nặng.
DEFAULT_TOP_K = 20
