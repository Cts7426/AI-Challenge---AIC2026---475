# tests/test_export.py — tầng định dạng + ghi file + đóng gói zip
#
# Trọng tâm:
#   1. File nộp đúng cột như tài liệu BTC
#   2. Thứ hạng = thứ tự dòng
#   3. Ghi ra UTF-8 không BOM — thứ dễ hỏng nhất trên Windows
#   4. File .zip có ĐÚNG lớp thư mục `submission/` mà BTC bắt buộc

from __future__ import annotations

import csv
import io
import zipfile

import pytest

from backend.export import (
    Issue,
    to_submission,
    validate_file,
    validate_zip,
    write_submission_zip,
    write_submissions,
)
from data.config.submit_format import (
    ANSWER_MAX_CHARS,
    Answer,
    build_submission,
    validate_format,
)
from tests.conftest import cat_bot, replace_answer, rules_of


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
    raw = to_submission(qa)
    dong = doc_csv(raw)
    assert len(dong[0]) == 3 and dong[0][2] == "5"
    assert raw.splitlines()[0].endswith(',"5"'), \
        "phòng vệ bảo thủ: answer đơn giản vẫn luôn được quote"


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


# --------------------------------------------------------------- định dạng CSV

def test_khong_co_dong_header(all_subs):
    """BTC: "CSV, no header row". Dòng đầu tiên phải LÀ dữ liệu, không phải tên cột."""
    for sub in all_subs:
        dong_dau = doc_csv(to_submission(sub))[0]
        assert dong_dau[0].startswith("L"), f"{sub.task_type}: dòng 1 trông như header"
        assert dong_dau[1].isdigit(), f"{sub.task_type}: ô 2 phải là frame_id"


def test_video_id_khong_co_duoi_mp4(all_subs):
    """BTC ghi video_id dạng `L00_V000` — có đuôi `.mp4` là sai toàn bộ bài nộp."""
    for sub in all_subs:
        for dong in doc_csv(to_submission(sub)):
            assert not dong[0].endswith(".mp4")


def test_ten_file_dung_ten_goi_cua_btc():
    """BTC phát `query-1-kis.txt` → mình nộp `query-1-kis.csv`. Dấu `-` phải qua được."""
    from data.config.submit_format import suggest_filename

    assert suggest_filename("query-1-kis") == "query-1-kis.csv"
    assert suggest_filename("query-4-trake") == "query-4-trake.csv"


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


def test_demo_lay_frame_tu_slot_allocator():
    """Demo phải đi qua `allocate()` thật, không tự tính frame bằng công thức.

    Đây là phép thử ĐẦU-CUỐI giữa D3.1 và D0.2: allocator đẻ ra thứ mà chính
    validator của mình từ chối thì lộ ngay ở đây. Bản cũ sinh frame bằng
    `(i+1)*bước` — đo lại thì 0/100 frame trùng keyframe thật.
    """
    from backend.export.exporter import _demo_subs, validate_all

    subs = _demo_subs()
    assert {s.task_type for s in subs} == {"KIS", "QA", "TRAKE"}
    assert all(len(s.answers) == 100 for s in subs)
    # Allocator xen kẽ theo shot → 5 dòng đầu KHÔNG được cùng một video/frame liền kề
    kis = next(s for s in subs if s.task_type == "KIS")
    assert len({(a.video_id, a.frame_ids) for a in kis.answers[:5]}) == 5
    assert validate_all(subs) == []


def test_validate_file_crlf_KHONG_con_la_loi(tmp_path):
    """BTC nhận "CRLF or LF" — báo lỗi cho CRLF là BÁO ĐỘNG GIẢ.

    Luật cũ (trước 16/08) bắt CRLF là `Issue`. Preflight D6.1 chạy ngay trước giờ
    nộp mà báo đỏ một file hoàn toàn hợp lệ thì người vận hành đi sửa thứ không
    hỏng, đúng lúc không còn thời gian.
    """
    p = tmp_path / "crlf.csv"
    p.write_bytes(b"L21_V001,100\r\nL21_V001,200\r\n")
    assert validate_file(p) == []


