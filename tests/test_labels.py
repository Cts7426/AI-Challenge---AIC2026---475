# tests/test_labels.py — D2.1: bộ nhãn dev set
#
# Trọng tâm: file nhãn là ĐẦU VÀO CHẤM ĐIỂM của E4.2 và D3.5. Sai ở đây thì mọi con
# số đo được sau này đều sai mà không có dấu hiệu gì — nên test bám vào ba thứ:
#   1. Ghi rồi đọc lại phải ra đúng thứ đã ghi (kể cả tiếng Việt)
#   2. Chấm lại thì dòng MỚI thắng, dòng cũ vẫn còn trong file
#   3. `is_correct` đúng ở BIÊN khoảng — chỗ dễ lệch một đơn vị nhất

from __future__ import annotations

import json

import pytest

from app.labels import BangNhan, Label, duong_dan_nhan, ghi_nhan, labels_of, load_labels


def mot_nhan(**thay_doi) -> Label:
    mac_dinh = dict(
        query_id="q001",
        query_vi="thủ môn cản phá quả penalty",
        task_type="KIS",
        video_id="L21_V001",
        frame_start=100,
        frame_end=200,
        label="correct",
        labeler="tester",
    )
    return Label(**{**mac_dinh, **thay_doi})


# ------------------------------------------------------------ dựng nhãn hợp lệ

def test_nhan_hop_le_thi_dung_nguyen_ven():
    n = mot_nhan()
    assert (n.frame_start, n.frame_end) == (100, 200)
    assert n.ts, "phải tự đóng dấu thời gian để biết dòng nào mới hơn"


@pytest.mark.parametrize("thay_doi,khop", [
    ({"label": "dung_roi"}, "label"),
    ({"query_id": ""}, "không được rỗng"),
    ({"video_id": ""}, "không được rỗng"),
    ({"frame_start": -1}, "< 0"),
    ({"frame_start": 300, "frame_end": 200}, "khoảng ngược"),
])
def test_nhan_sai_bi_chan_ngay_luc_dung(thay_doi, khop):
    """Nhãn sai nằm im trong file là thứ tệ nhất: eval chấm bằng nó rồi ra số sai."""
    with pytest.raises((ValueError, TypeError), match=khop):
        mot_nhan(**thay_doi)


def test_frame_khong_phai_so_nguyen_bi_tu_choi():
    with pytest.raises(TypeError, match="số nguyên"):
        mot_nhan(frame_start="một trăm")


def test_mot_frame_thi_hai_dau_bang_nhau():
    """Bấm đúng một frame là ca thường nhất — khoảng suy biến vẫn phải hợp lệ."""
    n = mot_nhan(frame_start=431, frame_end=431)
    assert n.chua(431) and not n.chua(430) and not n.chua(432)


# ------------------------------------------------------------------ ghi / đọc

def test_ghi_roi_doc_lai_ra_dung_thu_da_ghi(tmp_path):
    n = mot_nhan()
    ghi_nhan(n, tmp_path)
    doc = load_labels(tmp_path)
    assert len(doc) == 1
    assert doc[0].khoa == n.khoa and doc[0].label == "correct"


def test_tieng_viet_khong_bi_escape(tmp_path):
    """Nhãn phải đọc được bằng mắt — `ensure_ascii=True` biến query thành \\uXXXX."""
    ghi_nhan(mot_nhan(query_vi="cầu thủ áo đỏ sút bóng"), tmp_path)
    tho = duong_dan_nhan("tester", tmp_path).read_text(encoding="utf-8")
    assert "cầu thủ áo đỏ" in tho


def test_file_khong_bom_khong_crlf(tmp_path):
    """Cùng luật với file nộp (D0.2): UTF-8 không BOM, xuống dòng LF."""
    ghi_nhan(mot_nhan(), tmp_path)
    raw = duong_dan_nhan("tester", tmp_path).read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" not in raw


def test_moi_nguoi_mot_file_khong_dung_nhau(tmp_path):
    """Vì sao tách file: 5 người append chung một file là git conflict liên tục."""
    ghi_nhan(mot_nhan(labeler="minhhoang"), tmp_path)
    ghi_nhan(mot_nhan(labeler="thach", frame_start=500, frame_end=600), tmp_path)
    ten = {p.name for p in tmp_path.glob("*.jsonl")}
    assert ten == {"labels.minhhoang.jsonl", "labels.thach.jsonl"}
    assert len(load_labels(tmp_path)) == 2, "đọc phải GỘP nhãn của mọi người"


def test_thu_muc_chua_ton_tai_thi_tra_rong_chu_khong_sap(tmp_path):
    assert load_labels(tmp_path / "chua_co") == []


# --------------------------------------------------- append-only, dòng mới thắng

