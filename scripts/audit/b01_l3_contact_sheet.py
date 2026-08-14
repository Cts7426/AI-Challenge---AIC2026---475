import os
import cv2
import pandas as pd
import numpy as np
from pathlib import Path
import random

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT_DIR / "data"
FRAME_MAP_PATH = DATA_DIR / "derived/frame_map.parquet"
VIDEOS_DIR = DATA_DIR / "raw/videos/video"  # Dựa theo thư mục thực tế nãy bung nén
BTC_KF_DIR = DATA_DIR / "raw/btc/keyframes"
OUT_DIR = DATA_DIR / "derived/_audit/l3_sheets"

def draw_text(img, text, pos, color=(0, 255, 0), font_scale=1.0, thickness=2):
    cv2.putText(img, text, pos, cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 0, 0), thickness+1, cv2.LINE_AA)
    cv2.putText(img, text, pos, cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, thickness, cv2.LINE_AA)

def generate_contact_sheet(vid, kf_id, frame_idx, out_path):
    mp4_path = VIDEOS_DIR / f"{vid}.mp4"
    if not mp4_path.exists():
        print(f"⚠️ Không tìm thấy {mp4_path}")
        return False
        
    vid_dirs = list(BTC_KF_DIR.rglob(vid))
    if not vid_dirs:
        print(f"⚠️ Không tìm thấy thư mục ảnh gốc cho {vid}")
        return False
    vid_dir = vid_dirs[0]
    
    import re
    m = re.search(r'\d+$', kf_id)
    if not m:
        print(f"⚠️ Lỗi: Không thể trích xuất số frame từ kf_id: {kf_id}")
        return False
        
    num = int(m.group())
    btc_path = None
    for pad in [3, 4, 1, 2]:
        cand = vid_dir / f"{str(num).zfill(pad)}.jpg"
        if cand.exists():
            btc_path = cand
            break
            
    if not btc_path:
        print(f"⚠️ Không tìm thấy ảnh tương ứng num={num} trong {vid_dir}")
        return False
        
    btc_img = cv2.imread(str(btc_path))
    if btc_img is None:
        print(f"⚠️ Không đọc được ảnh BTC {btc_path}")
        return False
        
    # Chuẩn hoá kích thước
    W, H = 320, 180
    btc_img = cv2.resize(btc_img, (W, H))
    
    cap = cv2.VideoCapture(str(mp4_path))
    if not cap.isOpened():
        return False
        
    # Tạo canvas ngang (7 khung hình) x 2 hàng
    canvas = np.zeros((H * 2 + 100, W * 7, 3), dtype=np.uint8)
    
    # Tiêu đề
    draw_text(canvas, f"L3 AUDIT - Video: {vid} | BTC Keyframe: {kf_id} | Mapped frame_idx: {frame_idx}", (20, 40), (255, 255, 255), 1.5, 3)
    
    start_idx = frame_idx - 3
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, start_idx))
    
    for offset in range(-3, 4):
        ret, frame = cap.read()
        col = offset + 3
        if ret:
            frame = cv2.resize(frame, (W, H))
            
            # Ghi chú lên khung hình
            color = (0, 255, 0) if offset == 0 else (200, 200, 200)
            text = f"idx{'+' if offset > 0 else ''}{offset}"
            draw_text(frame, text, (10, 30), color, 1.0, 2)
            
            x_pos = col * W
            y_pos = 80
            canvas[y_pos:y_pos+H, x_pos:x_pos+W] = frame
            
            # Nếu là khung hình chính giữa, dán ảnh BTC ngay bên dưới để đối chiếu
            if offset == 0:
                y_pos_btc = y_pos + H + 10
                canvas[y_pos_btc:y_pos_btc+H, x_pos:x_pos+W] = btc_img
                draw_text(canvas, "BTC ORIGINAL", (x_pos + 10, y_pos_btc + 30), (0, 255, 255), 1.0, 2)
                
    cap.release()
    cv2.imwrite(str(out_path), canvas)
    return True

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    
    df_map = pd.read_parquet(FRAME_MAP_PATH)
    
    # Lọc ra các video L21 mà ta đang giữ file mp4
    l21_videos = [f"L21_V{str(i).zfill(3)}" for i in range(1, 21)]
    df_l21 = df_map[df_map["video_id"].isin(l21_videos)]
    
    # Chọn ngẫu nhiên 20 keyframe (Cố định seed để trung thực)
    random.seed(42)
    # Lấy 20 dòng ngẫu nhiên từ df_l21
    sample_df = df_l21.sample(n=20, random_state=42)
    
    success = 0
    print(f"Đang sinh 20 tấm Contact Sheet cho Audit L3...")
    for idx, row in sample_df.iterrows():
        vid = row["video_id"]
        kf_id = row["kf_id"]
        frame_idx = row["frame_idx"]
        
        out_path = OUT_DIR / f"{vid}_{kf_id}_sheet.jpg"
        if generate_contact_sheet(vid, kf_id, frame_idx, out_path):
            success += 1
            print(f"✅ Đã tạo Contact Sheet: {out_path.name}")
            
    print(f"\n🎉 Hoàn thành xuất {success}/20 tấm Contact Sheet.")

if __name__ == "__main__":
    main()
