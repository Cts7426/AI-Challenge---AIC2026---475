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
    "asr": True,        # lời nói (mức ĐOẠN THỜI GIAN)
}

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
TRAKE_ORDER_BONUS = 1.5

# Mỗi sự kiện TRAKE lấy top bấy nhiêu shot khi search() riêng (KHÔNG nối chuỗi
# N sự kiện thành 1 câu — vi phạm giới hạn 77 token của CLIP, xem
# backend/tasks/trake.py). Rộng hơn top-10 video cuối cùng để video đúng mà
# chỉ khớp yếu 1-2 sự kiện vẫn có cơ hội lọt vào bảng gộp điểm.
TRAKE_EVENT_SEARCH_POOL = 200
