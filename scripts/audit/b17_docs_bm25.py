import os
import sys
from pathlib import Path
import pandas as pd
import argparse

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

DATA_DIR = ROOT_DIR / "data"
DERIVED_DIR = DATA_DIR / "derived"
DOCS_FILE = DERIVED_DIR / "docs_bm25.parquet"
KF_FILE = DERIVED_DIR / "keyframes.parquet"

def b17_docs_audit(query=None):
    print("\n" + "="*50)
    print("NGHIỆM THU B1.7: TẠO DOCUMENTS BM25")
    print("="*50)
    
    # 1. Load Data
    try:
        df_docs = pd.read_parquet(DOCS_FILE)
        df_kf = pd.read_parquet(KF_FILE)
    except Exception as e:
        print(f"❌ FAIL: Không thể load dữ liệu: {e}")
        return False
        
    print(f"Tổng số Documents: {len(df_docs):,}")
    
    # L1: Khớp số lượng keyframes
    if len(df_docs) != len(df_kf):
        print(f"❌ FAIL L1: Số lượng documents ({len(df_docs)}) KHÔNG KHỚP với keyframes ({len(df_kf)})!")
    else:
        print("✅ PASS L1: Đảm bảo 100% keyframes đều có document text.")
        
    # L2: Mẫu ngẫu nhiên
    if not query:
        print("\n--- KIỂM TRA L2: CẤU TRÚC DOC_TEXT ---")
        sample_df = df_docs.sample(n=5, random_state=42)
        for _, row in sample_df.iterrows():
            print(f"\n[{row.kf_id}] (Video: {row.video_id}, Frame: {row.frame_idx})")
            print("-" * 50)
            print(row.doc_text)
            print("-" * 50)
    
    # L3: Tìm kiếm theo Keyword
    if query:
        print(f"\n--- KIỂM TRA L3: TÌM KIẾM TỪ KHOÁ '{query}' ---")
        query = query.lower()
        # Tìm các dòng có chứa query
        matches = df_docs[df_docs['doc_text'].str.contains(query, na=False)]
        
        if len(matches) == 0:
            print(f"❌ FAIL L3: Không tìm thấy bất kỳ frame nào chứa từ khóa '{query}'.")
        else:
            print(f"✅ PASS L3: Đã tìm thấy {len(matches)} frames chứa từ khóa '{query}'!")
            # In ra top 5
            for _, row in matches.head(5).iterrows():
                print(f"\n[{row.kf_id}] (Frame: {row.frame_idx})")
                print(row.doc_text.replace(query, f">>> {query.upper()} <<<"))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", type=str, help="Từ khoá hiếm để test nghiệm thu L3", default="")
    args = parser.parse_args()
    
    b17_docs_audit(args.query if args.query else None)
