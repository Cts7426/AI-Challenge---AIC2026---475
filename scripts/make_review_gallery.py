"""Sinh trang HTML xem toàn bộ ảnh ứng viên (top N) của một câu KIS/QA để soát mắt.

Vì sao cần: ảnh xem qua chat chỉ được vài tấm một lúc, không đủ để so hết 100
ứng viên với đề. Trang HTML này show đề + lưới ảnh (link file:// trực tiếp,
KHÔNG nhúng base64 — nhẹ, mở tức thì) kèm hạng/video_id/frame_id dưới mỗi ảnh,
để người thao tác tự cuộn và chỉ ra ảnh đúng.

Chạy:
    python scripts/make_review_gallery.py query-p1-1-kis
    python scripts/make_review_gallery.py query-p1-1-kis --top 100 --out /tmp/gallery.html
    python scripts/make_review_gallery.py --all --top 20   # 1 trang cho MỌI câu, 20 ảnh/câu
"""
from __future__ import annotations

import argparse
import glob
import html
import json
import os
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
CHECKPOINT = REPO / "submissions/lan_1/checkpoint.jsonl"
QUERIES = REPO / "dev_set/queries/sotuyen1.jsonl"
KF_ROOT = REPO / "data/raw/btc/keyframes"


def _load_frame_map() -> pd.DataFrame:
    return pd.read_parquet(REPO / "data/derived/frame_map.parquet")


def _find_kf_dir(vid: str) -> str | None:
    hits = glob.glob(str(KF_ROOT / f"*/{vid}"))
    return hits[0] if hits else None


def _nearest_keyframe(fm: pd.DataFrame, vid: str, fid: int) -> tuple[str | None, int]:
    sub = fm[fm.video_id == vid]
    if sub.empty:
        return None, -1
    diff = (sub["frame_idx_corrected"] - fid).abs()
    idx = diff.idxmin()
    row = sub.loc[idx]
    kdir = _find_kf_dir(vid)
    if not kdir:
        return None, int(diff.loc[idx])
    return os.path.join(kdir, f"{int(row['btc_ordinal']):03d}.jpg"), int(diff.loc[idx])


def _query_section(qid: str, top: int, fm: pd.DataFrame, queries: dict, checkpoint: dict) -> str:
    q = queries.get(qid)
    rec = checkpoint.get(qid)
    if not q or not rec:
        return f"<p>Không tìm thấy dữ liệu cho {html.escape(qid)}</p>"

    cards = []
    seen_img = set()
    for i, a in enumerate(rec["answers"][:top], 1):
        vid, fid = a["video_id"], a["frame_ids"][0]
        img, diff = _nearest_keyframe(fm, vid, fid)
        if not img or not os.path.exists(img):
            cards.append(f"""
              <div class="card missing">
                <div class="rank">#{i}</div>
                <div class="noimg">không có ảnh</div>
                <div class="meta">{html.escape(vid)}<br>frame {fid}</div>
              </div>""")
            continue
        dup = img in seen_img
        seen_img.add(img)
        cards.append(f"""
          <div class="card{' dup' if dup else ''}">
            <div class="rank">#{i}</div>
            <img src="file://{html.escape(img)}" loading="lazy">
            <div class="meta">{html.escape(vid)} · frame {fid}<br>lệch keyframe: {diff}{' (trùng ảnh ứng viên trước)' if dup else ''}</div>
          </div>""")

    return f"""
    <section>
      <h2>{html.escape(qid)} <span class="badge">{q['task_type']}</span></h2>
      <p class="query">{html.escape(q['query_vi'])}</p>
      <div class="grid">{''.join(cards)}</div>
    </section>
    """


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("query_id", nargs="?", help="vd: query-p1-1-kis")
    ap.add_argument("--all", action="store_true", help="làm cho mọi câu có trong checkpoint")
    ap.add_argument("--top", type=int, default=100, help="số ứng viên hiển thị (mặc định 100)")
    ap.add_argument("--out", default=None, help="đường dẫn file html ra")
    args = ap.parse_args()

    if not args.query_id and not args.all:
        ap.error("cần query_id hoặc --all")

    fm = _load_frame_map()
    queries = {json.loads(l)["query_id"]: json.loads(l) for l in QUERIES.read_text(encoding="utf-8").splitlines() if l.strip()}
    checkpoint = {}
    for l in CHECKPOINT.read_text(encoding="utf-8").splitlines():
        if l.strip():
            r = json.loads(l)
            checkpoint[r["query_id"]] = r  # dòng sau đè dòng trước, giống run.py

    qids = sorted(checkpoint.keys()) if args.all else [args.query_id]

    sections = "\n".join(_query_section(qid, args.top, fm, queries, checkpoint) for qid in qids)

    html_doc = f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<title>Soát ảnh — {html.escape(','.join(qids)) if len(qids) <= 3 else f'{len(qids)} câu'}</title>
<style>
  body {{ font-family: -apple-system, sans-serif; background:#111; color:#eee; margin:0; padding:20px; }}
  h2 {{ border-bottom:2px solid #444; padding-bottom:6px; }}
  .badge {{ font-size:12px; background:#2563eb; padding:2px 8px; border-radius:10px; margin-left:8px; }}
  .query {{ font-size:16px; background:#1e293b; padding:10px 14px; border-radius:8px; margin:10px 0 16px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(220px,1fr)); gap:10px; margin-bottom:40px; }}
  .card {{ background:#1a1a1a; border:1px solid #333; border-radius:8px; overflow:hidden; }}
  .card.dup {{ opacity:0.45; }}
  .card img {{ width:100%; display:block; aspect-ratio:16/9; object-fit:cover; }}
  .card .rank {{ font-weight:bold; padding:4px 8px; background:#333; }}
  .card .meta {{ font-size:11px; padding:6px 8px; color:#aaa; }}
  .card.missing {{ display:flex; flex-direction:column; }}
  .noimg {{ flex:1; display:flex; align-items:center; justify-content:center; color:#666; }}
</style></head>
<body>
{sections}
</body></html>"""

    out = Path(args.out) if args.out else REPO / "scratch" / f"gallery_{'ALL' if args.all else args.query_id}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_doc, encoding="utf-8")
    print(str(out))


if __name__ == "__main__":
    main()
