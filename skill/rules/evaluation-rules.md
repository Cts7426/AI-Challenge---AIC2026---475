---
title: "Evaluation Rules"
---

# 📊 Quy Tắc Đánh Giá (Evaluation)

Việc đánh giá điểm trong hệ thống AIC2026 (nằm tại `app/eval.py` và `dev_set/tools/scoring.py`) tuân theo luật cực kỳ khắt khe của BTC:

1. **TRAKE R-Score:**
   - Cấm sử dụng bảng tính rút gọn (Bảng 6 ô) để tính điểm trực tiếp. 
   - TRAKE phải được tính bằng công thức toán học nội suy điểm lẻ: `(1/N) * sum( I(id_j in [s_j, e_j]) )`. Khớp theo ĐÚNG vị trí j.
   - Sai thứ tự thời gian = 0 điểm tuyệt đối.
2. **Q&A R-Score:**
   - Phải vượt qua 3 cửa tử: Đúng video, đúng khoảng frame, VÀ đúng `answer_text` về mặt ngữ nghĩa (qua `answer_match.py`).
   - Nếu LLM không đưa ra câu trả lời (trả về rỗng), lập tức bị từ chối cấp phát slot.
