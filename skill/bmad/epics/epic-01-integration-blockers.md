---
title: "Epic 01: Nối Ống & Khai Thông Pipeline"
status: "TODO"
---

# 🚀 Epic 01: Nối Ống & Khai Thông Pipeline

**Bối cảnh:** Toàn bộ các hệ thống cốt lõi đã chạy xanh (Search A2.x, Allocator D3.1, QA/TRAKE C3.x). Tuy nhiên, chúng đang chạy độc lập qua các script CLI mà chưa kết nối vào luồng chạy chính. Điều này gây lãng phí toàn bộ tính năng "Đào sâu slot" và "Xen kẽ" của Allocator D3.1 cũng như pipeline chuyên sâu của QA/TRAKE.

**Mục tiêu:**
Đảm bảo khi gọi một lệnh chạy từ đầu đến cuối (`run_minimal.py` hoặc gọi API), hệ thống phải đi qua đúng tất cả các module đã được viết, trả ra bài nộp hoàn chỉnh với 100 dòng.

## 📝 Danh sách Stories
- [ ] **Story 01-1:** Nối `run_minimal.py` với `backend.slot.allocate()`. (Người phụ trách: Thạch)
- [ ] **Story 01-2:** Mở API / Gọi thẳng QA/TRAKE pipeline từ `backend/api/main.py`. (Người phụ trách: Thi)
