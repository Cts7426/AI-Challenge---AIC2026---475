# app/eval.py — E4.2: chấm một lô bài nộp bằng đúng công thức của BTC.
#
# Chạy:  python -m app.eval runs/lan_1.jsonl
#
# Vì sao cần: không có thước đo thì mọi thay đổi về sau là mò. Đổi trọng số fusion,
# đổi bảng ngân sách slot — tốt hơn hay tệ hơn? Tuần cuối sẽ tune bằng cảm giác.
#
# Hai thứ file này KHÔNG tự định nghĩa, vì định nghĩa hai lần là hai con số khác nhau:
#   · "thế nào là đúng"  → `BangNhan` của app/labels.py (D3.5 cũng gọi đúng hàm đó)
#   · công thức R@k/Final → data/config/scoring.py (chép nguyên văn tài liệu BTC)
#
# Ở đây chỉ có: ghép hai thứ trên theo từng dạng bài, rồi trình bày.

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from app.labels import BangNhan
from data.config.scoring import K_MOC, SO_CAU_TOI_DA, final_score, r_at_k

TASK_TYPES = ("KIS", "QA", "TRAKE")


# ------------------------------------------------------------------ dữ liệu vào

@dataclass(frozen=True)
class DongNop:
    """Một câu trả lời đã nộp. Thứ tự trong list CHÍNH LÀ thứ hạng."""

    video_id: str
    frame_ids: tuple[int, ...]
    answer_text: str | None = None


@dataclass(frozen=True)
class LoNop:
    """Toàn bộ bài nộp cho MỘT truy vấn."""

    query_id: str
    task_type: str
    answers: tuple[DongNop, ...]
    query_vi: str = ""


# ------------------------------------------------------------------- kết quả ra

@dataclass
class KetQuaCham:
    """Điểm của một truy vấn, kèm đủ thứ để soi vì sao nó thấp."""

    query_id: str
    task_type: str
    query_vi: str
    r_scores: list[float]
    final: float
    theo_k: dict[int, float]
    hang_dau_tien: int | None          # hạng câu đầu tiên có điểm > 0
    n_dong: int
    answer_chua_cham: int = 0          # Q&A: frame đúng nhưng chưa ai chấm answer

    @property
    def co_diem(self) -> bool:
        return self.final > 0


@dataclass
class BaoCao:
    ket_qua: list[KetQuaCham] = field(default_factory=list)
    bo_qua: list[str] = field(default_factory=list)   # query_id chưa có nhãn

    def theo_dang(self, task_type: str) -> list[KetQuaCham]:
        return [k for k in self.ket_qua if k.task_type == task_type]

    def trung_binh(self, ket_qua: list[KetQuaCham] | None = None) -> dict:
        """Final + 5 giá trị R@k, trung bình trên một nhóm truy vấn."""
        kq = self.ket_qua if ket_qua is None else ket_qua
        if not kq:
            return {"final": 0.0, "n": 0, **{k: 0.0 for k in K_MOC}}
        return {
            "final": sum(k.final for k in kq) / len(kq),
            "n": len(kq),
            **{k: sum(x.theo_k[k] for x in kq) / len(kq) for k in K_MOC},
        }


# ------------------------------------------------------- R-Score theo từng dạng

def r_score_kis(dong: DongNop, query_id: str, bn: BangNhan) -> float:
    """`I(đúng video ∧ frame ∈ [s,e])` — nhị phân.

    Chỉ xét frame ĐẦU TIÊN: KIS nộp đúng một frame mỗi dòng (export._check_shape đã
    chặn). Dòng có nhiều frame là dữ liệu hỏng, không phải cơ hội gỡ điểm.
    """
    if not dong.frame_ids:
        return 0.0
    return 1.0 if bn.is_correct(query_id, dong.video_id, dong.frame_ids[0]) else 0.0


def r_score_qa(dong: DongNop, query_id: str, bn: BangNhan) -> tuple[float, bool]:
    """`I(đúng video ∧ frame ∈ [s,e] ∧ answer đúng ngữ nghĩa)`.

    Ra: (điểm, answer_chưa_chấm). Cờ thứ hai để `eval.py` báo riêng số dòng "frame
    đúng mà answer chưa ai phán" — nếu nuốt nó thành 0 thì điểm Q&A tụt xuống theo
    số nhãn còn thiếu và nhìn như hệ thống dở.

    Hai cửa tử ĐỘC LẬP: frame sai = 0, answer sai = 0. Không có điểm an ủi.
    """
    if not dong.frame_ids or not bn.is_correct(query_id, dong.video_id, dong.frame_ids[0]):
        return 0.0, False
    phan = bn.answer_dung(query_id, dong.answer_text)
    if phan is None:
        return 0.0, True
    return (1.0 if phan else 0.0), False


