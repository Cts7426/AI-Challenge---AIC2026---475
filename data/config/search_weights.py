# data/config/search_weights.py — trọng số hợp nhất điểm khi search (Task 2.2)
#
# TODO: tune — các số dưới là điểm khởi đầu hợp lý, CHƯA tune trên data thật.
# Chỉnh ở đây, không sửa logic trong backend/retrieval/search.py.
#
# Trực giác đằng sau giá trị khởi đầu:
#   - vector (CLIP) là tín hiệu chính: hiểu ngữ nghĩa ảnh, phủ mọi query → 1.0
#   - objects chính xác khi query nhắc vật thể cụ thể, nhưng chỉ ~600 loại → 0.7
#   - ocr (khi có, Task 4.1): chữ trên màn hình cực đặc trưng (tên, tỉ số) → 0.6
#   - metadata mô tả CẢ video, không trỏ đúng khoảnh khắc → thấp nhất 0.4

FUSION_WEIGHTS = {
    "vector": 1.0,
    "objects": 0.7,
    "ocr": 0.6,
    "asr": 0.6,     # lời nói cực đặc trưng (bình luận, thuyết minh) — ngang ocr
    "metadata": 0.4,
}

# Mỗi nguồn lấy top_k * hệ số này làm ứng viên trước khi hợp nhất —
# rộng hơn top_k để keyframe mạnh ở nguồn phụ vẫn có cửa vào bảng cuối
CANDIDATE_MULTIPLIER = 3

# ASR join theo thời gian: đoạn nói [start, end] nới thêm ± pad này khi so với
# timestamp keyframe — lời bình thường lệch vài giây so với hình ảnh
ASR_TIME_PAD_MS = 2000

# Số đoạn ASR khớp nhất được quyền ĐỀ CỬ keyframe (tra Milvus theo khoảng
# thời gian). Cap lại để 1 query Milvus không phình filter vô hạn.
ASR_NOMINATE_SEGMENTS = 5
