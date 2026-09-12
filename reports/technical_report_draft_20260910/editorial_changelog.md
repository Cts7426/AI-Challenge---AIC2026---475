# Changelog biên tập cuối

- Giữ cấu trúc4 trang, kiến trúc, số liệu chẩn đoán, điểm final và phạm vi evidence đã duyệt. Mục1–3 chỉ chỉnh thuật ngữ và rút diễn giải trùng lặp.
- Đổi adapter thành **LLM/VLM adapter tích hợp trong pipeline**; hình giữ ba ranh giới. Đề xuất External AI đi tới người vận hành, rồi mới tới lựa chọn/hoàn thiện submission, không có cạnh AI tự ghi vào gói nộp.
- Rút các caveat lặp về kết quả chưa xác minh, deployment và cách đọc số đo; giữ caveat thiết yếu về GT, điểm diagnostic khác điểm BTC, final khác autonomous và timeline Q&A. Các câu được biên tập theo mục tiêu giảm khoảng20–25% phần diễn giải phòng vệ, không cắt20–25% toàn báo cáo.
- Bỏ ba median latency khỏi bản chính; giữ nhận xét lịch sử Q&A tốn thời gian xử lý hơn KIS. Số chính xác vẫn có trong claim review/evidence nội bộ.
- Giữ multi-anchor từ giả thuyết tới rollback/recheck và case Q&A refusal/export. Không thêm metric hoặc nâng confidence.
- Thống nhất “người vận hành”, “ứng viên”, “tìm kiếm bổ sung thủ công”, “chạy lại”; disclosure nói rõ người vận hành lựa chọn đề xuất AI. Tóm tắt form được đồng bộ cách diễn đạt.
- Đổi caption bảng điểm theo yêu cầu; đoạn dưới vẫn giới hạn đây là toàn bộ workflow có hỗ trợ, không phải autonomous benchmark. Phân loại score TEAM-REPORTED trong ledger nội bộ không thay đổi.
- Viết lại đoạn kết theo hướng cô lập lỗi, đo thay đổi và phát triển tính tự động/tái lập cho Vòng Chung kết; không thêm lời kêu gọi tuyển chọn.
- Giữ references công khai[1]–[2]. Giữ[3]–[5] vì hỗ trợ trực tiếp số liệu kỹ thuật, thống nhất nhãn **Hồ sơ đánh giá và kỹ thuật nội bộ**; không có liên kết hay lời hứa BTC truy cập được các hồ sơ này.
- Không thêm tên thành viên, đơn vị hoặc liên hệ khi chưa có yêu cầu bắt buộc trong tài liệu đã cung cấp. Không đưa personnel hoặc replay scores vào report.

## Kiểm tra bàn giao

PDF sửa đã render và đọc đủ4 trang A4; không quan sát thấy chữ/mũi tên đè nhau, cắt bảng hoặc tràn trang. Xem [checklist BTC cuối](C:/dev/aic2026/reports/technical_report_draft_20260910/final_btc_requirements_checklist.md) để biết các giới hạn của nguồn yêu cầu.

Bản trước biên tập được giữ trong `archive_before_editorial` để đối chiếu. Không upload/submit, không sửa production code/config hoặc artifact thi.
