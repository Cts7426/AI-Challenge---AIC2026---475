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

from dataclasses import asdict

from app.labels import (LabelIndex, Label, is_correct, label_path, append_label,
                        labels_of, load_labels)


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
    assert n.contains(431) and not n.contains(430) and not n.contains(432)


# ------------------------------------------------------------------ ghi / đọc

def test_ghi_roi_doc_lai_ra_dung_thu_da_ghi(tmp_path):
    n = mot_nhan()
    append_label(n, tmp_path)
    doc = load_labels(tmp_path)
    assert len(doc) == 1
    assert doc[0].key == n.key and doc[0].label == "correct"


def test_tieng_viet_khong_bi_escape(tmp_path):
    """Nhãn phải đọc được bằng mắt — `ensure_ascii=True` biến query thành \\uXXXX."""
    append_label(mot_nhan(query_vi="cầu thủ áo đỏ sút bóng"), tmp_path)
    tho = label_path("tester", tmp_path).read_text(encoding="utf-8")
    assert "cầu thủ áo đỏ" in tho


def test_file_khong_bom_khong_crlf(tmp_path):
    """Cùng luật với file nộp (D0.2): UTF-8 không BOM, xuống dòng LF."""
    append_label(mot_nhan(), tmp_path)
    raw = label_path("tester", tmp_path).read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" not in raw


def test_moi_nguoi_mot_file_khong_dung_nhau(tmp_path):
    """Vì sao tách file: 5 người append chung một file là git conflict liên tục."""
    append_label(mot_nhan(labeler="minhhoang"), tmp_path)
    append_label(mot_nhan(labeler="thach", frame_start=500, frame_end=600), tmp_path)
    ten = {p.name for p in tmp_path.glob("*.jsonl")}
    assert ten == {"labels.minhhoang.jsonl", "labels.thach.jsonl"}
    assert len(load_labels(tmp_path)) == 2, "đọc phải GỘP nhãn của mọi người"


def test_thu_muc_chua_ton_tai_thi_tra_rong_chu_khong_sap(tmp_path):
    assert load_labels(tmp_path / "chua_co") == []


# --------------------------------------------------- append-only, dòng mới thắng

def test_cham_lai_thi_dong_moi_thang(tmp_path):
    append_label(mot_nhan(label="correct", ts="2026-08-10T10:00:00+07:00"), tmp_path)
    append_label(mot_nhan(label="wrong", ts="2026-08-10T11:00:00+07:00"), tmp_path)
    doc = load_labels(tmp_path)
    assert len(doc) == 1 and doc[0].label == "wrong"


def test_dong_cu_van_con_trong_file(tmp_path):
    """Append-only: giữ lịch sử đổi ý, và ghi thêm thì không hỏng dữ liệu đã có."""
    append_label(mot_nhan(label="correct", ts="2026-08-10T10:00:00+07:00"), tmp_path)
    append_label(mot_nhan(label="wrong", ts="2026-08-10T11:00:00+07:00"), tmp_path)
    dong = label_path("tester", tmp_path).read_text(encoding="utf-8").strip().split("\n")
    assert len(dong) == 2, "không được sửa/xoá dòng cũ"
    assert json.loads(dong[0])["label"] == "correct"


def test_khoang_khac_nhau_la_hai_nhan_khac_nhau(tmp_path):
    append_label(mot_nhan(frame_start=100, frame_end=200), tmp_path)
    append_label(mot_nhan(frame_start=300, frame_end=400), tmp_path)
    assert len(load_labels(tmp_path)) == 2


def test_dong_hong_khong_lam_mat_ca_file(tmp_path, capsys):
    """Máy tắt giữa lúc ghi không đáng làm mất toàn bộ nhãn đã chấm."""
    append_label(mot_nhan(), tmp_path)
    p = label_path("tester", tmp_path)
    with open(p, "a", encoding="utf-8", newline="\n") as f:
        f.write('{"query_id": "hong", khong_phai_json\n')
    append_label(mot_nhan(query_id="q002"), tmp_path)

    doc = load_labels(tmp_path)
    assert {n.query_id for n in doc} == {"q001", "q002"}
    assert "bỏ qua dòng hỏng" in capsys.readouterr().out, "hỏng thì phải BÁO, không im lặng"


# ------------------------------------------------------------ chấm điểm: is_correct

