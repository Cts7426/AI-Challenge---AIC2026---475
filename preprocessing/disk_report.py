import os
import glob
import shutil
import statistics
import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"

def format_size(bytes_size):
    if bytes_size == 0:
        return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0

def get_dir_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    for p in path.rglob("*"):
        if p.is_file():
            total += p.stat().st_size
    return total

def get_metadata_total_duration() -> float:
    """Trả về tổng thời lượng video (tính bằng giờ) dựa trên các file JSON trong media-info"""
    media_info_dir = DATA_DIR / "raw" / "btc" / "metadata" / "media-info"
    total_seconds = 0.0
    if media_info_dir.exists():
        json_files = list(media_info_dir.rglob("*.json"))
        for j_path in json_files:
            try:
                with open(j_path, 'r', encoding='utf-8') as f:
                    info = json.load(f)
                    total_seconds += float(info.get("length", 0.0))
            except Exception:
                pass
    return total_seconds / 3600.0

def main():
    print("=" * 50)
    print(" BÁO CÁO DUNG LƯỢNG Ổ ĐĨA & TÀI NGUYÊN")
    print("=" * 50)
    
    # 1. Các file ZIP
    raw_dir = DATA_DIR / "raw"
    zip_files = list(raw_dir.rglob("*.zip"))
    zip_sizes = [z.stat().st_size for z in zip_files]
    total_zip_size = sum(zip_sizes)
    
    print(f"\n[1] File ZIP Video đã tải:")
    print(f"  - Số lượng: {len(zip_files)} file")
    print(f"  - Tổng dung lượng: {format_size(total_zip_size)}")
    if zip_sizes:
        print(f"  - ZIP Lớn nhất: {format_size(max(zip_sizes))}")
        print(f"  - ZIP Nhỏ nhất: {format_size(min(zip_sizes))}")
        print(f"  - ZIP Trung vị: {format_size(statistics.median(zip_sizes))}")
    else:
        print("  - Không tìm thấy file .zip nào.")

    # 2. Dung lượng đã giải nén
    mp4_files = list(raw_dir.rglob("*.mp4"))
    total_mp4_size = sum(m.stat().st_size for m in mp4_files)
    print(f"\n[2] Video MP4 đã giải nén:")
    print(f"  - Số lượng: {len(mp4_files)} file")
    print(f"  - Tổng dung lượng: {format_size(total_mp4_size)}")

    # 3. Dung lượng dữ liệu BTC (Keyframe, Meta, Objects...)
    btc_dir = DATA_DIR / "raw" / "btc"
    kf_size = get_dir_size(btc_dir / "keyframes")
    meta_size = get_dir_size(btc_dir / "metadata")
    obj_size = get_dir_size(btc_dir / "objects")
    clip_size = get_dir_size(btc_dir / "clip_b32.npy")
    # Nếu file clip có tên khác hoặc nằm thư mục gốc thì rglob
    if clip_size == 0:
        clip_files = list(btc_dir.rglob("*clip*.npy"))
        clip_size = sum(f.stat().st_size for f in clip_files)

    print(f"\n[3] Dung lượng dữ liệu phụ trợ (BTC):")
    print(f"  - Keyframes BTC: {format_size(kf_size)}")
    print(f"  - Metadata:      {format_size(meta_size)}")
    print(f"  - Objects:       {format_size(obj_size)}")
    print(f"  - CLIP (B/32):   {format_size(clip_size)}")

    # 4. Trống ổ đĩa
    total, used, free = shutil.disk_usage("/")
    print(f"\n[4] Trạng thái Ổ đĩa hệ thống:")
    print(f"  - Dung lượng trống: {format_size(free)}")
    print(f"  - Đang sử dụng:     {format_size(used)} / {format_size(total)}")

    # 5. Ước lượng giải nén
    print(f"\n[5] Ước lượng rủi ro nếu giải nén toàn bộ ZIP:")
    # Giả sử tỷ lệ giải nén là 1:1 so với dung lượng ZIP (mp4 nén khó nhỏ hơn được nữa)
    if total_zip_size > 0:
        needed_space = total_zip_size * 1.05 # +5% overhead
        print(f"  - Cần thêm khoảng: {format_size(needed_space)}")
        if free > needed_space + 50 * 1024**3: # Yêu cầu an toàn dư 50GB
            print("  - ĐÁNH GIÁ: Đủ không gian để giải nén (có dư dả).")
        else:
            print("  - ĐÁNH GIÁ: NGUY HIỂM! Không đủ không gian an toàn (thiếu hoặc sát nút). Nên dùng rolling_ingest.")
    else:
        print("  - Không có file ZIP, chưa thể ước lượng.")

    # 6. Ước lượng sản phẩm sau xử lý
    total_hours = get_metadata_total_duration()
    print(f"\n[6] Ước lượng sản phẩm đầu ra (Derived Data):")
    if total_hours > 0:
        print(f"  - Tổng thời lượng video ước tính: {total_hours:.2f} giờ")
        
        # Audio: ~115 MB / giờ
        est_audio_mb = total_hours * 115
        print(f"  - Ước tính Audio (WAV 16k mono): {format_size(est_audio_mb * 1024**2)}")
        
        # Keyframe: 40KB/ảnh. Mật độ mục tiêu 1 fps (3600 ảnh / giờ)
        # Bù trừ cho số shot quá ngắn làm ảnh hưởng mật độ, cứ tạm lấy ~3600 ảnh / giờ
        est_kf_count = total_hours * 3600
        est_kf_mb = (est_kf_count * 40) / 1024
        print(f"  - Ước tính Keyframes (1 fps, 40KB/ảnh): {format_size(est_kf_mb * 1024**2)} (~{int(est_kf_count):,} ảnh)")
        
        total_est = (est_audio_mb + est_kf_mb) * 1024**2
        print(f"  - TỔNG DUNG LƯỢNG SẼ SINH RA: {format_size(total_est)}")
    else:
        print("  - Không tìm thấy JSON metadata hợp lệ để tính toán thời lượng.")

if __name__ == "__main__":
    main()
