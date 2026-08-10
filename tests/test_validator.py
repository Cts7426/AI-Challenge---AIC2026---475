# tests/test_validator.py — validator ngữ nghĩa: mỗi luật 1 ca ĐÚNG + 1 ca SAI
#
# Vì sao phải có ca sai? Một validator luôn trả [] cũng "pass" mọi ca đúng.
# Chỉ ca sai mới chứng minh nó thật sự bắt được lỗi.

from __future__ import annotations

from backend.export import validate_all, validate_file, validate_submission
from tests.conftest import cat_bot, replace_answer, rules_of


# ------------------------------------------------------------------ ca ĐÚNG

def test_du_lieu_chuan_thi_khong_bao_loi(all_subs):
    """Ba dạng bài, 100 câu trả lời mỗi truy vấn → validator phải im lặng."""
    assert validate_all(all_subs) == []


def test_rong_thi_bao_loi():
    assert rules_of(validate_all([])) == {"empty"}


def test_query_khong_co_cau_tra_loi_nao(kis):
    assert "empty" in rules_of(validate_submission(cat_bot(kis, 0)))


# ------------------------------------------------- luật: đúng 100 câu trả lời

def test_thieu_cau_tra_loi_bi_bat(kis):
    assert "answer_count" in rules_of(validate_submission(cat_bot(kis, 99)))


def test_du_100_thi_khong_keu(kis):
    assert "answer_count" not in rules_of(validate_submission(kis))


def test_query_id_trung_bi_bat(kis):
    assert "query_duplicate" in rules_of(validate_all([kis, kis]))


# ------------------------------------------------------- luật: video_id tồn tại

def test_video_khong_ton_tai_bi_bat(kis):
    assert "video_unknown" in rules_of(validate_submission(replace_answer(kis, 0, video_id="L99_V999")))


def test_video_la_khong_lam_sap_validator(kis):
    """Video lạ phải thành Issue, KHÔNG được ném exception ra ngoài."""
    issues = validate_submission(replace_answer(kis, 0, video_id="KHONG_CO_THAT"))
    assert any(i.rule == "video_unknown" for i in issues)


# --------------------------------------------- luật: frame_id ∈ [0, n_frames)

def test_frame_vuot_do_dai_video_bi_bat(kis, real_videos):
    n = real_videos[0][1]
    assert "frame_out_of_range" in rules_of(validate_submission(replace_answer(kis, 3, frame_ids=(n,))))


def test_frame_am_bi_bat(kis):
    assert "frame_out_of_range" in rules_of(validate_submission(replace_answer(kis, 3, frame_ids=(-1,))))


def test_frame_cuoi_cung_van_hop_le(kis, real_videos):
    """Biên trên là n_frames-1 — phải được chấp nhận, không nhầm thành tràn."""
    n = real_videos[0][1]
    sub = replace_answer(kis, 3, frame_ids=(n - 1,))
    assert "frame_out_of_range" not in rules_of(validate_submission(sub))


# ----------------------------------------------------- luật: không trùng lặp

def test_hai_cau_tra_loi_trung_bi_bat(kis):
    sub = replace_answer(kis, 7, frame_ids=kis.answers[6].frame_ids)
    assert "duplicate_answer" in rules_of(validate_submission(sub))


def test_keyframe_id_khac_nhau_van_tinh_la_trung(kis):
    """keyframe_id chỉ để debug — không được cứu một dòng trùng nội dung."""
    sub = replace_answer(kis, 7, frame_ids=kis.answers[6].frame_ids, keyframe_id="L21_V001#k0009")
    assert "duplicate_answer" in rules_of(validate_submission(sub))


# ------------------------------------------- luật: TRAKE N frame, tăng dần ngặt

def test_trake_khong_tang_dan_bi_bat(trake):
    a, b, c, d = trake.answers[0].frame_ids
    assert "trake_not_increasing" in rules_of(
        validate_submission(replace_answer(trake, 0, frame_ids=(a, c, b, d)))
    )


