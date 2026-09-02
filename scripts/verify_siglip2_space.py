# scripts/verify_siglip2_space.py — R3.K2a: KIỂM CHỨNG KHÔNG GIAN VECTOR SigLIP2
#
# ===== Vì sao KHÔNG dùng lại verify_clip_space.py =====
# Phép kiểm cũ so vector ta encode với `clip-features-32` BTC cấp sẵn, mốc là
# cosine ≈ 1.0. Mốc đó CHẾT khi đổi encoder: SigLIP2 là không gian khác hẳn,
# BTC không cấp feature SigLIP2 nào để đối chiếu, và cosine với vector CLIP sẽ
# ra ~0 kể cả khi mọi thứ hoàn toàn đúng.
#
# ===== Nên đổi mốc: so với CHÍNH INDEX CỦA MÌNH =====
# Câu hỏi cần trả lời không còn là "ta có cùng model với BTC không" mà là
# "code query hôm nay có cùng không gian với vector đã nằm trong index không".
# Đó mới là thứ hỏng được trong thực tế: index encode một lần trên máy khác,
# fp16, thiết bị khác; query encode mỗi lần chạy, fp32, CPU. Lệch nhau thì
# Milvus vẫn trả top-k với điểm trông bình thường và sai toàn bộ.
#
# Bốn phép kiểm, hỏng cái nào cũng thoát khác 0:
#   ① XÁC ĐỊNH   encode cùng một ảnh hai lần → cosine = 1.0.
#                Hỏng = model không tất định (dropout/BN còn ở chế độ train).
#   ② CÙNG KHÔNG GIAN  ảnh encode lại vs vector ĐÃ LƯU trong .npy → ≥ 0.999.
#                Đây là phép kiểm chính. Hỏng = index và query khác model,
#                khác preprocessing, hoặc file .npy thuộc lần encode khác.
#   ③ CHUẨN HOÁ  norm ≈ 1.0 trên mẫu (bất biến 5 — index và query đều L2,
#                metric Milvus là COSINE).
#   ④ ĐỘ PHỦ     video trong shots.parquet mà index thiếu; và tỉ lệ frame nằm
#                NGOÀI mọi shot — những frame đó bị `group_by_shot=True` loại
#                lặng lẽ khỏi kết quả search, tức là vector đã encode nhưng
#                không bao giờ dùng được.
#
# ⚠️ Không có phép kiểm text↔ảnh ở đây. Cosine text-ảnh vốn chỉ ~0.1–0.3 kể cả
# khi đúng hoàn toàn, nên không có ngưỡng nào phân biệt được đúng/sai — cùng lý
# do verify_clip_space.py chọn so ảnh-ảnh.
#
# ===== Chạy =====
#   python scripts/verify_siglip2_space.py                 # 20 mẫu
#   python scripts/verify_siglip2_space.py --samples 50
#   python scripts/verify_siglip2_space.py --skip-coverage # bỏ ④ (đọc parquet chậm)
#
# Exit code: 0 = tất cả ĐẠT · 1 = có phép kiểm trượt · 2 = thiếu dữ liệu/thư viện.

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from data.config.siglip2_model import (  # noqa: E402
    SIGLIP2_EMBEDDING_DIM,
    SIGLIP2_MODEL_NAME,
    SIGLIP2_PRETRAINED,
    siglip2_emb_dir,
)

SHOTS_PATH = REPO_ROOT / "data" / "derived" / "shots.parquet"

DAT_CUNG_KHONG_GIAN = 0.999   # ② — cùng ảnh, cùng model → trùng khít
DAT_XAC_DINH = 0.99999        # ① — cùng ảnh, cùng model, phải trùng hẳn
NORM_SAI_SO = 1e-3            # ③

