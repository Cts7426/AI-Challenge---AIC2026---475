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
# ĐÃ CHỐT — nguồn: trang thi Codabench của BTC, hai trang "Hướng dẫn nộp bài sơ tuyển"
# và "Phương pháp đánh giá" (đọc 16/08):
#   · **CSV, KHÔNG header**, phân cách bằng dấu phẩy, UTF-8
#   · thứ tự ô đúng như trên, Q&A có thêm cột answer ở CUỐI
#   · answer: tiếng Việt HOẶC tiếng Anh, **tối đa 100 ký tự**
#   · tối đa 100 dòng mỗi truy vấn
#   · `video_id` ghi TRẦN, **không có đuôi `.mp4`** — BTC: "L00_V000"
#   · tên file = ĐÚNG tên gói truy vấn BTC phát, chỉ đổi đuôi `.txt` → `.csv`
#     (BTC phát `query-1-kis.txt` → mình nộp `query-1-kis.csv`)
#   · cả 3 file gói trong thư mục `submission/` rồi nén `.zip` — xem
#     `backend/export/exporter.py::write_submission_zip`
#
# Vì sao chỉ còn MỘT bộ ghi: trước 16/08 chưa biết BTC muốn CSV hay JSON, có header
# hay không, nên chỗ này có 3 format đăng ký qua `@register` để lật bằng một hằng.
# BTC đã chốt → hai format kia là đường chưa bao giờ dùng tới, và một nhánh code
# không ai chạy là một nhánh không ai kiểm. Xoá.
#
# TODO: BTC — `frame_id` đếm từ 0 hay 1 vẫn CHƯA chốt bằng văn bản. Trang chính thức
# chỉ ghi "Frame ID sẽ được so sánh dưới dạng số nguyên". Ghi chú buổi họp nói BTC
# đếm từ 1 nhưng châm chước lệch 1 frame. Tầng này đang ghi nguyên con số tầng trên
# đưa xuống (0-based, theo `data/config/frame_convention.md`) — CHƯA sửa, chờ chốt.

from __future__ import annotations

import csv
import io
import operator
from dataclasses import dataclass

TASK_TYPES = ("KIS", "QA", "TRAKE")

# Đuôi file nộp. BTC chốt CSV → hằng chứ không suy từ tên format nữa.
SUBMIT_EXT = "csv"

# Số câu trả lời mỗi truy vấn. BTC cho TỐI ĐA 100 và nộp sai KHÔNG bị trừ điểm
# → luôn nộp đủ 100 (BUILD_TASKS D3.1: "KHÔNG BAO GIỜ trả < 100 dòng").
#
# Đặt ở đây vì đây là LUẬT CỦA BTC, không phải lựa chọn của tầng nào. Cả validator
# (backend/export) lẫn slot allocator (data/config/slot_budget) đều đọc từ đúng chỗ này —
# hai bản sao của cùng một con số là cách chắc chắn nhất để chúng lệch nhau về sau.
ANSWERS_PER_QUERY = 100

# Độ dài tối đa của ô `answer` (Q&A). BTC: "Độ dài tối đa: 100 ký tự".
#
# ⚠️ KHÔNG phải `MAX_ANSWER_LEN = 500` của `backend/common/answer_match.py` — con số
# đó là chặn đầu vào cho `difflib` (chống chậm bậc hai), thuộc tầng so khớp. Đây là
# LUẬT BTC, đo trên chuỗi sẽ ghi ra file. Hai số, hai mục đích, đừng gộp.
ANSWER_MAX_CHARS = 100


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


def _csv_text(rows: list[list], task_type: str) -> str:
    """Các ô → nội dung CSV không header, đúng thứ BTC nhận.

    `lineterminator="\\n"`: mặc định của module `csv` là `\\r\\n`, mà `write_text()`
    còn dịch `\\n` → `\\r\\n` lần nữa trên Windows → ra `\\r\\r\\n`. BTC nhận cả CRLF
    lẫn LF nhưng KHÔNG nhận `\\r\\r\\n`.
    Q&A luôn quote riêng ô answer. BTC cho phép bỏ quote với answer đơn giản,
    nhưng bắt buộc quote khi có dấu phẩy/ngoặc kép/xuống dòng; luôn quote loại bỏ
    nhánh thao tác dễ nộp sai này. `csv.writer` không hỗ trợ quote theo một cột,
    nên phần prefix vẫn do writer chuẩn xử lý, còn answer escape `"` thành `""`.
    """
    if task_type == "QA":
        lines: list[str] = []
        for row in rows:
            prefix = io.StringIO()
            csv.writer(prefix, lineterminator="").writerow(row[:-1])
            answer = row[-1].replace('"', '""')
            lines.append(f'{prefix.getvalue()},"{answer}"\n')
        return "".join(lines)

    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerows(rows)
    return buf.getvalue()


