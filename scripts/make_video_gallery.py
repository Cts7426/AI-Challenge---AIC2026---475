"""Sinh trang HTML xem TOÀN BỘ keyframe của một video — dùng khi biết đúng
video nhưng nghi ngờ vùng frame đề xuất (slot allocator/BM25) trỏ sai chỗ.

Chạy:
    python scripts/make_video_gallery.py L30_V046
"""
from __future__ import annotations

import argparse
import glob
import html
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
KF_ROOT = REPO / "data/raw/btc/keyframes"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("video_id")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    kdir = glob.glob(str(KF_ROOT / f"*/{args.video_id}"))
    if not kdir:
        raise SystemExit(f"Không thấy thư mục keyframe cho {args.video_id}")
    kdir = kdir[0]

    fm = pd.read_parquet(REPO / "data/derived/frame_map.parquet")
    sub = fm[fm.video_id == args.video_id].set_index("btc_ordinal")

    files = sorted(Path(kdir).glob("*.jpg"))
    cards = []
    for f in files:
        ordv = int(f.stem)
        fidx = int(sub.loc[ordv, "frame_idx_corrected"]) if ordv in sub.index else -1
        pts = sub.loc[ordv, "pts_time"] if ordv in sub.index else None
        cards.append(f"""
          <div class="card">
            <div class="rank">ord {ordv:03d}</div>
            <img src="file://{html.escape(str(f))}" loading="lazy">
            <div class="meta">frame_idx {fidx}{f' · {pts:.1f}s' if pts is not None else ''}</div>
          </div>""")

    html_doc = f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<title>{html.escape(args.video_id)} — toàn bộ keyframe</title>
<style>
  body {{ font-family: -apple-system, sans-serif; background:#111; color:#eee; margin:0; padding:20px; }}
  h1 {{ border-bottom:2px solid #444; padding-bottom:6px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(200px,1fr)); gap:8px; }}
  .card {{ background:#1a1a1a; border:1px solid #333; border-radius:6px; overflow:hidden; }}
  .card img {{ width:100%; display:block; aspect-ratio:16/9; object-fit:cover; }}
  .card .rank {{ font-weight:bold; padding:3px 6px; background:#333; font-size:12px; }}
  .card .meta {{ font-size:11px; padding:4px 6px; color:#aaa; }}
</style></head>
<body>
<h1>{html.escape(args.video_id)} — {len(files)} keyframe</h1>
<div class="grid">{''.join(cards)}</div>
</body></html>"""

    out = Path(args.out) if args.out else REPO / "scratch" / f"video_{args.video_id}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_doc, encoding="utf-8")
    print(str(out))


if __name__ == "__main__":
    main()
