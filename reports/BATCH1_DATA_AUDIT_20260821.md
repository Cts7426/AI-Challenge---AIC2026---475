# Audit dữ liệu Batch 1 — 21/08/2026

Nguồn manifest:
`C:\Users\lehon\Downloads\Dữ liệu cho vòng Sơ Tuyển AIC 2026 - Batch1.csv`.

Lệnh kiểm và lưu data manifest bền vững:

```powershell
.venv\Scripts\python.exe scripts\audit_batch_manifest.py `
  "C:\Users\lehon\Downloads\Dữ liệu cho vòng Sơ Tuyển AIC 2026 - Batch1.csv" `
  --archives-dir "C:\Users\lehon\Downloads" `
  --extracted-root "C:\dev\aic2026\data\raw\btc" `
  --hash --count-extracted `
  --json-out reports\BATCH1_OPERATIONAL_MANIFEST_20260821.json
```

Lượt trên đã tính lại toàn bộ hash. Sau khi chỉ bổ sung trường provenance vào
script, artefact cuối được tái sinh bằng `--reuse-hashes-from` chính manifest
vừa hash; cache chỉ được nhận khi filename + kích thước archive còn khớp. Trường
`invocation.reuse_hashes_source_sha256` lưu hash của artefact nguồn trước khi ghi
đè, nên không ngụ ý rằng nội dung 29,45 GiB đã được hash lại lần hai.

## Kết quả — cập nhật 18:57 ngày 21/08

Manifest có **32 archive**. Trạng thái sau đợt tải đêm 20 rạng 21/08:

| Nhóm | Có / Tổng | Ghi chú |
|---|---|---|
| keyframes | **14/14** | đã giải nén, xem bên dưới |
| clip_features | 1/1 | đã nạp Milvus (177.321 vector) |
| frame_maps | 1/1 | đã dựng `frame_map.parquet` |
| metadata | 1/1 | đã nạp ES (873 video) |
| objects | 1/1 | đã nạp ES (177.321 keyframe) |
| **videos** | **0/14** | **cố ý chưa tải — xem "Vì sao bỏ video"** |

**Lớp dữ liệu vận hành đợt 1 đã đủ: 18/18 gói bắt buộc có mặt, có SHA-256 và
được đối chiếu member ZIP ↔ raw; 14/14 video được audit nhưng chủ động hoãn.**
Tính theo toàn bộ URL manifest là 18/32 present, không phải thiếu 14 gói vận
hành. Audit trả exit 0, `round1_download_ready=true` và
`round1_operational_audit_complete=true`. Chi tiết bất biến nằm trong
`reports/BATCH1_OPERATIONAL_MANIFEST_20260821.json`.

Audit mới đọc central directory của từng ZIP rồi đối chiếu đúng member tương ứng,
không đếm lặp thư mục raw dùng chung. Năm part L26 lần lượt có
14.235 / 15.626 / 16.731 / 16.500 / 16.498 ảnh và đều khớp raw 100%. Tổng 18
archive bắt buộc có **357.261/357.261 asset** đã giải nén; snapshot raw tách riêng
ghi nhận **177.321 ảnh keyframe / 873 video**.

## Giải nén keyframe — 21/08, 14:51–15:11

```sh
cd data/raw/btc && tar -xf "<Downloads>/Keyframes_L<xx>.zip"
```

Archive đã có sẵn lớp bọc `keyframes/` nên đích là `data/raw/btc/`, cho ra đúng
bố cục `data/raw/btc/keyframes/<video_id>/<ordinal>.jpg` mà resolver chờ.

- **28,664 GiB** · **873/873 thư mục video** · 177.321 ảnh — khớp đúng số vector trong
  Milvus và số dòng `frame_map`.
- Snapshot lúc **19:03:39 ICT ngày 21/08**: đĩa chứa raw còn **45,714 GiB** trống
  (`49.084.526.592` byte). Đây là số tại thời điểm audit, không phải cam kết dung
  lượng cố định.
- Script chỉ ghi ảnh, không đụng parquet/index.

## Nghiệm thu trên dữ liệu thật

| Phép kiểm | Lệnh | Kết quả |
|---|---|---|
| Resolver ảnh (R1.2) | 25 keyframe ngẫu nhiên từ `frame_map` → `resolve_frame_path()` | **25/25** tìm được file |
| Ảnh Q&A/UI | `preflight_check.py --profile release` | **ảnh phủ đủ 873/873 video** |
| Không gian vector CLIP | `scripts\verify_clip_space.py --n 12` | **cosine trung bình 0,9999 · nhỏ nhất 0,9993** |

Phép kiểm thứ ba đóng lại dòng *"Model/preprocess CLIP BTC — chưa có xác nhận đủ
mạnh"* trong `AGENTS.md`: encode lại ảnh BTC bằng `ViT-B-32-quickgelu/openai` cho
cosine ≈ 1,0 với feature BTC cấp, tức query encoder đúng cùng không gian. Trước
hôm nay không kiểm được vì máy chưa có ảnh gốc.

## Vì sao bỏ 14 archive video ở đợt 1

Bài nộp là cặp số nguyên `(video_id, frame_id)`; `frame_id` tra từ
`frame_map.parquet`, **không cần ảnh và không cần video** (`AGENTS.md`). Ba
đường dùng tới video đều không chặn đợt 1:

- trích frame dày cho TRAKE → allocator phát `frame_idx` bất kỳ trong shot, không
  cần ảnh thật;
- đối chiếu pixel để kiểm `frame_map` → **mới hoàn tất 84/873 video** (6/84 có
  offset khác 0); 789 video còn lại là rủi ro đã biết, không được mô tả là đã
  verify pixel;
- ảnh làm bằng chứng Q&A → dùng keyframe BTC, giờ đã đủ.

Chỉ tải video khi một lỗi map cần đối chiếu có mục tiêu hoặc thử nghiệm
TRAKE/frame dày đã chứng minh lợi ích lớn hơn chi phí lưu trữ. Với pipeline đợt
1 hiện hành, 14 video deferred không phải blocker; pixel parity chưa đủ vẫn được
ghi riêng là rủi ro thay vì che bằng trạng thái archive.
