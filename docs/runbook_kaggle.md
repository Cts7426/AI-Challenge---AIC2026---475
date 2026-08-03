# Runbook Vận Hành Kaggle (Dành cho Non-Coder)

**Người phụ trách:** Quang Linh và các thành viên chạy data  
**Mục tiêu:** Hướng dẫn từng bước chạy các job xử lý dữ liệu nặng (ASR, OCR, Shot Segmentation) trên Kaggle bằng tài nguyên GPU miễn phí (~30 giờ/tuần/người).  

> ⚠️ **LƯU Ý QUAN TRỌNG NHẤT:** 
> Kaggle có thể tự động ngắt phiên (session chết) bất cứ lúc nào sau 9-12 tiếng hoặc nếu bạn tắt trình duyệt quá lâu. **TUYỆT ĐỐI KHÔNG tích lũy kết quả đến cuối mới tải về.** Phải tải kết quả về máy tính cá nhân ngay sau khi chạy xong từng lô (batch). Nếu phiên chết, toàn bộ dữ liệu chưa tải sẽ mất trắng!

---

## 1. Chuẩn Bị: Upload Dữ Liệu Nguồn Lên Kaggle

Vì Kaggle không cho phép truy cập trực tiếp ổ cứng máy tính của bạn, bạn phải đẩy dữ liệu (video gốc) lên thành một "Dataset" trước khi chạy.

