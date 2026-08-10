# scripts/verify_clip_space.py — A1.0b: KIỂM CHỨNG KHÔNG GIAN VECTOR
#
# ===== Vì sao script này tồn tại =====
# BTC phát sẵn `clip-features-32` (.npy) cho ẢNH. Ta encode TEXT của truy vấn
# bằng model trong data/config/clip_model.py. Hai bên chỉ so sánh được nếu CÙNG
# một không gian vector — tức cùng model, cùng bộ trọng số, cùng preprocessing.
#
# Nếu lệch, KHÔNG có gì báo lỗi: Milvus vẫn trả top-10, cosine vẫn ra 0.2–0.3
# (đúng khoảng "bình thường" của CLIP), kết quả vẫn trông hợp lý — nhưng sai
# toàn bộ. Đây đúng loại lỗi im lặng CLAUDE.md bất biến #4 nói tới. Cách duy
# nhất phát hiện: tự encode lại chính tấm ảnh BTC đã encode, rồi so cosine.
#
# ===== Cách kiểm =====
# Lấy N keyframe BTC → encode ảnh bằng model ta đang cấu hình → cosine với
# vector BTC cấp cho đúng keyframe đó.
#   ≈ 1.0      → ĐẠT, cùng không gian
#   ~ 0        → SAI MODEL, dừng đỏ, TUYỆT ĐỐI không tin kết quả search nào
#   0.5 – 0.99 → NGHI NGỜ: cùng họ model nhưng lệch preprocessing/variant
#                (thủ phạm quen: QuickGELU vs GELU, resize/normalize khác)
#
# Vì sao so ẢNH-ẢNH mà không phải TEXT-ẢNH: cosine text-ảnh của CLIP vốn chỉ
# ~0.2–0.3 kể cả khi đúng, nên không có ngưỡng nào phân biệt được đúng/sai.
# Ảnh-ảnh cùng model phải ≈ 1.0 — một mốc dứt khoát, kiểm được.
#
# ===== Chạy =====
#   python scripts/verify_clip_space.py                        # 10 mẫu, model trong config
#   python scripts/verify_clip_space.py --n 30
#   python scripts/verify_clip_space.py --sweep                # DÒ xem model nào khớp
#   python scripts/verify_clip_space.py --data-root D:\aic_data
#
# --sweep giải luôn dấu "# TODO: BTC" trong clip_model.py: thử lần lượt các
# ứng viên phổ biến, in cosine trung bình của từng cái. Cái nào ≈ 1.0 chính là
# model BTC đã dùng → điền vào config, hết giả định.
#
# Exit code: 0 = tất cả ĐẠT · 1 = có mẫu không đạt · 2 = thiếu dữ liệu/thư viện.

from __future__ import annotations

import argparse
import os
import random
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from data.config.clip_model import (  # noqa: E402
    CLIP_EMBEDDING_DIM,
    CLIP_MODEL_NAME,
    CLIP_PRETRAINED,
)

CLIP_ROW_INDEX = REPO_ROOT / "data" / "derived" / "clip_row_index.parquet"

# Ứng viên cho --sweep. Xếp theo xác suất giảm dần dựa trên các kỳ AIC/VBS trước.
SWEEP_CANDIDATES = [
    ("ViT-B-32-quickgelu", "openai"),
    ("ViT-B-32", "openai"),
    ("ViT-B-32", "laion2b_s34b_b79k"),
    ("ViT-B-32", "datacomp_xl_s13b_b90k"),
    ("ViT-B-16-quickgelu", "openai"),
]

DAT = 0.99      # ≥ ngưỡng này = ĐẠT
SAI_HAN = 0.10  # < ngưỡng này = sai model hẳn


# --------------------------------------------------------------- tìm dữ liệu

def _data_root(arg: str | None) -> Path:
    """Gốc dữ liệu thô. Ưu tiên --data-root > env AIC_DATA_ROOT > data/raw."""
    if arg:
        return Path(arg)
    if os.environ.get("AIC_DATA_ROOT"):
        return Path(os.environ["AIC_DATA_ROOT"])
    return REPO_ROOT / "data" / "raw"


def _tim_thu_muc(root: Path, ten_goi_y: list[str]) -> Path | None:
    """Tìm thư mục con theo vài tên gợi ý (BTC đổi cách đặt tên giữa các kỳ)."""
    for ten in ten_goi_y:
        p = root / ten
        if p.is_dir():
            return p
    # Quét sâu 2 tầng cho trường hợp giải nén ra thư mục lồng
    for p in root.glob("*/"):
        for ten in ten_goi_y:
            if (p / ten).is_dir():
                return p / ten
    return None


