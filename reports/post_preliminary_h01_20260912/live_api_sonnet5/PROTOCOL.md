# PP-H01: protocol đóng trước run model đã chọn

Operator chọn `LLM_BACKEND=api`, model `claude-sonnet-5` trong lượt trả lời mới. Tên biến model được chuẩn hóa thành `LLM_API_MODEL`; không ghi tên model vào secret. Credential dùng cơ chế hiện có của adapter. Chỉ đặt environment trong process lệnh, không sửa `.env`.

Khóa đủ 30 query tune đã tiêu thụ: 23 KIS / 5 QA / 2 TRAKE. Giữ nguyên mọi field, không sửa query/GT để kết quả tốt hơn, không đọc sealed mới. `queries.json` và `preregistration.json` lưu hash trước output. Vai trò diagnostic/regression, không accuracy claim độc lập.

Thứ tự H01: kiểm đường dịch thật qua adapter bằng query QA01 để xác nhận runtime; thu identity đầy đủ; chạy prewarm cùng 30 query bằng runner production, lưu mọi output nhưng không nhận làm paired baseline. LLM response cache sau prewarm được đóng thành seed để on/off replay cùng evidence, tránh so hai lần sinh ngẫu nhiên. Nếu credential/model không dùng được, ghi lỗi và dừng gọi LLM; không tự đổi model.

Cache làm việc chỉ nằm trong thư mục thí nghiệm. Giữ nguyên cache lịch sử; snapshot seed được copy từ cache response đã sinh bằng model đã chọn. Trước on và off, cùng đường dẫn cache làm việc phải có cùng bytes. Sau từng arm, lưu nguyên cache phát sinh sang archive riêng trước khi khôi phục seed. Không xóa cache/evidence lịch sử. Cả hai arm dùng đúng source/config/model/path/runtime fingerprint ban đầu. Inference mode legacy, submission policy robust; không sửa ranking/allocation.

Baseline dùng nhãn PP-B0-RESTORED vì không chứng minh được trạng thái live lịch sử; DB hiện có không được reindex để chạy thử. Hash tài nguyên trước/sau qua collector, không gọi status available thay content digest thiếu. Giữ DB/assets không đổi trong run, mọi sai khác identity phải phân loại; scan Milvus có cảnh báo timestamp thì giữ nguyên trong evidence.

Gate đăng ký trước: đủ 30 query mỗi arm, task/export failures=0, mapping/export violations=0; source/config/data/index/model giữ nguyên và cache chỉ append, evidence cũ không bị sửa. So query-level task type/status, answers, query plan, raw/fused/reranked/final rank và điểm khi có thể quan sát, source contributions, task evidence và bytes CSV. Bỏ riêng timing, usage/cache counters, thời điểm cache, đường dẫn artifact; không bỏ answer/order/score hoặc lỗi. On/off search trace khác nhau theo thiết kế; semantic output của production runner phải bằng nhau. Mọi lệch ngoài correctness H01A đã đăng ký khiến DO NOT PROMOTE và phải báo nguyên nhân, không tự tune.

Latency là số đo mô tả trong H01, không claim cải thiện. Thu per-query và tổng, tách thời gian hash/capture khỏi query. Cùng CPU/resources, warm LLM evidence; không gọi chi phí sinh ban đầu là chi phí replay. Không đặt ngưỡng sau kết quả để nhận khác biệt ngoài dự kiến.

Sau run, cập nhật checkpoint A–L; H01 promotion chỉ nhận hạ tầng và baseline này, không nhận accuracy hoặc H02. Không bắt đầu H02–H05. Nếu H01 gate còn lỗi, giữ DO NOT PROMOTE. Ngưỡng H02 phải đăng ký riêng sau review baseline này.
