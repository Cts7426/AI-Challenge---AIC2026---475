"""
Module truy cập frame_map.parquet an toàn.

VÌ SAO CÓ 2 CỘT FRAME_IDX?
Do video BTC trích xuất keyframe bị lệch fps so với video mp4 gốc, frame_idx (gốc) không khớp với ảnh thực tế.
Chúng ta đã tính ra độ lệch (offset) và cộng vào tạo ra frame_idx_corrected.
Hàm load_frame_map() này sẽ đổi tên frame_idx_corrected thành 'frame_idx' để khi code, người dùng luôn lấy đúng frame.
Cột gốc được đổi tên thành 'frame_idx_raw'. Nếu cố tình dùng sai cột gốc, ảnh cắt ra sẽ bị lệch hàng chục frame.
"""

import sys
import pandas as pd
from pathlib import Path
from typing import Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT_DIR / "data"
DERIVED_DIR = DATA_DIR / "derived"

def get_video_path(video_id: str) -> Path:
    """
    Lấy đường dẫn TUYỆT ĐỐI tới file video dựa trên video_info.parquet.
    """
    info_path = DERIVED_DIR / "video_info.parquet"
    if not info_path.exists():
        raise FileNotFoundError("Không tìm thấy video_info.parquet")
    
    df = pd.read_parquet(info_path)
    row = df[df["video_id"] == video_id]
    if len(row) == 0:
        raise ValueError(f"Không tìm thấy video_id {video_id} trong video_info.parquet")
    
    rel_path = row.iloc[0]["path"]
    abs_path = (ROOT_DIR / rel_path).resolve()
    return abs_path

ROOT = Path(__file__).resolve().parents[2]

_frame_map_cache = None
_warning_printed = False

def load_frame_map(require_verified: bool = False) -> pd.DataFrame:
    """Tải và cache frame_map, đảm bảo luôn trả về cột frame_idx là đã corrected."""
    global _frame_map_cache, _warning_printed
    if _frame_map_cache is None:
        path = ROOT / "data/derived/frame_map.parquet"
        if not path.exists():
            raise FileNotFoundError(f"Không tìm thấy file: {path}")
            
        df = pd.read_parquet(path)

        # ⚠️ 19/08 — ĐÃ ĐỐI CHIẾU với bảng gốc `map-keyframes` của BTC và
        # QUYẾT ĐỊNH GIỮ NGUYÊN cột này. Lý do đầy đủ ở
        # scripts/audit/compare_frame_map_btc.py (đừng "sửa" lại lần nữa).
        #
        # Đổi tên để bảo vệ người dùng, tránh dùng nhầm cột bị lệch
        if "frame_idx_corrected" in df.columns:
            df = df.rename(columns={
                "frame_idx": "frame_idx_raw",
                "frame_idx_corrected": "frame_idx"
            })
            
        _frame_map_cache = df
        
    df = _frame_map_cache.copy()
    
    if not _warning_printed:
        total = 873
        if 'offset_verified' in df.columns:
            unverified = len(df[~df['offset_verified']]['video_id'].unique())
            if unverified > 0:
                print(f"CẢNH BÁO: {unverified}/{total} video chưa verify offset, đang dùng giả định offset=0.", file=sys.stderr)
        _warning_printed = True
        
    if require_verified and 'offset_verified' in df.columns:
        df = df[df['offset_verified']]
        
    return df

def get_frame_idx(video_id: str, btc_kf_ordinal: int) -> int:
    """Tra cứu frame index (đã cộng offset) của một keyframe. Ném KeyError nếu không có."""
    df = load_frame_map()
    mask = (df['video_id'] == video_id) & (df['btc_kf_ordinal'] == btc_kf_ordinal)
    res = df[mask]
    if len(res) == 0:
        raise KeyError(f"Không tìm thấy keyframe ordinal {btc_kf_ordinal} của video {video_id}")
    return int(res.iloc[0]['frame_idx'])

def get_kf_id(video_id: str, btc_kf_ordinal: int) -> str:
    """Tạo kf_id chuẩn (vd: L26_V022#k0121)"""
    return f"{video_id}#k{int(btc_kf_ordinal):04d}"

def parse_kf_id(kf_id: str) -> Tuple[str, int]:
    """Bóc tách kf_id thành video_id và btc_kf_ordinal. Vd: 'L26_V022#k0121' -> ('L26_V022', 121)"""
    parts = kf_id.split("#k")
    if len(parts) != 2:
        raise ValueError(f"Định dạng kf_id không hợp lệ: {kf_id}")
    return parts[0], int(parts[1])

def is_verified(video_id: str) -> bool:
    """Kiểm tra xem video này đã được kiểm định (verify) offset chưa."""
    df = load_frame_map()
    if 'offset_verified' not in df.columns:
        return False
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
        success_count = 0
        for _, row in test_rows.iterrows():
            kf = row['btc_kf_ordinal']
            raw = row['frame_idx_raw']
            corr = get_frame_idx(vid, kf)
            print(f"kf_ordinal={kf}, raw={raw}, corrected={corr}, diff={corr - raw}")
            assert corr == raw + 1, f"LỖI: {corr} != {raw} + 1"
            
            # Kèm test parse_kf_id và get_kf_id
            real_kf_id = row['kf_id']
            gen_kf_id = get_kf_id(vid, kf)
            assert real_kf_id == gen_kf_id, f"LỖI kf_id: {real_kf_id} != {gen_kf_id}"
            
            v, ord_val = parse_kf_id(real_kf_id)
            assert v == vid and ord_val == kf, f"LỖI bóc tách kf_id: {v}, {ord_val}"
            
            success_count += 1
            
        print(f"Test OK! Đã tra cứu chính xác {success_count} keyframe.")
        
        # Test 100 ngẫu nhiên để đảm bảo tính nhất quán
        print("\nTest 100 dòng ngẫu nhiên:")
        test_random = df.sample(min(100, len(df)), random_state=42)
        match_count = 0
        for _, row in test_random.iterrows():
            r_vid = row['video_id']
            r_ord = row['btc_kf_ordinal']
            r_kf_id = row['kf_id']
            
            gen_id = get_kf_id(r_vid, r_ord)
            assert gen_id == r_kf_id, f"Lỗi kf_id: {gen_id} != {r_kf_id}"
            
            p_vid, p_ord = parse_kf_id(r_kf_id)
            assert p_vid == r_vid and p_ord == r_ord, f"Lỗi bóc tách: {p_vid}, {p_ord}"
            match_count += 1
        print(f"Test ngẫu nhiên OK: {match_count}/{len(test_random)} khớp.")
    else:
        print("Không có video nào thỏa mãn offset=+1 để test.")
