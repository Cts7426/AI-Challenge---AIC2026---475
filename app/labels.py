# app/labels.py — D2.1: đọc/ghi bộ nhãn dev set (đáp án tự làm của nhóm).
#
# BTC không phát đáp án để tập. UI debug là máy sản xuất nhãn; E4.2 (`eval.py`) và
# D3.5 (mô phỏng chấm điểm) là hai nơi tiêu thụ.
#
# Ba quyết định định hình cả file (lý do đầy đủ: reports/D21_TECHNICAL_REPORT.md §5):
#   · Nhãn là một KHOẢNG `[frame_start, frame_end]`, gồm cả hai đầu — BTC chấm theo
#     cửa sổ, và allocator (D3.1) phát ra frame không phải keyframe.
#   · Mỗi người một file — nhãn được commit lên git, 5 người cùng append một file
#     thì conflict liên tục.
#   · Append-only — chấm lại thì ghi dòng mới, đọc lấy dòng `ts` mới nhất.
#
# ===== Tờ đáp án phải ghi đủ thứ BTC kiểm =====
# File này là đáp án tự soạn. Nó chỉ chấm đúng nếu ghi lại được MỌI điều kiện BTC
# kiểm — mà ba dạng bài kiểm ba thứ khác nhau (docs/contest.md §Cách chấm):
#
#   KIS    1 điều kiện : frame ∈ [s, e]                → khoảng có sẵn là đủ
#   Q&A    3 điều kiện : + answer đúng ngữ nghĩa       → cần `answer_text`/`answer_dung`
#   TRAKE  N điều kiện : mỗi khoảnh khắc j một [sⱼ,eⱼ] → cần `moment_idx`
#
# Thiếu ô nào thì `eval.py` bỏ qua đúng điều kiện đó và **cho điểm cao hơn thật**,
# im lặng. Với Q&A đó là ca tệ nhất: đường nộp đang điền "CHUA_CO_ANSWER" nên điểm
# thật là 0 tuyệt đối, mà thước đo lại báo có điểm.
#
# TRAKE ghi N DÒNG cho một truy vấn, mỗi dòng một `moment_idx` (0,1,2…), thay vì
# nhét N khoảng vào một dòng — giữ nguyên được luật append-only và khoá gộp.

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from data.config.debug_ui import DEV_SET_DIR, LABELER, NHAN_HOP_LE


