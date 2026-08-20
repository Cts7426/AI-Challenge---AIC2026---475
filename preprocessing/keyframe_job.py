"""
B1.2 — Keyframe Extraction Pipeline

Trích keyframe ở mật độ 1fps (KHÔNG PHẢI 2) cho mỗi shot đã có trong
shots.parquet (B1.1) — CHỈ để tìm đúng shot khi search, KHÔNG phải nguồn
frame_idx nộp bài (slot allocator phát frame_idx bất kỳ, xem CLAUDE.md §7).

Đầu vào:
  - data/derived/video_info.parquet  (NGUỒN SỰ THẬT: fps phân số, n_frames)
  - data/derived/shots.parquet       (B1.1: start_frame/end_frame mỗi shot)
  - File .mp4 trên đĩa (quét đệ quy data/raw/videos/)

Đầu ra:
  - data/derived/keyframes/<video_id>/f<frame_idx:07d>.jpg  (JPEG q90, cạnh dài 448px)
  - data/derived/keyframes_parts/<video_id>.parquet          (checkpoint per video)
  - Gộp bằng merge_keyframes_parts.py → data/derived/keyframes.parquet

Trích CHÍNH XÁC frame theo SỐ THỨ TỰ khi decode (`select='eq(n,idx)'`), KHÔNG
dùng `-ss` time-seek — seek theo thời gian phụ thuộc GOP/VFR, có thể lệch vài
frame (CLAUDE.md bất biến: lệch >1 frame là lỗi 0 điểm không báo lỗi). Toàn bộ
frame_idx cần cho MỘT video được gom vào MỘT lệnh ffmpeg (một lần decode tuần
tự) thay vì gọi ffmpeg riêng từng frame — nhanh hơn nhiều, độ chính xác không đổi.

Resize (scale filter) thực hiện ngay trong ffmpeg; PIL chỉ dùng để ép JPEG
quality=90 chính xác theo số (ffmpeg -q:v dùng thang khác, không phải %).

Song song: ProcessPoolExecutor, mỗi worker xử lý trọn một video (mirror
shot_job.py) — mỗi worker gọi 1 tiến trình ffmpeg + PIL nhẹ, không cần
giới hạn thread BLAS gắt như phát hiện shot, nhưng vẫn ép cho nhất quán.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
import psutil
import yaml

# ═══ ĐƯỜNG DẪN ═══
ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT_DIR / "data" / "config" / "config.yaml"
DERIVED_DIR = ROOT_DIR / "data" / "derived"
VIDEOS_DIR = ROOT_DIR / "data" / "raw" / "videos"
KEYFRAMES_PARTS_DIR = DERIVED_DIR / "keyframes_parts"

# Schema cố định — khớp CỘT của keyframes.parquet hiện có (BUILD_TASKS B1.2)
KEYFRAME_COLUMNS = ["kf_id", "video_id", "shot_id", "frame_idx", "path", "row_id"]


# ═══════════════════════════════════════════════════════
#  TIỆN ÍCH
# ═══════════════════════════════════════════════════════

def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_video_shard(video_id: str, num_shards: int) -> int:
    """Chia shard bằng md5 — xác định, KHÔNG dùng hash() built-in
    (hash() đổi giá trị giữa các lần chạy Python vì PYTHONHASHSEED)."""
    return int(hashlib.md5(video_id.encode("utf-8")).hexdigest(), 16) % num_shards


# ═══════════════════════════════════════════════════════
#  CHỌN FRAME_IDX MỖI SHOT
# ═══════════════════════════════════════════════════════

def sample_frame_indices(start: int, end: int, fps: float, min_n: int, max_n: int) -> list[int]:
    """1fps trong [start, end], ép về [min_n, max_n] mẫu.

    Shot 1 frame (start==end) → trả đúng 1, không ép được min_n (không có gì
    để ép thêm). Shot ngắn hơn 1/fps giây (bước 1fps chỉ rơi 1 điểm) → ép
    min_n bằng cách rải đều linspace. Shot dài hơn max_n giây → cắt bớt đều
    bằng linspace trên chính danh sách 1fps, GIỮ đầu/cuối.
    """
    n = end - start + 1
    if n <= 0:
        return []
    if n == 1:
        return [start]

    step = max(1, round(fps))
    idxs = list(range(start, end + 1, step))

    if len(idxs) < min_n:
        k = min(min_n, n)
        idxs = sorted(set(int(round(x)) for x in np.linspace(start, end, k)))
    elif len(idxs) > max_n:
        pick = np.linspace(0, len(idxs) - 1, max_n).round().astype(int)
        idxs = sorted(set(int(idxs[i]) for i in pick))
    return idxs


def build_video_targets(shots_video: pd.DataFrame, fps: float, n_frames_video: int,
                         min_n: int, max_n: int) -> list[tuple[str, int]]:
    """[(shot_id, frame_idx), ...] cho TOÀN BỘ video, sort theo frame_idx.

    Shot không overlap (bất biến của B1.1: liền mạch tuyệt đối) nên frame_idx
    giữa các shot không trùng nhau — không cần khử trùng lặp qua shot.
    """
    out: list[tuple[str, int]] = []
    for row in shots_video.itertuples():
        idxs = sample_frame_indices(int(row.start_frame), int(row.end_frame), fps, min_n, max_n)
        for idx in idxs:
            idx = min(max(idx, 0), n_frames_video - 1)  # phòng lệch làm tròn ở biên video
            out.append((row.shot_id, idx))
    out.sort(key=lambda t: t[1])
    return out


# ═══════════════════════════════════════════════════════
#  TRÍCH FRAME BẰNG FFMPEG
# ═══════════════════════════════════════════════════════

# ffmpeg dùng cây biểu thức đệ quy cho select — đo thật (14/08): 100 điều kiện
# eq(n,i) nối bằng "+" chạy được, 150 vỡ filter graph ("Error while parsing
# expression"). Chốt 90 để có biên an toàn, KHÔNG chỉnh sát ngưỡng đo được.
SELECT_CHUNK_SIZE = 90


def _extract_chunk(video_path: str, frame_idxs: list[int], tmp_dir: Path,
                    long_edge_px: int, chunk_no: int) -> dict[int, Path]:
    """Một lệnh ffmpeg cho MỘT batch ≤ SELECT_CHUNK_SIZE frame_idxs (một lần
    decode tuần tự trọn video). Trả {frame_idx: đường dẫn PNG tạm}.

    select='eq(n,i1)+eq(n,i2)+...': ffmpeg đếm SỐ THỨ TỰ frame khi decode,
    khớp tuyệt đối bất kể fps/VFR — không suy ra từ thời gian.
    """
    select_expr = "+".join(f"eq(n\\,{i})" for i in frame_idxs)
    scale_expr = (
        f"if(gt(iw\\,ih)\\,{long_edge_px}\\,-2):if(gt(iw\\,ih)\\,-2\\,{long_edge_px})"
    )
    out_pattern = str(tmp_dir / f"c{chunk_no:03d}_%08d.png")

    cmd = [
        "ffmpeg", "-y", "-nostdin", "-loglevel", "error",
        "-i", video_path,
        "-vf", f"select='{select_expr}',scale={scale_expr}",
        "-vsync", "0",
        out_pattern,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    outputs = sorted(tmp_dir.glob(f"c{chunk_no:03d}_*.png"))
    if len(outputs) != len(frame_idxs):
        raise RuntimeError(
            f"ffmpeg trích {len(outputs)}/{len(frame_idxs)} frame yêu cầu (batch {chunk_no}) cho "
            f"{video_path} (stderr: {r.stderr[-500:]})"
        )
    return dict(zip(frame_idxs, outputs))


def extract_frames_ffmpeg(video_path: str, frame_idxs: list[int], tmp_dir: Path,
                           long_edge_px: int) -> dict[int, Path]:
    """Trích TẤT CẢ frame_idxs của video này, chia batch SELECT_CHUNK_SIZE
    (xem lý do ở đó) — mỗi batch một lượt decode tuần tự trọn video. Trả
    {frame_idx: đường dẫn PNG tạm}, output theo đúng THỨ TỰ decode trong
    từng batch (đầu vào đã sort tăng dần nên zip theo thứ tự là đúng)."""
    if not frame_idxs:
        return {}
    tmp_dir.mkdir(parents=True, exist_ok=True)

    out: dict[int, Path] = {}
    for c, i in enumerate(range(0, len(frame_idxs), SELECT_CHUNK_SIZE)):
        batch = frame_idxs[i:i + SELECT_CHUNK_SIZE]
        out.update(_extract_chunk(video_path, batch, tmp_dir, long_edge_px, c))
    return out


def resize_and_save_jpeg(png_path: Path, dest_path: Path, quality: int) -> None:
    """PNG (đã scale sẵn trong ffmpeg) → JPEG quality=90 CHÍNH XÁC theo số
    (libjpeg qua PIL — ffmpeg -q:v dùng thang 2-31 khác hẳn, không phải %)."""
    from PIL import Image

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(png_path) as im:
        im.convert("RGB").save(dest_path, "JPEG", quality=quality)


# ═══════════════════════════════════════════════════════
#  XỬ LÝ MỘT VIDEO
# ═══════════════════════════════════════════════════════

def process_single_video(
    video_id: str,
    video_path: str,
    fps_num: int,
    fps_den: int,
    n_frames: int,
    shots_video: pd.DataFrame,
    cfg: dict,
    keyframes_root: Path,
    parts_dir: Path,
    write: bool = True,
) -> tuple[pd.DataFrame, dict]:
    """Trả (DataFrame, stats). Không in gì — worker chạy song song."""
    kc = cfg["keyframe_extraction"]
    fps = float(fps_num) / float(fps_den)
    min_n, max_n = int(kc["min_per_shot"]), int(kc["max_per_shot"])
    long_edge = int(kc["long_edge_px"])
    quality = int(kc["jpeg_quality"])

    targets = build_video_targets(shots_video, fps, n_frames, min_n, max_n)
    video_dir = keyframes_root / video_id

    # Idempotent theo TỪNG FRAME: bỏ qua frame đã có file ảnh trên đĩa (resume
    # sau khi phiên Kaggle ngắt giữa chừng một video dài).
    missing = [(sid, idx) for sid, idx in targets if not (video_dir / f"f{idx:07d}.jpg").exists()]

    t0 = time.perf_counter()
    if missing:
        tmp_dir = video_dir.parent / f".tmp_{video_id}"
        try:
            idxs = [idx for _, idx in missing]
            png_by_idx = extract_frames_ffmpeg(video_path, idxs, tmp_dir, long_edge)
            for sid, idx in missing:
                resize_and_save_jpeg(png_by_idx[idx], video_dir / f"f{idx:07d}.jpg", quality)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
    t_extract = time.perf_counter() - t0

    rows = [{
        "kf_id": f"{video_id}_{idx:07d}",
        "video_id": video_id,
        "shot_id": sid,
        "frame_idx": idx,
        "path": f"keyframes/{video_id}/f{idx:07d}.jpg",
        "row_id": i,
    } for i, (sid, idx) in enumerate(targets)]
    df = pd.DataFrame(rows, columns=KEYFRAME_COLUMNS)

    per_shot = df.groupby("shot_id").size()
    stats = {
        "video_id": video_id,
        "n_shots": shots_video["shot_id"].nunique(),
        "n_keyframes": len(df),
        "n_extracted_new": len(missing),
        "n_skipped_existing": len(targets) - len(missing),
        "min_per_shot_actual": int(per_shot.min()) if len(per_shot) else 0,
        "max_per_shot_actual": int(per_shot.max()) if len(per_shot) else 0,
        "extract_seconds": round(t_extract, 2),
    }

    if write:
        parts_dir.mkdir(parents=True, exist_ok=True)
        df.to_parquet(parts_dir / f"{video_id}.parquet", index=False)
    return df, stats


def _worker(task: dict) -> dict:
    """Điểm vào của tiến trình con. Chỉ trả stats, không trả DataFrame."""
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["OPENBLAS_NUM_THREADS"] = "1"

    try:
        _, stats = process_single_video(
            task["video_id"], task["video_path"],
            task["fps_num"], task["fps_den"], task["n_frames"],
            task["shots_video"], task["cfg"],
            task["keyframes_root"], task["parts_dir"],
        )
        stats["ok"] = True
        return stats
    except Exception as e:
        import traceback
        return {
            "video_id": task["video_id"], "ok": False,
            "error": f"{type(e).__name__}: {e}",
            "traceback": traceback.format_exc(limit=3),
        }


# ═══════════════════════════════════════════════════════
#  THU THẬP DANH SÁCH VIỆC
# ═══════════════════════════════════════════════════════

def collect_tasks(cfg: dict, shard: int, num_shards: int,
                   only_ids: list[str] | None) -> tuple[list[dict], list[str]]:
    """Quét ĐỆ QUY data/raw/videos/, join video_info (fps/n_frames) +
    shots.parquet (ranh giới shot). Video thiếu 1 trong 2 → BỎ QUA, báo ra —
    KHÔNG suy fps bằng cv2/ffprobe tại đây (video_info là nguồn sự thật, xem
    lý do ở shot_job.py collect_tasks)."""
    df_vi = pd.read_parquet(DERIVED_DIR / "video_info.parquet")
    info = {r["video_id"]: r for r in df_vi.to_dict("records")}

    df_shots = pd.read_parquet(DERIVED_DIR / "shots.parquet",
                                columns=["shot_id", "video_id", "start_frame", "end_frame"])
    shots_by_video = {vid: g for vid, g in df_shots.groupby("video_id")}

    files = {p.stem: p for p in VIDEOS_DIR.rglob("*.mp4")}

    candidates = [v for v in only_ids if v in files] if only_ids else sorted(files.keys())

    tasks, skipped = [], []
    for vid in candidates:
        if num_shards > 1 and get_video_shard(vid, num_shards) != shard:
            continue
        row = info.get(vid)
        if row is None or int(row.get("n_frames", 0) or 0) <= 0:
            skipped.append(f"{vid} (thiếu video_info)")
            continue
        shots_video = shots_by_video.get(vid)
        if shots_video is None or shots_video.empty:
            skipped.append(f"{vid} (thiếu shots.parquet)")
            continue
        tasks.append({
            "video_id": vid,
            "video_path": str(files[vid]),
            "fps_num": int(row["fps_num"]),
            "fps_den": int(row["fps_den"]),
            "n_frames": int(row["n_frames"]),
            "shots_video": shots_video,
            "cfg": cfg,
        })

    tasks.sort(key=lambda t: -t["n_frames"])  # video dài chạy trước — rút ngắn makespan
    return tasks, skipped


# ═══════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════

def main() -> None:
    ap = argparse.ArgumentParser(description="B1.2 Keyframe Extraction")
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--num-shards", type=int, default=1)
    ap.add_argument("--workers", type=int, default=0, help="0 = tự chọn theo số nhân CPU")
    ap.add_argument("--video-ids", nargs="*", default=None)
    ap.add_argument("--force", action="store_true", help="chạy lại cả video đã có part")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--keyframes-root", type=str, default=None,
                     help="Override thư mục ghi ảnh (mặc định data/derived/keyframes) — "
                          "dùng để test không đụng dữ liệu thật")
    ap.add_argument("--parts-dir", type=str, default=None,
                     help="Override thư mục ghi part parquet (mặc định keyframes_parts)")
    args = ap.parse_args()

    cfg = load_config()
    kc = cfg["keyframe_extraction"]
    ram_floor = float(kc.get("ram_floor_gb", 2.0))

    keyframes_root = Path(args.keyframes_root) if args.keyframes_root else DERIVED_DIR / "keyframes"
    parts_dir = Path(args.parts_dir) if args.parts_dir else KEYFRAMES_PARTS_DIR

    if shutil.which("ffmpeg") is None:
        print("❌ Không tìm thấy `ffmpeg` trong PATH. Cài trước khi chạy job này.", file=sys.stderr)
        sys.exit(1)

    tasks, skipped = collect_tasks(cfg, args.shard, args.num_shards, args.video_ids)
    for t in tasks:
        t["keyframes_root"] = keyframes_root
        t["parts_dir"] = parts_dir

    parts_dir.mkdir(parents=True, exist_ok=True)
    if not args.force:
        done = {p.stem for p in parts_dir.glob("*.parquet")}
        todo = [t for t in tasks if t["video_id"] not in done]
    else:
        todo = tasks

    n_cpu = os.cpu_count() or 4
    workers = args.workers or max(1, min(6, n_cpu - 2))
    workers = max(1, min(workers, len(todo) or 1))

    print(f"Tìm thấy {len(tasks)} video hợp lệ · cần xử lý {len(todo)}"
          f" · bỏ qua {len(skipped)} (thiếu dữ liệu phụ thuộc)")
    if skipped:
        print(f"  Bỏ qua: {', '.join(skipped[:10])}{' ...' if len(skipped) > 10 else ''}")
    print(f"1fps · min={kc['min_per_shot']}/shot · max={kc['max_per_shot']}/shot · "
          f"q{kc['jpeg_quality']} · cạnh dài {kc['long_edge_px']}px")
    print(f"Ghi ảnh vào: {keyframes_root}")
    print(f"Ghi part vào: {parts_dir}")
    print(f"workers={workers} (máy có {n_cpu} nhân)")

    if args.dry_run or not todo:
        return

    print("=" * 68)
    t_all = time.perf_counter()
    results, failures = [], []

    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_worker, t): t for t in todo}
        for i, fut in enumerate(as_completed(futures), 1):
            st = fut.result()
            vid = st["video_id"]

            if not st.get("ok"):
                failures.append(st)
                print(f"[{i}/{len(todo)}] ❌ {vid} — {st.get('error')}", file=sys.stderr)
                continue

            results.append(st)
            print(
                f"[{i}/{len(todo)}] {vid}: {st['n_shots']} shot → {st['n_keyframes']} keyframe "
                f"(mới {st['n_extracted_new']}, có sẵn {st['n_skipped_existing']}) | "
                f"{st['min_per_shot_actual']}-{st['max_per_shot_actual']}/shot | "
                f"{st['extract_seconds']:.1f}s"
            )

            avail = psutil.virtual_memory().available / 1e9
            if avail < ram_floor:
                print(f"\n🛑 RAM khả dụng {avail:.1f}GB < {ram_floor}GB. "
                      f"Dừng sạch, checkpoint đã ghi, chạy lại để tiếp tục.", file=sys.stderr)
                for f in futures:
                    f.cancel()
                break

    elapsed = time.perf_counter() - t_all
    print("=" * 68)
    print(f"XONG {len(results)}/{len(todo)} video trong {elapsed/60:.1f} phút")
    if results:
        tot_kf = sum(r["n_keyframes"] for r in results)
        tot_new = sum(r["n_extracted_new"] for r in results)
        print(f"Tổng keyframe: {tot_kf} · mới trích: {tot_new} · "
              f"{tot_kf/len(results):.0f} keyframe/video trung bình")
    if failures:
        print(f"\n❌ {len(failures)} video lỗi:", file=sys.stderr)
        for f in failures:
            print(f"  {f['video_id']}: {f.get('error')}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
