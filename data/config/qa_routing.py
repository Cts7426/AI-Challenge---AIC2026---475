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
# "đếm" phải đứng TRƯỚC "ocr" khi câu hỏi thực sự hỏi số vật thể ("có mấy chiếc
# xe biển số xanh" — ưu tiên đếm, không phải đọc biển số). KHÔNG dùng riêng cụm
# "bao nhiêu": nó còn xuất hiện trong khối lượng, chiều dài, giá… mà bằng chứng
# nằm trong ASR/OCR, không phải object detector.
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
    # Chỉ các cụm có DANH TỪ vật thể mới được đi detector. Câu "bao nhiêu gam"
    # hoặc "dài bao nhiêu mét" rơi về text_first để tìm nguyên văn trong ASR/OCR.
    ("count", ("bao nhiêu người", "bao nhiêu chiếc", "bao nhiêu xe",
               "bao nhiêu con", "mấy người", "mấy chiếc", "mấy cái",
               "số lượng", "đếm"), False),
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


# ---------------------------------------------------------------- nhãn đối tượng
#
# `backend/tasks/qa.py::_object_count` đếm detection theo nhãn. Nhãn nó đem đi so
# đến từ `query_understanding.extract_constraints()` — LLM sinh DANH TỪ TIẾNG ANH
# TỰ DO, không hề bị ràng buộc vào 600 lớp OpenImages V4 của detector.
#
# Bản trước so bằng `==` chính xác nên "people" ≠ "Person", "cars" ≠ "Car" →
# `sum(...)` ra **0**, mà 0 lại KHÁC None nên `_try_shot` coi đó là đếm thành công
# và nộp thẳng answer "0". Câu "có bao nhiêu người" trả lời "0", với confidence
# tuyệt đối, vì `CLAUDE.md` §5.2 quy định "đếm → detector, KHÔNG hỏi VLM" nên
# đường này được tin không hỏi lại.
#
# Bảng dưới ưu tiên GIAO THÔNG và THỂ THAO — BTC đã công bố đó là nội dung chính
# của vòng sơ tuyển. Thiếu nhãn nào thì bổ sung ở đây, không sửa qa.py.
#
# Một từ khoá có thể ra NHIỀU nhãn: "người" trong ảnh có thể được detector gán
# Person / Man / Woman / Boy / Girl tuỳ tư thế — đếm gộp mới ra con số người ta
# nhìn thấy bằng mắt.
OBJECT_LABEL_ALIASES: dict[str, tuple[str, ...]] = {
    # người
    "person": ("Person", "Man", "Woman", "Boy", "Girl"),
    "people": ("Person", "Man", "Woman", "Boy", "Girl"),
    "human": ("Person", "Man", "Woman", "Boy", "Girl"),
    "man": ("Man", "Person"),
    "men": ("Man", "Person"),
    "woman": ("Woman", "Person"),
    "women": ("Woman", "Person"),
    "child": ("Boy", "Girl", "Person"),
    "children": ("Boy", "Girl", "Person"),
    "player": ("Person", "Man", "Woman"),
    "players": ("Person", "Man", "Woman"),
    # giao thông
    "car": ("Car",), "cars": ("Car",),
    "vehicle": ("Car", "Truck", "Bus", "Van"),
    "vehicles": ("Car", "Truck", "Bus", "Van"),
    "bus": ("Bus",), "buses": ("Bus",),
    "truck": ("Truck",), "trucks": ("Truck",),
    "motorcycle": ("Motorcycle",), "motorcycles": ("Motorcycle",),
    "motorbike": ("Motorcycle",), "motorbikes": ("Motorcycle",),
    "bike": ("Bicycle", "Motorcycle"), "bikes": ("Bicycle", "Motorcycle"),
    "bicycle": ("Bicycle",), "bicycles": ("Bicycle",),
    "traffic light": ("Traffic light",), "traffic lights": ("Traffic light",),
    "traffic sign": ("Traffic sign",), "traffic signs": ("Traffic sign",),
    "boat": ("Boat",), "boats": ("Boat",),
    "train": ("Train",), "trains": ("Train",),
    "airplane": ("Airplane",), "airplanes": ("Airplane",), "plane": ("Airplane",),
    # thể thao
    "ball": ("Ball", "Football"), "balls": ("Ball", "Football"),
    "football": ("Football", "Ball"), "soccer ball": ("Football", "Ball"),
    "helmet": ("Helmet",), "helmets": ("Helmet",),
}


def resolve_object_labels(label_en: str) -> tuple[str, ...]:
    """Nhãn LLM sinh tự do → các nhãn OpenImages nên đếm gộp.

    Không có trong bảng → trả về chính nó (viết hoa chữ đầu, đúng quy ước
    OpenImages). Chỗ gọi vẫn so không phân biệt hoa/thường, nên đây chỉ là đường
    lui hợp lý chứ không phải phép đoán.
    """
    key = " ".join(label_en.lower().split())
    if key in OBJECT_LABEL_ALIASES:
        return OBJECT_LABEL_ALIASES[key]
    return (label_en.strip().capitalize(),) if label_en.strip() else ()


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
