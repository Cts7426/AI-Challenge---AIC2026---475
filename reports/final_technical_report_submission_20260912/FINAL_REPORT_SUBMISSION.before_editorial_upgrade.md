# Báo cáo kỹ thuật Vòng Sơ tuyển AI Challenge TP.HCM 2026

Đội Thanh Nghệ

## 1 Bài toán và đóng góp

Truy xuất khoảnh khắc video đòi hỏi đồng thời nhận diện đúng nội dung và định vị đúng thời điểm. Một video phù hợp về chủ đề vẫn có thể chứa nhiều cảnh gần giống nhau; tìm đúng video chưa đủ để chọn đúng frame. Đội Thanh Nghệ xây dựng hệ thống truy xuất đa phương thức cho ba dạng bài: KIS tìm khoảnh khắc theo mô tả, Q&A tìm bằng chứng và trả lời câu hỏi, TRAKE xác định chuỗi sự kiện theo thứ tự thời gian.

Hệ thống dùng chung hạ tầng tìm kiếm cho cả ba dạng bài, kết hợp tín hiệu hình ảnh, chữ trên hình, lời thoại, đối tượng và metadata. Đóng góp kỹ thuật tập trung vào hợp nhất ứng viên (candidate) từ các nguồn khác đơn vị, liên kết kết quả với frame tuyệt đối, xử lý riêng theo task và tự động hóa kiểm tra/xuất submission. Các quyết định thay đổi retrieval được đối chiếu bằng phép đo chẩn đoán theo truy vấn; trường hợp hồi quy dẫn đến rollback và kiểm tra lại trước khi chọn cấu hình vận hành.

## 2 Kiến trúc và tổ chức dữ liệu

Hệ thống tách dữ liệu BTC gốc khỏi dữ liệu dẫn xuất. Ảnh keyframe, thông tin video và các đặc trưng được liên kết bằng khóa `keyframe_id`; metadata, OCR, ASR và nhãn đối tượng được nạp vào Elasticsearch, còn vector hình ảnh được tìm kiếm qua Milvus. Bản dữ liệu được kiểm kê ghi nhận 873 video và 177.321 keyframe [3]; quy mô index có thể khác giữa các lượt thi.

Tầng mapping phân biệt thứ tự ảnh keyframe trong thư mục với chỉ số frame tuyệt đối trong video. Bảng frame map cung cấp liên kết này; bộ phân giải ảnh dùng khóa và frame được cấp để tìm ảnh gốc hoặc cache dẫn xuất. Q&A và phần kiểm tra hình ảnh dùng chung resolver, tránh việc mỗi caller tự suy frame từ tên ảnh. Việc kiểm tra cấu trúc bảng và biên video không thay thế kiểm chứng nội dung từng frame.

![Kiến trúc hệ thống và ranh giới hỗ trợ bên ngoài](FINAL_REPORT_ARCHITECTURE.svg)

*Hình 1. Phần lõi thực hiện truy xuất và xuất kết quả tự động, với LLM/VLM adapter tích hợp trong pipeline. Đề xuất từ External AI đi qua người vận hành trước khi được lựa chọn cho submission; mũi tên đứt biểu thị tương tác tùy truy vấn.*

<!-- PAGEBREAK -->

## 3 Từ truy vấn đến kết quả theo task

### Xử lý truy vấn và hợp nhất đa nguồn

Runner nhận truy vấn cùng loại task và chuyển đến nhánh xử lý tương ứng. Đối với truy xuất hình ảnh, mô tả tiếng Việt được chuyển thành caption tiếng Anh ngắn qua LLM/VLM adapter tích hợp trong pipeline. Module mở rộng truy vấn tạo các caption riêng, có kiểm soát độ dài theo giới hạn 77 token của CLIP; prompt yêu cầu không thêm màu sắc, số lượng hoặc đối tượng không có trong mô tả. Cơ chế này hạn chế mất thông tin do cắt chuỗi, nhưng vẫn cần kiểm tra sai lệch ngữ nghĩa của bản dịch.

Nhánh CLIP [1] dùng cấu hình ViT-B/32, vector 512 chiều; vector truy vấn và index được chuẩn hóa L2 rồi so cosine. Loader kiểm metadata model/index để phát hiện không gian embedding không tương thích. Các nhánh text tìm chữ OCR, đoạn ASR và metadata tiếng Việt; nhánh đối tượng khai thác nhãn nhận diện. Chúng bổ sung tín hiệu cụ thể như tên riêng hoặc chữ trên bảng, trong khi vector tìm sự tương đồng thị giác. Mô tả này tập trung vào các nhánh lõi, không bao gồm mọi nhánh thử nghiệm.

