# Architecture 04: Evaluation Loop (Đo lường & Chấm điểm)

Quy trình đánh giá thuật toán chạy bằng script `dev_set/tools/run_evaluation.py`. 

## 1. Chia tập Test & Giới hạn
Hệ thống có 2 tập Dev:
- **Tập Tune:** Dùng để test tính năng hàng ngày (Không giới hạn).
- **Tập Holdout:** Dùng để đánh giá độ chính xác thực tế trước khi đi thi. HỆ THỐNG GIỚI HẠN CHỈ CHO PHÉP CHẠY 5 LẦN (tránh trường hợp model Overfit vào tập test).

## 2. Streaming Output (Chống sập dữ liệu)
Thuật toán đo đếm chạy hàng ngàn câu hỏi. Nếu tới câu 999 bị crash, cách làm cũ (lưu vào biến Array rồi cuối cùng ghi ra file) sẽ bốc hơi toàn bộ công sức.
Kiến trúc ở đây ép mọi vòng lặp ghi chèn `flush()` theo cơ chế JSONL (Mỗi câu trả lời ghi ngay ra dòng mới trong đĩa). Khi chạy lại lệnh `run_evaluation` với tham số `--resume`, hệ thống sẽ skip tự động những câu đã ghi thành công trong file JSONL.

## 3. Số liệu Đo lường (Metrics)
Báo cáo đánh giá (Evaluation) tự sinh ra các cột: `Recall@1`, `Recall@5`, `Recall@20`, `Recall@50`, `Recall@100`. 
- **Tại sao?** Nếu Recall@100 cao mà Recall@1 thấp -> Vấn đề do Thuật toán Ranking kém. Nếu Recall@100 cũng lẹt đẹt -> Vector Search quá tệ. Phải có đủ 5 cột mới biết bệnh do đâu.

## 4. Cơ chế Failure Class
Khi 1 truy vấn fail (R@100 < 1.0), nó sẽ phân tích nhánh nào có lỗi (F0_CRASH, F_QA_RETRIEVAL_FAILED, F_QA_REASONING_FAILED...). Cực kỳ hữu dụng để khoanh vùng debug.