def test_is_correct_dung_o_hai_bien(tmp_path):
    """Biên là chỗ dễ lệch một đơn vị nhất — khoảng GỒM CẢ hai đầu."""
    append_label(mot_nhan(frame_start=100, frame_end=200), tmp_path)
    b = LabelIndex(directory=tmp_path)
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
    append_label(mot_nhan(frame_start=140, frame_end=160, kf_id="L21_V001#k0042"), tmp_path)
    b = LabelIndex(directory=tmp_path)
    assert b.is_correct("q001", "L21_V001", 143), "frame không phải keyframe vẫn phải chấm được"


def test_video_khac_thi_khong_tinh(tmp_path):
    """Cùng số frame ở hai video khác nhau là hai chuyện khác nhau."""
    append_label(mot_nhan(video_id="L21_V001"), tmp_path)
    b = LabelIndex(directory=tmp_path)
    assert not b.is_correct("q001", "L21_V002", 150)


def test_query_khac_thi_khong_tinh(tmp_path):
    append_label(mot_nhan(query_id="q001"), tmp_path)
    assert not LabelIndex(directory=tmp_path).is_correct("q999", "L21_V001", 150)


def test_nhan_wrong_khong_cho_diem(tmp_path):
    append_label(mot_nhan(label="wrong"), tmp_path)
    assert not LabelIndex(directory=tmp_path).is_correct("q001", "L21_V001", 150)


def test_unsure_khong_cho_diem(tmp_path):
    """`unsure` = đã soi, chưa dám kết luận. Không được lẳng lặng tính thành đúng."""
    append_label(mot_nhan(label="unsure"), tmp_path)
    assert not LabelIndex(directory=tmp_path).is_correct("q001", "L21_V001", 150)


def test_wrong_chong_len_correct_khong_phu_dinh_correct(tmp_path):
    """`wrong` chỉ nói 'chỗ này đã soi, không phải' — không chứng minh chỗ khác cũng sai."""
    append_label(mot_nhan(frame_start=100, frame_end=200, label="correct"), tmp_path)
    append_label(mot_nhan(frame_start=190, frame_end=195, label="wrong"), tmp_path)
    assert LabelIndex(directory=tmp_path).is_correct("q001", "L21_V001", 150)


# ------------------------------------------------------------ tra cứu cho UI

def test_nhan_cua_frame_lay_khoang_hep_nhat(tmp_path):
    """Khoanh hẹp lại chính là để nói rõ hơn → khoảng hẹp thắng khoảng rộng."""
    append_label(mot_nhan(frame_start=100, frame_end=200, label="correct"), tmp_path)
    append_label(mot_nhan(frame_start=148, frame_end=152, label="wrong"), tmp_path)
    b = LabelIndex(directory=tmp_path)
    assert b.label_of_frame("q001", "L21_V001", 150) == "wrong"
    assert b.label_of_frame("q001", "L21_V001", 120) == "correct"


def test_nhan_cua_frame_chua_cham_thi_None(tmp_path):
    assert LabelIndex(directory=tmp_path).label_of_frame("q001", "L21_V001", 1) is None


def test_labels_of_va_cac_query(tmp_path):
    append_label(mot_nhan(query_id="q001"), tmp_path)
    append_label(mot_nhan(query_id="q002", frame_start=1, frame_end=2), tmp_path)
    assert len(labels_of("q001", tmp_path)) == 1
    assert LabelIndex(directory=tmp_path).query_ids() == ["q001", "q002"]


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
        append_label(Label(frame_start=s, frame_end=e, moment_idx=j, **goc), tmp_path)

    bn = LabelIndex(directory=tmp_path)
    assert len(bn) == 2
    assert bn.n_moments("t1") == 2
    assert bn.is_correct("t1", "L10_V010", 101, moment_idx=0)
    assert not bn.is_correct("t1", "L10_V010", 101, moment_idx=1), "nhầm khoảnh khắc"


def test_answer_dung_tra_ba_gia_tri():
    """True / False / **None khi chưa ai chấm** — gộp None vào False là dìm điểm Q&A."""
    goc = dict(query_id="q1", query_vi="?", task_type="QA", video_id="L01_V001",
               frame_start=0, frame_end=9, labeler="test")
    bn = LabelIndex([
        Label(label="correct", answer_text="màu xanh", answer_correct=True, **goc),
        Label(label="wrong", answer_text="màu trắng", answer_correct=False, **goc),
    ])
    assert bn.is_answer_correct("q1", "màu xanh") is True
    assert bn.is_answer_correct("q1", "màu trắng") is False
    assert bn.is_answer_correct("q1", "màu tím") is None
    assert bn.is_answer_correct("q1", None) is None


