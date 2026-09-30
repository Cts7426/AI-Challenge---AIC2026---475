"""Biên tập từ v1 cho hạn nộp; giữ nguyên source/PDF cũ và toàn bộ engineering artifacts."""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'reports/technical_report_draft_20260910'
OUT = ROOT / 'output/pdf'
AUDIT = Path(__file__).resolve().parent

text = (BASE / 'ThanhNghe_TechnicalReport.md').read_text(encoding='utf-8')
text = text.replace('(architecture.svg)', '(FINAL_REPORT_ARCHITECTURE.svg)')
text = text.replace('Kiểm tra format độc lập với kiểm chứng đáp án đúng; mục 4 trình bày thời điểm bổ sung các kiểm tra câu từ chối và trace cũ.', 'Kiểm tra format độc lập với kiểm chứng đáp án đúng; mục 4 trình bày các bài học kiểm tra đầu ra và cải tiến sau sơ tuyển.')
old = '| Câu từ chối lọt vào answer và trace cũ còn được sử dụng | Diễn tập 28/08 phát hiện lỗ hổng; chạy lại trên nhánh sửa ngày 01/09 còn 0 thay vì 2 dòng từ chối [5] | Dùng kiểm tra answer chung ở export và release preflight; tạo bằng chứng mới | QA 0,200 và overall 0,363 không đổi; cải thiện tính hợp lệ trên nhánh sửa |'
new = '| Câu từ chối lọt vào answer và kết quả cũ còn được sử dụng | Diễn tập 28/08 phát hiện lỗi; kiểm lại trên nhánh sửa ngày 01/09 [5] | Dùng kiểm tra answer chung ở export và release preflight | Chặn trường hợp từ chối đã phát hiện; điểm chẩn đoán không đổi |'
assert old in text
text = text.replace(old, new)
start = text.index('### Quan sát vận hành')
end = text.index('<!-- PAGEBREAK -->', start)
text = text[:start] + '''### Cải tiến sau Vòng Sơ tuyển

Sau sơ tuyển, đội bổ sung định danh runtime/tài nguyên, siết kiểm tra cache/resume và lời gọi provider, đồng thời ghi nhận các giai đoạn trên đường xử lý thực tế. Hợp đồng kết quả Q&A được chuẩn hóa để phân biệt đáp án đủ bằng chứng với trường hợp cần người kiểm tra, không đủ bằng chứng, placeholder hoặc câu từ chối; kiểm tra áp dụng trên các đường replay/export liên quan. Đội cũng chuẩn bị quy trình ground truth do người xác minh, tách validation và sealed held-out trước thử nghiệm retrieval tiếp theo. Bộ đánh giá chưa hoàn tất nên chưa dùng để đưa ra kết quả hiệu năng mới; các thay đổi này không diễn giải lại điểm sơ tuyển [6].

''' + text[end:]
text = text.replace('Các phiên hỗ trợ bên ngoài được tách biệt với LLM/VLM adapter tích hợp trong hệ thống và không được tính là năng lực truy xuất tự động của engine.', 'Các phiên hỗ trợ bên ngoài được tách biệt với LLM/VLM adapter tích hợp trong hệ thống.')
text = text.replace('3. **Hợp nhất kiểm tra phát hành.** Đưa kiểm tra câu từ chối, bằng chứng cũ và export vào đúng nhánh release; diễn tập trên batch sạch và kiểm tra hồi quy theo task trước khi đóng băng. Báo riêng lỗi format, sai nội dung và thiếu tín hiệu retrieval.', '3. **Duy trì kiểm tra phát hành.** Kiểm tra xuyên suốt câu từ chối, bằng chứng cũ và export; diễn tập trên batch sạch và kiểm tra hồi quy theo task trước khi đóng băng. Báo riêng lỗi format, sai nội dung và thiếu tín hiệu retrieval.')
text = text.replace('4. **Gắn mỗi lần chạy với trạng thái đầy đủ hơn.** Mở rộng manifest tới phiên bản dữ liệu/index, dependency và cache; liên kết batch, cấu hình và gói xuất để không trộn khác biệt môi trường hay thao tác người dùng khi so sánh.', '4. **So sánh trong điều kiện được kiểm soát.** Khóa truy vấn, ground truth, bản dịch, model, dữ liệu/index, cấu hình và scorer trước mỗi phép so sánh; dùng cùng quy trình runtime/cache và chạy lại baseline khi tài nguyên thay đổi.')
text = text.replace('Kiến trúc dùng chung từ truy vấn đến submission cho phép đội cô lập lỗi theo từng tầng, đo tác động của thay đổi trước khi đưa vào vận hành và từng bước giảm phụ thuộc vào can thiệp thủ công. Đây là nền tảng để phát triển hệ thống theo hướng tự động hơn, có khả năng tái lập và ổn định hơn ở Vòng Chung kết.', 'Kiến trúc dùng chung giúp cô lập lỗi theo tầng và kiểm tra thay đổi trước vận hành. Hướng phát triển là nâng độ tin cậy, khả năng tái lập và mức tự động hóa của hệ thống, dựa trên đánh giá được kiểm chứng.')
text = text.rstrip() + '\n\n[6] Đội Thanh Nghệ. Hồ sơ cải tiến khả năng tái lập, hợp đồng kết quả Q&A và quy trình đánh giá sau sơ tuyển, 11-12/09/2026. Tài liệu kỹ thuật nội bộ.\n'
(OUT / 'FINAL_REPORT_SUBMISSION.md').write_text(text, encoding='utf-8')
shutil.copyfile(BASE / 'architecture.svg', OUT / 'FINAL_REPORT_ARCHITECTURE.svg')
shutil.copyfile(BASE / 'form_summary.md', OUT / 'FINAL_FORM_SUMMARY.md')
builder = (BASE / 'build_report.py').read_text(encoding='utf-8')
builder = builder.replace("ROOT = Path(__file__).resolve().parent\nOUT = ROOT.parents[1] / 'output' / 'pdf'", "ROOT = Path(__file__).resolve().parents[2] / 'output' / 'pdf'\nOUT = ROOT")
builder = builder.replace("ROOT / 'architecture.svg'", "ROOT / 'FINAL_REPORT_ARCHITECTURE.svg'").replace("ROOT / 'ThanhNghe_TechnicalReport.md'", "ROOT / 'FINAL_REPORT_SUBMISSION.md'").replace("OUT/'ThanhNghe_TechnicalReport.pdf'", "OUT/'FINAL_REPORT_SUBMISSION.pdf'")
(AUDIT / 'build_final_report.py').write_text(builder, encoding='utf-8')
shutil.copyfile('C:/Users/lehon/.codex/attachments/df751d84-9476-4eb4-9818-a57ef5a25f04/pasted-text.txt', AUDIT / 'deadline_authorization.txt')
print('Prepared final source from v1; original source/PDF preserved.')
