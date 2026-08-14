import sys
import time
from pathlib import Path
import pandas as pd

# Chặn av KHÔNG cho load để tránh đụng độ symbol với cv2
sys.modules["av"] = None

from shot_job import process_single_video, load_config

cfg = load_config()

vids = [
    ("L21_V015", "data/raw/videos/videos_L21_a/L21_V015.mp4", 30000, 1001, 38328),
    ("L22_V004", "data/raw/videos/videos_L22_a/L22_V004.mp4", 30000, 1001, 46152),
    ("L22_V015", "data/raw/videos/videos_L22_a/L22_V015.mp4", 30000, 1001, 42183),
    ("L22_V018", "data/raw/videos/videos_L22_a/L22_V018.mp4", 30000, 1001, 57793),
]

all_match = True
print("=== BẮT ĐẦU TEST OPENCV BACKEND ĐỂ CHỨNG MINH KẾT QUẢ GIỐNG PYAV 100% ===")

for vid, path, num, den, n_f in vids:
    print(f"\nĐang chạy {vid} bằng OPENCV...")
    t0 = time.time()
    
    df_cv, stats = process_single_video(
        video_id=vid,
        video_path=path,
        fps_num=num,
        fps_den=den,
        n_frames=n_f,
        cfg=cfg,
        output_dir=Path("tmp_cv_out"),
        write=False,
        backend="opencv"
    )
    t_elap = time.time() - t0
    speed = (n_f / (num/den)) / max(t_elap, 1e-6)
    print(f"Xong {vid} trong {t_elap:.1f}s (Tốc độ: {speed:.0f}x)")
    
    # Đọc bản backup của PyAV
    df_pyav = pd.read_parquet(f"data/derived/shots_parts_backup/{vid}.parquet")
    
    a = df_cv.drop(columns=["config_hash"], errors="ignore")
    b = df_pyav.drop(columns=["config_hash"], errors="ignore")
    
    if a.equals(b):
        print(f"✅ {vid}: MATCH 100% với PyAV!")
    else:
        print(f"❌ {vid}: LỆCH!")
        all_match = False
        print(a.compare(b).head())

if all_match:
    print("\n🎉 THÀNH CÔNG: OPENCV VÀ PYAV CHO RA KẾT QUẢ GIỐNG HỆT NHAU!")
    print("Bạn có thể an tâm đổi sang opencv để thoát khỏi vũng lầy 3x!")