def test_validate_file_bat_cr_don_le(tmp_path):
    """`\\r` KHÔNG đi kèm `\\n` (Mac cổ) không nằm trong hai kiểu BTC nhận."""
    p = tmp_path / "cr.csv"
    p.write_bytes(b"L21_V001,100\rL21_V001,200\r")
    assert rules_of(validate_file(p)) == {"cr_don_le"}


def test_validate_file_lf_thi_im_lang(tmp_path):
    """Đối chứng: LF thuần phải sạch, không báo nhầm."""
    p = tmp_path / "lf.csv"
    p.write_bytes(b"L21_V001,100\nL21_V001,200\n")
    assert validate_file(p) == []


def test_bom_van_la_loi_du_da_bo_luat_crlf(tmp_path):
    """Nới CRLF không được nới nhầm BOM — BOM làm hỏng ô đầu tiên."""
    p = tmp_path / "bom.csv"
    p.write_bytes(b"\xef\xbb\xbfL21_V001,100\n")
    assert "bom" in rules_of(validate_file(p))


# --------------------------------------------------- luật answer <= 100 ký tự

def test_answer_qua_100_ky_tu_bi_bat(qa):
    """BTC: "Độ dài tối đa: 100 ký tự"."""
    from backend.export import validate_submission

    sub = replace_answer(qa, 0, answer_text="a" * 101)
    loi = validate_submission(sub)
    assert "answer_too_long" in rules_of(loi)
    assert loi[0].position == 1, "phải chỉ đúng hạng nào sai"


def test_answer_dung_100_ky_tu_van_hop_le(qa):
    """Biên trên là ĐƯỢC PHÉP — 100 ký tự đúng bằng giới hạn, không phải vượt."""
    from backend.export import validate_submission

    assert validate_submission(replace_answer(qa, 0, answer_text="a" * 100)) == []


def test_dem_ky_tu_khong_dem_byte(qa):
    """Tiếng Việt có dấu: 100 ký tự nhưng ~140 byte UTF-8. Đếm byte là báo nhầm."""
    from backend.export import validate_submission

    tieng_viet = "ố" * 100          # 100 ký tự, 200 byte
    assert len(tieng_viet.encode("utf-8")) > ANSWER_MAX_CHARS
    assert validate_submission(replace_answer(qa, 0, answer_text=tieng_viet)) == []


# ------------------------------- luật khoảng trắng đầu/cuối trong answer (19/08)
#
# BTC: "Khoảng trắng đầu/cuối: Được giữ nguyên, không tự động trim" — và cùng trang
# đó ghi answer được so "dưới dạng chuỗi chính xác". Một dấu cách thừa là mất trắng
# câu đó, mà nhìn file bằng mắt KHÔNG THẤY.

def test_answer_thua_khoang_trang_dau_cuoi_bi_bat(qa):
    from backend.export import validate_submission

    for xau in (" Năm người", "Năm người ", "\tNăm người", "Năm người\n"):
        loi = validate_submission(replace_answer(qa, 0, answer_text=xau))
        assert "answer_whitespace" in rules_of(loi), f"bỏ lọt {xau!r}"
        assert loi[0].position == 1, "phải chỉ đúng hạng nào sai"


def test_khoang_trang_GIUA_cau_van_hop_le(qa):
    """Chỉ bắt hai ĐẦU. "Năm người" có dấu cách ở giữa là chuyện bình thường."""
    from backend.export import validate_submission

    assert validate_submission(replace_answer(qa, 0, answer_text="Năm người")) == []


def test_answer_rong_van_bao_answer_empty_chu_khong_phai_whitespace(qa):
    """Answer toàn khoảng trắng đã có luật riêng (`answer_empty`) — đừng báo hai lần
    cùng một chuyện, người đọc sẽ đi sửa hai chỗ cho một lỗi."""
    from backend.export import validate_submission

    slugs = rules_of(validate_submission(replace_answer(qa, 0, answer_text="   ")))
    assert "answer_empty" in slugs


# ------------------------------------------------------------- đóng gói .zip

