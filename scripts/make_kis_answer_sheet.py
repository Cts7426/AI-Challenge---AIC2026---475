"""Xuất bảng đối chiếu KIS: đề bài đầy đủ + đáp án đề xuất + ảnh keyframe.

Vì sao cần: người vận hành phải tự soát lại được từng câu mà không phải mở
terminal hay đọc JSON. Trang này đặt NGUYÊN VĂN đề bài cạnh ảnh keyframe đã
chọn, kèm đáp án cũ để thấy rõ đã đổi gì.

Ảnh nhúng bằng `file://` (không base64) nên trang nhẹ và mở tức thì; muốn gửi
đi máy khác thì dùng --embed để nhúng base64.

Chạy:
    .venv/bin/python3.14 scripts/make_kis_answer_sheet.py
    .venv/bin/python3.14 scripts/make_kis_answer_sheet.py --embed --out /tmp/kis.html
"""
from __future__ import annotations

import argparse
import base64
import csv
import html
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


def _img_src(path: str | None, embed: bool) -> str | None:
    if not path:
        return None
    if not embed:
        return "file://" + path
    data = base64.b64encode(Path(path).read_bytes()).decode("ascii")
    return f"data:image/jpeg;base64,{data}"


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
            img = _img_src(_nearest_keyframe(fm, vid, frame)[0], embed)
            status, badge = "ok", found["how"]
            note = found.get("note", "")
        else:
            vid = new_rows[0][0] if new_rows else "—"
            frame = new_rows[0][1] if new_rows else 0
            img = _img_src(_nearest_keyframe(fm, vid, frame)[0], embed) if new_rows else None
            status, badge = "open", "CHƯA XÁC NHẬN"
            note = "Hạng 1 do pipeline chọn, chưa soi ảnh xác nhận."

        top3 = " · ".join(f"{v}:{f}" for v, f in new_rows) or "—"
        picture = (
            f'<img src="{html.escape(img)}" loading="lazy" alt="keyframe {html.escape(vid)}">'
            if img else '<div class="noimg">không có ảnh keyframe</div>'
        )

        cards.append(f"""
    <article class="card {status}">
      <div class="head">
        <span class="qid">{html.escape(qid)}</span>
        <span class="badge">{html.escape(badge)}</span>
      </div>
      <div class="grid">
        <div class="left">
          <p class="label">Đề bài</p>
          <p class="query">{html.escape(q["query_vi"])}</p>
          <p class="label">Bản dịch dùng để tìm</p>
          <p class="en">{html.escape((found or {}).get("query_en_claude") or "—")}</p>
        </div>
        <div class="right">
          {picture}
          <p class="answer"><b>{html.escape(vid)}</b> · frame {frame}</p>
          <p class="note">{html.escape(note)}</p>
          <table class="cmp">
            <tr><td>Đã nộp đợt 1</td><td class="old">{html.escape(old_vid)}:{html.escape(str(old_frame))}</td></tr>
            <tr><td>Top-3 mới</td><td class="new">{html.escape(top3)}</td></tr>
          </table>
        </div>
      </div>
    </article>""")

    n_ok = sum(1 for q in queries if q["query_id"] in findings)
    return f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Đối chiếu đáp án KIS — Batch 1</title>
<style>
  :root {{ --bg:#0f141a; --card:#161d26; --sunken:#1d2530; --ink:#e4e9ef; --muted:#8e9ba8;
           --line:#2a343f; --ok:#6bc79a; --open:#dca94f; --bad:#e58a72; }}
  * {{ box-sizing:border-box; }}
  body {{ background:var(--bg); color:var(--ink); margin:0; padding:24px;
          font:15px/1.6 -apple-system,"Segoe UI",system-ui,sans-serif; }}
  h1 {{ font-size:1.5rem; margin:0 0 6px; }}
  .sub {{ color:var(--muted); margin:0 0 26px; font-size:.9rem; }}
  .card {{ background:var(--card); border:1px solid var(--line); border-left:4px solid var(--ok);
           border-radius:6px; margin-bottom:18px; overflow:hidden; }}
  .card.open {{ border-left-color:var(--open); }}
  .head {{ display:flex; gap:12px; align-items:center; padding:11px 16px;
           background:var(--sunken); border-bottom:1px solid var(--line); }}
  .qid {{ font-family:ui-monospace,Menlo,monospace; font-weight:600; }}
  .badge {{ font-family:ui-monospace,Menlo,monospace; font-size:10.5px; letter-spacing:.06em;
            padding:2px 8px; border-radius:3px; background:#0f141a; color:var(--ok); }}
  .card.open .badge {{ color:var(--open); }}
  .grid {{ display:grid; grid-template-columns:1fr 380px; gap:20px; padding:16px; }}
  @media (max-width:860px) {{ .grid {{ grid-template-columns:1fr; }} }}
  .label {{ font-size:10.5px; letter-spacing:.1em; text-transform:uppercase;
            color:var(--muted); margin:0 0 5px; }}
  .query {{ margin:0 0 16px; white-space:pre-wrap; }}
  .en {{ margin:0; color:var(--muted); font-style:italic; font-size:.88rem; }}
  .right img {{ width:100%; display:block; border-radius:4px; border:1px solid var(--line); }}
  .noimg {{ aspect-ratio:16/9; display:flex; align-items:center; justify-content:center;
            background:var(--sunken); color:var(--muted); border-radius:4px; font-size:.85rem; }}
  .answer {{ margin:10px 0 3px; font-size:.95rem; }}
  .note {{ margin:0 0 10px; color:var(--muted); font-size:.83rem; }}
  .cmp {{ width:100%; border-collapse:collapse; font-size:.78rem; }}
  .cmp td {{ padding:4px 0; border-top:1px solid var(--line); vertical-align:top; }}
  .cmp td:first-child {{ color:var(--muted); width:100px; }}
  .cmp .old {{ color:var(--bad); font-family:ui-monospace,Menlo,monospace; }}
  .cmp .new {{ color:var(--ok); font-family:ui-monospace,Menlo,monospace; }}
</style></head>
<body>
<h1>Đối chiếu đáp án KIS — Batch 1</h1>
<p class="sub">{len(queries)} câu · {n_ok} đã soi ảnh xác nhận · {len(queries)-n_ok} chưa.
Ảnh bên phải là keyframe gần nhất với frame đề xuất — so trực tiếp với đề bài bên trái.</p>
{"".join(cards)}
</body></html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=REPO / "scratch/kis_answer_sheet.html")
    parser.add_argument("--embed", action="store_true", help="nhúng ảnh base64 để gửi sang máy khác")
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(build(args.embed), encoding="utf-8")
    print(args.out)


if __name__ == "__main__":
    main()
