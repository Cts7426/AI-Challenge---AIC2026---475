# backend/export/exporter.py — D0.2: gom đáp án, kiểm ngữ nghĩa, ghi file nộp
#
# Chia vai với data/config/submit_format.py (BUILD_TASKS D0.2 yêu cầu tách hai tầng):
#   submit_format.py  → ĐỊNH DẠNG: file trông ra sao, tên cột, thứ tự ô
#   exporter.py (đây) → CƠ CHẾ  : gom theo truy vấn, kiểm ngữ nghĩa, ghi đĩa
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
    ANSWERS_PER_QUERY,
    SUBMIT_FORMAT,
    TASK_TYPES,
    Answer,
    build_submission,
    suggest_filename,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
VIDEO_INFO_PATH = REPO_ROOT / "data" / "derived" / "video_info.parquet"

# ANSWERS_PER_QUERY nhập từ submit_format — luật BTC, khai báo đúng MỘT chỗ.
# Re-export ở đây cho quen tay (đã dùng ở D0.2 trước khi gom về một mối).


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
        """Dựng từng mảnh vị trí độc lập nhau.

        Bản cũ lồng `position` bên trong nhánh `query_id is not None` → một Issue
        có `position` mà thiếu `query_id` sẽ in ra mất luôn số thứ hạng, im lặng.
        Chưa nổ vì mọi luật hiện tại đều đặt cả hai, nhưng đó là bẫy cho người
        thêm luật sau — và luật mới thì D6.1 sắp thêm.
        """
        phan = []
        if self.query_id is not None:
            phan.append(f"query={self.query_id}")
        if self.position is not None:
            phan.append(f"hạng {self.position}")
        vt = f" [{', '.join(phan)}]" if phan else ""
        return f"{self.rule}{vt}: {self.message}"


# ---------------------------------------------------- dữ liệu để kiểm ngữ nghĩa

# Tên cột chứa độ dài video trong video_info.parquet.
# 07/08: Data Factory đổi `n_frames` → `nb_frames_decoded`. Đặt thành hằng để lần đổi
# sau chỉ phải sửa một dòng, và để `_read_columns()` báo được tên cột nào đang thiếu.
COL_N_FRAMES = "nb_frames_decoded"


def _read_columns(path_: Path, required: list[str], owner: str):
    """Đọc parquet, ASSERT đủ cột cần trước khi nạp dữ liệu.

    Vào: đường dẫn · danh sách cột bắt buộc · tên người sở hữu file (để báo lỗi).
    Ra:  DataFrame chỉ gồm các cột đó.
    Bất biến: thiếu file hoặc thiếu cột thì **gãy to ngay lúc nạp**, kèm danh sách cột
    đang có, chứ không để pyarrow ném lỗi khó đọc ở tận trong ruột.

    Vì sao cần: 07/08 Data Factory đổi tên cột, cả bộ test đỏ với `ArrowInvalid` không
    nói được là thiếu cột gì. Mất công mới lần ra mình cần đọc cột nào.

    Đọc schema trước rồi mới đọc dữ liệu: `read_schema()` chỉ chạm phần đầu file nên
    gần như miễn phí, còn `read_parquet(columns=...)` bỏ qua hẳn các cột không cần.
    Đo trên shots.parquet (17 cột, cần 4): 11 ms → 6 ms.
    """
    import pandas as pd
    import pyarrow.parquet as pq

    if not path_.exists():
        raise FileNotFoundError(f"Không tìm thấy {path_} — cần {owner} giao file này trước.")
    available = list(pq.read_schema(path_).names)
    missing = [c for c in required if c not in available]
    if missing:
        raise KeyError(
            f"{path_.name} thiếu cột {missing}. Đang có: {available}. "
            f"Nhiều khả năng {owner} vừa đổi schema — sửa hằng tên cột trong file này."
        )
    return pd.read_parquet(path_, columns=required)


