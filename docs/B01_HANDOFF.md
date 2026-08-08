# TỔNG KẾT & BÀN GIAO DỮ LIỆU PHASE B (DATA PIPELINE)

Tài liệu này được viết bởi **Công Lý (Data Engineer)** nhằm bàn giao toàn bộ dữ liệu đã được tinh chế cho Team Backend, Team AI và Team UI. 

**Mục tiêu tối thượng:** Các team khác KHÔNG CẦN CHẠY LẠI bất kỳ script xử lý dữ liệu nào (trong thư mục `preprocessing/`). Các bạn **chỉ cần đọc trực tiếp các file `.parquet`** trong `data/derived/` để xây dựng Backend và model AI.

---

## 1. Hệ sinh thái Dữ liệu (Các file `.parquet` cần dùng)

Toàn bộ "tài sản" của Phase B nằm gọn trong thư mục `data/derived/`:

- `video_info.parquet` (B0.1): Chứa thông tin gốc của 873 video (duration, fps, độ phân giải...). Khóa chính: `video_id`.
- `frame_map.parquet` & `clip_row_index.parquet` (B0.1): Từ điển ánh xạ từ `frame_idx` tuyệt đối ra thời gian thực tế để chích xuất.
- `shots.parquet` (B1.1): Kết quả phân đoạn Video thành các Shot (TransNetV2). Chứa `start_frame`, `end_frame` và `rep_kf_id` cho mỗi `shot_id`.
- `keyframes.parquet` (B1.2): Tập hợp toàn bộ khung hình chốt (mật độ 1 FPS). Chứa `kf_id` chuẩn của hệ thống (ví dụ: `L22_V004_0000009`). Tổng cộng ~343,996 dòng.
- `asr.parquet` (B1.3): Các đoạn hội thoại bóc băng bằng Whisper. Đã được quy đổi sang `start_frame` và `end_frame`.
- `ocr.parquet` (B1.4): Dữ liệu nhận diện chữ viết (PaddleOCR) trên các frame đại diện của Shot (`rep_kf_id`).
- `docs_bm25.parquet` (B1.7): **Cơ sở dữ liệu cốt lõi cho Tìm kiếm Văn bản (KIS)**. Cứ 1 dòng tương ứng với 1 Keyframe, cột `doc_text` chứa trọn bộ: Metadata (Title/Desc) + OCR + ASR (giới hạn trong ±3 giây quanh keyframe đó).

---

## 2. Nhật ký Thực thi (Chi tiết các Task nhánh B)

### B0.1: Nền móng Video Info & Frame Map
- Xác minh được bộ dữ liệu chuẩn gồm **873 video hợp lệ**. Loại bỏ các video ma hoặc video mất gốc.
- Đã giải quyết bài toán ánh xạ frame vật lý bằng `frame_map.parquet`, đảm bảo không bao giờ trích xuất sai thời gian gốc (Lỗi thường gặp làm mất trắng điểm).

### B1.1: Shot Segmentation
- Chia nhỏ 873 video thành hơn 100,000 shots. 
- Các shot dài hơn 60s đều đã bị chặt bớt thành các đoạn 30s để tránh hiện tượng loãng nội dung.

### B1.2: Keyframe Extraction
- Mật độ chốt là **1 FPS** (không dùng 2 FPS hay 5 FPS để tiết kiệm không gian).
- Khóa `kf_id` được định nghĩa lại thành dạng `[VideoID]_[frame_idx_tuyệt_đối]` (Ví dụ: `L22_V004_0000009`), vứt bỏ hoàn toàn chuẩn đặt tên ngu ngốc theo số đếm (`0000.jpg`) của BTC.

### B1.3: Tích hợp ASR (Whisper)
- Audio được tách riêng khỏi Video trước để giảm tải.
- Toàn bộ kết quả ASR đã được quy ngược lại khung Frame Index tuyệt đối.

### B1.4: Tích hợp Text Recognition (PaddleOCR)
- Để tránh quá tải, OCR chỉ được chạy trên `rep_kf` (ảnh đại diện) của mỗi shot và các keyframe vượt qua bộ lọc Text Detector.
- Chữ tiếng Việt đã được làm sạch dấu bằng thuật toán nội bộ nhưng vẫn giữ cột `text_raw`.

### B1.7: Hợp nhất Document cho BM25 (docs_bm25)
- Một kiệt tác xử lý Join Time-Series bằng pandas. 
- Mọi mảng Text (OCR, ASR) đều bị ép ngược về từng Keyframe.
- **Quy tắc vàng ASR ±3s**: Một khung hình chỉ chứa câu nói của người dùng phát ra trong vòng 3 giây trước và sau nó.
- Đã vượt qua vòng Audit L3 (Tra từ khóa "naky" siêu hiếm và trúng phóc Frame chứa OCR đó).

---

## 3. Các Quy tắc Bất biến (Invariants) cho Team Backend/AI

> [!WARNING]
> Những quy tắc máu thịt Đội trưởng bắt buộc Team Backend/AI phải tuân thủ để tránh ăn 0 điểm:

1. **Khóa liên kết duy nhất**: Khóa join giữa các bảng trong hệ thống (Milvus, Elasticsearch, Parquet) CHỈ ĐƯỢC PHÉP dùng `video_id` và `frame_idx` (hoặc `kf_id` chuẩn hóa của chúng ta). 
2. **Cấm dùng Index BTC**: TUYỆT ĐỐI KHÔNG BAO GIỜ dùng số thứ tự file keyframe của BTC (0000.jpg, 0001.jpg) làm khóa tìm kiếm hoặc chích frame xuất ra file submit.
3. **Về Vector (Nhiệm vụ tương lai)**: Bắt buộc L2-Normalize vector ở CẢ 2 PHÍA (Query và Database) trước khi Index và Query. Hệ đo lường trong Milvus là COSINE.
4. **LLM Adapter**: Gọi duy nhất qua hàm `llm()` tại `backend/llm/adapter.py`. Tuyệt đối cấm team AI import thẳng thư viện `anthropic` hay `openai` vào code logic.

---

## 4. Hướng dẫn sử dụng cho Team Backend

Các file Parquet Data hiện đã đóng băng. Để đưa lên hệ thống tìm kiếm (Elasticsearch), Team Backend chỉ việc chạy các lệnh chuẩn bị sẵn:

```bash
# Nạp Metadata
python -m backend.indexing.load_metadata --recreate
# Nạp ASR
python -m backend.indexing.load_asr --recreate
# Nạp OCR
python -m backend.indexing.load_ocr --recreate
# (Sắp tới sẽ có lệnh nạp BM25 riêng)
```

**Thanh lý Code rác:** 
Những thứ trong thư mục `preprocessing/` giờ chỉ mang tính chất lưu trữ thuật toán của Data Engineer. Backend đừng gọi vào đó nhé! Toàn bộ mồ hôi nước mắt của tôi đã đọng lại thành mấy file `.parquet` kia rồi! Chúc các anh em Backend và AI xây tháp thành công!
