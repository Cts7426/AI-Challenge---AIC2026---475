"""Xuất bảng đối chiếu KIS: đề bài đầy đủ + đáp án đề xuất + ảnh keyframe.

Vì sao cần: người vận hành phải soát lại được từng câu bằng MẮT, không phải
đọc JSON. Trang đặt nguyên văn đề bài cạnh ảnh keyframe đã chọn, kèm đáp án cũ
để thấy rõ đã đổi gì.

Hai chế độ ảnh:
  mặc định   `file://` — nhẹ, mở tức thì, CHỈ chạy trên máy này
  --embed    base64 đã resize — gửi đi máy khác hoặc publish web được

Nền tối là lựa chọn có chủ đích, không phải mặc định: trang này để soi ảnh,
nền tối giúp màu trong ảnh không bị nền trắng lấn át (quy ước phòng tối).

Chạy:
    .venv/bin/python3.14 scripts/make_kis_answer_sheet.py
    .venv/bin/python3.14 scripts/make_kis_answer_sheet.py --embed --out /tmp/kis.html
"""
from __future__ import annotations

import argparse
import base64
import csv
import html
import io
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dev_set.tools.gt_verification_gallery import _load_frame_map, _nearest_keyframe

MANIFEST = REPO / "dev_set/manifests/batch1_round1_queries.json"
FINDINGS = REPO / "dev_set/ground_truth/round1_kis_findings.json"
OLD_SUBMISSION = REPO / "submission"
NEW_SUBMISSION = REPO / "submissions/kis_claude"

EMBED_WIDTH = 880   # đủ soi chi tiết, đủ nhẹ để nhúng 20 ảnh trong một trang
EMBED_QUALITY = 80


