import sys
from pathlib import Path
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT_DIR / "data" / "derived"

def check_file(filename, required_cols):
    path = DATA_DIR / filename
    if not path.exists():
        print(f"⚠️ BỎ QUA: Không tìm thấy {filename}")
        return None
    try:
        df = pd.read_parquet(path)
        missing = set(required_cols) - set(df.columns)
        if missing:
            print(f"❌ LỖI SCHEMA ({filename}): Thiếu các cột {missing}")
            return None
        print(f"✅ SCHEMA OK: {filename} ({len(df):,} dòng)")
        return df
    except Exception as e:
        print(f"❌ LỖI ĐỌC FILE ({filename}): {e}")
        return None

def main():
    print("=== BẮT ĐẦU QUÉT TỔNG LỰC DỮ LIỆU ĐÃ PUSH ===")
    
    # 1. Quét Schema
    df_info = check_file("video_info.parquet", ["video_id", "fps_num", "fps_den", "nb_frames_decoded"])
    df_shots = check_file("shots.parquet", ["shot_id", "video_id", "start_frame", "end_frame", "rep_kf_id"])
    df_kf = check_file("keyframes.parquet", ["kf_id", "video_id", "shot_id", "frame_idx", "path"])
    df_asr = check_file("asr.parquet", ["video_id", "start_frame", "end_frame", "text_vi"])
    df_ocr = check_file("ocr.parquet", ["text_raw", "text_clean"]) # ocr có thể chứa kf_id hoặc rep_kf
    
    if df_info is None:
        print("❌ LỖI CHÍ MẠNG: Không có video_info.parquet để đối chiếu khóa ngoại!")
        sys.exit(1)
        
    valid_videos = set(df_info["video_id"])
    
    # 2. Kiểm tra Khóa Ngoại (Foreign Keys)
    print("\n--- KIỂM TRA TOÀN VẸN KHÓA NGOẠI ---")
    
    if df_asr is not None:
        invalid_asr_vid = set(df_asr["video_id"]) - valid_videos
        if invalid_asr_vid:
            print(f"❌ FAIL: Có {len(invalid_asr_vid)} video_id trong asr.parquet KHÔNG TỒN TẠI trong video_info.parquet!")
        else:
            print("✅ PASS: 100% video_id của ASR hợp lệ.")
            
    if df_kf is not None:
        invalid_kf_vid = set(df_kf["video_id"]) - valid_videos
        if invalid_kf_vid:
            print(f"❌ FAIL: Có {len(invalid_kf_vid)} video_id trong keyframes.parquet KHÔNG hợp lệ!")
        else:
            print("✅ PASS: 100% video_id của Keyframes hợp lệ.")
            
        if df_shots is not None:
            valid_shots = set(df_shots["shot_id"])
            invalid_kf_shot = set(df_kf["shot_id"]) - valid_shots
            if invalid_kf_shot:
                print(f"❌ FAIL: Có {len(invalid_kf_shot)} shot_id trong keyframes.parquet KHÔNG TỒN TẠI trong shots.parquet!")
            else:
                print("✅ PASS: 100% shot_id của Keyframes trỏ đúng về shots.parquet.")

    if df_ocr is not None:
        # Tùy theo cách dev đặt tên cột khóa trong OCR (kf_id hoặc rep_kf_id)
        fk_col = "kf_id" if "kf_id" in df_ocr.columns else ("rep_kf_id" if "rep_kf_id" in df_ocr.columns else None)
        if fk_col and df_kf is not None:
            valid_kfs = set(df_kf["kf_id"])
            # Load thêm frame_map vì OCR có thể chạy trên BTC keyframes
            try:
                df_btc = pd.read_parquet(DATA_DIR / "frame_map.parquet")
                valid_kfs.update(df_btc["kf_id"])
            except:
                pass
                
            invalid_ocr = set(df_ocr[fk_col]) - valid_kfs
            if invalid_ocr:
                print(f"❌ FAIL: Có {len(invalid_ocr)} khóa {fk_col} trong ocr.parquet là mồ côi (Zero Orphan bị vi phạm)!")
            else:
                print(f"✅ PASS: 100% khóa của OCR trỏ đúng về hệ thống Keyframes.")
        elif not fk_col:
            print("⚠️ WARNING: ocr.parquet không có cột kf_id hay rep_kf_id để đối chiếu khóa ngoại!")

    print("\n--- KẾT LUẬN ---")
    print("Quá trình quét hoàn tất. Nếu không có dòng chữ ❌ FAIL nào, toàn bộ file đã push là AN TOÀN.")

if __name__ == "__main__":
    main()
