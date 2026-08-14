# tests/test_qa_routing.py — C3.1: bảng định tuyến câu hỏi → loại bằng chứng
#
# Trọng tâm: THỨ TỰ luật trong ROUTING_RULES phải đúng ưu tiên đã ghi trong
# docstring của qa_routing.py — "đếm" phải thắng "ocr" (câu hỏi đếm hay chứa số).

from __future__ import annotations

from data.config.qa_routing import DEFAULT_EVIDENCE_TYPE, route_question


def test_dem_thang_ocr_khi_ca_hai_cung_xuat_hien():
    """'có mấy chiếc xe biển số xanh' vừa có tín hiệu đếm vừa có tín hiệu OCR —
    đếm phải thắng vì đó là ý chính câu hỏi (BUILD_TASKS: đếm → detector)."""
    evidence_type, _ = route_question("có mấy chiếc xe biển số xanh trong ảnh")
    assert evidence_type == "count"


def test_ocr_cho_cau_hoi_ten():
    evidence_type, needs_images = route_question("Tên quán ăn là gì?")
    assert evidence_type == "ocr"
    assert needs_images is False


def test_asr_cho_cau_hoi_loi_noi():
    evidence_type, _ = route_question("Bình luận viên nói gì khi cầu thủ ghi bàn?")
    assert evidence_type == "asr"


def test_visual_can_anh_ngay():
    evidence_type, needs_images = route_question("Áo cầu thủ có màu gì?")
    assert evidence_type == "visual"
    assert needs_images is True  # duy nhất loại BẮT BUỘC ảnh ngay từ đầu


def test_metadata_cho_cau_hoi_dia_diem():
    evidence_type, _ = route_question("Trận đấu diễn ra ở đâu?")
    assert evidence_type == "metadata"


def test_khong_khop_luat_nao_roi_ve_text_first():
    evidence_type, needs_images = route_question("Người phụ nữ đang làm gì?")
    assert evidence_type == DEFAULT_EVIDENCE_TYPE
    assert needs_images is False


def test_khong_dau_roi_ve_default_khong_crash():
    """Gõ thiếu dấu (thực tế lúc thi) không khớp từ khoá có dấu → về mặc định
    AN TOÀN (text-first), không crash, không route sai sang loại tốn kém hơn."""
    evidence_type, _ = route_question("mau gi vay")
    assert evidence_type == DEFAULT_EVIDENCE_TYPE
