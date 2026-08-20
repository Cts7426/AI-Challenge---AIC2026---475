# Architecture 03: LLM Integration (Tích hợp Trí tuệ Nhân tạo)

Tất cả truy vấn gọi lên AI (Dịch thuật, Rút gọn câu hỏi, Q&A) ĐỀU PHẢI ĐI QUA `backend/llm/adapter.py`. 

## 1. Đa Backend & Cấu hình
Adapter này hỗ trợ chuyển đổi linh hoạt bằng cấu hình môi trường:
- `LLM_BACKEND=api`: Dùng Anthropic Claude (Default: `claude-opus-5`). Hỗ trợ output JSON qua `output_config.format`. Nhiệt độ (Temperature) bị bỏ qua.
- `LLM_BACKEND=gemini`: Dùng Google Gemini (Default: `gemini-2.5-flash`). Hỗ trợ đẩy ảnh và giữ nguyên cài đặt Temperature. Xử lý lược bỏ các từ khoá JSON Schema phức tạp (additionalProperties) để tương thích với Gemini.
- `LLM_BACKEND=local`: Dùng Ollama (`qwen2.5:7b-instruct`). Giải pháp backup khi thi Offline.

## 2. Hệ thống Cache (Chống lãng phí tiền bạc)
Lúc thi/dev thường xuyên search lặp lại các câu hỏi giống nhau. `adapter.py` sử dụng SHA-256 Hash để bắt chính xác các request lặp lại (dựa trên prompt, schema, model, parameter và byte của hình ảnh). Cache được lưu tại đĩa. Tiết kiệm 100% thời gian chờ và tiền bạc cho các câu hỏi trùng lặp.

## 3. Quản lý Lỗi (Retry logic)
- **Lỗi Mạng/Rate Limit (429/500):** Được xử lý mặc định bằng SDK (Anthropic `max_retries` / Gemini qua `tenacity`). Adapter cũng bọc thêm 1 lớp retry khi Gemini bị 503 ngâm lâu.
- **Lỗi JSON hỏng:** Nếu yêu cầu trả JSON mà LLM trả về Text, SDK sẽ coi đó là "Thành công". Adapter tự động bắt lỗi parse JSON và kích hoạt Retry ép Model sinh lại nội dung.

## 4. Ghi nhận chi phí (Usage Tracking)
Mọi lượt gọi LLM đều được đếm Token vào/ra + Token hit-cache để quy đổi ra USD. Hàm `print_usage()` hiển thị chi phí vào cuối ngày chạy dev.
