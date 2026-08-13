# tests/test_eval.py — E4.2: thước đo phải đúng trước khi tin bất cứ con số nào.
#
# Lỗi trong `eval.py` nguy hơn lỗi trong search: search sai thì điểm thấp và mình đi
# sửa; THƯỚC ĐO sai thì mình sửa nhầm chỗ suốt hai tuần. Nên phần lớn test dưới đây
# chạy lại ĐÚNG những ví dụ có số trong tài liệu BTC ("Thông tin vòng Sơ tuyển
# AIC2026", mục 2) — nguồn ngoài, không phải tự mình nghĩ ra rồi tự khớp.

from __future__ import annotations

import json

import pytest

from app.eval import (
    SubmittedRow,
    QueryRun,
    score_runs,
    score_query,
    read_runs,
    format_report,
    r_score_trake,
)
from app.labels import LabelIndex, Label
from data.config.scoring import final_score, r_at_k


def _nhan(**kw) -> Label:
    goc = dict(query_id="q1", query_vi="thử", task_type="KIS", video_id="L01_V001",
               frame_start=500, frame_end=510, label="correct", labeler="test")
    return Label(**{**goc, **kw})


def _lo(task="KIS", dong=(), qid="q1") -> QueryRun:
    return QueryRun(query_id=qid, task_type=task, answers=tuple(dong))


def _kis(video="L01_V001", frame=505) -> SubmittedRow:
    return SubmittedRow(video_id=video, frame_ids=(frame,))


# ================================================= công thức thuần (scoring.py)

def test_vi_du_CO_SO_cua_BTC_ra_dung_074():
    """Ví dụ mục 2.2: câu 1 = 0.5 · câu 3 = 0.8 · câu 15 = 0.6 → Final = 0.74.

    Đây là ca duy nhất trong tài liệu có sẵn cả đầu vào lẫn đáp số, nên nó là mỏ neo
    của toàn bộ file này. Sai ca này thì mọi con số khác đều vô nghĩa.
    """
    r = [0.0] * 100
    r[0], r[2], r[14] = 0.5, 0.8, 0.6
    assert r_at_k(r, 1) == 0.5
    assert all(r_at_k(r, k) == 0.8 for k in (5, 20, 50, 100))
    assert final_score(r) == pytest.approx(0.74)


@pytest.mark.parametrize("hang, mong_doi", [
    (1, 1.00), (2, 0.80), (5, 0.80), (6, 0.60), (20, 0.60),
    (21, 0.40), (50, 0.40), (51, 0.20), (100, 0.20),
])
def test_bang_rut_gon_la_HE_QUA_cua_cong_thuc(hang, mong_doi):
    """Bảng "hạng 1 → 1.00, 2–5 → 0.80…" phải TỰ RA từ công thức, không hard-code.

    Bảng đó có trong tài liệu rút gọn và rất dễ bị chép thẳng vào code. Chép thì
    TRAKE sai ngay, vì TRAKE có điểm lẻ mà bảng chỉ có 6 ô.
    """
    r = [0.0] * 100
    r[hang - 1] = 1.0
    assert final_score(r) == pytest.approx(mong_doi)


def test_khong_co_dong_dung_nao_thi_0():
    assert final_score([0.0] * 100) == 0.0


def test_dung_o_hang_101_tro_di_KHONG_duoc_tinh():
    """BTC chỉ chấm 100 câu đầu. Dòng 101 có đúng cũng vô nghĩa."""
    r = [0.0] * 100 + [1.0]
    assert final_score(r) == 0.0


def test_nop_it_hon_100_dong_van_cham_duoc():
    """Nộp 3 dòng, đúng ở hạng 2 → R@5..R@100 đều lấy được 1.0, không bị coi là thiếu."""
    assert final_score([0.0, 1.0, 0.0]) == pytest.approx(0.80)


# =========================================================== KIS — nhị phân

def test_kis_dung_frame_trong_khoang():
    bn = LabelIndex([_nhan()])
    kq = score_query(_lo("KIS", [_kis(frame=505)]), bn)
    assert kq.r_scores[0] == 1.0


def test_kis_frame_ngoai_khoang_thi_0():
    """Ví dụ BTC: đáp án [500,510], nộp 600 → R-Score = 0."""
    bn = LabelIndex([_nhan()])
    assert score_query(_lo("KIS", [_kis(frame=600)]), bn).r_scores[0] == 0.0


def test_kis_SAI_VIDEO_thi_0_du_frame_dung():
    """Ví dụ BTC: nộp L02_V003, 505 → sai video → 0."""
    bn = LabelIndex([_nhan()])
    assert score_query(_lo("KIS", [_kis(video="L02_V003", frame=505)]), bn).r_scores[0] == 0.0


def test_kis_hang_dau_tien_va_final_khop_nhau():
    bn = LabelIndex([_nhan()])
    dong = [_kis(frame=600), _kis(frame=600), _kis(frame=505)]
    kq = score_query(_lo("KIS", dong), bn)
    assert kq.first_hit_rank == 3
    assert kq.final == pytest.approx(0.80)


# =========================================================== Q&A — hai cửa tử

