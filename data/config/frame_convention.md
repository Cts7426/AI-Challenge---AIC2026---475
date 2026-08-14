# Quy ước Frame (Frame Convention)

**Khẳng định:** 
1. Chỉ số khung hình (`frame_idx`) trong toàn bộ hệ thống là **0-based** (khung hình đầu tiên của video là frame 0).
2. Số thứ tự keyframe mà BTC cấp (`0000.jpg`, `0001.jpg`...) là **0-based**, nhưng nó là số thứ tự ảnh trong thư mục, **KHÔNG PHẢI** là `frame_idx`.
3. Công thức chuyển đổi chính thức: KHÔNG có công thức toán học nào. BẮT BUỘC phải tra bảng `frame_map.parquet` bằng khoá `(video_id, btc_ordinal)` để lấy ra `frame_idx` gốc.
