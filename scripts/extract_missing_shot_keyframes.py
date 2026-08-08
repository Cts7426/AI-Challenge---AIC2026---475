import os
import sys
from pathlib import Path
import pandas as pd
import numpy as np
from PIL import Image
from tqdm import tqdm

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
DERIVED_DIR = DATA_DIR / "derived"
RAW_BTC_KF_DIR = DATA_DIR / "raw" / "btc" / "keyframes"
KEYFRAMES_OUT_DIR = DERIVED_DIR / "keyframes"

def build_btc_file_index():
    print("Pre-indexing BTC keyframe files...")
    file_map = {}
    for p in RAW_BTC_KF_DIR.rglob("*.jpg"):
        vid = p.parent.name
        try:
            ord_idx = int(p.stem)
            file_map[(vid, ord_idx)] = p
        except ValueError:
            pass
    print(f"Indexed {len(file_map):,} BTC keyframe files.")
    return file_map

def resize_and_save(img_path: Path, out_path: Path, max_edge: int = 448, quality: int = 90):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.open(img_path).convert("RGB")
    w, h = img.size
    if max(w, h) > max_edge:
        if w > h:
            new_w = max_edge
            new_h = int(h * max_edge / w)
        else:
            new_h = max_edge
            new_w = int(w * max_edge / h)
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    img.save(out_path, format="JPEG", quality=quality)

def main():
    print("==================================================")
    print("BẮT ĐẦU TRÍCH XUẤT KEYFRAME TÂM CHO CÁC SHOTS THIẾU")
    print("==================================================")
    
    df_shots = pd.read_parquet(DERIVED_DIR / "shots.parquet")
    df_kf = pd.read_parquet(DERIVED_DIR / "keyframes.parquet")
    df_fm = pd.read_parquet(DERIVED_DIR / "frame_map.parquet")
    
    # Tìm các shot chưa có keyframe nào trong keyframes.parquet
    kf_shot_ids = set(df_kf["shot_id"])
    all_shots = df_shots["shot_id"].values
    missing_shots_mask = ~df_shots["shot_id"].isin(kf_shot_ids)
    df_missing_shots = df_shots[missing_shots_mask]
    
    print(f"Tổng số shot trong shots.parquet: {len(df_shots):,}")
    print(f"Số shot ĐÃ CÓ keyframe:          {len(kf_shot_ids):,}")
    print(f"Số shot CHƯA CÓ keyframe:        {len(df_missing_shots):,}")
    
    if df_missing_shots.empty:
        print("✅ 100% Shots đã có keyframe!")
        return

    file_map = build_btc_file_index()
    fm_gb = df_fm.groupby("video_id")
    
    new_kf_list = []
    
    for row in tqdm(df_missing_shots.itertuples(), total=len(df_missing_shots), desc="Trích xuất Keyframe Tâm Shot"):
        vid = row.video_id
        shot_id = row.shot_id
        start_f = row.start_frame
        end_f = row.end_frame
        
        mid_frame = (start_f + end_f) // 2
        
        # Dùng frame_map để tìm BTC ordinal gần mid_frame nhất
        if vid in fm_gb.groups:
            df_fm_vid = fm_gb.get_group(vid)
            idx = np.argmin(np.abs(df_fm_vid["frame_idx"].values - mid_frame))
            closest_row = df_fm_vid.iloc[idx]
            btc_ord = closest_row["btc_ordinal"]
            actual_f = closest_row["frame_idx"]
        else:
            btc_ord = 1
            actual_f = mid_frame
            
        btc_img_path = file_map.get((vid, btc_ord))
        if btc_img_path and btc_img_path.exists():
            img_filename = f"f{actual_f:07d}.jpg"
            out_path = KEYFRAMES_OUT_DIR / vid / img_filename
            if not out_path.exists():
                resize_and_save(btc_img_path, out_path)
                
            kf_id = f"{vid}_{actual_f:07d}"
            rel_path = f"keyframes/{vid}/{img_filename}"
            new_kf_list.append({
                "kf_id": kf_id,
                "video_id": vid,
                "shot_id": shot_id,
                "frame_idx": actual_f,
                "path": rel_path
            })

    print(f"\n✅ Đã trích xuất thêm {len(new_kf_list):,} ảnh keyframe tâm shot mới.")
    
    # 2. Hợp nhất vào keyframes.parquet và re-index row_id
    if new_kf_list:
        df_new_kf = pd.DataFrame(new_kf_list)
        df_combined_kf = pd.concat([df_kf.drop(columns=["row_id"], errors="ignore"), df_new_kf], ignore_index=True)
        # Drop trùng lặp kf_id nếu có
        df_combined_kf = df_combined_kf.drop_duplicates(subset=["kf_id"]).sort_values(["video_id", "frame_idx"]).reset_index(drop=True)
        df_combined_kf["row_id"] = df_combined_kf.index
        
        schema = {
            "kf_id": "string",
            "video_id": "string",
            "shot_id": "string",
            "frame_idx": "int64",
            "path": "string",
            "row_id": "int64"
        }
        df_combined_kf = df_combined_kf.astype(schema)
        out_kf_path = DERIVED_DIR / "keyframes.parquet"
        df_combined_kf.to_parquet(out_kf_path, index=False)
        print(f"🎯 Đã cập nhật keyframes.parquet mới: {len(df_combined_kf):,} rows!")

        # Refresh df_kf reference
        df_kf = df_combined_kf

    # 3. Cập nhật rep_kf_id cho shots.parquet để xóa 100% NULL
    print("\n3. Cập nhật rep_kf_id cho shots.parquet...")
    kf_by_shot = df_kf.groupby("shot_id")["kf_id"].first().to_dict()
    
    rep_kf_ids = []
    rep_sources = []
    
    for row in df_shots.itertuples():
        shot_id = row.shot_id
        current_rep = row.rep_kf_id
        
        if pd.notna(current_rep) and str(current_rep).strip():
            rep_kf_ids.append(current_rep)
            rep_sources.append(getattr(row, "rep_source", "btc"))
        elif shot_id in kf_by_shot:
            rep_kf_ids.append(kf_by_shot[shot_id])
            rep_sources.append("exact_shot_center")
        else:
            # Fallback nếu vẫn rỗng: lấy keyframe đầu tiên của video đó
            vid = row.video_id
            vid_kfs = df_kf[df_kf["video_id"] == vid]
            if not vid_kfs.empty:
                rep_kf_ids.append(vid_kfs["kf_id"].iloc[0])
                rep_sources.append("video_fallback")
            else:
                rep_kf_ids.append(None)
                rep_sources.append("none")
                
    df_shots["rep_kf_id"] = rep_kf_ids
    df_shots["rep_source"] = rep_sources
    
    out_shots_path = DERIVED_DIR / "shots.parquet"
    df_shots.to_parquet(out_shots_path, index=False)
    print(f"🎯 Đã cập nhật shots.parquet: NULL rep_kf_id còn lại = {df_shots['rep_kf_id'].isna().sum()}")

if __name__ == "__main__":
    main()