def test_qa_dung_ca_frame_LAN_answer():
    bn = LabelIndex([_nhan(task_type="QA", answer_text="màu xanh", answer_correct=True)])
    lo = _lo("QA", [SubmittedRow("L01_V001", (505,), "màu xanh")])
    assert score_query(lo, bn).r_scores[0] == 1.0


def test_qa_frame_dung_ma_ANSWER_SAI_thi_0():
    """Ví dụ BTC: L05_V005, 888, "màu trắng" → sai answer → 0.

    Đây là ca mà bộ nhãn CŨ (không có trường answer) chấm nhầm thành 1.0.
    """
    bn = LabelIndex([
        _nhan(task_type="QA"),
        _nhan(task_type="QA", answer_text="màu trắng", answer_correct=False, label="wrong"),
    ])
    lo = _lo("QA", [SubmittedRow("L01_V001", (505,), "màu trắng")])
    assert score_query(lo, bn).r_scores[0] == 0.0


def test_qa_answer_CHUA_AI_CHAM_thi_bao_ra_chu_khong_nuot():
    """Chưa chấm ≠ sai. Tính 0 thì được, nhưng phải ĐẾM và BÁO.

    Nuốt im thì điểm Q&A tụt theo số nhãn còn thiếu, nhìn như hệ thống dở — người
    đọc sẽ đi sửa search trong khi thứ thiếu là nhãn.
    """
    bn = LabelIndex([_nhan(task_type="QA")])
    lo = _lo("QA", [SubmittedRow("L01_V001", (505,), "chưa ai phán câu này")])
    kq = score_query(lo, bn)
    assert kq.r_scores[0] == 0.0
    assert kq.answer_unjudged == 1


def test_qa_frame_sai_thi_khong_tinh_la_answer_chua_cham():
    """Frame đã sai thì answer không còn ý nghĩa — đừng báo nhầm là thiếu nhãn."""
    bn = LabelIndex([_nhan(task_type="QA")])
    lo = _lo("QA", [SubmittedRow("L01_V001", (999,), "gì đó")])
    assert score_query(lo, bn).answer_unjudged == 0


def test_qa_so_khop_answer_bo_qua_khoang_trang_va_hoa_thuong():
    bn = LabelIndex([_nhan(task_type="QA", answer_text="Màu Xanh", answer_correct=True)])
    lo = _lo("QA", [SubmittedRow("L01_V001", (505,), "  màu   xanh ")])
    assert score_query(lo, bn).r_scores[0] == 1.0


# ========================================================= TRAKE — điểm từng phần

@pytest.fixture
def bn_trake() -> LabelIndex:
    """Đáp án ví dụ của BTC: 4 khoảnh khắc, mỗi cái một khoảng riêng."""
    khoang = [(95, 105), (145, 155), (195, 205), (245, 255)]
    return LabelIndex([
        _nhan(query_id="t1", task_type="TRAKE", video_id="L10_V010",
              frame_start=s, frame_end=e, moment_idx=j)
        for j, (s, e) in enumerate(khoang)
    ])


def test_trake_vi_du_BTC_ra_dung_075(bn_trake):
    """Nộp 101, 156, 203, 251 → khớp 3/4 → R-Score = 0.75.

    156 trượt khoảng [145,155] đúng 1 frame — chính là lý do khoảnh khắc TRAKE
    "thường dưới 10 frame" bắt buộc phải trích frame dày.
    """
    dong = SubmittedRow("L10_V010", (101, 156, 203, 251))
    assert r_score_trake(dong, "t1", bn_trake) == pytest.approx(0.75)


def test_trake_khop_THEO_VI_TRI_khong_phai_bat_ky_thu_tu_nao(bn_trake):
    """Đảo thứ tự 4 frame đúng → 0 điểm. Frame thứ j phải vào khoảng thứ j.

    Nếu chấm kiểu "có mặt trong tập khoảng nào cũng được" thì ca này ra 1.0 — sai
    hoàn toàn, và là cách viết tự nhiên nhất nếu không đọc kỹ công thức.
    """
    dong = SubmittedRow("L10_V010", (251, 203, 156, 101))
    assert r_score_trake(dong, "t1", bn_trake) == 0.0


def test_trake_SAI_VIDEO_thi_0_du_moi_frame_deu_khop(bn_trake):
    """Điều kiện tiên quyết của BTC: sai video → 0 ngay lập tức."""
    dong = SubmittedRow("L99_V999", (101, 150, 203, 251))
    assert r_score_trake(dong, "t1", bn_trake) == 0.0


def test_trake_nop_THIEU_khoanh_khac_van_chia_cho_N_that(bn_trake):
    """Nộp 1 frame trúng 1 → 1/4 = 0.25, KHÔNG phải 1/1 = 1.0.

    Mẫu số lấy từ đáp án, không lấy `len(frame_ids)`. Lấy nhầm thì nộp càng ít càng
    điểm cao — vô lý mà chạy vẫn ra số.
    """
    dong = SubmittedRow("L10_V010", (101,))
    assert r_score_trake(dong, "t1", bn_trake) == pytest.approx(0.25)


