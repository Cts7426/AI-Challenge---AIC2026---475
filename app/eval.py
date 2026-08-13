# app/eval.py — E4.2: chấm một lô bài nộp bằng đúng công thức của BTC.
#
# Chạy:  python -m app.eval runs/lan_1.jsonl
#
# Không có thước đo thì mọi thay đổi về sau là mò. Và lỗi trong thước đo nguy hơn lỗi
# trong search: search sai thì điểm thấp và mình đi sửa; thước đo sai thì mình sửa
# nhầm chỗ suốt hai tuần mà vẫn thấy số đẹp.
#
# Hai thứ file này KHÔNG tự định nghĩa, vì định nghĩa hai lần là hai con số khác nhau:
#   · "thế nào là đúng"   → LabelIndex của app/labels.py (D3.5 gọi đúng hàm đó)
#   · công thức R@k/Final → data/config/scoring.py

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from app.labels import LabelIndex
from data.config.scoring import K_THRESHOLDS, MAX_ANSWERS, final_score, r_at_k

TASK_TYPES = ("KIS", "QA", "TRAKE")


# ------------------------------------------------------------------ dữ liệu vào

@dataclass(frozen=True)
class SubmittedRow:
    """Một câu trả lời đã nộp. Thứ tự trong list CHÍNH LÀ thứ hạng."""

    video_id: str
    frame_ids: tuple[int, ...]
    answer_text: str | None = None


@dataclass(frozen=True)
class QueryRun:
    """Toàn bộ bài nộp cho MỘT truy vấn."""

    query_id: str
    task_type: str
    answers: tuple[SubmittedRow, ...]
    query_vi: str = ""


# ------------------------------------------------------------------- kết quả ra

@dataclass
class QueryScore:
    """Điểm của một truy vấn, kèm đủ thứ để soi vì sao nó thấp."""

    query_id: str
    task_type: str
    query_vi: str
    r_scores: list[float]
    final: float
    by_k: dict[int, float]
    first_hit_rank: int | None      # hạng câu đầu tiên có điểm > 0
    n_rows: int
    answer_unjudged: int = 0        # Q&A: frame đúng nhưng chưa ai chấm answer


@dataclass
class Report:
    scores: list[QueryScore] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)   # query_id chưa có nhãn

    def by_task(self, task_type: str) -> list[QueryScore]:
        return [s for s in self.scores if s.task_type == task_type]

    def mean(self, scores: list[QueryScore] | None = None) -> dict:
        """Final + 5 giá trị R@k, trung bình trên một nhóm truy vấn."""
        group = self.scores if scores is None else scores
        if not group:
            return {"final": 0.0, "n": 0, **{k: 0.0 for k in K_THRESHOLDS}}
        return {
            "final": sum(s.final for s in group) / len(group),
            "n": len(group),
            **{k: sum(s.by_k[k] for s in group) / len(group) for k in K_THRESHOLDS},
        }


# ------------------------------------------------------- R-Score theo từng dạng

def r_score_kis(row: SubmittedRow, query_id: str, index: LabelIndex) -> float:
    """`I(đúng video ∧ frame ∈ [s,e])` — nhị phân.

    Chỉ xét frame đầu tiên: KIS nộp đúng một frame mỗi dòng (validator của D0.2 đã
    chặn). Dòng nhiều frame là dữ liệu hỏng, không phải cơ hội gỡ điểm.
    """
    if not row.frame_ids:
        return 0.0
    return 1.0 if index.is_correct(query_id, row.video_id, row.frame_ids[0]) else 0.0


def r_score_qa(row: SubmittedRow, query_id: str, index: LabelIndex) -> tuple[float, bool]:
    """`I(đúng video ∧ frame ∈ [s,e] ∧ answer đúng ngữ nghĩa)`.

    Ra: (điểm, answer_chưa_chấm). Cờ thứ hai để báo riêng số dòng "frame đúng mà
    answer chưa ai phán" — nuốt nó thành 0 thì điểm Q&A tụt theo số nhãn còn thiếu
    và nhìn như hệ thống dở.

    Hai cửa tử độc lập: frame sai = 0, answer sai = 0. Không có điểm an ủi.
    """
    if not row.frame_ids or not index.is_correct(query_id, row.video_id, row.frame_ids[0]):
        return 0.0, False
    verdict = index.is_answer_correct(query_id, row.answer_text)
    if verdict is None:
        return 0.0, True
    return (1.0 if verdict else 0.0), False