Kết quả được quy chiếu về keyframe trước khi hợp nhất: metadata mức video truyền thứ hạng đến các keyframe của video; ASR mức đoạn thời gian được nối với keyframe lân cận. Weighted Reciprocal Rank Fusion dựa trên RRF [2] cộng đóng góp của từng nhánh theo trọng số chia cho hằng số làm trơn cộng thứ hạng. Cách này tránh cộng trực tiếp cosine với BM25 vốn khác thang đo. Trọng số và hằng số nằm trong cấu hình; kết quả giữ thứ hạng, đóng góp theo nguồn để phân tích truy vấn thất bại. Một nhánh lỗi có thể trả rỗng để các nhánh còn lại tiếp tục xử lý với ít nguồn tín hiệu hơn.

### Ứng viên và ánh xạ frame cho KIS

Sau fusion, các keyframe được gom theo shot, tức đoạn cảnh, để hạn chế nhiều ảnh gần nhau chiếm danh sách. Bộ phân bổ slot phân chia ngân sách dòng nộp giữa các shot và các frame trong shot. Hai quyết định này giải quyết hai vấn đề khác nhau: retrieval chọn vùng nội dung đáng kiểm tra; phân bổ frame tìm vị trí cụ thể trong vùng đó. Danh sách giữ liên kết video, keyframe, frame và điểm/thứ hạng để người vận hành kiểm tra và xác minh ứng viên.

### Q&A và TRAKE dùng chung retrieval

Q&A tách mô tả cảnh cần tìm khỏi nội dung cần trả lời, lấy ứng viên từ search rồi thu thập OCR, ASR, metadata hoặc ảnh làm bằng chứng. Tùy kiểu câu hỏi và chế độ suy luận, LLM/VLM qua adapter tích hợp trong pipeline sinh answer gắn với video/frame; bằng chứng và kết quả có cache để kiểm tra hoặc chạy lại. Tầng suy luận và tầng phân bổ dòng nộp được tách riêng. Câu hỏi đếm hoặc đọc chi tiết hình ảnh cần bằng chứng cụ thể hơn một ứng viên chỉ đúng chủ đề.

TRAKE tách truy vấn thành các sự kiện và tìm ứng viên cho từng sự kiện. Trong mỗi video, quy hoạch động chọn chuỗi ứng viên giữ cả thứ tự sự kiện lẫn thứ tự frame, có ràng buộc khoảng cách tối thiểu. Khi thiếu bằng chứng, đường fallback có thể nội suy vị trí; vị trí nội suy không phải bằng chứng quan sát trực tiếp. Đầu ra là video và dãy frame theo thứ tự yêu cầu.

### Kiểm tra và xuất kết quả

Exporter kiểm số cột, video/frame, biên frame, dòng trùng và các ràng buộc theo task trước khi ghi CSV UTF-8 không header, tối đa 100 dòng/truy vấn, rồi đóng ZIP. Q&A giới hạn độ dài answer; TRAKE kiểm số frame theo truy vấn. Checkpoint lưu kết quả từng truy vấn; runtime fingerprint bao gồm cấu hình, các source quan trọng và lựa chọn model để kiểm soát resume. Kiểm tra format độc lập với kiểm chứng đáp án đúng; mục 4 trình bày các bài học kiểm tra đầu ra và cải tiến sau sơ tuyển.

<!-- PAGEBREAK -->

## 4 Đo lường và quyết định kỹ thuật

Đánh giá tách kiểm tra bất biến dữ liệu, đo chẩn đoán retrieval và kiểm tra chuỗi xuất kết quả. Repository có test chống nhầm ordinal/frame, sai thứ tự bằng chứng TRAKE và đầu ra sai cấu trúc. Với KIS, R@k là tỷ lệ truy vấn có dòng khớp ground truth trong top-k; điểm tổng hợp là trung bình R@1, R@5, R@20, R@50 và R@100. Các thử nghiệm định danh tập truy vấn, scorer và cấu hình.

### Multi-anchor và quyết định quay về single-anchor

