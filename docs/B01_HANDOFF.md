# PHASE B DATA PIPELINE: BÁO CÁO KỸ THUẬT VÀ ĐẶC TẢ DỮ LIỆU CHUẨN

Tài liệu này là **đặc tả kỹ thuật (Technical Specification)** cho toàn bộ dữ liệu đã được xử lý trong Phase B của dự án AIC 2026. Bất kỳ AI Agent, Kỹ sư Data, Kỹ sư Backend hay Frontend nào khi tương tác với dữ liệu của dự án đều **PHẢI** đọc và tuân thủ các quy chuẩn trong tài liệu này.

Tất cả các tệp dữ liệu được lưu dưới định dạng **Parquet** trong thư mục `data/derived/` để đảm bảo tốc độ đọc/ghi nhanh và bảo toàn cấu trúc kiểu dữ liệu.

---

## 1. NGUYÊN TẮC THIẾT KẾ & CÁC BẤT BIẾN (INVARIANTS)

Trước khi đi vào cấu trúc cụ thể, các hệ thống downstream (Elasticsearch, Milvus, Q&A Pipeline) cần nắm vững các bất biến sau để không làm sai lệch tính nguyên vẹn của dữ liệu:

1. **Chuẩn `kf_id` Mới (Mật độ 1 FPS)**: 
   - Định dạng: `{video_id}_{frame_idx:07d}` (Ví dụ: `L22_V004_0000009`).
   - Đây là khóa chính (Primary Key) liên kết mọi thông tin với một khung hình. Tuyệt đối **KHÔNG** sử dụng số thứ tự file keyframe (ví dụ `0000.jpg`, `0001.jpg`) của BTC cung cấp vì đó là số đếm, không phản ánh chỉ số frame vật lý. Sai lầm này sẽ dẫn đến việc trích xuất sai khung hình khi nộp bài.

2. **Ánh xạ Thời gian Tuyệt đối (Frame Map)**:
   - Việc chuyển đổi từ `frame_idx` sang `pts_time` (giây) hoặc ngược lại **bắt buộc** phải tra cứu thông qua `frame_map.parquet`. Không được dùng công thức `frame_idx / fps` vì video thực tế có Drop-frame (VFR) gây trượt thời gian (Drift).

3. **Cơ chế Hợp nhất Context cho BM25 (Join Logic)**:
   - **ASR**: Mỗi keyframe chỉ chứa lượng text ASR của các phân đoạn âm thanh nằm trong cửa sổ **±3 giây** (tức `±3.0 * fps`) xung quanh khung hình đó.
   - **OCR**: Nhận diện OCR ban đầu được chạy trên ảnh đại diện của Shot (`rep_kf`). Khi gom vào Keyframe, OCR được map ngược về `shot_id` qua `merge_asof` (hướng backward), sau đó lan tỏa (broadcast) cho tất cả các keyframe thuộc Shot đó. Điều này đảm bảo tính liên tục của văn bản mà không cần tốn chi phí chạy OCR trên toàn bộ frame.

---

## 2. ĐẶC TẢ LƯỢC ĐỒ DỮ LIỆU (SCHEMA SPECIFICATIONS)

### 2.1. Nền móng Video (`video_info.parquet` & `frame_map.parquet`)
*Tạo bởi Task B0.1*

**`video_info.parquet`** (Thông tin vĩ mô của 873 Video)
- `video_id` (string): Khóa chính, định dạng `L{N}_V{M}` (VD: `L21_V001`).
- `width`, `height` (int32): Độ phân giải gốc.
- `fps` (float32): Tốc độ khung hình trên giây.
- `duration` (float32): Thời lượng video tính bằng giây.
- `frame_count` (int32): Tổng số khung hình vật lý (lấy từ stream video).

**`frame_map.parquet`** (Bản đồ ánh xạ thời gian)
- `video_id` (string): Khóa ngoại.
- `frame_idx` (int64): Chỉ số khung hình vật lý (bắt đầu từ 0).
- `pts_time` (float32): Thời gian hiển thị (Presentation Time) thực tế theo giây. Dùng mốc này để gọi `ffmpeg` chích xuất frame.

### 2.2. Phân đoạn Video (`shots.parquet`)
*Tạo bởi Task B1.1 qua TransNetV2*
- `video_id` (string)
- `shot_id` (string): Định dạng `{video_id}#s{index:04d}` (VD: `L21_V001#s0000`).
- `start_frame` (int64): Frame bắt đầu của shot.
- `end_frame` (int64): Frame kết thúc của shot. Đảm bảo `<start_frame` của shot kế tiếp.
- `rep_kf_id` (string): ID của Keyframe đại diện (Representative Keyframe). 
*(Ghi chú: Để chống loãng nội dung, bất kỳ shot nào dài quá 60s đều bị force split thành các sub-shot 30s).*

