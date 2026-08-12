import json
from pathlib import Path
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "derived"

def generate_meta_jsons():
    print("==================================================")
    print("TỰ ĐỘNG TẠO FILE METADATA .meta.json CHO CÁC PARQUET")
    print("==================================================")
    
    parquet_files = list(DATA_DIR.glob("*.parquet"))
    for pf in parquet_files:
        try:
            df = pd.read_parquet(pf)
            meta = {
                "file_name": pf.name,
                "row_count": len(df),
                "columns": list(df.columns),
                "dtypes": {col: str(dt) for col, dt in zip(df.columns, df.dtypes)}
            }
            meta_path = pf.with_suffix(".parquet.meta.json")
            meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"  - Đã tạo: {meta_path.name} ({len(df):,} rows, {len(df.columns)} cols)")
        except Exception as e:
            print(f"❌ Lỗi khi tạo meta cho {pf.name}: {e}")

if __name__ == "__main__":
    generate_meta_jsons()
