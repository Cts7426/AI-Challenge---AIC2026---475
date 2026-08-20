# Architecture 01: Data Pipeline (Indexing & Vector Store)

Tài liệu này mô tả cách luồng dữ liệu (Data Pipeline) hoạt động, từ video gốc đến khi lưu vào cơ sở dữ liệu.

## 1. Hệ quản trị Cơ sở dữ liệu (DBMS)
Hệ thống sử dụng kiến trúc lai (Hybrid Search) với 2 DB chính:
- **Milvus (Vector DB):** Lưu trữ đặc trưng hình ảnh (CLIP features).
  - Metric sử dụng: `COSINE`.
  - Bắt buộc phải chuẩn hoá L2 (L2-normalize) cả hai đầu (lúc index và lúc search) vì `COSINE` trong Milvus thực chất là Inner Product sau khi chuẩn hoá.
  - Tham số tìm kiếm: `ef` (trong HNSW) phải luôn lớn hơn hoặc bằng `limit`.
- **Elasticsearch (Text DB):** Lưu trữ 4 loại văn bản:
  - `metadata`: Thông tin video (title, description, keywords).
  - `objects`: Nhãn sự vật trong ảnh (tiếng Anh).
  - `ocr`: Chữ trong ảnh.
  - `asr`: Lời nói trong video (kèm timestamp).

## 2. Khoá chính (Primary Keys)
- `keyframe_id` (Ví dụ: `L21_V001#k0001` hoặc `L21_V001_0000090`): Là khoá ngoại liên kết giữa Milvus và Elasticsearch. MỌI bảng bắt buộc phải có khoá này.
- **KHÔNG ĐƯỢC NHẦM:** Số thứ tự cuối của `keyframe_id` (ví dụ `0000090`) KHÔNG PHẢI là `frame_idx` thật sự trong video. Để lấy `frame_idx` nộp cho BTC, bắt buộc phải tra qua từ điển `frame_map`.

## 3. Chống trùng lặp (Idempotent Loaders)
Các script loader (`load_metadata.py`, `load_clip.py`...) đều có tính chất "idempotent". Nghĩa là chạy 1 lần hay 100 lần đều ra kết quả y hệt (không sinh rác). Update dựa theo `_id` hoặc `keyframe_id`. Dữ liệu mới ghi đè dữ liệu cũ.