def test_cham_lai_thi_dong_moi_thang(tmp_path):
    ghi_nhan(mot_nhan(label="correct", ts="2026-08-10T10:00:00+07:00"), tmp_path)
    ghi_nhan(mot_nhan(label="wrong", ts="2026-08-10T11:00:00+07:00"), tmp_path)
    doc = load_labels(tmp_path)
    assert len(doc) == 1 and doc[0].label == "wrong"


def test_dong_cu_van_con_trong_file(tmp_path):
    """Append-only: giữ lịch sử đổi ý, và ghi thêm thì không hỏng dữ liệu đã có."""
    ghi_nhan(mot_nhan(label="correct", ts="2026-08-10T10:00:00+07:00"), tmp_path)
    ghi_nhan(mot_nhan(label="wrong", ts="2026-08-10T11:00:00+07:00"), tmp_path)
    dong = duong_dan_nhan("tester", tmp_path).read_text(encoding="utf-8").strip().split("\n")
    assert len(dong) == 2, "không được sửa/xoá dòng cũ"
    assert json.loads(dong[0])["label"] == "correct"


def test_khoang_khac_nhau_la_hai_nhan_khac_nhau(tmp_path):
    ghi_nhan(mot_nhan(frame_start=100, frame_end=200), tmp_path)
    ghi_nhan(mot_nhan(frame_start=300, frame_end=400), tmp_path)
    assert len(load_labels(tmp_path)) == 2


def test_dong_hong_khong_lam_mat_ca_file(tmp_path, capsys):
    """Máy tắt giữa lúc ghi không đáng làm mất toàn bộ nhãn đã chấm."""
    ghi_nhan(mot_nhan(), tmp_path)
    p = duong_dan_nhan("tester", tmp_path)
    with open(p, "a", encoding="utf-8", newline="\n") as f:
        f.write('{"query_id": "hong", khong_phai_json\n')
    ghi_nhan(mot_nhan(query_id="q002"), tmp_path)

    doc = load_labels(tmp_path)
    assert {n.query_id for n in doc} == {"q001", "q002"}
    assert "bỏ qua dòng hỏng" in capsys.readouterr().out, "hỏng thì phải BÁO, không im lặng"


# ------------------------------------------------------------ chấm điểm: is_correct

def test_is_correct_dung_o_hai_bien(tmp_path):
    """Biên là chỗ dễ lệch một đơn vị nhất — khoảng GỒM CẢ hai đầu."""
    ghi_nhan(mot_nhan(frame_start=100, frame_end=200), tmp_path)
    b = BangNhan(thu_muc=tmp_path)
    assert b.is_correct("q001", "L21_V001", 100)
    assert b.is_correct("q001", "L21_V001", 200)
    assert b.is_correct("q001", "L21_V001", 150)
    assert not b.is_correct("q001", "L21_V001", 99)
    assert not b.is_correct("q001", "L21_V001", 201)


def test_is_correct_cham_dung_frame_KHONG_phai_keyframe(tmp_path):
    """Lý do nhãn phải là KHOẢNG: allocator phát ra frame bất kỳ trong shot.

    Nhãn ghi mỗi 'keyframe 150 đúng' thì frame 143 do mức ② rải ra sẽ bị chấm sai,
    dù nó nằm ngay trong cùng cửa sổ đáp án.
    """
    ghi_nhan(mot_nhan(frame_start=140, frame_end=160, kf_id="L21_V001#k0042"), tmp_path)
    b = BangNhan(thu_muc=tmp_path)
    assert b.is_correct("q001", "L21_V001", 143), "frame không phải keyframe vẫn phải chấm được"


def test_video_khac_thi_khong_tinh(tmp_path):
    """Cùng số frame ở hai video khác nhau là hai chuyện khác nhau."""
    ghi_nhan(mot_nhan(video_id="L21_V001"), tmp_path)
    b = BangNhan(thu_muc=tmp_path)
    assert not b.is_correct("q001", "L21_V002", 150)


def test_query_khac_thi_khong_tinh(tmp_path):
    ghi_nhan(mot_nhan(query_id="q001"), tmp_path)
    assert not BangNhan(thu_muc=tmp_path).is_correct("q999", "L21_V001", 150)


def test_nhan_wrong_khong_cho_diem(tmp_path):
    ghi_nhan(mot_nhan(label="wrong"), tmp_path)
    assert not BangNhan(thu_muc=tmp_path).is_correct("q001", "L21_V001", 150)


def test_unsure_khong_cho_diem(tmp_path):
    """`unsure` = đã soi, chưa dám kết luận. Không được lẳng lặng tính thành đúng."""
    ghi_nhan(mot_nhan(label="unsure"), tmp_path)
    assert not BangNhan(thu_muc=tmp_path).is_correct("q001", "L21_V001", 150)