def test_answer_khop_theo_LUAT_CHUNG_khong_so_chuoi_nguyen_van():
    """Cùng bộ luật với dev_set/tools/scoring.py và majority voting của qa.py.

    Người chấm phán trên MỘT cách diễn đạt ("5"); hệ thật trả về cách khác ("5 người",
    "Năm"). So chuỗi nguyên văn thì phán quyết đã có không được nhận ra → báo "chưa
    chấm" → eval.py tính 0. Điểm Q&A tụt theo số cách diễn đạt chứ không theo chất
    lượng hệ thống, và không có dấu hiệu gì.
    """
    goc = dict(query_id="q1", query_vi="mấy người?", task_type="QA",
               video_id="L01_V001", frame_start=0, frame_end=9, labeler="test")
    bn = LabelIndex([Label(label="correct", answer_text="5", answer_correct=True, **goc)])

    assert bn.is_answer_correct("q1", "5.") is True, "tầng 1 — dấu câu"
    assert bn.is_answer_correct("q1", "Năm") is True, "tầng 2 — số ↔ chữ"
    assert bn.is_answer_correct("q1", "7") is None, "khác nghĩa thì vẫn phải là chưa chấm"


def test_answer_dong_khop_NGUYEN_VAN_thang_dong_khop_gan_dung():
    """Tầng khớp quyết định, không phải thứ tự dòng nhãn trên đĩa."""
    goc = dict(query_id="q1", query_vi="?", task_type="QA", video_id="L01_V001",
               frame_start=0, frame_end=9, labeler="test")
    nhan = [
        Label(label="wrong", answer_text="ông nguyễn văn ba",
              answer_correct=False, **goc),
        Label(label="correct", answer_text="ông nguyễn văn bảo",
              answer_correct=True, **goc),
    ]
    # Cùng nội dung nhãn, đảo thứ tự đọc → phán quyết phải không đổi
    assert LabelIndex(nhan).is_answer_correct("q1", "ông nguyễn văn bảo") is True
    assert LabelIndex(nhan[::-1]).is_answer_correct("q1", "ông nguyễn văn bảo") is True


def test_so_khoanh_khac_None_cho_KIS():
    """Truy vấn không phải TRAKE thì không có N — đừng trả 0 rồi chia cho 0."""
    bn = LabelIndex([Label(query_id="q1", query_vi="?", task_type="KIS",
                         video_id="L01_V001", frame_start=0, frame_end=9,
                         label="correct", labeler="test")])
    assert bn.n_moments("q1") is None


# ================================================== hai lượt chấm CÙNG một khoá
# Q&A có hai cửa tử độc lập nhưng UI ghi cả hai vào cùng `Label.key`. Bốn test dưới
# khoá lại việc lượt sau không được xoá lượt trước.

def test_phan_answer_KHONG_lat_duoc_nhan_frame(tmp_path):
    """Bấm '✗ Sai' rồi phán answer đúng → frame vẫn phải là `wrong`.

    Bản cũ đặt `label` theo phán quyết ANSWER nên frame lật thành `correct`,
    `eval.py` chấm dòng đó 1.0 trong khi BTC chấm 0.
    """
    goc = dict(query_id="q1", task_type="QA", video_id="L21_V001",
               frame_start=888, frame_end=888)
    append_label(mot_nhan(label="wrong", ts="2026-08-14T10:00:00+07:00", **goc), tmp_path)
    append_label(mot_nhan(label="wrong", ts="2026-08-14T10:01:00+07:00",
                          answer_text="màu xanh", answer_correct=True, **goc), tmp_path)
    bn = LabelIndex(directory=tmp_path)
    assert not bn.is_correct("q1", "L21_V001", 888), "phán answer không được lật cửa frame"
    assert bn.is_answer_correct("q1", "màu xanh") is True


def test_cham_frame_SAU_khi_phan_answer_khong_xoa_answer(tmp_path):
    """Chiều ngược lại: nút frame ghi answer_text=None, không được coi là 'xoá answer'."""
    goc = dict(query_id="q1", task_type="QA", video_id="L21_V001",
               frame_start=500, frame_end=500)
    append_label(mot_nhan(label="unsure", ts="2026-08-14T10:00:00+07:00",
                          answer_text="màu xanh", answer_correct=True, **goc), tmp_path)
    append_label(mot_nhan(label="correct", ts="2026-08-14T10:01:00+07:00", **goc), tmp_path)
    bn = LabelIndex(directory=tmp_path)
    assert bn.is_correct("q1", "L21_V001", 500), "lượt chấm frame vẫn phải thắng ở ô label"
    assert bn.is_answer_correct("q1", "màu xanh") is True, "answer đã phán không được biến mất"


