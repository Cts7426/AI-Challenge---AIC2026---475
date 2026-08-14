import os
import sys
import json
import numpy as np
import statistics
import argparse
from pathlib import Path
from collections import defaultdict
import random
import math
from tqdm import tqdm
import easyocr

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
BTC_DIR = DATA_DIR / "raw" / "btc"

def main():
    parser = argparse.ArgumentParser(description="Chọn dev_videos đa dạng")
    parser.add_argument("--already-extracted", action="store_true", help="Ưu tiên các file đã giải nén nếu có")
    args = parser.parse_args()

    print("Bước 1: Kiểm kê toàn kho từ metadata...")
    meta_dir = BTC_DIR / "metadata" / "media-info"
    if not meta_dir.exists():
        print(f"Không tìm thấy thư mục {meta_dir}")
        return

    meta_files = list(meta_dir.rglob("*.json"))
    videos_meta = {}
    prefixes = defaultdict(int)
    lengths = []

    for mf in meta_files:
        vid = mf.stem
        try:
            with open(mf, 'r', encoding='utf-8') as f:
                data = json.load(f)
                length = float(data.get("length", 0.0))
                if length > 0:
                    videos_meta[vid] = length
                    prefixes[vid[:3]] += 1
                    lengths.append(length)
        except Exception:
            pass

    print(f"Tổng số video có metadata hợp lệ: {len(videos_meta)}")
    print(f"Phân bố prefix: {dict(prefixes)}")
    
    if not lengths:
        print("Không có video nào hợp lệ.")
        return

    lengths.sort()
    n = len(lengths)
    min_l = lengths[0]
    p25 = lengths[int(n * 0.25)]
    p50 = lengths[int(n * 0.50)]
    p75 = lengths[int(n * 0.75)]
    max_l = lengths[-1]

    print(f"Phân bố thời lượng (s): Min={min_l:.1f}, 25%={p25:.1f}, Median={p50:.1f}, 75%={p75:.1f}, Max={max_l:.1f}")

    def get_quartile(l):
        if l <= p25: return 1
        elif l <= p50: return 2
        elif l <= p75: return 3
        else: return 4

    print("\nBước 2 & 3: Thu thập các đặc trưng (Clip, Objects, Text)...")
    
    # Map clip files
    clip_files = list(BTC_DIR.rglob("*clip*.npy")) + list(BTC_DIR.rglob("*.npy"))
    clip_map = {f.stem: f for f in clip_files if f.stem in videos_meta}
    
    # Map object files (actually directories)
    obj_dirs = list((BTC_DIR / "objects").glob("*"))
    obj_map = {d.name: d for d in obj_dirs if d.name in videos_meta and d.is_dir()}

    print(f"Đã ánh xạ {len(clip_map)} file CLIP và {len(obj_map)} file Objects.")

    # Init OCR
    reader = easyocr.Reader(['vi', 'en'], gpu=False, verbose=False)

    valid_candidates = {}
    
    # Lấy mẫu một lượng video vừa đủ để làm candidate pool, nếu chạy OCR toàn kho sẽ quá lâu.
    # Lọc những video có đủ cả clip, objects.
    candidates = [v for v in videos_meta.keys() if v in clip_map and v in obj_map]
    print(f"Số lượng video có đủ (Meta + Clip + Objects): {len(candidates)}")
    
    # TỐI ƯU HÓA: Thay vì chọn random 200 video (rất lâu), ta dùng Phân tầng (Stratified)
    # Chọn tối đa 8 video cho mỗi prefix (L21, L22...) để đảm bảo bao phủ 10 prefix = 80 video max.
    prefix_to_vids = defaultdict(list)
    for v in candidates:
        prefix_to_vids[v[:3]].append(v)
        
    random.seed(42)
    selected_pool = []
    for pref, vids in prefix_to_vids.items():
        selected_pool.extend(random.sample(vids, min(8, len(vids))))
        
    print(f"Chọn {len(selected_pool)} video vào Candidate Pool (phân tầng theo prefix) để chạy nhanh hơn...")

    features = {}

    for vid in tqdm(selected_pool, desc="Extracting features"):
        # 1. Clip STD
        try:
            arr = np.load(clip_map[vid])
            if arr.ndim >= 2 and arr.shape[0] > 1:
                clip_std = float(np.mean(np.std(arr, axis=0)))
            else:
                clip_std = 0.0
        except:
            clip_std = 0.0

        # 2. Objects AVG
        try:
            frame_jsons = list(obj_map[vid].glob("*.json"))
            counts = []
            for fj in frame_jsons:
                with open(fj, 'r', encoding='utf-8') as f:
                    obj_data = json.load(f)
                    counts.append(len(obj_data.get("detection_scores", [])))
            obj_avg = float(np.mean(counts)) if counts else 0.0
        except:
            obj_avg = 0.0

        # 3. Text Density
        kf_vid_dirs = list((BTC_DIR / "keyframes").rglob(vid))
        text_density = 0.0
        if kf_vid_dirs:
            kf_dir = kf_vid_dirs[0]
            jpgs = list(kf_dir.rglob("*.jpg"))
            if len(jpgs) > 0:
                # TỐI ƯU: Chỉ sample 5 frame thay vì 10 để giảm 50% thời gian OCR
                sample_kfs = random.sample(jpgs, min(5, len(jpgs)))
                text_frames = 0
                for img_path in sample_kfs:
                    # TỐI ƯU: detect chữ chỉ cần nhận diện bounding box, tắt detail
                    results = reader.readtext(str(img_path), detail=0)
                    if any(len(txt) > 3 for txt in results):
                        text_frames += 1
                text_density = text_frames / len(sample_kfs)
        
        features[vid] = {
            "length": videos_meta[vid],
            "quartile": get_quartile(videos_meta[vid]),
            "prefix": vid[:3],
            "clip_std": clip_std,
            "obj_avg": obj_avg,
            "text_density": text_density
        }

    # Chuẩn hóa features (Z-score)
    all_clip = [f["clip_std"] for f in features.values()]
    all_obj = [f["obj_avg"] for f in features.values()]
    all_txt = [f["text_density"] for f in features.values()]

    mean_clip, std_clip = np.mean(all_clip), np.std(all_clip) + 1e-6
    mean_obj, std_obj = np.mean(all_obj), np.std(all_obj) + 1e-6
    mean_txt, std_txt = np.mean(all_txt), np.std(all_txt) + 1e-6

    for vid in features:
        features[vid]["norm"] = np.array([
            (features[vid]["clip_std"] - mean_clip) / std_clip,
            (features[vid]["obj_avg"] - mean_obj) / std_obj,
            (features[vid]["text_density"] - mean_txt) / std_txt
        ])

    print("\nBước 4: Greedy Tối đa hóa Đa dạng...")
    
    selected = []
    prefix_counts = defaultdict(int)
    quartile_counts = defaultdict(int)

    def dist(v_norm, s_norms):
        if not s_norms:
            return -np.linalg.norm(v_norm) # Chọn điểm gần gốc tọa độ nhất nếu S rỗng
        return np.mean([np.linalg.norm(v_norm - u) for u in s_norms])

    candidates_left = set(features.keys())
    
    for _ in range(20):
        best_vid = None
        best_dist = -float('inf')
        s_norms = [features[s]["norm"] for s in selected]

        for vid in candidates_left:
            feat = features[vid]
            # Constraints
            if prefix_counts[feat["prefix"]] >= 2:
                continue
            if quartile_counts[feat["quartile"]] >= 5:
                continue

            d = dist(feat["norm"], s_norms)
            if d > best_dist:
                best_dist = d
                best_vid = vid
                
        if best_vid:
            selected.append(best_vid)
            candidates_left.remove(best_vid)
            prefix_counts[features[best_vid]["prefix"]] += 1
            quartile_counts[features[best_vid]["quartile"]] += 1
        else:
            print("[CẢNH BÁO] Không thể tìm thêm video thỏa mãn ràng buộc cứng!")
            break

    print("\nBước 5: Kết quả Báo cáo\n")
    print("| Video ID | Prefix | ZIP (Ước tính) | Độ dài (s) | Mật độ chữ | Đa dạng cảnh (CLIP std) | Objects TB |")
    print("|---|---|---|---|---|---|---|")
    for vid in selected:
        f = features[vid]
        zip_est = f"videos_{f['prefix']}_*.zip" # Không có manifest ZIP chính xác ở đây, ta ước tính
        print(f"| {vid} | {f['prefix']} | {zip_est} | {f['length']:.0f} | {f['text_density']:.2f} | {f['clip_std']:.4f} | {f['obj_avg']:.1f} |")

    # Check stats
    n_high_text = sum(1 for v in selected if features[v]["text_density"] > mean_txt + 0.5 * std_txt)
    n_high_div = sum(1 for v in selected if features[v]["clip_std"] > mean_clip + 0.5 * std_clip)
    n_low_div = sum(1 for v in selected if features[v]["clip_std"] < mean_clip - 0.5 * std_clip)
    
    print("\n--- Kiểm tra Yêu cầu ---")
    print(f"Ít nhất 5 video nhiều chữ: Đạt {n_high_text}")
    print(f"Ít nhất 5 video đa dạng cảnh cao: Đạt {n_high_div}")
    print(f"Ít nhất 3 video đa dạng cảnh thấp: Đạt {n_low_div}")
    print(f"Số lượng mỗi quartile: {dict(quartile_counts)}")

    print("\n>>> KẾT THÚC. Bạn hãy xem bảng kết quả. Nếu đồng ý, chúng ta sẽ lưu dev_videos.txt!")

if __name__ == "__main__":
    main()
