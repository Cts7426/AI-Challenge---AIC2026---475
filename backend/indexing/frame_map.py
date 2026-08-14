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
    
    LƯU Ý QUAN TRỌNG: 18% keyframe của BTC bị lệch +1 frame (do lỗi decode). 
    Cột `frame_idx` trong `frame_map.parquet` ĐÃ ĐƯỢC CHỮA KHỎI LỖI NÀY bằng 
    phép kiểm chứng pixel (mse_best). Code bên dưới an toàn 100%, tuyệt đối không 
    tự đọc lại file CSV gốc của BTC.
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
    
    # Bổ sung key format chuẩn hóa keyframes.parquet ({video_id}_{frame_idx:07d})
    # để allocator tra được best_keyframe_id → frame_idx thật.
    #
    # Vì sao KHÔNG dùng replace("#k", "_"):
    #   L21_V001#k0001 → L21_V001_0001  (4 chữ số = ordinal BTC, KHÔNG phải frame_idx)
    #   keyframes.parquet dùng L21_V001_0000014  (7 chữ số = frame_idx zero-padded)
    #   Hai format khác nhau → .get() luôn trả None → allocator mất mức ưu tiên ①
    #   mà không log lỗi gì (lỗi im lặng).
    compat_dict = {}
    for k, v in res_dict.items():
        compat_dict[k] = v  # giữ key gốc format BTC (#k)
        if "#k" in k:
            video_id = k.split("#")[0]
            # Key chuẩn hóa khớp keyframes.parquet: {video_id}_{frame_idx:07d}
            compat_dict[f"{video_id}_{v:07d}"] = v

    return compat_dict
