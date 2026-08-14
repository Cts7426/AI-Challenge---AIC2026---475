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
from dataclasses import asdict, dataclass, replace
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

    # Bốn trường cho Q&A và TRAKE. Mặc định None để dòng nhãn KIS cũ đọc lại vẫn hợp lệ.
    answer_text: str | None = None      # câu trả lời hệ sinh ra (Q&A)
    answer_correct: bool | None = None  # người chấm phán; None = chưa ai chấm
    moment_idx: int | None = None       # khoảnh khắc thứ mấy của TRAKE; None = KIS/Q&A

    # N THẬT của đề TRAKE, do người chấm KHAI. None = chưa khai.
    #
    # Vì sao không suy từ `max(moment_idx) + 1`: suy như vậy chỉ đúng khi bộ nhãn đã
    # đủ N khoảnh khắc. Chấm dở dang 3/4 khoảnh khắc thì mẫu số thành 3, và công thức
    # `(1/N)·Σ` cho ra 1.0 thay vì 0.75 — thước đo tự thổi phồng đúng lúc bộ nhãn còn
    # thiếu, im lặng. Khai N là một con số người chấm ĐỌC ĐƯỢC TỪ ĐỀ, không phải suy.
    n_moments_total: int | None = None

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
        if self.n_moments_total is not None:
            n = int(self.n_moments_total)
            if n < 2:
                raise ValueError(f"n_moments_total = {n} — TRAKE phải có ít nhất 2 khoảnh khắc")
            if self.moment_idx is not None and not (0 <= self.moment_idx < n):
                raise ValueError(
                    f"moment_idx = {self.moment_idx} nằm ngoài [0, {n}) — "
                    "khai N nhỏ hơn số khoảnh khắc đang chấm là mâu thuẫn"
                )
            object.__setattr__(self, "n_moments_total", n)
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


def _ts_key(label: Label) -> datetime:
    """`ts` thành mốc thời gian THẬT để so sánh.

    KHÔNG so `ts` bằng chuỗi. `ts` ghi bằng `.astimezone()` nên mang offset của máy
    người chấm: Windows ở VN ra `+07:00`, còn WSL/Docker/CI ra `+00:00`. So chuỗi thì
    `2026-08-14T04:30:00+00:00` (VN 11:30) bị coi là CŨ HƠN `2026-08-14T10:00:00+07:00`
    (VN 10:00) — chấm lại xong dòng mới bị bỏ, dòng cũ vẫn thắng, không dấu hiệu gì.

    Chuỗi hỏng hoặc rỗng → mốc nhỏ nhất, tức luôn thua dòng có `ts` đọc được.
    Chuỗi không có offset (sửa tay) → hiểu là giờ máy đang chạy, để so được với dòng
    có offset mà không ném TypeError giữa lúc đang chấm.
    """
    try:
        moc = datetime.fromisoformat(label.ts)
    except (TypeError, ValueError):
        return datetime.min.replace(tzinfo=timezone.utc)
    if moc.tzinfo is None:
        return moc.astimezone()
    return moc


def _merge(cu: Label, moi: Label) -> Label:
    """Gộp hai lượt chấm CÙNG khoá: dòng mới thắng, nhưng không xoá ô nó không nói tới.

    Q&A có hai cửa tử ĐỘC LẬP (frame và answer) nên UI có hai nhóm nút, mà cả hai lại
    ghi ra cùng một khoá `(query_id, video_id, frame_start, frame_end, moment_idx)`.
    Đè nguyên khối thì lượt chấm sau xoá mất lượt trước: bấm "✓ Đúng" sau khi đã phán
    answer sẽ thổi bay phán quyết answer, và ngược lại. Cả hai đều im lặng.

    Quy ước: `answer_text`/`answer_correct` bằng `None` nghĩa là lượt chấm này KHÔNG
    nói gì về câu trả lời, không phải "câu trả lời rỗng" — nên lấy lại giá trị cũ.
    """
    if moi.answer_text is not None or moi.answer_correct is not None:
        moi_du = moi
    else:
        moi_du = replace(moi, answer_text=cu.answer_text, answer_correct=cu.answer_correct)
    if moi_du.n_moments_total is None and cu.n_moments_total is not None:
        moi_du = replace(moi_du, n_moments_total=cu.n_moments_total)
    return moi_du