def test_wrong_chong_len_correct_khong_phu_dinh_correct(tmp_path):
    """`wrong` chỉ nói 'chỗ này đã soi, không phải' — không chứng minh chỗ khác cũng sai."""
    ghi_nhan(mot_nhan(frame_start=100, frame_end=200, label="correct"), tmp_path)
    ghi_nhan(mot_nhan(frame_start=190, frame_end=195, label="wrong"), tmp_path)
    assert BangNhan(thu_muc=tmp_path).is_correct("q001", "L21_V001", 150)


# ------------------------------------------------------------ tra cứu cho UI

def test_nhan_cua_frame_lay_khoang_hep_nhat(tmp_path):
    """Khoanh hẹp lại chính là để nói rõ hơn → khoảng hẹp thắng khoảng rộng."""
    ghi_nhan(mot_nhan(frame_start=100, frame_end=200, label="correct"), tmp_path)
    ghi_nhan(mot_nhan(frame_start=148, frame_end=152, label="wrong"), tmp_path)
    b = BangNhan(thu_muc=tmp_path)
    assert b.nhan_cua_frame("q001", "L21_V001", 150) == "wrong"
    assert b.nhan_cua_frame("q001", "L21_V001", 120) == "correct"


def test_nhan_cua_frame_chua_cham_thi_None(tmp_path):
    assert BangNhan(thu_muc=tmp_path).nhan_cua_frame("q001", "L21_V001", 1) is None


def test_labels_of_va_cac_query(tmp_path):
    ghi_nhan(mot_nhan(query_id="q001"), tmp_path)
    ghi_nhan(mot_nhan(query_id="q002", frame_start=1, frame_end=2), tmp_path)
    assert len(labels_of("q001", tmp_path)) == 1
    assert BangNhan(thu_muc=tmp_path).cac_query() == ["q001", "q002"]


# ------------------------------------- ba trường cho Q&A và TRAKE (thêm ở E4.2)

def test_doc_duoc_dong_nhan_CU_thieu_ba_truong_moi(tmp_path):
    """Dòng nhãn viết trước khi có Q&A/TRAKE phải đọc lại được nguyên vẹn.

    `Label(**json.loads(...))` sẽ nổ `TypeError` nếu trường mới không có mặc định.
    Hiện `dev_set/` còn rỗng nên chưa mất gì, nhưng lần thêm trường TIẾP THEO sẽ
    diễn ra khi đã có vài trăm nhãn — test này chốt luật lại từ bây giờ.
    """
    p = tmp_path / "labels.cu.jsonl"
    p.write_text(json.dumps({
        "query_id": "q1", "query_vi": "cũ", "task_type": "KIS", "video_id": "L01_V001",
        "frame_start": 10, "frame_end": 20, "label": "correct", "labeler": "cu",
        "ts": "2026-08-01T00:00:00+07:00",
    }, ensure_ascii=False) + "\n", encoding="utf-8")

    nhan = load_labels(tmp_path)
    assert len(nhan) == 1
    assert nhan[0].answer_text is None and nhan[0].moment_idx is None


def test_hai_khoanh_khac_TRAKE_khong_de_len_nhau(tmp_path):
    """Khoá gộp phải gồm `moment_idx` — sửa khoảnh khắc 2 không được xoá khoảnh khắc 1."""
    goc = dict(query_id="t1", query_vi="nhảy cao", task_type="TRAKE",
               video_id="L10_V010", label="correct", labeler="test")
    for j, (s, e) in enumerate([(95, 105), (145, 155)]):
        ghi_nhan(Label(frame_start=s, frame_end=e, moment_idx=j, **goc), tmp_path)

    bn = BangNhan(thu_muc=tmp_path)
    assert len(bn) == 2
    assert bn.so_khoanh_khac("t1") == 2
    assert bn.is_correct("t1", "L10_V010", 101, moment_idx=0)
    assert not bn.is_correct("t1", "L10_V010", 101, moment_idx=1), "nhầm khoảnh khắc"


def test_answer_dung_tra_ba_gia_tri():
    """True / False / **None khi chưa ai chấm** — gộp None vào False là dìm điểm Q&A."""
    goc = dict(query_id="q1", query_vi="?", task_type="QA", video_id="L01_V001",
               frame_start=0, frame_end=9, labeler="test")
    bn = BangNhan([
        Label(label="correct", answer_text="màu xanh", answer_dung=True, **goc),
        Label(label="wrong", answer_text="màu trắng", answer_dung=False, **goc),
    ])
    assert bn.answer_dung("q1", "màu xanh") is True
    assert bn.answer_dung("q1", "màu trắng") is False
    assert bn.answer_dung("q1", "màu tím") is None
    assert bn.answer_dung("q1", None) is None


def test_so_khoanh_khac_None_cho_KIS():
    """Truy vấn không phải TRAKE thì không có N — đừng trả 0 rồi chia cho 0."""
    bn = BangNhan([Label(query_id="q1", query_vi="?", task_type="KIS",
                         video_id="L01_V001", frame_start=0, frame_end=9,
                         label="correct", labeler="test")])
    assert bn.so_khoanh_khac("q1") is None
