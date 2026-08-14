# BLOCKERS

## 1. Bridge ShotHit
- **Vấn đề**: Hàm `backend.retrieval.search.search()` trả về `keyframe_id` (cùng với `shot_id` và `ranks`). Tuy nhiên, module `allocator` cần nhận vào đối tượng `ShotHit` có trường `best_keyframe_id`.
- **Thực trạng**: Hiện không có module nào làm nhiệm vụ chuyển đổi (bridge) từ kết quả search sang allocator. Hàm `_chia_slot` trong `run_minimal.py` đang làm chức năng bypass allocator hoàn toàn.
- **Hành động**: Chủ sở hữu allocator cần viết API nhận vào trực tiếp `keyframe_id` và `shot_id` hoặc viết một bridge chuẩn để gọi từ bộ đo Dev Set. Bộ đo Dev Set KHÔNG tự viết bridge để tránh can thiệp vào logic hệ thống.
- **Tạm thời**: `dev_set/tools/run_evaluation.py` mượn lại `_chia_slot` của `run_minimal.py` và có log cảnh báo.
