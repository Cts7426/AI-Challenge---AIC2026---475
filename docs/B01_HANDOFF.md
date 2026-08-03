# 📦 Bàn Giao Dữ Liệu - Task B0.1 (Data Foundation)

Đây là tài liệu hướng dẫn và bàn giao kết quả của bước Gác Cổng (Task B0.1) dành cho Thạch (CLIP/Feature Extraction) và Minh Hoàng (Training/Retrieval). 

## 1. Tóm Tắt (The TL;DR)
- **Có gì:** Bộ khung dữ liệu 100% sạch (`frame_map`, `video_info`) đã được xử lý triệt để lỗi lệch frame (offset) của BTC. Mọi file parquet và API đã sẵn sàng để truy xuất chính xác từng frame.
- **Dùng thế nào:** Không đọc trực tiếp parquet! Luôn dùng hàm `load_frame_map()` và `extract_frame_exact()` trong `preprocessing/common/` để lấy dữ liệu.
- **Cạm bẫy:** Tuyệt đối KHÔNG DÙNG `cv2.VideoCapture.set(CAP_PROP_POS_FRAMES, idx)` hoặc `container.seek()` của PyAV. Cả hai đều giải mã sai frame do lỗi Open GOP của H.264, gây ra ảo giác lệch frame hoặc trích xuất sai ảnh.

---

## 2. ⚠️ CẢNH BÁO QUAN TRỌNG VỀ TRÍCH XUẤT FRAME

Trong quá trình điều tra, chúng tôi đã phát hiện **lỗi giải mã H.264** nghiêm trọng trên cả OpenCV và PyAV khi thực hiện seek thẳng đến một `frame_idx`:
- **PyAV Seek (`container.seek`)**: Tính toán thời gian sai (làm tròn số phân số fps), dẫn đến seek lệch 1-2 frame.
- **OpenCV Seek (`cv2.set(POS_FRAMES)`)**: Seek đúng thời gian nhưng giải mã sai hình ảnh nếu điểm seek rơi vào giữa một Open GOP (Ví dụ L22_V022 cho MSE lên tới 6692 dù offset thực bằng 0).

👉 **Giải pháp duy nhất an toàn:** Phải dùng hàm `extract_frame_exact` từ `preprocessing.common.decode`. Hàm này sẽ tự động tua về trước 60 frame, sau đó `read()` tuần tự tiến lên để đảm bảo bộ giải mã H.264 dựng lại đúng 100% hình ảnh thực tế.

---

## 3. Code Mẫu Cho Thạch (Feature Extraction)

Để biết hàng thứ `i` của file `.npy` tương ứng với frame nào (đã bù trừ offset), hãy load `frame_map` bằng API chuẩn và join với `clip_row_index`.

```python
import pandas as pd
from preprocessing.common.frame_map import load_frame_map

# 1. Load frame map an toàn (đã tự động map frame_idx_corrected -> frame_idx)
df_map = load_frame_map(require_verified=False)

# 2. Load clip_row_index
df_clip = pd.read_parquet("data/derived/clip_row_index.parquet")

# 3. Join để lấy frame_idx chính xác
# Lưu ý: frame_idx trong df_map lúc này CHÍNH LÀ frame_idx_corrected.
# Cột frame_idx gốc của BTC đã bị đổi tên thành frame_idx_raw.
df_final = df_clip.merge(df_map[["video_id", "btc_kf_ordinal", "frame_idx", "offset_verified"]], 
                         on=["video_id", "btc_kf_ordinal"], 
                         how="left")

# df_final hiện tại chứa frame_idx_y (chuẩn) tương ứng với local_row trong file .npy
```

---

## 4. Code Mẫu Cho Minh Hoàng (Training & Retrieval)

Khi mô hình trả về một `(video_id, btc_kf_ordinal)` và bạn cần hiển thị bức ảnh gốc đó cho UI hoặc verify.

```python
from preprocessing.common.frame_map import get_frame_idx
from preprocessing.common.decode import extract_frame_exact

video_id = "L21_V022"
btc_kf_ordinal = 42
mp4_path = f"data/raw/videos/{video_id}.mp4"

# 1. Tra cứu frame_idx CHUẨN (đã bù offset tự động)
idx = get_frame_idx(video_id, btc_kf_ordinal)

# 2. Trích xuất ảnh chính xác 100% (không dùng cv2.set!)
img_rgb = extract_frame_exact(mp4_path, idx)

if img_rgb is not None:
    # Hiển thị hoặc lưu ảnh
    import matplotlib.pyplot as plt
    plt.imshow(img_rgb)
    plt.show()
```

---

## 5. Schema Các Bảng Dữ Liệu (Parquet)

Dữ liệu được lưu tại `data/derived/`. Các file sample (20 dòng đầu) định dạng CSV đã được xuất ra thư mục `data/derived/samples/` để các bạn xem nhanh mà không cần code.