def _anh_keyframe(kf_dir: Path, video_id: str, ordinal: int) -> Path | None:
    """Đường dẫn ảnh keyframe BTC thứ `ordinal` (đếm từ 1) của một video.

    Không hardcode quy ước đặt tên: thử pattern trực tiếp trước (nhanh), không
    thấy thì liệt kê cả thư mục rồi sắp xếp và lấy theo vị trí. Sắp xếp theo
    TÊN chứ không theo thứ tự hệ thống trả về — os.listdir không đảm bảo thứ tự.
    """
    thu_muc = None
    for ung_vien in (kf_dir / video_id, kf_dir / video_id.split("_")[0] / video_id):
        if ung_vien.is_dir():
            thu_muc = ung_vien
            break
    if thu_muc is None:
        nested = list(kf_dir.glob(f"**/{video_id}"))
        thu_muc = nested[0] if nested else None
    if thu_muc is None:
        return None

    for mau in (f"{ordinal:03d}", f"{ordinal:04d}", f"{ordinal:05d}", str(ordinal)):
        for duoi in (".jpg", ".jpeg", ".png", ".webp"):
            p = thu_muc / f"{mau}{duoi}"
            if p.exists():
                return p

    anh = sorted(
        p for p in thu_muc.iterdir()
        if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")
    )
    return anh[ordinal - 1] if 0 < ordinal <= len(anh) else None


# ------------------------------------------------------------------- so khớp

def _chuan_hoa(v: np.ndarray) -> np.ndarray:
    """L2-normalize. CLAUDE.md bất biến #4: chuẩn hoá CẢ HAI PHÍA."""
    n = np.linalg.norm(v)
    return v if n == 0 else v / n


def _nap_model(ten: str, pretrained: str):
    try:
        import open_clip
        import torch
    except ImportError:
        print(
            "THIẾU THƯ VIỆN. Cài (torch bản CPU theo CLAUDE.md):\n"
            "  pip install torch --index-url https://download.pytorch.org/whl/cpu\n"
            "  pip install open_clip_torch pillow",
            file=sys.stderr,
        )
        raise SystemExit(2)

    model, _, preprocess = open_clip.create_model_and_transforms(ten, pretrained=pretrained)
    model.eval()
    return model, preprocess, torch


def _do_mot_bo(mau: list[dict], ten: str, pretrained: str, features_dir: Path) -> list[float]:
    """Encode lại các ảnh mẫu bằng (ten, pretrained), trả list cosine với vector BTC."""
    from PIL import Image

    model, preprocess, torch = _nap_model(ten, pretrained)
    cache: dict[str, np.ndarray] = {}
    cos: list[float] = []

    for m in mau:
        if m["npy_file"] not in cache:
            cache[m["npy_file"]] = np.load(features_dir / m["npy_file"])
        vec_btc = _chuan_hoa(cache[m["npy_file"]][m["local_row"]].astype(np.float32))

        anh = preprocess(Image.open(m["anh"]).convert("RGB")).unsqueeze(0)
        with torch.no_grad():
            vec_ta = model.encode_image(anh).cpu().numpy()[0].astype(np.float32)
        cos.append(float(np.dot(vec_btc, _chuan_hoa(vec_ta))))

    return cos


