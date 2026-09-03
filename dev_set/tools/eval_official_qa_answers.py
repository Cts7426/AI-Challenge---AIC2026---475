"""Chấm CỬA ANSWER của Q&A trên bộ đề chính thức (`official_r1r2.jsonl`).

Vì sao phải có file riêng
-------------------------
Trước 02/09 không có công cụ nào đọc được kết quả Q&A trên `p1`:

* `run_evaluation.py` chấm đủ hai cửa (frame + answer) nhưng chỉ nạp được GT
  đúng schema `dev_set/tools/schema.py::GroundTruthQA` — schema đó bắt buộc
  `frame_start`/`frame_end` và ≥ 3 `answer_variants`. `official_r1r2.jsonl`
  KHÔNG có cửa sổ `[s,e]` (BTC chưa công bố, xem `official_r1r2.meta.json`)
  và không có variants, nên nạp thẳng là `TypeError`.
* `eval_official.py` nạp được bộ đề chính thức nhưng chỉ chạy `search()` —
  nó đo TRẦN TRÊN của retrieval, không hề gọi `qa_pipeline`, nên không biết
  gì về answer (đúng như docstring của nó tự khai).

Tức mọi thay đổi thuộc làn Q&A (R3.Q4 định tuyến bằng chứng) không có cách nào
đọc được kết quả trên 4 câu Q&A của `p1`. File này lấp đúng khoảng đó.

⚠️ ĐÂY LÀ THƯỚC PHỤ, KHÔNG PHẢI ĐIỂM BTC
-----------------------------------------
Nó chấm MỘT cửa (answer), không phải hai. `CLAUDE.md` §5.2 nói rất rõ Q&A có
hai cửa tử ĐỘC LẬP: answer đúng + frame sai vẫn = 0. Con số ở đây vì thế luôn
là CẬN TRÊN của điểm thật.

Ngoài ra `official_r1r2.jsonl` không có `answer_variants`, nên `answer_matches`
chạy với variants rỗng — khắt khe hơn chính sách `semantic` mà `run_evaluation`
dùng trên dress25/holdout. Hai con số KHÔNG so trực tiếp với nhau được; chỉ so
TRƯỚC/SAU trong cùng một thước.

Cửa frame vẫn đo được ở `eval_official.py --task QA` (mức video + mức frame với
nhiều mức tolerance). Đọc hai file cùng nhau mới ra bức tranh đủ.

Hạn mức holdout
---------------
`--part p1` là tập TUNE, chạy thoải mái. `--part p2` là HOLDOUT Đợt 2 và tốn
một lượt trong hạn mức 2 lượt của chiến dịch Đợt 3 — phải truyền
`--i-am-spending-a-holdout-run`, script sẽ ghi vào `dev_set/holdout_log.md`.

Chạy
----
    .venv\\Scripts\\python.exe -m dev_set.tools.eval_official_qa_answers --part p1
    .venv\\Scripts\\python.exe -m dev_set.tools.eval_official_qa_answers --part p1 \\
        --out dev_set/results/qa_answers_p1_after_r3q4.json
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GT_PATH = REPO_ROOT / "dev_set" / "ground_truth" / "official_r1r2.jsonl"
HOLDOUT_LOG = REPO_ROOT / "dev_set" / "holdout_log.md"


def load_qa_gt(part: str) -> list[dict]:
    """Câu Q&A của bộ đề chính thức CÓ đáp án chuẩn và CÓ đề bài.

    Bỏ qua câu `answer_text` rỗng/None: không có đáp án thì không chấm được cửa
    answer, và đếm nó thành 0 sẽ làm mẫu số sai lệch âm thầm (`query-p1-9-qa`
    hiện đúng vào ca này — GT để trống).
    """
    if not GT_PATH.is_file():
        raise SystemExit(f"KHÔNG THẤY {GT_PATH}")
    out: list[dict] = []
    bo_qua: list[str] = []
    for line in GT_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        if r.get("task_type") != "QA":
            continue
        if part != "all" and r.get("part") != part:
            continue
        if not r.get("query_text"):
            bo_qua.append(f"{r['query_id']} (thiếu đề bài)")
            continue
        if not (r.get("answer_text") or "").strip():
            bo_qua.append(f"{r['query_id']} (GT chưa có answer_text)")
            continue
        out.append(r)
    if bo_qua:
        print("  [bỏ qua] " + " · ".join(bo_qua))
    return out


def note_holdout_run(n: int, part: str) -> None:
    stamp = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %z")
    with open(HOLDOUT_LOG, "a", encoding="utf-8") as f:
        f.write(
            f"\n- {stamp} · `eval_official_qa_answers.py --part {part}` · {n} câu · "
            f"chiến dịch Đợt 3 (hạn mức 2 lượt)\n"
        )
    print(f"  [holdout] đã ghi vào {HOLDOUT_LOG.name}")


def run(args) -> int:
    gts = load_qa_gt(args.part)
    if not gts:
        print("Không có câu Q&A nào khớp bộ lọc.")
        return 1

    if args.part in ("p2", "all") and not args.i_am_spending_a_holdout_run:
        raise SystemExit(
            "CHẶN: `--part p2` là HOLDOUT Đợt 2, chỉ được mở 2 lần trong cả chiến dịch.\n"
            "Muốn thật thì thêm --i-am-spending-a-holdout-run.\n"
            "Để lặp lại thoải mái, dùng --part p1 (tập tune)."
        )

    # Import muộn: chỉ chạm DB/LLM sau khi đã qua bộ lọc và cổng holdout.
    from backend.common.answer_match import answer_matches
    from backend.indexing.es_client import connect as es_connect
    from backend.indexing.milvus_client import connect as milvus_connect
    from backend.tasks.runner import (
        SolveQueryError,
        runtime_fingerprint as build_runtime_fingerprint,
        solve_query,
    )

    es_connect()
    milvus_connect()
    fingerprint = build_runtime_fingerprint()

    print(f"\n{len(gts)} câu Q&A · part={args.part} · fingerprint={fingerprint[:12]}\n")
    hdr = f"{'query_id':20s} {'khớp':>5s} {'giây':>7s}  {'đáp án hệ thống':38s} {'GT':20s}"
    print(hdr)
    print("-" * len(hdr))

    per_query: list[dict] = []
    for g in gts:
        query = {
            "query_id": g["query_id"],
            "task_type": "QA",
            "query_vi": g["query_text"],
            "split": "tune",
        }
        t0 = time.perf_counter()
        answer_text = ""
        loi = None
        route: dict[str, object] = {}
        video_pred = None
        try:
            run_result = solve_query(query, total=100, runtime_fingerprint=fingerprint)
            # Đáp án NỘP là `answers[0].answer_text` (dòng 1 sau slot allocator).
            # `run_result.answer_text` là đáp án pipeline suy ra trước khi xếp
            # slot; hai cái phải trùng, ưu tiên cái thật sự đi vào file nộp.
            if run_result.answers and run_result.answers[0].answer_text:
                answer_text = str(run_result.answers[0].answer_text)
                video_pred = run_result.answers[0].video_id
            else:
                answer_text = str(run_result.answer_text or "")
            # Route thực tế đã dùng — đây là thứ R3.Q4 thay đổi, phải log ra để
            # đọc được nguyên nhân chứ không chỉ đọc điểm.
            route = {
                key: (run_result.query_plan or {}).get(key)
                for key in ("evidence_type", "answer_mode", "planner_fallback")
            }
        except SolveQueryError as error:
            loi = f"{type(error).__name__}: {error}"
        except Exception as error:  # tool đo — một câu hỏng không được giết cả lượt
            loi = f"{type(error).__name__}: {error}"
        latency = time.perf_counter() - t0

        gt_text = str(g["answer_text"])
        # `official_r1r2.jsonl` không có answer_variants → variants rỗng. Khắt
        # khe hơn policy `semantic` của run_evaluation; xem cảnh báo đầu file.
        khop, tier = answer_matches(answer_text, gt_text, [])
        per_query.append({
            "query_id": g["query_id"],
            "video_id_gt": g.get("video_id"),
            "video_id_pred_row1": video_pred,
            "answer_pred": answer_text,
            "answer_gt": gt_text,
            "answer_match": bool(khop),
            "match_tier": tier,
            "route": route,
            "latency_s": round(latency, 3),
            "error": loi,
        })
        print(f"{g['query_id']:20s} {('✓' if khop else '✗'):>5s} {latency:>7.1f}  "
              f"{(answer_text or (loi or ''))[:38]:38s} {gt_text[:20]:20s}")

    n = len(per_query)
    n_khop = sum(1 for r in per_query if r["answer_match"])
    n_loi = sum(1 for r in per_query if r["error"])
    ty_le = n_khop / n
    tong_giay = sum(r["latency_s"] for r in per_query)

    print("\n" + "=" * 72)
    print("CỬA ANSWER (thước phụ — KHÔNG phải điểm BTC, chưa tính cửa frame)")
    print(f"  khớp           {n_khop}/{n} = {ty_le:.4f}")
    print(f"  lỗi            {n_loi}/{n}")
    print(f"  tổng thời gian {tong_giay/60:.1f} phút · trung bình {tong_giay/n:.1f}s/câu")
    print("  ⚠ answer đúng + frame sai = 0 điểm. Đọc kèm "
          "`eval_official.py --task QA` để biết cửa frame.")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps({
                "run_at": datetime.now(timezone.utc).isoformat(),
                "part": args.part,
                "gate": "answer_only",
                "runtime_fingerprint": fingerprint,
                "aggregate": {
                    "n_queries": n,
                    "n_answer_match": n_khop,
                    "answer_match_rate": round(ty_le, 4),
                    "n_error": n_loi,
                    "total_seconds": round(tong_giay, 1),
                },
                "per_query": per_query,
            }, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"\nĐã ghi → {args.out}")

    if args.part in ("p2", "all"):
        note_holdout_run(n, args.part)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--part", choices=["p1", "p2", "all"], default="p1",
                    help="p1 = tune (chạy thoải mái) · p2 = HOLDOUT (tốn hạn mức)")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--i-am-spending-a-holdout-run", action="store_true")
    return run(ap.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
