import os
import sys
from pathlib import Path
import pandas as pd
import numpy as np

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

DATA_DIR = ROOT_DIR / "data"
DERIVED_DIR = DATA_DIR / "derived"
OCR_FILE = DERIVED_DIR / "ocr.parquet"

def b14_ocr_audit():
    print("\n" + "="*50)
    print("NGHIỆM THU B1.4: TRÍCH XUẤT OCR")
    print("="*50)
    
    # 1. Load Data
    try:
        df_ocr = pd.read_parquet(OCR_FILE)
    except Exception as e:
        print(f"❌ FAIL: Không thể load dữ liệu: {e}")
        return False
        
    print(f"Tổng số Dòng Text (OCR): {len(df_ocr):,}")
    
    # L1-1: Cấu trúc cột & Null check
    # Có thể là kf_id hoặc rep_kf_id
    fk_col = "kf_id" if "kf_id" in df_ocr.columns else "rep_kf_id"
    req_cols = {fk_col, "text_raw", "text_clean"}
    missing = req_cols - set(df_ocr.columns)
    if missing:
        print(f"❌ FAIL L1-1a: Thiếu các cột bắt buộc: {missing}")
    else:
        print("✅ PASS L1-1a: Cấu trúc cột hợp lệ.")
        
        # Check Null
        null_raw = df_ocr["text_raw"].isnull().sum()
        null_clean = df_ocr["text_clean"].isnull().sum()
        
        if null_raw > 0 or null_clean > 0:
            print(f"❌ FAIL L1-1b: Có {null_raw} dòng text_raw và {null_clean} dòng text_clean bị NULL!")
        else:
            print("✅ PASS L1-1b: 100% dòng dữ liệu text_raw và text_clean đều có giá trị.")

    # L3: Khảo sát mẫu
    print("\n--- KIỂM TRA L3: THẨM ĐỊNH MẮT NGƯỜI (VISUAL VERIFICATION) ---")
    try:
        sample_df = df_ocr.sample(n=30, random_state=42)
        print("Mẫu 30 dòng OCR để Đội trưởng kiểm tra chất lượng sửa dấu của LLM:\n")
        
        print(f"{'KHÓA (kf_id)':<20} | {'TEXT_RAW (Gốc)':<40} | {'TEXT_CLEAN (LLM Sửa)':<40}")
        print("-" * 105)
        for _, row in sample_df.iterrows():
            raw = str(row['text_raw']).replace('\n', ' ')[:37] + ("..." if len(str(row['text_raw'])) > 37 else "")
            clean = str(row['text_clean']).replace('\n', ' ')[:37] + ("..." if len(str(row['text_clean'])) > 37 else "")
            print(f"{row[fk_col]:<20} | {raw:<40} | {clean:<40}")
            
        print("\n✅ Đã xuất 30 mẫu. Đội trưởng vui lòng kiểm tra xem text_clean có giữ nguyên được tên riêng, và đọc đúng >= 80% không nhé!")
    except Exception as e:
        print(f"⚠️ Không thể chạy test L3: {e}")

if __name__ == "__main__":
    b14_ocr_audit()
