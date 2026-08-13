# app/labels.py — đọc/ghi bộ nhãn dev set (đáp án tự soạn của nhóm).
#
# BTC không phát đáp án để tập. UI debug là máy sản xuất nhãn; eval.py (E4.2) và
# score_simulator.py (D3.5) là hai nơi tiêu thụ.
#
# Ba quyết định định hình cả file:
#   · Nhãn là một KHOẢNG [frame_start, frame_end] gồm cả hai đầu — BTC chấm theo cửa
#     sổ, và slot allocator phát ra frame không phải keyframe.
#   · Mỗi người một file — nhãn được commit lên git, 5 người cùng append một file thì
#     conflict liên tục.
#   · Append-only — chấm lại thì ghi dòng mới, đọc lấy dòng `ts` mới nhất.
#
# Tờ đáp án phải ghi đủ MỌI điều kiện BTC kiểm, mà ba dạng bài kiểm ba thứ khác nhau:
#   KIS    1 điều kiện : frame ∈ [s, e]                → khoảng là đủ
#   Q&A    3 điều kiện : + answer đúng ngữ nghĩa       → cần answer_text/answer_correct
#   TRAKE  N điều kiện : mỗi khoảnh khắc j một [sⱼ,eⱼ] → cần moment_idx
# Thiếu ô nào thì eval.py bỏ qua đúng điều kiện đó và cho điểm CAO HƠN THẬT, im lặng.

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from data.config.debug_ui import DEV_SET_DIR, LABELER, VALID_LABELS


@dataclass(frozen=True)
class Label:
    """Một lượt chấm: khoảng frame nào của video nào, cho truy vấn nào, đúng hay sai.

    `frame_start`/`frame_end` là FRAME INDEX TRONG VIDEO (thứ BTC chấm), gồm cả hai
    đầu — không phải số thứ tự keyframe. Hai số đó lệch nhau trung vị 5.300 frame.

    `kf_id`/`shot_id` chỉ để truy vết khi soi lại, không tham gia chấm điểm.
    """

    query_id: str
    query_vi: str
    task_type: str
    video_id: str
    frame_start: int
    frame_end: int
    label: str
    labeler: str = LABELER
    ts: str = ""
    kf_id: str | None = None
    shot_id: str | None = None
    source: str = "debug_ui"
    note: str = ""

    # Ba trường cho Q&A và TRAKE. Mặc định None để dòng nhãn KIS cũ đọc lại vẫn hợp lệ.
    answer_text: str | None = None      # câu trả lời hệ sinh ra (Q&A)
    answer_correct: bool | None = None  # người chấm phán; None = chưa ai chấm
    moment_idx: int | None = None       # khoảnh khắc thứ mấy của TRAKE; None = KIS/Q&A

    def __post_init__(self) -> None:
        """Chặn dữ liệu sai ngay lúc dựng, không đợi lúc ghi ra đĩa.

        Một nhãn sai nằm im trong file là thứ tệ nhất của cả luồng: eval chấm bằng nó
        và ra con số trông hợp lý mà sai, không dấu hiệu gì.
        """
        if self.label not in VALID_LABELS:
            raise ValueError(f"label '{self.label}' lạ, phải là một trong {VALID_LABELS}")
        if not self.query_id or not self.video_id:
            raise ValueError("query_id và video_id không được rỗng")
        try:
            start, end = int(self.frame_start), int(self.frame_end)
        except (TypeError, ValueError) as ex:
            raise TypeError(
                f"frame_start/frame_end phải là số nguyên, nhận "
                f"{self.frame_start!r}/{self.frame_end!r}"
            ) from ex
        if start < 0:
            raise ValueError(f"frame_start = {start} < 0 — frame index đếm từ 0")
        if end < start:
            raise ValueError(f"khoảng ngược: frame_start={start} > frame_end={end}")
        object.__setattr__(self, "frame_start", start)
        object.__setattr__(self, "frame_end", end)
        if not self.ts:
            object.__setattr__(self, "ts", datetime.now(timezone.utc).astimezone().isoformat())

    @property
    def key(self) -> tuple[str, str, int, int, int | None]:
        """Khoá gộp: chấm lại đúng khoảng này thì dòng mới thay dòng cũ.

        `moment_idx` nằm trong khoá vì hai khoảnh khắc TRAKE là hai đáp án độc lập —
        sửa khoảnh khắc 2 không được ghi đè khoảnh khắc 1.
        """
        return (self.query_id, self.video_id, self.frame_start, self.frame_end,
                self.moment_idx)

    def contains(self, frame_idx: int) -> bool:
        """frame_idx có nằm trong khoảng này không (gồm cả hai đầu)."""
        return self.frame_start <= frame_idx <= self.frame_end