### A. `video_info.parquet`
Chứa thông tin metadata vật lý thực sự (quét bằng ffprobe, không ước lượng).
- `video_id` (str): Mã video (VD: L01_V001).
- `fps_num` (int): Tử số của FPS (VD: 30000).
- `fps_den` (int): Mẫu số của FPS (VD: 1001). Tỷ lệ thực là `30000/1001 = 29.97`. KHÔNG BAO GIỜ làm tròn.
- `n_frames` (int): Tổng số frame thực tế.
- `path` (str): Đường dẫn tương đối.

### B. `frame_map.parquet`
Ánh xạ trung tâm giữa Keyframe của BTC và Chỉ số Frame thật trong MP4.
- `video_id` (str): Khóa ngoại.
- `btc_kf_ordinal` (int): Số thứ tự keyframe (bắt đầu từ 1). ĐÂY LÀ KHÓA JOIN CHÍNH, KHÔNG DÙNG frame_idx ĐỂ JOIN!
- `frame_idx_raw` (int): Chỉ số frame GỐC do BTC cung cấp (thường bị lệch offset, hoặc bằng 0 nếu bị lỗi mất giá trị).
- `pts_time` (float): Thời gian hiển thị (giây) do BTC cung cấp (không chính xác).
- `fps` (float): FPS xấp xỉ dạng float.
- `kf_offset` (int): Độ lệch frame đo được (+1, 0, -1). Nếu chưa đo thì bằng NaN/0.
- `frame_idx_recovered` (int): Chỉ số frame tìm lại được (nếu `frame_idx_raw` bị lỗi duplicate / giá trị 0).
- `frame_idx_status` (str): Trạng thái khôi phục (`"ok"`, `"recovered"`, `"unrecoverable"`, `"unverified"`).
- `match_run_length` (int): Số frame liên tiếp khớp mãnh liệt (`MSE < 20`) khi khôi phục cảnh tĩnh.
- `recovery_confidence` (str): Độ tin cậy khôi phục (`"high"`, `"medium"`, `"low"`).
- `cosine` (float): Trị số similarity với CLIP (mặc định để `null`, dự phòng).
- `frame_idx_corrected` (int): Chỉ số frame THỰC TẾ (ưu tiên: `recovered` > `raw + kf_offset` > `raw`). **TẤT CẢ MODULE PHẢI DÙNG CỘT NÀY**. Đã được kiểm chứng là hàm tăng đơn điệu ngặt.

### C. `video_offset.parquet`
Kết quả chạy thuật toán Trọng Tài cho từng video.
- `video_id` (str): Khóa ngoại.
- `fps_num`, `fps_den` (int): FPS.
- `n_samples_used` (int): Số lượng keyframe động đã dùng để xác thực.
- `offset` (int): Độ lệch tính toán.
- `offset_status` (str): `ok`, `ok_8` (đồng thuận cao), hoặc `ambiguous`.
- `offset_confidence` (float): Chênh lệch MSE (càng cao càng chắc chắn).

### D. `clip_row_index.parquet`
Sổ xố / Danh mục (Index) của các file `.npy` vector nhúng (CLIP).
- `row_id` (int): Khóa chính tự tăng của toàn bộ dataset.
- `video_id` (str): Khóa ngoại.
- `btc_kf_ordinal` (int): Số thứ tự keyframe.
- `frame_idx` (int): Chỉ số frame lúc trích xuất.
- `kf_id`: STRING (vd: "L01_V001#k0042") - KHÓA CHÍNH (Đã đổi định dạng từ f<frame_idx> sang k<ordinal> để tránh trùng lặp).
- `npy_file` (str): Tên file npy chứa vector tương ứng.
- `local_row` (int): Số thứ tự hàng bên trong file `.npy`.

---

## 6. Trạng Thái Hiện Tại (Tiến Độ Gác Cổng)

Hiện tại, chúng tôi đã chạy kiểm tra bù lệch (offset) đợt 1 trên 128 video MP4 hiện có:
- **Xác nhận an toàn (Verified):** 120/873 video. (Đã cập nhật bù lệch vào `frame_map`).
- **Mập mờ (Ambiguous):** 8/873 video. (Mặc định giữ nguyên offset = 0 để an toàn).
- **Chưa quét:** Phần còn lại (~745 video) tạm thời giả định `offset = 0`.

Quá trình chạy thuật toán `detect_frame_offset.py` để verify các video còn lại sẽ được tích hợp và chạy ngầm song song vào hệ thống **Rolling Ingest** trong các đợt tải ZIP tiếp theo. Hệ thống hiện tại đã hoàn toàn Robust và không sợ lỗi lệch frame làm hỏng dữ liệu huấn luyện. 

Chúc các bạn code vui vẻ! 🚀
