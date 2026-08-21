---
title: "Story 01-2: Gọi QA/TRAKE pipeline từ API"
status: "TODO"
---

# 🚀 Story 01-2: Gọi QA/TRAKE pipeline từ API

**Ngữ cảnh:** `qa_pipeline()` và `trake_stage1()` chỉ chạy trên terminal. Chưa có luồng API chính để nối các chức năng này với UI nộp bài.
**Việc cần làm:**
1. Tạo một endpoint hoặc mở rộng endpoint `/search` trong `backend/api/main.py`.
2. Kiểm tra `query_type` và gọi đúng pipeline tương ứng.
3. Đưa kết quả qua `allocate()` rồi trả JSON.
