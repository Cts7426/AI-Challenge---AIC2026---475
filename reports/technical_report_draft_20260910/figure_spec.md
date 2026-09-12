# Figure specification

Hình duy nhất trong báo cáo: **Kiến trúc hệ thống và ranh giới hỗ trợ bên ngoài**. Source chỉnh sửa được: [architecture.svg](C:/dev/aic2026/reports/technical_report_draft_20260910/architecture.svg). PDF nhúng hình dạng vector, không phải ảnh chụp màn hình.

Biên tập cuối: nhãn adapter đổi thành “LLM/VLM adapter tích hợp trong pipeline”; người vận hành nhận đề xuất External AI rồi lựa chọn khi hoàn thiện submission. Không có đường External AI ghi tự động vào submission. Ba ranh giới Core Retrieval System, Operator-assisted workflow và External AI được giữ nguyên.

## Các khối và luồng dữ liệu

| Khối | Input và output | Vị trí và bằng chứng |
| --- | --- | --- |
| Query và loại task | Nội dung query và nhãn KIS/QA/TRAKE | Trong core; runner |
| Xử lý và routing | Caption/ràng buộc/sự kiện cho retrieval | Trong core; query_understanding, QA planner, TRAKE parser; LLM gọi qua adapter |
| Dữ liệu BTC và index | Vector, OCR, ASR, labels, metadata đã liên kết | Trong core; loaders, Milvus, Elasticsearch |
| Retrieval đa nguồn | Query → ranked lists theo nguồn | Trong core; search |
| Weighted RRF và candidate | Ranked lists → fusion → gom shot và xếp candidate | Trong core; search, source ranks/contribution |
| Xử lý theo task | KIS frame, Q&A evidence/answer, TRAKE temporal sequence | Trong core; runner, qa, trake, slot allocator |
| Map và export | Candidate/task output → frame tuyệt đối → validator → CSV/ZIP | Trong core; frame_assets, frame map, exporter |
| Người vận hành | Kết quả hệ thống → kiểm bằng mắt, loại/rerank hoặc thêm candidate | Ngoài core; workflow team-confirmed và selected logs |
| External AI | ChatGPT/Claude → suy luận, đề xuất answer/frame cho operator | Ngoài core và khác LLM adapter nội bộ; tùy query |
| Final submission | Lựa chọn và chỉnh sửa/bổ sung theo workflow | Ngoài autonomous core; không đồng nhất với export ban đầu |

## Quy ước hình

- Core: nền xanh rất nhạt, viền liền. Đây là ranh giới logic phần mềm của đội, không phải tuyên bố tất cả inference chạy local.
- Operator layer: nền xám, viền liền; không xem thao tác operator là module autonomous.
- External AI: viền tím đứt, mũi tên đứt tới operator; không đặt vào nhánh production LLM.
- Data/index đi vào retrieval. Query đi qua processing, retrieval, fusion, task handling và map/export. Mapping cũng phục vụ retrieval/QA nội bộ; sơ đồ chỉ vẽ đường đọc chính để giữ gọn.
- Đường từ export đến operator biểu thị candidate/kết quả có thể được xem và sửa, không hàm ý chỉ được sửa sau lần export duy nhất. Operator có thể gọi tìm kiếm lại; vòng lặp đó được giải thích trong văn bản thay vì thêm cạnh giao nhau.
- External assistance là tương tác tùy query. Hình không định lượng tỷ lệ sử dụng, không chứng minh external proposal đúng, không chứng nhận tuân thủ thể lệ.
- Kích thước nguồn 1000 × 470; hiển thị rộng khoảng 180 mm ở trang 1. Text tiếng Việt dùng Arial có dấu.

## Những gì cố ý không vẽ

Không có model/module tưởng tượng; không đưa nhánh thử nghiệm chưa chứng minh dùng trong các scored runs thành capability bắt buộc. Không vẽ diagram causal từ nhân sự tới điểm. Không vẽ human uplift. Gate refusal/stale-trace ngày 01/09 được trình bày ở engineering table với branch-level qualification, không đưa vào core figure như protection đã triển khai khi thi.
