import cv2
import pandas as pd
import numpy as np
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from collections import Counter
from preprocessing.common.decode import extract_frame_exact
from preprocessing.common.frame_map import load_frame_map

def find_btc_keyframe_path(video_id, kf_ord):
    prefix = video_id[:3]
    # Keyframes folders might be named "Keyframes_L21", "Keyframes_L22", etc.
    # Alternatively, there's a folder "Keyframes_L21" inside "keyframes".
    kf_dir = RAW_DIR / "btc" / "keyframes" / f"Keyframes_{prefix}" / video_id
    if not kf_dir.exists():
        kf_dir = RAW_DIR / "btc" / "keyframes" / prefix / video_id
        if not kf_dir.exists():
            return None
            
    for pad in [3, 4, 1]:
        candidate = kf_dir / f"{kf_ord:0{pad}d}.jpg"
        if candidate.exists(): return candidate
    return None

# Hằng số đường dẫn
DATA_DIR = Path("data")
RAW_DIR = DATA_DIR / "raw"
VIDEOS_DIR = RAW_DIR / "videos"
DERIVED_DIR = DATA_DIR / "derived"

def select_dynamic_keyframes(video_id: str, df_map_vid: pd.DataFrame, top_k: int = 3) -> pd.DataFrame:
    npy_path = RAW_DIR / "btc" / "clip-features-32" / f"{video_id}.npy"
    df_sorted = df_map_vid.sort_values("btc_kf_ordinal").reset_index(drop=True)
    
    if not npy_path.exists() or len(df_sorted) < top_k + 2:
        return df_sorted.sample(min(len(df_sorted), top_k))
        
    arr = np.load(npy_path).astype(np.float32)
    if arr.shape[0] != len(df_sorted):
        return df_sorted.sample(min(len(df_sorted), top_k))
        
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    arr_norm = arr / norms
    
    cos_sims = np.sum(arr_norm[:-1] * arr_norm[1:], axis=1)
    diff_scores = []
    for i in range(1, len(df_sorted) - 1):
        neighbor_cos = max(cos_sims[i-1], cos_sims[i])
        diff_scores.append((neighbor_cos, i))
        
    diff_scores.sort(key=lambda x: x[0])
    selected_indices = [idx for _, idx in diff_scores[:top_k]]
    return df_sorted.iloc[selected_indices]

def sweep_single_keyframe(mp4_path, btc_img, base_idx):
    results = {}
    
    # We want frames from base_idx - 5 to base_idx + 5
    start_idx = max(0, base_idx - 5)
    end_idx = base_idx + 5
    
    # Use extract_frame_exact to jump securely to start_idx
    cap = cv2.VideoCapture(str(mp4_path))
    if not cap.isOpened():
        return results
        
    jump_target = max(0, start_idx - 60)
    cap.set(cv2.CAP_PROP_POS_FRAMES, jump_target)
    
    current_idx = jump_target
    while current_idx < start_idx:
        ret, _ = cap.read()
        if not ret: break
        current_idx += 1
        
    # Now at start_idx, read 11 frames
    for offset in range(start_idx - base_idx, end_idx - base_idx + 1):
        target_idx = base_idx + offset
        if target_idx < 0:
            continue
            
        ret, frame = cap.read()
        if not ret: break
        
        ext_img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        if btc_img.shape != ext_img.shape:
            ext_img = cv2.resize(ext_img, (btc_img.shape[1], btc_img.shape[0]))
        err = np.mean((btc_img.astype("float") - ext_img.astype("float")) ** 2)
        results[offset] = err
        
    cap.release()
    return results

