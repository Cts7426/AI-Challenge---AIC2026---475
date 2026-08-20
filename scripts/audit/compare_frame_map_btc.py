# scripts/audit/compare_frame_map_btc.py — đối chiếu frame_map.parquet với
# bảng GỐC `map-keyframes` của BTC (19/08)
#
# ===== Vì sao phép kiểm này quan trọng hơn mọi phép kiểm khác =====
# BTC chấm KIS/Q&A bằng `frame_id ∈ [s, e]` và TRAKE bằng từng mốc khoảnh khắc.
# Con số `frame_id` mình nộp phải nằm CÙNG HỆ ĐÁNH SỐ với đáp án của BTC. Lệch
# hệ đánh số = 0 điểm dù tìm đúng video, đúng cảnh, đúng mọi thứ (CLAUDE.md bất
# biến 5). Và lệch kiểu này KHÔNG có triệu chứng nào: search vẫn trả kết quả
# đẹp, validator vẫn cho qua, file nộp vẫn hợp lệ.
#
# Tới trước 19/08 `frame_map.parquet` được dựng bằng cách TỰ TÍNH từ pts_time ×
# fps, vì lúc đó chưa tải `map-keyframes`. Nay đã có bảng gốc → so được.
#
# ===== KẾT LUẬN 19/08: GIỮ NGUYÊN BẢNG CỦA MÌNH — ĐỪNG ĐỔI SANG SỐ BTC =====
# (đã thử đổi, đã đo, đã rút lại — đọc hết mục này trước khi định "sửa" lại)
#
#   số keyframe : khớp tuyệt đối, 0 dư 0 thiếu
#   pts_time    : khớp 100%      ·  fps: khớp 100%   → cùng nguồn thời gian
#   frame_idx   : lệch 19.381 keyframe (10,93%), gần như luôn +1
#   nguyên nhân : BTC = floor(pts_time × fps)  — khớp 100,0000%
#                 ta  = round(pts_time × fps)  — khớp  96,28%
#                 (phần 3,7% còn lại là 1.526 keyframe/32 video đã chữa tay
#                  bằng kiểm chứng pixel mse_best — báo cáo B01 mục 5.1–5.2)
#
# Vì sao ban đầu tưởng phải đổi: BTC chấm bằng hệ đánh số của chính họ, nên
# bảng gốc của họ nghe như đương nhiên là chuẩn.
#
# ===== Phép đo lật ngược kết luận đó: TÍNH TĂNG NGẶT =====
# Hai keyframe khác nhau của cùng một video KHÔNG THỂ nằm ở cùng một frame.
# Đếm số chỗ vi phạm (frame của ordinal sau ≤ ordinal trước):
#       bảng BTC : 614 chỗ vi phạm      ← bảng gốc TỰ MÂU THUẪN
#       bảng ta  :   0 chỗ vi phạm
# Đây đúng vấn đề #2 mà báo cáo B01 đã ghi: CSV của BTC có chỗ mất giá trị,
# nhiều keyframe liên tiếp cùng ghi một số. Ví dụ:
#       L21_V006#k0001  pts 0.000000 × 30 = 0.0     → BTC 0 · ta 0
#       L21_V006#k0002  pts 0.033333 × 30 = 0.99999 → BTC 0 · ta 1
# pts_time trong CSV bị cắt còn 6 chữ số thập phân, floor() của 0,99999 ra 0 —
# lỗi làm tròn của CHÍNH BTC. round() cho đúng frame 1.
#
# Hậu quả nếu đổi (đo thật, không phải suy đoán): tests/test_validator.py bắt
# ngay `duplicate_answer` trên L21_V006 — hai dòng nộp trùng khít (video, frame).
# Validator D0.2 từ chối ghi CẢ FILE khi có dòng trùng → những video đó KHÔNG
# CÓ bài nộp. Đổi để "đúng chuẩn BTC" hoá ra là tự loại mình khỏi cuộc chơi.
#
# ===== Vậy 10,93% lệch kia có mất điểm không? =====
# Lệch tối đa 1 frame. BTC chấm `frame_id ∈ [s, e]` với cửa sổ rộng nhiều frame,
# nên 1 frame gần như chắc chắn vẫn lọt. Đổi cả bảng để đuổi theo 1 frame, mà
# đánh đổi bằng 614 chỗ mâu thuẫn, là lỗ ròng.
#
# ⚠️ Câu hỏi CÒN MỞ, nên hỏi BTC (E-series): đáp án [s, e] của BTC được định
# nghĩa theo hệ đánh số nào — theo `map-keyframes` của họ, hay theo frame thật
# của mp4? Có câu trả lời thì phép đo dưới đây chốt lại được trong 5 giây.
#
# ===== Chạy =====
#   python scripts/audit/compare_frame_map_btc.py
#   python scripts/audit/compare_frame_map_btc.py --show 20   # xem nhiều ví dụ hơn
# Exit code: 0 = khớp hoàn toàn · 1 = có lệch (đọc bảng để quyết định)

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
FRAME_MAP = ROOT / "data" / "derived" / "frame_map.parquet"
MAP_KEYFRAMES = ROOT / "data" / "raw" / "btc" / "metadata" / "map-keyframes"