def test_trake_hai_frame_bang_nhau_bi_bat(trake):
    """Tăng dần NGẶT: hai khoảnh khắc khác nhau không thể cùng một frame."""
    a, b, c, d = trake.answers[0].frame_ids
    assert "trake_not_increasing" in rules_of(
        validate_submission(replace_answer(trake, 0, frame_ids=(a, b, b, d)))
    )


def test_trake_so_frame_khong_dong_nhat_bi_bat(trake):
    sub = replace_answer(trake, 2, frame_ids=trake.answers[2].frame_ids[:3])
    assert "trake_n_inconsistent" in rules_of(validate_submission(sub))


def test_trake_sai_N_so_voi_de_bai_bi_bat(trake):
    """Khi đề công bố N, nộp thiếu/thừa khoảnh khắc phải bị bắt."""
    assert "trake_n_mismatch" in rules_of(validate_submission(trake, expected_n=5))


def test_trake_dung_N_thi_khong_keu(trake):
    assert "trake_n_mismatch" not in rules_of(validate_submission(trake, expected_n=4))


def test_kis_nhieu_hon_1_frame_bi_bat(kis):
    assert "frame_count" in rules_of(validate_submission(replace_answer(kis, 0, frame_ids=(10, 20))))


# --------------------------------------------------- luật: Q&A có answer

def test_qa_thieu_answer_bi_bat(qa):
    assert "answer_empty" in rules_of(validate_submission(replace_answer(qa, 0, answer_text="")))


def test_qa_answer_toan_khoang_trang_bi_bat(qa):
    assert "answer_empty" in rules_of(validate_submission(replace_answer(qa, 0, answer_text="   ")))


def test_kis_co_answer_bi_bat(kis):
    assert "answer_unexpected" in rules_of(validate_submission(replace_answer(kis, 0, answer_text="thừa")))


# ------------------------------------------------------------ luật: task_type

def test_task_type_la_bi_bat(kis):
    import dataclasses

    assert "task_type" in rules_of(validate_submission(dataclasses.replace(kis, task_type="AVS")))


# ----------------------------------------------------- luật: UTF-8 không BOM

def test_file_utf8_khong_bom_thi_sach(tmp_path):
    p = tmp_path / "ok.csv"
    p.write_text("L21_V001,100\nL21_V001,tiếng Việt có dấu\n", encoding="utf-8", newline="")
    assert validate_file(p) == []


def test_file_co_bom_bi_bat(tmp_path):
    p = tmp_path / "bom.csv"
    p.write_text("L21_V001,100\n", encoding="utf-8-sig", newline="")
    assert "bom" in rules_of(validate_file(p))


def test_file_khong_phai_utf8_bi_bat(tmp_path):
    # 0xFF không bao giờ là byte hợp lệ trong UTF-8 — mô phỏng file ghi bằng
    # bảng mã Windows lọt vào bài nộp
    p = tmp_path / "sai_ma.csv"
    p.write_bytes(b"L21_V001,100,ti\xff\xfeng Vi\xeat\n")
    assert "not_utf8" in rules_of(validate_file(p))


def test_file_rong_bi_bat(tmp_path):
    p = tmp_path / "empty.csv"
    p.write_text("", encoding="utf-8")
    assert "file_empty" in rules_of(validate_file(p))


def test_file_khong_ton_tai_bi_bat(tmp_path):
    assert "file_missing" in rules_of(validate_file(tmp_path / "khong_co.csv"))


# ------------------------------------------------------------------- linh tinh

def test_gom_nhieu_loi_cung_luc(kis):
    """Validator phải trả HẾT lỗi một lượt, không dừng ở lỗi đầu tiên."""
    sub = cat_bot(kis, 99)
    sub = replace_answer(sub, 0, video_id="L99_V999")
    sub = replace_answer(sub, 1, frame_ids=(-5,))
    r = rules_of(validate_submission(sub))
    assert {"answer_count", "video_unknown", "frame_out_of_range"} <= r


def test_issue_co_vi_tri_de_truy(kis):
    """Issue phải chỉ ra đúng thứ hạng để người vận hành tìm được dòng lỗi."""
    issues = validate_submission(replace_answer(kis, 4, frame_ids=(-1,)))
    loi = [i for i in issues if i.rule == "frame_out_of_range"][0]
    assert loi.query_id == "kis_001" and loi.position == 5  # index 4 → hạng 5


