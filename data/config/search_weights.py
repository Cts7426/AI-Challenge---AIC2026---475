# data/config/search_weights.py — tham số hợp nhất kết quả search (A2.2)
#
# ⚠️ KHÔNG còn trọng số cộng điểm. Từ A2.2 fusion dùng RRF:
#       score(d) = Σ_nhánh 1 / (RRF_K + rank_nhánh(d))
#
# Vì sao bỏ weighted-sum (cách cũ) để đổi sang RRF?
#   Weighted-sum cộng ĐIỂM, mà điểm mỗi nhánh khác thang hoàn toàn (COSINE
#   [-1,1] vs BM25 không chặn trên) → phải chuẩn hoá, mà chuẩn hoá lại phụ
#   thuộc phân bố của đúng lần query đó. RRF chỉ cộng THỨ HẠNG nên miễn nhiễm:
#   nhánh nào cũng chỉ nói được "cái này tôi xếp thứ mấy", không cãi nhau về thang.
#   Hệ quả thực tế: hết cần tune trọng số — thứ mà nhóm nhỏ không có thời gian làm.
#
# RRF_K = 60 là giá trị chuẩn trong bài báo gốc (Cormack 2009) và cũng là mặc
# định của Elasticsearch/Milvus. K lớn → làm phẳng khác biệt giữa các hạng đầu
# (an toàn hơn khi một nhánh hay sai); K nhỏ → tin hạng 1 mạnh hơn.

RRF_K = 60

# Bật/tắt từng nhánh. Tắt = nhánh đó không chạy và không đóng góp hạng nào.
# Dùng để đo đóng góp thật của mỗi nhánh (tắt đi, xem điểm rớt bao nhiêu).
BRANCHES = {
    "vector": True,     # CLIP trên Milvus — nhánh lõi
    "metadata": True,   # BM25 title/description/keywords (mức VIDEO)
    "objects": True,    # nhãn OpenImages (mức KEYFRAME)
    "ocr": True,        # chữ trên hình (mức KEYFRAME)
    "asr": True,        # lời thoại tiếng Việt (mức ĐOẠN THỜI GIAN)
}

# Trọng số RRF cho từng nhánh (Weighted RRF).
# Các nhánh nhiễu như OCR/ASR thường sinh ra nhiều kết quả ảo do khớp từng từ,
# trong khi Vector (CLIP) mới là giá trị cốt lõi. Cần áp trọng số để Vector không bị chìm.
BRANCH_WEIGHTS = {
    "vector": 1.0,
    "objects": 0.7,
    "ocr": 0.6,
    "asr": 0.6,
    "metadata": 0.4,
}

# ----------------- Gom nhóm theo shot (B0.1) -----------------
# Mỗi nhánh lấy top_k * hệ số này làm ứng viên. Rộng hơn top_k để keyframe mạnh
# ở nhánh phụ vẫn lọt vào bảng hợp nhất; rộng quá thì tốn thời gian vô ích.
CANDIDATE_MULTIPLIER = 5

# Gom kết quả về SHOT, mỗi shot giữ 1 keyframe điểm cao nhất.
# Vì sao: 3–4 keyframe liền nhau trong cùng một shot là cùng một cảnh — chiếm
# chỗ của nhau trên màn hình mà không thêm thông tin gì cho người duyệt.
GROUP_BY_SHOT = True

# ASR join theo thời gian: đoạn nói [start, end] nới ± ngần này khi so với
# timestamp keyframe — lời bình thường lệch hình vài giây.
ASR_TIME_PAD_MS = 2000

# Số đoạn ASR khớp nhất được quyền ĐỀ CỬ keyframe (tra Milvus theo khoảng thời
# gian). Cap lại để 1 query Milvus không phình filter vô hạn.
ASR_NOMINATE_SEGMENTS = 5

# --------------------------------------------------------------- TRAKE (C3.2)

# Hệ số THƯỞNG (nhân điểm video) khi các sự kiện của TRAKE khớp trong video theo
# ĐÚNG trình tự thời gian đề bài mô tả. Đặt ở config chứ không hardcode trong
# backend/tasks/trake.py vì đây là chiến thuật cần tune trên dev_set (giống mọi
# trọng số khác trong file này), không phải hằng số thuật toán.
#
# ⚠️ Chỉ dùng để XẾP LẠI HẠNG trong nhóm video đã có điểm hợp lý — KHÔNG dùng
# làm ngưỡng lọc cứng: 1 video đúng nhưng có 1 sự kiện bị đảo thứ tự (nhiễu tìm
# kiếm) vẫn phải còn cơ hội lọt top-10, chỉ là xếp thấp hơn video khớp thứ tự
# hoàn hảo. Sai video ở TRAKE là 0 điểm tuyệt đối (docs/contest.md) — loại nhầm
# 1 video đúng khỏi top-10 vì phạt quá tay còn tệ hơn xếp nó hạng 8 thay vì hạng 2.
TRAKE_ORDER_BONUS = 5.0

# Mỗi sự kiện TRAKE lấy top bấy nhiêu shot khi search() riêng (KHÔNG nối chuỗi
# N sự kiện thành 1 câu — vi phạm giới hạn 77 token của CLIP, xem
# backend/tasks/trake.py). Rộng hơn top-10 video cuối cùng để video đúng mà
# chỉ khớp yếu 1-2 sự kiện vẫn có cơ hội lọt vào bảng gộp điểm.
TRAKE_EVENT_SEARCH_POOL = 1000

