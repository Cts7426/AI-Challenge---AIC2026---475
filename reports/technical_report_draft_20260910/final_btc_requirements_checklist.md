# Checklist BTC sau biên tập cuối

Nguồn: ảnh form BTC do người dùng cung cấp, bộ yêu cầu đã audit, strategy đã duyệt và yêu cầu biên tập cuối. Đã đọc lại ảnh form và đối chiếu mục yêu cầu trong audit. Không mở lại forensic hoặc tự liên hệ BTC.

**Phạm vi:** kiểm bản báo cáo với yêu cầu đã nhận; không chứng nhận toàn bộ thể lệ cuộc thi, không khẳng định ảnh chụp là toàn bộ form đăng ký/nộp bài.

## Yêu cầu định dạng và thông tin

| Yêu cầu được kiểm | Trạng thái | Kết quả và nguồn |
| --- | --- | --- |
| Một báo cáo kỹ thuật | PASS | Một PDF chính; tài liệu review không đưa vào PDF |
| Khoảng4 trang A4 | PASS | PDF thực tế4 trang; MediaBox A4; kiểm render từng trang |
| Tiếng Việt hoặc tiếng Anh | PASS | Tiếng Việt, giữ tên kỹ thuật chuẩn |
| PDF/DOC/DOCX | PASS | PDF phù hợp định dạng trong ảnh form |
| Không quá100MB | PASS | File132.237 byte sau biên tập |
| Tên khuyến nghị TeamName_TechnicalReport.pdf | PASS | ThanhNghe_TechnicalReport.pdf |
| Tên đội | PASS | “Đội Thanh Nghệ” ở đầu trang1 |
| Tóm tắt giải pháp100–200 từ | PASS | form_summary.md riêng,185 đơn vị tách bằng khoảng trắng sau đồng bộ; không chiếm trang thứ5 |
| Danh sách thành viên trong PDF | PARTIAL về phạm vi yêu cầu | Ảnh form và hồ sơ yêu cầu đã audit không nêu bắt buộc. Không thêm danh sách; chưa kết luận các phần form chưa được cung cấp không có trường thành viên |
| Cơ quan/trường/đơn vị trong PDF | PARTIAL về phạm vi yêu cầu | Không tìm thấy yêu cầu này trong tài liệu đã nhận. Không suy tên đơn vị từ email hoặc Git author |
| Thông tin liên hệ trong PDF | PARTIAL về phạm vi yêu cầu | Không thấy bắt buộc trong tài liệu đã nhận. Không tự thêm email/số điện thoại từ nguồn nội bộ |
| Tiêu đề mục bắt buộc | PASS trong phạm vi đã nhận | Không có danh sách heading bắt buộc trong nguồn đã cung cấp; giữ cấu trúc6 mục đã được người dùng duyệt |
| Template/font/lề bắt buộc | PASS trong phạm vi đã nhận | Không có template/font/lề cụ thể được cung cấp. Giữ A4, font và bố cục đã duyệt; không giả định đây là mẫu BTC phát hành |
| Upload/gửi BTC | Chưa thực hiện theo yêu cầu | Không phải lỗi deliverable; người dùng review và quyết định nộp |

Các mục PARTIAL phản ánh **độ phủ tài liệu yêu cầu**, không phải bằng chứng PDF thiếu trường bắt buộc. Không thêm thông tin cá nhân/đơn vị khi chưa có căn cứ yêu cầu. Nếu BTC cung cấp template hoặc điều khoản mới, chỉ mở lại các mục bị ảnh hưởng.

## Checklist nội dung sau biên tập

| Kiểm tra | Trạng thái | Vị trí |
| --- | --- | --- |
| Giữ kiến trúc và phần kỹ thuật1–3 | PASS | Không thêm hoặc bỏ module; thuật ngữ được chuẩn hóa |
| Adapter không hàm ý bắt buộc host local | PASS | Mục3 và Hình1 dùng “tích hợp trong pipeline” |
| Ba boundary và AI→người vận hành→lựa chọn cuối | PASS | Hình1; không có cạnh External AI→submission tự động |
| Multi-anchor có hypothesis/measurement/regression/rollback/recheck | PASS | Mục4; số liệu và19KIS giữ nguyên |
| Diagnostic không là điểm BTC, GT chưa đủ cho accuracy độc lập | PASS | Qualification ngay đoạn multi-anchor |
| Q&A fix đúng timeline, không quy ngược deployment | PASS | Bảng1 và đoạn sau; sauR2/trướcR3, chưa chứng minh áp dụng vào scored submissions |
| Bỏ exact historical latency | PASS | Không còn6.675/359.605/76.575 hoặc dạng dấu phẩy trong main source/PDF; số giữ internal |
| Manual reranking và tìm kiếm bổ sung thủ công | PASS | Mục5 |
| ChatGPT/Claude ngoài pipeline và ảnh hưởng final qua lựa chọn của người vận hành | PASS | Mục5, không ngụ ý blind insertion |
| Caption bảng điểm đúng yêu cầu | PASS | “Bảng2. Kết quả các submission cuối tại ba đợt Vòng Sơ tuyển.” |
| Điểm final không là autonomous performance | PASS | Đoạn ngay dưới bảng |
| Không replay scores/human uplift/personnel | PASS | Không đưa vào main report |
| References1–2 giữ;3–5 nhãn nội bộ nhất quán | PASS | Cuối trang4; không giả định reviewer có quyền truy cập |
| Kết luận hướng Chung kết bằng technical roadmap, không vận động lựa chọn | PASS | Đoạn cuối mục6 |
|4 trang,1 hình,2 bảng; không clipping/overlap | PASS | Đọc đủ4 ảnh render mới |

## Liên kết nguồn yêu cầu và ghi chú kỹ thuật

- [Ảnh form](C:/Users/lehon/AppData/Local/Temp/codex-clipboard-816517a5-4a2b-4744-a7ef-2ca2612cb144.png).
- [Audit yêu cầu BTC](C:/dev/aic2026/reports/internal_reporting_audit_20260909/audit_L_P.md:71).
- [Yêu cầu biên tập được phê duyệt](C:/Users/lehon/.codex/attachments/c9349ba3-0a1d-4250-bc28-25d0b601394f/pasted-text.txt).
- [Claim review nội bộ](C:/dev/aic2026/reports/technical_report_draft_20260910/claim_review_internal.md) giữ nguồn cho số liệu, kể cả latency đã bỏ khỏi main report.

Không tuyên bố hệ thống production đã qua selfcheck; đây là kiểm chất lượng tài liệu. Không sửa GT, DB, model, config hoặc môi trường thi.