def test_dong_moi_van_thang_o_o_no_thuc_su_noi_toi(tmp_path):
    """Gộp không được biến thành 'không bao giờ đổi ý được'."""
    goc = dict(query_id="q1", task_type="QA", video_id="L21_V001",
               frame_start=7, frame_end=7)
    append_label(mot_nhan(label="correct", ts="2026-08-14T10:00:00+07:00",
                          answer_text="màu xanh", answer_correct=True, **goc), tmp_path)
    append_label(mot_nhan(label="correct", ts="2026-08-14T10:01:00+07:00",
                          answer_text="màu xanh", answer_correct=False, **goc), tmp_path)
    assert LabelIndex(directory=tmp_path).is_answer_correct("q1", "màu xanh") is False


# ------------------------------------------------------------ ts lệch múi giờ

def test_ts_so_theo_MOC_THOI_GIAN_khong_so_chuoi(tmp_path):
    """`ts` mang offset của máy người chấm: Windows `+07:00`, WSL/Docker `+00:00`.

    So chuỗi thì `04:30+00:00` (VN 11:30) bị coi là CŨ HƠN `10:00+07:00` (VN 10:00)
    → chấm lại xong dòng mới bị bỏ, im lặng.
    """
    append_label(mot_nhan(label="correct", ts="2026-08-14T10:00:00+07:00"), tmp_path)
    append_label(mot_nhan(label="wrong", ts="2026-08-14T04:30:00+00:00"), tmp_path)
    doc = load_labels(tmp_path)
    assert len(doc) == 1 and doc[0].label == "wrong"


def test_ts_hong_thi_thua_dong_co_ts_doc_duoc(tmp_path):
    append_label(mot_nhan(label="wrong", ts="rác"), tmp_path)
    append_label(mot_nhan(label="correct", ts="2026-08-14T10:00:00+07:00"), tmp_path)
    assert load_labels(tmp_path)[0].label == "correct"


# --------------------------------------------------- N của TRAKE do người KHAI

def test_N_khai_thang_N_suy_tu_so_nhan_da_cham():
    """Chấm dở 3/4 khoảnh khắc mà suy mẫu số thì ra 3 → điểm cao hơn thật."""
    goc = dict(query_id="t1", query_vi="?", task_type="TRAKE", video_id="L10_V010",
               label="correct", labeler="test", n_moments_total=4)
    bn = LabelIndex([
        Label(frame_start=95, frame_end=105, moment_idx=0, **goc),
        Label(frame_start=145, frame_end=155, moment_idx=1, **goc),
        Label(frame_start=195, frame_end=205, moment_idx=2, **goc),
    ])
    assert bn.n_moments("t1") == 4, "phải lấy N người khai, không lấy max(moment_idx)+1"
    assert bn.n_is_declared("t1")


def test_khong_ai_khai_N_thi_suy_nhung_phai_bao_ra():
    goc = dict(query_id="t1", query_vi="?", task_type="TRAKE", video_id="L10_V010",
               label="correct", labeler="test")
    bn = LabelIndex([Label(frame_start=95, frame_end=105, moment_idx=0, **goc)])
    assert bn.n_moments("t1") == 1
    assert not bn.n_is_declared("t1"), "eval.py dựa vào cờ này để cảnh báo"


def test_hai_nguoi_khai_N_lech_nhau_thi_lay_so_LON_hon():
    """Mẫu số lớn → điểm thấp hơn. Thước đo lệch xuống thì có người đi soi."""
    goc = dict(query_id="t1", query_vi="?", task_type="TRAKE", video_id="L10_V010",
               label="correct", labeler="test", frame_start=0, frame_end=9)
    bn = LabelIndex([
        Label(moment_idx=0, n_moments_total=4, **goc),
        Label(moment_idx=1, n_moments_total=5, **goc),
    ])
    assert bn.n_moments("t1") == 5


@pytest.mark.parametrize("n, moment", [(1, None), (4, 4), (4, 9)])
def test_khai_N_mau_thuan_bi_chan_ngay_luc_dung(n, moment):
    with pytest.raises(ValueError):
        mot_nhan(task_type="TRAKE", n_moments_total=n, moment_idx=moment)