# ------------------------------------------------- chạy trên TOÀN BỘ dữ liệu thật
# Hai test dưới không dùng dữ liệu dựng sẵn — chúng quét thẳng 873 video và
# 177.321 keyframe của Data Factory. Mục đích: chứng minh validator KHÔNG báo
# nhầm trên dữ liệu đúng, và bắt được nếu Data Factory giao ra dữ liệu lệch.

def test_moi_keyframe_that_deu_qua_duoc_luat_bien():
    """Không keyframe nào trong frame_map được vượt quá n_frames của video nó.

    Đây chính là luật `frame_out_of_range` chạy trên toàn bộ dataset. Nếu test này
    đỏ thì hoặc Data Factory giao dữ liệu lệch, hoặc luật của mình sai — cả hai đều
    phải biết trước ngày nộp chứ không phải lúc đang thi.
    """
    import pandas as pd

    # Tên riêng tư → lấy thẳng từ module cài đặt, không qua __init__
    from backend.export.exporter import _video_frames
    from tests.conftest import _frame_map

    df = _frame_map().merge(
        pd.Series(_video_frames(), name="n_frames").rename_axis("video_id").reset_index(),
        on="video_id", how="left",
    )  # n_frames ở đây là tên do mình đặt cho Series, không phải tên cột trong parquet
    thieu = df[df.n_frames.isna()]
    assert thieu.empty, f"{thieu.video_id.nunique()} video có trong frame_map mà thiếu ở video_info"

    tran = df[(df.frame_idx < 0) | (df.frame_idx >= df.n_frames)]
    assert tran.empty, (
        f"{len(tran)} keyframe vượt biên, ví dụ:\n"
        f"{tran.head(5)[['video_id', 'btc_ordinal', 'frame_idx', 'n_frames']]}"
    )


def test_doi_ten_cot_thi_bao_ro_rang(tmp_path):
    """Data Factory đổi schema → phải gãy với thông báo đọc được, không phải ArrowInvalid.

    07/08 đã xảy ra thật: `n_frames` đổi thành `nb_frames_decoded`, cả bộ test đỏ với
    lỗi từ trong ruột pyarrow, mất công mới lần ra là thiếu cột gì.
    """
    import pandas as pd
    import pytest

    from backend.export.exporter import _doc_cot

    p = tmp_path / "gia.parquet"
    pd.DataFrame({"video_id": ["L21_V001"], "ten_moi": [100]}).to_parquet(p)

    with pytest.raises(KeyError) as e:
        _doc_cot(p, ["video_id", "ten_cu"], "Công Lý")
    assert "ten_cu" in str(e.value), "phải nói rõ cột nào thiếu"
    assert "ten_moi" in str(e.value), "phải liệt kê cột đang có"
    assert "Công Lý" in str(e.value), "phải nói rõ hỏi ai"


def test_thieu_file_thi_bao_ro_ai_phai_giao(tmp_path):
    import pytest

    from backend.export.exporter import _doc_cot

    with pytest.raises(FileNotFoundError, match="Công Lý"):
        _doc_cot(tmp_path / "khong_co.parquet", ["a"], "Công Lý")


def test_validator_khong_bao_nham_tren_20_video_that():
    """Dựng bài nộp từ keyframe thật của 20 video → validator phải im lặng hết.

    Bổ sung cho test trên: chỗ kia kiểm dữ liệu bằng pandas, chỗ này chạy ĐÚNG
    đường code mà lúc thi sẽ chạy.
    """
    from backend.export import all_video_ids, n_frames_of
    from tests.conftest import build_sub, frames_of

    da_kiem = 0
    for vid in all_video_ids():
        if len(frames_of(vid)) < 104:
            continue
        sub = build_sub(vid, n_frames_of(vid), task_type="KIS", query_id=f"q_{vid}")
        assert validate_submission(sub) == [], f"{vid} báo lỗi nhầm"
        da_kiem += 1
        if da_kiem == 20:
            break
    assert da_kiem == 20, f"chỉ kiểm được {da_kiem} video, cần 20"
