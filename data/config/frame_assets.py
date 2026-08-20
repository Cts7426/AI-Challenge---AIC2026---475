# data/config/frame_assets.py — vị trí hai lớp ảnh dùng chung cho Q&A và UI.
#
# Vì sao tách config: raw keyframe BTC và frame tự trích có quy ước tên hoàn
# toàn khác nhau. Nếu mỗi caller tự ghép đường dẫn, code vẫn chạy nhưng VLM/UI
# âm thầm mất ảnh. Hai root này là cấu hình; phép ánh xạ nằm ở
# backend/common/frame_assets.py.

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Giữ KEYFRAMES_DIR để tương thích lệnh/UI hiện có. Root nhận cả hai bố cục:
#   <root>/<video_id>/001.jpg
#   <root>/keyframes_L21/<video_id>/001.jpg
RAW_KEYFRAMES_DIR = Path(os.environ.get(
    "KEYFRAMES_DIR",
    str(REPO_ROOT / "data" / "raw" / "btc" / "keyframes"),
))

# Frame tự trích dùng frame index tuyệt đối: f0001234.jpg. Đây chỉ là cache;
# frame_map vẫn là nguồn sự thật cho con số nộp BTC.
DERIVED_KEYFRAMES_DIR = Path(os.environ.get(
    "DERIVED_KEYFRAMES_DIR",
    str(REPO_ROOT / "data" / "derived" / "keyframes"),
))
