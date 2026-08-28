"""Tìm bằng CẢ HAI encoder rồi xen kẽ ở MỨC SHOT.

Vì sao phải là hai: đo công bằng (cùng câu truy vấn, cùng quét phẳng, xếp hạng
theo shot để mật độ keyframe khác nhau không làm lệch) cho thấy hai model KHÔNG
phải một hơn một kém — chúng mạnh ở những câu khác nhau:

    câu      CLIP   SigLIP2          câu      CLIP   SigLIP2
    p1-11       1       5            p1-12   1078      46
    p1-13       1     133            p1-22    334       2
    p1-19       1    1165            p1-5     175       9
    p1-24      18     196            p1-7      18       1
    p1-2      991    2541            p1-8    6705    1725

    CLIP    Final 0.4600 · hạng-1 4/18 · top-20 12/18
    SigLIP2 Final 0.3911 · hạng-1 2/18 · top-20 10/18
    HỢP     ——                        · top-20 15/18   <- lý do có file này

CLIP thắng 8 câu, SigLIP2 thắng 7. Chọn một là vứt đi một nửa. Xen kẽ thì bảng
ứng viên đưa cho MẮT NGƯỜI phủ 15/18 câu trong 20 ô đầu thay vì 12/18.

Xen kẽ chứ không cộng điểm: hai không gian vector khác thang nhau (CLIP cosine
~0,2-0,3; SigLIP2 nén quanh 0), cộng thẳng là một bên nuốt hết. Xen kẽ chỉ dùng
THỨ HẠNG nên không cần chuẩn hoá gì.

CLIP đi trước ở mỗi vòng vì nó nhỉnh hơn ở hạng 1 (4/18 so với 2/18).

Chạy:
    python scripts/dual_search.py --text "a red drum kit on a school stage" --top 24
"""
from __future__ import annotations

import gc
import sys
from bisect import bisect_right
from functools import lru_cache
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

CLIP_CACHE = REPO / "data/derived/clip_flat.npz"
SCAN_CAP = 20000        # quét sâu bao nhiêu vector thô trước khi gộp shot


@lru_cache(maxsize=1)
def _shot_index():
    import pandas as pd
    sh = pd.read_parquet(REPO / "data/derived/shots.parquet")
    idx = {}
    for v, g in sh.sort_values("start_frame").groupby("video_id"):
        idx[str(v)] = (g.start_frame.astype(int).tolist(),
                       g.end_frame.astype(int).tolist(),
                       g.shot_id.astype(str).tolist())
    return idx


def _shot_of(video_id: str, frame: int):
    r = _shot_index().get(video_id)
    if not r:
        return None
    starts, ends, ids = r
    k = bisect_right(starts, frame) - 1
    return ids[k] if k >= 0 and frame <= ends[k] else None


def build_clip_cache() -> None:
    """Gộp .npy CLIP của BTC thành một mảng phẳng + bảng tra (video, frame).

    Hàng thứ i của mỗi .npy ứng với keyframe thứ i của video đó, nên phải đi qua
    `frame_map` mới ra frame index thật — tên file keyframe KHÔNG phải frame_id.
    """
    import glob
    import pandas as pd

    fm = pd.read_parquet(REPO / "data/derived/frame_map.parquet")
    by_v = {}
    for v, g in fm.groupby("video_id"):
        g = g.sort_values("btc_ordinal")
        by_v[str(v)] = g.frame_idx_corrected.astype(int).to_numpy()

    vecs, frames, vids = [], [], []
    for p in sorted(glob.glob(str(REPO / "data/raw/btc/clip-features-32/*.npy"))):
        v = Path(p).stem
        fr = by_v.get(v)
        if fr is None:
            continue
        a = np.load(p).astype(np.float16)
        n = min(len(a), len(fr))
        vecs.append(a[:n]); frames.append(fr[:n]); vids.append(np.full(n, v, dtype="<U16"))
    V = np.vstack(vecs)
    V = V / np.linalg.norm(V.astype(np.float32), axis=1, keepdims=True).astype(np.float16)
    CLIP_CACHE.parent.mkdir(parents=True, exist_ok=True)
    np.savez(CLIP_CACHE, V=V, F=np.concatenate(frames), I=np.concatenate(vids))
    print(f"cache CLIP: {V.shape} -> {CLIP_CACHE}")


_clip = _sig = None


def free_clip() -> None:
    """Trả lại 0,36 GB. Gọi ngay sau khi đã lấy xong bảng xếp hạng của CLIP."""
    global _clip
    _clip = None
    gc.collect()


def free_sig() -> None:
    """Trả lại 2,4 GB."""
    global _sig
    _sig = None
    gc.collect()


def _load_clip():
    global _clip
    if _clip is None:
        if not CLIP_CACHE.exists():
            build_clip_cache()
        z = np.load(CLIP_CACHE, allow_pickle=False)
        _clip = (np.ascontiguousarray(z["V"], dtype=np.float32), z["F"], z["I"])
        gc.collect()
    return _clip


def _load_sig():
    global _sig
    if _sig is None:
        from scripts.siglip2_direct import load_cache
        V, F, I = load_cache()
        _sig = (np.ascontiguousarray(V, dtype=np.float32), F, I)
        del V
        gc.collect()
    return _sig


