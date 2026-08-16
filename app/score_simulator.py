# app/score_simulator.py — D3.5: đổi bảng chia slot rồi xem điểm đổi thế nào,
# KHÔNG chạy lại pipeline.
#
# Vì sao cần một file riêng, `eval.py` không làm được:
# `eval.py` (E4.2) chấm bộ 100 dòng ĐÃ đóng gói xong. Muốn hỏi "chia slot kiểu khác
# thì được mấy điểm" thì phải mở gói ra đóng lại — mà nguyên liệu (danh sách shot ứng
# viên do search trả về) đã bị vứt ngay sau khi `allocate()` chạy. File này giữ nguyên
# liệu đó lại, đóng gói lại theo nhiều bảng, mỗi lần chấm một lượt.
#
# Chênh lệch chi phí là lý do task này tồn tại: một vòng search thật cho ~20 câu tốn
# hàng chục phút (dịch bằng LLM + Milvus + ES). Đóng gói lại từ nguyên liệu có sẵn tốn
# vài giây → thử 5 bảng trong một lần ngồi thay vì 5 buổi.
#
# ⚠️ KHÔNG tự định nghĩa công thức chấm. Ba nơi cùng chấm là ba con số khác nhau:
#   R-Score từng dòng (BTC mục 2.1) → dev_set/tools/scoring.py
#   R@k và Final Score (BTC mục 2.2) → data/config/scoring.py
#   Chia 100 slot                    → backend/slot/allocator.py
# File này chỉ ghép ba thứ đó lại và in ra cho người đọc.
#
# Hai chế độ:
#   replay — cần dev set thật. Trả lời "trên bộ đề của mình, bảng nào hơn".
#   sweep  — KHÔNG cần dev set. Trả lời "nếu cửa sổ đáp án của BTC rộng w frame thì
#            bảng nào hơn", quét trên shot THẬT của shots.parquet.
#
# Chạy (từ thư mục gốc repo):
#     python -m app.score_simulator sweep
#     python -m app.score_simulator replay --candidates dev_set/results/run_X/candidates.jsonl \
#                                          --gt dev_set/ground_truth/tune_gt.jsonl

from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass, field
from pathlib import Path

from backend.slot import ShotHit, allocate
from backend.slot.allocator import SHOTS_PATH
from data.config.scoring import K_THRESHOLDS, final_score, r_at_k
from data.config.slot_budget import SLOT_BUDGET
from data.config.submit_format import ANSWERS_PER_QUERY, Answer
from dev_set.tools.schema import GroundTruthKIS, GroundTruthQA, GroundTruthTRAKE
from dev_set.tools.scoring import rscore_kis, rscore_qa, rscore_trake

# Các bảng đem ra so, xếp từ ĐÀO SÂU tới RẢI RỘNG. Cả năm đều cộng đúng 100 slot.
#
# Đây là chỗ THỬ, không phải chỗ cấu hình: bảng nào thắng thì chép tay sang
# data/config/slot_budget.py. Để allocator đọc thẳng từ đây là biến một file thí
# nghiệm thành file sản xuất, và rồi không ai biết lúc thi đang chạy bảng nào.
CANDIDATE_TABLES: dict[str, list[tuple[int, int]]] = {
    "sâu    2×20": [(2, 20), (4, 10), (10, 2)],
    "hiện tại 3×8": list(SLOT_BUDGET),
    "cân    5×5": [(5, 5), (15, 3), (30, 1)],
    "rộng  10×3": [(10, 3), (20, 2), (30, 1)],
    "rất rộng 1×": [(100, 1)],
}


# ------------------------------------------------------------------ dữ liệu vào

@dataclass(frozen=True)
class Candidate:
    """Một shot ứng viên do search trả về — đủ để dựng lại 100 dòng nộp.

    Ba trường này là TOÀN BỘ thứ `allocate()` cần. Giữ đúng ba trường (không giữ
    cả kết quả search thô) để file nguyên liệu nhỏ và không phụ thuộc lược đồ của
    tầng search — tầng đó đổi trường thì chỗ nạp đổi, chỗ này không đổi.
    """

    shot_id: str
    score: float
    best_keyframe_id: str | None = None


@dataclass(frozen=True)
class QueryCandidates:
    """Cái "rổ" của một truy vấn: mọi thứ cần để đóng gói lại mà không chạy lại search.

    `answer_text` cố định theo truy vấn, KHÔNG đổi theo bảng slot — đổi cách chia slot
    không sửa được câu trả lời sai. Nên câu Q&A trả lời sai thì mọi bảng đều ra 0, và
    đó là thông tin đúng chứ không phải lỗi: nó nói "đừng tune slot, đi sửa Q&A".
    """

    query_id: str
    task_type: str
    candidates: list[Candidate]
    answer_text: str | None = None
    n_trake: int | None = None


