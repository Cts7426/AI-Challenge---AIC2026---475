# data/config/submit_format.py — W0.2 + D0.2: TẦNG ĐỊNH DẠNG của bài nộp
#
# TOÀN BỘ hiểu biết về "file nộp trông như thế nào" nằm trong file này.
# BTC công bố format thật → sửa file này, backend/export.py không thay đổi.
#
# ĐỊNH DẠNG MỘT CÂU TRẢ LỜI :
#     Textual KIS : <video_id>, <frame_id>
#     Q&A         : <video_id>, <frame_id>, <answer>
#     TRAKE       : <video_id>, <frame_id_1>, ..., <frame_id_N>
#
# Thứ hạng = THỨ TỰ dòng, mỗi truy vấn là 1 file riêng.
#
# ĐÃ CHỐT (tài liệu BTC "Thông tin vòng Sơ tuyển", mục 2.1):
#   · thứ tự ô đúng như trên, Q&A có thêm cột answer ở CUỐI
#   · answer chấp nhận tiếng Việt HOẶC tiếng Anh
#   · tối đa 100 câu trả lời mỗi truy vấn (mục 2)
#
# TODO: BTC — chưa công bố: CSV hay JSON · có header không · frame_id đếm từ 0 hay 1 ·
# quy ước đặt tên file · có gộp zip không. Ba format dưới là PHỎNG ĐOÁN (hậu tố _v0).
#
# TODO: BTC — ⚠️ `video_id` CÓ ĐUÔI `.mp4` KHÔNG? Tài liệu BTC viết ví dụ là
# `video_id = video_abc(.mp4)` — dấu ngoặc không nói rõ là tuỳ chọn hay bắt buộc.
# Tầng này đang ghi nguyên `video_id` như trong `shots.parquet`, tức KHÔNG đuôi
# (`L21_V001`). Nếu BTC đòi `L21_V001.mp4` thì SAI TOÀN BỘ bài nộp mà validator vẫn
# xanh — cùng hạng nguy hiểm với việc `frame_id` đếm từ 0 hay 1. Hỏi cùng lượt.

from __future__ import annotations

import csv
import io
import json
import operator
from collections.abc import Callable
from dataclasses import dataclass

# Format đang dùng. BTC chốt thì đổi ĐÚNG DÒNG NÀY, không chỗ nào khác.
#
# Cố ý KHÔNG cho chọn format bằng tham số: lúc thi chỉ có một định dạng đúng.
# Để nó thành tuỳ chọn là mở đường cho việc nộp nhầm format mà không ai biết.
SUBMIT_FORMAT = "csv_v0"

TASK_TYPES = ("KIS", "QA", "TRAKE")

# Số câu trả lời mỗi truy vấn. BTC cho TỐI ĐA 100 và nộp sai KHÔNG bị trừ điểm
# → luôn nộp đủ 100 (BUILD_TASKS D3.1: "KHÔNG BAO GIỜ trả < 100 dòng").
#
# Đặt ở đây vì đây là LUẬT CỦA BTC, không phải lựa chọn của tầng nào. Cả validator
# (backend/export) lẫn slot allocator (data/config/slot_budget) đều đọc từ đúng chỗ này —
# hai bản sao của cùng một con số là cách chắc chắn nhất để chúng lệch nhau về sau.
ANSWERS_PER_QUERY = 100


@dataclass(frozen=True)
class Answer:
    """Một câu trả lời cho một truy vấn. Thứ tự trong list là thứ hạng.

    - KIS   : frame_ids đúng 1 phần tử, answer_text = None
    - Q&A   : frame_ids đúng 1 phần tử, answer_text khác rỗng
    - TRAKE : frame_ids N phần tử tăng dần ngặt, answer_text = None

    `keyframe_id` chỉ để truy vết khi debug và để map lại nếu BTC đổi format.

    frozen=True → hashable → tầng ngữ nghĩa kiểm trùng lặp chỉ cần set().
    """

    video_id: str
    frame_ids: tuple[int, ...]
    answer_text: str | None = None
    keyframe_id: str | None = None

    def __post_init__(self) -> None:
        """Chuẩn hoá frame_ids về tuple[int].

        Vì sao cần: `BUILD_TASKS` viết kiểu là `list[int]`, mà list thì KHÔNG hashable
        → luật kiểm trùng lặp sẽ ném TypeError thay vì trả Issue. Và slot allocator
        (D3.1) tính frame từ parquet nên sẽ đưa xuống `numpy.int64`, không phải `int`
        thuần → validator sẽ báo nhầm "không phải số nguyên".

        Dùng `operator.index()` chứ KHÔNG dùng `int()`: nó chỉ nhận thứ chuyển sang
        số nguyên mà không mất mát. `numpy.int64(100)` được nhận, còn `100.7` bị từ
        chối chứ không âm thầm cắt thành 100 — tầng format vẫn không tự tính gì.
        """
        try:
            chuan = tuple(operator.index(f) for f in self.frame_ids)
        except TypeError as e:
            raise TypeError(
                f"frame_ids của video '{self.video_id}' phải là các số nguyên "
                f"(nhận: {self.frame_ids!r}). Tầng format không làm tròn hộ."
            ) from e
        object.__setattr__(self, "frame_ids", chuan)