def r_score_trake(row: SubmittedRow, query_id: str, index: LabelIndex) -> float:
    """`0` nếu sai video, ngược lại `(1/N)·Σⱼ I(idⱼ ∈ [sⱼ,eⱼ])` — điểm từng phần.

    Khớp THEO VỊ TRÍ: frame thứ j phải rơi vào khoảng của khoảnh khắc thứ j. Nộp đủ
    4 frame đúng nhưng đảo thứ tự vẫn là 0.

    Mẫu số lấy từ ĐÁP ÁN, không lấy len(frame_ids): nộp thiếu khoảnh khắc mà chia cho
    số mình nộp thì trúng 1/1 ra 1.0 thay vì 0.25.

    Sai video ra 0 tự nhiên vì `is_correct` tra theo khoá có video_id — không cần
    nhánh if riêng, và cũng không quên được.
    """
    n = index.n_moments(query_id) or len(row.frame_ids)
    if not n:
        return 0.0
    hits = sum(
        1 for j, f in enumerate(row.frame_ids[:n])
        if index.is_correct(query_id, row.video_id, f, moment_idx=j)
    )
    return hits / n


# ------------------------------------------------------------------ chấm một lô

def score_query(run: QueryRun, index: LabelIndex) -> QueryScore:
    """Chấm đủ 100 dòng của một truy vấn.

    Chỉ xét `MAX_ANSWERS` dòng đầu — nộp dư thì phần dư không được tính, đúng như
    BTC ("gửi tối đa 100 câu trả lời").
    """
    rows = run.answers[:MAX_ANSWERS]
    r_scores: list[float] = []
    unjudged = 0

    for row in rows:
        if run.task_type == "QA":
            score, missing = r_score_qa(row, run.query_id, index)
            unjudged += int(missing)
        elif run.task_type == "TRAKE":
            score = r_score_trake(row, run.query_id, index)
        else:
            score = r_score_kis(row, run.query_id, index)
        r_scores.append(score)

    rank = next((i for i, v in enumerate(r_scores, 1) if v > 0), None)
    return QueryScore(
        query_id=run.query_id,
        task_type=run.task_type,
        query_vi=run.query_vi,
        r_scores=r_scores,
        final=final_score(r_scores),
        by_k={k: r_at_k(r_scores, k) for k in K_THRESHOLDS},
        first_hit_rank=rank,
        n_rows=len(rows),
        answer_unjudged=unjudged,
    )


def score_runs(runs: list[QueryRun], index: LabelIndex | None = None) -> Report:
    """Chấm nhiều truy vấn.

    Truy vấn CHƯA CÓ NHÃN NÀO thì bỏ qua và ghi vào `skipped`, KHÔNG tính 0. Tính 0
    thì Final tụt theo số câu chưa chấm — con số trông như hệ thống dở, thật ra là bộ
    nhãn chưa xong, và người đọc sẽ đi sửa nhầm chỗ.
    """
    index = index or LabelIndex()
    labelled = set(index.query_ids())
    report = Report()
    for run in runs:
        if run.query_id not in labelled:
            report.skipped.append(run.query_id)
            continue
        report.scores.append(score_query(run, index))
    return report


# --------------------------------------------------------------------- đọc file

