import sys
from pathlib import Path
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT_DIR / "data"
DERIVED_DIR = DATA_DIR / "derived"

def load_frame_map(require_verified: bool = False) -> pd.DataFrame:
    """
    Tải file data/derived/frame_map.parquet an toàn.
    - Cảnh báo ra stderr nếu có video chưa verify offset.
    - Lọc bỏ video chưa verify nếu require_verified=True.
    """
    map_path = DERIVED_DIR / "frame_map.parquet"
    if not map_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file: {map_path}")
        
    df = pd.read_parquet(map_path)
    
    # Kiểm tra các cột bắt buộc
    required_cols = ["frame_idx", "frame_idx_corrected", "offset_verified"]
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"File frame_map.parquet thiếu cột bắt buộc: {col}")
            
    # Đếm số lượng video chưa verify
    n_total_vids = df["video_id"].nunique()
    unverified_vids = df[~df["offset_verified"]]["video_id"].nunique()
    
    if unverified_vids > 0:
        print(f"[CẢNH BÁO - FRAME_MAP] {unverified_vids}/{n_total_vids} video CHƯA VERIFY OFFSET, đang dùng giả định offset=0.", file=sys.stderr)
        
    if require_verified:
        df = df[df["offset_verified"]].reset_index(drop=True)
        print(f"Đã lọc bỏ {unverified_vids} video chưa verify. Số lượng còn lại: {df['video_id'].nunique()} video.", file=sys.stderr)
        
    return df