@dataclass
class QueryResult:
    """Kết quả đóng gói lại một truy vấn theo MỘT bảng."""

    query_id: str
    task_type: str
    table_name: str
    answers: list[Answer]
    r_scores: list[float]
    final: float
    by_k: dict[int, float] = field(default_factory=dict)
    winner_rank: dict[int, int | None] = field(default_factory=dict)


def load_candidates(path: str | Path) -> list[QueryCandidates]:
    """Đọc file nguyên liệu (JSONL, mỗi dòng một truy vấn).

        {"query_id": "K01", "task_type": "KIS", "answer_text": null, "n_trake": null,
         "candidates": [{"shot_id": "L21_V001#s0006", "score": 0.031,
                         "best_keyframe_id": "L21_V001#k0007"}, ...]}

    File này do `dev_set/tools/run_evaluation.py` ghi ra lúc chạy đo. Nó KHÔNG phải
    `answers.jsonl` — `answers.jsonl` là 100 dòng đã đóng gói, không lùi lại được.
    """
    out: list[QueryCandidates] = []
    for i, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
            out.append(QueryCandidates(
                query_id=d["query_id"],
                task_type=d["task_type"],
                candidates=[Candidate(c["shot_id"], float(c["score"]),
                                      c.get("best_keyframe_id")) for c in d["candidates"]],
                answer_text=d.get("answer_text"),
                n_trake=d.get("n_trake"),
            ))
        except Exception as e:
            print(f"  [cảnh báo] {Path(path).name}:{i} bỏ qua dòng hỏng — {type(e).__name__}: {e}")
    return out


def load_ground_truth(path: str | Path) -> dict[str, object]:
    """Đọc ground truth của dev set → {query_id: GroundTruth*}.

    Dùng lại lược đồ của `dev_set/tools/schema.py` chứ không dựng kiểu riêng: đây là
    định dạng đáp án mà `run_evaluation.py` đang đọc, hai định dạng đáp án song song
    là hai con số khác nhau (xem reports/E42_TECHNICAL_REPORT.md §7.4).
    """
    gts: dict[str, object] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        qid, task = row.get("query_id"), row.get("task_type")
        clean = {k: v for k, v in row.items() if k != "task_type"}
        try:
            if task == "KIS":
                gts[qid] = GroundTruthKIS(**clean)
            elif task == "QA":
                gts[qid] = GroundTruthQA(**clean)
            elif task == "TRAKE":
                gts[qid] = GroundTruthTRAKE(**clean)
            else:
                raise ValueError(f"task_type lạ: {task}")
        except Exception as e:
            print(f"  [cảnh báo] bỏ qua ground truth {qid} — {type(e).__name__}: {e}")
    return gts


# --------------------------------------------------------------- chấm một truy vấn

def r_scores_of(answers: list[Answer], gt, task_type: str) -> list[float]:
    """100 dòng đã nộp → 100 R-Score, đúng luật BTC mục 2.1.

    Gọi thẳng `rscore_*` của dev_set, không viết lại: luật "sai video = 0 ngay",
    "answer phải khớp ngữ nghĩa", "TRAKE khớp theo vị trí" đã nằm ở đó và đã có test.
    """
    out: list[float] = []
    for a in answers:
        if task_type == "KIS":
            out.append(rscore_kis(a.video_id, a.frame_ids[0], gt))
        elif task_type == "QA":
            out.append(rscore_qa(a.video_id, a.frame_ids[0], a.answer_text or "", gt))
        else:
            out.append(rscore_trake(a.video_id, a.frame_ids, gt))
    return out


def winner_ranks(r_scores: list[float]) -> dict[int, int | None]:
    """Ngưỡng k → HẠNG của dòng ăn điểm R@k. None = trong k dòng đầu không dòng nào có điểm.

    Đây là con số quyết định "đào sâu hay rải rộng", và là thứ điểm tổng KHÔNG nói ra:
      · dòng thắng nằm ở hạng 40 → R@1 và R@5 đang bỏ trắng, phải đẩy nó LÊN ĐẦU
        (đổi thứ hạng shot), thêm slot không cứu được gì
      · không dòng nào có điểm trong cả 100 → lỗi ở tầng search, không phải tầng slot
    """
    out: dict[int, int | None] = {}
    for k in K_THRESHOLDS:
        best = r_at_k(r_scores, k)
        out[k] = (next((i for i, v in enumerate(r_scores[:k], 1) if v == best), None)
                  if best > 0 else None)
    return out