Giả thuyết của multi-anchor là nhiều mô tả ngắn có thể bao phủ các thành phần khác nhau của truy vấn tốt hơn một caption. Sau triển khai và sửa lỗi tương thích schema của planner, phép đo ngày 27/08 chạy đúng multi-anchor trên 19/19 truy vấn KIS của bộ dress25, không fallback, không crash và không vi phạm kiểm tra mapping/biên [4]. Tuy nhiên, điểm tổng hợp nội bộ giảm từ 0,4000 ở lần single-fallback tham chiếu xuống 0,3263; R@100 giảm từ 0,5789 xuống 0,5263. Có 4 truy vấn tăng, 5 giảm và 10 giữ nguyên điểm.

Đội tắt multi-anchor trước đợt 2. Lần kiểm tra ngày 28/08 xác nhận 19/19 truy vấn chạy single-anchor, không gọi planner/search multi-anchor; điểm tổng hợp trở lại 0,4000 và R@100 đạt 0,5789 [4]. Đây là phép đo chẩn đoán trên cùng bộ 19 KIS, không phải điểm BTC. Ground truth cũ chưa xác minh đầy đủ và khác biệt runtime retrieval/LLM giới hạn kết luận về độ chính xác độc lập; kết quả được dùng để chọn cấu hình vận hành.

*Bảng 1. Ba quyết định kỹ thuật và phạm vi của bằng chứng.*

| Vấn đề hoặc giả thuyết | Đo lường hoặc quan sát | Quyết định | Kết quả và bài học |
| --- | --- | --- | --- |
| Không gian CLIP có thể lệch dù cùng số chiều | Kiểm tra trước đợt 1 trên 12 ảnh BTC: cosine trung bình 0,9999, nhỏ nhất 0,9993 [3] | Kiểm tương thích model, preprocessing và index; giữ metadata guard | Xác nhận tương thích trên mẫu đã kiểm, không mở rộng thành parity toàn kho |
| Nhiều anchor có thể tăng độ bao phủ | 19 KIS: điểm chẩn đoán 0,4000 xuống 0,3263; không lỗi thực thi [4] | Tắt multi-anchor, kiểm lại single-anchor ngày 28/08 | Điểm kiểm lại 0,4000; chọn cấu hình theo chất lượng thay vì chỉ khả năng thực thi |
| Câu từ chối lọt vào answer và kết quả cũ còn được sử dụng | Diễn tập 28/08 phát hiện lỗi; kiểm lại trên nhánh sửa ngày 01/09 [5] | Dùng kiểm tra answer chung ở export và release preflight | Chặn trường hợp từ chối đã phát hiện; điểm chẩn đoán không đổi |

Các sửa Q&A ngày 01/09 nằm trên nhánh phát triển sau đợt 2, trước đợt 3; chưa có bằng chứng chúng đã được áp dụng vào các submission được chấm. Bài học là kiểm tra xuyên suốt từ bằng chứng đến CSV, kể cả cache/trace sinh trước bản sửa.

### Cải tiến sau Vòng Sơ tuyển

Sau sơ tuyển, đội bổ sung định danh runtime/tài nguyên, siết kiểm tra cache/resume và lời gọi provider, đồng thời ghi nhận các giai đoạn trên đường xử lý thực tế. Hợp đồng kết quả Q&A được chuẩn hóa để phân biệt đáp án đủ bằng chứng với trường hợp cần người kiểm tra, không đủ bằng chứng, placeholder hoặc câu từ chối; kiểm tra áp dụng trên các đường replay/export liên quan. Đội cũng chuẩn bị quy trình ground truth do người xác minh, tách validation và sealed held-out trước thử nghiệm retrieval tiếp theo. Bộ đánh giá chưa hoàn tất nên chưa dùng để đưa ra kết quả hiệu năng mới; các thay đổi này không diễn giải lại điểm sơ tuyển [6].

<!-- PAGEBREAK -->

## 5 Quy trình thi và kết quả sơ tuyển

Trong sơ tuyển, người vận hành xem ảnh từ ứng viên hệ thống để kiểm chứng bằng mắt, loại bỏ hoặc xếp hạng lại. Một số truy vấn cần tìm thêm video/frame ngoài danh sách ban đầu, nên quy trình còn có tìm kiếm bổ sung thủ công.

