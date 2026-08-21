---
title: "Epic 02: Hoàn thiện Devset & Tuning (D4.1)"
status: "TODO"
---

# 🚀 Epic 02: Hoàn thiện Devset & Tuning

**Bối cảnh:** Thư mục dev_set hiện đang rỗng ảnh keyframe, khiến module `eval.py` (E4.2) không có đủ dữ liệu để mô phỏng và chấm điểm. Phải hoàn thiện dev_set mới có cơ sở để Tune tham số `SLOT_BUDGET` và ngưỡng `_object_count`.

**Mục tiêu:**
Khởi tạo dữ liệu chấm, chạy được Tool mô phỏng điểm (D3.5) và tối ưu hóa hệ thống.

## 📝 Danh sách Stories
- [ ] **Story 02-1:** Bổ sung ảnh Keyframe cho `dev_set/`. (Người phụ trách: Công Lý)
- [ ] **Story 02-2:** Tuning `search_weights.py` và bảng `SLOT_BUDGET` (D4.1).
- [ ] **Story 02-3:** Xây dựng Mô phỏng điểm D3.5 (Tối đa hóa ROI).
