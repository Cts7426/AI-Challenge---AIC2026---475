"""Dựng gallery localhost để người vận hành soi đáp án QA và TRAKE.

Ảnh hiển thị luôn đi qua ``resolve_frame_path``. Với frame chưa trùng một
keyframe BTC, trang chỉ tìm keyframe lân cận bằng ``frame_map`` và ghi rõ độ
lệch; không dùng ordinal ảnh làm frame nộp và không tự đánh dấu ``verified``.

Chạy từ gốc repo::

    python scripts/make_qa_trake_review.py
    python -m http.server 8765 --directory scratch/qa_trake_review
"""

from __future__ import annotations

import argparse
import html
import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path
from typing import Callable

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.common.frame_assets import resolve_frame_path  # noqa: E402
from backend.indexing.frame_map import load_frame_map  # noqa: E402

DEFAULT_SELECTION = REPO / "scratch/round3_qa_trake_review.json"
DEFAULT_OUTPUT = REPO / "scratch/qa_trake_review"
QUERY_DIR = REPO / "data/queries/round3_raw"

ContextProvider = Callable[[str, int], list[dict]]


def load_queries(query_dir: Path = QUERY_DIR) -> dict[str, str]:
    """Đọc đề TXT, trả ``query_id → nội dung`` mà không diễn giải lại đề."""
    return {
        path.stem: " ".join(path.read_text(encoding="utf-8").split())
        for path in sorted(query_dir.glob("*.txt"))
    }


def _image_cards(images: list[dict]) -> str:
    """Render các keyframe lân cận, luôn công khai frame thực sự đang hiện."""
    if not images:
        return '<div class="missing">Không tìm thấy ảnh lân cận.</div>'
    cards = []
    for image in images:
        offset = int(image["offset"])
        offset_text = f"{offset:+d}" if offset else "0"
        cards.append(
            '<figure class="frame-card">'
            f'<img src="{html.escape(str(image["url"]))}" loading="lazy" '
            f'alt="{html.escape(str(image["keyframe_id"]))}">'
            f'<figcaption><b>{html.escape(str(image["keyframe_id"]))}</b><br>'
            f'frame ảnh {int(image["mapped_frame"])} · lệch {offset_text}</figcaption>'
            "</figure>"
        )
    return "".join(cards)


def render_page(
    items: list[dict],
    queries: dict[str, str],
    context_provider: ContextProvider,
) -> str:
    """Render một trang; TRAKE giữ ánh xạ vị trí E1..EN với frame 1..N."""
    sections = []
    nav = []
    for item in items:
        query_id = str(item["query_id"])
        task_type = str(item["task_type"]).upper()
        video_id = str(item["video_id"])
        frame_ids = [int(value) for value in item["frame_ids"]]
        status = str(item.get("status", "needs_review"))
        note = str(item.get("note", ""))
        query_text = queries.get(query_id, "Không tìm thấy nội dung đề.")
        nav.append(f'<a href="#{html.escape(query_id)}">{html.escape(query_id)}</a>')

        details = []
        if task_type == "QA":
            if len(frame_ids) != 1:
                raise ValueError(f"{query_id}: QA cần đúng một frame mục tiêu")
            target = frame_ids[0]
            answer = html.escape(str(item.get("answer_text", "Chưa chốt")))
            details.append(
                f'<div class="answer">Đáp án đề xuất: <strong>{answer}</strong></div>'
                f'<h3>{html.escape(video_id)} · frame mục tiêu {target}</h3>'
                f'<div class="frame-grid">{_image_cards(context_provider(video_id, target))}</div>'
            )
        elif task_type == "TRAKE":
            events = [str(value) for value in item.get("event_descs", [])]
            if len(events) != len(frame_ids):
                raise ValueError(f"{query_id}: số frame khác số sự kiện TRAKE")
            for index, (event, target) in enumerate(zip(events, frame_ids), 1):
                details.append(
                    '<div class="event">'
                    f'<h3>E{index} · {html.escape(event)}</h3>'
                    f'<p class="target">{html.escape(video_id)} · frame mục tiêu {target}</p>'
                    f'<div class="frame-grid">{_image_cards(context_provider(video_id, target))}</div>'
                    "</div>"
                )
        else:
            raise ValueError(f"{query_id}: task_type không hỗ trợ: {task_type}")

        sections.append(
            f'<section id="{html.escape(query_id)}">'
            f'<h2>{html.escape(query_id)} <span class="badge">{task_type}</span> '
            f'<span class="status {html.escape(status)}">{html.escape(status)}</span></h2>'
            f'<p class="query">{html.escape(query_text)}</p>'
            f'<p class="note">{html.escape(note)}</p>'
            f'{"".join(details)}</section>'
        )

    return f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Review QA &amp; TRAKE — Round 3</title>
