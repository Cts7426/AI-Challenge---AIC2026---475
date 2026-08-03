import argparse
import os
import sys
import shutil
import hashlib
import glob
from pathlib import Path
from common.shard import get_zip_shard, get_video_shard
from common.manifest import ManifestManager
from common.ffmpeg import get_video_header, extract_audio
from common.decode import extract_keyframes_and_count, sample_keyframes_from_shots
import pandas as pd
from b01_full_verification import process_video

# SCENEDETECT
from scenedetect import ContentDetector, SceneManager, open_video

# Cấu trúc thư mục
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
RAW_VIDEOS_DIR = DATA_DIR / "raw" / "videos"
DERIVED_AUDIO_DIR = DATA_DIR / "derived" / "audio"
DERIVED_SHOTS_DIR = DATA_DIR / "derived" / "shots_parts"
DERIVED_KF_DIR = DATA_DIR / "derived" / "keyframes"
MANIFEST_PATH = DATA_DIR / "manifests" / "rolling_ingest.json"

def detect_shots(video_path: str, downscale_factor: int = 2) -> list:
    """Trả về danh sách các shot dạng [(start_frame, end_frame), ...]"""
    video = open_video(video_path)
    scene_manager = SceneManager()
    scene_manager.add_detector(ContentDetector(threshold=27))
    scene_manager.downscale = downscale_factor
    scene_manager.detect_scenes(video)
    scenes = scene_manager.get_scene_list()
    # Nếu không detect được scene nào, gán thành 1 scene bao trọn video
    if not scenes:
        frames = video.duration.get_frames()
        if frames > 0:
            return [(0, frames)]
        else:
            return [(0, 1)] # fallback if unknown
    
    return [(s[0].get_frames(), s[1].get_frames()) for s in scenes]