def test_dong_nhan_CU_thieu_o_khai_N_van_doc_duoc(tmp_path):
    """Nhãn chấm trước khi thêm ô này phải đọc lại được, không gãy."""
    dong = {"query_id": "q1", "query_vi": "?", "task_type": "TRAKE",
            "video_id": "L21_V001", "frame_start": 10, "frame_end": 20,
            "label": "correct", "labeler": "cu", "ts": "2026-08-10T10:00:00+07:00",
            "moment_idx": 0}
    p = label_path("cu", tmp_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(dong, ensure_ascii=False) + "\n", encoding="utf-8")
    bn = LabelIndex(directory=tmp_path)
    assert len(bn) == 1 and bn.n_moments("q1") == 1 and not bn.n_is_declared("q1")


def test_N_khai_khong_duoc_NHO_hon_so_khoanh_khac_da_cham():
    """`__post_init__` chỉ kiểm `moment_idx < n` TRÊN CHÍNH DÒNG khai N.

    Dòng khai N=2 và dòng `moment_idx=2` là hai dòng riêng nên qua được cửa đó —
    mẫu số ra 2 trong khi có 3 khoảnh khắc, đúng kiểu thổi phồng mà ô này sinh ra
    để chặn.
    """
    goc = dict(query_id="t", query_vi="?", task_type="TRAKE", video_id="L21_V001",
               label="correct", labeler="test", frame_start=0, frame_end=9)
    bn = LabelIndex([
        Label(moment_idx=0, n_moments_total=2, **goc),
        Label(moment_idx=1, n_moments_total=2, **goc),
        Label(moment_idx=2, **goc),
    ])
    assert bn.n_moments("t") == 3


def test_N_khai_LON_hon_so_da_cham_thi_giu_so_khai():
    goc = dict(query_id="t", query_vi="?", task_type="TRAKE", video_id="L21_V001",
               label="correct", labeler="test", frame_start=0, frame_end=9)
    assert LabelIndex([Label(moment_idx=0, n_moments_total=6, **goc)]).n_moments("t") == 6


# ===================== nhánh chưa từng chạy (đo bằng trace) — phủ nốt cho kín

def test_dong_trong_trong_file_bi_bo_qua(tmp_path):
    p = label_path("tester", tmp_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(mot_nhan())) + "\n\n   \n", encoding="utf-8")
    assert len(load_labels(tmp_path)) == 1


def test_ts_KHONG_co_mui_gio_van_so_duoc(tmp_path):
    """Dòng sửa tay thường mất offset — so với dòng có offset không được ném TypeError."""
    append_label(mot_nhan(label="correct", ts="2026-08-14T10:00:00"), tmp_path)
    append_label(mot_nhan(label="wrong", ts="2026-08-14T11:00:00+07:00"), tmp_path)
    doc = load_labels(tmp_path)
    assert len(doc) == 1 and doc[0].label == "wrong"


def test_dong_CU_den_sau_khong_de_len_dong_moi(tmp_path):
    """File của người A đọc sau file người B, mà nhãn của A lại cũ hơn."""
    goc = dict(query_id="q1", video_id="L21_V001", frame_start=5, frame_end=5)
    append_label(mot_nhan(labeler="aa", label="wrong", ts="2026-08-14T09:00:00+07:00", **goc), tmp_path)
    append_label(mot_nhan(labeler="zz", label="correct", ts="2026-08-14T08:00:00+07:00", **goc), tmp_path)
    assert LabelIndex(directory=tmp_path).is_correct("q1", "L21_V001", 5) is False


def test_gop_giu_N_khai_khi_dong_moi_khong_khai(tmp_path):
    goc = dict(query_id="t", task_type="TRAKE", video_id="L21_V001",
               frame_start=1, frame_end=9, moment_idx=0)
    append_label(mot_nhan(label="correct", n_moments_total=4,
                          ts="2026-08-14T10:00:00+07:00", **goc), tmp_path)
    append_label(mot_nhan(label="correct", answer_text="x", answer_correct=True,
                          ts="2026-08-14T11:00:00+07:00", **goc), tmp_path)
    assert LabelIndex(directory=tmp_path).n_moments("t") == 4


def test_ham_is_correct_tien_tay(tmp_path):
    append_label(mot_nhan(frame_start=100, frame_end=200), tmp_path)
    assert is_correct("q001", "L21_V001", 150, directory=tmp_path)
    assert not is_correct("q001", "L21_V001", 999, directory=tmp_path)
