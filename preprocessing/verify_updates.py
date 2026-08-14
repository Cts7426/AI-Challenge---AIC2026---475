import sys
import shutil
import subprocess
import pandas as pd
from pathlib import Path
import time
import os

ROOT = Path("data/derived/shots_parts")
BACKUP = Path("data/derived/shots_parts_backup")

# Các file cần backup
vids = ["L21_V015", "L22_V004", "L22_V015", "L22_V018"]
files = [f"{v}.parquet" for v in vids]

def step_3_4():
    print("=== BƯỚC 3 & 4: SAO LƯU VÀ CHẠY LẠI ===")
    BACKUP.mkdir(exist_ok=True)
    for f in files:
        src = ROOT / f
        if src.exists():
            shutil.copy(src, BACKUP / f)
            src.unlink()
            print(f"Đã sao lưu và xóa: {f}")
        else:
            print(f"⚠️ KHÔNG TÌM THẤY {f} trong {ROOT}! Có thể bạn chưa chạy hoặc đã xóa.")
            
    # Chạy lại
    print("\nĐang chạy lại 4 video bằng cấu hình mới (7 workers, pyav, none threading)...")
    cmd = [
        "/opt/anaconda3/bin/python", "preprocessing/shot_job.py", 
        "--workers", "7", "--backend", "pyav", "--video-ids"
    ] + vids
    
    t0 = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True)
    t_elapsed = time.time() - t0
    
    # Kiểm tra log xem còn objc warning không
    if "Class AVFFrameReceiver is implemented in both" in proc.stderr:
        print("❌ CẢNH BÁO OBJC VẪN CÒN XUẤT HIỆN TRONG LOG!")
    else:
        print("✅ CẢNH BÁO OBJC ĐÃ HOÀN TOÀN BIẾN MẤT!")
        
    print(f"Thời gian chạy 4 video: {t_elapsed:.1f}s")
    return proc.stdout

def step_5():
    print("\n=== BƯỚC 5: SO SÁNH PANDAS ===")
    all_match = True
    for f in files:
        old_path = BACKUP / f
        new_path = ROOT / f
        if not old_path.exists() or not new_path.exists():
            print(f"Bỏ qua {f} vì thiếu file old/new.")
            continue
            
        a = pd.read_parquet(old_path)
        b = pd.read_parquet(new_path)
        
        # Bỏ config_hash
        a_clean = a.drop(columns=['config_hash'], errors='ignore')
        b_clean = b.drop(columns=['config_hash'], errors='ignore')
        
        match = a_clean.equals(b_clean)
        print(f"So sánh {f}: {'✅ TRUE' if match else '❌ FALSE'}")
        
        if not match:
            all_match = False
            print(f"  -> Lệch dữ liệu ở file {f}!")
            # Tìm dòng lệch
            diff = a_clean.compare(b_clean)
            print("  Chi tiết lệch:\n", diff.head())
            
    if all_match:
        print("\n🎉 XÁC NHẬN: Dữ liệu hoàn toàn khớp (True cả 4)!")
    return all_match

if __name__ == "__main__":
    out = step_3_4()
    step_5()
    print("\n=== BƯỚC 7: LOG TỐC ĐỘ ===")
    for line in out.splitlines():
        if "raw=" in line or "Tổng thời lượng" in line:
            print(line)