# ------------------------------------------------------------------------ ghi

def label_path(labeler: str = LABELER, directory: Path | None = None) -> Path:
    """File nhãn của một người. Mỗi người một file → không bao giờ git conflict."""
    return (directory or DEV_SET_DIR) / f"labels.{labeler}.jsonl"


def append_label(label: Label, directory: Path | None = None) -> Path:
    """Nối MỘT dòng vào file nhãn của người chấm. Trả đường dẫn file đã ghi.

    Bất biến: chỉ nối thêm, không sửa/xoá dòng đã có · UTF-8 không BOM · xuống dòng
    LF · flush ngay từng dòng.

    Flush từng dòng vì Streamlit hay nạp lại app giữa chừng — ghi đệm thì nhãn vừa
    bấm bay mất mà người chấm tưởng đã lưu.
    """
    path = label_path(label.labeler, directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(asdict(label), ensure_ascii=False)
    # newline="\n": Windows tự dịch \n → \r\n, mà file này đọc bằng nhiều công cụ.
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(line + "\n")
        f.flush()
    return path


# ------------------------------------------------------------------------ đọc

def _read_file(path: Path) -> list[Label]:
    """Đọc một file JSONL. Dòng hỏng thì BÁO rồi bỏ qua, không kéo sập cả file.

    Một dòng hỏng (máy tắt giữa lúc ghi) không đáng làm mất toàn bộ nhãn đã chấm.
    Nhưng cũng không được im lặng: im lặng thì người ta tưởng đủ nhãn trong khi thiếu,
    rồi eval ra số thấp mà không hiểu vì sao.
    """
    out: list[Label] = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(Label(**json.loads(line)))
        except Exception as e:
            print(f"  [cảnh báo] {path.name}:{i} bỏ qua dòng hỏng — {type(e).__name__}: {e}")
    return out


def load_labels(directory: Path | None = None) -> list[Label]:
    """Đọc gộp nhãn của MỌI người trong dev_set/, đã khử trùng.

    Cùng một `key` thì giữ dòng có `ts` mới nhất — chấm lại thì lần sau thắng. Hai
    người chấm lệch nhau ở cùng một khoảng thường là truy vấn mơ hồ, đáng xem lại;
    cột `labeler` giữ lại để truy ra.
    """
    directory = directory or DEV_SET_DIR
    if not directory.is_dir():
        return []

    latest: dict[tuple, Label] = {}
    for path in sorted(directory.glob("labels.*.jsonl")):
        for label in _read_file(path):
            old = latest.get(label.key)
            if old is None or label.ts >= old.ts:
                latest[label.key] = label
    return list(latest.values())


def labels_of(query_id: str, directory: Path | None = None) -> list[Label]:
    """Nhãn của một truy vấn, đã khử trùng."""
    return [n for n in load_labels(directory) if n.query_id == query_id]


# -------------------------------------------------------- tra cứu để CHẤM ĐIỂM

def _normalize(text: str | None) -> str | None:
    """Chuẩn hoá answer trước khi so: gộp khoảng trắng, viết thường.

    Không bỏ dấu: "màu xanh" và "mau xanh" là hai câu khác nhau. BTC chấm ngữ nghĩa
    chứ không chấm chuỗi — mình không được tự nới rộng thay họ.
    """
    if text is None:
        return None
    return " ".join(text.split()).lower() or None


class LabelIndex:
    """Chỉ mục tra nhanh: (query_id, video_id) → các khoảng đã chấm.

    eval (E4.2) chấm 100 dòng × hàng chục truy vấn, còn D3.5 chấm lại nhiều lần liên
    tiếp khi thử phân bổ khác. Quét lại list mỗi lượt là hàng triệu phép so sánh vô
    ích. Dựng một lần rồi hỏi bao nhiêu lần cũng được; nhãn đổi thì dựng lại.
    """

    def __init__(self, labels: list[Label] | None = None, directory: Path | None = None):
        self.labels = load_labels(directory) if labels is None else labels
        self._by_key: dict[tuple[str, str], list[Label]] = {}
        for n in self.labels:
            self._by_key.setdefault((n.query_id, n.video_id), []).append(n)

    def is_correct(self, query_id: str, video_id: str, frame_idx: int,
                   moment_idx: int | None = None) -> bool:
        """Frame này có nằm trong khoảng nào đã chấm ĐÚNG không?

        Chỉ nhãn `correct` mới cho True. `wrong`/`unsure` KHÔNG phủ định một khoảng
        `correct` chồng lên nó — `wrong` chỉ nghĩa là "đã soi, không phải", nó không
        chứng minh được chỗ khác cũng sai.

        Khoá tra gồm `video_id` nên **sai video tự động ra False** — đúng luật BTC
        "sai video → 0 điểm ngay", không cần nhánh if riêng ở chỗ gọi.

        Đây là hàm chấm điểm dùng chung cho E4.2 và D3.5. Viết một lần ở đây để hai
        chỗ đó không tự định nghĩa "thế nào là đúng" theo hai kiểu.
        """
        return any(
            n.label == "correct" and n.moment_idx == moment_idx and n.contains(frame_idx)
            for n in self._by_key.get((query_id, video_id), ())
        )

    def is_answer_correct(self, query_id: str, answer_text: str | None) -> bool | None:
        """Câu trả lời này đã được chấm là đúng ngữ nghĩa chưa?

        Ba giá trị: True/False nếu có người chấm · **None nếu chưa ai chấm**. Gộp
        "chưa chấm" vào False thì điểm Q&A tụt theo số nhãn còn thiếu, nhìn như hệ
        thống dở — eval.py phải đếm riêng và báo ra.
        """
        want = _normalize(answer_text)
        if want is None:
            return None
        for n in self.labels:
            if (n.query_id == query_id and n.answer_correct is not None
                    and _normalize(n.answer_text) == want):
                return n.answer_correct
        return None

    def n_moments(self, query_id: str) -> int | None:
        """N của một truy vấn TRAKE, suy từ nhãn. None nếu không phải TRAKE.

        Là MẪU SỐ của công thức `(1/N)·Σ`. Lấy từ đáp án chứ không lấy số frame mình
        nộp: nộp thiếu khoảnh khắc mà chia cho số mình nộp thì trúng 1/1 ra 1.0 thay
        vì 0.25 — nộp càng ít điểm càng cao.
        """
        idx = [n.moment_idx for n in self.labels
               if n.query_id == query_id and n.moment_idx is not None]
        return max(idx) + 1 if idx else None

    def label_of_frame(self, query_id: str, video_id: str, frame_idx: int,
                       moment_idx: int | None = None) -> str | None:
        """Nhãn hiện tại của một frame, hoặc None nếu chưa ai chấm.

        UI dùng để tô nút theo trạng thái đã chấm. Khoảng HẸP NHẤT thắng: người ta
        khoanh hẹp lại chính là để nói rõ hơn.
        """
        found = [n for n in self._by_key.get((query_id, video_id), ())
                 if n.moment_idx == moment_idx and n.contains(frame_idx)]
        if not found:
            return None
        return min(found, key=lambda n: (n.frame_end - n.frame_start, n.ts)).label

    def query_ids(self) -> list[str]:
        """Danh sách query_id đã có nhãn, để eval biết chấm được câu nào."""
        return sorted({n.query_id for n in self.labels})

    def __len__(self) -> int:
        return len(self.labels)


def is_correct(query_id: str, video_id: str, frame_idx: int,
               directory: Path | None = None) -> bool:
    """Bản tiện tay cho chỗ chỉ hỏi vài lần. Hỏi nhiều thì dựng `LabelIndex` một lần."""
    return LabelIndex(directory=directory).is_correct(query_id, video_id, frame_idx)