@dataclass(frozen=True)
class Label:
    """Một lượt chấm: khoảng frame nào của video nào, cho truy vấn nào, đúng hay sai.

    `frame_start`/`frame_end` là FRAME INDEX TRONG VIDEO (thứ BTC chấm), gồm cả hai
    đầu. KHÔNG phải số thứ tự keyframe — hai số đó lệch nhau trung vị 5.300 frame
    trên toàn bộ 177.321 keyframe, và nhầm chúng chính là bug W0.2.

    `kf_id` / `shot_id` chỉ để truy vết khi soi lại, không tham gia chấm điểm.
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

    # --- ba trường cho Q&A và TRAKE. Xem đầu file, mục "tờ đáp án phải ghi gì".
    # Mặc định None để dòng nhãn KIS cũ đọc lại vẫn hợp lệ.
    answer_text: str | None = None   # câu trả lời hệ sinh ra (Q&A)
    answer_dung: bool | None = None  # người chấm phán: đúng ngữ nghĩa? None = chưa chấm
    moment_idx: int | None = None    # khoảnh khắc thứ mấy của TRAKE; None = KIS/Q&A

    def __post_init__(self) -> None:
        """Chuẩn hoá và chặn dữ liệu sai NGAY LÚC DỰNG, không đợi lúc ghi ra đĩa.

        Một nhãn sai nằm im trong file là thứ tệ nhất trong cả luồng này: eval sẽ
        chấm bằng nó và ra con số trông hợp lý mà sai, không có dấu hiệu gì.
        """
        if self.label not in NHAN_HOP_LE:
            raise ValueError(f"label '{self.label}' lạ, phải là một trong {NHAN_HOP_LE}")
        if not self.query_id or not self.video_id:
            raise ValueError("query_id và video_id không được rỗng")
        try:
            s, e = int(self.frame_start), int(self.frame_end)
        except (TypeError, ValueError) as ex:
            raise TypeError(
                f"frame_start/frame_end phải là số nguyên, nhận "
                f"{self.frame_start!r}/{self.frame_end!r}"
            ) from ex
        if s < 0:
            raise ValueError(f"frame_start = {s} < 0 — frame index đếm từ 0")
        if e < s:
            raise ValueError(f"khoảng ngược: frame_start={s} > frame_end={e}")
        object.__setattr__(self, "frame_start", s)
        object.__setattr__(self, "frame_end", e)
        if not self.ts:
            object.__setattr__(self, "ts", datetime.now(timezone.utc).astimezone().isoformat())

    @property
    def khoa(self) -> tuple[str, str, int, int, int | None]:
        """Khoá gộp: chấm lại đúng khoảng này thì dòng mới thay dòng cũ.

        `moment_idx` nằm trong khoá vì hai khoảnh khắc TRAKE là hai đáp án độc lập —
        sửa khoảnh khắc 2 không được ghi đè khoảnh khắc 1.
        """
        return (self.query_id, self.video_id, self.frame_start, self.frame_end,
                self.moment_idx)

    def chua(self, frame_idx: int) -> bool:
        """frame_idx có nằm trong khoảng này không (gồm cả hai đầu)."""
        return self.frame_start <= frame_idx <= self.frame_end


# ------------------------------------------------------------------------ ghi

def _chuan_hoa(s: str | None) -> str | None:
    """Chuẩn hoá answer trước khi so: bỏ khoảng trắng thừa, viết thường.

    Không bỏ dấu: "màu xanh" và "mau xanh" là hai câu khác nhau, và BTC chấm ngữ
    nghĩa chứ không chấm chuỗi — mình không được tự nới rộng thay họ.
    """
    if s is None:
        return None
    can = " ".join(s.split()).lower()
    return can or None


def duong_dan_nhan(labeler: str = LABELER, thu_muc: Path | None = None) -> Path:
    """File nhãn của một người. Mỗi người một file → không bao giờ git conflict."""
    return (thu_muc or DEV_SET_DIR) / f"labels.{labeler}.jsonl"


def ghi_nhan(nhan: Label, thu_muc: Path | None = None) -> Path:
    """Nối MỘT dòng vào file nhãn của người chấm. Trả đường dẫn file đã ghi.

    Vào: một Label hợp lệ. Ra: Path.
    Bất biến: chỉ NỐI THÊM, không bao giờ sửa/xoá dòng đã có · UTF-8 không BOM ·
    xuống dòng LF · flush ngay từng dòng.

    flush từng dòng vì Streamlit hay chết giữa chừng (sửa code là nó nạp lại app).
    Ghi đệm thì nhãn vừa bấm bay mất mà người chấm tưởng đã lưu.
    """
    p = duong_dan_nhan(nhan.labeler, thu_muc)
    p.parent.mkdir(parents=True, exist_ok=True)
    dong = json.dumps(asdict(nhan), ensure_ascii=False)
    # newline="\n": Windows tự dịch \n → \r\n, mà file này sẽ được đọc bằng nhiều
    # công cụ khác nhau. Cùng lý do với validate_file() của D0.2.
    with open(p, "a", encoding="utf-8", newline="\n") as f:
        f.write(dong + "\n")
        f.flush()
    return p


# ------------------------------------------------------------------------ đọc

def _doc_mot_file(p: Path) -> list[Label]:
    """Đọc một file JSONL. Dòng hỏng thì BÁO rồi bỏ qua, không kéo sập cả file.

    Vì sao không raise: một dòng hỏng (máy tắt giữa lúc ghi) không đáng làm mất
    toàn bộ nhãn đã chấm. Nhưng cũng KHÔNG được im lặng — im lặng thì người ta
    tưởng đủ nhãn trong khi thiếu, rồi eval ra số thấp mà không hiểu vì sao.
    """
    ra: list[Label] = []
    for i, dong in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        dong = dong.strip()
        if not dong:
            continue
        try:
            ra.append(Label(**json.loads(dong)))
        except Exception as e:
            print(f"  [cảnh báo] {p.name}:{i} bỏ qua dòng hỏng — {type(e).__name__}: {e}")
    return ra


def load_labels(thu_muc: Path | None = None) -> list[Label]:
    """Đọc gộp nhãn của MỌI người trong dev_set/.

    Vào: thư mục (mặc định `DEV_SET_DIR`). Ra: list[Label] đã khử trùng.
    Bất biến: cùng một khoá `(query_id, video_id, frame_start, frame_end)` thì giữ
    dòng có `ts` MỚI NHẤT — chấm lại thì lần sau thắng lần trước.

    Hai người chấm cùng một khoảng mà lệch nhau → người chấm sau thắng. Chỗ lệch
    thường là truy vấn mơ hồ, đáng xem lại; cột `labeler` giữ lại để truy ra.
    """
    thu_muc = thu_muc or DEV_SET_DIR
    if not thu_muc.is_dir():
        return []

    moi_nhat: dict[tuple, Label] = {}
    for p in sorted(thu_muc.glob("labels.*.jsonl")):
        for nhan in _doc_mot_file(p):
            cu = moi_nhat.get(nhan.khoa)
            if cu is None or nhan.ts >= cu.ts:
                moi_nhat[nhan.khoa] = nhan
    return list(moi_nhat.values())


def labels_of(query_id: str, thu_muc: Path | None = None) -> list[Label]:
    """Nhãn của một truy vấn, đã khử trùng."""
    return [n for n in load_labels(thu_muc) if n.query_id == query_id]


# -------------------------------------------------------- tra cứu để CHẤM ĐIỂM

class BangNhan:
    """Chỉ mục tra nhanh: (query_id, video_id) → các khoảng đã chấm.

    Vì sao cần lớp này thay vì quét thẳng list mỗi lần: eval (E4.2) chấm 100 dòng ×
    hàng chục truy vấn, còn D3.5 chấm lại nhiều lần liên tiếp khi thử phân bổ khác.
    Quét lại danh sách mỗi lượt là hàng triệu phép so sánh vô ích.

    Dựng một lần rồi hỏi bao nhiêu lần cũng được. Nhãn đổi → dựng lại.
    """

    def __init__(self, nhan: list[Label] | None = None, thu_muc: Path | None = None):
        self.nhan = load_labels(thu_muc) if nhan is None else nhan
        self._theo_khoa: dict[tuple[str, str], list[Label]] = {}
        for n in self.nhan:
            self._theo_khoa.setdefault((n.query_id, n.video_id), []).append(n)

    def is_correct(self, query_id: str, video_id: str, frame_idx: int,
                   moment_idx: int | None = None) -> bool:
        """Frame này có nằm trong khoảng nào đã chấm ĐÚNG không?

        Vào: id truy vấn · video · frame index TRONG VIDEO · khoảnh khắc thứ mấy
        (TRAKE; None cho KIS/Q&A). Ra: True/False.
        Bất biến: chỉ nhãn `correct` mới cho True. `wrong` và `unsure` KHÔNG phủ định
        một khoảng `correct` chồng lên nó — `wrong` chỉ có nghĩa "đã soi, không phải",
        nó không chứng minh được là chỗ khác cũng sai.

        Khoá tra gồm `video_id`, nên **sai video tự động ra False** — đúng luật BTC
        "sai video → 0 điểm ngay", không cần nhánh `if` riêng ở chỗ gọi.

        Đây chính là hàm chấm điểm dùng chung cho E4.2 và D3.5. Viết một lần ở đây
        để hai chỗ đó không tự định nghĩa "thế nào là đúng" theo hai kiểu.
        """
        return any(
            n.label == "correct" and n.moment_idx == moment_idx and n.chua(frame_idx)
            for n in self._theo_khoa.get((query_id, video_id), ())
        )

    def answer_dung(self, query_id: str, answer_text: str | None) -> bool | None:
        """Câu trả lời này đã được chấm là đúng ngữ nghĩa chưa?

        Ra: True/False nếu có người chấm rồi · **None nếu CHƯA AI CHẤM**.
        Ba giá trị chứ không phải hai: gộp "chưa chấm" vào False thì điểm Q&A tụt
        xuống theo số câu chưa chấm, nhìn như hệ thống dở. `eval.py` phải đếm riêng
        và báo ra, không được nuốt.

        So khớp sau khi chuẩn hoá khoảng trắng + viết thường: người chấm phán trên
        một chuỗi cụ thể, gõ thừa dấu cách không được thành câu trả lời khác.
        """
        can = _chuan_hoa(answer_text)
        if can is None:
            return None
        for n in self.nhan:
            if (n.query_id == query_id and n.answer_dung is not None
                    and _chuan_hoa(n.answer_text) == can):
                return n.answer_dung
        return None

    def so_khoanh_khac(self, query_id: str) -> int | None:
        """N của một truy vấn TRAKE, suy từ nhãn. None nếu truy vấn này không phải TRAKE.

        Là MẪU SỐ của công thức TRAKE `(1/N)·Σ`. Lấy từ đáp án chứ không lấy từ số
        frame mình nộp: nộp thiếu khoảnh khắc thì vẫn phải chia cho N thật, nếu không
        nộp 1 frame trúng 1 sẽ ra 1.0 thay vì 0.25.
        """
        idx = [n.moment_idx for n in self.nhan
               if n.query_id == query_id and n.moment_idx is not None]
        return max(idx) + 1 if idx else None

    def nhan_cua_frame(self, query_id: str, video_id: str, frame_idx: int,
                       moment_idx: int | None = None) -> str | None:
        """Nhãn hiện tại của một frame, hoặc None nếu chưa ai chấm.

        UI dùng để tô nút Đúng/Sai theo trạng thái đã chấm — chấm rồi thì khỏi chấm lại.
        Khoảng HẸP NHẤT thắng: người ta khoanh hẹp lại chính là để nói rõ hơn.
        """
        ung_vien = [n for n in self._theo_khoa.get((query_id, video_id), ())
                    if n.moment_idx == moment_idx and n.chua(frame_idx)]
        if not ung_vien:
            return None
        return min(ung_vien, key=lambda n: (n.frame_end - n.frame_start, n.ts)).label

    def cac_query(self) -> list[str]:
        """Danh sách query_id đã có nhãn, để eval biết chấm được câu nào."""
        return sorted({n.query_id for n in self.nhan})

    def __len__(self) -> int:
        return len(self.nhan)


def is_correct(query_id: str, video_id: str, frame_idx: int, thu_muc: Path | None = None) -> bool:
    """Bản tiện tay cho chỗ chỉ hỏi vài lần. Hỏi nhiều thì dựng `BangNhan` một lần."""
    return BangNhan(thu_muc=thu_muc).is_correct(query_id, video_id, frame_idx)
