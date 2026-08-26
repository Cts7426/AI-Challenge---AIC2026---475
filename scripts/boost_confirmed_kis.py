"""Tăng độ sâu submission KIS cho các câu ĐÃ xác nhận video bằng mắt.

Vì sao cần: pipeline xếp hạng theo shot nên một video đúng có thể chỉ được 2-3
dòng trong 100 slot — không đủ phủ cửa sổ đáp án [s,e]. Khi người/agent đã soi
ảnh và chắc chắn video nào đúng, "sai video = 0 điểm" không còn là rủi ro chính;
rủi ro chính là trượt cửa sổ frame. CLAUDE.md §7: frame_id nộp KHÔNG cần là
keyframe đã index, nên phủ dày quanh frame đã xác nhận là miễn phí.

Chiến lược mỗi câu đã xác nhận:
  - slot 1        : frame đã xác nhận
  - slot 2..N_NEAR: quạt đều quanh nó (bước STEP) — bắt cửa sổ [s,e] dù lệch
  - kế tiếp       : các shot khác CÙNG video (search có filter_video_id)
  - đuôi          : giữ ứng viên video khác của submission gốc làm phương án dự phòng

Xen kẽ theo shot (CLAUDE.md mục 6 luật 3) vẫn được giữ ở phần giữa: mỗi shot
khác chỉ góp 1 dòng trước khi vòng lại.

Chạy:
    .venv/bin/python3.14 scripts/boost_confirmed_kis.py \
        --submission submissions/kis_claude --confirmed scratch/kis_round1/confirmed.json
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:  # chạy trực tiếp `python scripts/...` không có repo trong path
    sys.path.insert(0, str(REPO))
TOTAL = 100
N_NEAR = 14      # số dòng quạt quanh frame đã xác nhận
STEP = 90        # bước quạt; cửa sổ đáp án KIS quan sát được ~150 frame
N_SAME_VIDEO = 46  # số dòng cho các shot khác trong cùng video


def _n_frames() -> dict[str, int]:
    df = pd.read_parquet(REPO / "data/derived/video_info.parquet")
    return {str(r.video_id): int(r.n_frames) for r in df.itertuples()}


def _near_frames(frame: int, limit: int, n_max: int) -> list[int]:
    """Quạt đối xứng quanh `frame`, cắt về biên hợp lệ [0, n_max)."""
    out = [frame]
    step = STEP
    while len(out) < limit:
        for cand in (frame + step, frame - step):
            if 0 <= cand < n_max and cand not in out and len(out) < limit:
                out.append(cand)
        step += STEP
        if step > STEP * limit:  # hết chỗ quạt
            break
    return out


def boost(submission_dir: Path, confirmed: dict, dry_run: bool = False) -> None:
    from backend.retrieval.search import search

    nframes = _n_frames()
    queries = {
        q["query_id"]: q
        for q in json.loads(
            (REPO / "dev_set/manifests/batch1_round1_queries.json").read_text(encoding="utf-8")
        )["queries"]
    }
    anchors = {
        json.loads(line)["query_id"]: json.loads(line)["query_en"]
        for line in (REPO / "scratch/kis_round1/queries_kis.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    }

    for qid, info in sorted(confirmed.items()):
        path = submission_dir / f"{qid}.csv"
        original = [(r[0], int(r[1])) for r in csv.reader(path.open())]
        video_id, frame = info["video_id"], int(info["frame"])
        n_max = nframes.get(video_id, frame + 10_000)

        rows: list[tuple[str, int]] = [
            (video_id, f) for f in _near_frames(frame, N_NEAR, n_max)
        ]

        # Các shot KHÁC trong cùng video, xen kẽ mỗi shot một dòng.
        same = search(
            queries[qid]["query_vi"], query_en=anchors[qid],
            top_k=N_SAME_VIDEO, filter_video_id=video_id,
        )
        seen = {f for _, f in rows}
        for hit in same:
            fidx = hit["frame_idx"]
            if fidx is None or fidx in seen:
                continue
            rows.append((video_id, int(fidx)))
            seen.add(fidx)
            if len(rows) >= N_NEAR + N_SAME_VIDEO:
                break

        # Đuôi: ứng viên VIDEO KHÁC của submission gốc — phòng khi xác nhận sai.
        for vid, fidx in original:
            if len(rows) >= TOTAL:
                break
            if vid == video_id and fidx in seen:
                continue
            rows.append((vid, fidx))
            if vid == video_id:
                seen.add(fidx)

        # Chốt đúng 100 dòng: thiếu thì quạt thêm quanh frame đã xác nhận.
        extra = STEP // 2
        while len(rows) < TOTAL:
            cand = frame + extra
            if 0 <= cand < n_max and (video_id, cand) not in rows:
                rows.append((video_id, cand))
            extra += STEP // 2
            if extra > n_max:
                break
        rows = rows[:TOTAL]

        assert len(rows) == TOTAL, f"{qid}: {len(rows)} dòng, phải đúng {TOTAL}"
        assert all(0 <= f < nframes.get(v, 1 << 30) for v, f in rows), f"{qid}: frame ngoài biên"

        if not dry_run:
            with path.open("w", newline="", encoding="utf-8") as fh:
                csv.writer(fh).writerows([[v, f] for v, f in rows])
        print(f"{qid:20s} {video_id:10s} {sum(1 for v, _ in rows if v == video_id):3d}/100 dòng cùng video")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--submission", type=Path, required=True)
    parser.add_argument("--confirmed", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    confirmed = json.loads(args.confirmed.read_text(encoding="utf-8"))
    boost(args.submission, confirmed, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
