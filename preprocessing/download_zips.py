import os
import sys
import json
import argparse
import hashlib
import shutil
import urllib.request
import re
from pathlib import Path
from datetime import datetime

try:
    import pandas as pd
    import requests
    from tqdm import tqdm
except ImportError:
    print("Vui lòng cài đặt các thư viện: pip install pandas requests tqdm")
    sys.exit(1)

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
ZIPS_DIR = DATA_DIR / "raw" / "zips"
MANIFEST_PATH = DATA_DIR / "manifests" / "download.json"

CSV_URL = "https://docs.google.com/spreadsheets/d/1rfn1fieTThS_Ki3SIoJ6uXOx2AhMq7wGCak6W4jZyZM/export?format=csv&gid=0"

def get_remote_file_size(url: str) -> int:
    """Lấy dung lượng file từ remote qua HTTP HEAD"""
    try:
        response = requests.head(url, allow_redirects=True, timeout=10)
        if response.status_code == 200 and 'content-length' in response.headers:
            return int(response.headers['content-length'])
    except Exception as e:
        pass
    return 0

def check_disk_space(required_bytes=0):
    """Báo lỗi nếu ổ cứng dưới 60GB"""
    # Nếu chưa có ổ đĩa/thư mục cha, đệ quy tìm thư mục tồn tại gần nhất để check
    check_dir = ZIPS_DIR
    while not check_dir.exists() and check_dir != check_dir.parent:
        check_dir = check_dir.parent
        
    free_bytes = shutil.disk_usage(check_dir).free
    MIN_FREE = 60 * 1024**3 # 60 GB
    
    # Cộng thêm required_bytes dự trù cho file đang chuẩn bị tải
    if free_bytes - required_bytes < MIN_FREE:
        print(f"\n[NGUY HIỂM] Đĩa chỉ còn {free_bytes/1024**3:.2f} GB trống, dưới mức an toàn 60 GB!")
        print("Dừng toàn bộ tiến trình tải để tránh sập hệ thống.")
        sys.exit(1)

def extract_prefix(filename: str):
    match = re.search(r'(L\d{2})', filename)
    if match:
        return match.group(1)
    return "UNKNOWN"

def download_file(url: str, dest_path: Path, expected_size: int = 0):
    """Tải file với tính năng Resume và Thanh tiến độ"""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = dest_path.with_suffix('.zip.part')
    
    headers = {}
    downloaded_bytes = 0
    
    if temp_path.exists():
        downloaded_bytes = temp_path.stat().st_size
        headers['Range'] = f'bytes={downloaded_bytes}-'
        print(f"Resume {dest_path.name} từ {downloaded_bytes / 1024**2:.1f} MB...")
    else:
        print(f"Bắt đầu tải {dest_path.name}...")

    try:
        response = requests.get(url, headers=headers, stream=True, allow_redirects=True, timeout=15)
    except requests.exceptions.RequestException as e:
        print(f"Lỗi mạng khi tải {url}: {e}")
        return False
        
    # Nếu server không hỗ trợ Partial Content (206) thì tải lại từ đầu
    if response.status_code == 200:
        downloaded_bytes = 0
        mode = 'wb'
    elif response.status_code == 206:
        mode = 'ab'
    else:
        print(f"Lỗi tải file {url}: HTTP {response.status_code}")
        return False
        
    total_size = int(response.headers.get('content-length', 0)) + downloaded_bytes
    if expected_size > 0 and total_size != expected_size and total_size > 0:
        print(f"Cảnh báo: Kích thước file trên mạng ({total_size}) khác khai báo ({expected_size})")

    check_disk_space(total_size - downloaded_bytes)

    try:
        with open(temp_path, mode) as f, tqdm(
            desc=dest_path.name,
            initial=downloaded_bytes,
            total=total_size,
            unit='B',
            unit_scale=True,
            unit_divisor=1024,
        ) as bar:
            for chunk in response.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
                    bar.update(len(chunk))
    except Exception as e:
        print(f"\n[LỖI] Đứt kết nối hoặc lỗi ghi đĩa: {e}")
        return False
                
    # Sau khi tải xong, đổi tên file part thành file thật
    if temp_path.exists():
        final_size = temp_path.stat().st_size
        # Nếu expected size tồn tại và file khác size, có thể lỗi đứt mạng.
        if total_size > 0 and final_size < total_size:
            print(f"\n[LỖI] {dest_path.name} tải chưa hoàn tất ({final_size}/{total_size}). Sẽ resume vào lần sau.")
            return False
            
        temp_path.rename(dest_path)
        return True
    return False

def is_already_extracted(zip_name: str) -> bool:
    """Kiểm tra xem file zip đã được giải nén thành folder chưa để không tải lại"""
    stem = zip_name.replace('.zip', '').lower()
    stem_no_us = stem.replace('_', '')
    
    # 1. Check folder Videos
    if (DATA_DIR / "raw" / "videos").exists():
        for d in (DATA_DIR / "raw" / "videos").glob("*"):
            if d.is_dir() and d.name.lower().replace('_', '') == stem_no_us:
                return True
                
    # 2. Check folder Keyframes
    if (DATA_DIR / "raw" / "btc" / "keyframes").exists():
        for d in (DATA_DIR / "raw" / "btc" / "keyframes").glob("*"):
            if d.is_dir() and d.name.lower().replace('_', '') == stem_no_us:
                return True
                
    # 3. Check các file meta khác
    if 'objects' in stem:
        return (DATA_DIR / "raw" / "btc" / "objects").exists()
    if 'clip-features' in stem:
        return (DATA_DIR / "raw" / "btc" / "clip-features-32").exists()
    if 'map-keyframes' in stem:
        return (DATA_DIR / "raw" / "btc" / "metadata" / "media-info" / "map-keyframes").exists()
    if 'media-info' in stem:
        return (DATA_DIR / "raw" / "btc" / "metadata" / "media-info").exists()
        
    return False

