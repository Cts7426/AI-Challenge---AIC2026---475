"""Chấm retrieval trên bộ đề CHÍNH THỨC Đợt 1+2 (`official_r1r2.jsonl`).

Vì sao cần bộ chấm riêng
------------------------
`eval_kis_only.py` chấm theo `GroundTruthKIS` có `[frame_start, frame_end]` thật.
Bộ đề chính thức KHÔNG có cửa sổ đó — BTC chưa công bố độ rộng `[s,e]`, ta chỉ
biết `frame_exact` mà người thao tác đã chốt. Chấm mù bằng một cửa sổ đoán ra là
tự tạo ra một con số không ai kiểm được.

Nên file này đo HAI TẦNG, tách bạch:

  1. MỨC VIDEO  — hạng của dòng đầu tiên trúng đúng `video_id`.
     Không phụ thuộc cửa sổ `[s,e]` chút nào, nên đây là thước ĐÁNG TIN NHẤT
     hiện có, và là thước dùng cho cổng chặn R3.K1 (đổi encoder) và R3.K4
     (rerank). Tường recall và tường ranking đều đo trọn ở tầng này.

  2. MỨC FRAME  — chấm như BTC nhưng với cửa sổ giả định `frame_exact ± tol`,
     báo cáo ở NHIỀU tol cùng lúc. Một thay đổi chỉ đáng tin khi nó cải thiện ở
     MỌI mức tol; thắng ở tol=40 mà thua ở tol=5 là dấu hiệu đang mua điểm bằng
     cách rải rộng chứ không phải định vị đúng hơn.

Mức video còn dùng được cho QA và TRAKE: cả ba dạng đều phải tìm đúng video
trước đã. Với QA, nếu retrieval không ra nổi video thì suy luận LLM giỏi tới đâu
cũng bằng 0 — chạy `--task QA` ở đây cho biết trần trên của làn Q&A mà không tốn
một lời gọi suy luận nào.

Hạn mức holdout
---------------
`--part p1` (Đợt 1) là tập TUNE, chạy thoải mái.
`--part p2` (Đợt 2) là HOLDOUT, chỉ được mở **2 lần** trong cả chiến dịch Đợt 3
(BUILD_TASKS "Chiến dịch Đợt 3"). Script CHẶN p2 trừ khi truyền
`--i-am-spending-a-holdout-run` và ghi lại vào `dev_set/holdout_log.md`.

Chạy
----
    .venv\\Scripts\\python.exe -m dev_set.tools.eval_official --part p1
    .venv\\Scripts\\python.exe -m dev_set.tools.eval_official --part p1 --task KIS --no-llm
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GT_PATH = REPO_ROOT / "dev_set" / "ground_truth" / "official_r1r2.jsonl"
HOLDOUT_LOG = REPO_ROOT / "dev_set" / "holdout_log.md"

# Thứ tự độ tin, cao xuống thấp. `--min-confidence` cắt theo danh sách này.
CONFIDENCE_ORDER = [
    "VERIFIED_ASSISTANT",
    "LIKELY_ASSISTANT",
    "CORROBORATED",
    "HIGH",
    "MEDIUM",
    "DISPUTED",
    "UNKNOWN",
]
K_THRESHOLDS = (1, 5, 20, 50, 100)
DEFAULT_TOLERANCES = (5, 15, 40)


# ───────────────────────────────────────────────────────────────── chấm điểm

def rscore_video(row_video_id: str, gt_video_id: str) -> float:
    """R-Score chỉ xét video. Không đụng tới frame nên không cần biết `[s,e]`."""
    return 1.0 if row_video_id == gt_video_id else 0.0


def recall_at_k_video(rows: list[dict], gt_video_id: str, k: int) -> float:
    """R@k = R-Score cao nhất trong k dòng đầu — cùng công thức BTC, tầng video."""
    best = 0.0
    for r in rows[:k]:
        best = max(best, rscore_video(r["video_id"], gt_video_id))
        if best == 1.0:
            break
    return best


def final_video(rows: list[dict], gt_video_id: str) -> float:
    return sum(recall_at_k_video(rows, gt_video_id, k) for k in K_THRESHOLDS) / len(K_THRESHOLDS)


def rank_of_video(rows: list[dict], gt_video_id: str) -> int | None:
    """Hạng 1-based của dòng đầu tiên trúng video, None nếu không có trong list."""
    for i, r in enumerate(rows, 1):
        if r["video_id"] == gt_video_id:
            return i
    return None


def recall_at_k_frame(rows: list[dict], gt_video_id: str, lo: int, hi: int, k: int) -> float:
    best = 0.0
    for r in rows[:k]:
        if r["video_id"] == gt_video_id and lo <= r["frame_idx"] <= hi:
            return 1.0
    return best


def final_frame(rows: list[dict], gt_video_id: str, lo: int, hi: int) -> float:
    return sum(
        recall_at_k_frame(rows, gt_video_id, lo, hi, k) for k in K_THRESHOLDS
    ) / len(K_THRESHOLDS)


# ───────────────────────────────────────────────────────────────── nạp dữ liệu

def load_gt(part: str, task: str, min_conf: str) -> list[dict]:
    if not GT_PATH.is_file():
        raise SystemExit(
            f"KHÔNG THẤY {GT_PATH}\n"
            "Dựng trước bằng: .venv\\Scripts\\python.exe dev_set\\tools\\build_official_gt.py ..."
        )
    keep = set(CONFIDENCE_ORDER[: CONFIDENCE_ORDER.index(min_conf) + 1])
    out = []
    for line in GT_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        if part != "all" and r["part"] != part:
            continue
        if task != "all" and r["task_type"] != task:
            continue
        if r.get("video_confidence") not in keep:
            continue
        if not r.get("query_text"):
            continue
        out.append(r)
    return out


def apply_query_en(gts: list[dict], en_file: Path | None, use_vi: bool) -> str:
    """Quyết định `query_en` cho từng câu và trả tên nguồn để ghi vào artefact.

    Ba nguồn, loại trừ nhau:
      `file` — bản dịch ĐÓNG BĂNG (dev_set/tools/freeze_query_en.py). Dùng cho
               bake-off: mọi nhánh nhận đúng một chuỗi EN nên encoder là biến duy nhất.
      `vi`   — nhánh vector nhận thẳng tiếng Việt. Đo được "bỏ bước dịch thì sao"
               với encoder đa ngữ, và cũng là chế độ suy giảm khi không có LLM.
      `auto` — để `search()` tự dịch qua llm() (hành vi cũ). ⚠️ Bản dịch thành
               biến trôi giữa các lần chạy, và lỗi LLM bị nuốt rồi rơi về tiếng
               Việt IM LẶNG — không dùng cho phép so encoder.

    Sửa `gts` tại chỗ. Trả tên nguồn để `--out` ghi lại được arm nào đã chạy.
    """
    if en_file is not None and use_vi:
        raise SystemExit("--query-en và --query-en-vi loại trừ nhau, chọn một.")

    if use_vi:
        for g in gts:
            g["query_en"] = g["query_text"]
        return "vi"

    if en_file is not None:
        if not en_file.is_file():
            raise SystemExit(
                f"KHÔNG THẤY {en_file}\n"
                "Dựng trước bằng: python -m dev_set.tools.freeze_query_en --part p1"
            )
        data = json.loads(en_file.read_text(encoding="utf-8"))
        meta = data.get("_meta", {})
        thieu = [g["query_id"] for g in gts if not data.get(g["query_id"])]
        if thieu:
            # Thiếu câu nào là câu đó lặng lẽ rơi về tiếng Việt — đúng thứ bản
            # đóng băng sinh ra để loại bỏ. Dừng thay vì đo một tập lai.
            raise SystemExit(
                f"File dịch thiếu {len(thieu)}/{len(gts)} câu (ví dụ: {thieu[:3]}). "
                "Chạy lại freeze_query_en.py cho đủ trước khi đo."
            )
        for g in gts:
            g["query_en"] = data[g["query_id"]]
        return f"file:{en_file.name}(model={meta.get('llm_model', '?')})"

    return "auto"


def note_holdout_run(n: int, part: str) -> None:
    stamp = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %z")
    line = (
        f"\n- {stamp} · `eval_official.py --part {part}` · {n} câu · "
        f"chiến dịch Đợt 3 (hạn mức 2 lượt)\n"
    )
    with open(HOLDOUT_LOG, "a", encoding="utf-8") as f:
        f.write(line)
    print(f"  [holdout] đã ghi vào {HOLDOUT_LOG.name}")


# ────────────────────────────────────────────────────────────────────── chạy

def run(args) -> int:
    gts = load_gt(args.part, args.task, args.min_confidence)
    if not gts:
        print("Không có câu nào khớp bộ lọc.")
        return 1

    query_en_source = apply_query_en(gts, args.query_en, args.query_en_vi)
    vector_backend = os.environ.get("VECTOR_BACKEND", "clip").strip().lower()

    if args.part in ("p2", "all") and not args.i_am_spending_a_holdout_run:
        raise SystemExit(
            "CHẶN: `--part p2` là HOLDOUT Đợt 2, chỉ được mở 2 lần trong cả chiến dịch.\n"
            "Muốn thật thì thêm --i-am-spending-a-holdout-run (sẽ ghi vào holdout_log.md).\n"
            "Để lặp lại thoải mái, dùng --part p1 (tập tune)."
        )

    # Import muộn: chỉ chạm DB/model khi đã qua hết bộ lọc và cổng holdout.
    from backend.indexing.es_client import connect as es_connect
    from backend.indexing.milvus_client import connect as milvus_connect
    from backend.retrieval import search as search_mod
    from backend.retrieval.search import search
    from backend.slot.allocator import ShotHit, allocate
    from dev_set.tools.run_evaluation import _to_shot_hits

    # Ghi đè độ sâu pool cho lượt đo. Gán vào module chứ không truyền tham số:
    # `_search_core()` đọc hằng số này như biến toàn cục, nên đây là điểm duy
    # nhất đổi được mà không phải sửa chữ ký hàm production giữa lúc đo.
    if args.candidate_multiplier is not None:
        search_mod.CANDIDATE_MULTIPLIER = args.candidate_multiplier
    candidate_multiplier = search_mod.CANDIDATE_MULTIPLIER
    if args.rrf_k is not None:
        search_mod.RRF_K = args.rrf_k
    rrf_k = search_mod.RRF_K
    if args.rerank and args.no_rerank:
        raise SystemExit("--rerank và --no-rerank loại trừ nhau, chọn một.")
    branches = {"ocr_probe": not args.no_ocr_probe}
    if args.dual_vector:
        branches["vector_siglip2"] = True
    # None = để config quyết định; False = tắt tường minh bất kể config.
    rerank_flag = False if args.no_rerank else (args.rerank or None)

    # Giá trị THỰC THI của hai knob đọc-từ-config, tính ngay tại đây để ghi vào
    # artefact. Phải khớp đúng cách `search()` giải nghĩa None, nếu không thì
    # nhãn lại nói dối lần nữa — xem chú thích ở chỗ ghi provenance bên dưới.
    from data.config.rerank import ENABLED as _RERANK_ON
    from data.config.video_prior import ALPHA as _VP_ALPHA, ENABLED as _VP_ON
    rerank_effective = bool(_RERANK_ON) if rerank_flag is None else bool(rerank_flag)
    if not _VP_ON:
        video_prior_effective = 0.0
    elif args.video_prior is None:
        video_prior_effective = float(_VP_ALPHA)
    else:
        video_prior_effective = float(args.video_prior)

    # Trọng số nhánh: sửa TRÊN MODULE config. `_search_core()` import
    # BRANCH_WEIGHTS ở trong thân hàm (mỗi lần gọi một lần) nên nó đọc lại giá
    # trị mới; vá ở đây là điểm duy nhất đổi được mà không sửa file config giữa
    # lúc đang đo.
    import data.config.search_weights as sw_mod
    if args.branch_weights:
        try:
            for o in args.branch_weights.split(","):
                ten, gt = o.split("=")
                ten = ten.strip()
                if ten not in sw_mod.BRANCHES:
                    raise SystemExit(
                        f"--branch-weights: không có nhánh {ten!r}. "
                        f"Có: {sorted(sw_mod.BRANCHES)}")
                sw_mod.BRANCH_WEIGHTS[ten] = float(gt)
        except ValueError:
            raise SystemExit(f"--branch-weights sai định dạng: "
                             f"{args.branch_weights!r}. Đúng dạng: ten=so,ten=so")
    branch_weights = dict(sw_mod.BRANCH_WEIGHTS)

    # Bảng chia slot: truyền THẲNG vào allocate() qua tham số `table` sẵn có,
    # không vá module — allocate() đã nhận bảng làm đối số nên không cần mẹo.
    from data.config.slot_budget import SLOT_BUDGET
    slot_budget = SLOT_BUDGET
    if args.slot_budget:
        try:
            slot_budget = [
                (int(a), int(b))
                for a, b in (o.split("x") for o in args.slot_budget.split(","))
            ]
        except ValueError:
            raise SystemExit(f"--slot-budget sai định dạng: {args.slot_budget!r}. "
                             "Đúng dạng: 1x8,4x4,10x2,56x1")
        tong = sum(a * b for a, b in slot_budget)
        if tong != args.total:
            raise SystemExit(
                f"--slot-budget cộng ra {tong} slot, cần đúng {args.total}. "
                "Bảng thiếu slot là bỏ trống dòng nộp — vứt điểm miễn phí.")

    es_connect()
    milvus_connect()

    tols = [int(t) for t in args.tolerances.split(",")]
    per_query: list[dict] = []

    print(f"\n{len(gts)} câu · part={args.part} · task={args.task} · "
          f"độ tin ≥ {args.min_confidence}")
    # In cấu hình arm ngay đầu output: đọc lại log mà không biết arm nào đã chạy
    # thì hai bảng số trông giống hệt nhau.
    print(f"VECTOR_BACKEND={vector_backend} · query_en={query_en_source} · "
          f"candidate_multiplier={candidate_multiplier} "
          f"(pool={args.total * candidate_multiplier}/nhánh)\n")
    hdr = f"{'query_id':24s} {'task':6s} {'hạng vid':>9s} {'Final_vid':>10s} " + \
          " ".join(f"{'±'+str(t):>7s}" for t in tols)
    print(hdr)
    print("-" * len(hdr))

    for g in gts:
        t0 = time.perf_counter()
        try:
            res = search(
                g["query_text"],
                query_en=g.get("query_en"),
                top_k=100,
                group_by_shot=True,
                branches=branches,
                rerank_top50=rerank_flag,
                video_prior_alpha=args.video_prior,
            )
        except Exception as e:
            print(f"{g['query_id']:24s} LỖI: {type(e).__name__}: {e}")
            per_query.append({"query_id": g["query_id"], "error": f"{type(e).__name__}: {e}"})
            continue
        latency = time.perf_counter() - t0

        rows = allocate(_to_shot_hits(res), total=args.total, table=slot_budget)
        rows = [
            {"video_id": r.video_id, "frame_idx": r.frame_ids[0]}
            for r in rows if r.frame_ids
        ]

        gv = g["video_id"]
        rank = rank_of_video(rows, gv)
        fv = final_video(rows, gv)

        rec = {
            "query_id": g["query_id"],
            "task_type": g["task_type"],
            "video_id_gt": gv,
            "video_rank": rank,
            "final_video": round(fv, 4),
            "r_at_k_video": {
                str(k): recall_at_k_video(rows, gv, k) for k in K_THRESHOLDS
            },
            "latency_s": round(latency, 3),
            "video_confidence": g.get("video_confidence"),
        }
        if g.get("frame_exact") is not None:
            fe = g["frame_exact"]
            rec["frame_exact"] = fe
            rec["final_frame"] = {
                str(t): round(final_frame(rows, gv, fe - t, fe + t), 4) for t in tols
            }
        per_query.append(rec)

        ff = rec.get("final_frame", {})
        print(
            f"{g['query_id']:24s} {g['task_type']:6s} "
            f"{(str(rank) if rank else '—'):>9s} {fv:>10.4f} "
            + " ".join(f"{ff.get(str(t), 0.0):>7.2f}" for t in tols)
        )

    ok = [r for r in per_query if "error" not in r]
    if not ok:
        print("\nKhông câu nào chạy được.")
        return 1

    n = len(ok)
    agg = {
        "n_queries": n,
        "n_error": len(per_query) - n,
        "final_video": round(sum(r["final_video"] for r in ok) / n, 4),
        "r_at_k_video": {
            str(k): round(sum(r["r_at_k_video"][str(k)] for r in ok) / n, 4)
            for k in K_THRESHOLDS
        },
        "video_found_in_100": sum(1 for r in ok if r["video_rank"]),
        "video_rank_1": sum(1 for r in ok if r["video_rank"] == 1),
        "latency_median_s": round(sorted(r["latency_s"] for r in ok)[n // 2], 3),
    }
    withf = [r for r in ok if "final_frame" in r]
    if withf:
        agg["final_frame"] = {
            str(t): round(sum(r["final_frame"][str(t)] for r in withf) / len(withf), 4)
            for t in tols
        }

    print("\n" + "=" * 72)
    print("MỨC VIDEO — thước chính, không phụ thuộc cửa sổ [s,e] chưa biết")
    print(f"  Final          {agg['final_video']:.4f}")
    for k in K_THRESHOLDS:
        print(f"  R@{k:<4d}        {agg['r_at_k_video'][str(k)]:.4f}")
    print(f"  tìm ra video   {agg['video_found_in_100']}/{n}")
    print(f"  đúng hạng 1    {agg['video_rank_1']}/{n}")
    print(f"  latency median {agg['latency_median_s']:.3f}s  (ngân sách 30s)")
    if withf:
        print("\nMỨC FRAME — cửa sổ giả định frame_exact ± tol")
        for t in tols:
            print(f"  Final ±{t:<3d}     {agg['final_frame'][str(t)]:.4f}")
        print("  ⚠ chỉ tin thay đổi nào cải thiện ở MỌI mức tol")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(
                {
                    "run_at": datetime.now(timezone.utc).isoformat(),
                    "part": args.part,
                    "task": args.task,
                    "min_confidence": args.min_confidence,
                    # Hai trường này ĐỊNH DANH ARM. Thiếu chúng thì ba file kết
                    # quả bake-off không phân biệt được nhau ngoài tên file.
                    "vector_backend": vector_backend,
                    "query_en_source": query_en_source,
                    "candidate_multiplier": candidate_multiplier,
                    "rrf_k": rrf_k,
                    "dual_vector": bool(args.dual_vector),
                    "slot_budget": slot_budget,
                    # ⚠️ Ghi giá trị THỰC THI, không phải cờ dòng lệnh. Bản cũ ghi
                    # `bool(args.rerank)`: không truyền cờ nào thì nó ghi `false`
                    # trong khi `search()` nhận None rồi đọc `data/config/rerank.py`
                    # — mà file đó ENABLED=True từ 02/09. Tức artefact khai "rerank
                    # tắt" cho những lượt rerank THỰC SỰ CHẠY. Đúng lớp lỗi im lặng
                    # mà bất biến 8 (mọi artefact đi kèm meta) sinh ra để chặn:
                    # số thì đúng, nhãn thì sai, và sáu tháng sau không ai dựng lại nổi.
                    "rerank_top50": rerank_effective,
                    "video_prior_alpha": video_prior_effective,
                    "branch_weights": branch_weights,
                    "tolerances": tols,
                    "aggregate": agg,
                    "per_query": per_query,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"\nĐã ghi → {args.out}")

    if args.part in ("p2", "all"):
        note_holdout_run(n, args.part)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--part", choices=["p1", "p2", "all"], default="p1",
                    help="p1 = tune (Đợt 1, chạy thoải mái) · p2 = HOLDOUT (Đợt 2, 2 lượt)")
    ap.add_argument("--task", choices=["KIS", "QA", "TRAKE", "all"], default="all")
    ap.add_argument("--min-confidence", choices=CONFIDENCE_ORDER, default="HIGH",
                    help="mặc định HIGH — bỏ MEDIUM/DISPUTED khỏi phép đo")
    ap.add_argument("--query-en", type=Path, default=None, metavar="FILE",
                    help="file bản dịch ĐÓNG BĂNG (dev_set.tools.freeze_query_en). "
                         "Dùng cho bake-off encoder: mọi nhánh nhận cùng một chuỗi EN")
    ap.add_argument("--query-en-vi", action="store_true",
                    help="nhánh vector nhận thẳng tiếng Việt (bỏ bước dịch). "
                         "Loại trừ với --query-en")
    ap.add_argument("--branch-weights", default=None, metavar="A=x,B=y",
                    help="ghi đè trọng số RRF của một số nhánh, vd "
                         "'vector_siglip2=0.6'. Nhánh không nhắc tới giữ nguyên "
                         "giá trị trong config. R3.K3.")
    ap.add_argument("--video-prior", type=float, default=None, metavar="A",
                    help="trọng số tiên nghiệm mức video (0..1). Bỏ trống = đọc "
                         "data/config/video_prior.py. 0 = tắt hẳn.")
    # Hai công tắc TẮT. Cần để dựng lại đúng cấu hình đã chạy ở Đợt 2 (trước
    # chiến dịch Đợt 3): lúc đó chưa có `ocr_probe` lẫn rerank. Không có chúng
    # thì không A/B được "cấu hình cũ vs mới" trên holdout, mà đó là phép đo duy
    # nhất phân biệt được "tune đúng" với "học thuộc 20 câu p1".
    ap.add_argument("--no-ocr-probe", action="store_true",
                    help="tắt nhánh probe token hiếm (R3 mới thêm 03/09). "
                         "Dùng để dựng lại cấu hình Đợt 2.")
    ap.add_argument("--no-rerank", action="store_true",
                    help="tắt hẳn rerank top-50, KỂ CẢ khi data/config/rerank.py "
                         "đang bật. Loại trừ với --rerank.")
    ap.add_argument("--rerank", action="store_true",
                    help="bật tầng rerank top-50 (R3.K4). Mặc định tắt, "
                         "đúng như config production.")
    ap.add_argument("--slot-budget", default=None, metavar="BANG",
                    help="ghi đè SLOT_BUDGET, dạng '1x8,4x4,10x2,56x1' "
                         "(số shot × số slot mỗi shot). R3.K5.")
    ap.add_argument("--dual-vector", action="store_true",
                    help="bật nhánh vector THỨ HAI (encoder còn lại) — R3.K3. "
                         "Mặc định tắt, đúng như production.")
    ap.add_argument("--rrf-k", type=int, default=None, metavar="K",
                    help="ghi đè RRF_K cho lượt đo này (quét R3.K3)")
    ap.add_argument("--candidate-multiplier", type=int, default=None, metavar="N",
                    help="ghi đè CANDIDATE_MULTIPLIER cho lượt đo này (mỗi nhánh "
                         "lấy top_k*N ứng viên đưa vào RRF). Không truyền thì "
                         "dùng giá trị trong data/config/search_weights.py")
    ap.add_argument("--tolerances", default=",".join(map(str, DEFAULT_TOLERANCES)))
    ap.add_argument("--total", type=int, default=100)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--i-am-spending-a-holdout-run", action="store_true",
                    help="bắt buộc khi --part p2; ghi vào dev_set/holdout_log.md")
    return run(ap.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
