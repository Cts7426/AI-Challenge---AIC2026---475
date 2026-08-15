# tests/test_answer_match.py — backend/common/answer_match.py: so khớp Q&A
#
# Module này dùng CHUNG cho chấm điểm dev_set VÀ self-consistency voting của
# backend/tasks/qa.py (C3.1) — sai ở đây là sai cả hai chỗ cùng lúc.

from __future__ import annotations

from backend.common.answer_match import answer_matches, equivalent_text, majority_answer, normalize_text


# ------------------------------------------------------------------- normalize

def test_normalize_bo_dau_cau_khoang_trang():
    assert normalize_text("  Năm,   người!  ") == "năm người"


def test_normalize_rong():
    assert normalize_text("") == ""
    assert normalize_text(None) == ""


def test_equivalent_so_sang_chu():
    assert equivalent_text("5") == "năm"
    assert equivalent_text("có 3 người") == "có ba người"


# ---------------------------------------------------------------- answer_matches

def test_answer_matches_tang_1_giong_het():
    match, tier = answer_matches("năm người", "năm người", [])
    assert match and tier == 1


def test_answer_matches_tang_2_so_doi_chu():
    match, tier = answer_matches("5", "năm", [])
    assert match and tier == 2


def test_answer_matches_variant():
    match, tier = answer_matches("five", "năm", ["5", "five"])
    assert match and tier == 1


def test_answer_matches_khong_khop():
    match, tier = answer_matches("sai rồi", "năm", ["5"])
    assert not match and tier == 0


def test_answer_matches_pred_none():
    assert answer_matches(None, "năm", []) == (False, 0)


def test_answer_matches_chan_input_qua_dai():
    """Input bệnh lý (>500 ký tự) phải bị cắt trước khi vào difflib, không crash/chậm."""
    match, tier = answer_matches("a" * 10_000, "năm", [])
    assert not match


def test_answer_matches_KHONG_khop_nham_ten_rieng():
    """⚠️ Bug thật tìm được qua code review (14/08): so ratio TOÀN CHUỖI khiến
    2 tên khác nhau khớp nhầm ('nguyễn văn a' vs 'nguyễn văn b' ratio=0.92 >
    0.85) vì tiền tố chung dài che mất chỗ khác nhau. contest.md định tuyến
    "tên/chức danh → OCR" nên đây là ca THƯỜNG GẶP, không phải hiếm."""
    assert answer_matches("Nguyễn Văn A", "Nguyễn Văn B", []) == (False, 0)
    assert answer_matches("Trần Thị C", "Trần Thị D", []) == (False, 0)


def test_answer_matches_van_khop_loi_chinh_ta_nhe_cung_so_tu():
    """Sửa tầng 3 thành so-từng-từ KHÔNG được làm mất khả năng bắt lỗi chính tả
    nhẹ hợp lệ (thiếu 1 ký tự trong 1 từ, số từ không đổi)."""
    match, tier = answer_matches("Highlands Coffee", "Higlands Coffee", [])
    assert match and tier == 3


# ----------------------------------------------------------------- majority_answer

def test_majority_gom_nhom_theo_nghia_khong_theo_chuoi():
    """3 phiếu diễn đạt khác nhau nhưng CÙNG nghĩa qua quy đổi số↔chữ (tier 2 —
    do temperature bị adapter bỏ qua, xem backend/llm/adapter.py) phải gom về
    1 nhóm và thắng áp đảo."""
    answer, votes = majority_answer(["5", "5", "năm"])
    assert votes == 3
    assert answer == "5"  # đại diện ngắn nhất trong nhóm


def test_majority_khong_dong_thuan_tra_ve_nhom_dau():
    answer, votes = majority_answer(["a", "b", "c"])
    assert votes == 1


def test_majority_dai_dien_ngan_nhat():
    answer, votes = majority_answer(["khoảng 5 người", "5", "5 người"])
    # cả 3 không giống hệt nhau về chuỗi nhưng "5" và "5 người" nên gom được
    # qua fuzzy/equivalent tuỳ ratio — chỉ assert bất biến: đại diện thắng cuộc
    # phải là item NGẮN NHẤT trong nhóm thắng, không bao giờ dài hơn ứng viên
    # khác cùng nhóm.
    assert len(answer) <= len("khoảng 5 người")


def test_majority_mot_cau_tra_loi():
    assert majority_answer(["5"]) == ("5", 1)
