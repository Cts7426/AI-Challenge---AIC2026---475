---
title: "Frontend & UI Rules"
---

# 🎨 Quy Tắc UI & Frontend

Dự án này sử dụng 2 hệ thống giao diện với mục đích hoàn toàn khác biệt:

1. **Frontend Cuộc Thi (Production):**
   - Nằm tại thư mục `frontend/` (ví dụ `app.js`).
   - Yêu cầu: Sử dụng Vanilla JS/HTML. **Tuyệt đối không dùng Framework** như React/Vue để đảm bảo hệ thống cực kỳ ổn định trong môi trường thi đấu.
   - Bắt buộc hỗ trợ đầy đủ phím tắt thao tác nhanh.
2. **Debug UI (Internal/Dev):**
   - Nằm tại `app/debug_ui.py`.
   - Sử dụng Streamlit, chỉ với mục đích gán nhãn và kiểm tra chéo nội bộ.
   - Yêu cầu: Cấm nhét logic search/retrieval cốt lõi vào file này.