# ------------------------------------------------------- ô dữ liệu của một dòng

def answer_to_cells(task_type: str, a: Answer) -> list:
    """Một Answer → danh sách ô, đúng thứ tự cột quy định.

    Input: task_type + Answer. Output: list các ô. Không serialize.
    Không tính toán, không tra bảng — chỉ sắp xếp lại thứ tự.
    """
    cells: list = [a.video_id, *a.frame_ids]
    if task_type == "QA":
        cells.append(a.answer_text)
    return cells


def _header_for(task_type: str, n_frames_per_row: int) -> list[str]:
    """Tên cột — chỉ dùng cho format có header. TODO: BTC xác nhận tên thật."""
    cols = ["video_id"]
    cols += ["frame_id"] if n_frames_per_row == 1 else [
        f"frame_id_{i}" for i in range(1, n_frames_per_row + 1)
    ]
    if task_type == "QA":
        cols.append("answer")
    return cols


# ---------------------------------------------------------------- kho định dạng

FORMATS: dict[str, Callable[[str, list[list], int], str]] = {}


def register(name: str) -> Callable:
    """Đăng ký một bộ ghi. Thêm format mới = thêm 1 hàm + 1 dòng decorator."""

    def deco(fn: Callable) -> Callable:
        FORMATS[name] = fn
        return fn

    return deco


def _csv_text(rows: list[list], header: list[str] | None) -> str:
    buf = io.StringIO()
    # lineterminator="\n": mặc định của csv là "\r\n" → trên Windows thành \r\r\n
    w = csv.writer(buf, lineterminator="\n")
    if header:
        w.writerow(header)
    w.writerows(rows)
    return buf.getvalue()


@register("csv_v0")
def _fmt_csv_v0(task_type: str, rows: list[list], n_frames_per_row: int) -> str:
    """CSV không header — sát nhất với mục 2.1 của BTC."""
    return _csv_text(rows, None)


@register("csv_header_v0")
def _fmt_csv_header_v0(task_type: str, rows: list[list], n_frames_per_row: int) -> str:
    """CSV có header, phòng khi BTC yêu cầu tên cột."""
    return _csv_text(rows, _header_for(task_type, n_frames_per_row))


@register("json_v0")
def _fmt_json_v0(task_type: str, rows: list[list], n_frames_per_row: int) -> str:
    """JSON — giữ frame_ids dạng list, dễ đọc lại khi debug."""
    out = []
    for r in rows:
        item: dict = {"video_id": r[0], "frame_ids": r[1 : 1 + n_frames_per_row]}
        if task_type == "QA":
            item["answer"] = r[-1]
        out.append(item)
    return json.dumps(out, ensure_ascii=False, indent=2) + "\n"


# -------------------------------------------------------------------- API chính

def build_submission(query_id: str, task_type: str, answers: list[Answer]) -> str:
    """Dựng NỘI DUNG file nộp cho MỘT truy vấn.

    Input:
      query_id  — chỉ để báo lỗi cho dễ truy; KHÔNG xuất hiện trong file.
      task_type — "KIS" | "QA" | "TRAKE"
      answers   — thứ tự CHÍNH LÀ thứ hạng, phần tử đầu = hạng 1
    Output: chuỗi nội dung file, theo SUBMIT_FORMAT.
    Bất biến: không tra bảng, không suy diễn — mọi frame_id phải do tầng trên đưa xuống.

    ⚠️ KHÔNG nhận `frame_map`, và sẽ không bao giờ nhận. Tra keyframe_id → frame_idx
    là việc của slot allocator (D3.1), nơi vốn đã mở frame_map để chọn frame trong shot.
    Cho tầng này tra bảng = trả lại đúng cái bug W0.2 vừa xoá.
    """
    if task_type not in TASK_TYPES:
        raise ValueError(f"[{query_id}] task_type '{task_type}' không hợp lệ, phải là {TASK_TYPES}")
    fmt = SUBMIT_FORMAT
    if fmt not in FORMATS:
        raise ValueError(
            f"SUBMIT_FORMAT='{fmt}' chưa đăng ký. Đang có: {sorted(FORMATS)}. "
            "Thêm bằng @register('ten') trong data/config/submit_format.py."
        )
    if not answers:
        raise ValueError(f"[{query_id}] không có câu trả lời nào để nộp")

    rows = [answer_to_cells(task_type, a) for a in answers]
    loi = validate_format(task_type, rows)
    if loi:
        raise ValueError(f"[{query_id}] sai định dạng: " + " · ".join(loi[:3]))

    return FORMATS[fmt](task_type, rows, len(answers[0].frame_ids))