def main():
    parser = argparse.ArgumentParser(description="Tải các ZIP từ nguồn BTC")
    parser.add_argument("--execute", action="store_true", help="Chạy tải thực sự thay vì in báo cáo")
    parser.add_argument("--shard", type=int, default=0, help="ID shard hiện tại")
    parser.add_argument("--num-shards", type=int, default=1, help="Tổng số shard (người tải)")
    args = parser.parse_args()

    ZIPS_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)

    print("Đang đọc danh sách từ Google Sheets...")
    try:
        df = pd.read_csv(CSV_URL)
        df.dropna(subset=['Filenames', 'Download link'], inplace=True)
    except Exception as e:
        print(f"Không thể đọc Google Sheets: {e}")
        return

    print("Đang lấy thông tin dung lượng các file từ server (HTTP HEAD)...")
    remote_files = []
    total_remote_size = 0
    
    # Lấy thông tin dung lượng remote
    for _, row in tqdm(df.iterrows(), total=len(df), desc="Fetching metadata"):
        fname = row['Filenames'].strip()
        link = row['Download link'].strip()
        # Bỏ qua các file không phải zip
        if not fname.endswith('.zip'):
            continue
            
        prefix = extract_prefix(fname)
        size = get_remote_file_size(link)
        total_remote_size += size
        
        remote_files.append({
            'name': fname,
            'url': link,
            'size': size,
            'prefix': prefix
        })

    # Lấy thông tin file local (file .zip)
    existing_zips = {f.name for f in ZIPS_DIR.glob("*.zip")}
    
    # So sánh
    missing_files = []
    total_missing_size = 0
    extracted_count = 0
    out_of_range_prefixes = set()
    
    valid_prefixes = {f"L{i}" for i in range(21, 31)}
    
    for f in remote_files:
        if f['prefix'] not in valid_prefixes and f['prefix'] != "UNKNOWN":
            out_of_range_prefixes.add(f['prefix'])
            
        # Kiểm tra file zip đã tải hoặc thư mục đã giải nén
        if f['name'] in existing_zips:
            continue
        elif is_already_extracted(f['name']):
            extracted_count += 1
            continue
        else:
            missing_files.append(f)
            total_missing_size += f['size']

    # IN BÁO CÁO
    print("\n" + "="*50)
    print(" BÁO CÁO TRƯỚC KHI TẢI (DRY RUN)")
    print("="*50)
    print(f"Tổng số ZIP trên nguồn: {len(remote_files)} file ({total_remote_size / 1024**3:.2f} GB)")
    print(f"Tổng số ZIP/Thư mục đã có sẵn trên máy: {len(existing_zips) + extracted_count} file (Đã giải nén: {extracted_count})")
    print(f"Tổng số ZIP CÒN THIẾU: {len(missing_files)} file ({total_missing_size / 1024**3:.2f} GB cần tải)")
    
    if missing_files:
        print("\n--- CHI TIẾT CÁC FILE CẦN TẢI ---")
        for idx, f in enumerate(missing_files, 1):
            print(f"{idx:2d}. {f['name']:<30} | {f['size'] / 1024**3:5.2f} GB")
    
    if out_of_range_prefixes:
        print("\n[CẢNH BÁO ĐỎ] Phát hiện ZIP có prefix ngoài dải L21-L30!")
        print(f"Các prefix ngoài dải: {out_of_range_prefixes}")
        print("Điều này có nghĩa kho dữ liệu BTC đã có thêm video mà bạn chưa có metadata JSON.")
        
    if not args.execute:
        print("\n=> Chạy với cờ `--execute` để tiến hành tải.")
        return

    # THỰC THI TẢI
    print("\n" + "="*50)
    print(f" BẮT ĐẦU TẢI (Shard {args.shard}/{args.num_shards})")
    print("="*50)
    
    # Load manifest
    manifest = {}
    if MANIFEST_PATH.exists():
        try:
            with open(MANIFEST_PATH, 'r', encoding='utf-8') as f:
                manifest = json.load(f)
        except:
            pass

    # Lọc theo shard
    shard_files = []
    for f in missing_files:
        md5_hash = int(hashlib.md5(f['name'].encode()).hexdigest(), 16)
        if md5_hash % args.num_shards == args.shard:
            shard_files.append(f)
            
    print(f"Shard {args.shard} chịu trách nhiệm tải {len(shard_files)} file còn thiếu.")
    
    for idx, f in enumerate(shard_files, 1):
        # Nếu đã ghi nhận trong manifest và file thực sự tồn tại hợp lệ thì bỏ qua
        if f['name'] in manifest and (ZIPS_DIR / f['name']).exists():
            print(f"[{idx}/{len(shard_files)}] Bỏ qua {f['name']} (Đã hoàn thành)")
            continue
            
        print(f"\n[{idx}/{len(shard_files)}] Đang xử lý: {f['name']}")
        dest_path = ZIPS_DIR / f['name']
        
        success = download_file(f['url'], dest_path, f['size'])
        if success:
            manifest[f['name']] = {
                "size_bytes": dest_path.stat().st_size,
                "downloaded_at": datetime.now().isoformat()
            }
            # Ghi lại manifest ngay sau mỗi file
            with open(MANIFEST_PATH, 'w', encoding='utf-8') as mf:
                json.dump(manifest, mf, indent=4, ensure_ascii=False)
            print(f"[OK] Đã hoàn thành tải {f['name']}")
        else:
            print(f"[FAIL] Tải thất bại hoặc bị ngắt: {f['name']}")

if __name__ == "__main__":
    main()
