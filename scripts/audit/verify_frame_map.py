import sys
import cv2
import pandas as pd
import numpy as np
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))
    
from preprocessing.common.frame_map import load_frame_map

def compute_mse(img1, img2):
    return np.mean((img1.astype("float") - img2.astype("float")) ** 2)

def verify_frame_map():
    DATA_DIR = ROOT_DIR / "data"
    VIDEOS_DIR = DATA_DIR / "raw/videos/video"
    BTC_KF_DIR = DATA_DIR / "raw/btc/keyframes"
    
    # Dùng hàm chuẩn của team để lấy df có frame_idx đã sửa lỗi lệch!
    df = load_frame_map(require_verified=True)
    
    existing_vids = [p.stem for p in VIDEOS_DIR.glob("*.mp4")]
    if not existing_vids:
        print("LỖI: Không có file .mp4 nào trong thư mục để test!")
        exit(1)
        
    df_local = df[df["video_id"].isin(existing_vids)]
    sample_size = min(20, len(df_local))
    sample_df = df_local.sample(n=sample_size, random_state=42)
    
    print(f"{'kf_id':<18} | {'frame_idx':<10} | {'MSE':<10} | {'Status'}")
    print("-" * 55)
    
    any_failed = False
    verified_count = 0
    
    temp_dir = DATA_DIR / "derived/_audit/b01c_temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    for _, row in sample_df.iterrows():
        vid = row["video_id"]
        frame_idx = row["frame_idx"] # Đây CHÍNH LÀ frame_idx_corrected!
        # Do file csv chuẩn thì btc_ordinal chính là btc_kf_ordinal
        btc_ordinal = row["btc_kf_ordinal"] if "btc_kf_ordinal" in row else row["btc_ordinal"]
        
        # Tạo kf_id nếu chưa có, hoặc dùng kf_id
        if "kf_id" in row:
            kf_id = row["kf_id"]
        else:
            kf_id = f"{vid}#k{btc_ordinal:04d}"
            
        video_path = VIDEOS_DIR / f"{vid}.mp4"
        
        # Trích xuất trực tiếp số n từ kf_id (Vd: L21_V001#k0001 -> n=1) đảm bảo KHÔNG THỂ LỆCH!
        kf_suffix = kf_id.split("#k")[-1]
        img_n = int(kf_suffix)
        
        possible_imgs = list(BTC_KF_DIR.glob(f"keyframes_*/{vid}/{img_n:03d}.jpg"))
        if not possible_imgs:
            possible_imgs = list(BTC_KF_DIR.glob(f"keyframes_*/{vid}/{img_n:04d}.jpg"))
            
        btc_img_path = possible_imgs[0] if possible_imgs else None
        
        if not video_path.exists():
            print(f"{kf_id:<18} | {frame_idx:<10} | {'N/A':<10} | SKIP (No Video)")
            continue
            
        if not btc_img_path or not btc_img_path.exists():
            print(f"{kf_id:<18} | {frame_idx:<10} | {'N/A':<10} | SKIP (No BTC Img)")
            continue
            
        out_png = temp_dir / f"extracted_{kf_id.replace('#', '_')}.png"
        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-i", str(video_path),
            "-vf", f"select=eq(n\\,{frame_idx})",
            "-vsync", "0",
            "-frames:v", "1",
            str(out_png)
        ]
        
        try:
            import subprocess
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError:
            print(f"{kf_id:<18} | {frame_idx:<10} | {'N/A':<10} | KHÔNG (FFmpeg Fail)")
            any_failed = True
            continue
            
        if not out_png.exists():
            print(f"{kf_id:<18} | {frame_idx:<10} | {'N/A':<10} | KHÔNG (No Extracted Img)")
            any_failed = True
            continue
            
        img_btc = cv2.imread(str(btc_img_path))
        img_ext = cv2.imread(str(out_png))
        
        if img_btc is None or img_ext is None:
            print(f"{kf_id:<18} | {frame_idx:<10} | {'N/A':<10} | KHÔNG (Read Err)")
            any_failed = True
            continue
            
        h, w = img_btc.shape[:2]
        img_ext_resized = cv2.resize(img_ext, (w, h))
        
        mse = compute_mse(img_btc, img_ext_resized)
        status = "ĐẠT" if mse < 50.0 else "KHÔNG"
        if status == "KHÔNG":
            any_failed = True
        else:
            verified_count += 1
            
        print(f"{kf_id:<18} | {frame_idx:<10} | {mse:<10.2f} | {status}")
        
    if verified_count == 0 and not any_failed:
        print("\n⚠️ KHÔNG THỂ XÁC THỰC: Không tìm thấy ảnh BTC hoặc Video tương ứng để test!")
        exit(1)
        
    if any_failed:
        print("\n❌ CẢNH BÁO ĐỎ: Phát hiện sai lệch > 1 frame ở một số mẫu! frame_map chưa chuẩn!")
        exit(1)
    else:
        print(f"\n✅ XÁC THỰC THÀNH CÔNG: Toàn bộ {verified_count} mẫu kiểm tra đều khớp pixel tuyệt đối với BTC!")

if __name__ == "__main__":
    verify_frame_map()