# ---------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description="Kiểm chứng không gian vector CLIP (A1.0b)")
    ap.add_argument("--n", type=int, default=10, help="số keyframe lấy mẫu (mặc định 10)")
    ap.add_argument("--data-root", help="gốc data thô (mặc định data/raw hoặc $AIC_DATA_ROOT)")
    ap.add_argument("--features-dir", help="thư mục .npy của BTC")
    ap.add_argument("--keyframes-dir", help="thư mục ảnh keyframe của BTC")
    ap.add_argument("--seed", type=int, default=42, help="cố định để chạy lại ra cùng mẫu")
    ap.add_argument("--sweep", action="store_true",
                    help="thử nhiều model ứng viên để DÒ ra model BTC đã dùng")
    args = ap.parse_args()

    import pandas as pd

    if not CLIP_ROW_INDEX.exists():
        print(f"THIẾU {CLIP_ROW_INDEX} — cần clip_row_index.parquet từ B0.1.", file=sys.stderr)
        return 2

    root = _data_root(args.data_root)
    features_dir = (
        Path(args.features_dir) if args.features_dir
        else _tim_thu_muc(root, ["clip-features-32", "clip_features", "clip-features"])
    )
    kf_dir = (
        Path(args.keyframes_dir) if args.keyframes_dir
        else _tim_thu_muc(root, ["keyframes", "Keyframes", "keyframe"])
    )

    if not features_dir or not features_dir.is_dir():
        print(f"KHÔNG THẤY thư mục .npy dưới {root}. Chỉ định bằng --features-dir.", file=sys.stderr)
        return 2
    if not kf_dir or not kf_dir.is_dir():
        print(f"KHÔNG THẤY thư mục ảnh keyframe dưới {root}. Dùng --keyframes-dir.", file=sys.stderr)
        return 2

    print(f"features : {features_dir}")
    print(f"keyframes: {kf_dir}")

    # --- lấy mẫu: rải đều nhiều video, không dồn vào một video (một video lỗi
    #     lẻ có thể làm cả bảng đỏ hoặc cả bảng xanh giả)
    df = pd.read_parquet(CLIP_ROW_INDEX)
    rng = random.Random(args.seed)
    videos = sorted(df["video_id"].unique())
    rng.shuffle(videos)

    mau: list[dict] = []
    for video_id in videos:
        if len(mau) >= args.n:
            break
        hang = df[df["video_id"] == video_id]
        r = hang.iloc[rng.randrange(len(hang))]
        if not (features_dir / r["npy_file"]).exists():
            continue
        anh = _anh_keyframe(kf_dir, video_id, int(r["btc_kf_ordinal"]))
        if anh is None:
            continue
        mau.append({
            "kf_id": r["kf_id"], "npy_file": r["npy_file"],
            "local_row": int(r["local_row"]), "anh": anh,
        })

    if not mau:
        print("KHÔNG ghép được mẫu nào (không tìm thấy ảnh khớp ordinal). "
              "Kiểm tra lại layout thư mục keyframes.", file=sys.stderr)
        return 2
    if len(mau) < args.n:
        print(f"[cảnh báo] chỉ ghép được {len(mau)}/{args.n} mẫu.")

    # --- chế độ dò model
    if args.sweep:
        print(f"\nDÒ MODEL trên {len(mau)} mẫu — tìm cái cho cosine ≈ 1.0\n")
        print(f"{'model':<24} {'pretrained':<24} {'cosine TB':>10}  kết luận")
        print("-" * 76)
        tot: tuple[float, tuple[str, str]] | None = None
        for ten, pre in SWEEP_CANDIDATES:
            try:
                tb = float(np.mean(_do_mot_bo(mau, ten, pre, features_dir)))
            except SystemExit:
                raise
            except Exception as e:
                print(f"{ten:<24} {pre:<24} {'—':>10}  lỗi: {str(e)[:28]}")
                continue
            ket = "KHỚP" if tb >= DAT else ("gần" if tb >= 0.5 else "khác không gian")
            print(f"{ten:<24} {pre:<24} {tb:>10.4f}  {ket}")
            if tot is None or tb > tot[0]:
                tot = (tb, (ten, pre))
        if tot and tot[0] >= DAT:
            print(f"\n→ BTC dùng: {tot[1][0]} / {tot[1][1]}  (cosine {tot[0]:.4f})")
            print("  Điền vào data/config/clip_model.py và XOÁ dấu # TODO: BTC.")
            return 0
        print("\n→ KHÔNG ứng viên nào đạt. Vector BTC có thể không phải open_clip "
              "chuẩn, hoặc đã bị chuẩn hoá/nén khác. Hỏi BTC.")
        return 1

    # --- chế độ kiểm model đang cấu hình
    print(f"\nModel đang cấu hình: {CLIP_MODEL_NAME} / {CLIP_PRETRAINED} "
          f"({CLIP_EMBEDDING_DIM} chiều)\n")
    cos = _do_mot_bo(mau, CLIP_MODEL_NAME, CLIP_PRETRAINED, features_dir)

    print(f"{'keyframe_id':<22} {'cosine':>9}  kết quả")
    print("-" * 52)
    hong = 0
    for m, c in zip(mau, cos):
        if c >= DAT:
            kq = "ĐẠT"
        elif c < SAI_HAN:
            kq = "SAI MODEL"
            hong += 1
        else:
            kq = "NGHI NGỜ"
            hong += 1
        print(f"{m['kf_id']:<22} {c:>9.4f}  {kq}")

    tb = float(np.mean(cos))
    print("-" * 52)
    print(f"{'trung bình':<22} {tb:>9.4f}   nhỏ nhất {min(cos):.4f}")

    if hong == 0:
        print("\nĐẠT — query encoder cùng không gian với vector BTC.")
        return 0

    print(f"\n{'='*52}\nKHÔNG ĐẠT: {hong}/{len(cos)} mẫu lệch.")
    if tb < SAI_HAN:
        print("Cosine ≈ 0 → SAI MODEL HẲN. Mọi kết quả nhánh vector hiện tại là RÁC.")
        print("Chạy lại với --sweep để dò đúng model BTC đã dùng.")
    else:
        print("Cùng họ model nhưng lệch preprocessing/variant.")
        print("Nghi trước tiên: QuickGELU vs GELU, rồi tới resize/normalize.")
    print("KHÔNG nạp lại Milvus và KHÔNG tin kết quả search cho tới khi bảng này xanh.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
