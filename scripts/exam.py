"""Quy trình thi — bốn bước, mỗi bước một lệnh.

Thiết kế cho cách làm việc thật lúc thi: Claude viết anchor và soi ảnh, người
vận hành bấm lệnh. Sơ tuyển nộp lô và KHÔNG trừ thời gian (AGENTS.md), nên
vòng "máy lọc -> Claude nhìn -> chốt" hoàn toàn nằm trong luật và đáng làm:
đo được đầu bảng tự động chỉ đúng 7/17 lần, còn Claude soi ảnh đúng 17/20.

    1  python scripts/exam.py prepare  SOTUYEN2-bo-de-thi
       -> dev_set/queries/exam_queries.jsonl + exam_plan.json (khung rỗng)
       -> Claude điền anchor/giả thuyết/probe vào exam_plan.json

    2  python scripts/exam.py run
       -> submissions/exam_auto/  (chạy pipeline, chưa có mắt người)

    3  python scripts/exam.py review
       -> scratch/exam_review.html — ảnh top ứng viên từng câu để Claude soi
       -> Claude ghi lựa chọn vào exam_confirm.json

    4  python scripts/exam.py finalize
       -> submissions/exam_final/ + .zip đã qua validator

Bước 3-4 lặp được nhiều lần; mỗi lần chỉ tốn vài phút.
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

PY = sys.executable
QUERIES = REPO / "dev_set/queries/exam_queries.jsonl"
PLAN = REPO / "dev_set/queries/exam_plan.json"
CONFIRM = REPO / "dev_set/queries/exam_confirm.json"
AUTO_DIR = REPO / "submissions/exam_auto"
FINAL_DIR = REPO / "submissions/exam_final"


def _load_queries() -> list[dict]:
    return [json.loads(l) for l in QUERIES.read_text(encoding="utf-8").splitlines() if l.strip()]


def cmd_prepare(args) -> int:
    """Đề .txt -> jsonl + khung plan để Claude điền."""
    subprocess.run([PY, str(REPO / "scripts/txt_to_run_queries.py"),
                    str(args.folder), "-o", str(QUERIES)], check=True, cwd=REPO)
    rows = _load_queries()

    plan = {}
    for q in rows:
        if q["task_type"] != "KIS":
            continue
        plan[q["query_id"]] = {
            "_de_bai": " ".join(q["query_vi"].split()),   # để Claude đọc, không dùng khi chạy
            # BẢN DỊCH ĐẦY ĐỦ cả câu đề, trung thành, dưới 77 token CLIP. Đây là
            # trường quan trọng nhất: đo được dùng bản dịch đầy đủ làm đầu bảng cho
            # Final 0.5459, còn dùng anchor ngắn đầu tiên chỉ 0.2894.
            "query_en": "",
            "anchors": [],   # 2-3 câu tiếng Anh NGẮN, trung thành với đề, mỗi câu tả 1 khoảnh khắc
            "hyp": [],       # giả thuyết cụ thể hoá phần đề nói chung chung (sai chỉ tốn slot)
            "ocr": [],       # chữ có khả năng HIỆN TRÊN MÀN HÌNH: tên riêng, số, từ nước ngoài
            "asr": [],       # từ có khả năng ĐƯỢC NÓI trong video
        }
    PLAN.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")

    # XOÁ xác nhận của đề CŨ. Nếu để lại, `finalize` sẽ nhét đáp án đợt trước vào
    # bài nộp đợt này — sai hoàn toàn mà KHÔNG báo lỗi, đúng lớp lỗi im lặng đã
    # làm hỏng đợt 1. Thà mất công điền lại còn hơn nộp nhầm.
    if CONFIRM.exists():
        CONFIRM.write_text(json.dumps({
            "_huong_dan": "Claude điền: {query_id: {video_id, frame, note}}. "
                          "Câu không điền thì giữ nguyên thứ tự tự động.",
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        print("  đã xoá exam_confirm.json của đề cũ")

    n = {t: sum(1 for q in rows if q["task_type"] == t) for t in ("KIS", "QA", "TRAKE")}
    print(f"\n{len(rows)} câu: KIS {n['KIS']} · QA {n['QA']} · TRAKE {n['TRAKE']}")
    print(f"  đề     -> {QUERIES}")
    print(f"  plan   -> {PLAN}   ← Claude điền anchors/hyp/ocr/asr rồi chạy bước 2")
    return 0


def _llm_ready() -> bool:
    """QA/TRAKE cần LLM. `run.py` CHỦ ĐỘNG DỪNG nếu lô có câu cần LLM mà
    LLM_BACKEND chưa đặt tường minh — hành vi đúng (không tự tiêu tiền của ai),
    nhưng nó làm chết luôn cả 20 câu KIS vốn không cần LLM. Nên KIS phải được
    tách ra chạy riêng, đừng để nó chết lây."""
    import os
    return bool(os.environ.get("LLM_BACKEND"))


def cmd_run(args) -> int:
    """Plan -> submission tự động (chưa có mắt người)."""
    if not PLAN.exists():
        print("chưa có exam_plan.json — chạy bước prepare trước")
        return 1
    plan = {k: v for k, v in json.loads(PLAN.read_text(encoding="utf-8")).items()
            if v.get("anchors")}
    if not plan:
        print("exam_plan.json chưa có anchor nào — Claude cần điền trước")
        return 1

    # Bước 1: run.py dựng bảng đầu bằng slot allocator (đo được tốt hơn hẳn lấy
    # thẳng output search làm đầu bảng: Final 0.4894 so với 0.3035).
    base_dir = REPO / "submissions/exam_base"
    rows = _load_queries()
    enriched = []
    for q in rows:
        pl = plan.get(q["query_id"])
        if pl:
            # ƯU TIÊN bản dịch đầy đủ; chỉ lùi về anchor đầu khi Claude chưa viết.
            # Chênh lệch giữa hai lựa chọn này là 0.5459 so với 0.2894 — lớn hơn
            # mọi cải tiến thuật toán đã thử.
            qen = (pl.get("query_en") or "").strip() or (pl["anchors"][0] if pl.get("anchors") else None)
            if qen:
                q = {**q, "query_en": qen}
        enriched.append(q)
    thieu = [k for k, v in plan.items() if not (v.get("query_en") or "").strip()]
    if thieu:
        print(f"  ⚠ {len(thieu)} câu chưa có bản dịch đầy đủ `query_en`, đang dùng tạm "
              f"anchor đầu (kém hơn nhiều): {', '.join(thieu[:6])}")

    # KIS chạy riêng, LUÔN chạy. QA/TRAKE chỉ chạy khi có LLM.
    kis = [q for q in enriched if q["task_type"] == "KIS"]
    rest = [q for q in enriched if q["task_type"] != "KIS"]

    tmp = REPO / "dev_set/queries/exam_queries_en.jsonl"
    tmp.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in kis) + "\n",
                   encoding="utf-8")
    subprocess.run([PY, str(REPO / "run.py"), "--queries", str(tmp),
                    "--out", str(base_dir)], check=True, cwd=REPO)

    if rest:
        if _llm_ready():
            tmp2 = REPO / "dev_set/queries/exam_queries_llm.jsonl"
            tmp2.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rest) + "\n",
                            encoding="utf-8")
            r = subprocess.run([PY, str(REPO / "run.py"), "--queries", str(tmp2),
                                "--out", str(base_dir)], cwd=REPO)
            if r.returncode:
                print(f"\n  ⚠ {len(rest)} câu QA/TRAKE chạy lỗi — KIS vẫn xong, xử lý riêng sau")
        else:
            ids = ", ".join(q["query_id"] for q in rest)
            print(f"\n  ⚠ BỎ QUA {len(rest)} câu cần LLM: {ids}")
            print("     LLM_BACKEND chưa đặt. Đặt rồi chạy lại `exam.py run` để làm nốt.")
            print("     KIS không bị ảnh hưởng, vẫn chạy đủ.\n")

    # Bước 2: đắp đuôi bằng probe + giả thuyết + đào sâu video
    plan_only = {k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")}
                 for k, v in plan.items()}
    plan_tmp = REPO / "dev_set/queries/exam_plan_clean.json"
    plan_tmp.write_text(json.dumps(plan_only, ensure_ascii=False), encoding="utf-8")
    subprocess.run([PY, str(REPO / "scripts/build_kis_submission.py"),
                    "--plans", str(plan_tmp), "--manifest", str(QUERIES),
                    "--base", str(base_dir), "--out", str(AUTO_DIR)], check=True, cwd=REPO)

    # Câu QA/TRAKE lấy nguyên từ run.py
    for q in rows:
        if q["task_type"] != "KIS":
            src = base_dir / f"{q['query_id']}.csv"
            if src.exists():
                (AUTO_DIR / src.name).write_bytes(src.read_bytes())
    print(f"\nxong -> {AUTO_DIR}   (bước 3: review)")
    return 0


def cmd_review(args) -> int:
    """Trang ảnh top ứng viên để Claude soi bằng mắt."""
    # KHÔNG dùng make_kis_answer_sheet.py: nó gắn cứng vào manifest và findings
    # của Batch 1, với đề mới nó hiện lại đáp án cũ mà không báo lỗi.
    subprocess.run([PY, str(REPO / "scripts/make_exam_review.py")], check=True, cwd=REPO)
    if not CONFIRM.exists():
        CONFIRM.write_text(json.dumps({
            "_huong_dan": "Claude điền: {query_id: {video_id, frame, note}}. "
                          "Câu không điền thì giữ nguyên thứ tự tự động.",
        }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nảnh -> scratch/exam_review.html")
    print(f"chốt -> {CONFIRM}   ← Claude điền lựa chọn rồi chạy bước 4")
    return 0


def cmd_finalize(args) -> int:
    """Áp lựa chọn của Claude, validate, đóng ZIP."""
    from backend.export.exporter import validate_file

    conf = {}
    if CONFIRM.exists():
        conf = {k: v for k, v in json.loads(CONFIRM.read_text(encoding="utf-8")).items()
                if not k.startswith("_")}
    if conf:
        findings = REPO / "dev_set/queries/exam_findings.json"
        findings.write_text(json.dumps({"entries": conf}, ensure_ascii=False), encoding="utf-8")
        subprocess.run([PY, str(REPO / "scripts/apply_visual_rerank.py"),
                        "--in", str(AUTO_DIR), "--out", str(FINAL_DIR),
                        "--findings", str(findings)], check=True, cwd=REPO)
    else:
        FINAL_DIR.mkdir(parents=True, exist_ok=True)
        for p in AUTO_DIR.glob("*.csv"):
            (FINAL_DIR / p.name).write_bytes(p.read_bytes())
        print("chưa có xác nhận nào — dùng nguyên kết quả tự động")

    bad = [p.name for p in sorted(FINAL_DIR.glob("*.csv")) if validate_file(p)]
    n = len(list(FINAL_DIR.glob("*.csv")))
    print(f"\nvalidator: {n - len(bad)}/{n} file sạch" + (f" · LỖI: {bad}" if bad else ""))
    if bad:
        print("KHÔNG đóng ZIP khi còn file lỗi — sửa trước đã")
        return 1

    import zipfile
    zip_path = REPO / "submissions/exam_final.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(FINAL_DIR.glob("*.csv")):
            z.write(p, f"submission/{p.name}")   # ZIP phải có thư mục top-level `submission/`
    import hashlib
    sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    print(f"ZIP  -> {zip_path}")
    print(f"SHA256 {sha}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("prepare"); p1.add_argument("folder", type=Path); p1.set_defaults(fn=cmd_prepare)
    sub.add_parser("run").set_defaults(fn=cmd_run)
    sub.add_parser("review").set_defaults(fn=cmd_review)
    sub.add_parser("finalize").set_defaults(fn=cmd_finalize)
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