# -------------------------------------------------------------------- API chính

def build_submission(query_id: str, task_type: str, answers: list[Answer]) -> str:
    """Dựng NỘI DUNG file nộp cho MỘT truy vấn.

    Input:
      query_id  — chỉ để báo lỗi cho dễ truy; KHÔNG xuất hiện trong file.
      task_type — "KIS" | "QA" | "TRAKE"
      answers   — thứ tự CHÍNH LÀ thứ hạng, phần tử đầu = hạng 1
    Output: chuỗi nội dung file CSV không header.
    Bất biến: không tra bảng, không suy diễn — mọi frame_id phải do tầng trên đưa xuống.

    ⚠️ KHÔNG nhận `frame_map`, và sẽ không bao giờ nhận. Tra keyframe_id → frame_idx
    là việc của slot allocator (D3.1), nơi vốn đã mở frame_map để chọn frame trong shot.
    Cho tầng này tra bảng = trả lại đúng cái bug W0.2 vừa xoá.
    """
    if task_type not in TASK_TYPES:
        raise ValueError(f"[{query_id}] task_type '{task_type}' không hợp lệ, phải là {TASK_TYPES}")
    if not answers:
        raise ValueError(f"[{query_id}] không có câu trả lời nào để nộp")

    rows = [answer_to_cells(task_type, a) for a in answers]
    loi = validate_format(task_type, rows)
    if loi:
        raise ValueError(f"[{query_id}] sai định dạng: " + " · ".join(loi[:3]))

    return _csv_text(rows, task_type)


# Ký tự không được có trong `query_id` vì nó đi thẳng vào TÊN FILE.
# `/` `\` thoát khỏi thư mục ra; `: * ? " < > |` là ký tự cấm của Windows — cả nhóm
# đang chạy Windows nên chúng làm `write_text()` ném OSError khó đọc.
_FORBIDDEN_CHARS = set('/\\:*?"<>|\0')


def suggest_filename(query_id: str) -> str:
    """Tên file nộp cho một truy vấn: `<query_id>.csv`.

    ⚠️ `query_id` PHẢI là tên gói BTC phát, gõ y nguyên. BTC phát
    `query-1-kis.txt` … `query-4-trake.txt` thì bài nộp phải là `query-1-kis.csv` …
    `query-4-trake.csv`. Tự đặt id kiểu `kis_001` là nộp sai tên file — BTC không
    ghép được đáp án với câu hỏi, và không có thông báo lỗi nào.
    Dấu `-` hợp lệ, không nằm trong `_FORBIDDEN_CHARS`.

    Bất biến: KẾT QUẢ LUÔN LÀ MỘT TÊN FILE, không bao giờ là đường dẫn.

    Vì sao phải gác: `write_submissions()` ghi ra `out_dir / suggest_filename(qid)`.
    Ghép chuỗi trần thì `query_id="../../evil"` cho `"../../evil.csv"` — file nộp
    rơi ra NGOÀI thư mục ra mà hàm vẫn báo thành công và trả về đường dẫn đó. Không
    phải chuyện bảo mật (chạy local), mà là bài nộp nằm ở chỗ không ai nhìn: lúc
    kiểm lại trước hạn sẽ thấy thư mục thiếu file mà không hiểu vì sao.

    Đường tới được: `backend/api/main.py` nhận `query_id` thẳng từ body request.

    Raise chứ không tự làm sạch: tầng format KHÔNG tự suy ra gì (luật W0.2). Đổi
    thầm tên file là mất luôn đường map ngược bài nộp về truy vấn.
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

    return f"{query_id}.{SUBMIT_EXT}"


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
