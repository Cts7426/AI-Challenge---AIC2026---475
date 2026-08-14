# data/config/qa_routing.py — C3.1: bảng định tuyến câu hỏi Q&A → loại bằng chứng
#
# Vì sao rule-based (từ khoá) chứ không hỏi llm() để định tuyến?
# → Route chỉ quyết định NGUỒN BẰNG CHỨNG nào đáng tin nhất, không cần suy luận
#   sâu — hỏi LLM cho việc này là thêm 1 vòng gọi mạng có độ trễ + tiền, cho một
#   quyết định mà 1 phép match từ khoá trả lời được ngay. Regex sai thì text-first
#   fallback (data/config/qa_routing.py::DEFAULT_EVIDENCE_TYPE) vẫn thử được OCR/
#   ASR/metadata trước khi phải dùng VLM, nên route sai không làm mất bằng chứng.
#
# Thứ tự trong ROUTING_RULES LÀ ưu tiên: khớp luật nào trước, dùng luật đó —
# "đếm" phải đứng TRƯỚC "ocr" vì câu hỏi đếm cũng hay chứa số ("có mấy chiếc xe
# biển số xanh" — ưu tiên đếm, không phải đọc biển số).
#
# ⚠️ evidence_type "count" KHÔNG được gọi VLM đếm bằng mắt (BUILD_TASKS C3.1:
# "đếm → detector, KHÔNG hỏi VLM") — VLM đếm người/vật trong ảnh sai rất thường
# xuyên khi số lượng > 4-5. backend/tasks/qa.py phải route case này sang đếm
# bằng ES objects index (FasterRCNN detections), không đưa ảnh vào llm().
#
# GIỚI HẠN ĐÃ BIẾT: objects index là detection TỪNG FRAME riêng lẻ, không có
# tracker xuyên frame (CLAUDE.md — không cài package tracking). Đếm "bao nhiêu
# người" lấy max/mode qua các frame trong shot vẫn có thể sai khi người ra/vào
# khung hình hoặc bị che khuất. Chấp nhận sai số này ở v1, ghi log confidence
# thấp khi số đếm dao động mạnh giữa các frame trong cùng shot.

from __future__ import annotations

# Các loại bằng chứng qa.py biết xử lý. "count" đi thẳng ES objects, không qua
# llm() với ảnh. Còn lại đều là bằng chứng TEXT trước — visual là loại duy nhất
# buộc phải có ảnh ngay từ đầu (câu hỏi về màu sắc, hình dáng thị giác thuần).
EVIDENCE_TYPES = ("count", "ocr", "asr", "metadata", "visual", "text_first")

# (evidence_type, từ khoá nhận diện, bắt buộc ảnh ngay từ đầu?)
# Khớp bằng substring trên câu hỏi đã lowercase — không cần bỏ dấu vì từ khoá
# tiếng Việt ở đây luôn viết có dấu, người dùng gõ thiếu dấu thì rơi về
# DEFAULT_EVIDENCE_TYPE (text_first) — vẫn đúng, chỉ mất ưu tiên nguồn.
ROUTING_RULES: list[tuple[str, tuple[str, ...], bool]] = [
    ("count", ("bao nhiêu", "mấy người", "mấy chiếc", "số lượng", "đếm"), False),
    ("ocr", ("tên ", "chức danh", "biển số", "logo", "dòng chữ",
             "tỉ số", "số áo", "kết quả trận", "bảng điện tử"), False),
    ("asr", ("nói gì", "nói rằng", "phát biểu", "hô to", "bình luận viên",
             "câu nói", "lời bài hát"), False),
    ("metadata", ("địa điểm", "ở đâu", "nơi nào", "thành phố nào", "quốc gia nào"), False),
    ("visual", ("màu gì", "màu sắc", "hình dáng", "kiểu dáng"), True),
]

# Câu hỏi không khớp luật nào → thử bằng chứng TEXT (OCR+ASR+metadata) trước,
# chỉ thêm ảnh khi text-only trả confidence thấp. Đây là mặc định AN TOÀN —
# đúng chiến thuật "Text-first" đã chốt ở Phase 2 (tiết kiệm token, VLM chỉ khi
# thật sự cần).
DEFAULT_EVIDENCE_TYPE = "text_first"


def route_question(question_vi: str) -> tuple[str, bool]:
    """Câu hỏi (phần "cần trả lời", KHÔNG phải phần "sự kiện") → (evidence_type, cần_ảnh_ngay).

    Luật nào đứng trước trong ROUTING_RULES thắng — xem docstring đầu file vì sao
    thứ tự quan trọng (đếm phải thắng ocr).
    """
    q = question_vi.lower()
    for evidence_type, keywords, needs_images in ROUTING_RULES:
        if any(kw in q for kw in keywords):
            return evidence_type, needs_images
    return DEFAULT_EVIDENCE_TYPE, False
