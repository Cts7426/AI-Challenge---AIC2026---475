## Task 1: Product spec và nền tảng đánh giá có provenance

- Thay nội dung `docs/product-spec.md` bằng đặc tả đã duyệt với đúng các mục:
  Problem, Goals, Non-goals, User stories, Functional requirements,
  Non-functional requirements, Constraints, Acceptance criteria, Risks.
- Mở rộng schema ground truth bằng metadata `verification_status`, `provenance`,
  `verified_by`, `verified_at` theo cách tương thích dữ liệu cũ.
- Scorer promotion chỉ nhận nhãn `verified`; chế độ phân tích legacy vẫn đọc
  được GT cũ nhưng phải báo rõ không đủ điều kiện promotion.
- Đóng băng đủ 25 query vòng 1 từ artefact/HEAD mà không sửa file query đang dùng.
- Chọn 10 KIS + 3 QA từ Batch 1 holdout hiện có làm manifest
  `batch1_holdout13`; giữ nhãn `unknown` nếu chưa xác minh, không bịa đáp án.
- Thêm test schema/gate trước khi sửa production code.

