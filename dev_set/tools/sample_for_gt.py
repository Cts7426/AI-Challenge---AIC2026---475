# dev_set/tools/sample_for_gt.py — E4.1: lấy mẫu video "mù" để người gán nhãn viết query
#
# VÌ SAO "MÙ": người viết query trong dự án này CŨNG LÀ người viết code retrieval
# (CLAUDE.md), nên rủi ro thiên lệch lớn nhất không phải là "lỡ đọc OCR/ASR" mà là
# TRÍ NHỚ — họ đã nhìn kết quả search hàng tuần, tự nhiên nhớ video nào "ăn điểm".
# Chặn truy cập DB không chặn được trí nhớ đó — chỉ có cách CƠ HỌC (tên file không
# lộ video/thời điểm, mapping thật nằm tách biệt) mới chặn được. Script này KHÔNG
# đọc Milvus/Elasticsearch/OCR/ASR — chỉ đọc file .mp4 gốc + shots.parquet (ranh
# giới cảnh, không phải nội dung ngữ nghĩa) để cắt khỏi bị dính cắt cảnh.
#
# Đầu ra CHỦ ĐÍCH tách làm hai, không bao giờ gộp:
#   dev_set/gt_staging/clips/*.mp4              — AN TOÀN, gửi cho người gán nhãn
#   dev_set/gt_staging/annotation_template.jsonl — AN TOÀN, người gán nhãn điền vào đây
#   dev_set/gt_staging/_secret_mapping.jsonl     — clip_id → video_id/frame thật.
#                                                   KHÔNG MỞ trước khi gán nhãn xong.
#
# TRAKE dùng cửa sổ DÀI HƠN và bắt buộc trải qua ≥2 shot thật (không phải cắt ngẫu
# nhiên một khoảng dài): GroundTruthTRAKE (schema.py) từ chối các cửa sổ khoảnh khắc
# chồng lấn, nên nếu clip chỉ chứa 1 khoảnh khắc thật, người gán nhãn sẽ bịa ra một
# quỹ đạo không có trong clip — sai ngay từ khâu lấy mẫu.
#
# Bước tiếp theo (E4.2, KHÔNG nằm trong file này): một script "reveal" đọc
# annotation_template.jsonl + _secret_mapping.jsonl, ghép theo clip_id, sinh ra
# dev_set/queries/*.jsonl và dev_set/ground_truth/*.jsonl đúng schema.py.

from __future__ import annotations

import argparse
import json
import random
import secrets
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

from backend.export import all_video_ids, n_frames_of

REPO_ROOT = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------- probing

@dataclass(frozen=True)
class VideoProbe:
    """fps/duration THẬT của một file .mp4, đọc bằng ffprobe — không suy diễn
    từ n_frames_of() vì fps có thể là số phân số (29.97, không phải 30) và
    n_frames_of() không cho fps, chỉ cho tổng số frame."""

    duration_sec: float
    fps: float


def _parse_rate(s: str) -> float:
    """ffprobe trả frame rate dạng 'num/den' (vd '30000/1001')."""
    if not s or s == "0/0":
        return 0.0
    if "/" in s:
        num, den = s.split("/")
        den_f = float(den)
        return float(num) / den_f if den_f else 0.0
    return float(s)


def probe_video(path: Path) -> VideoProbe | None:
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=r_frame_rate,avg_frame_rate:format=duration",
        "-of", "json", str(path),
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30).stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return None
    try:
        data = json.loads(out)
        duration = float(data["format"]["duration"])
        stream = data["streams"][0]
        fps = _parse_rate(stream.get("avg_frame_rate", "")) or _parse_rate(stream.get("r_frame_rate", ""))
    except (KeyError, IndexError, ValueError, TypeError):
        return None
    if duration <= 0 or fps <= 0:
        return None
    return VideoProbe(duration_sec=duration, fps=fps)


def is_degenerate_frame(video_path: Path, at_sec: float, min_std: float) -> bool:
    """True nếu frame ở giữa cửa sổ gần như trơn màu — slate/màn đen/chuyển cảnh
    fade. Không đáng để người gán nhãn xem, và không mô tả được gì."""
    cap = cv2.VideoCapture(str(video_path))
    cap.set(cv2.CAP_PROP_POS_MSEC, at_sec * 1000)
    ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        return True
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return float(np.std(gray)) < min_std


# --------------------------------------------------------------------- shots

def load_shots_table(shots_path: Path) -> pd.DataFrame | None:
    if not shots_path.exists():
        print(f"CẢNH BÁO: không thấy {shots_path} — lấy mẫu KHÔNG né được điểm cắt cảnh.")
        return None
    return pd.read_parquet(shots_path)


