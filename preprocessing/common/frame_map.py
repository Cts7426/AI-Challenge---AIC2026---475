"""
Module truy cập frame_map.parquet an toàn.

VÌ SAO CÓ 2 CỘT FRAME_IDX?
Do bộ BTC trích xuất keyframe bị lệch fps so với .mp4, frame_idx (gốc) không
khớp với .mp4 thực tế. Chúng ta tính ra offset và cộng vào ra frame_idx_corrected.
Để tránh lỗi dùng nhầm cột gốc, hàm load_frame_map() sẽ đổi tên frame_idx_corrected
thành frame_idx, và frame_idx gốc thành frame_idx_raw.
Nếu dùng sai cột, frame lấy ra từ .mp4 sẽ bị lệch (có thể lên tới hàng chục frame).
"""
import pandas as pd
import sys
from pathlib import Path

_frame_map_cache = None
_warning_printed = False
ROOT_DIR = Path("/Users/hoangcongly/Desktop/AI-Challenge---AIC2026---475")

def load_frame_map(require_verified=False) -> pd.DataFrame:
    global _frame_map_cache, _warning_printed
    if _frame_map_cache is None:
        path = ROOT_DIR / "data/derived/frame_map.parquet"
        df = pd.read_parquet(path)
        # Đổi tên để bảo vệ người dùng
        df = df.rename(columns={
            "frame_idx": "frame_idx_raw",
            "frame_idx_corrected": "frame_idx"
        })
        _frame_map_cache = df
        
    df = _frame_map_cache.copy()
    
    if not _warning_printed:
        total = len(df['video_id'].unique())
        unverified = len(df[~df['offset_verified']]['video_id'].unique())
        if unverified > 0:
            print(f"CẢNH BÁO: {unverified}/{total} video chưa verify offset, đang dùng giả định 0. Kiểm cột offset_verified.", file=sys.stderr)
        _warning_printed = True
        
    if require_verified:
        df = df[df['offset_verified']]
        
    return df

def get_frame_idx(video_id: str, btc_kf_ordinal: int) -> int:
    df = load_frame_map()
    mask = (df['video_id'] == video_id) & (df['btc_kf_ordinal'] == btc_kf_ordinal)
    res = df[mask]
    if len(res) == 0:
        raise KeyError(f"Không tìm thấy video_id={video_id} và btc_kf_ordinal={btc_kf_ordinal}")
    return int(res.iloc[0]['frame_idx'])

def get_kf_id(video_id: str, btc_kf_ordinal: int) -> str:
    f_idx = get_frame_idx(video_id, btc_kf_ordinal)
    return f"{video_id}#f{f_idx:07d}"

def is_verified(video_id: str) -> bool:
    df = load_frame_map()
    mask = df['video_id'] == video_id
    res = df[mask]
    if len(res) == 0:
        return False
    return bool(res.iloc[0]['offset_verified'])

if __name__ == "__main__":
    df = load_frame_map()
    vids = df[(df['offset_verified']) & (df['frame_offset'] == 1)]['video_id'].unique()
    if len(vids) > 0:
        vid = vids[0]
        test_rows = df[df['video_id'] == vid].head(5)
        print(f"Test offset=+1 cho video {vid}:")
        for _, row in test_rows.iterrows():
            kf = row['btc_kf_ordinal']
            raw = row['frame_idx_raw']
            corr = get_frame_idx(vid, kf)
            print(f"kf_ordinal={kf}, raw={raw}, corrected={corr}, diff={corr - raw}")
            assert corr == raw + 1, f"LỖI: {corr} != {raw} + 1"
        print("Test OK!")
    else:
        print("Không có video nào thỏa mãn offset=+1 để test.")
