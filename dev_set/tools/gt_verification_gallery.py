"""Sinh trang HTML để người vận hành soát tay GT của một manifest đã đóng băng.

Vì sao cần: `batch1_holdout13`/`batch1_round1_queries` đứng yên ở
`verification_status="unknown"` không phải vì thiếu code mà vì chưa ai NHÌN
frame để xác nhận — đây là việc CHỈ người mới làm được (xem
`docs/product-spec.md` §Non-goals: không được tự suy/bịa GT). Script này chỉ
làm phần máy làm được: dựng lại đúng cặp (query, GT) qua `_load_frozen_inputs`
(cùng đường load evaluator thật dùng, tránh lệch logic) rồi tra keyframe gần
nhất ở đầu/cuối cửa sổ frame để hiển thị — không suy đoán, không tự chấm.

Chạy:
    python -m dev_set.tools.gt_verification_gallery --manifest batch1_holdout13
    python -m dev_set.tools.gt_verification_gallery --manifest batch1_holdout13 --out /tmp/gt_review.html

Sau khi soát xong, ghi lại quyết định bằng:
    python -m dev_set.tools.mark_verified --manifest batch1_holdout13 \
        --query-id KIS_001 --status verified --by "Cong Ly"
"""
from __future__ import annotations

import argparse
import glob
import html
import os
from pathlib import Path

import pandas as pd

from dev_set.tools.run_evaluation import _load_frozen_inputs

REPO = Path(__file__).resolve().parents[2]
KF_ROOT = REPO / "data/raw/btc/keyframes"
MANIFEST_DIR = REPO / "dev_set/manifests"


def _load_frame_map() -> pd.DataFrame:
    return pd.read_parquet(REPO / "data/derived/frame_map.parquet")


def _find_kf_dir(video_id: str) -> str | None:
    hits = glob.glob(str(KF_ROOT / f"*/{video_id}"))
    return hits[0] if hits else None


def _nearest_keyframe(fm: pd.DataFrame, video_id: str, frame_idx: int) -> tuple[str | None, int]:
    sub = fm[fm.video_id == video_id]
    if sub.empty:
        return None, -1
    diff = (sub["frame_idx_corrected"] - frame_idx).abs()
    row_idx = diff.idxmin()
    row = sub.loc[row_idx]
    kdir = _find_kf_dir(video_id)
    if not kdir:
        return None, int(diff.loc[row_idx])
    path = os.path.join(kdir, f"{int(row['btc_ordinal']):03d}.jpg")
    return (path if os.path.exists(path) else None), int(diff.loc[row_idx])


def _image_card(label: str, video_id: str, frame_idx: int, fm: pd.DataFrame) -> str:
    img, diff = _nearest_keyframe(fm, video_id, frame_idx)
    if not img:
        return f"""<div class="card missing"><div class="lbl">{html.escape(label)}</div>
          <div class="noimg">không có keyframe gần frame {frame_idx}</div></div>"""
    return f"""<div class="card"><div class="lbl">{html.escape(label)} (frame {frame_idx})</div>
      <img src="file://{html.escape(img)}" loading="lazy">
      <div class="meta">lệch keyframe gần nhất: {diff} frame</div></div>"""


def _query_section(query, gt, fm: pd.DataFrame) -> str:
    qv = html.escape(query.query_vi)
    qe = html.escape(query.query_en or "")
    status = html.escape(gt.verification_status)
    extra = ""
    if query.task_type == "QA":
        extra = f"""<div class="answer">Đáp án hiện có: <b>{html.escape(gt.answer_text)}</b>
          (biến thể: {html.escape(', '.join(gt.answer_variants))})</div>"""
    cards = _image_card("Đầu cửa sổ", gt.video_id, gt.frame_start, fm) + _image_card(
        "Cuối cửa sổ", gt.video_id, gt.frame_end, fm,
    )
    return f"""
    <section>
      <h2>{html.escape(query.query_id)} <span class="badge">{query.task_type}</span>
        <span class="status status-{status}">{status}</span></h2>
      <p class="query">{qv}<br><span class="en">{qe}</span></p>
      <p class="gt">GT hiện có: <b>{html.escape(gt.video_id)}</b>,
        frame [{gt.frame_start}, {gt.frame_end}]</p>
      {extra}
      <div class="grid">{cards}</div>
    </section>"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, help="tên manifest, vd: batch1_holdout13")
    parser.add_argument("--ground-truth", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    manifest_path = MANIFEST_DIR / f"{args.manifest}.json"
    manifest_id, queries, gts, _paths = _load_frozen_inputs(manifest_path, args.ground_truth)

    fm = _load_frame_map()
    sections = "\n".join(
        _query_section(q, gts[q.query_id], fm) for q in queries if q.task_type != "TRAKE"
    )
    n_skipped_trake = sum(1 for q in queries if q.task_type == "TRAKE")

    doc = f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<title>Soát GT — {html.escape(manifest_id)}</title>
<style>
  body {{ font-family: -apple-system, sans-serif; background:#111; color:#eee; margin:0; padding:20px; }}
  h2 {{ border-bottom:2px solid #444; padding-bottom:6px; }}
  .badge {{ font-size:12px; background:#2563eb; padding:2px 8px; border-radius:10px; margin-left:8px; }}
  .status {{ font-size:12px; padding:2px 8px; border-radius:10px; margin-left:6px; }}
  .status-unknown {{ background:#7c2d12; }}
  .status-verified {{ background:#166534; }}
  .query {{ font-size:16px; background:#1e293b; padding:10px 14px; border-radius:8px; margin:10px 0 6px; }}
  .query .en {{ color:#94a3b8; font-size:13px; }}
  .gt {{ font-size:13px; color:#cbd5e1; }}
  .answer {{ font-size:14px; background:#312e81; padding:8px 12px; border-radius:8px; margin:6px 0; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(280px,1fr)); gap:10px; margin-bottom:36px; }}
  .card {{ background:#1a1a1a; border:1px solid #333; border-radius:8px; overflow:hidden; }}
  .card img {{ width:100%; display:block; aspect-ratio:16/9; object-fit:cover; }}
  .card .lbl {{ font-weight:bold; padding:4px 8px; background:#333; font-size:12px; }}
  .card .meta {{ font-size:11px; padding:4px 8px; color:#aaa; }}
  .card.missing {{ display:flex; flex-direction:column; }}
  .noimg {{ flex:1; display:flex; align-items:center; justify-content:center; color:#666; padding:20px; text-align:center; }}
</style></head>
<body>
<p style="color:#94a3b8">Manifest: {html.escape(manifest_id)} · {len(queries)} câu
  ({n_skipped_trake} TRAKE bị bỏ qua — không có frame_start/frame_end đơn).
  Soát xong ghi quyết định bằng <code>python -m dev_set.tools.mark_verified</code>,
  KHÔNG sửa tay JSONL.</p>
{sections}
</body></html>"""

    out = args.out or REPO / f"scratch/gt_review_{manifest_id}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    print(str(out))


if __name__ == "__main__":
    main()
