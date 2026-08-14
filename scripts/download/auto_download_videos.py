import os
import csv
import urllib.request
import zipfile
import subprocess
from pathlib import Path
from tqdm import tqdm
import requests
import json

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
DERIVED_DIR = DATA_DIR / "derived"
ZIPS_DIR = RAW_DIR / "zips"
VIDEOS_DIR = RAW_DIR / "videos"
INFO_PATH = DERIVED_DIR / "video_info.parquet"
TEMP_METADATA = DERIVED_DIR / "real_metadata_temp.json"

ZIPS_DIR.mkdir(parents=True, exist_ok=True)
VIDEOS_DIR.mkdir(parents=True, exist_ok=True)

SHEET_URL = "https://docs.google.com/spreadsheets/d/1rfn1fieTThS_Ki3SIoJ6uXOx2AhMq7wGCak6W4jZyZM/export?format=csv&gid=0"

# Giữ lại 20 video L21_V001 -> L21_V020 để phục vụ test mắt L3
KEEP_VIDEOS = [f"L21_V{str(i).zfill(3)}" for i in range(1, 21)] 

def download_file(url, output_path):
    print(f"\n⬇️ Đang tải: {output_path.name}")
    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}
    
    # Dùng stream=True để tải file lớn mà không bị tràn RAM
    response = requests.get(url, headers=headers, stream=True)
    response.raise_for_status() # Quăng lỗi nếu vẫn bị chặn (403, 404...)
    
    total_size = int(response.headers.get('content-length', 0))
    
    with open(output_path, 'wb') as file, tqdm(
        desc=output_path.name,
        total=total_size,
        unit='B',
        unit_scale=True,
        unit_divisor=1024,
    ) as bar:
        for data in response.iter_content(chunk_size=1024*1024):
            size = file.write(data)
            bar.update(size)

def extract_zip(zip_path, extract_to):
    print(f"\n📦 Đang giải nén: {zip_path.name}")
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        # Danh sách file trong zip
        members = zip_ref.namelist()
        for member in tqdm(members, desc="Giải nén"):
            zip_ref.extract(member, extract_to)

def get_real_metadata_sync(mp4_path):
    try:
        cmd = [
            "ffprobe", "-v", "error", 
            "-select_streams", "v:0",
            "-count_frames", 
            "-show_entries", "stream=r_frame_rate,nb_read_frames,duration,width,height",
            "-of", "csv=p=0", 
            str(mp4_path)
        ]
        
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True).strip()
        parts = output.split(",")
        if len(parts) >= 5:
            width = int(parts[0])
            height = int(parts[1])
            fps_str = parts[2]
            duration_s = float(parts[3])
            n_frames = int(parts[4])
            
            if "/" in fps_str:
                fps_num, fps_den = map(int, fps_str.split("/"))
            else:
                fps_num = int(float(fps_str))
                fps_den = 1
                
            return {
                "fps_num": fps_num,
                "fps_den": fps_den,
                "n_frames": n_frames,
                "duration_s": duration_s,
                "width": width,
                "height": height
            }, None
        else:
            return None, f"Lỗi output không chuẩn: {output}"
            
    except Exception as e:
        return None, f"Lỗi đếm frame vật lý {mp4_path.name}: {e}"

def process_and_clean_videos():
    results = {}
    if TEMP_METADATA.exists():
        with open(TEMP_METADATA, "r") as f:
            results = json.load(f)
            
    mp4_files = list(VIDEOS_DIR.rglob("*.mp4"))
    if not mp4_files:
        return
        
    print(f"\n🔎 Đang soi cấu trúc vật lý của {len(mp4_files)} video...")
    
    for mp4_path in tqdm(mp4_files, desc="Quét FFprobe"):
        vid = mp4_path.stem
        if vid not in results:
            res, err = get_real_metadata_sync(mp4_path)
            if res:
                results[vid] = res
            else:
                print(err)
                
        # DỌN RÁC NGAY LẬP TỨC: Xoá video MP4 để nhả RAM và Disk
        if vid not in KEEP_VIDEOS:
            os.remove(mp4_path)
            
    with open(TEMP_METADATA, "w") as f:
        json.dump(results, f)

def main():
    print("🚀 Bắt đầu kiến trúc Cuốn chiếu (Rolling Pipeline) - Chống tràn ổ đĩa")
    
    csv_path = ZIPS_DIR / "links.csv"
    req = urllib.request.Request(SHEET_URL, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as response, open(csv_path, 'wb') as out_file:
        out_file.write(response.read())
        
    video_links = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            filename = row.get("Filenames", "")
            link = row.get("Download link", "")
            if filename.startswith("Videos_") and filename.endswith(".zip") and link:
                video_links.append((filename, link))
                
    print(f"✅ Đã nhận lệnh tải {len(video_links)} cục ZIP khổng lồ.")
    
    for filename, link in video_links:
        zip_path = ZIPS_DIR / filename
        
        # 1. Kiểm tra và tải
        needs_download = True
        if zip_path.exists():
            if zipfile.is_zipfile(zip_path):
                print(f"\n✅ Cục {filename} đã tải hoàn chỉnh và nằm sẵn trên đĩa.")
                needs_download = False
            else:
                print(f"\n⚠️ Cục {filename} bị hỏng (có thể do lúc nãy Đội trưởng bấm Ctrl+C ngắt ngang). Đang tự động xoá để tải lại...")
                os.remove(zip_path)
                
        if needs_download:
            try:
                download_file(link, zip_path)
            except Exception as e:
                print(f"❌ Lỗi khi tải {filename}: {e}")
                if zip_path.exists():
                    os.remove(zip_path)
                continue
            
        # 2. Giải nén
        extract_zip(zip_path, VIDEOS_DIR)
        
        # 3. FFprobe + Dọn MP4
        process_and_clean_videos()
        
        # 4. Dọn ZIP
        print(f"🗑️ Tiêu huỷ xác file nén {filename} để nhả 100% dung lượng.")
        if zip_path.exists():
            os.remove(zip_path)
        
    print("\n5️⃣ Lắp ráp linh kiện Metadata cuối cùng vào video_info.parquet...")
    import pandas as pd
    
    with open(TEMP_METADATA, "r") as f:
        results = json.load(f)
        
    records = []
    for vid, r in results.items():
        records.append({
            "video_id": vid,
            "fps_num": r.get("fps_num", 0),
            "fps_den": r.get("fps_den", 1),
            "n_frames": r.get("n_frames", 0),
            "duration_s": r.get("duration_s", 0.0),
            "width": r.get("width", 0),
            "height": r.get("height", 0)
        })
        
    if records:
        df = pd.DataFrame(records)
        df.to_parquet(DATA_DIR / "derived/video_info.parquet", index=False)
        print("✅ Dữ liệu TRUNG THỰC đã được chốt hạ vào data/derived/video_info.parquet!")
    else:
        print("⚠️ Không có dữ liệu để xuất Parquet.")
        
    print("\n🎉 HOÀN TẤT CHIẾN DỊCH TẢI VÀ ĐẾM FRAME.")
    
    print("\n6️⃣ Ra toà án binh: Khởi động Audit L1...")
    subprocess.run(["python", "-m", "scripts.audit.b01_mapping_check"], cwd=str(ROOT_DIR))
    print("\n🎉 CHIẾN DỊCH HOÀN TẤT THẮNG LỢI!")

if __name__ == "__main__":
    main()