# ===== Hai kiểu hỏng KHÁC HẲN NHAU, đừng gộp làm một =====
# Dưới ngưỡng này = SAI MODEL: hai không gian vector không liên quan gì nhau,
# cosine giữa hai vector ngẫu nhiên 1152 chiều nằm quanh 0. Đây là hỏng CHẾT
# NGƯỜI — mọi kết quả nhánh vector thành rác.
SAI_MODEL = 0.10
# Trong khoảng [SAI_MODEL, DAT_CUNG_KHONG_GIAN) = CÙNG không gian nhưng KHÔNG
# cùng tấm ảnh. Đo được: hai frame kề nhau cùng cảnh cho ~0,91. Nguyên nhân là
# lệch ánh xạ frame→ảnh (xem `_duong_dan_ca_hai_nguon`), KHÔNG phải lệch encoder
# — nên nó không chặn quyết định đổi encoder, nhưng phải được báo cáo vì cùng
# ánh xạ đó cấp ảnh bằng chứng cho Q&A.
# Vượt tỉ lệ này thì mới coi là hỏng hệ thống chứ không phải vài ca lẻ.
TI_LE_LECH_ANH_TOI_DA = 0.25


def _nap_model():
    """Nạp model + preprocess ĐÚNG như `siglip2_query.py` production làm.

    Cố ý KHÔNG dùng lại `siglip2_query._get_model()`: hàm đó chỉ trả model và
    tokenizer, không trả `preprocess` của ảnh — mà chính preprocessing mới là
    thủ phạm quen thuộc khi hai bên lệch không gian (resize/crop/normalize).
    Ở đây phải dựng lại đầy đủ để kiểm được cả phần đó.
    """
    try:
        import open_clip
        import torch
        from PIL import Image  # noqa: F401 — kiểm sớm để báo lỗi gọn
    except ImportError as e:
        print(f"THIẾU THƯ VIỆN ({e}). Cần: open_clip_torch, torch, pillow", file=sys.stderr)
        raise SystemExit(2)

    model, _, preprocess = open_clip.create_model_and_transforms(
        SIGLIP2_MODEL_NAME, pretrained=SIGLIP2_PRETRAINED
    )
    model = model.eval()
    return model, preprocess, torch


def _encode(model, preprocess, torch, path: Path) -> np.ndarray:
    from PIL import Image

    with torch.no_grad():
        v = model.encode_image(preprocess(Image.open(path).convert("RGB")).unsqueeze(0))
        v = v / v.norm(dim=-1, keepdim=True)
    return v[0].float().cpu().numpy().astype(np.float32)


_KHONG_TON_TAI = Path("__khong_co_raw__")


def _duong_dan_ca_hai_nguon(video_id: str, frame_idx: int) -> list[tuple[str, Path]]:
    """Mọi ảnh có thể ĐÃ sinh ra vector của frame này — [(nguồn, path), ...].

    ⚠️ Vì sao phải thử CẢ HAI nguồn thay vì tin resolver một lần:
    `encode_siglip2.py::build_index()` gom ảnh từ hai nơi vào cùng một danh sách —
    derived 1 fps (`keyframes.parquet`) và keyframe BTC (`frame_map`) — nên hàng
    thứ i của `.npy` có thể thuộc nguồn nào cũng được. Trong khi
    `resolve_frame_path()` LUÔN ưu tiên raw BTC.

    Hai ảnh "cùng frame_idx" từ hai nguồn không nhất thiết trùng pixel: một bên
    là I-frame BTC đã bù offset, một bên là frame ffmpeg trích ở 1 fps. Đo được
    hôm nay: chúng lệch nhau cosine ≈ 0,909 — tức hai khoảnh khắc kề nhau cùng
    cảnh, KHÔNG phải sai model (sai model cho ≈ 0).

    So nhầm nguồn làm phép kiểm báo TRƯỢT giả. Thử cả hai và lấy cái khớp nhất
    mới trả lời đúng câu hỏi cần hỏi: "vector đã lưu có phải do CHÍNH code
    encode hiện tại sinh ra từ MỘT trong hai ảnh hợp lệ không".
    """
    from backend.common.frame_assets import resolve_frame_path

    ra: list[tuple[str, Path]] = []
    r = resolve_frame_path(video_id, frame_idx=frame_idx)
    if r.path is not None:
        ra.append((r.source or "?", r.path))
    # Ép nhánh derived bằng cách trỏ raw_root vào chỗ không tồn tại — dùng đúng
    # API công khai của resolver, không tự ghép đường dẫn (bất biến AGENTS.md).
    r2 = resolve_frame_path(video_id, frame_idx=frame_idx, raw_root=_KHONG_TON_TAI)
    if r2.path is not None and all(r2.path != p for _, p in ra):
        ra.append((r2.source or "derived", r2.path))
    return ra


