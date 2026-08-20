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
    # tầng fuzzy đổi số hiệu 3 → 4 từ 16/08 (chèn thêm tầng "chứa nhau" ở vị trí 3)
    match, tier = answer_matches("Highlands Coffee", "Higlands Coffee", [])
    assert match and tier == 4


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
    """⚠️ SIẾT 16/08. Bản trước chỉ assert `len(answer) <= len("khoảng 5 người")`
    — điều đó ĐÚNG kể cả khi gom nhóm thất bại hoàn toàn, nên test vẫn xanh trong
    khi `majority_answer` trả về phiếu = 1 và `qa.py` bỏ nguyên shot. Comment cũ
    còn tự thừa nhận "nên gom được qua fuzzy/equivalent tuỳ ratio", tức người viết
    cũng không chắc. Test không chốt được hành vi thì không phải test.

    Giờ chốt cả hai: gom đủ 3 phiếu, VÀ đại diện là chuỗi ngắn nhất.
    """
    answer, votes = majority_answer(["khoảng 5 người", "5", "5 người"])
    assert votes == 3, "ba cách nói cùng một con số phải về CÙNG một nhóm"
    assert answer == "5", "đại diện phải là câu ngắn nhất (BUILD_TASKS C3.1)"


def test_majority_gom_duoc_dung_vi_du_trong_docstring():
    """Docstring của `majority_answer` hứa gom "5" / "5 người" / "khoảng 5".
    Đo 16/08: trước khi thêm tầng 3 (chứa nhau) thì phiếu = 1 → `_try_shot` trả
    None → thử hết 3 shot → `qa_pipeline` raise → câu Q&A 0 điểm."""
    assert majority_answer(["5 người", "5", "khoảng 5"]) == ("5", 3)


# ---------------------------------------- tầng 3: chứa nhau theo TẬP TỪ

def test_khop_khi_cau_ngan_nam_tron_trong_cau_dai():
    assert answer_matches("5", "5 người", [])[0]
    assert answer_matches("5 người", "5", [])[0]


def test_chua_nhau_KHONG_pha_ve_chan_ten_rieng():
    """Hai tên cùng số từ, khác một từ → không bên nào là tập con của bên kia."""
    assert not answer_matches("Nguyễn Văn A", "Nguyễn Văn B", [])[0]


# ⚠️ Bản ĐẦU của tầng 3 (sáng 16/08) chỉ kiểm tập con thuần, và mọi câu trả lời
# BỊ CẮT CỤT đều được chấm đúng. Sáu test dưới khoá lại chỗ đó — chúng đỏ với bản
# đầu, xanh với bản đã siết (phần thừa phải toàn từ đệm).

def test_ten_rieng_cut_phai_TRUOT():
    assert not answer_matches("Nguyễn", "Nguyễn Văn An", [])[0]
    assert not answer_matches("Highlands", "Highlands Coffee", [])[0]


def test_thieu_con_so_phai_TRUOT():
    """Số KHÔNG BAO GIỜ là từ đệm — "người" không thay được cho "5 người"."""
    assert not answer_matches("người", "5 người", [])[0]


def test_thieu_tu_phan_loai_phai_TRUOT():
    assert not answer_matches("xe", "xe máy", [])[0]


def test_tu_dem_thi_van_khop():
    assert answer_matches("5", "5 người", [])[0]
    assert answer_matches("khoảng 5", "5", [])[0]
    assert answer_matches("xanh", "màu xanh", [])[0]
    assert answer_matches("Hà Nội", "thành phố Hà Nội", [])[0]


def test_chua_nhau_so_theo_TU_khong_theo_substring():
    """`"5" in "15 người"` đúng về chuỗi nhưng sai về nghĩa — phải so theo từ."""
    assert not answer_matches("5", "15 người", [])[0]


def test_answer_rong_khong_khop_moi_thu():
    """Tập rỗng là tập con của mọi tập — không chặn thì answer rỗng khớp tất cả."""
    assert not answer_matches("", "bất kỳ câu nào", [])[0]


# ------------------------------------ tầng 1: dấu câu KHÔNG được dính hai bên