def detect_video_offset(video_id: str, mp4_path: Path, df_map_vid: pd.DataFrame) -> dict:
    fps_val = float(df_map_vid["fps"].iloc[0]) if "fps" in df_map_vid.columns else 30.0
    fps_num = int(df_map_vid["fps_num"].iloc[0]) if "fps_num" in df_map_vid.columns else int(round(fps_val))
    fps_den = int(df_map_vid["fps_den"].iloc[0]) if "fps_den" in df_map_vid.columns else 1

    def try_measure(k):
        samples = select_dynamic_keyframes(video_id, df_map_vid, top_k=k)
        best_offsets = []
        winning_mses = []
        second_mses = []
        
        for _, row in samples.iterrows():
            ordinal = int(row["btc_kf_ordinal"])
            base_idx = int(row["frame_idx_raw"])
            
            btc_path = find_btc_keyframe_path(video_id, ordinal)
            if btc_path is None: continue
            btc_img = cv2.cvtColor(cv2.imread(str(btc_path)), cv2.COLOR_BGR2RGB)
            
            mses = sweep_single_keyframe(str(mp4_path), btc_img, base_idx)
            if mses:
                sorted_mses = sorted(mses.items(), key=lambda x: x[1])
                best_off, best_mse = sorted_mses[0]
                sec_mse = sorted_mses[1][1] if len(sorted_mses) > 1 else float('inf')
                
                best_offsets.append(best_off)
                winning_mses.append(best_mse)
                second_mses.append(sec_mse)
                
        return best_offsets, winning_mses, second_mses

    # THỬ LẦN 1: 3 KEYFRAMES
    best_offsets, winning_mses, second_mses = try_measure(3)
    
    def check_conditions(offs, mses1, mses2):
        if not offs: return False, 0, 9999
        counts = Counter(offs)
        most_common_off, count = counts.most_common(1)[0]
        
        if count != len(offs): return False, 0, 9999
        
        win_mses_filtered = [m1 for off, m1 in zip(offs, mses1) if off == most_common_off]
        sec_mses_filtered = [m2 for off, m2 in zip(offs, mses2) if off == most_common_off]
        
        best_m1 = np.mean(win_mses_filtered)
        best_m2 = np.mean(sec_mses_filtered)
        
        if best_m1 > 50: return False, 0, 9999
        if best_m2 < best_m1 * 10: return False, 0, 9999
        
        return True, most_common_off, best_m1

    ok, off, mse_val = check_conditions(best_offsets, winning_mses, second_mses)
    
    res = {
        "video_id": video_id,
        "fps_num": fps_num,
        "fps_den": fps_den,
        "n_samples_used": len(best_offsets)
    }

    if ok:
        res.update({"offset": int(off), "offset_status": "ok", "offset_confidence": mse_val})
        return res
        
    # THỬ LẦN 2: 8 KEYFRAMES
    best_offsets, winning_mses, second_mses = try_measure(8)
    res["n_samples_used"] = len(best_offsets)
    
    if not best_offsets:
        res.update({"offset": 0, "offset_status": "unresolved", "offset_confidence": 9999.0})
        return res
        
    counts = Counter(best_offsets)
    most_common_off, count = counts.most_common(1)[0]
    
    if count >= len(best_offsets) // 2 + 1:
        win_mses_filtered = [m1 for off, m1 in zip(best_offsets, winning_mses) if off == most_common_off]
        sec_mses_filtered = [m2 for off, m2 in zip(best_offsets, second_mses) if off == most_common_off]
        
        best_m1 = np.mean(win_mses_filtered)
        best_m2 = np.mean(sec_mses_filtered)
        
        if best_m1 < 100 and best_m2 > best_m1 * 5:
            res.update({"offset": int(most_common_off), "offset_status": "ok_8", "offset_confidence": best_m1})
            return res
            
    res.update({
        "offset": 0, 
        "offset_status": "ambiguous", 
        "offset_confidence": np.mean(winning_mses) if winning_mses else 9999.0
    })
    return res

def update_frame_map_parquet(df_offset: pd.DataFrame):
    map_path = DERIVED_DIR / "frame_map.parquet"
    if not map_path.exists():
        print("Chưa có frame_map.parquet để cập nhật.")
        return

    df_map = pd.read_parquet(map_path)
    
    offset_dict = df_offset.set_index("video_id")["offset"].to_dict()
    status_dict = df_offset.set_index("video_id")["offset_status"].to_dict()

    if "frame_offset" not in df_map.columns:
        df_map["frame_offset"] = 0
    if "offset_status" not in df_map.columns:
        df_map["offset_status"] = "no_video"

    mask = df_map["video_id"].isin(offset_dict.keys())
    if mask.any():
        df_map.loc[mask, "frame_offset"] = df_map.loc[mask, "video_id"].map(offset_dict).astype(int)
        df_map.loc[mask, "offset_status"] = df_map.loc[mask, "video_id"].map(status_dict)
    
    df_map["offset_verified"] = df_map["offset_status"].isin(["ok", "ok_8", "ambiguous"])
    df_map["frame_idx_corrected"] = df_map["frame_idx_raw"] + df_map["frame_offset"]

    # Đổi tên frame_idx_corrected thành frame_idx theo chuẩn gác cổng, giữ raw là frame_idx_raw
    if "frame_idx_corrected" in df_map.columns:
        df_map["frame_idx"] = df_map["frame_idx_corrected"]
        
    df_map.to_parquet(map_path, index=False)
    
    n_verified = df_map[df_map["offset_verified"]]["video_id"].nunique()
    total_vids = df_map["video_id"].nunique()
    print(f"\n[FRAME_MAP UPDATED] Đã verify chính xác offset cho {n_verified}/{total_vids} video.")

def main():
    print("=" * 70)
    print(" VIỆC 1 & 2: ĐO OFFSET RIÊNG CHO TỪNG VIDEO (DÙNG CẢNH ĐỘNG)")
    print("=" * 70)

    df_map = load_frame_map()
    mp4_map = {mp4.stem: mp4 for mp4 in VIDEOS_DIR.rglob("*.mp4")}
    
    offset_results = []
    for vid, mp4_path in mp4_map.items():
        df_vid = df_map[df_map["video_id"] == vid]
        if len(df_vid) == 0: continue
        res = detect_video_offset(vid, mp4_path, df_vid)
        offset_results.append(res)
        print(f"[{len(offset_results)}/{len(mp4_map)}] {vid:<10} | {res['offset']:+2d} | {res['offset_status']:<10} | {res['offset_confidence']:.1f}", flush=True)
        
    df_offset = pd.DataFrame(offset_results)
    DERIVED_DIR.mkdir(parents=True, exist_ok=True)
    df_offset.to_parquet(DERIVED_DIR / "video_offset.parquet", index=False)
    
    update_frame_map_parquet(df_offset)

if __name__ == "__main__":
    main()
