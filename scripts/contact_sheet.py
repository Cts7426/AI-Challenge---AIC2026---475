"""Ghép nhiều keyframe thành MỘT tấm lưới để soi hàng chục ảnh trong một lần nhìn.

Vì sao cần: soi từng ảnh một rất tốn — mỗi ảnh là một lượt đọc. Với câu khó
phải quét vài chục ứng viên thì lưới 6x8 cho phép loại nhanh 48 ảnh cùng lúc,
rồi mới phóng to vài ảnh đáng ngờ.

Mỗi ô có số thứ tự để chỉ đích danh ô cần xem kỹ.

Chạy:
    python scripts/contact_sheet.py --video L25_V087 --out scratch/cs.jpg
    python scripts/contact_sheet.py --frames "L25_V087:16350,L25_V033:13544" --out scratch/cs.jpg
"""
from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path

from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

CELL_W, COLS = 320, 6
LABEL_H = 18


def _kf_path(video_id: str, ordinal: int) -> str | None:
    hits = glob.glob(str(REPO / f"data/raw/btc/keyframes/*/{video_id}/{ordinal:03d}.jpg"))
    return hits[0] if hits else None


def build(pairs: list[tuple[str, int]], out: Path, cols: int = COLS) -> None:
    """pairs = [(video_id, frame_idx)]. Frame tra ngược về keyframe gần nhất."""
    from dev_set.tools.gt_verification_gallery import _load_frame_map, _nearest_keyframe

    fm = _load_frame_map()
    tiles = []
    for v, f in pairs:
        p, _ = _nearest_keyframe(fm, v, int(f))
        if p:
            tiles.append((p, f"{len(tiles)+1}. {v}:{f}"))
    if not tiles:
        raise SystemExit("không có ảnh nào")

    rows = (len(tiles) + cols - 1) // cols
    cell_h = int(CELL_W * 9 / 16)
    sheet = Image.new("RGB", (cols * CELL_W, rows * (cell_h + LABEL_H)), (18, 20, 24))
    draw = ImageDraw.Draw(sheet)

    for i, (path, label) in enumerate(tiles):
        r, c = divmod(i, cols)
        x, y = c * CELL_W, r * (cell_h + LABEL_H)
        with Image.open(path) as im:
            im = im.convert("RGB").resize((CELL_W, cell_h), Image.LANCZOS)
            sheet.paste(im, (x, y))
        draw.rectangle([x, y + cell_h, x + CELL_W, y + cell_h + LABEL_H], fill=(28, 32, 38))
        draw.text((x + 4, y + cell_h + 3), label[:44], fill=(200, 210, 220))

    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, "JPEG", quality=78, optimize=True)
    print(f"{out}  ({len(tiles)} ô, {sheet.size[0]}x{sheet.size[1]}, "
          f"{out.stat().st_size/1024:.0f} KB)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--video", help="lấy đều keyframe của một video")
    ap.add_argument("--frames", help="danh sách video:frame,video:frame")
    ap.add_argument("--every", type=int, default=8, help="lấy 1 trong mỗi N keyframe (chế độ --video)")
    ap.add_argument("--limit", type=int, default=48)
    ap.add_argument("--out", type=Path, default=REPO / "scratch/contact_sheet.jpg")
    args = ap.parse_args()

    if args.frames:
        pairs = []
        for tok in args.frames.split(","):
            v, f = tok.strip().split(":")
            pairs.append((v, int(f)))
    elif args.video:
        import pandas as pd
        fm = pd.read_parquet(REPO / "data/derived/frame_map.parquet")
        sub = fm[fm.video_id == args.video].sort_values("btc_ordinal")
        pairs = [(args.video, int(r.frame_idx_corrected))
                 for r in sub.itertuples()][::args.every]
    else:
        ap.error("cần --video hoặc --frames")

    build(pairs[:args.limit], args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