def r_score_trake(dong: DongNop, query_id: str, bn: BangNhan) -> float:
    """`0` nếu sai video, ngược lại `(1/N)·Σⱼ I(idⱼ ∈ [sⱼ, eⱼ])` — điểm từng phần.

    Khớp THEO VỊ TRÍ: frame thứ j phải rơi vào khoảng của khoảnh khắc thứ j. Không
    phải khớp bất kỳ thứ tự nào — nộp đúng 4 frame nhưng đảo thứ tự vẫn là 0.

    Mẫu số lấy từ ĐÁP ÁN (`so_khoanh_khac`), không lấy `len(frame_ids)`: nộp thiếu
    khoảnh khắc mà chia cho số mình nộp thì trúng 1/1 sẽ ra 1.0 thay vì 0.25.

    Sai video ra 0 tự nhiên vì `is_correct` tra theo khoá có `video_id` — không cần
    nhánh `if` riêng, và cũng không quên được.
    """
    n = bn.so_khoanh_khac(query_id) or len(dong.frame_ids)
    if not n:
        return 0.0
    khop = sum(
        1 for j, f in enumerate(dong.frame_ids[:n])
        if bn.is_correct(query_id, dong.video_id, f, moment_idx=j)
    )
    return khop / n


# ------------------------------------------------------------------ chấm một lô

def cham_query(lo: LoNop, bn: BangNhan) -> KetQuaCham:
    """Chấm đủ 100 dòng của một truy vấn.

    Bất biến: CHỈ xét `SO_CAU_TOI_DA` dòng đầu — nộp dư thì phần dư không được tính,
    đúng như BTC ("gửi tối đa 100 câu trả lời").
    """
    dong = lo.answers[:SO_CAU_TOI_DA]
    r_scores: list[float] = []
    chua_cham = 0

    for d in dong:
        if lo.task_type == "QA":
            diem, co_thieu = r_score_qa(d, lo.query_id, bn)
            chua_cham += int(co_thieu)
        elif lo.task_type == "TRAKE":
            diem = r_score_trake(d, lo.query_id, bn)
        else:
            diem = r_score_kis(d, lo.query_id, bn)
        r_scores.append(diem)

    hang = next((i for i, v in enumerate(r_scores, 1) if v > 0), None)
    return KetQuaCham(
        query_id=lo.query_id,
        task_type=lo.task_type,
        query_vi=lo.query_vi,
        r_scores=r_scores,
        final=final_score(r_scores),
        theo_k={k: r_at_k(r_scores, k) for k in K_MOC},
        hang_dau_tien=hang,
        n_dong=len(dong),
        answer_chua_cham=chua_cham,
    )


def cham_lo(cac_lo: list[LoNop], bn: BangNhan | None = None) -> BaoCao:
    """Chấm nhiều truy vấn.

    Bất biến: truy vấn CHƯA CÓ NHÃN NÀO thì bỏ qua và ghi vào `bo_qua`, KHÔNG tính
    0 điểm. Tính 0 thì `Final` tụt theo số câu chưa chấm — con số trông như hệ thống
    dở, thật ra là bộ nhãn chưa xong. Đúng loại lỗi im lặng dự án đang phòng.
    """
    bn = bn or BangNhan()
    co_nhan = set(bn.cac_query())
    bc = BaoCao()
    for lo in cac_lo:
        if lo.query_id not in co_nhan:
            bc.bo_qua.append(lo.query_id)
            continue
        bc.ket_qua.append(cham_query(lo, bn))
    return bc


# --------------------------------------------------------------------- đọc file

