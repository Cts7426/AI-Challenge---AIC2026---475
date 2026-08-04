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
from concurrent.futures import ThreadPoolExecutor, as_completed

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

from shot_job import process_single_video, load_config
import cv2

def check_disk_space(min_required_bytes: int):
    total, used, free = shutil.disk_usage("/")
    if free < min_required_bytes:
        print(f"[FATAL] Không đủ dung lượng đĩa. Trống: {free/1e9:.2f}GB. Yêu cầu: {min_required_bytes/1e9:.2f}GB.")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Rolling Ingest Pipeline")
    parser.add_argument("--shard", type=int, required=True, help="Shard ID của người chạy (0-4)")
    parser.add_argument("--num-shards", type=int, default=5, help="Tổng số shard (default: 5)")
    parser.add_argument("--workers", type=int, default=1, help="Số luồng xử lý đồng thời")
    parser.add_argument("--keep-videos", action="store_true", help="Giữ lại file mp4 thay vì xóa")
    parser.add_argument("--dev-subset", action="store_true", help="Chỉ xử lý danh sách dev_videos.txt và luôn giữ lại")
    parser.add_argument("--dry-run", action="store_true", help="Chỉ in ra công việc sẽ làm, không thực thi")
    parser.add_argument("--local-dir", type=str, help="Xử lý trực tiếp các video đã tải sẵn trong thư mục này thay vì tải ZIP")
    parser.add_argument("--video-ids", nargs="+", help="Chỉ định danh sách video_id cụ thể để chạy nghiệm thu")
    
    args = parser.parse_args()
    
    manifest = ManifestManager(str(MANIFEST_PATH))
    
   
    DEV_VIDEOS_PATH = DATA_DIR / "dev_videos.txt"
    dev_videos = set()
    if DEV_VIDEOS_PATH.exists():
        with open(DEV_VIDEOS_PATH, "r") as f:
            dev_videos = {line.strip() for line in f if line.strip()}
    
    cfg = load_config()
    sc = cfg["shot_detection"]
    thr = float(sc.get("content_threshold", 27.0))
    ds = int(sc.get("downscale_factor", 2))
    min_shot_frames = max(1, round(float(sc.get("min_shot_seconds", 0.5)) * 30))
    min_s = float(sc.get("min_shot_seconds", 0.5))
    max_s = float(sc.get("max_shot_seconds", 60.0))
    force_s = float(sc.get("force_split_seconds", 30.0))
    hash_str = f"pyav|{ds}|{thr}|{min_s}|{max_s}|{force_s}"
    import hashlib
    config_hash = hashlib.sha256(hash_str.encode()).hexdigest()[:12]
    print(f"==> CONFIG_HASH SẼ DÙNG: [{config_hash}]")
    
    # Load video_info.parquet
    INFO_PATH = DATA_DIR / "derived" / "video_info.parquet"
    if not INFO_PATH.exists():
        print("[FATAL] Không tìm thấy video_info.parquet!")
        sys.exit(1)
    df_vi = pd.read_parquet(INFO_PATH)
    video_info_dict = {r["video_id"]: r for r in df_vi.to_dict("records")}
    
    if args.local_dir:
        search_path = Path(args.local_dir)
        video_files = list(search_path.rglob("*.mp4"))
        
        to_process = []
        skipped_no_info = []
        for v_path in video_files:
            video_id = v_path.stem
            
            if args.video_ids and video_id not in args.video_ids:
                continue
                
            if video_id not in video_info_dict:
                skipped_no_info.append(video_id)
                continue
                
            # Check manifest OR if it was already processed by shot_job (has parquet)
            has_parquet = (DATA_DIR / "derived" / "shots_parts" / f"{video_id}.parquet").exists()
            
            # Bỏ qua kiểm tra manifest/parquet nếu user chỉ định cụ thể video (để test lại)
            if (not manifest.is_video_processed(video_id) and not has_parquet) or args.video_ids:
                to_process.append(v_path)
                
        print(f"Tìm thấy {len(video_files)} video tại {args.local_dir}, cần xử lý: {len(to_process)}")
        if skipped_no_info:
            print(f"[CẢNH BÁO] Đã bỏ qua {len(skipped_no_info)} video vì KHÔNG CÓ TRONG video_info.parquet!")

        
        if args.dry_run:
            keep_list = [v.stem for v in to_process if v.stem in dev_videos]
            delete_list = [v.stem for v in to_process if v.stem not in dev_videos]
            print(f"[DRY-RUN] Sẽ xử lý: {len(to_process)} video")
            print(f"[DRY-RUN] Sẽ GIỮ LẠI mp4 của {len(keep_list)} video dev: {keep_list}")
            print(f"[DRY-RUN] Sẽ XÓA mp4 của {len(delete_list)} video khác.")
            print(f"[DRY-RUN] config_hash = {config_hash}")
            return
            
        print(f"Bắt đầu xử lý với {args.workers} luồng...")
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(process_video_pipeline, v_path, args, video_info_dict, dev_videos, manifest): v_path for v_path in to_process}
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    v_path = futures[future]
                    print(f"Lỗi không xác định khi xử lý {v_path.stem}: {e}")

