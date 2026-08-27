"""Luồng ứng viên SigLIP2 quét thẳng toàn kho — cứu những câu đường ống chính đánh rơi.

Vì sao cần: đo được đường ống chính (gom shot -> cắt top-k -> cấp slot) LÀM MẤT
đáp án ở nhiều câu mà bản thân encoder tìm ra được. Quét phẳng toàn bộ 521.526
vector bằng numpy, không gom shot, không cắt sớm, cho thấy shot đúng nằm ở:

    query-p1-2   hạng 14      (đường ống chính: không có trong 100)
    query-p1-8   hạng 30      (đường ống chính: không có trong 100)
    query-p1-14  hạng 30      (đường ống chính: không có trong 100)
    query-p1-21  hạng 44      (đường ống chính: hạng 62)
    query-p1-22  hạng  8      (đường ống chính: hạng 18)
    query-p1-5   hạng 12      (đường ống chính: hạng 23)

Nghĩa là mất mát không nằm ở model mà nằm ở các bước LỌC phía sau. Luồng này đi
vòng qua toàn bộ các bước đó: một phép nhân ma trận, dưới một giây, không Milvus.

Mỗi anchor giữ bảng riêng rồi xen kẽ (luật 2 của build_kis_submission), và giới
hạn số frame mỗi video để một video không chiếm hết chỗ.

Chạy:
    .venv/bin/python3.14 scripts/build_sigdirect_stream.py --out submissions/kis_sigdirect
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

TOTAL = 100
PER_VIDEO = 12     # số frame tối đa lấy từ một video cho mỗi anchor
PER_SHOT = 2       # số frame tối đa lấy từ MỘT SHOT — xem chú thích dưới
PER_ANCHOR = 60    # độ sâu bảng riêng của mỗi anchor


def _shot_index():
    """Tra shot theo khoảng frame. Tên keyframe không join được với bảng shot,
    phải tra bằng khoảng — đây đúng là lỗi đã làm `search()` trả rỗng im lặng."""
    import pandas as pd
    sh = pd.read_parquet(REPO / "data/derived/shots.parquet")
    idx = {}
    for v, g in sh.sort_values("start_frame").groupby("video_id"):
        idx[str(v)] = (g.start_frame.astype(int).tolist(),
                       g.end_frame.astype(int).tolist(),
                       g.shot_id.astype(str).tolist())
    return idx


def _shot_of(idx, video_id: str, frame: int):
    from bisect import bisect_right
    r = idx.get(video_id)
    if not r:
        return None
    starts, ends, ids = r
    k = bisect_right(starts, frame) - 1
    return ids[k] if k >= 0 and frame <= ends[k] else None


def _stream(Vf, F, I, q, per_video: int, depth: int, shots=None,
            per_shot: int = PER_SHOT) -> list[tuple[str, int]]:
    """Bảng riêng của MỘT anchor, chặn hai mức: mỗi shot tối đa `per_shot` frame,
    mỗi video tối đa `per_video` frame.

    Vì sao phải chặn theo SHOT chứ không chỉ theo video: một shot dài chứa hàng
    chục frame gần như giống hệt nhau, tất cả cùng ăn điểm cao, và chúng ăn hết
    hạn ngạch của video trước khi tới lượt shot chứa đáp án. Đo được ở câu p1-2:
    shot đúng (`s0021`, chỉ dài 73 frame) đứng hạng 14 khi quét thô, nhưng biến
    mất khỏi bảng vì 13 hạng trên nó đều là frame của cùng một shot khác."""
    sc = Vf @ q
    order = np.argsort(-sc)[: depth * 60]
    out, n_video, n_shot = [], {}, {}
    for j in order:
        v = str(I[j])
        f = int(F[j])
        if n_video.get(v, 0) >= per_video:
            continue
        sid = _shot_of(shots, v, f) if shots else None
        if sid is not None:
            if n_shot.get(sid, 0) >= per_shot:
                continue
            n_shot[sid] = n_shot.get(sid, 0) + 1
        n_video[v] = n_video.get(v, 0) + 1
        out.append((v, f))
        if len(out) >= depth:
            break
    return out


def _interleave(streams: list[list], total: int = TOTAL) -> list:
    rows, seen = [], set()
    idx = [0] * len(streams)
    while len(rows) < total and any(i < len(st) for i, st in zip(idx, streams)):
        for j, st in enumerate(streams):
            while idx[j] < len(st) and st[idx[j]] in seen:
                idx[j] += 1
            if idx[j] < len(st) and len(rows) < total:
                rows.append(st[idx[j]])
                seen.add(st[idx[j]])
                idx[j] += 1
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plans", type=Path, default=REPO / "dev_set/queries/round1_kis_plans.json")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--per-video", type=int, default=PER_VIDEO)
    ap.add_argument("--per-shot", type=int, default=PER_SHOT)
    ap.add_argument("--depth", type=int, default=PER_ANCHOR)
    args = ap.parse_args()

    from scripts.siglip2_direct import encode, load_cache

    V, F, I = load_cache()
    Vf = V.astype(np.float32)
    shots = _shot_index()
    plans = json.loads(args.plans.read_text(encoding="utf-8"))
    args.out.mkdir(parents=True, exist_ok=True)

    for qid, plan in sorted(plans.items(), key=lambda kv: int(kv[0].split("-")[2])):
        anchors = plan["anchors"] + plan.get("hyp", [])
        streams = [_stream(Vf, F, I, encode([a])[0].astype(np.float32),
                           args.per_video, args.depth, shots, args.per_shot)
                   for a in anchors]
        rows = _interleave(streams)
        for st in streams:                      # còn thiếu thì vét cho đủ 100
            for k in st:
                if len(rows) >= TOTAL:
                    break
                if k not in rows:
                    rows.append(k)
        with (args.out / f"{qid}.csv").open("w", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerows([[v, f] for v, f in rows])
        print(f"  {qid:22s} {len(rows):3d} dòng · {len({v for v, _ in rows}):3d} video")

    print(f"XONG · {len(plans)} file trong {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