def shots_of(shots_df: pd.DataFrame | None, video_id: str) -> list[tuple[int, int]]:
    if shots_df is None:
        return []
    sub = shots_df[shots_df["video_id"] == video_id].sort_values("start_frame")
    return list(zip(sub["start_frame"].tolist(), sub["end_frame"].tolist()))


# --------------------------------------------------------------------- windowing

def pick_single_moment_window(
    rng: random.Random, probe: VideoProbe, shots: list[tuple[int, int]],
    n_frames: int, clip_range: tuple[float, float], edge_margin_frac: float,
) -> tuple[int, int] | None:
    """KIS/QA: một cửa sổ NẰM TRỌN trong một shot — không dính cắt cảnh."""
    lo, hi = clip_range
    margin = int(n_frames * edge_margin_frac)

    if shots:
        candidates = [
            (s, e) for s, e in shots
            if s >= margin and e <= n_frames - margin and (e - s + 1) / probe.fps >= lo
        ]
        if candidates:
            s, e = rng.choice(candidates)
            shot_len_sec = (e - s + 1) / probe.fps
            clip_len_sec = rng.uniform(lo, min(hi, shot_len_sec))
            clip_len_frames = max(1, round(clip_len_sec * probe.fps))
            max_start = max(s, e - clip_len_frames + 1)
            start = rng.randint(s, max_start)
            end = min(e, start + clip_len_frames - 1)
            return start, end

    # Không có shots.parquet (hoặc video không có shot đủ dài) → random thuần,
    # không đảm bảo tránh cắt cảnh — chấp nhận đánh đổi để vẫn ra được mẫu.
    clip_len_sec = rng.uniform(lo, hi)
    clip_len_frames = max(1, round(clip_len_sec * probe.fps))
    lo_frame, hi_frame = margin, n_frames - margin - clip_len_frames
    if hi_frame <= lo_frame:
        return None
    start = rng.randint(lo_frame, hi_frame)
    return start, start + clip_len_frames - 1


def pick_trake_window(
    rng: random.Random, probe: VideoProbe, shots: list[tuple[int, int]],
    n_frames: int, clip_range: tuple[float, float], edge_margin_frac: float,
) -> tuple[int, int] | None:
    """TRAKE: một cửa sổ trải qua ÍT NHẤT 2 shot thật — để clip thật sự chứa
    nhiều hơn một khoảnh khắc, người gán nhãn không phải bịa quỹ đạo."""
    lo, hi = clip_range
    margin = int(n_frames * edge_margin_frac)

    if len(shots) >= 2:
        runs: list[tuple[int, int]] = []
        for i in range(len(shots)):
            start_f = shots[i][0]
            if start_f < margin:
                continue
            for j in range(i + 1, len(shots)):
                end_f = shots[j][1]
                if end_f > n_frames - margin:
                    break
                dur_sec = (end_f - start_f + 1) / probe.fps
                if dur_sec > hi:
                    break
                if dur_sec >= lo:
                    runs.append((start_f, end_f))
        if runs:
            return rng.choice(runs)

    print("  CẢNH BÁO: không ghép được ≥2 shot cho TRAKE trong video này — "
          "cắt một khoảng dài ngẫu nhiên, KHÔNG đảm bảo nhiều khoảnh khắc tách biệt.")
    clip_len_sec = rng.uniform(lo, hi)
    clip_len_frames = max(1, round(clip_len_sec * probe.fps))
    lo_frame, hi_frame = margin, n_frames - margin - clip_len_frames
    if hi_frame <= lo_frame:
        return None
    start = rng.randint(lo_frame, hi_frame)
    return start, start + clip_len_frames - 1


# --------------------------------------------------------------------- extraction

def extract_clip(video_path: Path, start_sec: float, end_sec: float, out_path: Path) -> bool:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(video_path),
        # -ss/-to SAU -i = seek chính xác theo frame (chậm hơn nhưng đúng biên);
        # ĐỪNG đặt trước -i, keyframe-seek nhanh có thể lệch vài trăm ms.
        "-ss", f"{start_sec:.3f}", "-to", f"{end_sec:.3f}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(out_path),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=60)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False
    return True


def extract_gif(mp4_path: Path, out_gif_path: Path, fps: int = 8, width: int = 480) -> bool:
    palette = out_gif_path.with_suffix(".palette.png")
    filt = f"fps={fps},scale={width}:-1:flags=lanczos"
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp4_path), "-vf", f"{filt},palettegen", str(palette)],
            check=True, capture_output=True, timeout=60,
        )
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp4_path), "-i", str(palette),
             "-lavfi", f"{filt}[x];[x][1:v]paletteuse", str(out_gif_path)],
            check=True, capture_output=True, timeout=60,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False
    finally:
        palette.unlink(missing_ok=True)
    return True


