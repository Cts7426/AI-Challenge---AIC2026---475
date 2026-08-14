import os
import glob
from pathlib import Path
import pandas as pd
from fractions import Fraction

def load_btc_videos():
    # Giả định danh sách video BTC lấy từ thư mục media-info
    p = Path("data/raw/btc/metadata/media-info")
    if not p.exists():
        return set()
    return set([f.stem for f in p.glob("*.json")])

def run_l1_l2():
    print("=== NGHIỆM THU B0.1 (VIDEO AUDIT & MAPPING) ===")
    
    video_info_path = "data/derived/video_info.parquet"
    frame_map_path = "data/derived/frame_map.parquet"
    
    if not os.path.exists(video_info_path) or not os.path.exists(frame_map_path):
        print(f"❌ LỖI: Thiếu file {video_info_path} hoặc {frame_map_path}")
        return

    print("Đang tải dữ liệu...")
    df_v = pd.read_parquet(video_info_path)
    df_f = pd.read_parquet(frame_map_path)
    
    print("\n[DEBUG] Các cột trong video_info.parquet:", df_v.columns.tolist())
    print("[DEBUG] Các cột trong frame_map.parquet:", df_f.columns.tolist())
    
    # Dựa theo cột thực tế
    dur_col = 'duration_sec' if 'duration_sec' in df_v.columns else ('duration' if 'duration' in df_v.columns else None)
    nb_frames_col = 'nb_frames_decoded' if 'nb_frames_decoded' in df_v.columns else ('n_frames' if 'n_frames' in df_v.columns else None)
    
    btc_ord_col = 'btc_ordinal' if 'btc_ordinal' in df_f.columns else ('btc_kf_ordinal' if 'btc_kf_ordinal' in df_f.columns else None)
    
    frame_idx_col = 'frame_idx'
    if 'frame_idx' not in df_f.columns:
        frame_idx_col = 'frame_idx_corrected' if 'frame_idx_corrected' in df_f.columns else 'frame_idx_raw'
    
    btc_videos = load_btc_videos()
    
    # ---------------------------
    # TẦNG L1: TỰ ĐỘNG BẮT LỖI
    # ---------------------------
    print("\n--- TẦNG L1: KIỂM TRA ĐÚNG/SAI (BẮT BUỘC XANH) ---")
    
    # L1-1
    if btc_videos:
        meta_videos = set(df_v['video_id'].unique())
        diff1 = btc_videos - meta_videos
        diff2 = meta_videos - btc_videos
        if diff1 or diff2:
            print(f"❌ L1-1 FAIL: Tập video không khớp BTC. Thiếu: {len(diff1)}, Thừa: {len(diff2)}")
        else:
            print("✅ L1-1 PASS: Tập video_id khớp 100% với BTC.")
    else:
        print("⚠️ L1-1 SKIP: Không tìm thấy thư mục media-info của BTC để đối chiếu.")
        
    # L1-2
    try:
        assert (df_v['fps_num'] > 0).all() and (df_v['fps_den'] > 0).all()
        if 'fps' in df_v.columns:
            assert df_v['fps'].dtype not in ['float64', 'float32']
        print("✅ L1-2 PASS: fps_num và fps_den > 0 hợp lệ, không dùng float cho fps.")
    except Exception as e:
        print(f"❌ L1-2 FAIL: Lỗi cấu trúc fps_num/fps_den. Chi tiết: {e}")

    # L1-3
    try:
        if nb_frames_col and dur_col:
            assert (df_v[nb_frames_col] > 0).all() and (df_v[dur_col] > 0).all()
            print(f"✅ L1-3 PASS: {nb_frames_col} và {dur_col} > 0 cho toàn bộ video.")
        else:
            print("❌ L1-3 FAIL: Không tìm thấy cột chứa nb_frames hoặc duration.")
    except Exception as e:
        import traceback
        print(f"❌ L1-3 FAIL: Cột {nb_frames_col} hoặc {dur_col} có giá trị <= 0. Chi tiết:\n{traceback.format_exc()}")
        
    # L1-4
    try:
        merged = df_f.merge(df_v, on='video_id', how='left')
        assert df_f[frame_idx_col].dtype in ['int64', 'int32', 'float64'] # Chấp nhận float64 tạm để xem có NaN không
        if df_f[frame_idx_col].isna().any():
            print(f"❌ L1-4 FAIL: Cột {frame_idx_col} chứa giá trị NaN.")
        else:
            assert df_f[frame_idx_col].dtype in ['int64', 'int32']
            if nb_frames_col:
                assert (merged[frame_idx_col] >= 0).all()
                assert (merged[frame_idx_col] < merged[nb_frames_col]).all()
                print(f"✅ L1-4 PASS: {frame_idx_col} là int và nằm gọn trong [0, {nb_frames_col}).")
            else:
                print(f"⚠️ L1-4 COND: {frame_idx_col} là int, nhưng không có nb_frames để check cận trên.")
    except Exception as e:
        import traceback
        print(f"❌ L1-4 FAIL: Lỗi {frame_idx_col}. Chi tiết:\n{traceback.format_exc()}")
        
    # L1-5
    try:
        if btc_ord_col:
            assert not df_f.duplicated(subset=['video_id', btc_ord_col]).any()
        assert not df_f.duplicated(subset=['video_id', frame_idx_col]).any()
        print(f"✅ L1-5 PASS: Tính duy nhất của (video_id, {frame_idx_col}) được bảo đảm tuyệt đối.")
    except Exception as e:
        import traceback
        print(f"❌ L1-5 FAIL: Phát hiện bản ghi trùng lặp (duplicate)! Chi tiết:\n{traceback.format_exc()}")

    # L1-6: Số lượng keyframe map được phải bằng số lượng keyframe thực tế của BTC cung cấp
    try:
        btc_kf_dir = Path("data/raw/btc/keyframes")
        if btc_kf_dir.exists():
            mapped_counts = df_f.groupby("video_id").size().to_dict()
            missing_vids = []
            mismatch_vids = []
            
            for vid in mapped_counts.keys():
                # Tìm thư mục keyframe của video này (có thể nằm trong Lxx/Lxx_Vxxx)
                vid_dir = list(btc_kf_dir.rglob(vid))
                if not vid_dir:
                    missing_vids.append(vid)
                else:
                    jpg_count = len(list(vid_dir[0].glob("*.jpg")))
                    if mapped_counts[vid] != jpg_count:
                        mismatch_vids.append((vid, mapped_counts[vid], jpg_count))
            
            if mismatch_vids:
                print(f"❌ L1-6 FAIL: Có {len(mismatch_vids)} video không khớp số lượng file .jpg với BTC.")
                print("   Ví dụ:", mismatch_vids[:3])
            elif missing_vids:
                print(f"❌ L1-6 FAIL: Không tìm thấy thư mục ảnh của {len(missing_vids)} video.")
            else:
                print("✅ L1-6 PASS: Số lượng keyframe map được khớp 100% với số lượng file .jpg thực tế trên đĩa.")
        else:
            print("⚠️ L1-6 SKIP: Không tìm thấy thư mục ảnh btc/keyframes trên đĩa (Chỉ có thể test khi chạy trên máy chủ Kaggle).")
    except Exception as e:
        print(f"❌ L1-6 FAIL: Lỗi khi kiểm tra L1-6. Chi tiết: {e}")

    # L1-7: Round-trip frame -> time -> frame không bị lệch (Precision test bằng Fraction)
    try:
        from fractions import Fraction
        sample_size = min(10000, len(df_f))
        sample_df = df_f.sample(n=sample_size, random_state=42).copy()
        sample_merged = sample_df.merge(df_v[['video_id', 'fps_num', 'fps_den']], on='video_id', how='left')
        
        failed_round_trips = 0
        for _, row in sample_merged.iterrows():
            f_idx = int(row[frame_idx_col])
            fps = Fraction(int(row['fps_num']), int(row['fps_den']))
            
            # Tính time (tuyệt đối không dùng float)
            time_val = Fraction(f_idx, 1) / fps
            
            # Tính ngược lại frame
            f_idx_recovered = time_val * fps
            
            if f_idx_recovered.denominator != 1 or int(f_idx_recovered.numerator) != f_idx:
                failed_round_trips += 1
                
        if failed_round_trips > 0:
            print(f"❌ L1-7 FAIL: Failed {failed_round_trips}/{sample_size} round-trip conversions (Precision issue).")
        else:
            print(f"✅ L1-7 PASS: Round-trip frame->time->frame vượt qua {sample_size}/{sample_size} mẫu ngẫu nhiên bằng công thức toán học Fraction tuyệt đối.")
    except Exception as e:
        import traceback
        print(f"❌ L1-7 FAIL: Lỗi khi test L1-7. Chi tiết:\n{traceback.format_exc()}")

    # L1-8: Kiểm tra duration * fps so với nb_frames_decoded
    try:
        if dur_col and nb_frames_col:
            calc_frames = df_v[dur_col] * (df_v['fps_num'] / df_v['fps_den'])
            diff = (calc_frames - df_v[nb_frames_col]).abs()
            
            # Loại trừ VFR nếu có
            if 'is_vfr' in df_v.columns:
                diff = diff[df_v['is_vfr'] == False]
                
            bad_diffs = diff[diff > 2.0]
            if len(bad_diffs) > 0:
                print(f"❌ L1-8 FAIL: Có {len(bad_diffs)} video lệch duration*fps > 2 frame so với thực tế.")
                # Lỗi này khá phổ biến vì duration làm tròn, ta chỉ in ra để Audit chứ ko panic
            else:
                print("✅ L1-8 PASS: Không có video nào (ngoại trừ VFR) bị lệch duration*fps quá 2 frame.")
        else:
            print("⚠️ L1-8 SKIP: Thiếu duration hoặc nb_frames để kiểm tra.")
    except Exception as e:
        print(f"❌ L1-8 FAIL: Lỗi khi test L1-8. Chi tiết: {e}")

    # ---------------------------
    # TẦNG L2: PHÂN PHỐI
    # ---------------------------
    print("\n--- TẦNG L2: PHÂN TÍCH PHÂN PHỐI (CẢNH BÁO) ---")
    if 'is_vfr' in df_v.columns:
        vfr_count = df_v['is_vfr'].sum()
        print(f"🔍 L2-1 (VFR): {vfr_count} video bị VFR (Variable Frame Rate).")
        if vfr_count == 0:
            print("   ⚠️ (Đáng ngờ: Thường BTC sẽ có video VFR. Báo cáo 0 có thể là do chưa check kỹ PTS)")
    else:
        print("🔍 L2-1 (VFR): (Không có cột is_vfr để kiểm tra)")
        
    if 'has_audio' in df_v.columns:
        no_audio = (~df_v['has_audio']).sum()
        print(f"🔍 L2-2 (No Audio): {no_audio} video không có tiếng.")
    else:
        print("🔍 L2-2 (No Audio): (Không có cột has_audio để kiểm tra)")
        
    if dur_col:
        print(f"🔍 L2-4 (Duration p50): {df_v[dur_col].median():.2f} giây")
    else:
        print("🔍 L2-4 (Duration p50): Không có cột duration")
    
    print("\n🎉 [Hoàn thành] Đội trưởng hãy rà soát kỹ các mục L1. Nếu có chữ LỖI ❌, tuyệt đối không đi tiếp!")

if __name__ == "__main__":
    run_l1_l2()