def _shot_list(pack, q: np.ndarray, depth: int, per_video: int) -> list[tuple[str, int]]:
    """Danh sách (video, frame) đã gộp về shot: mỗi shot đúng MỘT ảnh đại diện.

    Gộp shot trước khi cắt là điều bắt buộc: một shot dài chứa hàng chục frame
    gần như giống hệt nhau, không gộp thì chúng chiếm hết chỗ của shot khác.
    """
    Vf, F, I = pack
    sc = Vf @ q
    cap = min(depth * 400, len(sc) - 1)
    part = np.argpartition(-sc, cap)[:cap]
    order = part[np.argsort(-sc[part])]
    out, seen_shot, n_video = [], set(), {}
    for j in order:
        v = str(I[j]); f = int(F[j])
        s = _shot_of(v, f)
        key = s if s is not None else (v, f // 200)
        if key in seen_shot or n_video.get(v, 0) >= per_video:
            continue
        seen_shot.add(key); n_video[v] = n_video.get(v, 0) + 1
        out.append((v, f))
        if len(out) >= depth:
            break
    return out


def dual_candidates(texts: list[str], top: int = 24, per_video: int = 3,
                    use_clip: bool = True, use_sig: bool = True) -> list[tuple[str, int]]:
    """Ứng viên hợp nhất từ hai encoder cho một danh sách câu mô tả.

    Mỗi (encoder, câu mô tả) giữ bảng riêng rồi xen kẽ — KHÔNG cộng điểm giữa các
    câu mô tả: đề KIS hay kể một chuỗi, mỗi câu tả một khoảnh khắc, nên frame đúng
    chỉ khớp mạnh với MỘT câu. Cộng dồn thưởng cho shot khớp lờ mờ với tất cả.
    """
    texts = [t for t in texts if t and t.strip()]
    if not texts:
        return []
    depth = max(top, 40)
    streams = []
    # Chạy XONG hẳn một encoder rồi mới nạp encoder kia, và giải phóng ở giữa.
    # Giữ đồng thời hai mảng float32 (CLIP 0,36 GB + SigLIP2 2,4 GB) cùng với
    # Milvus và Elasticsearch đang chạy thì tiến trình bị hệ điều hành giết ngang
    # — không có traceback, chỉ im lặng thoát. Đã dính đúng một lần.
    if use_clip:
        from backend.retrieval.text_query import encode_text as clip_enc
        pack = _load_clip()
        for t in texts:
            streams.append(_shot_list(pack, np.asarray(clip_enc(t), dtype=np.float32),
                                      depth, per_video))
        free_clip()
    if use_sig:
        from scripts.siglip2_direct import encode as sig_enc
        pack = _load_sig()
        for t in texts:
            streams.append(_shot_list(pack, sig_enc([t])[0].astype(np.float32),
                                      depth, per_video))

    rows, seen, i = [], set(), [0] * len(streams)
    while len(rows) < top and any(i[j] < len(s) for j, s in enumerate(streams)):
        for j, s in enumerate(streams):
            while i[j] < len(s) and s[i[j]] in seen:
                i[j] += 1
            if i[j] < len(s) and len(rows) < top:
                rows.append(s[i[j]]); seen.add(s[i[j]]); i[j] += 1
    return rows


def dual_candidates_batch(jobs: dict[str, list[str]], top: int = 24,
                          per_video: int = 3) -> dict[str, list[tuple[str, int]]]:
    """Như `dual_candidates` nhưng cho NHIỀU việc một lượt.

    Vì sao cần: gọi lẻ từng việc thì mỗi lần lại nạp rồi giải phóng cache
    (CLIP 0,36 GB + SigLIP2 2,4 GB) — 20 câu x 5 làn là 100 lần nạp lại. Ở đây
    nạp CLIP MỘT lần cho mọi việc, giải phóng, rồi nạp SigLIP2 một lần, cuối
    cùng mới xen kẽ. Vẫn không bao giờ giữ hai mảng cùng lúc.
    """
    depth = max(top, 40)
    per_enc: dict[str, list[list]] = {k: [] for k in jobs}

    from backend.retrieval.text_query import encode_text as clip_enc
    pack = _load_clip()
    for k, texts in jobs.items():
        for t in texts:
            if t and t.strip():
                per_enc[k].append(_shot_list(pack, np.asarray(clip_enc(t), dtype=np.float32),
                                             depth, per_video))
    free_clip()

    from scripts.siglip2_direct import encode as sig_enc
    pack = _load_sig()
    for k, texts in jobs.items():
        for t in texts:
            if t and t.strip():
                per_enc[k].append(_shot_list(pack, sig_enc([t])[0].astype(np.float32),
                                             depth, per_video))
    free_sig()

    out = {}
    for k, streams in per_enc.items():
        rows, seen, i = [], set(), [0] * len(streams)
        while len(rows) < top and any(i[j] < len(st) for j, st in enumerate(streams)):
            for j, st in enumerate(streams):
                while i[j] < len(st) and st[i[j]] in seen:
                    i[j] += 1
                if i[j] < len(st) and len(rows) < top:
                    rows.append(st[i[j]]); seen.add(st[i[j]]); i[j] += 1
        out[k] = rows
    return out


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--text", action="append", required=True)
    ap.add_argument("--top", type=int, default=24)
    ap.add_argument("--sheet", type=Path, help="ghi luôn một tấm lưới ảnh")
    ap.add_argument("--rebuild-clip", action="store_true")
    args = ap.parse_args()

    if args.rebuild_clip and CLIP_CACHE.exists():
        CLIP_CACHE.unlink()
    rows = dual_candidates(args.text, args.top)
    for i, (v, f) in enumerate(rows, 1):
        print(f"{i:3d}. {v}:{f}")
    if args.sheet:
        from scripts.contact_sheet import build
        build(rows, args.sheet)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