def simulate_query(qc: QueryCandidates, gt, table: list[tuple[int, int]],
                   table_name: str = "", total: int = ANSWERS_PER_QUERY) -> QueryResult:
    """Đóng gói lại một truy vấn theo `table` rồi chấm. Đây là vòng lặp trong cùng.

    Gọi ĐÚNG `allocate()` của đường nộp thật, không mô phỏng lại cách chia: mô phỏng
    lại là đo một hệ khác với hệ lúc thi, và sai lệch đó không có dấu hiệu gì.
    """
    answers = allocate(
        [ShotHit(c.shot_id, c.score, c.best_keyframe_id) for c in qc.candidates],
        qc.task_type, answer_text=qc.answer_text, n_trake=qc.n_trake,
        total=total, table=table,
    )
    rs = r_scores_of(answers, gt, qc.task_type)
    return QueryResult(
        query_id=qc.query_id, task_type=qc.task_type, table_name=table_name,
        answers=answers, r_scores=rs, final=final_score(rs),
        by_k={k: r_at_k(rs, k) for k in K_THRESHOLDS},
        winner_rank=winner_ranks(rs),
    )


def compare_tables(qcs: list[QueryCandidates], gts: dict[str, object],
                   tables: dict[str, list[tuple[int, int]]]) -> dict[str, dict]:
    """Mỗi bảng → điểm trung bình trên mọi truy vấn CÓ ground truth.

    Truy vấn thiếu đáp án bị bỏ qua chứ không tính 0 — tính 0 thì điểm tụt theo số
    đáp án còn thiếu và nhìn như bảng slot dở (cùng lối nghĩ với `eval.py::score_runs`).
    """
    out: dict[str, dict] = {}
    for name, table in tables.items():
        results = [simulate_query(qc, gts[qc.query_id], table, name)
                   for qc in qcs if qc.query_id in gts]
        if not results:
            continue
        n = len(results)
        out[name] = {
            "n": n,
            "final": sum(r.final for r in results) / n,
            **{k: sum(r.by_k[k] for r in results) / n for k in K_THRESHOLDS},
            "results": results,
        }
    return out


# ------------------------------------------------------------------ chế độ sweep

def _sample_scenario(rng: random.Random, shots_df, n_shots: int) -> list[ShotHit]:
    """`n_shots` shot THẬT, mỗi shot một video khác nhau, điểm giảm dần theo hạng.

    Mỗi video một shot vì tầng search có `group_by_shot=True` và kết quả thật trải trên
    nhiều video. Lấy liền một mạch các shot của cùng một video sẽ cho độ dài shot tương
    quan với nhau, làm số quét ra đẹp hơn thực tế.
    """
    rows = shots_df.sample(n=n_shots, random_state=rng.randrange(1 << 30))
    return [ShotHit(r.shot_id, 1.0 - i * 0.01)
            for i, r in enumerate(rows.itertuples(index=False))]


# Trần số vị trí cửa sổ đem quét trong một shot. Shot dài nhất 1795 frame; quét hết
# mọi vị trí × mọi bảng × mọi kịch bản là hàng chục triệu vòng lặp cho một con số mà
# lấy 400 điểm rải đều đã hội tụ. Đây là hằng CHI PHÍ, không phải hằng chiến thuật.
MAX_WINDOW_POSITIONS = 400


