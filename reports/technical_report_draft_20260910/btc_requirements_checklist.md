# BTC requirements checklist

> Bản checklist của draft đầu. Sau editorial revision, dùng [checklist BTC cuối](C:/dev/aic2026/reports/technical_report_draft_20260910/final_btc_requirements_checklist.md); wording và kích thước PDF dưới đây là lịch sử.

Ngày kiểm 10/09/2026. Checklist này đánh giá **deliverable theo yêu cầu báo cáo đã được cung cấp/audit**, không chứng nhận toàn bộ workflow thi tuân thủ mọi điều khoản BTC. Không upload hoặc submit trong bước này.

## Yêu cầu BTC đã xác định

Nguồn trực tiếp: [ảnh form do người dùng cung cấp](C:/Users/lehon/AppData/Local/Temp/codex-clipboard-816517a5-4a2b-4744-a7ef-2ca2612cb144.png). Bộ nguồn chính thức 2026 và phạm vi kiểm tra trước đó ở [audit L–P mục M](C:/dev/aic2026/reports/internal_reporting_audit_20260909/audit_L_P.md).

| Yêu cầu | Trạng thái | Kiểm chứng |
| --- | --- | --- |
| 01 báo cáo kỹ thuật | PASS | Một PDF chính; các file internal không phải tài liệu đề xuất upload |
| Khoảng 04 trang A4 | PASS | PDF thực tế 4 trang; kiểm MediaBox A4 và render cả4 trang |
| Tiếng Việt hoặc tiếng Anh | PASS | Tiếng Việt chuyên nghiệp, thuật ngữ kỹ thuật giữ khi cần |
| Định dạng PDF, DOC hoặc DOCX | PASS | PDF; không cần nộp đồng thời các định dạng |
| File không quá100MB | PASS | 132.765 byte tại bản render kiểm cuối |
| Khuyến nghị tên TeamName_TechnicalReport.pdf | PASS | ThanhNghe_TechnicalReport.pdf |
| Tóm tắt giải pháp khoảng100–200 từ | PASS | form_summary.md,178 đơn vị phân tách bằng khoảng trắng; đủ hệ thống/phương pháp/chiến lược thi |
| Mô tả hệ thống và phương pháp sử dụng | PASS | Mục1–4, Hình1; mô tả cấu trúc, retrieval, Q&A/TRAKE, mapping/export |
| Contribution theo tên từng thành viên | PASS trong phạm vi tài liệu đã nhận | Không có yêu cầu bắt buộc này trong form đã cung cấp; không chèn contribution map nội bộ. Đánh giá lại nếu BTC cung cấp yêu cầu mới |
| Upload/nộp thực tế | PARTIAL có chủ ý | Bản thảo đã sẵn để người dùng review; chưa upload/nộp theo chỉ thị rõ của người dùng |

Không có MISSING trong các yêu cầu **soạn báo cáo** đã xác định. “PASS” ở đây không chứng minh BTC đã chấp nhận file hoặc workflow thi.

## Yêu cầu bổ sung của người dùng

| Kiểm tra | Trạng thái | Vị trí hoặc quyết định |
| --- | --- | --- |
| Mở bằng problem/contribution, không score hoặc nhân sự | PASS | Trang1 |
| Kiến trúc end-to-end, chỉ component có thật | PASS | Mục2–3; claim review đối chiếu source |
| Một architecture figure có boundary | PASS | Hình1, source SVG riêng; external AI ngoài core |
| Tối đa2 bảng | PASS | Bảng engineering3 case; bảng điểm3 vòng |
| Multi-anchor là measured regression/rollback | PASS | Mục4, có19KIS/legacy GT/runtime scope |
| Q&A fix đúng timeline và deployment scope | PASS | Bảng1 và đoạn ngay sau; branch-level sauR2/trướcR3 |
| Human reranking lẫn manual discovery | PASS | Mục5 |
| External ChatGPT/Claude, direct suggestions có dùng final | PASS | Mục5 có qualification “theo xác nhận của đội” |
| Final scores không phải autonomous benchmark | PASS | Caption Bảng2 và đoạn ngay dưới |
| Không human/AI uplift, contribution percentages | PASS | Không có phép tính attribution từ score deltas |
| Không nhãn compliance audit trong narrative | PASS | Không claim allowed/prohibited; ambiguity giữ internal |
| Không SHA, receipt gap, chat lineage, filesystem paths trong report | PASS | Scan source/PDF; các chi tiết nằm trong internal files |
| Không personnel conflict hoặc tên thành viên inactive | PASS | Không đưa phần nhân sự vào báo cáo |
| Không ép đưa replay numbers | PASS | Bỏ6.8/4.4/11.2/11.4 khỏi bản chính theo approval mới |
| Roadmap cụ thể theo failure mode | PASS | Mục6 có4 hướng, future work rõ |
| Có review riêng sau khi viết | PASS | claim_review_internal.md và vòng render/đọc4 trang |
| Không sửa production code/config hoặc artifact thi | PASS | Chỉ thêm thư mục draft và output PDF |
| Không tự gửi BTC | PASS | Không dùng công cụ upload/submit/message |

## Kiểm tra xuất bản

PDF dùng font Arial nhúng, body10,5pt, leading14,2pt; hình vector; table body9pt, references8,4pt. Đã kiểm ảnh render tất cả4 trang, dấu tiếng Việt, vị trí mũi tên, dòng bảng, danh sách roadmap, số trang và phần cuối references. Không có clipping/overlap quan sát được.

PDF là bản được chốt số trang. Markdown là source để chỉnh nội dung, không bảo đảm mọi renderer Markdown sẽ cho cùng phân trang. Chưa tạo DOCX vì PDF đã đáp ứng định dạng BTC; không dùng một DOCX chưa render làm deliverable.
