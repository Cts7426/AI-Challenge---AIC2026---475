# data/config/text_vi_vector.py — R3.X4: nhánh tìm kiếm NGỮ NGHĨA tiếng Việt
#
# ===== Lỗ hổng nhánh này lấp =====
# Năm nhánh hiện có là: CLIP/SigLIP2 (tiếng Anh, qua bản dịch) + bốn nhánh BM25
# khớp TỪ KHOÁ. Không có chỗ nào hiểu nghĩa tiếng Việt. Query "người đàn ông
# chèo thuyền" không khớp đoạn ASR nói "anh ấy đang bơi ghe" — cùng nghĩa, khác
# chữ, BM25 mù hoàn toàn. Đây là lỗ hổng NĂNG LỰC, không phải chất lượng.
#
# ===== Trạng thái: ĐÃ ĐẤU NỐI, CHƯA CÓ DỮ LIỆU =====
# Nhánh chạy được ngay khi R3.X2 (Công Lý) encode xong đoạn ASR vào một
# collection Milvus. Trước đó `ENABLED = False` và bật lên sẽ báo lỗi rõ ràng
# chứ không im lặng trả rỗng — im lặng thì người vận hành tưởng nhánh đang chạy.
#
# ⚠️ 90/873 video KHÔNG có ASR. Nhánh này mù với những video đó — nó bổ sung,
# không thay thế nhánh hình ảnh.

# Bật/tắt. MẶC ĐỊNH TẮT: Q&A và TRAKE cũng gọi search(), bật ngầm là đổi hành vi
# của hai làn không phải của mình.
ENABLED = False

# Collection Milvus chứa vector đoạn ASR. R3.X2 đo hai ứng viên rồi chọn một:
#   `dangvantuan/vietnamese-embedding` — PhoBERT, 768 chiều, cửa sổ 512 token.
#       ⚠️ BẮT BUỘC `pyvi.ViTokenizer.tokenize()` trước khi encode. Bỏ bước này
#       thì model vẫn chạy, vector vẫn norm = 1, chỉ chất lượng tụt KHÔNG CẢNH BÁO.
#   `BAAI/bge-m3` — huấn luyện thẳng cho retrieval, đa ngữ, cửa sổ 8192, không
#       cần tách từ.
# Bảng của MERVIN đo STS (đối xứng) chứ không đo retrieval (bất đối xứng:
# truy vấn → tài liệu), nên dangvantuan đứng đầu STS là dấu hiệu, không phải
# bằng chứng — phải đo cả hai trên bộ đề thật.
COLLECTION = "asr_text_vi"

# Tên model để assert lúc nạp (bất biến 8: mọi artefact đi kèm meta và assert khi
# load). Encoder và collection LUÔN đi theo cặp — dùng model này với index kia
# thì Milvus vẫn trả top-k điểm trông bình thường mà sai toàn bộ.
MODEL_NAME = "dangvantuan/vietnamese-embedding"
EMBEDDING_DIM = 768

# Có phải model họ PhoBERT không → quyết định có chạy ViTokenizer trước khi encode.
CAN_TACH_TU = True
