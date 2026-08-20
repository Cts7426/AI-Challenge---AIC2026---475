# data/config/qa_evaluation.py — chính sách đo và đóng gói câu trả lời Q&A.
#
# BTC mô tả mâu thuẫn: một mục ghi chấm theo ngữ nghĩa, mục khác ghi so chuỗi
# chính xác. Giữ hai chế độ tách bạch để không ép production chọn một giả định
# chưa được xác nhận. `semantic` là hành vi đo hiện tại, nên mọi caller cũ giữ
# nguyên kết quả; `exact` chỉ là thước phụ và không được dùng cho majority vote.

from __future__ import annotations

# Các chế độ bộ đo hiểu. Đặt ở config thay vì rải chuỗi trong dev_set để BTC xác
# nhận luật nào thì đổi một chỗ, không sửa thuật toán retrieval.
QA_MATCH_POLICIES = ("semantic", "exact")

# Tương thích ngược với điểm dev_set đã có: mặc định chấm bằng các biến thể ngữ
# nghĩa do người gán nhãn cung cấp. Gói nộp exact/robust sẽ chọn ở tầng export,
# không tự đổi thước đo này.
DEFAULT_QA_MATCH_POLICY = "semantic"

# Ba kiểu artefact nộp sẽ được tạo từ CÙNG một bể evidence đã đóng băng. Hằng này
# mới là hợp đồng cho tầng đóng gói; nó không làm thay đổi CSV hay số dòng.
QA_SUBMISSION_POLICIES = ("semantic", "exact", "robust")

# Exact cần thử vài dạng bề mặt của CÙNG fact, nhưng nhân mọi 100 frame sẽ phá
# recall vị trí. Chỉ các frame đầu có xác suất cao được nhân; mọi số ở đây là
# chiến thuật thay đổi được, không nằm cứng trong export.
QA_MAX_SURFACE_FORMS = 3
QA_EXACT_VARIANT_FRAMES = 10
QA_ROBUST_VARIANT_FRAMES = 1
