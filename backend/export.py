# backend/export.py — D0.2: gom đáp án, kiểm ngữ nghĩa, ghi file nộp
#
# Chia vai với data/config/submit_format.py (BUILD_TASKS D0.2 yêu cầu tách hai tầng):
#   submit_format.py  → ĐỊNH DẠNG: file trông ra sao, tên cột, thứ tự ô
#   export.py (đây)   → CƠ CHẾ  : gom theo truy vấn, kiểm ngữ nghĩa, ghi đĩa
#
# Vì sao file này KHÔNG được biết tên cột nào?
# → BTC chưa công bố định dạng. Tách ra thì lúc công bố chỉ sửa submit_format.py,
#   pipeline không đổi một dòng.
#
# Vì sao validator ngữ nghĩa nằm ở đây mà không nằm cạnh tầng định dạng?
# → Cần đọc video_info.parquet (video có thật không, dài bao nhiêu frame).
#   Tầng định dạng phải sạch, không phụ thuộc dữ liệu dẫn xuất của Data Factory.
#
# Vì sao trả list[Issue] thay vì raise ngay lỗi đầu tiên?
# → D6.1 (preflight) cần in TOÀN BỘ lỗi một lượt. 
#   Nếu raise từng cái thì sửa một lỗi,chạy lại, lòi lỗi tiếp.
#   Trước hạn nộp thì đó là công thức trượt hạn.
#
# Định dạng KHÔNG phải tham số của bất kỳ hàm nào ở đây — nó là hằng SUBMIT_FORMAT
# bên submit_format.py. BTC công bố thì sửa đúng một dòng đó.
#
# Chạy thử (từ thư mục gốc repo):
#     python -m backend.export --demo

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from data.config.submit_format import (
    SUBMIT_FORMAT,
    TASK_TYPES,
    Answer,
    build_submission,
    suggest_filename,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
VIDEO_INFO_PATH = REPO_ROOT / "data" / "derived" / "video_info.parquet"

ANSWERS_PER_QUERY = 100


@dataclass(frozen=True)
class QuerySubmission:
    """Toàn bộ bài nộp cho MỘT truy vấn. Thứ tự `answers` chính là thứ hạng."""

    query_id: str
    task_type: str
    answers: tuple[Answer, ...]


@dataclass(frozen=True)
class Issue:
    """Một lỗi. `rule` là slug ổn định để test bám vào, không bám câu chữ."""

    rule: str
    message: str
    query_id: str | None = None
    position: int | None = None  # vị trí trong list = thứ hạng, đếm từ 1

    def __str__(self) -> str:
        vt = ""
        if self.query_id is not None:
            vt = f" [query={self.query_id}"
            vt += f", hạng {self.position}]" if self.position is not None else "]"
        return f"{self.rule}{vt}: {self.message}"


# ---------------------------------------------------- dữ liệu để kiểm ngữ nghĩa

@lru_cache(maxsize=1)
def _video_frames() -> dict[str, int]:
    """video_id → n_frames, đọc từ video_info.parquet của Data Factory.

    Nạp MỘT lần thành dict: validator tra hàng nghìn lượt, lọc DataFrame mỗi lần
    thì 100 query × 100 dòng đã mất hàng chục giây.
    """
    import pandas as pd

    if not VIDEO_INFO_PATH.exists():
        raise FileNotFoundError(
            f"Không tìm thấy {VIDEO_INFO_PATH} — cần video_info.parquet "
            "(video_id, số frame) để kiểm frame_id hợp lệ."
        )

    # Vì sao dò tên cột thay vì hardcode "n_frames":
    # BUILD_TASKS B0.1a đặt tên cột là `n_frames`, nhưng build_video_info thực tế
    # sinh ra `nb_frames_decoded` (số frame ĐẾM THẬT bằng ffprobe, đúng tinh thần
    # B0.1a: không lấy từ metadata container). Hardcode một tên → ArrowInvalid,
    # validator gãy trên data thật dù test fixture vẫn xanh.
    # Ưu tiên nb_frames_decoded vì nó là số đếm thật; n_frames giữ lại cho fixture.
    df = pd.read_parquet(VIDEO_INFO_PATH)
    for cot in ("nb_frames_decoded", "n_frames"):
        if cot in df.columns:
            return {str(v): int(n) for v, n in zip(df["video_id"], df[cot])}

    raise KeyError(
        f"{VIDEO_INFO_PATH} không có cột số frame nào trong "
        f"('nb_frames_decoded', 'n_frames'). Cột đang có: {list(df.columns)}. "
        "Đây là khoá kiểm frame_id ∈ [0, n_frames) — không có thì không validate được."
    )


def all_video_ids() -> list[str]:
    """Danh sách video_id đã kiểm kê — dùng để dựng dữ liệu test/demo thật."""
    return sorted(_video_frames())


def n_frames_of(video_id: str) -> int:
    return _video_frames()[video_id]


# ----------------------------------------------------- validator TẦNG NGỮ NGHĨA

def validate_submission(
    sub: QuerySubmission,
    *,
    expect_answers: int = ANSWERS_PER_QUERY,
    expected_n: int | None = None,
) -> list[Issue]:
    """Kiểm ngữ nghĩa bài nộp của MỘT truy vấn.

    Input:
      sub            — QuerySubmission
      expect_answers — số câu trả lời bắt buộc (mặc định 100)
      expected_n     — số khoảnh khắc N của TRAKE, nếu đề bài công bố
    Output: list[Issue], rỗng = hợp lệ.
    Bất biến: không sửa `sub`, không ném exception vì dữ liệu sai.
    """
    q = sub.query_id
    issues: list[Issue] = []

    if sub.task_type not in TASK_TYPES:
        issues.append(Issue("task_type", f"task_type '{sub.task_type}' lạ, phải là {TASK_TYPES}", q))

    if not sub.answers:
        return issues + [Issue("empty", "không có câu trả lời nào", q)]

    if len(sub.answers) != expect_answers:
        issues.append(Issue(
            "answer_count",
            f"có {len(sub.answers)} câu trả lời, phải đúng {expect_answers}. "
            "Nộp sai không bị trừ điểm nên thiếu là tự vứt cơ hội.",
            q,
        ))

    issues += _check_duplicates(sub)
    issues += _check_shape(sub, expected_n)
    issues += _check_video_and_frames(sub)
    return issues


def validate_all(
    subs: list[QuerySubmission],
    *,
    expect_answers: int = ANSWERS_PER_QUERY,
    expected_n: dict[str, int] | None = None,
) -> list[Issue]:
    """Kiểm nhiều truy vấn một lượt, kèm phát hiện query_id trùng."""
    issues: list[Issue] = []
    if not subs:
        return [Issue("empty", "không có truy vấn nào để nộp")]

    dem: dict[str, int] = defaultdict(int)
    for s in subs:
        dem[s.query_id] += 1
    for qid, n in dem.items():
        if n > 1:
            issues.append(Issue("query_duplicate", f"query_id xuất hiện {n} lần", qid))

    for s in subs:
        issues += validate_submission(
            s,
            expect_answers=expect_answers,
            expected_n=(expected_n or {}).get(s.query_id),
        )
    return issues


def _check_duplicates(sub: QuerySubmission) -> list[Issue]:
    """Hai câu trả lời trùng nội dung = tiêu hai slot mà chỉ mua một cơ hội."""
    seen: dict[tuple, int] = {}
    out: list[Issue] = []
    for i, a in enumerate(sub.answers, 1):
        # keyframe_id chỉ để debug nên KHÔNG tính vào khóa so trùng
        k = (a.video_id, a.frame_ids, a.answer_text)
        if k in seen:
            out.append(Issue(
                "duplicate_answer",
                f"trùng nội dung với hạng {seen[k]} (video={a.video_id}, frame={a.frame_ids})",
                sub.query_id, i,
            ))
        else:
            seen[k] = i
    return out


def _check_shape(sub: QuerySubmission, expected_n: int | None) -> list[Issue]:
    """Số frame đúng theo dạng bài · TRAKE tăng dần ngặt · Q&A có answer."""
    out: list[Issue] = []
    q, task = sub.query_id, sub.task_type

    if task == "TRAKE":
        do_dai = {len(a.frame_ids) for a in sub.answers}
        if len(do_dai) > 1:
            out.append(Issue(
                "trake_n_inconsistent",
                f"số frame không đồng nhất giữa các dòng: {sorted(do_dai)}. "
                "Mọi câu trả lời của một truy vấn TRAKE phải có cùng N.",
                q,
            ))

    for i, a in enumerate(sub.answers, 1):
        if task in ("KIS", "QA"):
            if len(a.frame_ids) != 1:
                out.append(Issue(
                    "frame_count", f"{task} phải đúng 1 frame, đang có {len(a.frame_ids)}", q, i
                ))
        elif task == "TRAKE":
            if len(a.frame_ids) < 2:
                out.append(Issue(
                    "frame_count", f"TRAKE phải có ít nhất 2 frame, đang có {len(a.frame_ids)}", q, i
                ))
            if expected_n is not None and len(a.frame_ids) != expected_n:
                out.append(Issue(
                    "trake_n_mismatch",
                    f"đề yêu cầu {expected_n} khoảnh khắc, đang nộp {len(a.frame_ids)}", q, i,
                ))
            # Hai khoảnh khắc khác nhau không thể ở cùng một frame
            if any(x >= y for x, y in zip(a.frame_ids, a.frame_ids[1:])):
                out.append(Issue(
                    "trake_not_increasing",
                    f"frame phải tăng dần ngặt, đang là {a.frame_ids}", q, i,
                ))

        if task == "QA" and not (a.answer_text or "").strip():
            out.append(Issue(
                "answer_empty",
                "Q&A bắt buộc có answer — answer sai/rỗng thì frame đúng cũng 0 điểm", q, i,
            ))
        if task != "QA" and a.answer_text is not None:
            out.append(Issue("answer_unexpected", f"{task} không được có answer", q, i))
    return out


def _check_video_and_frames(sub: QuerySubmission) -> list[Issue]:
    """video_id phải tồn tại · frame_id ∈ [0, n_frames).

    Video lạ thì BÁO LỖI chứ không bỏ qua: bỏ qua = lặng lẽ cho trôi dòng sai,
    đúng loại lỗi mà cả dự án đang phòng.
    """
    out: list[Issue] = []
    vf = _video_frames()

    for i, a in enumerate(sub.answers, 1):
        n = vf.get(a.video_id)
        if n is None:
            out.append(Issue(
                "video_unknown",
                f"video_id '{a.video_id}' không có trong video_info.parquet",
                sub.query_id, i,
            ))
            continue  # không biết n_frames thì không kiểm được biên
        for f in a.frame_ids:
            if not (0 <= f < n):
                out.append(Issue(
                    "frame_out_of_range",
                    f"frame_id {f} nằm ngoài [0, {n}) của video {a.video_id}",
                    sub.query_id, i,
                ))
    return out


# ------------------------------------------------------------- kiểm file đã ghi

def validate_file(path: str | Path) -> list[Issue]:
    """File nộp phải là UTF-8 và KHÔNG có BOM.

    Ghi bằng PowerShell (Out-File / Set-Content) trên Windows chèn 3 byte BOM
    \\xef\\xbb\\xbf. Mở bằng mắt không thấy, nhưng bộ chấm đọc cột đầu ra rác.
    """
    path = Path(path)
    if not path.exists():
        return [Issue("file_missing", f"không tìm thấy file: {path}")]

    out: list[Issue] = []
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        out.append(Issue("bom", f"{path.name} có BOM ở đầu file — phải ghi UTF-8 không BOM"))
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as e:
        out.append(Issue("not_utf8", f"{path.name} không phải UTF-8 hợp lệ: {e}"))
    if not raw.strip():
        out.append(Issue("file_empty", f"{path.name} rỗng"))
    return out


def format_issues(issues: list[Issue]) -> str:
    """Gom lỗi thành báo cáo đọc được, nhóm theo luật."""
    if not issues:
        return "HỢP LỆ — không phát hiện lỗi nào."
    theo_luat: dict[str, list[Issue]] = defaultdict(list)
    for i in issues:
        theo_luat[i.rule].append(i)
    dong = [f"KHÔNG HỢP LỆ — {len(issues)} lỗi thuộc {len(theo_luat)} loại:"]
    for rule, ds in sorted(theo_luat.items()):
        dong.append(f"  [{rule}] {len(ds)} lỗi")
        for i in ds[:3]:
            dong.append(f"      - {i}")
        if len(ds) > 3:
            dong.append(f"      ... và {len(ds) - 3} lỗi nữa")
    return "\n".join(dong)


# -------------------------------------------------------------------- xuất file

def to_submission(sub: QuerySubmission) -> str:
    """Nội dung file nộp của MỘT truy vấn. Uỷ quyền toàn bộ định dạng cho submit_format.

    Không có tham số chọn format: định dạng do hằng SUBMIT_FORMAT quyết định.
    Đổi format = sửa một dòng trong data/config/submit_format.py.
    """
    return build_submission(sub.query_id, sub.task_type, list(sub.answers))


def write_submissions(
    subs: list[QuerySubmission],
    out_dir: str | Path,
    *,
    validate: bool = True,
    expect_answers: int = ANSWERS_PER_QUERY,
    expected_n: dict[str, int] | None = None,
) -> tuple[list[Path], list[Issue]]:
    """Ghi MỖI TRUY VẤN MỘT FILE, UTF-8 không BOM.

    Vào: danh sách QuerySubmission + thư mục ra.
    Ra: (danh sách file đã ghi, list Issue của bước kiểm file).
    Bất biến: validate=True (mặc định) thì KHÔNG BAO GIỜ ghi dữ liệu sai ra đĩa —
    thà gãy to còn hơn sinh ra file trông hợp lệ mà sai.
    """
    if validate:
        issues = validate_all(subs, expect_answers=expect_answers, expected_n=expected_n)
        if issues:
            raise ValueError(
                "Dữ liệu không hợp lệ, KHÔNG ghi file.\n"
                + format_issues(issues)
                + "\n(Muốn ghi ra để soi thì gọi lại với validate=False.)"
            )

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    da_ghi: list[Path] = []
    loi_file: list[Issue] = []
    for s in subs:
        p = out_dir / suggest_filename(s.query_id)
        # encoding="utf-8" (KHÔNG utf-8-sig) + newline="" → không BOM, không \r\n
        p.write_text(to_submission(s), encoding="utf-8", newline="")
        da_ghi.append(p)
        loi_file += validate_file(p)
    return da_ghi, loi_file


# ------------------------------------------------------------------------- demo

def _demo_subs(n_answers: int = ANSWERS_PER_QUERY) -> list[QuerySubmission]:
    """Sinh bài nộp giả HỢP LỆ từ video có thật, đủ ba dạng bài.

    Dùng video_id và n_frames thật để dòng sinh ra qua được luật video/biên frame —
    demo bằng video bịa thì không chứng minh được gì.
    """
    vids = [v for v in all_video_ids() if n_frames_of(v) > 1000][:3]
    subs: list[QuerySubmission] = []

    for task, vid in zip(("KIS", "QA", "TRAKE"), vids):
        n = n_frames_of(vid)
        buoc = max(1, (n - 20) // (n_answers + 1))
        answers = []
        for i in range(n_answers):
            base = (i + 1) * buoc
            frames = tuple(base + k * 3 for k in range(4)) if task == "TRAKE" else (base,)
            answers.append(Answer(
                video_id=vid,
                frame_ids=frames,
                answer_text="5" if task == "QA" else None,
            ))
        subs.append(QuerySubmission(f"{task.lower()}_001", task, tuple(answers)))
    return subs


def main() -> int:
    ap = argparse.ArgumentParser(description="Sinh file nộp mẫu và tự kiểm (D0.2).")
    ap.add_argument("--demo", action="store_true", help="chạy trên dữ liệu giả")
    ap.add_argument("--answers", type=int, default=ANSWERS_PER_QUERY)
    ap.add_argument("--out", default=None, help="thư mục ra")
    args = ap.parse_args()

    if not args.demo:
        ap.print_help()
        return 0

    subs = _demo_subs(args.answers)
    out_dir = Path(args.out) if args.out else REPO_ROOT / "submissions" / f"demo_{SUBMIT_FORMAT}"

    print("== Kiểm ngữ nghĩa ==")
    loi = validate_all(subs, expect_answers=args.answers)
    print(format_issues(loi))
    if loi:
        return 1

    files, loi_file = write_submissions(subs, out_dir, expect_answers=args.answers)
    print(f"\n== Đã ghi {len(files)} file vào {out_dir.relative_to(REPO_ROOT)} ==")
    for p in files:
        print(f"   {p.name}  ({p.stat().st_size} byte)")
    print("== Kiểm file ==")
    print(format_issues(loi_file))
    return 1 if loi_file else 0


if __name__ == "__main__":
    raise SystemExit(main())