def doc_runs(path: str | Path) -> list[LoNop]:
    """Đọc file kết quả chạy, JSONL — mỗi dòng là một truy vấn.

    Dạng một dòng:
        {"query_id": "q_ab12", "task_type": "KIS", "query_vi": "...",
         "answers": [{"video_id": "L21_V001", "frame_ids": [123], "answer_text": null}]}

    Chọn JSONL thay vì đọc thẳng file nộp: file nộp (CSV theo `submit_format`) đã bị
    tước `query_id` và `task_type` — đúng như thiết kế của tầng đó — nên không đủ để
    chấm. Đây là định dạng của khâu ĐO, không phải khâu nộp.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"không có file runs: {p}")

    ra: list[LoNop] = []
    for i, dong in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        dong = dong.strip()
        if not dong:
            continue
        try:
            d = json.loads(dong)
            ra.append(LoNop(
                query_id=d["query_id"],
                task_type=d["task_type"],
                query_vi=d.get("query_vi", ""),
                answers=tuple(
                    DongNop(
                        video_id=a["video_id"],
                        frame_ids=tuple(int(f) for f in a["frame_ids"]),
                        answer_text=a.get("answer_text"),
                    )
                    for a in d["answers"]
                ),
            ))
        except Exception as e:
            print(f"  [cảnh báo] {p.name}:{i} bỏ qua dòng hỏng — {type(e).__name__}: {e}")
    return ra


def tu_submissions(subs) -> list[LoNop]:
    """`QuerySubmission` của D0.2 → `LoNop`. Cho chỗ đã có sẵn object trong RAM."""
    return [
        LoNop(
            query_id=s.query_id,
            task_type=s.task_type,
            answers=tuple(
                DongNop(a.video_id, tuple(a.frame_ids), a.answer_text) for a in s.answers
            ),
        )
        for s in subs
    ]


# ------------------------------------------------------------------- trình bày

def _hang_bang(ten: str, m: dict) -> str:
    return (f"  {ten:<22}{m['final']:>6.3f}   " +
            "  ".join(f"{m[k]:>5.3f}" for k in K_MOC))


def in_bao_cao(bc: BaoCao, so_cau_te: int = 10) -> str:
    """Ba mức: theo dạng bài · tổng chung · danh sách câu tệ nhất."""
    d: list[str] = []
    d.append(f"TỔNG ({len(bc.ket_qua)} truy vấn có nhãn)".ljust(24)
             + " Final   " + "  ".join(f"R@{k:<3}" for k in K_MOC))

    for t in TASK_TYPES:
        nhom = bc.theo_dang(t)
        if nhom:
            d.append(_hang_bang(f"{t} ({len(nhom)} câu)", bc.trung_binh(nhom)))
    d.append("  " + "─" * 58)
    d.append(_hang_bang("CHUNG", bc.trung_binh()))

    thieu = sum(k.answer_chua_cham for k in bc.ket_qua)
    if thieu:
        d.append(f"\n⚠️  {thieu} dòng Q&A có frame ĐÚNG nhưng answer CHƯA AI CHẤM "
                 f"→ đang tính 0. Điểm Q&A thật có thể cao hơn.")
    if bc.bo_qua:
        d.append(f"⚠️  {len(bc.bo_qua)} truy vấn chưa có nhãn nào → BỎ QUA, không tính 0: "
                 + ", ".join(bc.bo_qua[:5]) + ("…" if len(bc.bo_qua) > 5 else ""))

    te = sorted(bc.ket_qua, key=lambda k: k.final)[:so_cau_te]
    if te:
        d.append(f"\n{len(te)} CÂU TỆ NHẤT")
        for k in te:
            ly_do = (f"đúng đầu tiên ở hạng {k.hang_dau_tien}" if k.hang_dau_tien
                     else f"không có dòng đúng nào trong {k.n_dong}")
            mo_ta = f'"{k.query_vi[:34]}"' if k.query_vi else k.task_type
            d.append(f"  {k.query_id:<14}{k.final:>5.2f}  {mo_ta:<38} — {ly_do}")
    return "\n".join(d)


def main() -> int:
    """CLI: `python -m app.eval runs/lan_1.jsonl`"""
    import argparse

    ap = argparse.ArgumentParser(description="Chấm điểm bài nộp theo công thức BTC (E4.2).")
    ap.add_argument("runs", help="file JSONL kết quả chạy")
    ap.add_argument("--labels-dir", type=Path, default=None,
                    help="thư mục nhãn (mặc định dev_set/)")
    ap.add_argument("--worst", type=int, default=10, help="số câu tệ nhất cần liệt kê")
    args = ap.parse_args()

    bn = BangNhan(thu_muc=args.labels_dir)
    if not len(bn):
        print("Chưa có nhãn nào trong dev_set/ — chấm nhãn bằng UI debug trước "
              "(streamlit run app/debug_ui.py).")
        return 1

    bc = cham_lo(doc_runs(args.runs), bn)
    if not bc.ket_qua:
        print("Không truy vấn nào trong file runs có nhãn để chấm.")
        return 1
    print(in_bao_cao(bc, args.worst))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
