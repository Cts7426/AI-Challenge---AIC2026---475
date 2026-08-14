# Hướng dẫn viết query, gán nhãn, chạy đánh giá cho bộ Dev Set.

## Quy tắc viết query
- **Tách vai**: Người viết query và người chạy thử phải khác nhau (xem phân công).
- **Ngoại lệ "3 Không"**: Cần 20% query nhắm vào chữ (`has_text`) và 20% lời nói (`has_speech`).
- **Đa dạng độ khó**: 1/3 dễ, 1/3 trung bình, 1/3 khó.
- **Số lượng tối thiểu**: KIS 25/10, QA 20/8, TRAKE 15/6 (tune/holdout).

## Cấu trúc thư mục
- `queries/`: Chứa các query được định nghĩa theo `schema.py`.
- `ground_truth/`: Chứa nhãn đúng (GT).
- `gt_preview/`: Chứa ảnh trích xuất của GT để kiểm tra bằng mắt (kết quả của `check_gt.py`).
- `results/`: Kết quả chạy của `run_evaluation.py`.
- `tools/`: Chứa các script đo đạc và kiểm tra.

## Các lệnh thường dùng
```bash
# Kiểm tra GT (Bước 2)
PYTHONPATH=. .venv/bin/python dev_set/tools/check_gt.py --split tune

# Chạy đánh giá (Bước 4)
PYTHONPATH=. .venv/bin/python dev_set/tools/run_evaluation.py --split tune

# Xem báo cáo (Bước 5)
PYTHONPATH=. .venv/bin/python dev_set/tools/evaluate.py --run-dir dev_set/results/run_XXX
```
