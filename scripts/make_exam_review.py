"""Trang soi ảnh cho ĐỀ ĐANG THI — không phải bộ đề cũ.

Vì sao viết mới thay vì dùng `make_kis_answer_sheet.py`: script đó gắn cứng vào
manifest Batch 1 và file findings của đợt 1, nên với đề mới nó hiện lại đáp án
đợt 1 — vô dụng, mà lại KHÔNG báo lỗi. Đúng lớp lỗi im lặng đã làm hỏng đợt 1.

Trang này lấy thẳng từ `submissions/exam_auto`: mỗi câu KIS in đề bài rồi bày
ảnh của N ứng viên đầu bảng, mỗi ảnh đánh số để chỉ đích danh.

Đồng thời ghi mỗi câu một tấm LƯỚI (contact sheet) vào `scratch/exam_sheets/`
để soi nhiều ảnh trong một lần nhìn.

Chạy:
    python scripts/make_exam_review.py --top 18
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

QUERIES = REPO / "dev_set/queries/exam_queries.jsonl"
PLAN = REPO / "dev_set/queries/exam_plan.json"
AUTO = REPO / "submissions/exam_auto"
DUAL_TOP = 48      # tấm chính: bản dịch đầy đủ, hai encoder — đo được phủ 12/18 câu
ANCHOR_TOP = 24    # mỗi anchor một tấm riêng, hẹp hơn


def _dedup_by_shot(rows, shot_of, limit):
    """Một shot chỉ giữ một ảnh: các frame cùng shot trông giống hệt nhau, bày
    nhiều chỉ tốn chỗ mà không thêm thông tin nào để quyết định."""
    out, seen = [], set()
    for v, f in rows:
        key = (v, shot_of(v, f) or f // 200)
        if key in seen:
            continue
        seen.add(key)
        out.append((v, f))
        if len(out) >= limit:
            break
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--top", type=int, default=18, help="số ứng viên bày ra mỗi câu")
    ap.add_argument("--auto", type=Path, default=AUTO)
    ap.add_argument("--out", type=Path, default=REPO / "scratch/exam_review.html")
    ap.add_argument("--sheets", type=Path, default=REPO / "scratch/exam_sheets")
    ap.add_argument("--no-sheets", action="store_true")
    ap.add_argument("--no-siglip2", action="store_true",
                    help="bỏ luồng mắt thứ hai (nhanh hơn ~1 phút, nhưng mất phủ)")
    args = ap.parse_args()

    from backend.retrieval.search import _shot_of_frame as shot_of
    from dev_set.tools.gt_verification_gallery import _load_frame_map, _nearest_keyframe

    fm = _load_frame_map()
    queries = [json.loads(l) for l in QUERIES.read_text(encoding="utf-8").splitlines() if l.strip()]

    parts = ["<title>Soi ứng viên — đề đang thi</title>",
             "<style>body{background:#14161a;color:#dfe4ea;font:15px/1.55 system-ui;margin:24px}"
             "h2{margin:34px 0 6px;font-size:17px;color:#9ad}"
             ".de{color:#c9d1d9;margin:0 0 10px;max-width:900px}"
             ".g{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:8px}"
             ".c{background:#1c2026;border-radius:6px;overflow:hidden}"
             ".c img{width:100%;display:block}"
             ".c b{display:block;padding:4px 6px;font:12px ui-monospace;color:#8fa}</style>"]

    n_sheet = 0
    if not args.no_sheets:
        args.sheets.mkdir(parents=True, exist_ok=True)

    for q in queries:
        if q["task_type"] != "KIS":
            continue
        p = args.auto / f"{q['query_id']}.csv"
        if not p.exists():
            parts.append(f"<h2>{html.escape(q['query_id'])}</h2>"
                         f"<p class='de' style='color:#f66'>THIẾU FILE {p.name}</p>")
            continue
        rows = [(r[0], int(r[1])) for r in csv.reader(p.open())]
        cands = _dedup_by_shot(rows, shot_of, args.top)

        parts.append(f"<h2>{html.escape(q['query_id'])}</h2>")
        parts.append(f"<p class='de'>{html.escape(' '.join(q['query_vi'].split()))}</p><div class='g'>")
        for i, (v, f) in enumerate(cands, 1):
            path, _ = _nearest_keyframe(fm, v, f)
            img = f"<img src='file://{path}'>" if path else "<div style='height:130px'></div>"
            parts.append(f"<div class='c'>{img}<b>{i}. {v}:{f}</b></div>")
        parts.append("</div>")

        if not args.no_sheets:
            from scripts.contact_sheet import build
            try:
                build(cands, args.sheets / f"{q['query_id']}.jpg")
                n_sheet += 1
            except SystemExit:
                pass

    # --- CON MẮT THỨ HAI: HỢP NHẤT CLIP + SigLIP2 ở mức shot ---
    # Đo công bằng (cùng câu truy vấn, cùng quét phẳng, xếp hạng theo shot) cho
    # thấy hai encoder KHÔNG phải một hơn một kém — CLIP thắng 8 câu, SigLIP2
    # thắng 7. Hợp lại thì bảng ứng viên phủ nhiều hơn hẳn mỗi bên:
    #     chỉ CLIP     9/18 câu có đáp án trong lưới
    #     chỉ SigLIP2  9/18
    #     HAI CÁI     12/18            <- lý do bước này tồn tại
    #
    # Chia LÀN chứ không trộn hết vào một tấm: đo được thêm anchor vào cùng tấm
    # với query_en KHÔNG tăng độ phủ (11-12/18) mà lại đẩy đáp án xuống sâu hơn
    # (p1-22 từ ô 4 xuống ô 10). Nên query_en giữ tấm riêng, mỗi anchor một tấm.
    n_dual = 0
    if not args.no_siglip2 and not args.no_sheets and PLAN.exists():
        try:
            from scripts.contact_sheet import build
            from scripts.dual_search import dual_candidates

            plans = json.loads(PLAN.read_text(encoding="utf-8"))
            for q in queries:
                pl = plans.get(q["query_id"])
                if q["task_type"] != "KIS" or not pl:
                    continue
                qen = (pl.get("query_en") or "").strip()
                lanes = []
                if qen:
                    lanes.append(("dual", [qen], DUAL_TOP))
                for i, a in enumerate(list(pl.get("anchors", [])) + list(pl.get("hyp", [])), 1):
                    lanes.append((f"m{i}", [a], ANCHOR_TOP))
                for name, texts, top in lanes:
                    rows = dual_candidates(texts, top)
                    if rows:
                        build(rows, args.sheets / f"{q['query_id']}.{name}.jpg")
                        n_dual += 1
        except Exception as e:   # mắt thứ hai hỏng KHÔNG được kéo sập bước review
            print(f"  ⚠ làn hợp nhất hai encoder lỗi, bỏ qua: {e}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(parts), encoding="utf-8")
    print(f"\ntrang  -> {args.out}")
    if n_sheet:
        print(f"lưới CLIP    -> {args.sheets}/<query_id>.jpg      ({n_sheet} tấm)")
    if n_dual:
        print(f"lưới HAI MẮT -> {args.sheets}/<query_id>.dual.jpg (bản dịch đầy đủ) "
              f"và .m1/.m2/... (từng anchor) · {n_dual} tấm")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