def _img_src(path: str | None, embed: bool) -> str | None:
    """file:// cho bản local; data URI đã resize cho bản mang đi được."""
    if not path:
        return None
    if not embed:
        return "file://" + path

    from PIL import Image

    with Image.open(path) as im:
        im = im.convert("RGB")
        if im.width > EMBED_WIDTH:
            h = round(im.height * EMBED_WIDTH / im.width)
            im = im.resize((EMBED_WIDTH, h), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=EMBED_QUALITY, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _qnum(qid: str) -> int:
    return int(qid.split("-")[2])


def build(embed: bool) -> str:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    findings = json.loads(FINDINGS.read_text(encoding="utf-8"))["entries"]
    fm = _load_frame_map()

    queries = sorted(
        (q for q in manifest["queries"] if q["task_type"] == "KIS"),
        key=lambda q: _qnum(q["query_id"]),
    )

    cards = []
    for q in queries:
        qid = q["query_id"]
        found = findings.get(qid)
        short = qid.replace("query-", "").replace("-kis", "")

        old_vid = old_frame = "—"
        old_path = OLD_SUBMISSION / f"{qid}.csv"
        if old_path.exists():
            first = next(csv.reader(old_path.open()), None)
            if first:
                old_vid, old_frame = first[0], first[1]

        new_rows = []
        new_path = NEW_SUBMISSION / f"{qid}.csv"
        if new_path.exists():
            new_rows = [(r[0], int(r[1])) for r in csv.reader(new_path.open())][:3]

        if found:
            vid, frame = found["video_id"], int(found["frame"])
            state, badge = "ok", "đã soi ảnh · " + found["how"]
            note = found.get("note", "")
        else:
            vid = new_rows[0][0] if new_rows else "—"
            frame = new_rows[0][1] if new_rows else 0
            state, badge = "open", "CHƯA XÁC NHẬN"
            note = "Hạng 1 do pipeline chọn — cần bạn soi và quyết."

        img = _img_src(_nearest_keyframe(fm, vid, frame)[0], embed) if vid != "—" else None
        picture = (
            f'<img src="{img}" loading="lazy" alt="keyframe {html.escape(vid)} frame {frame}">'
            if img else '<div class="noimg">không có ảnh keyframe</div>'
        )
        alts = "".join(
            f'<li><code>{html.escape(v)}</code>:{f}</li>' for v, f in new_rows[1:]
        )

        cards.append(f"""
    <article class="card {state}" id="{html.escape(short)}">
      <div class="bar">
        <span class="qid">{html.escape(short)}</span>
        <span class="badge">{html.escape(badge)}</span>
      </div>
      <div class="body">
        <div class="text">
          <p class="lbl">Đề bài</p>
          <p class="query">{html.escape(q["query_vi"])}</p>
          <p class="lbl">Cần thấy gì trong ảnh</p>
          <p class="note">{html.escape(note)}</p>
          <dl class="meta">
            <dt>Đáp án đề xuất</dt>
            <dd class="pick"><code>{html.escape(vid)}</code> · frame {frame}</dd>
            <dt>Đã nộp đợt 1</dt>
            <dd class="old"><code>{html.escape(old_vid)}</code>:{html.escape(str(old_frame))}</dd>
            <dt>Phương án kế</dt>
            <dd><ul class="alts">{alts or "<li>—</li>"}</ul></dd>
          </dl>
        </div>
        <figure class="shot">{picture}</figure>
      </div>
    </article>""")

    n_ok = sum(1 for q in queries if q["query_id"] in findings)
    nav = "".join(
        f'<a href="#{q["query_id"].replace("query-", "").replace("-kis", "")}" '
        f'class="{"ok" if q["query_id"] in findings else "open"}">'
        f'{q["query_id"].replace("query-", "").replace("-kis", "")}</a>'
        for q in queries
    )

    return f"""<title>Soát đáp án KIS Batch 1</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,400;6..72,600&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>
  :root {{
    --bg:#0E1319; --card:#161D26; --sunken:#1D2530; --ink:#E4E9EF; --muted:#8E9BA8;
    --line:#2A343F; --ok:#6BC79A; --open:#DCA94F; --bad:#E58A72; --accent:#57C2B8;
    --display:"Newsreader",Georgia,serif;
    --body:"IBM Plex Sans",system-ui,-apple-system,sans-serif;
    --mono:"IBM Plex Mono",ui-monospace,Menlo,monospace;
  }}
  * {{ box-sizing:border-box; }}
  body {{ background:var(--bg); color:var(--ink); margin:0; padding:0 20px 80px;
          font-family:var(--body); font-size:16px; line-height:1.6;
          -webkit-font-smoothing:antialiased; }}
  .wrap {{ max-width:1120px; margin:0 auto; }}

  header {{ padding:56px 0 26px; border-bottom:1px solid var(--line); }}
  .eyebrow {{ font-family:var(--mono); font-size:11.5px; letter-spacing:.13em;
              text-transform:uppercase; color:var(--accent); margin:0 0 14px; }}
  h1 {{ font-family:var(--display); font-weight:600; font-size:clamp(2rem,5vw,2.9rem);
        line-height:1.08; letter-spacing:-.02em; margin:0 0 14px; }}
  .sub {{ color:var(--muted); margin:0; max-width:62ch; font-size:.95rem; }}

  nav {{ display:flex; flex-wrap:wrap; gap:6px; padding:22px 0 0; }}
  nav a {{ font-family:var(--mono); font-size:12px; text-decoration:none;
           padding:4px 9px; border:1px solid var(--line); border-radius:3px;
           background:var(--card); }}
  nav a.ok {{ color:var(--ok); }}
  nav a.open {{ color:var(--open); border-color:var(--open); }}
  nav a:hover {{ border-color:var(--accent); }}

  .card {{ background:var(--card); border:1px solid var(--line); border-left:4px solid var(--ok);
           border-radius:7px; margin-top:22px; overflow:hidden; scroll-margin-top:16px; }}
  .card.open {{ border-left-color:var(--open); }}
  .bar {{ display:flex; gap:12px; align-items:center; flex-wrap:wrap;
          padding:11px 18px; background:var(--sunken); border-bottom:1px solid var(--line); }}
  .qid {{ font-family:var(--mono); font-weight:500; font-size:.95rem; }}
  .badge {{ font-family:var(--mono); font-size:10.5px; letter-spacing:.07em;
            padding:3px 9px; border-radius:3px; background:var(--bg); color:var(--ok); }}
  .card.open .badge {{ color:var(--open); }}

  .body {{ display:grid; grid-template-columns:1fr 620px; gap:26px; padding:20px 18px 22px; }}
  @media (max-width:980px) {{ .body {{ grid-template-columns:1fr; }} }}

  .lbl {{ font-family:var(--mono); font-size:10.5px; letter-spacing:.11em;
          text-transform:uppercase; color:var(--muted); margin:0 0 6px; }}
  .query {{ margin:0 0 20px; white-space:pre-wrap; font-size:1.02rem; line-height:1.62; }}
  .note {{ margin:0 0 20px; color:var(--muted); font-size:.9rem; }}

  .meta {{ display:grid; grid-template-columns:auto 1fr; gap:7px 16px; margin:0;
           padding-top:16px; border-top:1px solid var(--line); font-size:.85rem; }}
  .meta dt {{ color:var(--muted); font-size:11px; letter-spacing:.05em;
              text-transform:uppercase; font-family:var(--mono); padding-top:2px; }}
  .meta dd {{ margin:0; }}
  .meta .pick {{ color:var(--ok); font-weight:500; }}
  .meta .old {{ color:var(--bad); }}
  .alts {{ list-style:none; margin:0; padding:0; }}
  .alts li {{ color:var(--muted); }}
  code {{ font-family:var(--mono); font-size:.9em; }}

  .shot {{ margin:0; }}
  .shot img {{ width:100%; display:block; border-radius:5px; border:1px solid var(--line);
               background:var(--sunken); }}
  .noimg {{ aspect-ratio:16/9; display:flex; align-items:center; justify-content:center;
            background:var(--sunken); color:var(--muted); border-radius:5px; font-size:.88rem; }}

  a:focus-visible, nav a:focus-visible {{ outline:2px solid var(--accent); outline-offset:2px; }}
  @media (prefers-reduced-motion:reduce) {{ * {{ transition:none !important; }} }}
</style>

<div class="wrap">
<header>
  <p class="eyebrow">Sơ tuyển đợt 1 · Batch 1</p>
  <h1>Soát đáp án KIS</h1>
  <p class="sub">{len(queries)} câu · {n_ok} đã soi ảnh xác nhận · {len(queries) - n_ok} còn treo.
     Đề bài bên trái, ảnh keyframe của đáp án đề xuất bên phải — so trực tiếp bằng mắt.
     Frame ghi ở đây là keyframe soi thấy đúng cảnh, không phải biên cửa sổ đáp án của BTC.</p>
  <nav>{nav}</nav>
</header>
{"".join(cards)}
</div>"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=REPO / "scratch/kis_answer_sheet.html")
    parser.add_argument("--embed", action="store_true", help="nhúng ảnh base64 (đã resize) để mang đi được")
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(build(args.embed), encoding="utf-8")
    size_mb = args.out.stat().st_size / 1_048_576
    print(f"{args.out}  ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
