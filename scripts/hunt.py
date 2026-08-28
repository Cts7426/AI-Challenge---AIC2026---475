"""Săn đáp án cho MỘT câu khó bằng cả hai con mắt — CLIP và SigLIP2.

Vì sao cần công cụ riêng: đường ống chính trả về một bảng 100 dòng đã trộn nhiều
nguồn. Khi một câu trượt, thứ cần không phải bảng đó mà là ẢNH — nhiều ảnh, từ
nhiều góc mô tả khác nhau, xếp thành lưới để loại nhanh.

Hai con mắt nhìn khác nhau và đó là lý do giữ cả hai (đo được ở mục 4.4 báo cáo):
với những câu đường ống chính đánh rơi, SigLIP2 quét phẳng đặt shot đúng ở hạng
8-44 — nghĩa là ảnh đúng NẰM TRONG tấm lưới, chỉ cần nhìn.

Mỗi text tả một khoảnh khắc cho ra một tấm lưới riêng: gộp chung thì khoảnh khắc
mạnh nuốt hết chỗ của khoảnh khắc yếu.

Chạy:
    python scripts/hunt.py --qid query-p1-20-kis
    python scripts/hunt.py --text "a red drum kit on a school stage" --both
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

PLANS = REPO / "dev_set/queries/exam_plan.json"
PER_SHOT, PER_VIDEO, DEPTH = 1, 2, 24   # 1 ảnh/shot: frame cùng shot giống hệt nhau


def _texts_for(qid: str, plans_path: Path) -> list[tuple[str, str]]:
    plans = json.loads(plans_path.read_text(encoding="utf-8"))
    p = plans.get(qid)
    if not p:
        raise SystemExit(f"{qid} không có trong {plans_path.name}")
    out = []
    if (p.get("query_en") or "").strip():
        out.append(("full", p["query_en"].strip()))
    for i, a in enumerate(p.get("anchors", []), 1):
        out.append((f"a{i}", a))
    for i, h in enumerate(p.get("hyp", []), 1):
        out.append((f"h{i}", h))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--qid", help="lấy mọi câu mô tả từ file plan")
    ap.add_argument("--plans", type=Path, default=PLANS)
    ap.add_argument("--text", action="append", default=[], help="thêm một câu mô tả rời")
    ap.add_argument("--clip", action="store_true", help="chỉ CLIP")
    ap.add_argument("--siglip2", action="store_true", help="chỉ SigLIP2")
    ap.add_argument("--both", action="store_true", help="cả hai (mặc định)")
    ap.add_argument("--video", help="chỉ tìm trong một video (CLIP)")
    ap.add_argument("--depth", type=int, default=DEPTH)
    ap.add_argument("--out", type=Path, default=REPO / "scratch/hunt")
    args = ap.parse_args()

    texts = _texts_for(args.qid, args.plans) if args.qid else []
    texts += [(f"t{i}", t) for i, t in enumerate(args.text, 1)]
    if not texts:
        ap.error("cần --qid hoặc --text")

    do_clip = args.clip or args.both or not (args.clip or args.siglip2)
    do_sig = args.siglip2 or args.both or not (args.clip or args.siglip2)

    from scripts.contact_sheet import build
    args.out.mkdir(parents=True, exist_ok=True)
    tag = args.qid or "hunt"
    made = []

    if do_clip:
        from backend.retrieval.search import search
        for name, t in texts:
            rows = search(t, query_en=t, top_k=args.depth,
                          filter_video_id=args.video, group_by_shot=True)
            pairs = [(r["video_id"], int(r["frame_idx"])) for r in rows if r.get("frame_idx") is not None]
            if pairs:
                out = args.out / f"{tag}.clip.{name}.jpg"
                build(pairs[: args.depth], out)
                made.append((out, t))

    if do_sig:
        import numpy as np
        from scripts.build_sigdirect_stream import _shot_index, _stream
        from scripts.siglip2_direct import encode, load_cache

        V, F, I = load_cache()
        Vf = V.astype(np.float32)
        shots = _shot_index()
        for name, t in texts:
            q = encode([t])[0].astype(np.float32)
            pairs = _stream(Vf, F, I, q, PER_VIDEO, args.depth, shots, PER_SHOT)
            if pairs:
                out = args.out / f"{tag}.sig.{name}.jpg"
                build(pairs[: args.depth], out)
                made.append((out, t))

    print()
    for out, t in made:
        print(f"  {out.name:44s} {t[:70]}")
    print(f"\n{len(made)} tấm lưới -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
