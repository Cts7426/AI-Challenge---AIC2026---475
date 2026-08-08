# PHASE B DATA PIPELINE: BÁO CÁO KỸ THUẬT VÀ ĐẶC TẢ DỮ LIỆU CHUẨN

Tài liệu này là **đặc tả kỹ thuật (Technical Specification)** cho toàn bộ dữ liệu đã được xử lý trong Phase B của dự án AIC 2026. Bất kỳ AI Agent, Kỹ sư Data, Kỹ sư Backend hay Frontend nào khi tương tác với dữ liệu của dự án đều **PHẢI** đọc và tuân thủ các quy chuẩn trong tài liệu này.

Tất cả các tệp dữ liệu được lưu dưới định dạng **Parquet** trong thư mục `data/derived/` để đảm bảo tốc độ đọc/ghi nhanh và bảo toàn cấu trúc kiểu dữ liệu.

---

## 1. TỔNG QUAN HỆ THỐNG DỮ LIỆU
- **Mục đích**: Chuyển đổi dữ liệu thô (Video MP4, Audio WAV, Keyframe ảnh BTC) thành 7 file Parquet tiêu chuẩn trong `data/derived/` để phục vụ các module Elasticsearch, Milvus Vector Search, và VLM/LLM Q&A Pipeline.
- **Nguyên tắc thiết kế**: 
  - Toàn bộ dữ liệu được chuẩn hóa dưới dạng Parquet với Schema tĩnh (Strongly Typed).
  - Không có bất kỳ phụ thuộc nào vào code xử lý dữ liệu (`preprocessing/`) ở tầng runtime online (`backend/`).
  - Toàn bộ 7 file Parquet đều độc lập, liên kết với nhau bằng các khóa `video_id`, `shot_id`, `kf_id`, và `frame_idx`.

---

## 2. ĐẶC TẢ CHI TIẾT LƯỢC ĐỒ VÀ CẤU TRÚC 7 FILE PARQUET (`data/derived/`)

### 2.1 `video_info.parquet` (Tổng cộng: 873 dòng)
- **Nguồn gốc**: Được tạo từ bước phân tích metadata vĩ mô của 873 file video MP4 gốc.
- **Cấu trúc cột & Dtype**:
  - `video_id` (`object` / `string`): Mã video (VD: `L22_V010`, `L21_V001`).
  - `fps_num` (`int64`): Tử số tốc độ khung hình (VD: `25`).
  - `fps_den` (`int64`): Mẫu số tốc độ khung hình (VD: `1`). FPS thực tế = `fps_num / fps_den`.
  - `nb_frames_decoded` (`int64`): Tổng số frame vật lý được giải mã đầy đủ từ video stream (VD: `27276`).
  - `path` (`object` / `string`): Đường dẫn tương đối đến file MP4 gốc (VD: `data/raw/videos/videos_L22_a/L22_V010.mp4`).
  - `duration_sec` (`float64`): Thời lượng thực tế tính theo giây (VD: `1091.105669`).
  - `has_audio` (`bool`): `True` nếu video có luồng âm thanh, `False` nếu không tiếng.
  - `is_vfr` (`bool`): `True` nếu video là Variable Frame Rate, `False` nếu Constant Frame Rate.

### 2.2 `frame_map.parquet` (Tổng cộng: 177,321 dòng)
- **Nguồn gốc**: Từ điển ánh xạ thời gian thực cho các keyframe BTC.
- **Cấu trúc cột & Dtype**:
  - `video_id` (`object` / `string`): Mã video.
  - `btc_ordinal` (`int64`): Số thứ tự file keyframe do BTC đánh số trong thư mục (VD: `1` cho file `0001.jpg`).
  - `frame_idx` (`int64`): Frame index tuyệt đối thực tế trong video gốc (VD: `0`, `90`, `261`).
  - `pts_time` (`float64`): Timestamp Presentation Time tính bằng giây (VD: `0.0`, `3.6`).
  - `fps` (`float64`): Tốc độ khung hình (VD: `25.0` hoặc `30.0`).
  - `kf_id` (`object` / `string`): Mã Keyframe chuẩn BTC (VD: `L21_V001#k0001`).

