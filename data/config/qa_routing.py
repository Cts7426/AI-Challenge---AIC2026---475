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
    # ⚠️ "asr" phải đứng TRƯỚC "ocr" (R3.Q4, 02/09). Các cụm chỉ-nguồn-lời-nói
    # ("theo lời thoại", "được nhắc đến") là bằng chứng MẠNH về NGUỒN, trong khi
    # "tên " chỉ nói về KIỂU câu trả lời — một câu có cả hai ("Nhà văn được nhắc
    # đến trong đoạn này tên gì?", DRESS_QA_01) thì nguồn thắng kiểu. Bản trước
    # để "ocr" trước nên 5/5 câu dress25 rơi vào OCR-ưu-tiên trong khi câu trả
    # lời nằm trong lời thoại.
    ("asr", ("lời thoại", "theo lời", "được nhắc đến", "nhắc đến",
             "nói gì", "nói rằng", "phát biểu", "hô to", "bình luận viên",
             "câu nói", "lời bài hát", "cho biết", "chia sẻ", "kể lại",
             "được giới thiệu", "giới thiệu"), False),
    # CLAUDE.md §5.2: "tên/chức danh → OCR · số/tỉ số → OCR". Bản trước thiếu
    # hẳn nhánh SỐ ĐỌC TRÊN HÌNH — "con số hiển thị cuối cùng trên cân"
    # (query-p1-3-qa) và "con số được ghi trên biển báo" (query-p1-9-qa) đều
    # không khớp luật nào và rơi về text_first.
    ("ocr", ("tên ", "chức danh", "biển số", "biển báo", "biển hiệu",
             "bảng hiệu", "logo", "dòng chữ", "chữ trên", "tỉ số", "số áo",
             "kết quả trận", "bảng điện tử", "con số", "chỉ số",
             "hiển thị", "ghi trên", "ghi ở", "màn hình"), False),
    ("metadata", ("địa điểm", "ở đâu", "nơi nào", "thành phố nào", "quốc gia nào"), False),
    ("visual", ("màu gì", "màu sắc", "hình dáng", "kiểu dáng"), True),
]

# Câu hỏi không khớp luật nào → thử bằng chứng TEXT (OCR+ASR+metadata) trước,
# chỉ thêm ảnh khi text-only trả confidence thấp. Đây là mặc định AN TOÀN —
# đúng chiến thuật "Text-first" đã chốt ở Phase 2 (tiết kiệm token, VLM chỉ khi
# thật sự cần).
DEFAULT_EVIDENCE_TYPE = "text_first"


# ------------------------------------------------- R3.Q4: route → ưu tiên nguồn
#
# Vì sao cần bảng này: `route_question()` / planner đã kết luận câu hỏi nên tin
# nguồn nào, nhưng TRƯỚC 02/09 kết luận đó KHÔNG hề tới được prompt suy luận.
# `backend/tasks/qa.py::_build_prompt` đổ mọi bằng chứng vào prompt theo một thứ
# tự CỐ ĐỊNH (metadata → OCR → ASR), ngang hàng nhau, không nói nguồn nào đáng
# tin hơn. Hệ quả im lặng: câu "Theo lời thoại, giá tàu lá là bao nhiêu?"
# (DRESS_QA_04) được đưa metadata video lên đầu prompt, kèm OCR mà đo được phần
# lớn là nhiễu watermark ("htv online", slide cạnh shot — xem ghi chú R3.Q2 đầu
# `qa.py`: 136/140 shot có OCR khác rỗng nhưng gần như không có bằng chứng thật).
#
# Bảng dưới CHỈ đổi THỨ TỰ trình bày + nhãn "nguồn chính" trong prompt. Nó KHÔNG
# lọc bỏ nguồn nào — loại hẳn nguồn phụ sẽ biến route sai (regex/planner đoán
# nhầm) từ "mất ưu tiên" thành "mất bằng chứng", tức đổi một lỗi nhẹ lấy một lỗi
# im lặng nặng hơn.
EVIDENCE_PRIORITY: dict[str, tuple[str, ...]] = {
    "ocr":        ("ocr", "asr", "metadata"),
    "asr":        ("asr", "ocr", "metadata"),
    "metadata":   ("metadata", "asr", "ocr"),
    # Detector đã trượt mới tới LLM (xem NO_IMAGE_ESCALATION_ROUTES): số đọc được
    # trên hình đáng tin hơn lời bình luận.
    "count":      ("ocr", "asr", "metadata"),
    "visual":     ("ocr", "asr", "metadata"),
    "text_first": ("ocr", "asr", "metadata"),
}

# Nhãn tiếng Việt hiển thị trong prompt cho từng nguồn.
EVIDENCE_SOURCE_LABELS: dict[str, str] = {
    "ocr": "Chữ đọc được trên hình (OCR)",
    "asr": "Lời thoại quanh khoảnh khắc (ASR, ±3s)",
    "metadata": "Metadata video (tiêu đề/mô tả cấp VIDEO, không riêng khoảnh khắc)",
}


# ------------------------------------ R3.Q4: route nào được leo thang sang ảnh
#
# `CLAUDE.md` §5.2 và docstring "count" ở đầu file này viết là "đếm → detector,
# TUYỆT ĐỐI không hỏi VLM". Trước 02/09 câu đó chỉ đúng một nửa: `_try_shot` quả
# thật không gửi ảnh NGAY (`route_question` trả needs_images=False cho "count"),
# nhưng khi detector trượt (`_object_count` trả None — nhãn LLM sinh không khớp
# 600 lớp OpenImages, ca rất thường gặp) thì luồng rơi xuống `_infer_legacy` /
# `_infer_two_stage`, và ở đó hễ confidence text < LOW_CONFIDENCE là gọi thẳng
# `collect_evidence(..., needs_images=True)` → VLM đếm bằng mắt. Không exception,
# không cảnh báo, và answer sai của VLM lại thường kèm confidence cao.
#
# Route nằm ngoài tập này thì KHÔNG được leo thang ảnh; vẫn được hỏi LLM bằng
# bằng chứng TEXT (OCR/ASR/metadata có thể ghi thẳng con số) — cấm là cấm cho
# VLM NHÌN ẢNH mà đếm, không phải cấm suy luận.
NO_IMAGE_ESCALATION_ROUTES = frozenset({"count"})


def evidence_order(evidence_type: str) -> tuple[str, ...]:
    """Route → thứ tự nguồn bằng chứng đưa vào prompt (nguồn chính đứng đầu)."""
    return EVIDENCE_PRIORITY.get(evidence_type, EVIDENCE_PRIORITY[DEFAULT_EVIDENCE_TYPE])


def allows_image_escalation(evidence_type: str) -> bool:
    """Route này có được phép leo thang sang ảnh khi bằng chứng text yếu không?

    Chỉ "count" bị cấm (CLAUDE.md §5.2). Route lạ/rỗng được coi là text_first —
    mặc định AN TOÀN theo nghĩa không mất bằng chứng; muốn cấm thì phải khai báo
    tường minh ở trên.
    """
    return evidence_type not in NO_IMAGE_ESCALATION_ROUTES


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