def check_disk_space(min_required_bytes: int):
    total, used, free = shutil.disk_usage("/")
    if free < min_required_bytes:
        print(f"[FATAL] Không đủ dung lượng đĩa. Trống: {free/1e9:.2f}GB. Yêu cầu: {min_required_bytes/1e9:.2f}GB.")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Rolling Ingest Pipeline")
    parser.add_argument("--shard", type=int, required=True, help="Shard ID của người chạy (0-4)")
    parser.add_argument("--num-shards", type=int, default=5, help="Tổng số shard (default: 5)")
    parser.add_argument("--keep-videos", action="store_true", help="Giữ lại file mp4 thay vì xóa")
    parser.add_argument("--dev-subset", action="store_true", help="Chỉ xử lý danh sách dev_videos.txt và luôn giữ lại")
    parser.add_argument("--dry-run", action="store_true", help="Chỉ in ra công việc sẽ làm, không thực thi")
    parser.add_argument("--local-dir", type=str, help="Xử lý trực tiếp các video đã tải sẵn trong thư mục này thay vì tải ZIP")
    
    args = parser.parse_args()
    
    manifest = ManifestManager(str(MANIFEST_PATH))
    
    # Ở đây chúng ta implement luồng xử lý local (do người dùng đã tải L21, L22, L23)
    # Pipeline cho Google Sheets (ZIP) sẽ tương tự nhưng vòng ngoài là tải ZIP.
    # Để kiểm thử nhanh theo yêu cầu hiện tại, ta xử lý các file local.
    
    if args.local_dir:
        search_path = Path(args.local_dir)
        video_files = list(search_path.rglob("*.mp4"))
        print(f"Tìm thấy {len(video_files)} video tại {args.local_dir}")
        
        for v_path in video_files:
            video_id = v_path.stem
            
            # Shard cho ingest vẫn có thể áp dụng theo ZIP name nếu có metadata, 
            # nhưng vì file đã giải nén, ta có thể tạm chia theo video_id hoặc không chia để test.
            # Theo yêu cầu 1: "ingest chia theo ZIP". Nếu chạy local, không có ZIP name.
            # Tạm skip check shard nếu truyền local_dir để ưu tiên quá trình xử lý video
            
            if manifest.is_video_processed(video_id):
                print(f"Skip {video_id} (đã xử lý)")
                continue
                
            print(f"\n--- Xử lý {video_id} ---")
            
            if args.dry_run:
                print(f"[DRY-RUN] Sẽ xử lý: {v_path}")
                continue
                
            # 1. ffprobe header
            header = get_video_header(str(v_path))
            print(f"Header: {header}")
            
            # 2. extract audio
            audio_path = DERIVED_AUDIO_DIR / f"{video_id}.wav"
            if header["has_audio"]:
                extract_audio(str(v_path), str(audio_path))
            
            # 3. shot detect
            shots = detect_shots(str(v_path), downscale_factor=2)
            print(f"Phát hiện {len(shots)} shots.")
            
            # (Có thể lưu danh sách shots vào DERIVED_SHOTS_DIR ở đây, dạng json/parquet)
            
            # 4. Trích keyframe và đếm n_frames
            kf_targets = sample_keyframes_from_shots(shots, header["fps_num"], header["fps_den"])
            out_kf_dir = DERIVED_KF_DIR / video_id
            
            n_frames = extract_keyframes_and_count(str(v_path), set(kf_targets.keys()), str(out_kf_dir))
            print(f"Tổng số frame thực đếm được: {n_frames}")
            
            # 5. Xác minh (Verify)
            is_valid = True
            
            if header["has_audio"]:
                if not audio_path.exists() or os.path.getsize(str(audio_path)) == 0:
                    print(f"[ERROR] Audio không hợp lệ: {audio_path}")
                    is_valid = False
                    
            if len(shots) == 0:
                print("[ERROR] Số lượng shot = 0")
                is_valid = False
                
            kf_files = list(out_kf_dir.glob("f*.jpg"))
            if len(kf_files) < 2 * len(shots):
                print(f"[ERROR] Thiếu keyframe: có {len(kf_files)}, yêu cầu tối thiểu {2 * len(shots)}")
                is_valid = False
                
            # 6. Chạy FULL verification TRƯỚC KHI xóa
            keep_mp4_due_to_offset = False
            if is_valid:
                print(f"Bắt đầu FULL verification cho {video_id}...")
                try:
                    df_map = pd.read_parquet(DATA_DIR / "derived" / "frame_map.parquet")
                    if "frame_idx_raw" not in df_map.columns and "frame_idx" in df_map.columns:
                        df_map = df_map.rename(columns={"frame_idx": "frame_idx_raw"})
                        
                    df_vid = df_map[df_map["video_id"] == video_id]
                    if len(df_vid) > 0:
                        df_info_path = DATA_DIR / "derived" / "video_info.parquet"
                        if df_info_path.exists():
                            df_info = pd.read_parquet(df_info_path)
                            n_frames_total = df_info[df_info["video_id"] == video_id]["n_frames"].iloc[0] if video_id in df_info["video_id"].values else 999999
                        else:
                            n_frames_total = 999999
                            
                        results, has_dup = process_video(video_id, df_vid, n_frames_total)
                        
                        if results:
                            df_res = pd.DataFrame(results)
                            df_res["has_duplicate_frames"] = has_dup
                            
                            if has_dup:
                                from b01_recover_missing_frameidx import recover_video
                                print(f"Phát hiện frame lỗi (delta=0), tiến hành khôi phục...")
                                df_res, rc, uc, uv = recover_video(video_id, df_res, str(v_path))
                                print(f"Khôi phục: {rc} thành công, {uc} thất bại.")
                                
                            PARTS_DIR = DATA_DIR / "derived" / "full_verification_parts"
                            PARTS_DIR.mkdir(parents=True, exist_ok=True)
                            
                            df_res.to_parquet(PARTS_DIR / f"{video_id}.parquet", index=False)
                            print(f"Hoàn tất verification cho {video_id}. Lưu checkpoint part thành công.")
                            
                            # Decide if we need to keep mp4
                            num_shifted = len(df_res[df_res["verdict"] == "shifted"])
                            num_nomatch = len(df_res[df_res["verdict"] == "no_match"])
                            if num_nomatch > 0 or (num_shifted / len(df_res)) > 0.5:
                                print(f"[CẢNH BÁO] Phát hiện lỗi nghiêm trọng (no_match hoặc shift > 50%). GIỮ LẠI .mp4 để kiểm tra tay.")
                                keep_mp4_due_to_offset = True
                    else:
                        print(f"Không có dữ liệu keyframe nào trong frame_map.parquet cho {video_id}")
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    print(f"[LỖI] Lỗi khi chạy verification: {e}. GIỮ LẠI .mp4.")
                    keep_mp4_due_to_offset = True
                    
            # 7. Ghi manifest và Xóa (nếu is_valid)
            if is_valid:
                size = os.path.getsize(str(v_path))
                # Hash md5
                md5_hash = hashlib.md5()
                with open(v_path, "rb") as f:
                    # Đọc 1 chunk nhỏ đầu file để demo, nếu đọc cả file quá lâu.
                    # Khuyến cáo đọc cả file để băm chính xác.
                    for byte_block in iter(lambda: f.read(4096), b""):
                        md5_hash.update(byte_block)
                        
                manifest.mark_video_processed(video_id, size, md5_hash.hexdigest())
                
                if not args.keep_videos and not args.dev_subset and not keep_mp4_due_to_offset:
                    os.remove(str(v_path))
                    print(f"Đã xóa {v_path} an toàn.")
                else:
                    reason = "theo cấu hình"
                    if keep_mp4_due_to_offset:
                        reason = "BẢO VỆ DO LỖI OFFSET / CHƯA CHẮC CHẮN"
                    print(f"Giữ lại video {v_path} ({reason}).")
            else:
                print(f"Xử lý {video_id} THẤT BẠI. Không xóa video gốc.")

if __name__ == "__main__":
    main()
