# tests/test_debug_ui.py — D2.1: kiểm màn hình Streamlit có VẼ ĐƯỢC không
#
# `debug_ui.py` chỉ vẽ, logic nằm ở labels/evidence/offline_search và đã có test
# riêng. Nhưng "chỉ vẽ" vẫn hỏng được: đổi tên một trường trong `BangChung` là trang
# nổ giữa lúc đang chấm nhãn, mà không test nào bắt.
#
# `AppTest` của Streamlit chạy THẬT kịch bản trong tiến trình pytest và thu lại
# exception — đủ để bắt đúng loại lỗi đó mà không cần mở trình duyệt.

from __future__ import annotations

import pytest

pytest.importorskip("streamlit", reason="app/requirements.txt chưa cài")

from streamlit.testing.v1 import AppTest  # noqa: E402

from app.debug_ui import query_id_cua  # noqa: E402

DUONG_DAN = "app/debug_ui.py"


def _chay() -> AppTest:
    return AppTest.from_file(DUONG_DAN, default_timeout=120).run()


# ------------------------------------------------------------------ query_id

def test_query_id_on_dinh_giua_cac_phien():
    """Nhãn của cùng một câu hỏi phải gom về một chỗ, kể cả sau khi tắt máy."""
    assert query_id_cua("thủ môn cản phá") == query_id_cua("thủ môn cản phá")


def test_query_id_bo_qua_khoang_trang_va_hoa_thuong():
    """Gõ thừa một dấu cách không được biến thành truy vấn khác — nhãn sẽ tách hai đống."""
    assert query_id_cua("  Thủ Môn cản phá  ") == query_id_cua("thủ môn cản phá")


def test_query_id_khac_nhau_cho_cau_khac_nhau():
    assert query_id_cua("thủ môn") != query_id_cua("hậu vệ")


# --------------------------------------------------------------- vẽ được không

def test_trang_ve_duoc_khong_loi():
    at = _chay()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert at.title[0].value == "UI debug — AIC 2026"


def test_khong_tu_chay_search_khi_chua_bam_nut():
    """Streamlit vẽ lại trang sau MỌI thao tác. Tự chạy search là bắt đợi 8 giây mỗi
    lần chạm bàn phím, kể cả lúc chỉ bấm nút chấm nhãn."""
    at = _chay()
    at.sidebar.text_area[0].set_value("thủ môn cản phá penalty").run()
    assert not at.exception
    assert any("Bấm **Tìm kiếm**" in i.value for i in at.info)


def test_hien_query_id_khi_da_go_truy_van():
    at = _chay()
    at.sidebar.text_area[0].set_value("thủ môn cản phá penalty").run()
    qid = query_id_cua("thủ môn cản phá penalty")
    assert any(qid in c.value for c in at.caption), "phải hiện query_id để biết nhãn gom vào đâu"


def test_bao_khi_chua_dat_ten_nguoi_cham(monkeypatch):
    """Nhãn không có tên người chấm thì sau này không truy ra ai chấm cái gì."""
    monkeypatch.setenv("AIC_LABELER", "unknown")
    at = _chay()
    assert any("AIC_LABELER" in w.value for w in at.sidebar.warning)


def test_bao_khi_chua_co_anh_keyframe():
    """Thiếu ảnh làm UI kém vui chứ không sai số nào — nhưng phải nói cho người dùng biết."""
    at = _chay()
    assert not at.exception
    # có ảnh thì không cần báo; chưa có thì phải báo
    from data.config.debug_ui import KEYFRAMES_DIR

    if not KEYFRAMES_DIR.is_dir():
        assert any("ảnh keyframe" in i.value for i in at.sidebar.info)


def test_du_5_o_bat_tat_nhanh():
    """Bật/tắt từng nhánh là công cụ chẩn đoán chính: tắt đi để xem nguồn nào gánh điểm."""
    at = _chay()
    ten = {c.label for c in at.sidebar.checkbox}
    assert {"vector", "metadata", "objects", "ocr", "asr"} <= ten


def test_co_o_chon_che_do_live_va_offline():
    at = _chay()
    lua_chon = set(at.sidebar.radio[0].options)
    assert lua_chon == {"live", "offline"}
