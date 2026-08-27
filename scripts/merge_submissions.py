"""Trộn hai bộ submission thành một, xen kẽ theo luồng.

Vì sao: A/B đo được CLIP và SigLIP2 gần như ngang điểm (0.2424 vs 0.2329) NHƯNG
bù trừ cho nhau — SigLIP2 cứu được p1-5/p1-6/p1-7/p1-18/p1-2/p1-24, CLIP cứu
được p1-10/p1-13/p1-19. Với KIS chỉ cần MỘT dòng đúng trong 100, phủ song song
hai giả thuyết luôn tốt hơn chọn một.

Giữ nguyên `keep` dòng đầu của bộ CHÍNH (đã đo là tốt nhất ở hạng đầu), phần
đuôi xen kẽ hai bên. Không bao giờ đẩy dòng đang đúng ở hạng 1 xuống — đó là
bài học đắt nhất của cả quá trình (chèn 2 dòng lên đầu làm Final tụt từ 0.58
xuống 0.38).

Chạy:
    python scripts/merge_submissions.py --primary submissions/kis_v8 \
        --secondary submissions/kis_siglip2 --out submissions/kis_merged
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

TOTAL = 100
KEEP = 12


def merge_one(primary: list, secondary: list, keep: int = KEEP) -> list:
    rows = list(primary[:keep])
    seen = set(rows)
    ia = ib = keep
    # xen kẽ: một dòng bộ chính, một dòng bộ phụ
    while len(rows) < TOTAL and (ia < len(primary) or ib < len(secondary)):
        for src, idx_name in ((primary, "a"), (secondary, "b")):
            i = ia if idx_name == "a" else ib
            while i < len(src) and src[i] in seen:
                i += 1
            if i < len(src) and len(rows) < TOTAL:
                rows.append(src[i]); seen.add(src[i]); i += 1
            if idx_name == "a":
                ia = i
            else:
                ib = i
    return rows[:TOTAL]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--primary", type=Path, required=True)
    ap.add_argument("--secondary", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--keep", type=int, default=KEEP)
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    n = 0
    for p in sorted(args.primary.glob("*.csv")):
        a = [tuple(r) for r in csv.reader(p.open())]
        sp = args.secondary / p.name
        if not sp.exists():                       # không có bộ phụ -> giữ nguyên
            (args.out / p.name).write_bytes(p.read_bytes())
            continue
        b = [tuple(r) for r in csv.reader(sp.open())]
        # TRAKE có 4 cột, KIS có 2 — chỉ trộn khi cùng số cột
        if a and b and len(a[0]) != len(b[0]):
            (args.out / p.name).write_bytes(p.read_bytes())
            continue
        rows = merge_one(a, b, args.keep)
        assert len(rows) == TOTAL, f"{p.name}: {len(rows)} dòng"
        with (args.out / p.name).open("w", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerows([list(r) for r in rows])
        n += 1
    print(f"đã trộn {n} câu -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