# --------------------------------------------------------------------- video pool

class VideoPool:
    """Chọn video có TRỌNG SỐ theo n_frames (dùng làm proxy cho độ dài — rẻ, đã
    có sẵn), CHẶN TRẦN mỗi video (mặc định 1) để 50 câu trải rộng nhiều video
    nhất có thể thay vì dồn vào vài video dài. Dùng CHUNG một pool cho cả
    KIS+QA+TRAKE — không tách theo loại — để tối đa độ đa dạng nguồn trên cả bộ."""

    def __init__(self, video_ids: list[str], max_per_video: int, rng: random.Random):
        self._base_weights = {vid: max(1, n_frames_of(vid)) for vid in video_ids}
        self._max_per_video = max_per_video
        self._rng = rng
        self._used: dict[str, int] = {}
        self._avail = dict(self._base_weights)

    def pick(self) -> str | None:
        if not self._avail:
            print("CẢNH BÁO: hết video chưa dùng — cho phép DÙNG LẠI video (đa dạng bộ dữ liệu giảm).")
            self._avail = dict(self._base_weights)
            self._used.clear()
            if not self._avail:
                return None
        ids = list(self._avail.keys())
        weights = [self._avail[i] for i in ids]
        vid = self._rng.choices(ids, weights=weights, k=1)[0]
        self._used[vid] = self._used.get(vid, 0) + 1
        if self._used[vid] >= self._max_per_video:
            del self._avail[vid]
        return vid


# --------------------------------------------------------------------- clip records

@dataclass
class ClipTask:
    task_type: str
    is_buffer: bool


def _new_clip_id(used_ids: set[str]) -> str:
    while True:
        cid = secrets.token_hex(5)  # 10 ký tự hex, không mang thông tin video/thời điểm
        if cid not in used_ids:
            used_ids.add(cid)
            return cid


def _template_row(clip_id: str, split: str, task: ClipTask) -> dict:
    row = {
        "clip_id": clip_id,
        "task_type": task.task_type,
        "split": split,
        "is_buffer": task.is_buffer,
        "query_vi": "",
        "query_en": "",
    }
    if task.task_type == "QA":
        row["answer_text"] = ""
        row["answer_variants"] = ["", "", ""]  # GroundTruthQA cần >= 3 (schema.py)
    elif task.task_type == "TRAKE":
        row["n_events"] = None
        row["event_descs"] = []  # người gán nhãn liệt kê từng khoảnh khắc thấy được
    return row


# --------------------------------------------------------------------- main

def build_task_list(n_kis: int, n_qa: int, n_trake: int, buffer_frac: float) -> list[ClipTask]:
    tasks: list[ClipTask] = []
    for task_type, n in (("KIS", n_kis), ("QA", n_qa), ("TRAKE", n_trake)):
        n_buffer = round(n * buffer_frac)
        tasks += [ClipTask(task_type, is_buffer=False) for _ in range(n)]
        tasks += [ClipTask(task_type, is_buffer=True) for _ in range(n_buffer)]
    return tasks


