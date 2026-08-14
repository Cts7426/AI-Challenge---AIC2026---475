import os
import sys
import json
from pathlib import Path
import pandas as pd
import numpy as np
from tqdm import tqdm

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

DATA_DIR = ROOT_DIR / "data"
DERIVED_DIR = DATA_DIR / "derived"
RAW_META_DIR = DATA_DIR / "raw" / "btc" / "metadata" / "media-info"

def run_bm25_job():
    print("1. Loading Parquet files...")
    try:
        df_kf = pd.read_parquet(DERIVED_DIR / "keyframes.parquet")
        df_info = pd.read_parquet(DERIVED_DIR / "video_info.parquet")
    except Exception as e:
        print(f"❌ FAIL: {e}")
        return
    
    # --- METADATA ---
    print("2. Parsing Metadata JSONs...")
    meta_dict = {}
    if RAW_META_DIR.exists():
        for f in RAW_META_DIR.glob("*.json"):
            vid = f.stem
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                title = data.get("title", "")
                desc = data.get("description", "")
                meta_dict[vid] = {"title": title, "desc": desc}
            except Exception:
                pass
    else:
        print(f"⚠️ WARNING: Không tìm thấy thư mục {RAW_META_DIR}")
    
    df_meta = pd.DataFrame.from_dict(meta_dict, orient='index').reset_index()
    if not df_meta.empty:
        df_meta.columns = ["video_id", "meta_title", "meta_desc"]
        df_kf = df_kf.merge(df_meta, on="video_id", how="left")
    else:
        df_kf["meta_title"] = ""
        df_kf["meta_desc"] = ""
        
    df_kf["meta_title"] = df_kf["meta_title"].fillna("")
    df_kf["meta_desc"] = df_kf["meta_desc"].fillna("")

    # --- OCR ---
    print("3. Merging OCR...")
    try:
        df_ocr = pd.read_parquet(DERIVED_DIR / "ocr.parquet")
        df_shots = pd.read_parquet(DERIVED_DIR / "shots.parquet")
        
        # Sắp xếp và chuyển đổi kiểu dữ liệu để merge_asof không lỗi
        df_ocr["video_id"] = df_ocr["video_id"].astype(str)
        df_shots["video_id"] = df_shots["video_id"].astype(str)
        
        df_ocr = df_ocr.sort_values("frame_idx")
        df_shots = df_shots.sort_values("start_frame")
        
        # Map mỗi OCR vào shot_id gần nhất của video_id đó
        df_ocr_mapped = pd.merge_asof(
            df_ocr, 
            df_shots[["video_id", "shot_id", "start_frame"]], 
            left_on="frame_idx", 
            right_on="start_frame", 
            by="video_id", 
            direction="backward"
        )
        
        # Gom text_clean theo shot_id
        df_ocr_grouped = df_ocr_mapped.groupby("shot_id")["text_clean"].apply(lambda x: " ".join(x.dropna().astype(str))).reset_index()
        df_ocr_grouped.rename(columns={"text_clean": "ocr_text"}, inplace=True)
        
        df_kf["shot_id"] = df_kf["shot_id"].astype(str)
        df_ocr_grouped["shot_id"] = df_ocr_grouped["shot_id"].astype(str)
        
        df_kf = df_kf.merge(df_ocr_grouped, on="shot_id", how="left")
    except Exception as e:
        print(f"⚠️ Lỗi xử lý OCR: {e}")
        df_kf["ocr_text"] = ""
        
    df_kf["ocr_text"] = df_kf["ocr_text"].fillna("")

    # --- ASR ---
    print("4. Merging ASR (±3s window)...")
    try:
        df_asr = pd.read_parquet(DERIVED_DIR / "asr.parquet")
        fps_dict = (df_info.set_index("video_id")["fps_num"] / df_info.set_index("video_id")["fps_den"]).to_dict()
        
        asr_texts_list = []
        asr_gb = df_asr.groupby("video_id")
        
        for row in tqdm(df_kf.itertuples(), total=len(df_kf), desc="Mapping ASR"):
            vid = row.video_id
            kf_frame = row.frame_idx
            
            asr_text = ""
            if vid in asr_gb.groups:
                fps = fps_dict.get(vid, 25.0)
                window = 3.0 * fps
                
                vid_asr = asr_gb.get_group(vid)
                mask = (vid_asr["start_frame"] <= kf_frame + window) & (vid_asr["end_frame"] >= kf_frame - window)
                overlapping = vid_asr[mask]
                
                if not overlapping.empty:
                    asr_text = " ".join(overlapping["text_vi"].dropna().astype(str))
                    
            asr_texts_list.append(asr_text)
            
        df_kf["asr_text"] = asr_texts_list
    except Exception as e:
        print(f"⚠️ Không tìm thấy asr.parquet hoặc lỗi ASR ({e}), bỏ qua.")
        df_kf["asr_text"] = ""
    
    # --- GOM THÀNH doc_text ---
    print("5. Formatting doc_text...")
    titles = df_kf["meta_title"].values
    descs = df_kf["meta_desc"].values
    asrs = df_kf["asr_text"].values
    ocrs = df_kf["ocr_text"].values
    
    doc_texts = []
    for t, d, a, o in tqdm(zip(titles, descs, asrs, ocrs), total=len(df_kf), desc="Joining fields"):
        parts = []
        if t: parts.append(f"[TITLE] {t}")
        if d: parts.append(f"[DESC] {d}")
        if a: parts.append(f"[ASR] {a}")
        if o: parts.append(f"[OCR] {o}")
        doc_texts.append("\n".join(parts).lower())
        
    df_kf["doc_text"] = doc_texts
    
    # Final Output
    df_out = df_kf[["kf_id", "video_id", "shot_id", "frame_idx", "doc_text"]]
    out_path = DERIVED_DIR / "docs_bm25.parquet"
    df_out.to_parquet(out_path, index=False)
    
    print(f"\n✅ Đã lưu {len(df_out):,} documents vào {out_path}!")

if __name__ == "__main__":
    run_bm25_job()