1. Đăng nhập vào [Kaggle](https://www.kaggle.com/).
2. Nhấn nút **+ Create** ở menu bên trái -> Chọn **New Dataset**.
3. Điền tên Dataset (VD: `aic2026-videos-l21`). 
4. Kéo thả file `.zip` (chứa các video MP4) vào ô tải lên.
5. Nhấn **Create** và chờ Kaggle xử lý.  
   *[ẢNH: Màn hình tạo và tải dataset trên Kaggle]*

---

## 2. Tạo Notebook và Bật GPU

1. Ở trang chủ Kaggle, nhấn **+ Create** -> Chọn **New Notebook**.
2. Đặt tên Notebook ở góc trên cùng bên trái (VD: `AIC2026-ASR-Linh-Shard0`).
3. **Bật GPU (BẮT BUỘC):** 
   - Nhìn sang menu **Session Options** ở bên phải màn hình.
   - Mục **Accelerator**, đổi từ *None* sang **GPU P100** hoặc **GPU T4x2**.
   - Chờ một lát để Kaggle khởi động lại phiên máy chủ với GPU.
   *[ẢNH: Chọn GPU trong thanh menu bên phải]*
4. **Gắn Dataset:**
   - Trong menu bên phải, nhấn nút **+ Add Input**.
   - Chuyển sang tab **Your Datasets**, chọn dataset video bạn vừa upload ở Bước 1.
   - Nhấn dấu **+** để đính kèm vào Notebook.
   *[ẢNH: Nút Add Input và màn hình chọn Dataset]*

---

## 3. Cài Đặt Môi Trường (Chạy 1 lần khi mới mở Notebook)

Trong Notebook, bạn sẽ thấy các ô trống để nhập lệnh (gọi là cell). Copy nguyên văn đoạn code dưới đây dán vào ô đầu tiên và nhấn nút **Play ▶️** (hoặc tổ hợp phím `Shift + Enter`) để chạy:

```bash
!git clone https://github.com/Cts7426/AI-Challenge---AIC2026---475.git
%cd AI-Challenge---AIC2026---475
!pip install -r backend/requirements.txt
```
*Đợi khoảng 2-3 phút cho chữ `[ * ]` bên cạnh ô lệnh biến thành số thứ tự, báo hiệu đã cài xong.*

---

## 4. Lệnh Chạy Job Chính Thức

Kaggle chỉ cho 30h/tuần, nên nhóm 5 người phải chia nhau việc ra làm 5 phần (gọi là 5 **shard**, đánh số từ 0 đến 4). Bạn cần hỏi team trưởng xem bạn được phân công chạy shard số mấy.

Tạo một ô code mới (nhấn nút `+ Code`), copy đoạn lệnh dưới đây và thay số `0` bằng số shard của bạn:

```bash
# Lệnh chạy job (VD: Chạy ASR Job, thay đổi script tương ứng nếu chạy OCR)
!python preprocessing/asr_job.py \
    --input-dir /kaggle/input/aic2026-videos-l21 \
    --output-dir /kaggle/working/outputs \
    --shard 0 \
    --num-shards 5
```
Nhấn nút **Play ▶️** để bắt đầu chạy.
*[ẢNH: Ô code chứa lệnh chạy job kèm tham số]*

---

## 5. Làm Sao Biết Job Đang Chạy Đúng?

Khi nhấn chạy, bạn sẽ thấy các dòng log liên tục in ra bên dưới ô lệnh.
- **Dấu hiệu tốt:** Có thanh tiến trình (progress bar) hiển thị dạng `[ 5/100 ] ETA: 2h:30m`. Tốc độ chạy ổn định, không có thông báo lỗi màu đỏ.
- **Con số bình thường:** Tùy vào loại GPU, nhưng thường xử lý xong 1 video mất khoảng vài phút.
*[ẢNH: Dòng log mẫu cho thấy tiến trình chạy bình thường]*

---

## 6. TẢI KẾT QUẢ VỀ (CỰC KỲ QUAN TRỌNG)

Job đã được cấu hình để cứ xong 20 video sẽ tự động nén kết quả lại thành file `.zip` (hoặc lưu file parquet) trong thư mục lưu trữ. 

1. Nhìn sang menu bên phải, tìm phần **Output** (hoặc `/kaggle/working/outputs`).
2. Nhấn nút **Refresh** (hình mũi tên xoay tròn) nếu chưa thấy file hiện ra.
3. Khi thấy file kết quả (VD: `asr_shard0_batch1.zip`), **hãy tải về máy tính cá nhân ngay lập tức** bằng cách bấm dấu 3 chấm cạnh file -> Chọn **Download**.
4. Lặp lại việc này liên tục mỗi khi thấy có batch mới được sinh ra.
*[ẢNH: Hướng dẫn tìm và tải file trong thanh Output]*

---

## 7. Xử Lý Sự Cố Thường Gặp

| Sự cố | Dấu hiệu | Cách xử lý |
| :--- | :--- | :--- |
| **Hết hạn ngạch GPU (Quota Limit)** | Kaggle báo không cho bật GPU, hoặc báo lỗi khi chọn Accelerator. | Báo cho team biết. Đợi sang tuần sau để Kaggle reset 30h, hoặc nhờ thành viên khác chạy hộ đoạn còn lại. |
| **Hết dung lượng ổ cứng (Disk Out Of Space)** | Báo lỗi `No space left on device` đỏ rực ở log. | Bạn đã để dồn quá nhiều file kết quả không xóa. Hãy xóa bớt các file `.zip` kết quả ở thư mục Output (sau khi đã tải về máy tính an toàn). |
| **Tràn RAM / OOM (Out Of Memory)** | Kaggle báo `Session Restarted` đột ngột mất sạch mọi thứ. | Báo lại cho team code để họ giảm `batch_size` xuống. Kaggle chỉ có 16GB RAM GPU. |
| **Session tự tắt (Disconnected)** | Màn hình xám, có popup báo mất kết nối. | Nhấn nút Restart lại Session. Nếu bạn làm đúng nguyên tắc "tải về liên tục ở Bước 6", bạn chỉ việc chạy lại Bước 4, hệ thống sẽ tự đọc file đã làm và chạy tiếp phần còn thiếu. |

---

## 8. Checklist Trước Khi Đóng Notebook

Trước khi đi ngủ hoặc tắt trình duyệt, **HÃY KIỂM TRA LẠI CÁC BƯỚC NÀY**:
- [ ] Tôi đã tải **toàn bộ** các file kết quả mới nhất trong Output về máy tính chưa?
- [ ] Tôi đã kiểm tra xem file tải về có bị lỗi (0 byte) không?
- [ ] Nhấn nút **Stop Session** (Nút nguồn màu đỏ góc trên cùng bên phải) để tắt máy chủ ảo. **Nếu không tắt, Kaggle sẽ trừ lố giờ GPU của bạn dù bạn đã tắt trình duyệt.**
*[ẢNH: Nút Stop Session đỏ góc phải màn hình]*

Chúc Linh chạy data suôn sẻ! Có lỗi gì lạ không nằm trong bảng trên, cứ copy nguyên dòng lỗi đỏ ném vào nhóm chat cho team xử lý nhé!
