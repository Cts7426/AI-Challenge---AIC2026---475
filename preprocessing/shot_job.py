"""
B1.1 — Shot Segmentation Pipeline

Chia mỗi video thành các shot (đoạn liên tục giữa hai lần chuyển cảnh).
Shot là đơn vị index nhỏ nhất của hệ thống — không phải frame rời.

Đầu vào:
  - data/derived/video_info.parquet  (NGUỒN SỰ THẬT: fps phân số, n_frames)
  - File .mp4 trên đĩa (quét đệ quy data/raw/videos/)

Đầu ra:
  - data/derived/shots_parts/<video_id>.parquet   (checkpoint per video)
  - Gộp bằng merge_shots_parts.py → data/derived/shots.parquet

Bộ phát hiện: PySceneDetect ContentDetector + StatsManager
  - threshold, downscale_factor, min_scene_len đọc từ config.yaml
  - Backend PyAV nếu có (nhanh hơn OpenCV cho decode tuần tự)

Song song: ProcessPoolExecutor, mỗi worker xử lý trọn một video.
  PySceneDetect chỉ giữ buffer nhỏ nên song song theo video là an toàn.
  Trên Apple Silicon 8 nhân: 5-6 worker cho tốc độ ~200-280x realtime.

Bất biến được đảm bảo (assert):
  - 0 <= start_frame <= end_frame < n_frames (theo video_info)
  - Liền mạch tuyệt đối: end[k] + 1 == start[k+1]
  - shot đầu start == 0, shot cuối end == n_frames - 1
  - Không shot nào ngắn hơn min_shot_seconds (trừ video chỉ có 1 shot)
  - Không shot nào dài hơn max_shot_seconds
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from fractions import Fraction
from pathlib import Path

import pandas as pd
import psutil
import yaml


# ═══ ĐƯỜNG DẪN ═══
ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT_DIR / "data" / "config" / "config.yaml"
DERIVED_DIR = ROOT_DIR / "data" / "derived"
VIDEOS_DIR = ROOT_DIR / "data" / "raw" / "videos"
SHOTS_PARTS_DIR = DERIVED_DIR / "shots_parts"

# Schema cố định — merge_shots_parts.py và các task sau phụ thuộc vào đây
SHOT_COLUMNS = [
    "shot_id", "video_id", "shot_seq",
    "start_frame", "end_frame", "n_frames", "duration_s",
    "is_force_split", "n_raw_shots_merged",
    "detector_confidence", "detector", "config_hash"
]


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


def _pick_backend() -> str | None:
    """PyAV decode tuần tự nhanh hơn OpenCV khoảng 20-40%.
    Trả None nếu không có, để scenedetect tự chọn mặc định."""
    try:
        import av  # noqa: F401
        return "pyav"
    except ImportError:
        return None


# ═══════════════════════════════════════════════════════
#  PHÁT HIỆN SHOT
# ═══════════════════════════════════════════════════════

def detect_shots_pyscenedetect(
    video_path: str,
    threshold: float,
    downscale_factor: int,
    min_scene_len_frames: int,
    backend: str | None = None,
) -> tuple[list[tuple[int, int, float | None]], int]:
    """
    Phát hiện shot bằng ContentDetector.

    Trả về:
      shots: list[(start_frame, end_frame, confidence)]  — end inclusive
      n_frames_decoder: tổng số frame theo decoder (để đối chiếu video_info)

    min_scene_len_frames là hàng rào chống rác đầu tiên. Đặt = 1 sẽ sinh
    ra hàng trăm "chuyển cảnh" giả trên video đã qua chuyển đổi khung hình
    (quan sát thực tế: video 25fps sinh 250+ shot dưới 0.5s, video 30fps
    chỉ 10-60). Đặt bằng khoảng 40% ngưỡng gộp là điểm cân bằng: đủ thấp
    để bộ lọc merge vẫn còn việc và n_raw_shots_merged vẫn có nghĩa, đủ
    cao để loại rác 1-2 frame ngay trong lúc decode.
    """
    from scenedetect import ContentDetector, SceneManager, StatsManager, open_video

    if backend is None:
        backend = _pick_backend()
        
    if backend == "pyav":
        from scenedetect.backends.pyav import VideoStreamAv
        video = VideoStreamAv(video_path, threading_mode="NONE")
    elif backend == "opencv":
        video = open_video(video_path, backend="opencv")
    else:
        video = open_video(video_path)

    stats = StatsManager()
    sm = SceneManager(stats_manager=stats)
    sm.auto_downscale = False
    sm.downscale = downscale_factor
    sm.add_detector(
        ContentDetector(threshold=threshold, min_scene_len=min_scene_len_frames)
    )
    sm.detect_scenes(video, show_progress=False)

    scene_list = sm.get_scene_list()
    n_frames_decoder = int(video.duration.frame_num) if video.duration else 0

    if not scene_list:
        if n_frames_decoder > 0:
            return [(0, n_frames_decoder - 1, None)], n_frames_decoder
        return [], 0

    shots: list[tuple[int, int, float | None]] = []
    for i, (start_tc, end_tc) in enumerate(scene_list):
        start_f = int(start_tc.frame_num)          # .frame_num thay get_frames()
        end_f = int(end_tc.frame_num) - 1          # scenedetect trả end exclusive
        if end_f < start_f:
            end_f = start_f

        # Điểm cắt của scene i là start_f. content_val tại đó là độ mạnh
        # của chuyển cảnh — hữu ích để sau này lọc shot đáng ngờ.
        conf = None
        if i > 0:
            try:
                m = stats.get_metrics(start_f, ["content_val"])
                if m and m[0] is not None:
                    conf = float(m[0])
            except Exception:
                pass
        shots.append((start_f, end_f, conf))

    return shots, n_frames_decoder


# ═══════════════════════════════════════════════════════
#  HẬU XỬ LÝ
# ═══════════════════════════════════════════════════════

def reconcile_with_video_info(
    shots: list[tuple[int, int, float | None]], n_frames_total: int
) -> list[tuple[int, int, float | None]]:
    """
    Đồng bộ biên shot với n_frames trong video_info.parquet.

    Vì sao cần: n_frames trong video_info đếm THẬT bằng ffprobe -count_frames,
    còn decoder của scenedetect có thể trả số khác (frame hỏng, packet lỗi,
    hoặc container ghi sai). Nếu không đồng bộ, assert liền mạch sẽ vỡ hoặc
    tệ hơn là shot cuối trỏ ra ngoài phạm vi video — lỗi im lặng.

    video_info là NGUỒN SỰ THẬT vì frame_map và mọi đáp án nộp cho BTC đều
    dựa trên hệ quy chiếu đó.
    """
    if not shots or n_frames_total <= 0:
        return []

    out: list[tuple[int, int, float | None]] = []
    for s, e, c in shots:
        if s >= n_frames_total:
            break                                   # shot nằm ngoài phạm vi
        out.append((s, min(e, n_frames_total - 1), c))

    if not out:
        return [(0, n_frames_total - 1, None)]

    # Ép shot đầu bắt đầu từ 0, shot cuối kết thúc tại n_frames - 1
    s0, e0, c0 = out[0]
    out[0] = (0, e0, c0)
    sl, el, cl = out[-1]
    out[-1] = (sl, n_frames_total - 1, cl)

    # Vá mọi khe hở còn lại (không nên có, nhưng rẻ và chặn được lỗi im lặng)
    for i in range(len(out) - 1):
        s_i, e_i, c_i = out[i]
        s_next = out[i + 1][0]
        if e_i != s_next - 1:
            out[i] = (s_i, s_next - 1, c_i)

    return [(s, e, c) for (s, e, c) in out if e >= s]


def merge_short_shots(
    shots: list[tuple[int, int, float | None]],
    min_frames: int,
) -> list[tuple[int, int, float | None, int]]:
    """
    Gộp shot ngắn hơn min_frames vào shot liền kề.

    SỬA LỖI so với bản cũ: shot ĐẦU TIÊN nếu ngắn thì gộp vào shot SAU nó,
    không phải bỏ qua. Bản cũ chỉ gộp về trước nên shot đầu luôn sót lại,
    gây cảnh báo "1 shot vẫn ngắn hơn 0.5s" ở MỌI video.

    Trả về: list[(start, end, confidence, n_raw_merged)]
    Bất biến: tổng số frame trước và sau gộp bằng nhau, không hở.
    """
    if not shots:
        return []
    if len(shots) == 1:
        s, e, c = shots[0]
        return [(s, e, c, 1)]

    merged: list[list] = []
    for s, e, c in shots:
        n = e - s + 1
        if merged and n < min_frames:
            merged[-1][1] = e                       # nuốt vào shot trước
            merged[-1][3] += 1
        else:
            merged.append([s, e, c, 1])

    # Shot đầu tiên ngắn: gộp về SAU (hướng duy nhất còn lại)
    if len(merged) > 1:
        s0, e0, c0, n0 = merged[0]
        if (e0 - s0 + 1) < min_frames:
            s1, e1, c1, n1 = merged[1]
            merged[1] = [s0, e1, c1, n0 + n1]
            merged.pop(0)

    return [(m[0], m[1], m[2], m[3]) for m in merged]


def force_split_long_shots(
    shots: list[tuple[int, int, float | None, int]],
    max_frames: int,
    split_frames: int,
) -> list[tuple[int, int, float | None, int, bool]]:
    """
    Cắt cưỡng bức shot dài quá max_frames thành các đoạn split_frames.

    Lý do tồn tại: bản tin có đoạn studio dài hàng phút. Để nguyên thì một
    shot phủ quá nhiều nội dung, và ở tầng gom điểm nó sẽ hút hết ứng viên
    top vì bất kỳ truy vấn nào cũng khớp một phần với nó.

    Đoạn đuôi ngắn hơn nửa split_frames được nhập vào đoạn trước để tránh
    sinh ra một mẩu vụn.
    """
    out: list[tuple[int, int, float | None, int, bool]] = []
    for s, e, c, n_merged in shots:
        n = e - s + 1
        if n <= max_frames:
            out.append((s, e, c, n_merged, False))
            continue

        cursor = s
        first = True
        while cursor <= e:
            chunk_end = min(cursor + split_frames - 1, e)
            # Đuôi quá ngắn thì nhập vào đoạn này luôn
            if 0 < (e - chunk_end) < split_frames // 2:
                chunk_end = e
            out.append((cursor, chunk_end, c if first else None,
                        n_merged if first else 1, True))
            cursor = chunk_end + 1
            first = False
    return out


def build_shot_dataframe(
    video_id: str,
    shots: list[tuple[int, int, float | None, int, bool]],
    fps: Fraction,
    n_frames_total: int,
    config_hash: str,
) -> pd.DataFrame:
    """Xây DataFrame đúng schema + assert toàn bộ bất biến."""
    if not shots:
        return pd.DataFrame(columns=SHOT_COLUMNS)

    rows = []
    for seq, (s, e, c, n_merged, is_force) in enumerate(shots):
        n_f = e - s + 1
        rows.append({
            "shot_id": f"{video_id}#s{seq:04d}",
            "video_id": video_id,
            "shot_seq": seq,
            "start_frame": s,
            "end_frame": e,
            "n_frames": n_f,
            "duration_s": round(n_f / float(fps), 4),
            "is_force_split": is_force,
            "n_raw_shots_merged": n_merged,
            "detector_confidence": c,
            "detector": "pyscenedetect",
            "config_hash": config_hash,
        })

    df = pd.DataFrame(rows, columns=SHOT_COLUMNS)
    df = df.astype({
        "shot_seq": "int32",
        "start_frame": "int64",
        "end_frame": "int64",
        "n_frames": "int32",
        "duration_s": "float64",
        "is_force_split": "bool",
        "n_raw_shots_merged": "int32",
        "detector_confidence": "float32",   # cố định dtype kể cả khi toàn null
    })

    sf = df["start_frame"].to_numpy()
    ef = df["end_frame"].to_numpy()

    assert sf[0] == 0, f"{video_id}: shot đầu start={sf[0]} != 0"
    assert ef[-1] == n_frames_total - 1, \
        f"{video_id}: shot cuối end={ef[-1]} != {n_frames_total - 1}"
    assert (sf >= 0).all(), f"{video_id}: có start_frame âm"
    assert (sf <= ef).all(), f"{video_id}: có start > end"
    assert (ef < n_frames_total).all(), f"{video_id}: end_frame vượt n_frames"
    if len(df) > 1:
        gaps = sf[1:] - ef[:-1] - 1
        bad = (gaps != 0).nonzero()[0]
        assert len(bad) == 0, (
            f"{video_id}: hở/chồng lấn tại shot {bad[0]} "
            f"(end={ef[bad[0]]}) → shot {bad[0]+1} (start={sf[bad[0]+1]})"
        )
    return df


# ═══════════════════════════════════════════════════════
#  XỬ LÝ MỘT VIDEO — hàm public, rolling_ingest gọi lại được
# ═══════════════════════════════════════════════════════

def process_single_video(
    video_id: str,
    video_path: str,
    fps_num: int,
    fps_den: int,
    n_frames: int,
    cfg: dict,
    output_dir: Path | None = None,
    write: bool = True,
    backend: str | None = None,
    config_hash: str = "",
) -> tuple[pd.DataFrame, dict]:
    """
    Pipeline đầy đủ cho một video. Trả về (DataFrame, stats).
    Không in gì — worker chạy song song nên mọi log do tiến trình cha in.
    """
    out_dir = output_dir or SHOTS_PARTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    sc = cfg["shot_detection"]
    fps = Fraction(int(fps_num), int(fps_den))

    # Quy đổi mọi ngưỡng sang FRAME một lần, tránh so sánh giây với frame
    min_shot_frames = max(1, round(float(sc["min_shot_seconds"]) * float(fps)))
    max_shot_frames = max(1, round(float(sc["max_shot_seconds"]) * float(fps)))
    split_frames = max(1, round(float(sc["force_split_seconds"]) * float(fps)))
    # Hàng rào rác trong lúc decode — xem docstring detect_shots_pyscenedetect
    det_min_len = int(sc.get("detector_min_scene_len_frames", 0)) or \
        max(2, int(min_shot_frames * 0.4))

    t0 = time.perf_counter()
    raw, n_dec = detect_shots_pyscenedetect(
        video_path,
        float(sc["content_threshold"]),
        int(sc["downscale_factor"]),
        det_min_len,
        backend,
    )
    t_detect = time.perf_counter() - t0

    import hashlib
    hash_str = f"{backend or 'opencv'}|{int(sc.get('downscale_factor', 2))}|" \
               f"{float(sc.get('content_threshold', 27.0))}|" \
               f"{float(sc.get('min_shot_seconds', 0.5))}|" \
               f"{float(sc.get('max_shot_seconds', 60.0))}|" \
               f"{float(sc.get('force_split_seconds', 30.0))}"
    actual_hash = hashlib.sha256(hash_str.encode()).hexdigest()[:12]

    raw = reconcile_with_video_info(raw, n_frames)
    n_raw = len(raw)

    merged = merge_short_shots(raw, min_shot_frames)
    n_merged = len(merged)

    final = force_split_long_shots(merged, max_shot_frames, split_frames)
    df = build_shot_dataframe(video_id, final, fps, n_frames, actual_hash)

    # Phân bố độ dài shot thô — để phát hiện video bất thường
    hist = {"<0.5s": 0, "0.5-1s": 0, "1-2s": 0, "2-5s": 0,
            "5-10s": 0, "10-30s": 0, "30-60s": 0, ">60s": 0}
    edges = [(0.5, "<0.5s"), (1, "0.5-1s"), (2, "1-2s"), (5, "2-5s"),
             (10, "5-10s"), (30, "10-30s"), (60, "30-60s")]
    for s, e, _ in raw:
        d = (e - s + 1) / float(fps)
        for lim, key in edges:
            if d < lim:
                hist[key] += 1
                break
        else:
            hist[">60s"] += 1

    stats = {
        "video_id": video_id,
        "n_raw": n_raw,
        "n_after_merge": n_merged,
        "n_final": len(df),
        "n_force_split": int(df["is_force_split"].sum()) if len(df) else 0,
        "avg_duration_s": float(df["duration_s"].mean()) if len(df) else 0.0,
        "min_duration_s": float(df["duration_s"].min()) if len(df) else 0.0,
        "max_duration_s": float(df["duration_s"].max()) if len(df) else 0.0,
        "n_frames_decoder": n_dec,
        "n_frames_info": n_frames,
        "frame_count_mismatch": int(n_dec - n_frames) if n_dec else 0,
        "detect_seconds": round(t_detect, 2),
        "video_seconds": n_frames / float(fps),
        "raw_hist": hist,
        "detector_min_scene_len": det_min_len,
    }

    if write:
        df.to_parquet(out_dir / f"{video_id}.parquet", index=False)
    return df, stats


def _worker(task: dict) -> dict:
    """Điểm vào của tiến trình con. Chỉ trả stats, không trả DataFrame"""
    import os
    import sys
    
    # 1. Ép luồng TRƯỚC MỌI IMPORT theo đúng yêu cầu
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"
    os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
    
    backend = task.get("backend")
    
    if backend == "opencv":
        import cv2
        cv2.setNumThreads(1)
        # Chặn đường av nếu xài opencv
        sys.modules["av"] = None
        
    try:
        _, stats = process_single_video(
            task["video_id"], task["video_path"],
            task["fps_num"], task["fps_den"], task["n_frames"],
            task["cfg"],
            backend=backend
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
    """
    Quét ĐỆ QUY data/raw/videos/ và join với video_info.parquet.

    video_info là nguồn sự thật cho fps phân số và n_frames. Video không có
    trong đó bị BỎ QUA và báo ra — KHÔNG suy fps bằng cv2.CAP_PROP_FPS như
    bản cũ, vì cách đó cho float làm tròn (25.0 thay vì 25/1, hoặc 29.97
    thay vì 30000/1001) và vi phạm quy ước fps phân số trong AGENTS.md.
    """
    df_vi = pd.read_parquet(DERIVED_DIR / "video_info.parquet")
    info = {r["video_id"]: r for r in df_vi.to_dict("records")}   # O(1) lookup

    files = {p.stem: p for p in VIDEOS_DIR.rglob("*.mp4")}

    if only_ids:
        candidates = [v for v in only_ids if v in files]
    else:
        candidates = sorted(files.keys())

    tasks, skipped = [], []
    for vid in candidates:
        if num_shards > 1 and get_video_shard(vid, num_shards) != shard:
            continue
        row = info.get(vid)
        if row is None or int(row.get("n_frames", 0) or 0) <= 0:
            skipped.append(vid)
            continue
        tasks.append({
            "video_id": vid,
            "video_path": str(files[vid]),
            "fps_num": int(row["fps_num"]),
            "fps_den": int(row["fps_den"]),
            "n_frames": int(row["n_frames"]),
            "cfg": cfg,
        })

    # Video dài chạy trước: worker rảnh cuối cùng không phải chờ một video
    # dài lê thê — rút ngắn tổng thời gian tường (makespan)
    tasks.sort(key=lambda t: -t["n_frames"])
    return tasks, skipped


# ═══════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════

def main() -> None:
    ap = argparse.ArgumentParser(description="B1.1 Shot Segmentation")
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--num-shards", type=int, default=1)
    ap.add_argument("--workers", type=int, default=0,
                    help="0 = tự chọn theo số nhân CPU")
    ap.add_argument("--video-ids", nargs="*", default=None)
    ap.add_argument("--force", action="store_true",
                    help="chạy lại cả video đã có part")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--backend", type=str, default=None, choices=["opencv", "pyav"])
    ap.add_argument("--downscale", type=int, default=None, help="Override downscale_factor from config")
    args = ap.parse_args()

    cfg = load_config()
    sc = cfg["shot_detection"]
    if args.downscale is not None:
        sc["downscale_factor"] = args.downscale
    ram_floor = float(sc.get("ram_floor_gb", 2.0))

    if args.backend is None:
        args.backend = _pick_backend() or "opencv"

    thr = float(sc.get("content_threshold", 27.0))
    ds = int(sc.get("downscale_factor", 2))
    msl = int(sc.get("detector_min_scene_len", 1))
    min_s = float(sc.get("min_shot_seconds", 0.5))
    max_s = float(sc.get("max_shot_seconds", 60.0))
    force_s = float(sc.get("force_split_seconds", 30.0))
    
    hash_str = f"{args.backend}|{ds}|{thr}|{msl}|{min_s}|{max_s}|{force_s}"
    config_hash = hashlib.sha256(hash_str.encode()).hexdigest()[:12]

    tasks, skipped = collect_tasks(cfg, args.shard, args.num_shards, args.video_ids)
    
    # Pass backend down
    for t in tasks:
        t["backend"] = args.backend
        t["config_hash"] = config_hash

    SHOTS_PARTS_DIR.mkdir(parents=True, exist_ok=True)
    if not args.force:
        done = {p.stem for p in SHOTS_PARTS_DIR.glob("*.parquet")}
        todo = [t for t in tasks if t["video_id"] not in done]
    else:
        todo = tasks

    # PySceneDetect ở downscale 2-3 chỉ chiếm ~150MB mỗi worker.
    # Chừa 3 nhân cho hệ điều hành và cho chính tiến trình cha.
    n_cpu = os.cpu_count() or 4
    workers = args.workers or max(1, min(7, n_cpu - 3))
    workers = max(1, min(workers, len(todo) or 1))

    total_s = sum(t["n_frames"] / (t["fps_num"] / t["fps_den"]) for t in todo)
    print(f"Tìm thấy {len(tasks)} video hợp lệ · cần xử lý {len(todo)}"
          f" · bỏ qua {len(skipped)} (thiếu video_info)")
    if skipped:
        print(f"  Bỏ qua: {', '.join(skipped[:10])}"
              f"{' ...' if len(skipped) > 10 else ''}")
    print(f"Tổng thời lượng cần xử lý: {total_s/3600:.1f} giờ"
          f" · workers={workers} (máy có {n_cpu} nhân)")
    print(f"==> CONFIG_HASH SẼ DÙNG TRONG MẺ NÀY: [{config_hash}]")

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
                print(f"[{i}/{len(todo)}] ❌ {vid} — {st.get('error')}",
                      file=sys.stderr)
                continue

            results.append(st)
            speed = st["video_seconds"] / max(st["detect_seconds"], 1e-6)
            mismatch = st["frame_count_mismatch"]
            flag = f" ⚠️ lệch {mismatch:+d} frame so với video_info" if mismatch else ""
            print(
                f"[{i}/{len(todo)}] {vid}: "
                f"raw={st['n_raw']} → merge={st['n_after_merge']} "
                f"→ final={st['n_final']} (cắt {st['n_force_split']}) | "
                f"avg={st['avg_duration_s']:.1f}s "
                f"[{st['min_duration_s']:.1f}–{st['max_duration_s']:.1f}s] | "
                f"{st['detect_seconds']:.1f}s @ {speed:.0f}x{flag}"
            )

            # Phanh an toàn: dừng SẠCH thay vì để hệ điều hành kill
            avail = psutil.virtual_memory().available / 1e9
            if avail < ram_floor:
                print(f"\n🛑 RAM khả dụng {avail:.1f}GB < {ram_floor}GB. "
                      f"Dừng sạch, checkpoint đã ghi, chạy lại để tiếp tục.",
                      file=sys.stderr)
                for f in futures:
                    f.cancel()
                break

    elapsed = time.perf_counter() - t_all
    done_s = sum(r["video_seconds"] for r in results)
    print("=" * 68)
    print(f"XONG {len(results)}/{len(todo)} video trong {elapsed/60:.1f} phút")
    if done_s:
        print(f"Tốc độ tổng: {done_s/elapsed:.0f}x realtime "
              f"({done_s/3600:.1f} giờ video)")
    if results:
        tot_shots = sum(r["n_final"] for r in results)
        print(f"Tổng shot: {tot_shots} · trung bình "
              f"{tot_shots/len(results):.0f} shot/video · "
              f"{tot_shots/(done_s/60):.1f} shot/phút video")
    if failures:
        print(f"\n❌ {len(failures)} video lỗi:", file=sys.stderr)
        for f in failures:
            print(f"  {f['video_id']}: {f.get('error')}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
