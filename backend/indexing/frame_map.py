# backend/indexing/frame_map.py — nguồn DUY NHẤT của frame_map (W0.2)
#
# frame_map: dict keyframe_id → frame index TRONG VIDEO — thứ BTC dùng để chấm.
# CLAUDE.md bất biến 5: nhầm frame index với số thứ tự keyframe = 0 điểm dù đúng video.

from functools import lru_cache
import sys
from pathlib import Path

# Thêm gốc dự án vào path để import được preprocessing
ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from preprocessing.common.frame_map import load_frame_map as load_frame_map_df

@lru_cache(maxsize=1)
def load_frame_map() -> dict[str, int]:
    """
    Trả về dictionary ánh xạ từ kf_id (ví dụ: L26_V022#k0121) 
    sang frame_idx đã bù trừ offset (ví dụ: 1205).
    """
    try:
        # Require_verified=False để có thể chạy được với dữ liệu đang crawl dở
        df = load_frame_map_df(require_verified=False)
        
        # Đảm bảo cột kf_id và frame_idx tồn tại
        if 'kf_id' not in df.columns or 'frame_idx' not in df.columns:
            raise KeyError("Bảng frame_map.parquet thiếu cột kf_id hoặc frame_idx")
            
        # Chuyển đổi DataFrame thành dictionary với định dạng gốc (#k)
        res_dict = df.set_index('kf_id')['frame_idx'].to_dict()
        
        # Bổ sung key format cũ (L21_V001_0001) để tương thích ngược với Thạch và Frontend
        compat_dict = {}
        for k, v in res_dict.items():
            compat_dict[k] = v
            if "#k" in k:
                old_key = k.replace("#k", "_")
                compat_dict[old_key] = v
                
        return compat_dict
        
    except FileNotFoundError:
        raise FileNotFoundError(
            "Không tìm thấy file frame_map.parquet tại data/derived/frame_map.parquet. "
            "Cần chạy module sinh frame_map (b01_recover_missing_frameidx.py) trước."
        )
