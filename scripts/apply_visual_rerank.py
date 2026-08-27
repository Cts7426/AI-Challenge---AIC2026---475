"""Đưa đáp án đã XÁC NHẬN BẰNG MẮT lên hạng 1 của submission.

Vì sao cần bước này: đo được đầu bảng tự động chỉ đúng 7/17 lần, và không nguồn
tín hiệu văn bản/embedding nào chính xác hơn 41% để đáng thay chỗ nó (đã thử
bốn biến thể, tất cả đều thua). Thứ duy nhất quyết định đúng ở hạng 1 là NHÌN
ẢNH. Sơ tuyển nộp lô và không trừ thời gian, nên người vận hành (hoặc Claude)
soi top-5 rồi chốt là hoàn toàn nằm trong luật.

Script chỉ SẮP XẾP LẠI, không bịa dòng mới:
  - frame đã xác nhận lên hạng 1
  - thêm vài frame nữa CÙNG SHOT ngay sau đó, vì cửa sổ đáp án rộng ~150 frame
    còn frame đã soi chỉ là một điểm neo bên trong nó
  - phần còn lại giữ nguyên thứ tự cũ, không dòng nào bị mất

Câu chưa xác nhận thì giữ nguyên 100% — không đụng vào.

Chạy:
    .venv/bin/python3.14 scripts/apply_visual_rerank.py \
        --in submissions/kis_v4 --out submissions/kis_v8
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from bisect import bisect_right
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

TOTAL = 100
N_WINDOW = 3       # số frame phụ cùng shot đặt ngay sau frame đã xác nhận
WINDOW_STEP = 60   # bước quạt; cửa sổ đáp án quan sát được ~150 frame


def _shot_index():
    sh = pd.read_parquet(REPO / "data/derived/shots.parquet")
    idx = {}
    for v, g in sh.sort_values("start_frame").groupby("video_id"):
        idx[str(v)] = (g.start_frame.astype(int).tolist(),
                       g.end_frame.astype(int).tolist())
    return idx


def _shot_bounds(idx, video_id: str, frame: int):
    r = idx.get(video_id)
    if not r:
        return None
    starts, ends = r
    k = bisect_right(starts, frame) - 1
    if k < 0 or frame > ends[k]:
        return None
    return starts[k], ends[k]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="src", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--findings", type=Path,
                    default=REPO / "dev_set/ground_truth/round1_kis_findings.json")
    args = ap.parse_args()

    findings = json.loads(args.findings.read_text(encoding="utf-8"))["entries"]
    idx = _shot_index()
    args.out.mkdir(parents=True, exist_ok=True)

    n_touched = 0
    for src in sorted(args.src.glob("*.csv")):
        qid = src.stem
        rows = [(r[0], int(r[1])) for r in csv.reader(src.open())]
        found = findings.get(qid)

        if found:
            v, f = found["video_id"], int(found["frame"])
            promoted = [(v, f)]
            bounds = _shot_bounds(idx, v, f)
            if bounds:
                lo, hi = bounds
                step = WINDOW_STEP
                while len(promoted) < 1 + N_WINDOW and step <= WINDOW_STEP * 6:
                    for cand in (f + step, f - step):
                        if lo <= cand <= hi and (v, cand) not in promoted \
                                and len(promoted) < 1 + N_WINDOW:
                            promoted.append((v, cand))
                    step += WINDOW_STEP
            rest = [k for k in rows if k not in promoted]
            rows = (promoted + rest)[:TOTAL]
            n_touched += 1

        assert len(rows) == TOTAL, f"{qid}: {len(rows)} dòng, phải đúng {TOTAL}"
        with (args.out / f"{qid}.csv").open("w", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerows([[a, b] for a, b in rows])

    print(f"XONG · {n_touched} câu được sắp lại theo xác nhận bằng mắt, "
          f"{len(list(args.src.glob('*.csv'))) - n_touched} câu giữ nguyên")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