def _lay_mau(emb_dir: Path, n: int, seed: int) -> list[dict]:
    """n mẫu (video, chỉ số hàng, frame_idx, các ảnh ứng viên) rải trên NHIỀU video.

    Rải nhiều video chứ không dồn một video: một video encode lỗi lẻ có thể làm
    cả bảng đỏ hoặc — tệ hơn — cả bảng xanh giả nếu vô tình chọn đúng video tốt.
    """
    files = sorted(p for p in emb_dir.glob("*.npy") if not p.name.endswith(".frames.npy"))
    if not files:
        print(f"KHÔNG THẤY vector nào trong {emb_dir}", file=sys.stderr)
        raise SystemExit(2)

    rng = random.Random(seed)
    rng.shuffle(files)

    mau: list[dict] = []
    for p in files:
        if len(mau) >= n:
            break
        video_id = p.stem
        fp = emb_dir / f"{video_id}.frames.npy"
        if not fp.exists():
            continue
        frames = np.load(fp)
        if len(frames) == 0:
            continue
        # Thử vài vị trí ngẫu nhiên trong video: không phải frame nào cũng còn
        # ảnh trên đĩa (keyframe BTC thưa, derived có thể đã dọn).
        for _ in range(8):
            i = rng.randrange(len(frames))
            f = int(frames[i])
            anh = _duong_dan_ca_hai_nguon(video_id, f)
            if anh:
                mau.append({"video_id": video_id, "row": i, "frame_idx": f, "anh": anh})
                break
    return mau


def _kiem_do_phu(emb_dir: Path) -> tuple[bool, list[str]]:
    """④ — video thiếu vector, và frame nằm ngoài mọi shot (bị gom-shot loại)."""
    dong: list[str] = []
    try:
        import pandas as pd
    except ImportError:
        return True, ["  [bỏ qua] không có pandas"]

    if not SHOTS_PATH.exists():
        return True, [f"  [bỏ qua] không thấy {SHOTS_PATH.name}"]

    df = pd.read_parquet(SHOTS_PATH, columns=["video_id", "start_frame", "end_frame"])
    video_co_shot = set(df["video_id"].astype(str).unique())
    video_co_vector = {
        p.stem for p in emb_dir.glob("*.npy") if not p.name.endswith(".frames.npy")
    }

    thieu = sorted(video_co_shot - video_co_vector)
    dong.append(f"  video có shot: {len(video_co_shot)} · có vector: {len(video_co_vector)}")
    if thieu:
        dong.append(f"  ⚠ {len(thieu)} video CÓ shot nhưng THIẾU vector: {thieu[:5]}")
    else:
        dong.append("  ✓ mọi video có shot đều có vector")

    # Frame ngoài shot: đếm trên một mẫu video để khỏi đọc hết 521K frame.
    khoang: dict[str, list[tuple[int, int]]] = {}
    for vid, s, e in df.itertuples(index=False):
        khoang.setdefault(str(vid), []).append((int(s), int(e)))

    mau_video = sorted(video_co_vector)[:40]
    tong = ngoai = 0
    for vid in mau_video:
        fp = emb_dir / f"{vid}.frames.npy"
        if not fp.exists() or vid not in khoang:
            continue
        rs = sorted(khoang[vid])
        for f in np.load(fp).tolist():
            tong += 1
            if not any(s <= f <= e for s, e in rs):
                ngoai += 1
    if tong:
        ti_le = ngoai / tong
        dong.append(
            f"  frame ngoài mọi shot: {ngoai}/{tong} ({ti_le:.1%}) trên {len(mau_video)} video mẫu"
        )
        if ti_le > 0.05:
            dong.append(
                "  ⚠ tỉ lệ này bị `group_by_shot=True` loại LẶNG LẼ khỏi kết quả search — "
                "vector đã encode nhưng không dùng được"
            )
    return not thieu, dong


