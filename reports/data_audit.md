# B0.1 Data Audit Report

> **Báo cáo lịch sử.** Số liệu scan video và pixel parity phản ánh checkpoint
> B0.1 tại thời điểm lập báo cáo, không phải trạng thái raw hiện hành. Đợt 1 chỉ
> giữ các archive/raw asset cần cho pipeline; 14 archive video đang deferred.

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

*Chưa có bằng chứng job verify đã chạy tiếp sau checkpoint này. Vì archive video
đang deferred, 789 video chưa verify là rủi ro đã biết chứ không được tính là đã
hoàn tất.*

## 7. Phát hiện khung hình đen (Black Keyframes)
Đã quét toàn bộ 873 thư mục ảnh tĩnh của BTC để tìm các `ordinal 1` (frame đầu tiên) có dung lượng siêu nhỏ (< 10KB), thường là khung hình đen hoàn toàn ở đầu video.

**Giả thuyết lịch sử:** Các file nhỏ có thể là khung đen và có thể ảnh hưởng truy
vấn "cảnh tối", nhưng báo cáo này chưa lưu phép đo pixel hay ablation retrieval.
**Quyết định hiện tại:** Hoãn xóa. Không loại riêng 11 keyframe khỏi Milvus/ES/map
vì sẽ phá parity 177.321 nếu không migration đồng bộ. Chỉ xem xét sau khi kiểm
ảnh, đo query-level và có kế hoạch cập nhật mọi lớp dữ liệu cùng lúc.

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