def expected_final(answers: list[Answer], video_id: str, bounds: tuple[int, int],
                   width: int) -> float:
    """Điểm kỳ vọng nếu cửa sổ đáp án rộng `width` nằm ĐÂU ĐÓ trong shot đúng.

    Vào: 100 dòng đã nộp · video và biên của shot đúng · độ rộng cửa sổ giả định.
    Ra: trung bình Final Score trên mọi vị trí đặt được của cửa sổ.

    Vì sao quét mọi vị trí thay vì bốc ngẫu nhiên: chạy lại phải ra đúng một con số,
    nếu không thì lần tune sau không so được với lần trước.

    Cửa sổ [s, e] của BTC nằm trong shot ở đâu thì mình không biết — đó chính là ẩn số
    `CLAUDE.md` mục 11 nói "chênh lệch giữa hai giả định này lớn hơn mọi cải tiến model".
    Nên coi mọi vị trí là như nhau và lấy trung bình.
    """
    a, b = bounds
    ranked = [(i, f) for i, ans in enumerate(answers, 1)
              if ans.video_id == video_id for f in ans.frame_ids]
    if not ranked:
        return 0.0

    last = max(a, b - width + 1)
    step = max(1, (last - a + 1) // MAX_WINDOW_POSITIONS)
    positions = range(a, last + 1, step)

    tong = 0.0
    n_pos = 0
    for s in positions:
        rs = [0.0] * len(answers)
        for rank, f in ranked:
            if s <= f <= s + width - 1:
                rs[rank - 1] = 1.0
        tong += final_score(rs)
        n_pos += 1
    return tong / n_pos if n_pos else 0.0


def sweep(tables: dict[str, list[tuple[int, int]]], widths: list[int], ranks: list[int],
          n_scenarios: int, n_shots: int, seed: int = 42) -> dict[str, dict[int, float]]:
    """Quét GIẢ ĐỊNH — không cần dev set. Ra: {tên bảng: {độ rộng cửa sổ: điểm kỳ vọng}}.

    Ba ẩn số được quét thay vì đoán:
      · độ rộng cửa sổ đáp án (`widths`) — BTC chưa công bố cho KIS
      · shot đúng nằm ở hạng mấy (`ranks`) — tầng search quyết định, chưa đo được
      · shot dài bao nhiêu — lấy MẪU THẬT từ shots.parquet, không giả lập

    `allocate()` chỉ chạy MỘT lần cho mỗi (kịch bản, bảng): 100 dòng nộp ra sao không
    phụ thuộc việc shot nào là shot đúng. Chỉ định shot đúng rồi tính là phép số học
    trên kết quả đã có — nhờ vậy quét 5 bảng × 5 độ rộng × 3 hạng chỉ tốn vài giây.
    """
    import pandas as pd

    from backend.slot.allocator import _bounds_of

    rng = random.Random(seed)
    shots_df = pd.read_parquet(SHOTS_PATH, columns=["shot_id", "video_id"])
    # Mỗi video giữ 1 shot rồi mới bốc mẫu — tránh hai shot cùng video trong một kịch bản
    shots_df = shots_df.groupby("video_id", sort=True).head(1)

    out: dict[str, dict[int, float]] = {name: {w: 0.0 for w in widths} for name in tables}
    for _ in range(n_scenarios):
        hits = _sample_scenario(rng, shots_df, n_shots)
        for name, table in tables.items():
            answers = allocate(hits, "KIS", table=table)
            for r in ranks:
                if r > len(hits):
                    continue
                vid, start, end = _bounds_of(hits[r - 1])
                for w in widths:
                    out[name][w] += expected_final(answers, vid, (start, end), w)

    n = n_scenarios * len([r for r in ranks if r <= n_shots])
    return {name: {w: v / n for w, v in cols.items()} for name, cols in out.items()}


# -------------------------------------------------------------------- trình bày

def format_slots(res: QueryResult, top: int = 10) -> str:
    """In các dòng đầu + MỌI dòng có điểm, đánh dấu dòng nào ăn điểm ở ngưỡng nào.

    Không in đủ 100 dòng như đặc tả D3.5 viết: 100 dòng × 20 truy vấn × 5 bảng là
    10.000 dòng, không ai đọc. In `top` dòng đầu (nơi 40% điểm nằm) cộng mọi dòng có
    điểm ở sâu hơn — đó là toàn bộ thông tin cần để phán "đào sâu hay đẩy hạng".
    Cần đủ 100 thì `--slots 100`.
    """
    # Một dòng thường thắng NHIỀU ngưỡng (hạng 3 ăn cả R@5, R@20, R@50, R@100). Giữ
    # ngưỡng NHỎ NHẤT — đó là ngưỡng dòng này bắt đầu ăn điểm, và cũng là thứ cho biết
    # còn cách R@1 bao xa. Giữ ngưỡng lớn nhất thì dòng nào cũng hiện "thắng R@100",
    # vô nghĩa.
    thang: dict[int, int] = {}
    for k in sorted(K_THRESHOLDS):
        rank = res.winner_rank[k]
        if rank is not None and rank not in thang:
            thang[rank] = k
    lines = [f"  {res.query_id}  {res.task_type}  ·  bảng «{res.table_name}»  "
             f"·  Final = {res.final:.3f}"]
    for i, (a, s) in enumerate(zip(res.answers, res.r_scores), 1):
        if i > top and s <= 0:
            continue
        dau = f"  ✓ {s:.2f}" if s > 0 else ""
        nhan = f"   ← thắng R@{thang[i]}" if i in thang else ""
        frames = ", ".join(map(str, a.frame_ids))
        lines.append(f"    hạng {i:>3}  {a.video_id:<10} frame {frames:<22}{dau}{nhan}")
    dong_k = "  ".join(f"R@{k}={res.by_k[k]:.2f}" for k in K_THRESHOLDS)
    lines.append(f"    {dong_k}")
    return "\n".join(lines)


def format_comparison(cmp: dict[str, dict]) -> str:
    """Bảng so sánh các phương án chia slot, sắp theo Final giảm dần."""
    if not cmp:
        return "Không có truy vấn nào có ground truth để chấm."
    head = f"  {'BẢNG':<14}{'n':>4}{'Final':>8}" + "".join(f"{'R@' + str(k):>8}" for k in K_THRESHOLDS)
    lines = [head, "  " + "─" * (len(head) - 2)]
    for name, m in sorted(cmp.items(), key=lambda kv: -kv[1]["final"]):
        lines.append(f"  {name:<14}{m['n']:>4}{m['final']:>8.3f}"
                     + "".join(f"{m[k]:>8.3f}" for k in K_THRESHOLDS))
    return "\n".join(lines)


def format_sweep(table: dict[str, dict[int, float]], widths: list[int]) -> str:
    """Ma trận bảng × độ rộng cửa sổ. Đọc theo CỘT: mỗi cột là một giả định về BTC."""
    head = f"  {'BẢNG':<14}" + "".join(f"{'w=' + str(w):>9}" for w in widths)
    lines = [head, "  " + "─" * (len(head) - 2)]
    for name, cols in table.items():
        lines.append(f"  {name:<14}" + "".join(f"{cols[w]:>9.3f}" for w in widths))
    return "\n".join(lines)


# -------------------------------------------------------------------------- CLI

def main() -> int:
    ap = argparse.ArgumentParser(description="Mô phỏng chấm điểm khi đổi bảng chia slot (D3.5).")
    sub = ap.add_subparsers(dest="mode", required=True)

    p_re = sub.add_parser("replay", help="chạy lại trên nguyên liệu của một lần đo thật")
    p_re.add_argument("--candidates", required=True, help="candidates.jsonl của một run")
    p_re.add_argument("--gt", required=True, help="file ground truth của dev set")
    p_re.add_argument("--slots", type=int, default=10, help="số dòng đầu in ra mỗi truy vấn")
    p_re.add_argument("--detail", action="store_true", help="in chi tiết 100 slot từng truy vấn")

    p_sw = sub.add_parser("sweep", help="quét giả định, KHÔNG cần dev set")
    p_sw.add_argument("--widths", default="5,10,20,50,100", help="độ rộng cửa sổ đáp án giả định")
    p_sw.add_argument("--ranks", default="1,3,10", help="shot đúng nằm ở hạng mấy")
    p_sw.add_argument("--scenarios", type=int, default=20)
    p_sw.add_argument("--shots", type=int, default=31, help="số shot ứng viên mỗi kịch bản")
    args = ap.parse_args()

    if args.mode == "sweep":
        widths = [int(x) for x in args.widths.split(",")]
        ranks = [int(x) for x in args.ranks.split(",")]
        print(f"Quét {len(CANDIDATE_TABLES)} bảng × {len(widths)} độ rộng cửa sổ × "
              f"{len(ranks)} hạng, trên {args.scenarios} kịch bản shot THẬT.\n")
        out = sweep(CANDIDATE_TABLES, widths, ranks, args.scenarios, args.shots)
        print(format_sweep(out, widths))
        print("\n  w = độ rộng cửa sổ đáp án [s,e] của BTC (chưa công bố cho KIS).")
        print(f"  Trung bình trên các giả định shot đúng ở hạng {ranks}.")
        print("  Bảng thắng ở cột nào thì chép tay sang data/config/slot_budget.py.")
        return 0

    qcs = load_candidates(args.candidates)
    gts = load_ground_truth(args.gt)
    if not qcs:
        print("Không đọc được truy vấn nào trong file nguyên liệu.")
        return 1
    thieu = [q.query_id for q in qcs if q.query_id not in gts]
    if thieu:
        print(f"  [cảnh báo] {len(thieu)} truy vấn không có ground truth, BỎ QUA: "
              + ", ".join(thieu[:5]) + ("…" if len(thieu) > 5 else ""))

    cmp = compare_tables(qcs, gts, CANDIDATE_TABLES)
    print(format_comparison(cmp))

    if args.detail and cmp:
        tot_nhat = max(cmp, key=lambda k: cmp[k]["final"])
        print(f"\nChi tiết theo bảng thắng «{tot_nhat}»:")
        for res in cmp[tot_nhat]["results"]:
            print(format_slots(res, args.slots))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