def main() -> int:
    ap = argparse.ArgumentParser(description="E4.1 — lấy mẫu clip mù cho Dev Set (KIS/QA/TRAKE)")
    ap.add_argument("--out", default="dev_set/gt_staging")
    ap.add_argument("--video-dir", default="data/video")
    ap.add_argument("--shots-path", default="data/derived/shots.parquet")
    ap.add_argument("--n-kis", type=int, default=25)
    ap.add_argument("--n-qa", type=int, default=15)
    ap.add_argument("--n-trake", type=int, default=10)
    ap.add_argument("--buffer-frac", type=float, default=0.2,
                     help="tỉ lệ clip dự phòng thêm mỗi loại, phòng khi vài clip không dùng được")
    ap.add_argument("--holdout-frac", type=float, default=0.2)
    ap.add_argument("--max-per-video", type=int, default=1)
    ap.add_argument("--kis-clip-range", type=float, nargs=2, default=(3.0, 5.0))
    ap.add_argument("--qa-clip-range", type=float, nargs=2, default=(3.0, 5.0))
    ap.add_argument("--trake-clip-range", type=float, nargs=2, default=(15.0, 30.0))
    ap.add_argument("--edge-margin-frac", type=float, default=0.02,
                     help="bỏ qua phần trăm đầu/cuối video (mở đầu/credit thường không có nội dung)")
    ap.add_argument("--min-brightness-std", type=float, default=8.0,
                     help="ngưỡng lọc frame gần như trơn màu (slate/màn đen/chuyển cảnh)")
    ap.add_argument("--max-retries-per-clip", type=int, default=20)
    ap.add_argument("--gif", action="store_true", help="xuất thêm .gif xem nhanh cạnh .mp4")
    ap.add_argument("--seed", type=int, default=20260812)
    ap.add_argument("--dry-run", action="store_true", help="chỉ in kế hoạch, không chạy ffmpeg")
    ap.add_argument("--force", action="store_true", help="xoá sạch --out cũ trước khi chạy")
    args = ap.parse_args()

    if args.n_kis + args.n_qa + args.n_trake <= 0:
        print("LỖI: tổng số câu cần lấy mẫu phải > 0")
        return 2

    out_dir = REPO_ROOT / args.out
    clips_dir = out_dir / "clips"
    mapping_path = out_dir / "_secret_mapping.jsonl"
    template_path = out_dir / "annotation_template.jsonl"
    log_path = out_dir / "sampling_log.json"
    readme_path = out_dir / "README_ANNOTATOR.md"

    if mapping_path.exists() and not args.force:
        print(f"LỖI: {mapping_path} đã tồn tại — dùng --force nếu muốn lấy mẫu lại từ đầu "
              "(sẽ xoá batch cũ, tránh trộn hai lần lấy mẫu khác nhau).")
        return 1
    if args.force and out_dir.exists():
        import shutil
        shutil.rmtree(out_dir)
    clips_dir.mkdir(parents=True, exist_ok=True)

    video_dir = REPO_ROOT / args.video_dir
    shots_df = load_shots_table(REPO_ROOT / args.shots_path)

    all_ids = all_video_ids()
    usable_ids = [vid for vid in all_ids if (video_dir / f"{vid}.mp4").exists()]
    n_missing = len(all_ids) - len(usable_ids)
    if n_missing:
        print(f"CẢNH BÁO: {n_missing}/{len(all_ids)} video không có file local trong {video_dir}, bỏ qua.")
    if not usable_ids:
        print(f"LỖI: không có video nào trong {video_dir}")
        return 1

    rng = random.Random(args.seed)
    pool = VideoPool(usable_ids, args.max_per_video, rng)

    clip_range_by_type = {
        "KIS": tuple(args.kis_clip_range),
        "QA": tuple(args.qa_clip_range),
        "TRAKE": tuple(args.trake_clip_range),
    }

    tasks = build_task_list(args.n_kis, args.n_qa, args.n_trake, args.buffer_frac)
    rng.shuffle(tasks)  # thứ tự lấy mẫu KHÔNG được lộ qua thứ tự file — trộn trước khi cắt

    used_clip_ids: set[str] = set()
    mapping_records: list[dict] = []
    template_records: list[dict] = []
    probe_cache: dict[str, VideoProbe] = {}
    stats = {"generated": 0, "skipped_no_probe": 0, "skipped_no_window": 0,
             "skipped_degenerate": 0, "skipped_ffmpeg_fail": 0}

    for i, task in enumerate(tasks, 1):
        clip_range = clip_range_by_type[task.task_type]
        placed = False

        for _attempt in range(args.max_retries_per_clip):
            vid = pool.pick()
            if vid is None:
                print("LỖI: không còn video nào để lấy mẫu.")
                break

            probe = probe_cache.get(vid)
            if probe is None:
                probe = probe_video(video_dir / f"{vid}.mp4")
                if probe is not None:
                    probe_cache[vid] = probe
            if probe is None:
                stats["skipped_no_probe"] += 1
                continue

            n_frames = n_frames_of(vid)
            shots = shots_of(shots_df, vid)
            window = (
                pick_trake_window(rng, probe, shots, n_frames, clip_range, args.edge_margin_frac)
                if task.task_type == "TRAKE"
                else pick_single_moment_window(rng, probe, shots, n_frames, clip_range, args.edge_margin_frac)
            )
            if window is None:
                stats["skipped_no_window"] += 1
                continue

            start_f, end_f = window
            start_sec, end_sec = start_f / probe.fps, (end_f + 1) / probe.fps
            mid_sec = (start_sec + end_sec) / 2
            if is_degenerate_frame(video_dir / f"{vid}.mp4", mid_sec, args.min_brightness_std):
                stats["skipped_degenerate"] += 1
                continue

            clip_id = _new_clip_id(used_clip_ids)
            split = "holdout" if rng.random() < args.holdout_frac else "tune"
            out_mp4 = clips_dir / f"{clip_id}.mp4"

            if args.dry_run:
                ok = True
            else:
                ok = extract_clip(video_dir / f"{vid}.mp4", start_sec, end_sec, out_mp4)
                if ok and args.gif:
                    extract_gif(out_mp4, clips_dir / f"{clip_id}.gif")

            if not ok:
                used_clip_ids.discard(clip_id)
                stats["skipped_ffmpeg_fail"] += 1
                continue

            mapping_records.append({
                "clip_id": clip_id,
                "video_id": vid,
                "frame_start": start_f,
                "frame_end": end_f,
                "task_type": task.task_type,
                "split": split,
                "is_buffer": task.is_buffer,
            })
            template_records.append(_template_row(clip_id, split, task))
            stats["generated"] += 1
            placed = True
            break

        if not placed:
            print(f"[{i}/{len(tasks)}] BỎ QUA: không lấy được clip hợp lệ cho {task.task_type} "
                  f"sau {args.max_retries_per_clip} lần thử.")

    with open(mapping_path, "w", encoding="utf-8") as f:
        for rec in mapping_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    with open(template_path, "w", encoding="utf-8") as f:
        for rec in template_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    log_path.write_text(json.dumps({
        "seed": args.seed,
        "args": vars(args),
        "n_videos_considered": len(usable_ids),
        "n_videos_missing_local_file": n_missing,
        "stats": stats,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    readme_path.write_text(README_TEMPLATE, encoding="utf-8")

    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Hoàn thành: {stats['generated']} clip.")
    print(f"  Bỏ qua — không probe được video: {stats['skipped_no_probe']}")
    print(f"  Bỏ qua — không tìm được cửa sổ hợp lệ: {stats['skipped_no_window']}")
    print(f"  Bỏ qua — frame gần như trơn màu: {stats['skipped_degenerate']}")
    print(f"  Bỏ qua — ffmpeg lỗi: {stats['skipped_ffmpeg_fail']}")
    print(f"\nGửi cho người gán nhãn: {clips_dir}/  +  {template_path}")
    print(f"TUYỆT ĐỐI KHÔNG mở trước khi gán nhãn xong: {mapping_path}")
    return 0


README_TEMPLATE = """# Hướng dẫn gán nhãn Dev Set (mù)

## Bạn được xem gì
Một thư mục `clips/` chứa các đoạn video 3–5 giây (TRAKE dài hơn, 15–30 giây).
Tên file là mã ngẫu nhiên, KHÔNG liên quan gì tới video gốc hay mốc thời gian
trong video — đây là chủ đích, không phải thiếu sót.

## Bạn được dùng gì / KHÔNG được dùng gì
- ĐƯỢC: mọi thứ bạn tự thấy/tự nghe TRONG đoạn clip (hình ảnh, chữ trên màn
  hình, lời thoại). Đó là nội dung video gốc, không phải rò rỉ dữ liệu.
- KHÔNG ĐƯỢC: mở `_secret_mapping.jsonl`, tra cứu qua UI search của hệ thống,
  hay xem file OCR/ASR/Objects đã trích sẵn trong `data/derived/`. Viết câu
  truy vấn CHỈ dựa trên những gì bạn thấy trong clip, như một người dùng thật
  lần đầu xem đoạn video này.

## Việc cần làm
Mở `annotation_template.jsonl`, với mỗi dòng (mỗi clip):
- `query_vi` (bắt buộc), `query_en` (có thể để trống, hệ thống tự dịch sau)
- Nếu `task_type == "QA"`: điền `answer_text` + ít nhất 3 `answer_variants`
  (cách diễn đạt khác của cùng một câu trả lời — vd số/chữ, có/không dấu)
- Nếu `task_type == "TRAKE"`: điền `event_descs` — mô tả NGẮN từng khoảnh khắc
  tách biệt mà bạn thấy trong clip (2 trở lên), theo đúng thứ tự xuất hiện;
  `n_events` = số khoảnh khắc bạn liệt kê

Nếu một clip không đủ rõ để viết truy vấn (mờ, không có nội dung đáng nói),
để trống `query_vi` và ghi chú lý do — nó sẽ bị loại ở bước tổng hợp.

## KHÔNG làm gì
Đừng đổi tên file trong `clips/`, đừng thêm/xoá dòng trong template — mỗi dòng
khớp 1-1 với một clip qua `clip_id`.
"""


if __name__ == "__main__":
    sys.exit(main())