### 2.3 `shots.parquet` (Tổng cộng: 100,810 dòng)
- **Nguồn gốc**: Phân đoạn video thành các Shot bằng thuật toán TransNetV2 / PySceneDetect.
- **Cấu trúc cột & Dtype**:
  - `shot_id` (`object` / `string`): Định dạng `{video_id}#s{shot_seq:04d}` (VD: `L21_V001#s0000`).
  - `video_id` (`object` / `string`)
  - `shot_seq` (`int32`): Số thứ tự shot trong video (bắt đầu từ 0).
  - `start_frame` (`int64`): Frame index bắt đầu shot.
  - `end_frame` (`int64`): Frame index kết thúc shot.
  - `n_frames` (`int32`): Số lượng frame trong shot (`end_frame - start_frame + 1`).
  - `duration_s` (`float64`): Thời lượng shot tính bằng giây.
  - `is_force_split` (`bool`): `True` nếu shot gốc > 60s và bị ép cắt nhỏ thành các đoạn 30s.
  - `n_raw_shots_merged` (`int32`): Số lượng raw shot được gộp lại.
  - `detector_confidence` (`float32`): Độ tin cậy của thuật toán phát hiện cảnh cắt.
  - `detector` (`object` / `string`): Tên thuật toán (VD: `pyscenedetect` hoặc `transnetv2`).
  - `config_hash` (`object` / `string`): Hash cấu hình phân đoạn.
  - `split_reason` (`object` / `string`): Lý do cắt (VD: `detector`, `force_split`).
  - `rep_kf_id` (`object` / `string`): Keyframe đại diện của shot (lấy theo BTC ordinal hoặc frame giữa).
  - `rep_source` (`object` / `string`): Nguồn lấy rep_kf (VD: `btc`).
  - `rep_offset` (`float64`): Độ lệch thời gian của rep_kf so với tâm shot.
  - `keyframes_config_hash` (`object` / `string`).

### 2.4 `keyframes.parquet` (Tổng cộng: 343,996 dòng)
- **Nguồn gốc**: Tập hợp khung hình chốt mật độ **1 FPS** (1 giây / 1 frame) phục vụ truy xuất hình ảnh và vector.
- **Cấu trúc cột & Dtype**:
  - `kf_id` (`string`): **Khóa chính chuẩn hóa của hệ thống**, định dạng `{video_id}_{frame_idx:07d}` (VD: `L22_V004_0000009`).
  - `video_id` (`string`)
  - `shot_id` (`string`): Trỏ về `shots.parquet`.
  - `frame_idx` (`int64`): Chỉ số frame tuyệt đối.
  - `path` (`string`): Đường dẫn tương đối lưu trữ file JPEG (`keyframes/L22_V004/f0000009.jpg`).
  - `row_id` (`int64`): Số thứ tự dòng toàn cục.

### 2.5 `asr.parquet` (Tổng cộng: 13,415 dòng)
- **Nguồn gốc**: Kết quả nhận diện giọng nói (Speech-to-Text) chạy bởi `mlx-community/whisper-large-v3-turbo` hoặc PhoWhisper trên toàn bộ luồng audio.
- **Cấu trúc cột & Dtype**:
  - `video_id` (`string`)
  - `seg_id` (`int32`): ID phân đoạn thoại trong video (0, 1, 2...).
  - `start_s` (`float32`): Thời gian bắt đầu thoại (giây).
  - `end_s` (`float32`): Thời gian kết thúc thoại (giây).
  - `start_frame` (`int64`): Frame tuyệt đối bắt đầu (`int(start_s * fps)`).
  - `end_frame` (`int64`): Frame tuyệt đối kết thúc (`int(end_s * fps)`).
  - `text_vi` (`string`): Câu tiếng Việt được giải mã.
  - `avg_logprob` (`float32`): Xác suất trung bình của mô hình (log probability).
  - `no_speech_prob` (`float32`): Xác suất phân đoạn không có tiếng nói.