# Ký tự không được có trong `query_id` vì nó đi thẳng vào TÊN FILE.
# `/` `\` thoát khỏi thư mục ra; `: * ? " < > |` là ký tự cấm của Windows — cả nhóm
# đang chạy Windows nên chúng làm `write_text()` ném OSError khó đọc.
_FORBIDDEN_CHARS = set('/\\:*?"<>|\0')


def suggest_filename(query_id: str) -> str:
    """Tên file nộp cho một truy vấn. Đuôi file suy từ SUBMIT_FORMAT.

    Bất biến: KẾT QUẢ LUÔN LÀ MỘT TÊN FILE, không bao giờ là đường dẫn.

    Vì sao phải gác: `write_submissions()` ghi ra `out_dir / suggest_filename(qid)`.
    Ghép chuỗi trần thì `query_id="../../evil"` cho `"../../evil.csv"` — file nộp
    rơi ra NGOÀI thư mục ra mà hàm vẫn báo thành công và trả về đường dẫn đó. Không
    phải chuyện bảo mật (chạy local), mà là bài nộp nằm ở chỗ không ai nhìn: lúc
    kiểm lại trước hạn sẽ thấy thư mục thiếu file mà không hiểu vì sao.

    Đường tới được: `backend/api/main.py` nhận `query_id` thẳng từ body request.

    Raise chứ không tự làm sạch: tầng format KHÔNG tự suy ra gì (luật W0.2). Đổi
    thầm tên file là mất luôn đường map ngược bài nộp về truy vấn.

    TODO: BTC — quy ước đặt tên chưa công bố. Tạm dùng "<query_id>.<đuôi>".
    """
    if not query_id or not query_id.strip():
        raise ValueError("query_id rỗng — không dựng được tên file nộp")
    # Kèm cả ký tự điều khiển (\n, \t, \b…): chúng làm hỏng tên file mà MẮT THƯỜNG
    # KHÔNG THẤY — một query_id dán từ chỗ khác rất dễ dính chúng ở đầu hoặc cuối.
    bad_chars = sorted(c for c in set(query_id) if c in _FORBIDDEN_CHARS or ord(c) < 32)
    if bad_chars:
        raise ValueError(
            f"query_id {query_id!r} chứa ký tự không dùng được trong tên file: "
            f"{bad_chars!r}. "
            "Tầng format không tự làm sạch — sửa query_id ở tầng gọi."
        )
    if query_id.strip(".") == "":
        # "." và ".." là thư mục, không phải tên file
        raise ValueError(f"query_id '{query_id}' là tên thư mục đặc biệt, không phải id")

    duoi = "json" if SUBMIT_FORMAT.startswith("json") else "csv"
    return f"{query_id}.{duoi}"


# ----------------------------------------------------- validator TẦNG ĐỊNH DẠNG
# Chỉ kiểm CẤU TRÚC: đúng số cột, đúng kiểu dữ liệu.
# Kiểm NGỮ NGHĨA (đủ 100 dòng, frame trong [0,n_frames), trùng lặp, TRAKE tăng dần)
# nằm ở backend/export.py — vì chỗ đó mới cần đọc video_info.parquet.

def validate_format(task_type: str, rows: list[list]) -> list[str]:
    """Kiểm cấu trúc các dòng trước khi serialize.

    Input: task_type + rows (list các ô). Output: list mô tả lỗi, rỗng = đúng cấu trúc.
    """
    loi: list[str] = []
    if not rows:
        return ["không có dòng nào"]

    so_frame = len(rows[0]) - (2 if task_type == "QA" else 1)
    if task_type in ("KIS", "QA") and so_frame != 1:
        loi.append(f"{task_type} phải đúng 1 frame mỗi dòng, đang có {so_frame}")
    if task_type == "TRAKE" and so_frame < 2:
        loi.append(f"TRAKE phải có ít nhất 2 frame mỗi dòng, đang có {so_frame}")

    so_cot = len(rows[0])
    for i, r in enumerate(rows):
        if len(r) != so_cot:
            loi.append(f"dòng {i + 1}: có {len(r)} ô, các dòng khác có {so_cot}")
            continue
        if not isinstance(r[0], str) or not r[0]:
            loi.append(f"dòng {i + 1}: video_id phải là chuỗi khác rỗng")
        het = so_cot - 1 if task_type == "QA" else so_cot
        for f in r[1:het]:
            if not isinstance(f, int) or isinstance(f, bool):
                loi.append(f"dòng {i + 1}: frame_id phải là số nguyên, đang là {type(f).__name__}")
                break
        if task_type == "QA" and not isinstance(r[-1], str):
            loi.append(f"dòng {i + 1}: Q&A phải có cột answer dạng chuỗi")
    return loi