def test_zip_co_dung_lop_thu_muc_submission(all_subs, tmp_path):
    """Bất biến số một của bước nộp: BTC bắt buộc có thư mục `submission/` trong zip."""
    zip_path, loi = write_submission_zip(all_subs, tmp_path)
    assert loi == []
    with zipfile.ZipFile(zip_path) as z:
        ten = sorted(z.namelist())
    assert ten == [
        "submission/kis_001.csv",
        "submission/qa_001.csv",
        "submission/trake_001.csv",
    ]


def test_zip_doc_lai_ra_dung_noi_dung(kis, tmp_path):
    """Nội dung trong zip phải khớp nguyên văn thứ `to_submission()` sinh ra."""
    zip_path, _ = write_submission_zip([kis], tmp_path)
    with zipfile.ZipFile(zip_path) as z:
        trong_zip = z.read("submission/kis_001.csv").decode("utf-8")
    assert trong_zip == to_submission(kis)


def test_zip_de_lai_thu_muc_chua_nen_de_soi(all_subs, tmp_path):
    """Người vận hành phải mở CSV soi được mà không phải giải nén."""
    write_submission_zip(all_subs, tmp_path)
    assert (tmp_path / "submission" / "kis_001.csv").exists()


def test_validate_zip_bat_zip_thieu_thu_muc(all_subs, tmp_path):
    """Ca hỏng hay gặp nhất: nén bằng cách CHỌN FILE thay vì chọn thư mục.

    Zip mở ra vẫn thấy đủ 3 file, tên đúng, nội dung đúng — và BTC từ chối.
    """
    write_submission_zip(all_subs, tmp_path)
    sai = tmp_path / "nen_tay.zip"
    with zipfile.ZipFile(sai, "w") as z:
        for p in sorted((tmp_path / "submission").glob("*.csv")):
            z.write(p, arcname=p.name)   # KHÔNG có lớp "submission/"
    assert rules_of(validate_zip(sai)) == {"zip_no_submission_dir"}


def test_validate_zip_bat_file_hong(tmp_path):
    p = tmp_path / "hong.zip"
    p.write_bytes(b"day khong phai zip")
    assert rules_of(validate_zip(p)) == {"zip_corrupt"}


def test_validate_zip_bat_zip_rong(tmp_path):
    p = tmp_path / "rong.zip"
    with zipfile.ZipFile(p, "w"):
        pass
    assert rules_of(validate_zip(p)) == {"zip_empty"}


def test_validate_zip_bat_file_thieu(tmp_path):
    assert rules_of(validate_zip(tmp_path / "khong_co.zip")) == {"zip_missing"}


def test_zip_bao_file_csv_con_sot_tu_lan_truoc(all_subs, tmp_path):
    """Chỉ được nộp 3 lần/gói — một file cũ nằm lẫn là một lần nộp nhầm."""
    (tmp_path / "submission").mkdir()
    (tmp_path / "submission" / "query-cu.csv").write_text("L21_V001,1\n", encoding="utf-8")
    _, loi = write_submission_zip(all_subs, tmp_path)
    assert "stale_file" in rules_of(loi)


def test_zip_khong_duoc_tao_khi_du_lieu_sai(kis, tmp_path):
    """Cùng bất biến với `write_submissions`: không sinh bài nộp từ dữ liệu sai."""
    with pytest.raises(ValueError, match="KHÔNG ghi file"):
        write_submission_zip([cat_bot(kis, 50)], tmp_path)
    assert not list(tmp_path.glob("*.zip"))


def test_issue_giu_position_khi_khong_co_query_id():
    """Issue có `position` mà thiếu `query_id` vẫn phải in ra số thứ hạng.

    Bản cũ lồng position bên trong nhánh query_id → mất số 7 im lặng.
    """
    assert "7" in str(Issue("x", "lỗi gì đó", None, 7))
    # đối chứng: dạng đầy đủ không đổi cách in
    day_du = str(Issue("x", "lỗi", "q001", 7))
    assert "q001" in day_du and "7" in day_du


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
    answer = '5, anh ấy nói "có thể hơn"'
    sub = replace_answer(qa, 0, answer_text=answer)
    raw = to_submission(sub)
    dong = doc_csv(raw)
    assert dong[0][2] == answer and len(dong[0]) == 3
    assert '"5, anh ấy nói ""có thể hơn"""' in raw
