---
title: "Architecture Rules"
---

# 🏗️ Quy Tắc Kiến Trúc AIC2026

Các Agent KHÔNG ĐƯỢC PHÉP vi phạm các bất biến sau:

1. **Giao tiếp với LLM:** 
   - Cấm gọi trực tiếp Anthropic, Google hay OpenAI SDK từ bất kỳ file nào.
   - Bắt buộc phải qua `backend/llm/adapter.py`.
2. **Giới hạn 77 Token của CLIP:**
   - Khi xử lý chuỗi truy vấn (đặc biệt là TRAKE), tuyệt đối không nối chuỗi dài rồi đẩy vào Search. 
   - Phải chia nhỏ thành các sự kiện (events) và search song song để tránh bị CLIP cắt cụt âm thầm.
3. **Mức độ phụ thuộc:**
   - Slot Allocator (`backend.slot.allocate`) là điểm duy nhất được quyền chốt danh sách 100 frame_id cuối cùng.
   - Cấm các script bên ngoài tự ý gán frame_id giả (như độn frame 0).
