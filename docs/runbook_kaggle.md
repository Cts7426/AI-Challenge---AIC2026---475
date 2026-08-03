# Runbook Vận Hành Kaggle (Dành cho Non-Coder)

**Người phụ trách:** Quang Linh và các thành viên chạy data  
**Mục tiêu:** Hướng dẫn từng bước chạy các job xử lý dữ liệu nặng (ASR, OCR, Shot Segmentation) trên Kaggle bằng tài nguyên GPU miễn phí (~30 giờ/tuần/người).

> ℹ️ **Cách kiểm tra giờ GPU còn lại:**
> Click vào ảnh đại diện của bạn ở góc trên bên phải trang chủ Kaggle -> Chọn **Settings** -> Cuộn xuống phần **Quotas** -> Xem thanh **GPU (tối đa 30h/tuần)**.

> ⚠️ **LƯU Ý QUAN TRỌNG NHẤT:** 
> Kaggle có thể tự động ngắt phiên (session chết) bất cứ lúc nào sau 9-12 tiếng. **TUYỆT ĐỐI KHÔNG tích lũy kết quả đến cuối mới tải về.** Phải tải kết quả về máy tính cá nhân ngay sau khi chạy xong từng lô (batch). Nếu phiên chết, toàn bộ dữ liệu chưa tải sẽ mất trắng!

---

## 1. Chuẩn Bị: Upload Dữ Liệu Lên Kaggle

Tùy vào job bạn chạy, dữ liệu cần upload sẽ khác nhau. **Tuyệt đối KHÔNG upload video MP4** vì upload rất lâu và Kaggle không đủ chỗ chứa.

| Tên Job | Chạy trên dữ liệu gì? | Thư mục cần upload lên Kaggle | Dung lượng ước tính |
| :--- | :--- | :--- | :--- |
| **ASR** (Nhận diện giọng nói) | Audio `.wav` 16k mono | `data/derived/audio/` | ~3 - 5 GB |
| **OCR** (Nhận diện chữ trên ảnh) | Ảnh Keyframe `.jpg` | Thư mục keyframes BTC cấp | ~1 - 2 GB |