def main() -> int:
    ap = argparse.ArgumentParser(description="Kiểm chứng không gian vector SigLIP2 (R3.K2a)")
    ap.add_argument("--samples", type=int, default=20, help="số mẫu ảnh (mặc định 20)")
    ap.add_argument("--seed", type=int, default=42, help="cố định để chạy lại ra cùng mẫu")
    ap.add_argument("--skip-coverage", action="store_true", help="bỏ phép kiểm ④")
    args = ap.parse_args()

    emb_dir = siglip2_emb_dir()
    print(f"model    : {SIGLIP2_MODEL_NAME} / {SIGLIP2_PRETRAINED} ({SIGLIP2_EMBEDDING_DIM} chiều)")
    print(f"vector   : {emb_dir}")
    if not emb_dir.is_dir():
        print(f"KHÔNG THẤY {emb_dir} — chạy scripts/encode_siglip2.py trước.", file=sys.stderr)
        return 2

    mau = _lay_mau(emb_dir, args.samples, args.seed)
    if not mau:
        print("KHÔNG ghép được mẫu nào (không frame nào còn ảnh trên đĩa).", file=sys.stderr)
        return 2
    if len(mau) < args.samples:
        print(f"[cảnh báo] chỉ ghép được {len(mau)}/{args.samples} mẫu — "
              "phần lớn frame không còn ảnh trên đĩa.")

    print(f"\nnạp model ...", flush=True)
    model, preprocess, torch = _nap_model()

    hong = 0

    # ---------------------------------------------------------------- ① xác định
    print("\n① XÁC ĐỊNH — cùng một ảnh encode hai lần")
    anh_dau = mau[0]["anh"][0][1]
    a = _encode(model, preprocess, torch, anh_dau)
    b = _encode(model, preprocess, torch, anh_dau)
    cos_xd = float(np.dot(a, b))
    dat_xd = cos_xd >= DAT_XAC_DINH
    print(f"  cosine = {cos_xd:.6f}   {'ĐẠT' if dat_xd else 'TRƯỢT — model không tất định'}")
    hong += 0 if dat_xd else 1

    # -------------------------------------------------- ② cùng không gian với index
    print(f"\n② CÙNG KHÔNG GIAN — ảnh encode lại vs vector đã lưu ({len(mau)} mẫu)")
    print(f"  {'video':<12} {'frame':>9} {'cosine':>10} {'nguồn':<9} kết quả")
    print("  " + "-" * 56)
    cos_list: list[float] = []
    norms: list[float] = []
    lech_anh: list[tuple[str, int, float]] = []
    cache: dict[str, np.ndarray] = {}
    for m in mau:
        vid = m["video_id"]
        if vid not in cache:
            cache[vid] = np.load(emb_dir / f"{vid}.npy")
        luu = cache[vid][m["row"]].astype(np.float32)
        norms.append(float(np.linalg.norm(luu)))
        # Lấy nguồn KHỚP NHẤT: hàng .npy này do một trong hai nguồn sinh ra, ta
        # không biết cái nào (xem `_duong_dan_ca_hai_nguon`). Dừng sớm khi đã đạt
        # để khỏi encode thừa.
        tot_c, tot_nguon = -1.0, "?"
        for nguon, path in m["anh"]:
            c = float(np.dot(luu, _encode(model, preprocess, torch, path)))
            if c > tot_c:
                tot_c, tot_nguon = c, nguon
            if tot_c >= DAT_CUNG_KHONG_GIAN:
                break
        cos_list.append(tot_c)
        if tot_c >= DAT_CUNG_KHONG_GIAN:
            kq = "ĐẠT"
        elif tot_c < SAI_MODEL:
            kq = "SAI MODEL"
            hong += 1
        else:
            kq = "lệch ảnh"
            lech_anh.append((vid, m["frame_idx"], tot_c))
        print(f"  {vid:<12} {m['frame_idx']:>9} {tot_c:>10.6f} {tot_nguon:<9} {kq}")

    tb = float(np.mean(cos_list))
    khop_khit = sum(1 for c in cos_list if c >= DAT_CUNG_KHONG_GIAN)
    print("  " + "-" * 56)
    print(f"  trung bình {tb:.6f} · nhỏ nhất {min(cos_list):.6f}")
    print(f"  khớp khít {khop_khit}/{len(cos_list)} · lệch ảnh {len(lech_anh)} · "
          f"sai model {sum(1 for c in cos_list if c < SAI_MODEL)}")

    if lech_anh:
        ti_le = len(lech_anh) / len(cos_list)
        print(f"\n  ⚠ {len(lech_anh)} mẫu CÙNG không gian nhưng KHÔNG cùng tấm ảnh "
              f"({ti_le:.0%}):")
        for vid, f, c in lech_anh:
            print(f"      {vid} frame {f} → cosine {c:.4f}")
        print("    Đây là lệch ÁNH XẠ frame→ảnh, không phải lệch encoder (lệch encoder")
        print("    cho cosine ≈ 0). Không chặn quyết định đổi encoder, NHƯNG cùng ánh xạ")
        print("    đó cấp ảnh bằng chứng cho Q&A — cần Data Factory soi lại.")
        if ti_le > TI_LE_LECH_ANH_TOI_DA:
            print(f"    TRƯỢT: vượt trần {TI_LE_LECH_ANH_TOI_DA:.0%} → nghi lỗi ánh xạ hệ thống.")
            hong += 1

    # ------------------------------------------------------------------ ③ chuẩn hoá
    print("\n③ CHUẨN HOÁ L2 — norm của vector trong index")
    lech = [n for n in norms if abs(n - 1.0) > NORM_SAI_SO]
    print(f"  min {min(norms):.6f} · max {max(norms):.6f} · lệch quá {NORM_SAI_SO}: {len(lech)}")
    if lech:
        print("  TRƯỢT — index chưa chuẩn hoá L2 mà metric Milvus là COSINE")
        hong += 1
    else:
        print("  ĐẠT")

    # -------------------------------------------------------------------- ④ độ phủ
    if not args.skip_coverage:
        print("\n④ ĐỘ PHỦ")
        ok_phu, dong = _kiem_do_phu(emb_dir)
        for d in dong:
            print(d)
        hong += 0 if ok_phu else 1

    # ------------------------------------------------------------------- kết luận
    print("\n" + "=" * 56)
    if hong == 0:
        print("ĐẠT — index SigLIP2 cùng không gian với code query hiện tại.")
        print(f"  {khop_khit}/{len(cos_list)} mẫu khớp khít (cosine ≥ {DAT_CUNG_KHONG_GIAN}).")
        if lech_anh:
            print(f"  {len(lech_anh)} mẫu lệch ánh xạ frame→ảnh — xem cảnh báo ở ② "
                  "(không chặn đổi encoder).")
        print("Đổi encoder bằng VECTOR_BACKEND=siglip2 là an toàn.")
        return 0

    print(f"KHÔNG ĐẠT: {hong} phép kiểm trượt.")
    if cos_list and min(cos_list) < SAI_MODEL:
        print("Có mẫu cosine ≈ 0 → index và query KHÁC MODEL HẲN.")
        print("Mọi kết quả nhánh vector là RÁC. Nghi trước tiên: đổi "
              "SIGLIP2_MODEL_NAME/PRETRAINED mà chưa encode lại.")
    print("KHÔNG đặt VECTOR_BACKEND=siglip2 cho tới khi bảng này xanh.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
