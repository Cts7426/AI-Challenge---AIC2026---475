# backend/indexing/frame_map.py — nguồn DUY NHẤT của frame_map (W0.2)
#
# frame_map: dict keyframe_id → frame index TRONG VIDEO — thứ BTC dùng để chấm.
# CLAUDE.md bất biến 5: nhầm frame index với số thứ tự keyframe = 0 điểm dù đúng video.
#
# Nguồn đọc, theo thứ tự ưu tiên:
# 1. env FRAME_MAP_FILE → file JSON {keyframe_id: frame_idx} sinh từ file
#    map-keyframes THẬT của BTC (task B0.1b sẽ tạo loader đó — TODO: B0.1b).
# 2. Fallback DEV: data/sample/keyframes.json (field frame_index) — chỉ để
#    pipeline chạy được với data mẫu, có in cảnh báo.
# 3. Không có cả hai → FileNotFoundError, KHÔNG trả map rỗng (map rỗng sẽ làm
#    mọi lần tra keyframe gãy từng cái một, khó hiểu hơn là gãy ngay tại nguồn).

import json
import os
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_KEYFRAMES = REPO_ROOT / "data" / "sample" / "keyframes.json"


@lru_cache(maxsize=1)  # map thật có thể hàng trăm nghìn dòng — đọc đĩa 1 lần/process
def load_frame_map() -> dict[str, int]:
    env_file = os.environ.get("FRAME_MAP_FILE")
    if env_file:
        path = Path(env_file)
        if not path.exists():
            raise FileNotFoundError(
                f"FRAME_MAP_FILE={env_file} không tồn tại — kiểm tra lại đường dẫn."
            )
        return {k: int(v) for k, v in json.loads(path.read_text(encoding="utf-8")).items()}

    if SAMPLE_KEYFRAMES.exists():
        print("[cảnh báo] frame_map đang dùng DATA MẪU (data/sample/keyframes.json) — "
              "khi có data BTC phải set FRAME_MAP_FILE trỏ tới map thật.")
        records = json.loads(SAMPLE_KEYFRAMES.read_text(encoding="utf-8"))
        return {r["keyframe_id"]: int(r["frame_index"]) for r in records}

    raise FileNotFoundError(
        "Không có nguồn frame_map nào: env FRAME_MAP_FILE chưa set và "
        f"{SAMPLE_KEYFRAMES} không tồn tại. Tìm file map-keyframes của BTC "
        "(CSV: n, pts_time, fps, frame_idx) — xem docs/contest.md mục frame_map."
    )
