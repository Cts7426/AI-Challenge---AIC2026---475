---
title: "Story 01-1: Nối `run_minimal.py` với `allocate()`"
status: "TODO"
---

# 🚀 Story 01-1: Nối `run_minimal.py` với `allocate()`

**Ngữ cảnh:** Script `run_minimal.py` hiện tại tự viết hàm `_chia_slot` và `_don_cho_du`, bypass hoàn toàn `allocate()` của D3.1. Việc này làm mất các tối ưu đào sâu và xen kẽ.
**Việc cần làm:**
1. Mở `run_minimal.py`.
2. Sửa hàm xử lý kết quả search để gọi thẳng `backend.slot.allocate(hits)`.
3. Bỏ các hàm chia slot thủ công cũ.