def test_trake_diem_le_KHONG_co_trong_bang_rut_gon(bn_trake):
    """Hạng 1 được 0.5, hạng 3 được 0.75 → Final = 0.70.

    Không ô nào của bảng rút gọn (1.00/0.80/0.60/0.40/0.20) ra được 0.70 — đây là
    bằng chứng chạy được rằng bảng đó không dùng cho TRAKE.
    """
    lo = _lo("TRAKE", [
        SubmittedRow("L10_V010", (101, 150, 250, 260)),   # khớp 2/4 = 0.5
        SubmittedRow("L99_V999", (0, 0, 0, 0)),
        SubmittedRow("L10_V010", (101, 156, 203, 251)),   # khớp 3/4 = 0.75
    ], qid="t1")
    kq = score_query(lo, bn_trake)
    assert kq.r_scores[0] == pytest.approx(0.5)
    assert kq.r_scores[2] == pytest.approx(0.75)
    assert kq.final == pytest.approx(0.70)


def test_trake_moment_idx_khong_de_dong_nay_de_len_dong_kia(bn_trake):
    """4 khoảnh khắc là 4 dòng nhãn độc lập — khoá gộp phải gồm `moment_idx`."""
    assert len(bn_trake) == 4
    assert bn_trake.n_moments("t1") == 4


# ================================================================ chấm cả lô

def test_query_CHUA_CO_NHAN_thi_bo_qua_chu_khong_tinh_0():
    """Tính 0 cho câu chưa chấm thì Final tụt theo số nhãn còn thiếu.

    Con số đó trông như hệ thống dở, thật ra là bộ nhãn chưa xong — người đọc sẽ đi
    sửa nhầm chỗ. Đúng loại lỗi im lặng cả dự án đang phòng.
    """
    bn = LabelIndex([_nhan(query_id="q1")])
    bc = score_runs([_lo("KIS", [_kis()], qid="q1"),
                  _lo("KIS", [_kis()], qid="q_chua_cham")], bn)
    assert [k.query_id for k in bc.scores] == ["q1"]
    assert bc.skipped == ["q_chua_cham"]
    assert bc.mean()["final"] == pytest.approx(1.0), "câu chưa chấm đã kéo điểm xuống"


def test_tach_theo_dang_bai():
    """Gộp ba dạng vào một số là giấu mất chỗ đang hỏng."""
    bn = LabelIndex([_nhan(query_id="k1"), _nhan(query_id="a1", task_type="QA")])
    bc = score_runs([_lo("KIS", [_kis()], qid="k1"), _lo("QA", [_kis()], qid="a1")], bn)
    assert len(bc.by_task("KIS")) == 1 and len(bc.by_task("QA")) == 1
    assert bc.mean(bc.by_task("KIS"))["final"] == pytest.approx(1.0)
    assert bc.mean(bc.by_task("QA"))["final"] == 0.0  # answer chưa chấm


def test_nop_du_hon_100_dong_thi_cat():
    bn = LabelIndex([_nhan()])
    lo = _lo("KIS", [_kis(frame=600)] * 100 + [_kis(frame=505)])
    kq = score_query(lo, bn)
    assert kq.n_rows == 100 and kq.final == 0.0


# ==================================================================== đọc file

def test_doc_runs_jsonl(tmp_path):
    p = tmp_path / "runs.jsonl"
    p.write_text(json.dumps({
        "query_id": "q1", "task_type": "KIS", "query_vi": "thử",
        "answers": [{"video_id": "L01_V001", "frame_ids": [505], "answer_text": None}],
    }, ensure_ascii=False) + "\n", encoding="utf-8")
    lo = read_runs(p)
    assert len(lo) == 1 and lo[0].answers[0].frame_ids == (505,)


def test_doc_runs_dong_hong_thi_bo_qua_chu_khong_sap(tmp_path):
    """Một dòng hỏng không đáng làm mất cả lô — nhưng phải in cảnh báo."""
    p = tmp_path / "runs.jsonl"
    p.write_text('{"hong": true}\n{"query_id":"q1","task_type":"KIS","answers":[]}\n',
                 encoding="utf-8")
    assert len(read_runs(p)) == 1


def test_thieu_file_runs_thi_bao_ro(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_runs(tmp_path / "khong_co.jsonl")


# =================================================================== trình bày

def test_bao_cao_neu_ro_so_answer_chua_cham():
    bn = LabelIndex([_nhan(task_type="QA")])
    bc = score_runs([_lo("QA", [SubmittedRow("L01_V001", (505,), "chưa phán")], qid="q1")], bn)
    assert "CHƯA AI CHẤM" in format_report(bc)


def test_bao_cao_liet_ke_cau_te_nhat_kem_ly_do():
    bn = LabelIndex([_nhan(query_id="q1")])
    bc = score_runs([_lo("KIS", [_kis(frame=600)], qid="q1")], bn)
    ra = format_report(bc)
    assert "TỆ NHẤT" in ra and "không có dòng đúng nào" in ra


def test_bao_cao_khong_sap_khi_khong_co_gi_de_cham():
    assert isinstance(format_report(score_runs([], LabelIndex([]))), str)
