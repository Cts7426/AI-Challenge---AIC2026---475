"""
B1.1 — Công cụ kiểm tra shot bằng mắt (Contact Sheet).

Nhận video_id, đọc shots_parts/<video_id>.parquet,
trích frame đầu + cuối mỗi shot bằng extract_frame_exact(),
ghép contact sheet, xuất reports/shot_preview/<video_id>.jpg.

Mỗi shot 1 hàng: [frame đầu | frame cuối]
Nhãn: shot_seq, start_frame, end_frame, duration_s, is_force_split
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

# Phải chạy từ thư mục preprocessing/ hoặc thêm vào sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "preprocessing"))

from common.decode import extract_frame_exact

SHOTS_PARTS_DIR = ROOT_DIR / "data" / "derived" / "shots_parts"
PREVIEW_DIR = ROOT_DIR / "reports" / "shot_preview"


def make_contact_sheet(video_id: str, video_path: str,
                       df_shots: pd.DataFrame,
                       output_path: Path,
                       thumb_w: int = 320, thumb_h: int = 180,
                       max_shots_per_sheet: int = 150):
    n_shots = len(df_shots)
    if n_shots == 0:
        print(f"  {video_id}: 0 shot, bỏ qua")
        return

    # Kích thước: hỗ trợ tối đa 5 thumbnail cạnh nhau (đầu, 25, 50, 75, cuối)
    label_w = 280
    row_h = thumb_h + 10  # padding
    img_w = label_w + thumb_w * 5 + 50

    try:
        font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 12)
        font_header = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 14)
    except Exception:
        font = ImageFont.load_default()
        font_header = font

    for part_idx in range(0, n_shots, max_shots_per_sheet):
        df_part = df_shots.iloc[part_idx:part_idx + max_shots_per_sheet]
        n_part_shots = len(df_part)
        
        img_h = 40 + n_part_shots * row_h
        sheet = Image.new("RGB", (img_w, img_h), (30, 30, 30))
        draw = ImageDraw.Draw(sheet)

        # Header
        part_str = f" (Part {part_idx//max_shots_per_sheet + 1})" if n_shots > max_shots_per_sheet else ""
        draw.text((10, 10),
                  f"{video_id}{part_str}  |  {n_shots} shots total  |  threshold=27  downscale=2",
                  fill=(255, 255, 100), font=font_header)

        y = 40
        for _, row in df_part.iterrows():
            seq = int(row["shot_seq"])
            start_f = int(row["start_frame"])
            end_f = int(row["end_frame"])
            dur = float(row["duration_s"])
            is_fs = bool(row["is_force_split"])
            n_merged = int(row.get("n_raw_shots_merged", 1))

            # Nhãn
            fs_tag = " ✂️FORCE" if is_fs else ""
            mg_tag = f" 🔗x{n_merged}" if n_merged > 1 else ""
            label = (f"s{seq:04d}\n"
                     f"  {start_f}-{end_f}\n"
                     f"  {dur:.1f}s{fs_tag}{mg_tag}")

            color = (255, 100, 100) if is_fs else (200, 200, 200)
            draw.text((5, y + 5), label, fill=color, font=font)
            
            # Khung trích xuất
            # Mặc định: trích frame đầu và cuối
            frames_to_extract = [(start_f, 0), (end_f, 1)] # (frame_idx, vị trí cột)
            
            # Nếu > 10s và KHÔNG phải force_split, trích thêm 25%, 50%, 75%
            # (force_split là cắt cứng, không quan trọng vụ chuyển cảnh sót bằng cảnh tự nhiên dài)
            if dur > 10.0 and not is_fs:
                p25 = start_f + int((end_f - start_f) * 0.25)
                p50 = start_f + int((end_f - start_f) * 0.50)
                p75 = start_f + int((end_f - start_f) * 0.75)
                frames_to_extract = [
                    (start_f, 0), (p25, 1), (p50, 2), (p75, 3), (end_f, 4)
                ]
            elif dur > 10.0 and is_fs:
                # Nếu là force_split thì vẫn để 2 thumbnail, giãn ra 2 đầu cho dễ nhìn
                frames_to_extract = [(start_f, 0), (end_f, 4)]
            else:
                # Ngắn thì để cạnh nhau
                frames_to_extract = [(start_f, 0), (end_f, 1)]

            for f_idx, col_idx in frames_to_extract:
                try:
                    frame = extract_frame_exact(video_path, f_idx)
                    if frame is not None:
                        img_thumb = Image.fromarray(frame).resize((thumb_w, thumb_h))
                        x_pos = label_w + col_idx * (thumb_w + 10)
                        sheet.paste(img_thumb, (x_pos, y))
                except Exception as e:
                    x_pos = label_w + col_idx * (thumb_w + 10) + 10
                    draw.text((x_pos, y + thumb_h // 2), f"ERR: {e}", fill=(255, 0, 0), font=font)

            draw.line([(0, y + row_h - 2), (img_w, y + row_h - 2)],
                      fill=(60, 60, 60), width=1)
            y += row_h

        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Suffix part name if chunked
        out_file = output_path
        if n_shots > max_shots_per_sheet:
            out_file = output_path.with_name(f"{output_path.stem}_pt{part_idx//max_shots_per_sheet + 1}{output_path.suffix}")
            
        sheet.save(str(out_file), "JPEG", quality=85)
        print(f"  ✅ {out_file.name} ({n_part_shots} shots, {img_w}x{img_h}px)")


def main():
    parser = argparse.ArgumentParser(description="Preview shots — contact sheet")
    parser.add_argument("--video-ids", nargs="+", required=True,
                        help="Danh sách video_id cần preview")
    args = parser.parse_args()

    # Load video_info để lấy đường dẫn
    vi_path = ROOT_DIR / "data" / "derived" / "video_info.parquet"
    df_vi = pd.read_parquet(vi_path)

    for vid in args.video_ids:
        part_path = SHOTS_PARTS_DIR / f"{vid}.parquet"
        if not part_path.exists():
            print(f"❌ {vid}: chưa có shots_parts. Chạy shot_job.py trước.")
            continue

        # Lấy đường dẫn video
        res = df_vi[df_vi["video_id"] == vid]
        if len(res) == 0:
            found = list((ROOT_DIR / "data" / "raw" / "videos").rglob(f"{vid}.mp4"))
            if not found:
                print(f"❌ {vid}: không tìm thấy trong video_info và không thấy trên đĩa")
                continue
            vpath = str(found[0])
        else:
            vpath = str(ROOT_DIR / res.iloc[0]["path"])
        
        if not Path(vpath).exists():
            print(f"❌ {vid}: file .mp4 không tồn tại: {vpath}")
            continue

        df_shots = pd.read_parquet(part_path).sort_values("shot_seq")
        out_path = PREVIEW_DIR / f"{vid}.jpg"

        print(f"\n🎬 {vid}: {len(df_shots)} shots")
        make_contact_sheet(vid, vpath, df_shots, out_path)


if __name__ == "__main__":
    main()
