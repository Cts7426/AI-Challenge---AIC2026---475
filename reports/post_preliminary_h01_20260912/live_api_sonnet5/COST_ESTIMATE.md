# Ước tính trước khi được phép gọi API

Chưa được phép gửi payload ra Anthropic: operator đã chọn model, sau đó hỏi chi phí; câu hỏi không phải phê duyệt egress hoặc ngân sách.

Giá xác minh ngày 2026-09-12: Sonnet 5 **$2/MTok input, $10/MTok output**. Anthropic đã giữ giá giới thiệu thành giá chính thức, hủy đợt tăng lên $3/$15. Nguồn: [Pricing, Claude Platform](https://platform.claude.com/docs/en/about-claude/pricing), phần model pricing.

**Lưu ý đo lường:** bảng `PRICING` trong source checkpoint hiện vẫn ghi $3/$15. Khi báo chi phí Sonnet 5, giữ số token/ước lượng gốc và ghi thêm số tính lại theo bảng giá ngày trên; không gọi trường `usage.usd` cũ là hóa đơn thực tế. Với đúng model này và công thức cache hiện hành, số ước lượng cũ nhân 2/3 cho giá mới. Không sửa source giữa khi capture identity đang chạy.

Tập H01 gồm 23 KIS (chỉ 3 câu có query_en sẵn, 20 câu còn cần dịch), 5 QA và 2 TRAKE. Q&A legacy có tối đa 5 shot chính + 5 đề cử text + 3 video × 3 shot mở rộng = 19 shot mỗi câu trước khử trùng. Mỗi shot thường sinh 3 lần; fallback từ text sang ảnh có thể thêm 3 lần, ảnh evidence tối đa 8 frame/cohort. Chi phí vì vậy không bằng 30 request đơn. Parse/dịch và retry cũng cần tính.

Ước tính sơ bộ cho lượt tạo cache: **$5–15**, có thể **$20–30** nếu nhiều fallback/retry và output dài. Đây là dự trù từ cấu trúc gọi, chưa có token usage thực của run này, không phải upper bound được bảo đảm. Ví dụ 1 triệu input + 300.000 output là $5; 3 triệu input + 900.000 output là $15. Thuế và điều khoản riêng tài khoản chưa tính.

Hai lượt on/off dùng local response cache đã đóng băng; nếu mọi request hit cache thì phí API thêm bằng 0. Cache miss hoặc retry không được coi là miễn phí. Không nhầm local response cache với prompt caching có tính phí phía Anthropic.

Đề xuất cho operator: pilot một QA với ngân sách $1, hoặc cả bộ với ngân sách $10. **Chưa chọn/cho phép.** Trước khi thực thi cần có cơ chế chặn dự toán từng request; không hứa hard cap chỉ bằng việc in tổng tiền sau query. Nếu ngân sách không đủ, checkpoint giữ nguyên và run không được nhận thành baseline đủ 30 câu. Budget policy phải vào protocol/identity trước output.