def test_normalize_khong_dinh_hai_ben_dau_cau():
    """`CLAUDE.md` §5.2: "số/tỉ số → OCR" là một dạng Q&A chính."""
    assert normalize_text("2-1") == "2 1"
    assert normalize_text("21/08") == "21 08"
    assert normalize_text("10-0") == "10 0"


def test_ti_so_KHONG_va_cham_voi_so_nguyen():
    """Bug cũ: "2-1" → "21" nên tỉ số 2-1 bị chấm ĐÚNG cho đáp án "21".
    Đây là chấm SAI, không phải bỏ sót."""
    assert not answer_matches("2-1", "21", [])[0]
    assert not answer_matches("10-0", "100", [])[0]


def test_ti_so_van_khop_bien_the_co_khoang_trang():
    assert answer_matches("2-1", "2 - 1", [])[0]


def test_khong_fuzzy_tren_dap_an_thuan_so():
    """Fuzzy dung túng lỗi chính tả trong CHỮ, nhưng số thì sai 1 chữ số là đáp
    án khác hẳn. Đo 16/08: "10 0" vs "100" ratio 0.857 ≥ 0.85 nên vẫn lọt qua
    tầng fuzzy dù tầng 1 đã sửa — phải chặn hẳn fuzzy cho chuỗi thuần số."""
    assert not answer_matches("10-0", "100", [])[0]
    assert not answer_matches("21", "2 1", [])[0]


def test_so_van_khop_duoc_qua_cac_tang_an_toan():
    """Chặn fuzzy KHÔNG được làm số mất đường khớp hợp lệ."""
    assert answer_matches("5", "5", [])[0]          # tầng 1
    assert answer_matches("5", "năm", [])[0]        # tầng 2
    assert answer_matches("5", "5 người", [])[0]    # tầng 3


def test_majority_mot_cau_tra_loi():
    assert majority_answer(["5"]) == ("5", 1)


# ============================ dấu phân cách nghìn (20/08) ============================
# Bối cảnh: QA04 nộp "2.970 m", chuẩn hoá cũ ra "2 970 m" — ba token, không còn
# là một con số. Hậu quả nặng nhất không phải chấm điểm mà là majority_answer():
# 3 lần sinh viết cùng một số ba kiểu → ba nhóm một phiếu → qa.py bỏ shot → 0 điểm.

def test_gop_dau_cham_phan_cach_nghin():
    assert normalize_text("2.970 m") == "2970 m"
    assert normalize_text("1.234.567") == "1234567"


def test_gop_dau_phay_phan_cach_nghin():
    assert normalize_text("1,000") == "1000"


def test_KHONG_gop_dau_thap_phan():
    """Nhóm sau dấu chỉ 1 chữ số → thập phân, không phải phân cách nghìn."""
    assert normalize_text("2969.4m") == "2969 4m"
    assert normalize_text("2,5 kg") == "2 5 kg"


def test_KHONG_gop_ngay_thang():
    """⚠️ Chống hồi quy: nhóm 2 chữ số là ngày tháng. Gộp nhầm thì "20.08.2026"
    thành "20082026" và hết khớp với "20/08/2026" ghi ở bản ghi khác."""
    assert normalize_text("20.08.2026") == "20 08 2026"
    assert answer_matches("20.08.2026", "20/08/2026", [])[0]


def test_KHONG_gop_ti_so():
    """Tỉ số không phải số nghìn — "2-1" vẫn phải là hai token."""
    assert normalize_text("2-1") == "2 1"
    assert not answer_matches("2-1", "21", [])[0]


def test_vote_gom_duoc_cac_cach_viet_cung_mot_so():
    """Đây là lý do THẬT SỰ phải sửa: self-consistency n=3 chia phiếu ảo."""
    winner, votes = majority_answer(["2.970 m", "2970m", "2970 mét"])
    assert votes == 3, "ba cách viết cùng một số phải về cùng một nhóm"
    assert winner == "2970m", "phải lấy câu ngắn nhất trong nhóm thắng"


def test_lam_tron_van_KHONG_duoc_tu_khop():
    """2970 và 2969.4 là HAI con số khác nhau. Bộ khớp không được tự quyết định
    dung sai làm tròn — đó là việc của người ra đề, khai qua answer_variants."""
    assert not answer_matches("2.970 m", "2969.4m", [])[0]
    assert answer_matches("2.970 m", "2969.4m", ["2970m"])[0]