@lru_cache(maxsize=1)
def _video_frames() -> dict[str, int]:
    """video_id → số frame của video, đọc từ video_info.parquet của Data Factory.

    Nạp MỘT lần thành dict: validator tra hàng nghìn lượt, lọc DataFrame mỗi lần
    thì 100 query × 100 dòng đã mất hàng chục giây.
    """
    df = _read_columns(VIDEO_INFO_PATH, ["video_id", COL_N_FRAMES], "Công Lý (B0.1a)")
    return {str(v): int(n) for v, n in zip(df["video_id"], df[COL_N_FRAMES])}


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
        issues.append(Issue(
            "task_type", f"task_type '{sub.task_type}' lạ, phải là {TASK_TYPES}", q
        ))

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
    """Luật 4 — không hai dòng nào trùng nội dung hoàn toàn.

    Vào: một QuerySubmission. Ra: list Issue `duplicate_answer`, rỗng = sạch.
    Bất biến: `keyframe_id` KHÔNG nằm trong khóa so trùng — nó chỉ để debug, không
    được phép cứu một dòng đã trùng về nội dung nộp.

    Vì sao là lỗi: hai dòng giống nhau tiêu hai slot mà chỉ mua một cơ hội. Nộp sai
    không bị trừ điểm, nên mỗi slot lãng phí là một cơ hội bị vứt miễn phí.
    """
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
    """Luật 5 + 6 — hình dạng một dòng phải khớp dạng bài.

    Vào: QuerySubmission + `expected_n` (số khoảnh khắc đề TRAKE công bố, None = chưa biết).
    Ra: list Issue, rỗng = sạch. Sáu slug: `frame_count` · `trake_n_inconsistent` ·
    `trake_n_mismatch` · `trake_not_increasing` · `answer_empty` · `answer_unexpected`.
    Bất biến: KHÔNG sửa dữ liệu, chỉ báo. Ép về đúng hình dạng là việc của tầng trên.

    Vì sao TRAKE phải tăng dần NGẶT: hai khoảnh khắc khác nhau không thể ở cùng một
    frame. Vì sao Q&A bắt lỗi answer rỗng: hai cửa tử độc lập — frame đúng mà answer
    sai vẫn 0 điểm (tài liệu BTC — Q&A có hai cửa tử độc lập).
    """
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
                    "frame_count",
                    f"TRAKE phải có ít nhất 2 frame, đang có {len(a.frame_ids)}", q, i
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
    """Luật 2 + 3 — video có thật, và frame nằm trong độ dài video.

    Vào: QuerySubmission. Ra: list Issue `video_unknown` / `frame_out_of_range`.
    Bất biến: video lạ thì BÁO LỖI chứ không bỏ qua — bỏ qua là lặng lẽ cho trôi dòng
    sai, đúng loại lỗi im lặng mà cả dự án đang phòng. Biên trên là `n_frames - 1`.

    Đây là luật duy nhất cần dữ liệu ngoài (`video_info.parquet`) — cũng chính là lý do
    validator ngữ nghĩa nằm ở đây chứ không nằm cạnh tầng định dạng.
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
    """File nộp phải là UTF-8, KHÔNG BOM, KHÔNG CRLF.

    Vào: đường dẫn file đã ghi. Ra: list[Issue], rỗng = file sạch.
    Bốn slug: `file_missing` · `bom` · `not_utf8` · `crlf` · `file_empty`.

    Ghi bằng PowerShell (Out-File / Set-Content) trên Windows chèn 3 byte BOM
    \\xef\\xbb\\xbf. Mở bằng mắt không thấy, nhưng bộ chấm đọc cột đầu ra rác.

    Vì sao kiểm CRLF Ở ĐÂY chứ không chỉ tin test: `write_submissions()` ghi
    đúng (newline="") nên test đi qua — nhưng D6.1 chạy hàm này lên file CUỐI
    CÙNG trước khi nộp, mà file đó có thể do UI, script tay, hoặc một lần copy
    qua PowerShell ghi ra. Không có luật này thì CRLF lọt im lặng.
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

    # Đếm để báo được mức độ: 1 dòng lẻ dính CRLF khác hẳn cả file sai newline.
    n_crlf = raw.count(b"\r\n")
    n_cr = raw.count(b"\r")
    if n_crlf:
        out.append(Issue(
            "crlf",
            f"{path.name} có {n_crlf} dòng kết thúc bằng CRLF (\\r\\n) — phải ghi LF. "
            "Ghi bằng open(..., newline='') hoặc Path.write_text(..., newline='').",
        ))
    elif n_cr:
        # \r đơn lẻ: newline kiểu Mac cổ, hoặc file bị sửa bằng công cụ lạ
        out.append(Issue("crlf", f"{path.name} có {n_cr} ký tự \\r đơn lẻ — phải ghi LF"))

    if not raw.strip():
        out.append(Issue("file_empty", f"{path.name} rỗng"))
    return out


