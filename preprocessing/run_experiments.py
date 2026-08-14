import subprocess
import time
import pandas as pd
from pathlib import Path
import os
import glob

# Video dùng để test nghiệm (trộn lẫn video dài và ngắn)
TEST_VIDS = ["L22_V016", "L22_V012", "L22_V013", "L22_V015", "L22_V006", "L22_V004"]
CMD_BASE = ["python", "preprocessing/shot_job.py", "--video-ids"] + TEST_VIDS

# Cấu hình thử nghiệm
configs = [
    # So sánh Backend & Threading (ở downscale chuẩn = 2)
    {"workers": 1, "backend": "opencv", "downscale": 2},
    {"workers": 1, "backend": "pyav", "downscale": 2},
    {"workers": 4, "backend": "opencv", "downscale": 2},
    {"workers": 6, "backend": "opencv", "downscale": 2},
    {"workers": 8, "backend": "opencv", "downscale": 2},
    {"workers": 6, "backend": "pyav", "downscale": 2},
    
    # So sánh Downscale (lấy cấu hình có khả năng nhất là 6/opencv hoặc 6/pyav làm base)
    {"workers": 6, "backend": "opencv", "downscale": 3},
    {"workers": 6, "backend": "opencv", "downscale": 4},
]

def get_total_shots():
    # Đếm tổng số lượng shot được lưu trong các file parquet test
    files = glob.glob("data/derived/shots_parts/*.parquet")
    if not files: return 0
    total = 0
    for f in files:
        df = pd.read_parquet(f)
        total += len(df)
    return total

def run_experiment():
    results = []
    
    print("🚀 BẮT ĐẦU CHẠY THÍ NGHIỆM THEO MA TRẬN...\n")
    
    for idx, cfg in enumerate(configs, 1):
        # 1. Dọn dẹp rác
        for f in glob.glob("data/derived/shots_parts/*.parquet"):
            os.remove(f)
            
        print(f"[{idx}/{len(configs)}] Test: Workers={cfg['workers']} | Backend={cfg['backend']} | Downscale={cfg['downscale']}")
        
        cmd = CMD_BASE + [
            "--workers", str(cfg["workers"]),
            "--backend", cfg["backend"],
            "--downscale", str(cfg["downscale"])
        ]
        
        t0 = time.time()
        # Chạy ẩn, chỉ chờ kết quả
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            elapsed = time.time() - t0
            
            shots = get_total_shots()
            
            results.append({
                "Cấu hình": f"{cfg['workers']} luồng | {cfg['backend']}",
                "Downscale": cfg['downscale'],
                "Thời gian (s)": round(elapsed, 1),
                "Số shot": shots
            })
            print(f"   ➜ Xong trong {elapsed:.1f}s | Số shot: {shots}")
        except subprocess.CalledProcessError as e:
            print(f"   ➜ LỖI khi chạy cấu hình này!")
            
    # In Bảng Kết Quả
    df = pd.DataFrame(results)
    
    # Tính chênh lệch shot so với chuẩn (Downscale 2, lấy dòng đầu tiên làm chuẩn)
    if not df.empty:
        base_shots = df[df["Downscale"] == 2]["Số shot"].max()
        df["Sai số (%)"] = ((df["Số shot"] - base_shots) / base_shots * 100).round(2)
        df["Sai số (%)"] = df["Sai số (%)"].apply(lambda x: f"{x:+.2f}%" if pd.notna(x) else "")
        
    print("\n" + "="*60)
    print(" KẾT QUẢ ĐO ĐẠC (ĐO, ĐỪNG ĐOÁN)")
    print("="*60)
    print(df.to_markdown(index=False))
    print("="*60)

if __name__ == "__main__":
    run_experiment()