<style>
:root {{ color-scheme:dark; --bg:#0b1020; --panel:#121a2d; --line:#2b3957; --muted:#9badca; }}
* {{ box-sizing:border-box }}
body {{ margin:0; background:var(--bg); color:#ecf2ff; font:15px/1.5 system-ui,sans-serif }}
header {{ position:sticky; top:0; z-index:5; padding:14px 22px; background:#0b1020ee; border-bottom:1px solid var(--line) }}
header h1 {{ margin:0 0 8px; font-size:20px }}
nav {{ display:flex; gap:7px; flex-wrap:wrap }}
nav a {{ color:#b9d7ff; background:#17233c; padding:3px 8px; border-radius:12px; text-decoration:none; font-size:12px }}
main {{ max-width:1500px; margin:auto; padding:18px }}
section {{ scroll-margin-top:110px; margin:0 0 28px; padding:18px; background:var(--panel); border:1px solid var(--line); border-radius:12px }}
h2 {{ margin:0 0 10px; font-size:19px }} h3 {{ margin:12px 0 7px; font-size:14px }}
.badge,.status {{ display:inline-block; padding:2px 8px; border-radius:10px; font-size:11px; vertical-align:2px }}
.badge {{ background:#244b84 }} .confirmed {{ background:#166534 }} .needs_review {{ background:#854d0e }} .rejected {{ background:#991b1b }}
.query {{ background:#1a2741; padding:10px 12px; border-radius:8px }}
.note,.target {{ color:var(--muted) }} .answer {{ padding:9px 12px; border-left:4px solid #60a5fa; background:#102a4a }}
.event {{ margin-top:14px; padding-top:2px; border-top:1px solid var(--line) }}
.frame-grid {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:9px }}
.frame-card {{ margin:0; overflow:hidden; background:#09101d; border:1px solid #263653; border-radius:8px }}
.frame-card img {{ display:block; width:100%; aspect-ratio:16/9; object-fit:cover }}
figcaption {{ padding:6px 8px; color:#adbad1; font:12px/1.35 ui-monospace,monospace }}
.missing {{ padding:25px; color:#fca5a5; border:1px dashed #7f1d1d }}
@media(max-width:720px) {{ .frame-grid {{ grid-template-columns:1fr }} }}
</style></head><body>
<header><h1>Review QA &amp; TRAKE — Round 3</h1><nav>{''.join(nav)}</nav></header>
<main>{''.join(sections)}</main>
</body></html>"""


def build_context_provider(output_dir: Path) -> ContextProvider:
    """Tạo provider lấy ba keyframe gần target và sao ảnh vào gallery tĩnh."""
    by_video: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for keyframe_id, frame_idx in load_frame_map().items():
        if "#k" not in keyframe_id:
            continue
        by_video[keyframe_id.split("#", 1)[0]].append((int(frame_idx), keyframe_id))
    for entries in by_video.values():
        entries.sort()

    assets_dir = output_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    def provide(video_id: str, target_frame: int) -> list[dict]:
        entries = by_video.get(video_id, [])
        if not entries:
            return []
        nearest = min(range(len(entries)), key=lambda index: abs(entries[index][0] - target_frame))
        context = entries[max(0, nearest - 1):min(len(entries), nearest + 2)]
        images = []
        for mapped_frame, keyframe_id in context:
            resolution = resolve_frame_path(
                video_id,
                frame_idx=mapped_frame,
                keyframe_id=keyframe_id,
            )
            if resolution.path is None:
                continue
            asset_name = f"{video_id}-{keyframe_id.split('#', 1)[1]}.jpg"
            destination = assets_dir / asset_name
            if not destination.exists():
                shutil.copy2(resolution.path, destination)
            images.append({
                "url": f"assets/{asset_name}",
                "mapped_frame": mapped_frame,
                "keyframe_id": keyframe_id,
                "offset": mapped_frame - target_frame,
            })
        return images

    return provide


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, default=DEFAULT_SELECTION)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    items = json.loads(args.selection.read_text(encoding="utf-8"))
    args.out.mkdir(parents=True, exist_ok=True)
    page = render_page(items, load_queries(), build_context_provider(args.out))
    (args.out / "index.html").write_text(page, encoding="utf-8")
    print(f"Trang review: {args.out / 'index.html'}")
    print(f"Số câu: {len(items)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
