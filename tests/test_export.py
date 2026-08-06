# tests/test_export.py — tầng định dạng + ghi file
#
# Trọng tâm:
#   1. File nộp đúng cột như tài liệu BTC
#   2. Thứ hạng = thứ tự dòng
#   3. Ghi ra UTF-8 không BOM, không CRLF — hai thứ dễ hỏng nhất trên Windows
#   4. "Đổi format = sửa 1 dòng SUBMIT_FORMAT" là thật (không có tham số fmt)

from __future__ import annotations

import csv
import io
import json

import pytest

from backend.export import to_submission, validate_file, write_submissions
from data.config.submit_format import FORMATS, Answer, build_submission, validate_format
from tests.conftest import cat_bot, replace_answer


def doc_csv(noi_dung: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(noi_dung)))


# ----------------------------------------- định dạng đúng tài liệu

def test_kis_dung_2_cot(kis):
    """BTC mục 2.1.1: <video_id>, <frame_id>."""
    dong = doc_csv(to_submission(kis))
    assert len(dong) == 100
    assert len(dong[0]) == 2
    assert dong[0][0] == kis.answers[0].video_id


def test_qa_dung_3_cot(qa):
    """BTC mục 2.1.2: <video_id>, <frame_id>, <answer>."""
    dong = doc_csv(to_submission(qa))
    assert len(dong[0]) == 3 and dong[0][2] == "5"


def test_trake_dung_1_cong_N_cot(trake):
    """BTC mục 2.1.3: <video_id>, <frame_id_1>, ..., <frame_id_N>."""
    dong = doc_csv(to_submission(trake))
    assert len(dong[0]) == 5  # video_id + 4 frame
    frames = [int(x) for x in dong[0][1:]]
    assert frames == sorted(set(frames)), "frame TRAKE phải tăng dần ngặt"


def test_khong_co_cot_query_id_va_rank(kis):
    """Tài liệu BTC không có hai cột này — thừa cột là sai định dạng."""
    dong = doc_csv(to_submission(kis))
    assert "kis_001" not in dong[0], "query_id không được nằm trong file"
    assert dong[0][1].isdigit(), "cột thứ 2 phải là frame_id, không phải rank"


def test_thu_tu_dong_chinh_la_thu_hang(kis):
    """Thứ hạng = thứ tự list. Đảo list thì file phải đảo theo."""
    import dataclasses

    dao = dataclasses.replace(kis, answers=tuple(reversed(kis.answers)))
    goc = doc_csv(to_submission(kis))
    nguoc = doc_csv(to_submission(dao))
    assert nguoc[0] == goc[-1] and nguoc[-1] == goc[0]


# --------------------------------------------------------------- kho định dạng

def dat_format(monkeypatch, ten: str) -> None:
    """Đổi định dạng bài nộp — mô phỏng đúng thao tác lúc BTC công bố format.

    Không có tham số `fmt` nào để truyền: cách duy nhất đổi format là sửa hằng
    SUBMIT_FORMAT. Test này chứng minh đúng một dòng đó là đủ.
    """
    import data.config.submit_format as sf

    monkeypatch.setattr(sf, "SUBMIT_FORMAT", ten)


def test_moi_format_deu_xuat_duoc(all_subs, monkeypatch):
    """Sửa mỗi hằng SUBMIT_FORMAT là đủ — không format nào cần sửa gì thêm."""
    for fmt in FORMATS:
        dat_format(monkeypatch, fmt)
        for sub in all_subs:
            assert to_submission(sub).strip(), f"{fmt} xuất ra rỗng"


def test_format_la_bi_tu_choi(kis, monkeypatch):
    """Gõ sai tên format phải gãy to ngay, không âm thầm rơi về mặc định."""
    dat_format(monkeypatch, "format_khong_ton_tai")
    with pytest.raises(ValueError, match="chưa đăng ký"):
        to_submission(kis)


def test_build_submission_dung_3_tham_so():
    """BUILD_TASKS D0.2 chốt chữ ký: (query_id, task_type, answers). Không hơn.

    Đặc biệt KHÔNG có `frame_map`: tra keyframe_id → frame_idx là việc của slot
    allocator, cho tầng định dạng tra bảng là trả lại bug W0.2.
    """
    import inspect

    ten = list(inspect.signature(build_submission).parameters)
    assert ten == ["query_id", "task_type", "answers"], f"chữ ký đã lệch: {ten}"


def test_khong_co_cau_tra_loi_bi_tu_choi(kis):
    with pytest.raises(ValueError, match="không có câu trả lời"):
        to_submission(cat_bot(kis, 0))


def test_task_type_la_bi_tu_choi(kis):
    import dataclasses

    with pytest.raises(ValueError, match="task_type"):
        to_submission(dataclasses.replace(kis, task_type="AVS"))


def test_csv_co_header_thi_nhieu_hon_dung_1_dong(kis, monkeypatch):
    khong = to_submission(kis).splitlines()
    dat_format(monkeypatch, "csv_header_v0")
    co = to_submission(kis).splitlines()
    assert len(co) == len(khong) + 1
    assert co[0].startswith("video_id,frame_id")