### 2.6 `ocr.parquet` (Tổng cộng: 160,393 dòng)
- **Nguồn gốc**: Trích xuất chữ trên màn hình (PaddleOCR / Apple Vision) thực thi trên các `rep_kf` và vùng có văn bản.
- **Cấu trúc cột & Dtype**:
  - `video_id` (`string`)
  - `kf_id` (`string`): Mã keyframe theo chuẩn BTC (`L21_V001#k0001`).
  - `frame_idx` (`int64`): Frame index tuyệt đối tương ứng với keyframe đó.
  - `text_raw` (`string`): Chuỗi chữ thô giữ nguyên hoa/thường và dấu tiếng Việt (VD: `06:30:11 giây)`).
  - `text_clean` (`string`): Chuỗi chữ đã xóa dấu tiếng Việt và chuyên về chữ thường (lowercase) phục vụ BM25 (VD: `06:30:11 giay)`).
  - `n_boxes` (`int32`): Số lượng bounding box chứa chữ.
  - `avg_conf` (`float32`): Độ tin cậy trung bình của kết quả OCR.
  - `boxes` (`string`): JSON String chứa mảng các tọa độ box `[x, y, w, h]` hoặc các đỉnh đa giác.

### 2.7 `docs_bm25.parquet` (Tổng cộng: 343,996 dòng)
- **Nguồn gốc**: Hợp nhất toàn bộ tri thức (Title, Description, ASR window ±3s, OCR theo shot) vào đúng 343,996 Keyframes.
- **Cấu trúc cột & Dtype**:
  - `kf_id` (`string`): Mã keyframe chuẩn hóa (`L22_V004_0000009`).
  - `video_id` (`object` / `string`)
  - `shot_id` (`object` / `string`)
  - `frame_idx` (`int64`)
  - `doc_text` (`object` / `string`): Văn bản hợp nhất được hạ về chữ thường (lowercase), cấu trúc chính xác:
    ```text
    [title] {meta_title}
    [desc] {meta_desc}
    [asr] {gộp toàn bộ text_vi trong cửa sổ ±3s}
    [ocr] {gộp toàn bộ text_clean OCR thuộc shot này}
    ```

---

## 3. CHI TIẾT THUẬT TOÁN VÀ LOGIC XỬ LÝ (IMPLEMENTATION DETAILS)

### Task B0.1: Video Info & Frame Map Parity
- **Vấn đề**: Video MP4 có thể bị trượt frame (frame drift) nếu dùng công thức `frame = time * fps`.
- **Giải pháp**: Xây dựng `frame_map.parquet` lưu chính xác `pts_time` cho từng `frame_idx`. Sửa đổi lệch offset bằng bộ kiểm tra Parity 20 mẫu (`test_opencv_parity.py`), đảm bảo chỉ số `frame_idx_corrected` tăng đơn điệu tuyệt đối (strictly monotonic).

### Task B1.1: Shot Segmentation & Force Split
- PySceneDetect / TransNetV2 cắt video dựa trên ngưỡng thay đổi cảnh (threshold 27).
- Để tránh hiện tượng Shot kéo dài hàng phút làm loãng thông tin hình ảnh, thuật toán ép cắt cưỡng bức (force split) các Shot > 60s thành các sub-shot tối đa 30s (`is_force_split = True`).

### Task B1.2: Keyframe Extraction (1 FPS)
- Trích xuất 1 frame mỗi giây (1 FPS).
- Đặt giới hạn an toàn cho mỗi Shot: Tối thiểu 2 keyframes/shot, tối đa 20 keyframes/shot.
- Định dạng ảnh: JPEG Quality 90, cạnh dài 448px.
- Khóa chính `kf_id` được chuyển từ chuẩn đếm BTC (`0001.jpg`) sang chuẩn frame index tuyệt đối (`L22_V004_0000009`).