def read_runs(path: str | Path) -> list[QueryRun]:
    """Đọc file kết quả chạy, JSONL — mỗi dòng một truy vấn.

        {"query_id": "q_ab12", "task_type": "KIS", "query_vi": "…",
         "answers": [{"video_id": "L21_V001", "frame_ids": [123], "answer_text": null}]}

    Không đọc thẳng file nộp: file nộp (CSV theo submit_format) đã bị tước `query_id`
    và `task_type` — đúng như thiết kế tầng đó — nên không đủ để chấm. Đây là định
    dạng của khâu ĐO, không phải khâu nộp.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"không có file runs: {p}")

    out: list[QueryRun] = []
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
            out.append(QueryRun(
                query_id=d["query_id"],
                task_type=d["task_type"],
                query_vi=d.get("query_vi", ""),
                answers=tuple(
                    SubmittedRow(
                        video_id=a["video_id"],
                        frame_ids=tuple(int(f) for f in a["frame_ids"]),
                        answer_text=a.get("answer_text"),
                    )
                    for a in d["answers"]
                ),
            ))
        except Exception as e:
            print(f"  [cảnh báo] {p.name}:{i} bỏ qua dòng hỏng — {type(e).__name__}: {e}")
    return out


def from_submissions(subs) -> list[QueryRun]:
    """`QuerySubmission` của D0.2 → `QueryRun`, cho chỗ đã có sẵn object trong RAM."""
    return [
        QueryRun(
            query_id=s.query_id,
            task_type=s.task_type,
            answers=tuple(
                SubmittedRow(a.video_id, tuple(a.frame_ids), a.answer_text) for a in s.answers
            ),
        )
        for s in subs
    ]


# ------------------------------------------------------------------- trình bày

def _table_row(name: str, m: dict) -> str:
    return (f"  {name:<22}{m['final']:>6.3f}   " +
            "  ".join(f"{m[k]:>5.3f}" for k in K_THRESHOLDS))


def format_report(report: Report, n_worst: int = 10) -> str:
    """Ba mức: theo dạng bài · tổng chung · danh sách câu tệ nhất."""
    out: list[str] = []
    out.append(f"TỔNG ({len(report.scores)} truy vấn có nhãn)".ljust(24)
               + " Final   " + "  ".join(f"R@{k:<3}" for k in K_THRESHOLDS))

    for task in TASK_TYPES:
        group = report.by_task(task)
        if group:
            out.append(_table_row(f"{task} ({len(group)} câu)", report.mean(group)))
    out.append("  " + "─" * 58)
    out.append(_table_row("CHUNG", report.mean()))

    unjudged = sum(s.answer_unjudged for s in report.scores)
    if unjudged:
        out.append(f"\n⚠️  {unjudged} dòng Q&A có frame ĐÚNG nhưng answer CHƯA AI CHẤM "
                   f"→ đang tính 0. Điểm Q&A thật có thể cao hơn.")
    if report.skipped:
        out.append(f"⚠️  {len(report.skipped)} truy vấn chưa có nhãn nào → BỎ QUA, "
                   "không tính 0: " + ", ".join(report.skipped[:5])
                   + ("…" if len(report.skipped) > 5 else ""))

    worst = sorted(report.scores, key=lambda s: s.final)[:n_worst]
    if worst:
        out.append(f"\n{len(worst)} CÂU TỆ NHẤT")
        for s in worst:
            why = (f"đúng đầu tiên ở hạng {s.first_hit_rank}" if s.first_hit_rank
                   else f"không có dòng đúng nào trong {s.n_rows}")
            desc = f'"{s.query_vi[:34]}"' if s.query_vi else s.task_type
            out.append(f"  {s.query_id:<14}{s.final:>5.2f}  {desc:<38} — {why}")
    return "\n".join(out)


def main() -> int:
    """CLI: `python -m app.eval runs/lan_1.jsonl`"""
    import argparse

    ap = argparse.ArgumentParser(description="Chấm điểm bài nộp theo công thức BTC.")
    ap.add_argument("runs", help="file JSONL kết quả chạy")
    ap.add_argument("--labels-dir", type=Path, default=None,
                    help="thư mục nhãn (mặc định dev_set/)")
    ap.add_argument("--worst", type=int, default=10, help="số câu tệ nhất cần liệt kê")
    args = ap.parse_args()

    index = LabelIndex(directory=args.labels_dir)
    if not len(index):
        print("Chưa có nhãn nào trong dev_set/ — chấm nhãn bằng UI debug trước "
              "(streamlit run app/debug_ui.py).")
        return 1

    report = score_runs(read_runs(args.runs), index)
    if not report.scores:
        print("Không truy vấn nào trong file runs có nhãn để chấm.")
        return 1
    print(format_report(report, args.worst))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