# Trong TỪNG video ứng viên, mỗi sự kiện giữ lại tối đa bấy nhiêu khung hình
# điểm cao nhất làm ứng viên cho DP xếp chuỗi tăng dần (backend/tasks/trake.py
# ::_align_events_in_video). >1 (khác bản cũ chỉ giữ đúng 1) để DP có phương án
# B khi ứng viên điểm cao nhất của một sự kiện phá thứ tự — không phải "+1
# nudge" giả tạo lên bằng chứng thật. DP là O((N·K)²) nên K lớn vẫn rẻ; 6 đủ
# rộng cho N TRAKE thường gặp (2-6 sự kiện) mà không làm chậm search.
TRAKE_CANDIDATES_PER_EVENT = 6

# Khoảng cách FRAME tối thiểu giữa 2 vị trí LIÊN TIẾP mà DP chọn (backend/tasks/
# trake.py::_align_events_in_video). Đo thật: CLIP không phân biệt nổi "đổ
# muối vào nước" với "đổ rau vào nước" bằng caption ngắn — cả hai ra CÙNG 1
# khung hình top-1 (cách nhau ~19 frame), khiến DP ghép chúng thành "2 sự kiện"
# dù đó chỉ là 1 khoảnh khắc CLIP nhầm lẫn. Ràng buộc này không sửa được lỗi
# CLIP (cần "tầng tinh" — docs/contest.md), chỉ ép DP bỏ qua tổ hợp chụm 1 chỗ.
#
# TODO: BTC/D4.1 — chưa biết fps thật của video (docs/contest.md), nên đây là
# số frame THÔ, chưa quy đổi ra giây. 30 là ước lượng "đủ để không phải cùng 1
# khoảnh khắc nhầm lẫn" nhưng "đủ nhỏ để không loại nhầm 2 hành động cắt nhanh
# thật" — cần tune trên dev_set khi có video có timestamp thật để đối chiếu.
TRAKE_MIN_FRAME_GAP = 30


# ============================ Q&A — ứng viên nhánh TEXT (A-fix 20/08) ============
#
# Vì sao cần: sau khi thay CLIP mock bằng features THẬT (20/08), điểm KIS tăng
# 10,6 lần nhưng Q&A tụt 0,360 → 0,160. Mổ QA05 ("video nhắc tới bến phà nào
# trên sông Mê Kông") thấy rõ cơ chế:
#
#   · bằng chứng nằm trong ASR (lời thoại đọc tên bến phà)
#   · CLIP thật làm đúng việc của nó: kéo lên các cảnh TRÔNG GIỐNG phà
#   · video đúng tụt từ hạng 3 (thời mock) xuống hạng 16
#   · `qa_pipeline` chỉ đem MAX_SHOTS_TRIED = 3 shot đầu đi suy luận
#   → LLM đọc ASR của video KHÁC, trả lời "Phà Châu Giang" thay vì "bến phà
#     Vàm Cống". Sai answer = 0 điểm cho CẢ 100 dòng (cửa tử thứ hai của Q&A).
#
# Nói gọn: hỏi bằng TAI, tìm bằng MẮT. Thời vector còn là nhiễu, nhánh text vô
# tình nắm quyền xếp hạng nên Q&A đúng — đó là may, không phải thiết kế.
#
# Đo thật trên 5 câu QA (20/08), hạng của video ĐÚNG:
#     câu    đủ nhánh   chỉ nhánh text
#     QA01       7            6
#     QA02       4            1
#     QA03       1            1
#     QA04       5            1
#     QA05      16            3        ← câu bản vá này nhắm tới
#
# Cách vá: chạy THÊM 1 lần search chỉ trên nhánh text rồi NỐI ứng viên mới vào
# CUỐI danh sách gốc. Không hợp nhất lại, không cắt lại top-K, không đổi thứ tự
# ứng viên cũ — nên nhánh KIS/TRAKE không thể bị ảnh hưởng kể cả khi cờ này sai.
QA_TEXT_FALLBACK_ENABLED = True

# Số ứng viên nối thêm. Nhỏ hơn NHIỀU so với top_k chính (100) là có chủ đích:
# đây là cửa hậu cho vài shot mà nhánh text tin tưởng, không phải một bảng xếp
# hạng thứ hai. 5 đủ để QA05 (hạng 3 theo nhánh text) lọt vào.
#
# ⚠️ Nếu QA01–04 TỤT sau bản vá thì GIẢM số này, đừng tăng — tụt nghĩa là ứng
# viên nối thêm đang chen vào bước suy luận và làm nhiễu, không phải thiếu ứng viên.
QA_TEXT_FALLBACK_QUOTA = 5

# Loại câu hỏi được hưởng bản vá — đúng những loại mà bằng chứng nằm trong CHỮ
# hoặc TIẾNG, không nằm ở hình. "visual" và "count" cố tình đứng ngoài: câu về
# màu sắc/hình dáng thì CLIP mới là nguồn đúng, còn đếm thì đi đường detector.
QA_TEXT_FALLBACK_ROUTES = ("ocr", "asr", "metadata", "text_first")
