# Review PP-H01

Review độc lập, chỉ đọc, qua skill `requesting-code-review`; xử lý phản hồi theo `receiving-code-review`. Không review hai thay đổi có từ trước ở `.claude/launch.json` và `scripts/txt_to_run_queries.py`.

## Findings và bằng chứng đóng

| Finding | Sửa trong H01 | Kiểm tra |
|---|---|---|
| Hash bằng nhau của hai identity thiếu vẫn có thể được nhận | `require_reproducible` kiểm completeness riêng, chặn DB/asset/content digest thiếu | `identity_gate_red.log`, `review_fixes_green.log` |
| Mapping chỉ kiểm số frame, chưa kiểm video và vị trí event TRAKE | Tra video từ parquet, kiểm từng cặp keyframe/frame theo event index; không sửa localization | `review_mapping_assets_red.log`, `review_fixes_green.log` |
| Identity bỏ ảnh VLM và manifest archive vận hành | Thêm `asset_identity` hash pixel, trạng thái chưa hash chặn paired; thêm manifest vận hành Batch1 | Cùng logs trên; `asset_identity.json` là capture riêng |
| Cache sinh sau query đầu chưa được bảo vệ khi resume | Ghi `cache_after` và hash cùng dòng checkpoint; resume kiểm từng snapshot với cache hiện tại; kiểm lại sau run | `reviewer_final_red.log`, `reviewer_final_green.log` |
| Weights CLIP có thể bị xem là đủ cho SigLIP2 | Ghi encoder đã capture và encoder yêu cầu; SigLIP2 thiếu collector thành gap chặn baseline | Cùng logs trên |

Tự rà soát còn bắt được: trace bị mất ở worker TRAKE, lỗi OCR probe bị ghi nhầm zero-hit và thiếu runtime bị nuốt thành translation fallback. Các test RED/GREEN ở `h01_review_red.log` và `h01_review_green.log` chứng minh lỗi trước/sau sửa.

Xác nhận cuối của reviewer: hai findings cuối đã được xử lý trong phạm vi sửa; không còn finding cụ thể ở hai phần này. Reviewer không chạy lại suite và không xác nhận baseline live. Không thấy đổi thuật toán ranking trong diff đã đọc.

Verdict baseline: **DO NOT PROMOTE** cho đến khi operator chọn model và có run live dưới identity đủ điều kiện.
