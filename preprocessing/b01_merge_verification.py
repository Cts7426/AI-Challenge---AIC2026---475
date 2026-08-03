import pandas as pd
from pathlib import Path
import sys

DATA_DIR = Path("data")
DERIVED_DIR = DATA_DIR / "derived"
PARTS_DIR = DERIVED_DIR / "full_verification_parts"
OUT_PATH = DERIVED_DIR / "full_verification.parquet"

def main():
    part_files = list(PARTS_DIR.glob("*.parquet"))
    if not part_files:
        print("No part files found to merge.")
        sys.exit(1)
        
    print(f"Found {len(part_files)} part files. Merging...")
    
    dfs = []
    for f in part_files:
        df = pd.read_parquet(f)
        dfs.append(df)
        
    df_res = pd.concat(dfs, ignore_index=True)
    df_res.to_parquet(OUT_PATH, index=False)
    print(f"Merged successfully into {OUT_PATH}. Total rows: {len(df_res)}")

if __name__ == "__main__":
    main()