### 2.3. Khung hình Chốt (`keyframes.parquet`)
*Tạo bởi Task B1.2*
- `video_id` (string)
- `shot_id` (string): Khóa ngoại trỏ về `shots.parquet`.
- `kf_id` (string): Khóa chính chuẩn hóa (VD: `L22_V004_0000009`).
- `frame_idx` (int64): Frame Index tuyệt đối.
- `path` (string): Đường dẫn tương đối lưu file ảnh trên đĩa cứng nội bộ. Mật độ lấy là 1 FPS (giới hạn min 2, max 20 kf mỗi shot).

### 2.4. Dữ liệu m thanh & Chữ viết (`asr.parquet` & `ocr.parquet`)
*Tạo bởi Task B1.3 & B1.4*

**`asr.parquet`** (PhoWhisper)
- `video_id` (string)
- `seg_id` (int): ID phân đoạn thoại trong video.
- `start_s`, `end_s` (float32): Thời gian bắt đầu/kết thúc câu nói (giây).
- `start_frame`, `end_frame` (int64): Đã được quy đổi sang frame qua `frame_map`.
- `text_vi` (string): Văn bản thô được gỡ băng.

**`ocr.parquet`** (PaddleOCR)
- `video_id` (string)
- `kf_id` (string): Sử dụng ID cũ của BTC (`L21_V001#k0001`) đại diện cho `rep_kf`. 
- `frame_idx` (int64): Frame tuyệt đối của khung ảnh được OCR.
- `text_raw` (string): Văn bản thô PaddleOCR trả về.
- `text_clean` (string): Đã loại bỏ dấu tiếng Việt (lowercase) cho Elastic.
- `n_boxes` (int): Số lượng bounding box text.
- `avg_conf` (float): Độ tin cậy trung bình của các text box.

### 2.5. Cơ sở dữ liệu Tìm kiếm Trung tâm (`docs_bm25.parquet`)
*Tạo bởi Task B1.7 - Trái tim của Textual Search Engine*

Chứa 343,996 Document. Mỗi Document đại diện cho một Khung hình (`kf_id`), tổng hợp toàn bộ tri thức tĩnh (OCR) và động (ASR, Metadata) xung quanh khung hình đó.
- `video_id` (string)
- `shot_id` (string)
- `kf_id` (string)
- `frame_idx` (int64)
- `ocr_text` (string): Toàn bộ text_clean của OCR thuộc về Shot này.
- `doc_text` (string): Dữ liệu khổng lồ gộp chung theo format:
  ```
  [title] Tiêu đề video
  [desc] Mô tả (metadata) video
  [asr] Nội dung thoại ±3s
  [ocr] Văn bản chữ trên màn hình
  ```
Toàn bộ `doc_text` đã được `.lower()` để tương thích tốt nhất với bộ Analyzer của Elasticsearch.

---

## 3. HƯỚNG DẪN TÍCH HỢP CHO HỆ THỐNG DOWNSTREAM

### Dành cho Backend (Tạo Index Elasticsearch)
Để đồng bộ dữ liệu lên Elasticsearch, Team Backend cần thực thi chuỗi lệnh Indexing thông qua các script đã được chuẩn bị sẵn:
```bash
python -m backend.indexing.load_metadata --recreate
python -m backend.indexing.load_asr --recreate
python -m backend.indexing.load_ocr --recreate
```
*Script `load_objects` và `load_clip` sẽ được bổ sung khi Phase B hoàn tất toàn bộ các AI model còn lại.*

### Dành cho AI Agent & RAG Pipeline (Task C3.1 / C3.2)
Khi xử lý các Pipeline Trả lời Câu hỏi (Q&A) hoặc TRAKE:
1. Đọc context từ `docs_bm25.parquet` qua Elasticsearch.
2. Trích xuất thời gian hoặc ngữ cảnh rộng hơn bằng cách query `asr.parquet` thông qua `frame_idx` trong khoảng `[frame_idx - fps*N, frame_idx + fps*N]`.
3. Khi ra quyết định cuối cùng, kết quả Frame trả về (để Submit) phải lấy trực tiếp từ `frame_idx` của `docs_bm25.parquet`.

> **LỜI KẾT TỪ DATA ENGINEER:** Toàn bộ pipeline đã được đóng gói và kiểm thử Unit Test nghiêm ngặt (pass toàn bộ Audit L1-L3). Tuyệt đối không thay đổi logic Join Data mà không có sự thông qua của Team Data.