Với một số truy vấn, người vận hành tham khảo thêm ChatGPT và Claude bên ngoài pipeline để hỗ trợ suy luận hoặc đề xuất answer/video/frame. Một số đề xuất từ các công cụ này được người vận hành lựa chọn sử dụng khi hoàn thiện submission. Các phiên hỗ trợ bên ngoài được tách biệt với LLM/VLM adapter tích hợp trong hệ thống.

*Bảng 2. Kết quả các submission cuối tại ba đợt Vòng Sơ tuyển.*

| Đợt | Ngày thi | Điểm submission cuối |
| --- | --- | --- |
| 1 | 21/08/2026 | 8,6 / 13 |
| 2 | 28/08/2026 | 13,6 / 15 |
| 3 | 04/09/2026 | 11,8 / 17 |

Các điểm này phản ánh toàn bộ quy trình thi có hỗ trợ người vận hành, gồm retrieval, kiểm chứng/xếp hạng lại, tìm kiếm bổ sung thủ công và hỗ trợ AI bên ngoài khi được sử dụng. Chúng không phải benchmark truy xuất thuần tự động của engine.

## 6 Giới hạn và hướng phát triển

Phép đo chẩn đoán cho thấy vẫn có truy xuất bỏ sót và ứng viên đúng video nhưng sai frame. Q&A có thể thiếu bằng chứng hoặc sinh câu từ chối, còn TRAKE có thể phải nội suy khi thiếu sự kiện. Ground truth chưa xác minh đầy đủ tiếp tục giới hạn đánh giá độc lập. Các bước tiếp theo tập trung vào những lỗi này.

1. **Đánh giá retrieval và định vị riêng.** Hoàn thiện ground truth được kiểm bằng mắt, đo recall theo top-K và độ đúng frame trên tập giữ riêng; dùng ablation để quyết định thay đổi fusion, tập ứng viên hoặc xếp hạng lại. Nhãn từ submission có hỗ trợ cần được xác minh độc lập trước khi dùng đánh giá.
2. **Giảm suy luận thiếu bằng chứng.** Cải thiện routing Q&A theo kiểu câu hỏi và chọn bằng chứng trước khi gọi model; với TRAKE, phân biệt vị trí có bằng chứng với vị trí nội suy. Đo tác động đồng thời lên chất lượng và thời gian xử lý, thay vì chỉ giảm số request.
3. **Duy trì kiểm tra phát hành.** Kiểm tra xuyên suốt câu từ chối, bằng chứng cũ và export; diễn tập trên batch sạch và kiểm tra hồi quy theo task trước khi đóng băng. Báo riêng lỗi format, sai nội dung và thiếu tín hiệu retrieval.
4. **So sánh trong điều kiện được kiểm soát.** Khóa truy vấn, ground truth, bản dịch, model, dữ liệu/index, cấu hình và scorer trước mỗi phép so sánh; dùng cùng quy trình runtime/cache và chạy lại baseline khi tài nguyên thay đổi.

Kiến trúc dùng chung giúp cô lập lỗi theo tầng và kiểm tra thay đổi trước vận hành. Hướng phát triển là nâng độ tin cậy, khả năng tái lập và mức tự động hóa của hệ thống, dựa trên đánh giá được kiểm chứng.

## Tài liệu tham khảo

[1] Radford và cộng sự. Learning Transferable Visual Models From Natural Language Supervision. ICML, 2021. https://proceedings.mlr.press/v139/radford21a.html

[2] Cormack, Clarke và Büttcher. Reciprocal Rank Fusion outperforms Condorcet and individual Rank Learning Methods. SIGIR, 2009. https://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf

[3] Đội Thanh Nghệ. Kiểm kê dữ liệu và kiểm tra không gian CLIP Batch 1, 21/08/2026. Hồ sơ đánh giá và kỹ thuật nội bộ.

[4] Đội Thanh Nghệ. Đo multi-anchor và kiểm tra lại single-anchor, 27–28/08/2026, dress25, 19 KIS. Hồ sơ đánh giá và kỹ thuật nội bộ.

[5] Đội Thanh Nghệ. Diễn tập đợt 2 và kiểm tra export/preflight trên nhánh sửa, 28/08–01/09/2026. Hồ sơ đánh giá và kỹ thuật nội bộ.

[6] Đội Thanh Nghệ. Hồ sơ cải tiến khả năng tái lập, hợp đồng kết quả Q&A và quy trình đánh giá sau sơ tuyển, 11-12/09/2026. Tài liệu kỹ thuật nội bộ.
