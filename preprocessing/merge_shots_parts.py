"""
B1.1 — Gộp shots_parts/*.parquet → shots.parquet

Chạy sau khi shot_job.py xử lý xong tất cả video.
Assert toàn cục:
  - shot_id unique
  - Liền mạch trong mỗi video
  - Không overlap
"""

import sys
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
PARTS_DIR = ROOT_DIR / "data" / "derived" / "shots_parts"
OUTPUT_PATH = ROOT_DIR / "data" / "derived" / "shots.parquet"


def main():
    parts = sorted(PARTS_DIR.glob("*.parquet"))
    if not parts:
        print("Không tìm thấy part nào trong shots_parts/")
        sys.exit(1)

    print(f"Tìm thấy {len(parts)} parts")

    dfs = []
    for p in parts:
        df = pd.read_parquet(p)
        dfs.append(df)

    df_all = pd.concat(dfs, ignore_index=True)
    print(f"Tổng: {len(df_all)} shot từ {df_all['video_id'].nunique()} video")

    # ═══ ASSERT CONFIG_HASH ═══
    if "config_hash" in df_all.columns:
        hashes = df_all.groupby("config_hash")["video_id"].unique()
        if len(hashes) > 1:
            print("\n❌ LỖI NGHIÊM TRỌNG: Các part được sinh ra từ nhiều cấu hình khác nhau!")
            for h, vids in hashes.items():
                print(f"  ➤ config_hash [{h}]: {len(vids)} video (VD: {vids[:3]})")
            print("Vui lòng xóa các part cũ và chạy lại đồng bộ.")
            sys.exit(1)
        else:
            print(f"✅ config_hash đồng nhất: {list(hashes.keys())[0]}")

    # ═══ ASSERT TOÀN CỤC ═══

    # shot_id unique
    dupes = df_all["shot_id"].duplicated().sum()
    assert dupes == 0, f"shot_id trùng: {dupes} dòng"

    # Liền mạch trong mỗi video
    errors = []
    for vid, grp in df_all.groupby("video_id"):
        grp = grp.sort_values("shot_seq")
        if len(grp) < 2:
            continue
        ends = grp["end_frame"].values[:-1]
        starts = grp["start_frame"].values[1:]
        gaps = starts - ends - 1
        bad = (gaps != 0).sum()
        if bad > 0:
            errors.append(vid)

    if errors:
        print(f"⚠️ {len(errors)} video có shot không liền mạch: {errors[:5]}")
    else:
        print("✅ Tất cả video liền mạch")

    # Shot đầu tiên = 0 cho mỗi video
    first_shots = df_all.groupby("video_id").apply(
        lambda g: g.sort_values("shot_seq").iloc[0]["start_frame"],
        include_groups=False
    )
    bad_first = first_shots[first_shots != 0]
    if len(bad_first) > 0:
        print(f"⚠️ {len(bad_first)} video có start_frame đầu != 0")
    else:
        print("✅ Tất cả video bắt đầu từ frame 0")

    # ═══ GÁN REP_KF_ID ═══
    print("\nĐang gán rep_kf_id...")
    import numpy as np
    if str(ROOT_DIR) not in sys.path:
        sys.path.insert(0, str(ROOT_DIR))
    from preprocessing.common.frame_map import load_frame_map
    
    df_all["split_reason"] = np.where(df_all["is_force_split"], "forced", "detector")
    df_all["rep_kf_id"] = None
    df_all["rep_source"] = "none"
    df_all["rep_offset"] = None
    df_all["keyframes_config_hash"] = None
    
    df_btc = None
    df_own = None
    try:
        df_btc = load_frame_map(require_verified=False)
        btc_col = "btc_kf_ordinal" if "btc_kf_ordinal" in df_btc.columns else "btc_ordinal"
        # Đảm bảo sort cứng để giải quyết tie-break ổn định
        df_btc = df_btc.sort_values(["video_id", "frame_idx", btc_col])
    except Exception as e:
        print(f"⚠️ Không load được frame_map (BTC): {e}")

    try:
        kf_path = ROOT_DIR / "data/derived/keyframes.parquet"
        if kf_path.exists():
            df_own = pd.read_parquet(kf_path)
            # Tie-break cho own keyframes
            df_own = df_own.sort_values(["video_id", "frame_idx", "kf_id"])
    except Exception as e:
        print(f"⚠️ Không load được keyframes (Own 1fps): {e}")

    # Lấy fps cho margin calculation
    try:
        df_info = pd.read_parquet(ROOT_DIR / "data/derived/video_info.parquet")
        df_info["fps"] = df_info["fps_num"] / df_info["fps_den"]
        fps_dict = df_info.set_index("video_id")["fps"].to_dict()
    except Exception:
        fps_dict = {}

    def _assign_source(df_candidates, source_name):
        nonlocal df_all
        if df_candidates is None or df_candidates.empty:
            return
            
        for vid, grp in df_all.groupby("video_id"):
            cand_v = df_candidates[df_candidates["video_id"] == vid]
            if cand_v.empty: continue
            
            kf = cand_v["frame_idx"].to_numpy()
            kf_ids = cand_v["kf_id"].to_numpy()
            
            idx = grp.index
            starts = grp["start_frame"].to_numpy()
            ends = grp["end_frame"].to_numpy()
            mids = (starts + ends) // 2
            
            # Tính margin m = min(0.25s, 20% len)
            fps = fps_dict.get(vid, 30.0)
            m_frames = np.minimum(0.25 * fps, (ends - starts) * 0.2).astype(int)
            
            # Step 1: Find best in [start + m, end - m]
            j = np.searchsorted(kf, mids)
            left = np.clip(j - 1, 0, len(kf) - 1)
            right = np.clip(j, 0, len(kf) - 1)
            
            # Tie-break bằng <= (vì kf đã sort theo btc_kf_ordinal)
            pick_idx = np.where(np.abs(kf[left] - mids) <= np.abs(kf[right] - mids), left, right)
            best_kf = kf[pick_idx]
            
            # Check điều kiện [start + m, end - m]
            valid_margin = (best_kf >= starts + m_frames) & (best_kf <= ends - m_frames)
            # Check điều kiện nới lỏng [start, end]
            valid_shot = (best_kf >= starts) & (best_kf <= ends)
            
            # Lọc những shot chưa có rep_kf_id (tức là none)
            needs_rep = (df_all.loc[idx, "rep_source"] == "none").to_numpy()
            
            # Gán nếu hợp lệ (ưu tiên margin, nếu rớt margin mà đậu shot thì vẫn lấy)
            mask_assign = needs_rep & valid_shot
            
            if np.any(mask_assign):
                assign_idx = idx[mask_assign]
                pick_assign = pick_idx[mask_assign]
                
                df_all.loc[assign_idx, "rep_kf_id"] = kf_ids[pick_assign]
                df_all.loc[assign_idx, "rep_source"] = source_name
                df_all.loc[assign_idx, "rep_offset"] = kf[pick_assign] - mids[mask_assign]

    # Ưu tiên 1: BTC
    _assign_source(df_btc, "btc")
    # Ưu tiên 2: Own 1fps
    _assign_source(df_own, "own_1fps")

    # Đánh dấu hash của cấu hình keyframes đã dùng
    # Tạm gán hash tĩnh để nhận biết (chờ B1.2 cập nhật)
    df_all["keyframes_config_hash"] = "fc5908cf2177" 

    # Ghi
    df_all = df_all.sort_values(["video_id", "shot_seq"]).reset_index(drop=True)
    df_all.to_parquet(OUTPUT_PATH, index=False)

    print(f"\n📦 Đã ghi {OUTPUT_PATH} ({len(df_all)} shot)")

    # Thống kê nhanh
    print(f"\nThống kê:")
    print(f"  Số video: {df_all['video_id'].nunique()}")
    print(f"  Tổng shot: {len(df_all)}")
    print(f"  Shot/video trung bình: {len(df_all) / df_all['video_id'].nunique():.1f}")
    print(f"  Thời lượng shot trung bình: {df_all['duration_s'].mean():.1f}s")
    print(f"  Thời lượng shot trung vị: {df_all['duration_s'].median():.1f}s")
    print(f"  Force split: {df_all['is_force_split'].sum()} shot "
          f"({df_all['is_force_split'].mean()*100:.1f}%)")
    print(f"  Merged (n_raw > 1): {(df_all['n_raw_shots_merged'] > 1).sum()} shot")


if __name__ == "__main__":
    main()
