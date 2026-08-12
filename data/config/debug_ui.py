# data/config/debug_ui.py — D2.1: tham số của UI debug và bộ nhãn dev set
#
# Vì sao tách ra config thay vì để trong app/: cùng lý do với slot_budget.py —
# chỗ nào ĐỔI NHIỀU LẦN thì tách khỏi chỗ viết một lần là xong. Đường dẫn ảnh đổi
# theo máy từng người, cửa sổ ASR sẽ phải chỉnh khi soi dữ liệu thật.
#
# ⚠️ Không có gì trong file này nằm trên đường chạy lúc thi. UI debug là công cụ
# dev: nó sản xuất ra bộ nhãn, còn bộ nhãn mới là thứ E4.2 và D3.5 tiêu thụ.

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# ------------------------------------------------------------------ bộ nhãn

# Nhãn là CÔNG SỨC NGƯỜI (chấm 200 nhãn là vài giờ ngồi soi) nên nó được commit
# lên git, KHÔNG gitignore. Mỗi người một file để không bao giờ conflict:
#     dev_set/labels.minhhoang.jsonl
#     dev_set/labels.thach.jsonl
# `load_labels()` đọc gộp tất cả.
DEV_SET_DIR = REPO_ROOT / "dev_set"

# Tên người chấm, vào tên file. Đặt qua env để hai người dùng chung một máy vẫn
# tách được nhãn của nhau.
LABELER = os.environ.get("AIC_LABELER", "unknown")

# Ba giá trị nhãn hợp lệ.
#   correct — frame nằm trong khoảng đáp án
#   wrong   — đã soi, không phải
#   unsure  — đã soi, chưa dám kết luận (giữ lại để soi lại sau, KHÔNG tính điểm)
NHAN_HOP_LE = ("correct", "wrong", "unsure")

# ------------------------------------------------------------------ hiển thị

# Thư mục ảnh keyframe BTC (kiểu `L21_V001/0001.jpg`). Chưa có ảnh → UI vẽ thẻ
# xám thay vì sập. Dùng CHUNG tên biến với backend/api/main.py — ba tên khác nhau
# cho một thư mục là cách chắc chắn để có người set nhầm cái không ai đọc.
KEYFRAMES_DIR = Path(os.environ.get("KEYFRAMES_DIR", str(REPO_ROOT / "data" / "keyframes")))

# Cửa sổ gán đoạn ASR cho một frame, tính bằng giây.
# ±3s theo BUILD_TASKS B1.7 ("ASR gán theo cửa sổ ±3s, KHÔNG gán cả video").
ASR_PAD_S = 3.0

# Số kết quả mặc định của một lần search trong UI. Không để 100: duyệt nhãn thực
# tế chỉ nhìn vài chục cái đầu, mà 100 thẻ có ảnh là trang nặng và cuộn mỏi tay.
TOP_K_MAC_DINH = 20
