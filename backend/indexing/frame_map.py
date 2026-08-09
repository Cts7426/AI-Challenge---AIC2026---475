# backend/indexing/frame_map.py — nguồn DUY NHẤT của frame_map (W0.2)
#
# frame_map: dict keyframe_id → frame index TRONG VIDEO — thứ BTC dùng để chấm.
# CLAUDE.md bất biến 5: nhầm frame index với số thứ tự keyframe = 0 điểm dù đúng video.

import pandas as pd
from pathlib import Path
from functools import lru_cache

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "derived"
FRAME_MAP_PATH = DATA_DIR / "frame_map.parquet"

@lru_cache(maxsize=1)
def load_frame_map() -> dict[str, int]:
    """
    Trả về dictionary ánh xạ từ kf_id (ví dụ: L26_V022#k0121 hoặc L26_V022_0001205) 
    sang frame_idx đã bù trừ offset (ví dụ: 1205).
    """
    if not FRAME_MAP_PATH.exists():
        raise FileNotFoundError(
            f"Không tìm thấy file frame_map.parquet tại {FRAME_MAP_PATH}."
        )
        
    df = pd.read_parquet(FRAME_MAP_PATH)
    
    # Đảm bảo cột kf_id và frame_idx tồn tại
    if 'kf_id' not in df.columns or 'frame_idx' not in df.columns:
        raise KeyError("Bảng frame_map.parquet thiếu cột kf_id hoặc frame_idx")
        
    # Chuyển đổi DataFrame thành dictionary với định dạng gốc (#k)
    res_dict = df.set_index('kf_id')['frame_idx'].to_dict()
    
    # Bổ sung key format chuẩn 1fps (_000000) và format cũ (_0001) để tương thích ngược 100%
    compat_dict = {}
    for k, v in res_dict.items():
        compat_dict[k] = v
        if "#k" in k:
            old_key = k.replace("#k", "_")
            compat_dict[old_key] = v
            
    return compat_dict
