# Page budget review

> Sau editorial revision: vẫn4 trang; mục latency đổi thành nhận xét ngắn không có median; form summary đồng bộ thành185 từ. Dàn trang của lần draft đầu dưới đây được giữ làm lịch sử; bản kiểm mới ở [checklist cuối](C:/dev/aic2026/reports/technical_report_draft_20260910/final_btc_requirements_checklist.md).

Bản PDF kiểm cuối: **4 trang A4**, gồm cả1 hình,2 bảng và references. Không có cover riêng hoặc appendix trong file nộp đề xuất.

| Trang thực tế | Nội dung | Đánh giá |
| --- | --- | --- |
| 1 | Bài toán/contribution; tổ chức dữ liệu và frame map; Hình1 cùng caption | Architecture có vị trí rõ, đủ khoảng thở. Không thêm bảng số liệu vào đây |
| 2 | Query processing, fusion, candidate/slot, QA, TRAKE và exporter | Phần kỹ thuật dày nhất nhưng body vẫn đọc được. Không thêm catalogue model/nhánh thử nghiệm |
| 3 | Methodology; multi-anchor case; bảng3 engineering decisions; timing/trace scope | Số đo và qualification cùng trang; bảng không bị tách |
| 4 | Human/external workflow; điểm3 vòng; limitations; roadmap4 mục; references | Trang chặt nhất. Disclosure và score caption vẫn rõ; references nằm trọn trang |

## Nếu cần bổ sung nội dung sau review

Rút theo thứ tự sau, không giảm cỡ chữ body để nhét trang:

1. Rút câu latency thành KIS median/n và một nhận xét Q&A tốn thời gian; giữ đúng run scope và không gán scored artifact.
2. Rút phần giải thích lại multi-anchor đã có trong bảng; giữ hypothesis, observed regression, disable, recheck, legacy-GT caveat.
3. Bỏ một số mô tả cơ chế cache/slot ở mục3 nếu reviewer không cần sâu; giữ vai trò và liên kết giữa các tầng.
4. Nếu vẫn thiếu chỗ, đổi bảng điểm thành một câu có đủ3 điểm và nhãn final workflow, giữ bảng engineering.

Không cắt: human verification/reranking **và** manual discovery; external suggestions có dùng final; final score không là autonomous benchmark; branch/timeline qualification của QA; phạm vi diagnostic/GT của số đo.

## Những gì đã rút có chủ đích

Không có replay-number table, score-uplift chart, personnel paragraph, hash/receipt/packaging discussion hoặc raw chat lineage. Không bỏ kiến trúc để dành chỗ cho forensic. Bản tóm tắt178 từ dùng cho form riêng, không cộng thành trang thứ5 của PDF.

## Kết quả vòng dàn trang

Vòng đầu tràn phần references sang trang5. Đã rút câu kết luận và wording lặp ở workflow, đồng thời sửa roadmap thành4 đoạn riêng. Bản render cuối đủ4 trang, không cần giảm body font qua các vòng chỉnh. Hình được sửa đường đi của hai mũi tên và nhãn dài để không đè lên tiêu đề hoặc viền.
