## Quy ước định danh (KHÔNG BAO GIỜ được đổi)
- video_id: "L01_V001" — trùng tên file .mp4, không đuôi
- frame_idx: số nguyên, CHỈ SỐ FRAME GỐC trong video, đếm từ 0.
  Đây là thứ nộp cho ban tổ chức.
- shot_id: "L01_V001#s0042" — video_id + số thứ tự shot, pad 4 chữ số
- kf_id: "L01_V001#f0001234" — video_id + frame_idx, pad 7 chữ số.
  ĐÂY LÀ KHÓA JOIN XUYÊN SUỐT MỌI BẢNG.

## Quy tắc tuyệt đối
- KHÔNG BAO GIỜ dùng số thứ tự file keyframe của BTC (0000.jpg, 0001.jpg)
  làm khóa. Đó là số thứ tự trong thư mục, KHÔNG phải chỉ số frame.
  Nhầm hai thứ này là lỗi im lặng làm toàn bộ điểm số bằng 0.
- fps luôn lưu dạng phân số (fps_num, fps_den). KHÔNG BAO GIỜ làm tròn.
  Video 29.97 fps thực chất là 30000/1001.
- Mọi tham số đọc từ data/config/config.yaml. Không hardcode đường dẫn,
  ngưỡng, tên model.
- Mọi output nặng đi kèm file .meta.json cùng tên: model, version,
  ngày chạy, commit hash, tham số, số bản ghi.

## Kỷ luật job dài
Mọi job xử lý dữ liệu phải:
- Chia lô, ghi checkpoint sau mỗi lô
- Đọc data/manifests/<job>.json lúc khởi động, bỏ qua phần đã xong
- Chạy lại được sau khi bị ngắt giữa chừng mà không làm lại từ đầu
- Nhận tham số --shard i --num-shards n để chia việc.
  Lưu ý quan trọng về Shard: 
  + Ingest (tải ZIP): Chia theo ZIP `int(md5(zip_name).hexdigest(), 16) % num_shards`.
  + Các job Kaggle (ASR, OCR): Chia theo `int(md5(video_id).hexdigest(), 16) % num_shards`. Hai kiểu shard này CỐ Ý khác nhau.
- In tiến độ và thời gian còn lại ước tính

## Ngăn xếp
Python 3.10+, pandas, pyarrow, ffmpeg-python (hoặc subprocess ffmpeg).
KHÔNG dùng Milvus, KHÔNG dùng Elasticsearch, KHÔNG dùng Docker cho
phần preprocessing. docker-compose.yml và embedEtcd.yaml trong repo là
tàn dư, bỏ qua.

## Phong cách
- Ưu tiên code đọc được hơn code ngắn
- Mỗi hàm xử lý dữ liệu phải có docstring ghi rõ đầu vào, đầu ra, và
  bất biến (invariant) mà nó giữ
- Giải thích lý do cho mọi quyết định kỹ thuật không hiển nhiên