def format_issues(issues: list[Issue]) -> str:
    """Gom lỗi thành báo cáo đọc được, nhóm theo luật."""
    if not issues:
        return "HỢP LỆ — không phát hiện lỗi nào."
    by_rule: dict[str, list[Issue]] = defaultdict(list)
    for i in issues:
        by_rule[i.rule].append(i)
    lines = [f"KHÔNG HỢP LỆ — {len(issues)} lỗi thuộc {len(by_rule)} loại:"]
    for rule, group in sorted(by_rule.items()):
        lines.append(f"  [{rule}] {len(group)} lỗi")
        for i in group[:3]:
            lines.append(f"      - {i}")
        if len(group) > 3:
            lines.append(f"      ... và {len(group) - 3} lỗi nữa")
    return "\n".join(lines)


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

    ⚠️ Dựng ĐỦ tên file và nội dung TRƯỚC, ghi đĩa sau. Vòng lặp vừa dựng vừa ghi
    thì một truy vấn hỏng ở giữa để lại thư mục ghi DỞ DANG — vài file đã có, phần
    còn lại không, mà hàm thì ném exception nên không trả về danh sách nào cả.
    Người vận hành nhìn thư mục thấy có file, tưởng xong. Đo được: 4 truy vấn với
    `query_id="a/b"` ở vị trí 3 → 2 file nằm lại trên đĩa.

    Hai bước dựng đều raise được: `suggest_filename()` chặn query_id không thành
    tên file, `to_submission()` chặn sai cấu trúc dòng.
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

    # Dựng hết trước — hỏng thì gãy khi chưa chạm đĩa
    planned = [(out_dir / suggest_filename(s.query_id), to_submission(s)) for s in subs]

    trung = [p for p, _ in planned if [q for q, _ in planned].count(p) > 1]
    if trung:
        # query_id trùng đã bị `validate_all` bắt, nhưng chỉ khi validate=True —
        # gọi với validate=False thì file sau ghi đè file trước, mất bài nộp im lặng.
        raise ValueError(f"Hai truy vấn cùng ra một tên file: {sorted({p.name for p in trung})}")

    out_dir.mkdir(parents=True, exist_ok=True)
    da_ghi: list[Path] = []
    loi_file: list[Issue] = []
    for p, noi_dung in planned:
        # encoding="utf-8" (KHÔNG utf-8-sig) + newline="" → không BOM, không \r\n
        p.write_text(noi_dung, encoding="utf-8", newline="")
        da_ghi.append(p)
        loi_file += validate_file(p)
    return da_ghi, loi_file


# ------------------------------------------------------------------------- demo

def _demo_subs(n_answers: int = ANSWERS_PER_QUERY) -> list[QuerySubmission]:
    """Sinh bài nộp mẫu đủ ba dạng bài, frame do CHÍNH slot allocator (D3.1) cấp.

    Vào: số câu trả lời mỗi truy vấn. Ra: 3 QuerySubmission (KIS · QA · TRAKE).
    Bất biến: không tự tính frame nào — mọi con số đi qua `allocate()`.

    Vì sao đổi khỏi công thức cũ: bản trước sinh frame bằng `(i+1)*bước`, đo lại
    thì 0/100 frame trùng với keyframe thật của video. Không sai (demo chỉ để xem
    file trông ra sao), nhưng phí: gọi thẳng allocator thì demo vừa bớt một chỗ
    sinh dữ liệu giả, vừa thành phép thử ĐẦU-CUỐI thật giữa D3.1 và D0.2 —
    allocator đẻ ra thứ mà chính validator của mình từ chối thì lộ ngay tại đây.

    Import trong hàm: `backend.slot.allocator` import ngược lại module này
    (`REPO_ROOT`, `n_frames_of`), để ở đầu file là vòng import.
    """
    import pandas as pd

    from backend.slot import ShotHit, allocate
    from backend.slot.allocator import SHOTS_PATH

    # Vài shot của nhiều video khác nhau — giống kết quả search thật hơn là lấy
    # liền một mạch các shot đầu của cùng một video.
    df = pd.read_parquet(SHOTS_PATH, columns=["shot_id", "video_id"])
    df = df.groupby("video_id", sort=True).head(3).head(31)
    hits = [
        ShotHit(r.shot_id, 1.0 - i * 0.01)
        for i, r in enumerate(df.itertuples(index=False))
    ]

    return [
        QuerySubmission(
            f"{task.lower()}_001",
            task,
            tuple(allocate(
                hits, task,
                answer_text="5" if task == "QA" else None,
                total=n_answers,
            )),
        )
        for task in ("KIS", "QA", "TRAKE")
    ]


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
    issues_ = validate_all(subs, expect_answers=args.answers)
    print(format_issues(issues_))
    if issues_:
        return 1

    files, loi_file = write_submissions(subs, out_dir, expect_answers=args.answers)
    print(f"\n== Đã ghi {len(files)} file vào {out_dir.relative_to(REPO_ROOT)} ==")
    for p in files:
        print(f"   {p.name}  ({p.stat().st_size} byte)")
    print("== Kiểm file ==")
    print(format_issues(loi_file))
    return 1 if loi_file else 0


# Điểm vào CLI nằm ở backend/export/__main__.py — `python -m backend.export --demo`