### Task B1.3: ASR Whisper Windowing
- Trích xuất luồng audio `.wav` từ video MP4.
- Chạy mô hình `mlx-community/whisper-large-v3-turbo` (trên Mac Neural Engine) hoặc `faster-whisper` (trên Kaggle GPU).
- Quy đổi thời gian thoại `[start_s, end_s]` sang frame `[start_frame, end_frame]` bằng công thức `int(sec * (fps_num / fps_den))`.

### Task B1.4: PaddleOCR & Apple Vision OCR
- Thực thi nhận diện chữ trên các `rep_kf` đại diện của Shot.
- Xuất ra 2 trường song song: `text_raw` (giữ nguyên gốc) và `text_clean` (xóa dấu bằng unicodedata NFD + thay `đ/Đ` thành `d/D`).

### Task B1.7: BM25 Time-Series Merge (docs_bm25_job.py)
- **Gộp OCR qua Shot (`merge_asof`)**: Do OCR ban đầu gắn theo `rep_kf_id` hoặc frame lẻ, job dùng `pandas.merge_asof` với `by="video_id"` và `direction="backward"` dựa trên `frame_idx` và `start_frame` để map mọi bản ghi OCR vào đúng `shot_id`. Sau đó gộp tất cả `text_clean` theo `shot_id` và join vào `keyframes.parquet`.
- **Gộp ASR theo cửa sổ thời gian (±3s Window)**: Với mỗi keyframe `kf_frame` thuộc `video_id`, tính `window = 3.0 * (fps_num / fps_den)`. Lọc tất cả phân đoạn ASR thỏa mãn:
  `start_frame <= kf_frame + window` VÀ `end_frame >= kf_frame - window`
  Sau đó nối toàn bộ các câu thoại lại với nhau.
- **Hợp nhất cuối cùng**: Ghép các trường có dữ liệu với tiền tố `[TITLE]`, `[DESC]`, `[ASR]`, `[OCR]` và gọi `.lower()`.

---

## 4. QUY TẮC BẤT BIẾN CHO BACKEND / AI / UI (INVARIANTS)

1. **Khóa Join chuẩn duy nhất**:
   Mọi liên kết giữa Elasticsearch, Milvus Vector DB, và Parquet **CHỈ ĐƯỢC DÙNG** `kf_id` (`L22_V004_0000009`) hoặc cặp `(video_id, frame_idx)`. **CẤM** dùng số đếm file `0000.jpg` của BTC.

2. **Quy đổi Submit**:
   Khi nộp bài thi (Submit KIS/Q&A/TRAKE), `frame_id` nộp cho BTC **bắt buộc** là `frame_idx` tuyệt đối (lấy từ cột `frame_idx` của `keyframes.parquet` / `docs_bm25.parquet`). Nộp nhầm số thứ tự file keyframe = 0 điểm tuyệt đối.

3. **Giao tiếp LLM**:
   Mọi thao tác gọi LLM phải đi qua `backend/llm/adapter.py:llm()`. Không được tự tiện import SDK bên ngoài trong các module retrieval/tasks.

---

## 5. LỆNH CHẠY NẠP DỮ LIỆU VÀO ELASTICSEARCH

Để nạp dữ liệu từ các file Parquet vào Elasticsearch local:

```bash
# 1. Khởi động Docker Elasticsearch + Milvus
docker compose up -d

# 2. Nạp Metadata
python -m backend.indexing.load_metadata --recreate

# 3. Nạp OCR
python -m backend.indexing.load_ocr --recreate

# 4. Nạp ASR
python -m backend.indexing.load_asr --recreate

# 5. Kiểm tra kết nối và query thử nghiệm
python -m backend.retrieval.search "tản mạn mê kông" --en "tan man me kong" --top-k 10
```