def test_json_doc_lai_duoc(trake, monkeypatch):
    dat_format(monkeypatch, "json_v0")
    data = json.loads(to_submission(trake))
    assert len(data) == 100
    assert set(data[0]) == {"video_id", "frame_ids"}
    assert len(data[0]["frame_ids"]) == 4


# ------------------------------------- tầng định dạng KHÔNG được tự tính gì

def test_format_khong_tu_suy_frame_id_tu_keyframe_id():
    """Bug cũ: cắt hậu tố keyframe_id ra frame_id. Giờ phải ghi đúng frame_ids được đưa."""
    a = Answer(video_id="L21_V001", frame_ids=(2131,), keyframe_id="L21_V001#k0017")
    dong = doc_csv(build_submission("q1", "KIS", [a]))
    assert dong[0] == ["L21_V001", "2131"], "phải ghi frame_ids, không suy từ keyframe_id"


def test_keyframe_id_khong_lot_vao_file():
    """keyframe_id chỉ để debug — không được xuất hiện trong bài nộp."""
    a = Answer(video_id="L21_V001", frame_ids=(2131,), keyframe_id="L21_V001#k0017")
    assert "#k0017" not in build_submission("q1", "KIS", [a])


# ------------------------- chuẩn hoá frame_ids (kiểu dữ liệu tầng trên đưa xuống)

def test_nhan_frame_ids_dang_list():
    """BUILD_TASKS ghi kiểu là list[int] — phải nhận, và list không hashable
    nên bắt buộc chuyển sang tuple, không thì luật kiểm trùng lặp ném TypeError."""
    a = Answer(video_id="L21_V001", frame_ids=[100, 103])
    assert a.frame_ids == (100, 103) and isinstance(a.frame_ids, tuple)
    hash(a)  # phải hash được


def test_nhan_numpy_int():
    """Slot allocator (D3.1) tính frame từ parquet → numpy.int64, không phải int thuần."""
    np = pytest.importorskip("numpy")
    a = Answer(video_id="L21_V001", frame_ids=(np.int64(100),))
    assert a.frame_ids == (100,) and type(a.frame_ids[0]) is int
    dong = doc_csv(build_submission("q1", "KIS", [a]))
    assert dong[0] == ["L21_V001", "100"]


def test_tu_choi_float_khong_lam_tron_ho():
    """Tầng format không được tự tính — 100.7 phải gãy, không âm thầm cắt thành 100."""
    with pytest.raises(TypeError, match="số nguyên"):
        Answer(video_id="L21_V001", frame_ids=(100.7,))


# ------------------------------------------------ validator tầng định dạng

def test_format_bat_sai_so_cot():
    assert validate_format("KIS", [["L21_V001", 1], ["L21_V001", 2, 3]])


def test_format_bat_frame_khong_phai_so_nguyen():
    loi = validate_format("KIS", [["L21_V001", "100"]])
    assert any("số nguyên" in x for x in loi)


def test_format_bat_video_id_rong():
    loi = validate_format("KIS", [["", 100]])
    assert any("video_id" in x for x in loi)


def test_format_dung_thi_khong_keu():
    assert validate_format("KIS", [["L21_V001", 100], ["L21_V001", 200]]) == []


# --------------------------------------------------------------- ghi ra đĩa

def test_ghi_moi_query_mot_file(all_subs, tmp_path):
    files, loi = write_submissions(all_subs, tmp_path)
    assert len(files) == 3 and loi == []
    assert {p.name for p in files} == {"kis_001.csv", "qa_001.csv", "trake_001.csv"}


def test_file_khong_bom_khong_crlf(all_subs, tmp_path):
    files, _ = write_submissions(all_subs, tmp_path)
    for p in files:
        raw = p.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), f"{p.name} có BOM"
        assert b"\r\n" not in raw, f"{p.name} dùng CRLF"
        assert validate_file(p) == []


def test_ghi_tao_thu_muc_cha(kis, tmp_path):
    files, _ = write_submissions([kis], tmp_path / "chua" / "co")
    assert files[0].exists()


def test_khong_ghi_file_khi_du_lieu_sai(kis, tmp_path):
    """Bất biến quan trọng nhất: không bao giờ sinh file nộp từ dữ liệu sai."""
    with pytest.raises(ValueError, match="KHÔNG ghi file"):
        write_submissions([cat_bot(kis, 50)], tmp_path)
    assert not list(tmp_path.glob("*.csv"))


def test_tat_validate_thi_ghi_duoc_du_lieu_hong(kis, tmp_path):
    """Có đường thoát để soi dữ liệu hỏng, nhưng phải nói rõ ý định."""
    files, _ = write_submissions([cat_bot(kis, 50)], tmp_path, validate=False)
    assert files[0].exists()


def test_tieng_viet_khong_hong_khi_ghi_doc(qa, tmp_path):
    sub = replace_answer(qa, 0, answer_text="màu xanh dương")
    files, _ = write_submissions([sub], tmp_path)
    assert "màu xanh dương" in files[0].read_text(encoding="utf-8")


def test_answer_co_dau_phay_khong_lam_lech_cot(qa):
    """CSV phải escape dấu phẩy trong answer, không thì lệch toàn bộ cột."""
    sub = replace_answer(qa, 0, answer_text="5, có thể hơn")
    dong = doc_csv(to_submission(sub))
    assert dong[0][2] == "5, có thể hơn" and len(dong[0]) == 3