def doc_btc(thu_muc: Path) -> pd.DataFrame:
    """Gộp toàn bộ CSV map-keyframes của BTC (1 file/video) thành một bảng.

    Cột gốc: n · pts_time · fps · frame_idx. `n` là SỐ THỨ TỰ keyframe trong
    video (đếm từ 1) — cùng nghĩa với `btc_ordinal` bên frame_map.parquet, đây
    là khoá join giữa hai bảng.
    """
    if not thu_muc.is_dir():
        raise SystemExit(
            f"Không thấy {thu_muc}.\n"
            "  Giải nén map-keyframes-aic25-b1.zip vào data/raw/btc/metadata/ trước."
        )
    ds = []
    for f in sorted(thu_muc.glob("*.csv")):
        d = pd.read_csv(f)
        d["video_id"] = f.stem
        ds.append(d)
    if not ds:
        raise SystemExit(f"{thu_muc} không có file .csv nào.")
    return pd.concat(ds, ignore_index=True).rename(
        columns={"n": "btc_ordinal", "frame_idx": "btc_frame_idx",
                 "pts_time": "btc_pts_time", "fps": "btc_fps"}
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Đối chiếu frame_map với map-keyframes của BTC")
    ap.add_argument("--show", type=int, default=8, help="số ví dụ lệch in ra")
    args = ap.parse_args()

    ta = pd.read_parquet(FRAME_MAP)
    btc = doc_btc(MAP_KEYFRAMES)

    # --- 1. số lượng: thiếu/dư keyframe là lỗi nặng hơn lệch số, kiểm trước
    m = ta.merge(btc, on=["video_id", "btc_ordinal"], how="outer",
                 indicator=True, suffixes=("", "_btc"))
    chi_ta = int((m._merge == "left_only").sum())
    chi_btc = int((m._merge == "right_only").sum())

    print(f"keyframe của ta  : {len(ta):>9,}")
    print(f"keyframe của BTC : {len(btc):>9,}")
    print(f"chỉ có ở ta      : {chi_ta:>9,}"
          + ("   ← keyframe lạ, index đang chứa thứ BTC không chấm" if chi_ta else ""))
    print(f"chỉ có ở BTC     : {chi_btc:>9,}"
          + ("   ← BỎ SÓT keyframe, mất ứng viên" if chi_btc else ""))

    k = m[m._merge == "both"].copy()

    # --- 2. cùng nguồn thời gian? pts_time/fps lệch nghĩa là hai bên nói về hai
    # phiên bản video khác nhau — lúc đó lệch frame_idx chỉ là triệu chứng.
    pts_khop = float(np.isclose(k["pts_time"], k["btc_pts_time"]).mean())
    fps_khop = float((k["fps"] == k["btc_fps"]).mean())
    print(f"\npts_time khớp    : {pts_khop:>9.4%}")
    print(f"fps khớp         : {fps_khop:>9.4%}")
    if pts_khop < 1.0 or fps_khop < 1.0:
        print("  ⚠️ pts_time/fps KHÔNG khớp 100% — hai bên đang nói về hai bản video "
              "khác nhau, sửa việc đó trước khi bàn tới frame_idx.")

    # --- 3. frame_idx: con số THẬT SỰ đem đi nộp
    d = k["frame_idx"] - k["btc_frame_idx"]
    n_lech = int((d != 0).sum())
    print(f"\nframe_idx khớp   : {int((d == 0).sum()):>9,} / {len(k):,}  ({(d == 0).mean():.2%})")
    print(f"frame_idx lệch   : {n_lech:>9,}")

    if n_lech:
        print(f"  phân bố lệch (ta − BTC): "
              f"{ {int(v): int(c) for v, c in d[d != 0].value_counts().head(6).items()} }")

        # Truy nguyên nhân: cùng pts_time × fps, chỉ khác cách làm tròn.
        x = k["pts_time"] * k["fps"]
        print("\n  Cách làm tròn nào tái tạo được từng bảng:")
        for ten, val in (("floor(pts×fps)", np.floor(x)), ("round(pts×fps)", np.round(x))):
            print(f"    BTC == {ten:<15}: {(k.btc_frame_idx == val).mean():8.4%}"
                  f"     ta == {ten:<15}: {(k.frame_idx == val).mean():8.4%}")

        print(f"\n  {args.show} ví dụ lệch:")
        vi_du = k[d != 0].head(args.show)
        print("    " + vi_du[["kf_id", "pts_time", "fps", "frame_idx", "btc_frame_idx"]]
              .to_string(index=False).replace("\n", "\n    "))

    # --- 4. TÍNH TĂNG NGẶT — phép đo quyết định (xem ghi chú đầu file)
    # Hai keyframe khác nhau của cùng một video không thể ở cùng một frame.
    # Bảng nào vi phạm nhiều hơn thì bảng đó kém tin cậy hơn, bất kể bảng nào
    # là "bản gốc".
    print("\n  Số chỗ KHÔNG tăng ngặt (ordinal tăng mà frame không tăng):")
    s = k.sort_values(["video_id", "btc_ordinal"])
    for ten, cot in (("bảng của ta", "frame_idx"), ("bảng của BTC", "btc_frame_idx")):
        vp = int((s.groupby("video_id")[cot].diff() <= 0).sum())
        print(f"    {ten:<14}: {vp:>6,} chỗ"
              + ("   ← tự mâu thuẫn" if vp else "   ← nhất quán"))
    print("    Nộp bài có hai dòng trùng (video, frame) thì validator D0.2 từ chối "
          "ghi CẢ FILE.")

    print("\n  → Kết luận 19/08: GIỮ bảng của ta. Chi tiết ở đầu file này.")
    return 1 if (n_lech or chi_ta or chi_btc) else 0


if __name__ == "__main__":
    sys.exit(main())