def load_labels(directory: Path | None = None) -> list[Label]:
    """Đọc gộp nhãn của MỌI người trong dev_set/, đã khử trùng.

    Cùng một `key` thì giữ dòng có `ts` mới nhất — chấm lại thì lần sau thắng — nhưng
    GỘP các ô mà dòng mới không nói tới (xem `_merge`). Hai người chấm lệch nhau ở cùng
    một khoảng thường là truy vấn mơ hồ, đáng xem lại; cột `labeler` giữ lại để truy ra.
    """
    directory = directory or DEV_SET_DIR
    if not directory.is_dir():
        return []

    latest: dict[tuple, Label] = {}
    for path in sorted(directory.glob("labels.*.jsonl")):
        for label in _read_file(path):
            old = latest.get(label.key)
            if old is None:
                latest[label.key] = label
            elif _ts_key(label) >= _ts_key(old):
                latest[label.key] = _merge(old, label)
            else:
                latest[label.key] = _merge(label, old)
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
        """N của một truy vấn TRAKE. None nếu không phải TRAKE.

        Là MẪU SỐ của công thức `(1/N)·Σ`. Hai nguồn, theo thứ tự ưu tiên:

        ① `n_moments_total` — người chấm ĐỌC TỪ ĐỀ rồi khai. Đúng kể cả khi bộ nhãn
           mới chấm được vài khoảnh khắc.
        ② `max(moment_idx) + 1` — suy từ nhãn đang có. **Chỉ đúng khi đã chấm đủ N.**
           Chấm dở 3/4 thì mẫu số ra 3, và điểm ra 1.0 thay vì 0.75. Đường lui này giữ
           lại để dòng nhãn cũ (chưa có ô khai N) vẫn chấm được, nhưng `n_is_declared()`
           báo ra để `eval.py` cảnh báo chứ không im lặng.

        Lấy từ ĐÁP ÁN chứ không lấy số frame mình nộp: nộp thiếu khoảnh khắc mà chia
        cho số mình nộp thì trúng 1/1 ra 1.0 thay vì 0.25 — nộp càng ít điểm càng cao.
        """
        cua_query = [n for n in self.labels if n.query_id == query_id]
        khai = [n.n_moments_total for n in cua_query if n.n_moments_total is not None]
        if khai:
            # Hai người khai lệch nhau → lấy số LỚN NHẤT. Mẫu số lớn cho điểm THẤP hơn,
            # mà thước đo sai lệch về phía thấp thì người đọc đi soi, còn sai lệch về
            # phía cao thì không ai soi.
            return max(khai)
        idx = [n.moment_idx for n in cua_query if n.moment_idx is not None]
        return max(idx) + 1 if idx else None

    def n_is_declared(self, query_id: str) -> bool:
        """N của truy vấn này là do người chấm KHAI, hay chỉ suy từ số nhãn đang có?

        `False` nghĩa là mẫu số đang bằng số khoảnh khắc ĐÃ CHẤM. Chấm thiếu thì điểm
        TRAKE cao hơn thật — `eval.py` phải đếm và báo, không được nuốt.
        """
        return any(n.query_id == query_id and n.n_moments_total is not None
                   for n in self.labels)

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
        return min(found, key=lambda n: (n.frame_end - n.frame_start, _ts_key(n))).label

    def query_ids(self) -> list[str]:
        """Danh sách query_id đã có nhãn, để eval biết chấm được câu nào."""
        return sorted({n.query_id for n in self.labels})

    def __len__(self) -> int:
        return len(self.labels)


def is_correct(query_id: str, video_id: str, frame_idx: int,
               directory: Path | None = None) -> bool:
    """Bản tiện tay cho chỗ chỉ hỏi vài lần. Hỏi nhiều thì dựng `LabelIndex` một lần."""
    return LabelIndex(directory=directory).is_correct(query_id, video_id, frame_idx)