1. Đăng nhập vào [Kaggle](https://www.kaggle.com/).
2. Nhấn nút **+ Create** ở menu bên trái -> Chọn **New Dataset**.
3. Điền tên Dataset (VD: `aic2026-audio-l21`). 
4. Kéo thả thư mục chứa các file tương ứng vào ô tải lên.
5. Nhấn **Create** và chờ Kaggle xử lý.  
   *[ẢNH: Màn hình tạo và tải dataset trên Kaggle]*

---

## 2. Tạo Notebook và Bật GPU

1. Ở trang chủ Kaggle, nhấn **+ Create** -> Chọn **New Notebook**.
2. Đặt tên Notebook ở góc trên cùng bên trái (VD: `AIC2026-ASR-Shard4`).
3. **Bật GPU (BẮT BUỘC):** 
   - Nhìn sang menu **Session Options** ở bên phải màn hình.
   - Mục **Accelerator**, đổi từ *None* sang **GPU P100** hoặc **GPU T4x2**.
   - Chờ một lát để Kaggle khởi động lại phiên máy chủ với GPU.
   *[ẢNH: Chọn GPU trong thanh menu bên phải]*
4. **Gắn Dataset:**
   - Trong menu bên phải, nhấn nút **+ Add Input**.
   - Chuyển sang tab **Your Datasets**, chọn dataset bạn vừa upload ở Bước 1.
   - Nhấn dấu **+** để đính kèm vào Notebook.
   *[ẢNH: Nút Add Input và màn hình chọn Dataset]*

---

## 3. Cài Đặt Môi Trường (Chạy 1 lần khi mới mở Notebook)

Copy đoạn code dưới đây dán vào ô code (cell) đầu tiên và nhấn nút **Play ▶️** (hoặc tổ hợp phím `Shift + Enter`):

```bash
!git clone https://github.com/Cts7426/AI-Challenge---AIC2026---475.git
%cd AI-Challenge---AIC2026---475
!pip install -r backend/requirements.txt
```
*Đợi khoảng 2-3 phút cho cài đặt hoàn tất.*

---

## 4. Lệnh Chạy Job Chính Thức

Bảng phân công Shard cố định cho nhóm (việc chia shard dựa trên mã băm `md5(video_id) % 5` nên luôn cố định, mỗi người luôn nhận đúng cùng một tập video, chạy lại bao nhiêu lần cũng vậy):
* **Thạch**: Shard 0
* **Công Lý**: Shard 1
* **Thi**: Shard 2
* **Minh Hoàng**: Shard 3
* **Quang Linh**: Shard 4

Tạo một ô code mới, copy lệnh dưới đây và thay số `--shard` bằng số của bạn:

```bash
# VD: Chạy ASR cho shard 4
!python preprocessing/asr_job.py \
    --input-dir /kaggle/input/aic2026-audio-l21 \
    --output-dir /kaggle/working/outputs \
    --shard 4 \
    --num-shards 5
```
Nhấn nút **Play ▶️** để bắt đầu chạy.
*[ẢNH: Ô code chứa lệnh chạy job kèm tham số]*

---

## 5. Làm Sao Biết Job Đang Chạy Đúng?

Khi nhấn chạy, log sẽ liên tục in ra bên dưới ô lệnh:
- **Dấu hiệu tốt:** Có thanh tiến trình (progress bar) hiển thị dạng `[ 5/100 ] ETA: 2h:30m`.
- **Con số bình thường:** Xử lý xong 1 file mất khoảng vài phút. Không có dòng chữ đỏ báo lỗi bự.
*[ẢNH: Dòng log mẫu cho thấy tiến trình chạy bình thường]*

---

## 6. TẢI KẾT QUẢ VỀ (CỰC KỲ QUAN TRỌNG)

1. Nhìn sang menu bên phải, tìm phần **Output** (hoặc `/kaggle/working/outputs`).
2. Nhấn nút **Refresh** (hình mũi tên xoay tròn).
3. Khi thấy file kết quả dạng part (VD: `asr_shard4_part1.zip`), **hãy tải về máy tính cá nhân ngay lập tức** bằng cách bấm dấu 3 chấm cạnh file -> Chọn **Download**.
4. Lặp lại việc này mỗi khi có file part mới sinh ra.
*[ẢNH: Hướng dẫn tìm và tải file trong thanh Output]*

---

## 7. Xử Lý Sự Cố Thường Gặp

| Sự cố | Dấu hiệu | Cách xử lý |
| :--- | :--- | :--- |
| **Hết hạn ngạch GPU** | Kaggle báo lỗi khi chọn Accelerator. | Đợi sang tuần để reset 30h, hoặc nhờ người khác chạy hộ. |
| **Hết dung lượng ổ cứng** | Báo lỗi `No space left on device` đỏ rực ở log. | Nhớ xóa bớt các file kết quả `.zip` ở thư mục Output (sau khi đã tải về an toàn). |
| **Tràn RAM / OOM** | Kaggle báo `Session Restarted` đột ngột mất sạch. | Báo lại cho team code giảm `batch_size`. |
| **Session tự tắt (Mất sạch Output)** | Màn hình xám, có popup báo Disconnected, thư mục Output bị xóa trắng. | Xem hướng dẫn ở ngay bên dưới. |

### Cách phục hồi chạy tiếp khi Session tự tắt:
Khi session tắt, toàn bộ dữ liệu trong `/kaggle/working/` (bao gồm file theo dõi tiến độ manifest) đều bay màu. Để tiếp tục chạy phần còn thiếu mà không bị trùng lặp, hãy làm đúng 3 bước sau:

1. Đóng gói các file part đã tải về máy tính, upload ngược lên Kaggle dưới dạng một **Dataset phụ** (VD: `aic2026-asr-parts-shard4`). Hoặc dùng lại link nếu bạn đã lưu.
2. Gắn (Add Input) Dataset phụ đó vào Notebook của bạn. Chạy lệnh khôi phục trạng thái (Manifest):
   ```bash
   !python preprocessing/recover_manifest.py --input-parts /kaggle/input/aic2026-asr-parts-shard4
   ```
3. Sau khi khôi phục xong, **chạy lại lệnh ở Bước 4**, script sẽ tự động bỏ qua những video đã có trong các file part cũ.

*(Lưu ý: Tính năng `recover_manifest.py` đang được team code phát triển, nếu chưa có, hãy báo lại cho nhóm!)*

---

## 8. Checklist Trước Khi Đóng Notebook

- [ ] Tôi đã tải **toàn bộ** các file kết quả mới nhất trong Output về máy chưa?
- [ ] Tôi đã nhắn Báo cáo (Mục 9) vào nhóm chat chưa?
- [ ] Nhấn nút **Stop Session** (Nút nguồn màu đỏ góc phải) để tắt máy chủ ảo. **Nếu không tắt, Kaggle sẽ trừ lố giờ GPU của bạn.**
*[ẢNH: Nút Stop Session đỏ góc phải màn hình]*

---

## 9. Báo Cáo Sau Mỗi Phiên

Sau khi hoàn thành hoặc tắt máy, **BẮT BUỘC** nhắn 1 dòng vào nhóm chat (Telegram/Zalo) theo mẫu sau để team dễ theo dõi tiến độ và số giờ GPU mà không cần phải hỏi:

```
[ASR][shard 4] xong 40/150 video · 3.2h GPU · lỗi: 0 · đã tải về: có
```
