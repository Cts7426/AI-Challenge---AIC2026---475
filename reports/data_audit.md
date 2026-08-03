# B0.1 Data Audit Report

## 1. Tổng quan dữ liệu
- **Tổng số video:** 873
- **Tổng thời lượng:** 130.67 giờ (470428 giây)
- **Phân bố thời lượng:**
  - < 5 phút: 121 video
  - 5 - 15 phút: 562 video
  - > 15 phút: 190 video

## 2. Thông số kỹ thuật (dựa trên mẫu MP4 đã tải)
*Đã scan 85 video trên đĩa để lấy thông số chính xác.*
- **Phân bố FPS (phân số):**
  - 25/1: 47 video
  - 30/1: 38 video
- **Phân bố độ phân giải:**
  - 1280x720: 85 video

## 3. Video không có Audio
> Không phát hiện video nào mất audio trong các file đã tải.

## 4. Tính toàn vẹn của dữ liệu (Missing Files)
- **Thiếu metadata (.json):** 0 video
- **Thiếu map-keyframes (.csv):** 0 video
- **Thiếu CLIP features (.npy):** 0 video

## 5. Keyframes & Object Detections (BTC)
- **Tổng số keyframe do BTC cung cấp:** 177321
- **Trung bình:** 203.1 keyframe / video
- **Mật độ:** 0.38 keyframe / giây

> [!WARNING]
> **Bão hòa Object Detections**: Cột `objects` (trong các file `.csv` của BTC) bị bão hòa ở mức tối đa **100 detection** cho mỗi keyframe. Do đó, **TUYỆT ĐỐI KHÔNG** sử dụng số lượng object (chiều dài của chuỗi JSON) làm đặc trưng để train model hay ranking, vì nó bị cắt ngắt nhân tạo và không phản ánh đúng mật độ vật thể thực tế.

## 6. Kết quả Gác Cổng (Offset & Alignment)
- **Đã verify offset:** 84 video
- **Chưa verify (giả định 0):** 789 video
- **Số video bị lệch offset:** 6/84 (7.1%)

*Việc verify offset sẽ tiếp tục chạy song song trong quá trình `rolling_ingest` khi tải data.*

## 7. Phát hiện khung hình đen (Black Keyframes)
Đã quét toàn bộ 873 thư mục ảnh tĩnh của BTC để tìm các `ordinal 1` (frame đầu tiên) có dung lượng siêu nhỏ (< 10KB), thường là khung hình đen hoàn toàn ở đầu video.

**Vấn đề:** Các khung hình đen này được trích xuất vector CLIP và vẫn nằm trong bộ chỉ mục (index). Vector của chúng không mang thông tin ngữ nghĩa thực tế nhưng vẫn có thể bị trả về cho các truy vấn về "cảnh tối". 
**Khuyến nghị:** Team Retrieval (Thạch) nên loại bỏ chúng khỏi index, và bước B1.2 nên bỏ qua không trích xuất đặc trưng bổ sung cho các frame này.

**Danh sách 11 video có `ordinal 1` là khung hình đen:**
- L21_V006 (5621 bytes)
- L21_V007 (5621 bytes)
- L21_V012 (5621 bytes)
- L21_V013 (5621 bytes)
- L21_V014 (5621 bytes)
- L21_V015 (5621 bytes)
- L21_V016 (5621 bytes)
- L21_V022 (5621 bytes)
- L21_V023 (5621 bytes)
- L21_V029 (5621 bytes)
- L30_V036 (5621 bytes)