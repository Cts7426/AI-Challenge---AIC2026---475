# Gán nhãn E01 từ nguồn

Mở [annotation_packet.html](annotation_packet.html). 44 gói nguồn, query/GT còn trống. Mỗi mục có template JSON, keyframe theo số frame tuyệt đối và keyframe_id. Không có ranking/answer hệ thống. Người duyệt chọn evidence từ `source_catalog.json`; không sửa catalog, sampling plan hoặc revision bằng tay.

## Thực hiện

1. Chọn một packet; xem nguồn để tự viết `query_text`, không xem output hệ thống.
2. Sao chép template tương ứng sang file nháp riêng. Điền `label`: KIS windows/evidence; QA thêm answerability/acceptable_answers; TRAKE thêm ordered events. Evidence gồm video_id/keyframe_id/frame_idx/path/sha256 đúng catalog, cùng `support` mô tả bằng chứng.
3. Điền grouping sau khi kiểm các video khác, danh sách đã dùng và `leakage_audit.json`. Trùng/gần trùng qua split thì PENDING và yêu cầu version sampling mới. Khi shared frames không phải cùng sự kiện/footage, giải thích bằng nguồn cụ thể, không chỉ ghi “đã xem”.
4. Chưa đủ chắc: `verification.status=pending`, ghi notes. Đủ chắc: `verified`; chỉ người đã xem nguồn được dùng `--human-reviewed`. Tên và thời điểm người duyệt được CLI ghi vào revision. Không chạy các lệnh verified bên dưới khi chưa thực sự duyệt.

Ví dụ ghi một quyết định human từ file nháp đã hoàn chỉnh (thay tên và file bằng giá trị thật):

```powershell
.venv\Scripts\python.exe -m dev_set.tools.e01_dataset record --dataset reports/post_preliminary_e01_20260912/dataset_v1 --input reports/post_preliminary_e01_20260912/human_entry.json --by "Tên người đã xem nguồn" --reason "Mô tả bằng chứng và lý do nhãn" --human-reviewed
.venv\Scripts\python.exe -m dev_set.tools.e01_dataset quality --dataset reports/post_preliminary_e01_20260912/dataset_v1
```

Tool không kết nối mạng, không sửa retrieval hay GT lịch sử. `record` thêm revision, không ghi đè revision cũ. Nên bắt đầu với một packet validation để kiểm thao tác; không dùng kết quả retrieval để tìm đáp án cho packet held-out.

## Schema tóm tắt

`annotation_schema.json` là JSON Schema xuất từ `dev_set/tools/e01_schema.py`; validator Pydantic còn kiểm các điều kiện liên trường nên cần chạy CLI, không chỉ JSON Schema. Query ID khóa task/split. Window start/end là integer >=0, start<=end. KIS/QA phải có reference nằm trong region. QA answerable cần ít nhất một form khác rỗng; zero và phủ định hợp lệ không bị chặn. Unanswerable phải có lý do và không có answer giả. TRAKE >=2 sự kiện; mỗi event cần reference nằm trong window, thứ tự không đảo, ambiguous không được verified, tolerance khác 0 có giải thích.

QA exact policy `e01.qa.nfc_casefold_whitespace_v1`: NFC + casefold + collapse whitespace; giữ dấu, dấu câu, chữ số và đơn vị. Semantic policy `human_registered_variants_only_no_online_judge_v1`: các biến thể tương đương được human đăng ký trước seal; không gọi AI judge, không nói đây là scorer semantic BTC. Khi cần scorer khác phải preregister/version, không thay sau khi xem prediction.

## Seal và mở held-out — chỉ thực hiện sau đủ gate

```powershell
.venv\Scripts\python.exe -m dev_set.tools.e01_dataset seal --dataset reports/post_preliminary_e01_20260912/dataset_v1 --by "Tên người duyệt cuối"
.venv\Scripts\python.exe -m dev_set.tools.e01_dataset consume --dataset reports/post_preliminary_e01_20260912/dataset_v1 --by "Tên người mở" --protocol "Protocol đã duyệt và quyết định cuối"
```

Hiện tại seal bị chặn đúng thiết kế. Lệnh consume không phải quyền chạy H03: H03 implementation vẫn chưa được phép. Sau khi opened, mọi sửa GT phải tạo version bằng `fork-correction` rồi record old/new reason/verifier/date; không được gọi version kế thừa consumed là independent. Việc loại/thay video trước seal cần sampling version mới; công cụ không có shortcut đổi split tại chỗ.