def process_video_pipeline(v_path, args, video_info_dict, dev_videos, manifest):
    video_id = v_path.stem
    print(f"\n--- Xử lý {video_id} ---")
        
    # 1. Lấy thông tin từ video_info.parquet
    info = video_info_dict[video_id]
    fps_num = info["fps_num"]
    fps_den = info.get("fps_den", 1)
    n_frames_total = info["n_frames"]
    print(f"Info từ parquet: {fps_num}/{fps_den} fps, {n_frames_total} frames")
    
    # 2. Extract audio (Dùng get_video_header chỉ để lấy has_audio)
    header = get_video_header(str(v_path))
    audio_path = DERIVED_AUDIO_DIR / f"{video_id}.wav"
    if header["has_audio"]:
        extract_audio(str(v_path), str(audio_path))
    
    # 3. shot detect
    cfg = load_config()
    
    df_shots, stats = process_single_video(
        video_id=video_id,
        video_path=str(v_path),
        fps_num=fps_num,
        fps_den=fps_den,
        n_frames=n_frames_total,
        cfg=cfg,
        output_dir=DERIVED_SHOTS_DIR,
        backend="pyav"
    )
    
    # Xác minh (Verify)
    is_valid = True
    
    # KIỂM BỔ SUNG (b): Kiểm tra part parquet đã sinh ra có chứa config_hash không
    part_path = DERIVED_SHOTS_DIR / f"{video_id}.parquet"
    if not part_path.exists():
        print(f"[ERROR] Quá trình phân mảnh shot không tạo ra file {part_path}!")
        is_valid = False
    else:
        try:
            df_part = pd.read_parquet(part_path)
            if "config_hash" not in df_part.columns:
                print(f"[ERROR] File part {part_path} bị thiếu cột config_hash!")
                is_valid = False
        except Exception as e:
            print(f"[ERROR] Không thể đọc file part {part_path}: {e}")
            is_valid = False
    
    shots = list(zip(df_shots["start_frame"], df_shots["end_frame"]))
    print(f"Phát hiện {len(shots)} shots cho {video_id}.")
    
    # 4. Trích keyframe và đếm n_frames
    kf_targets = sample_keyframes_from_shots(shots, fps_num, fps_den)
    out_kf_dir = DERIVED_KF_DIR / video_id
    
    n_frames = extract_keyframes_and_count(str(v_path), set(kf_targets.keys()), str(out_kf_dir))
    print(f"Tổng số frame đếm được khi trích xuất: {n_frames}")
    
    # KIỂM BỔ SUNG (a): Cảnh báo nếu n_frames đếm thực tế lệch với video_info
    if n_frames != n_frames_total:
        print(f"[CẢNH BÁO MẠNH] Decoder ffmpeg đếm được {n_frames} frames, LỆCH so với {n_frames_total} trong video_info.parquet!")
        
    # 5. Xác minh Audio và Keyframes
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
                        print(f"Phát hiện frame lỗi (delta=0), tiến hành khôi phục cho {video_id}...")
                        df_res, rc, uc, uv = recover_video(video_id, df_res, str(v_path))
                        print(f"Khôi phục {video_id}: {rc} thành công, {uc} thất bại.")
                        
                    PARTS_DIR = DATA_DIR / "derived" / "full_verification_parts"
                    PARTS_DIR.mkdir(parents=True, exist_ok=True)
                    
                    df_res.to_parquet(PARTS_DIR / f"{video_id}.parquet", index=False)
                    print(f"Hoàn tất verification cho {video_id}. Lưu checkpoint part thành công.")
                    
                    # Decide if we need to keep mp4
                    num_shifted = len(df_res[df_res["verdict"] == "shifted"])
                    num_nomatch = len(df_res[df_res["verdict"] == "no_match"])
                    if num_nomatch > 0 or (num_shifted / len(df_res)) > 0.5:
                        print(f"[CẢNH BÁO] Phát hiện lỗi nghiêm trọng (no_match hoặc shift > 50%). GIỮ LẠI {video_id}.mp4 để kiểm tra tay.")
                        keep_mp4_due_to_offset = True
            else:
                print(f"Không có dữ liệu keyframe nào trong frame_map.parquet cho {video_id}")
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[LỖI] Lỗi khi chạy verification cho {video_id}: {e}. GIỮ LẠI .mp4.")
            keep_mp4_due_to_offset = True
            
    # 7. Ghi manifest và Xóa (nếu is_valid)
    if is_valid:
        size = os.path.getsize(str(v_path))
        # Hash md5 1MB đầu + 1MB cuối + size để tối ưu
        md5_hash = hashlib.md5()
        with open(v_path, "rb") as f:
            f.seek(0, os.SEEK_END)
            f_size = f.tell()
            f.seek(0)
            chunk_size = min(1024 * 1024, f_size)
            md5_hash.update(f.read(chunk_size))
            if f_size > 1024 * 1024:
                f.seek(-chunk_size, os.SEEK_END)
                md5_hash.update(f.read(chunk_size))
        md5_hash.update(str(f_size).encode())
                
        manifest.mark_video_processed(video_id, size, md5_hash.hexdigest())
        
        is_dev = video_id in dev_videos
        # Đảm bảo điều kiện xoá là: hợp lệ VÀ đã sinh parquet part VÀ không thuộc dev VÀ không bảo vệ
        if not args.keep_videos and not is_dev and not keep_mp4_due_to_offset and is_valid:
            os.remove(str(v_path))
            print(f"Đã xóa {v_path} an toàn.")
        else:
            reason = "thuộc dev_videos" if is_dev else "theo cấu hình"
            if keep_mp4_due_to_offset:
                reason = "BẢO VỆ DO LỖI OFFSET / CHƯA CHẮC CHẮN"
            if not is_valid:
                reason = "KHÔNG HỢP LỆ (lỗi audio/shot/keyframe)"
            print(f"Giữ lại video {v_path} ({reason}).")
    else:
        print(f"Xử lý {video_id} THẤT BẠI. Không xóa video gốc.")

if __name__ == "__main__":
    main()
