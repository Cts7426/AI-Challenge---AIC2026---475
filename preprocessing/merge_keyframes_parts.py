"""
B1.2 — Gộp keyframes_parts/*.parquet (+ keyframes.parquet cũ nếu có) →
data/derived/keyframes.parquet

Chạy sau khi keyframe_job.py xử lý xong các video cần.

Video đã có trong keyframes.parquet CŨ (vd L21-L30 trích bằng quy trình cũ,
đã kiểm chứng frame_idx đúng — xem reports/) mà KHÔNG có part mới thì GIỮ
NGUYÊN, không xoá. Video có cả hai (hiếm — chỉ xảy ra khi chạy keyframe_job.py
--force cho video đã có sẵn) thì bản PART MỚI đè bản cũ.

Assert toàn cục:
  - kf_id unique
  - frame_idx nằm trong [0, n_frames) theo video_info.parquet
  - path trỏ tới file ảnh THẬT TỒN TẠI TRÊN ĐĨA (mẫu ngẫu nhiên, không quét hết —
    371k+ dòng, quét hết stat() từng file quá chậm cho một lần merge)
"""

import sys
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
DERIVED_DIR = ROOT_DIR / "data" / "derived"
PARTS_DIR = DERIVED_DIR / "keyframes_parts"
OUTPUT_PATH = DERIVED_DIR / "keyframes.parquet"
N_FILE_EXIST_SAMPLE = 200


def main() -> None:
    parts = sorted(PARTS_DIR.glob("*.parquet"))
    if not parts:
        print("Không tìm thấy part nào trong keyframes_parts/. "
              "Chạy preprocessing/keyframe_job.py trước.")
        sys.exit(1)

    print(f"Tìm thấy {len(parts)} part mới")
    df_new = pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True)
    new_video_ids = set(df_new["video_id"].unique())

    if OUTPUT_PATH.exists():
        df_old = pd.read_parquet(OUTPUT_PATH)
        n_old_before = len(df_old)
        df_old = df_old[~df_old["video_id"].isin(new_video_ids)]
        n_replaced = n_old_before - len(df_old)
        if n_replaced:
            print(f"⚠️ {n_replaced} dòng cũ bị THAY THẾ (video có part mới, chạy --force)")
        df_all = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df_all = df_new

    df_all = df_all.sort_values(["video_id", "frame_idx"]).reset_index(drop=True)
    df_all["row_id"] = range(len(df_all))

    # ═══ ASSERT ═══
    dupes = df_all["kf_id"].duplicated().sum()
    assert dupes == 0, f"kf_id trùng: {dupes} dòng"
    print("✅ kf_id unique")

    try:
        df_info = pd.read_parquet(DERIVED_DIR / "video_info.parquet",
                                   columns=["video_id", "n_frames"])
        nf = df_info.set_index("video_id")["n_frames"]
        joined = df_all.join(nf.rename("n_frames_video"), on="video_id")
        oob = joined[joined["n_frames_video"].notna() &
                      ((joined["frame_idx"] < 0) |
                       (joined["frame_idx"] >= joined["n_frames_video"]))]
        if len(oob):
            print(f"❌ {len(oob)} dòng frame_idx VƯỢT phạm vi video_info: "
                  f"{oob['video_id'].unique()[:5]}")
        else:
            print("✅ frame_idx trong phạm vi n_frames cho mọi video")
    except FileNotFoundError:
        print("⚠️ Không có video_info.parquet — bỏ qua assert phạm vi frame_idx")

    sample = df_all.sample(n=min(N_FILE_EXIST_SAMPLE, len(df_all)), random_state=0)
    missing = [p for p in sample["path"] if not (DERIVED_DIR / p).exists()]
    if missing:
        print(f"⚠️ {len(missing)}/{len(sample)} file ảnh MẪU không tồn tại trên đĩa "
              f"(bình thường nếu ảnh chưa tải về máy này — xem KEYFRAME_ROOT trong qa.py). "
              f"VD: {missing[:3]}")
    else:
        print(f"✅ {len(sample)}/{len(sample)} file ảnh mẫu tồn tại trên đĩa")

    df_all.to_parquet(OUTPUT_PATH, index=False)
    print(f"\n📦 Đã ghi {OUTPUT_PATH} ({len(df_all)} dòng, "
          f"{df_all['video_id'].nunique()} video)")
    print("Chạy `python scripts/generate_parquet_meta.py` để cập nhật .meta.json")


if __name__ == "__main__":
    main()
