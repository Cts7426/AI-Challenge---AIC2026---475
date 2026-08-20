# Audit dữ liệu Batch 1 — 21/08/2026

Nguồn manifest:
`C:\Users\lehon\Downloads\Dữ liệu cho vòng Sơ Tuyển AIC 2026 - Batch1.csv`.

Lệnh kiểm:

```powershell
.venv\Scripts\python.exe scripts\audit_batch_manifest.py `
  "C:\Users\lehon\Downloads\Dữ liệu cho vòng Sơ Tuyển AIC 2026 - Batch1.csv" `
  --archives-dir "C:\Users\lehon\Downloads" --hash
```

## Kết quả hiện tại

- Manifest có **32 archive**: 14 keyframes, 14 videos, 1 CLIP features,
  1 frame maps, 1 metadata và 1 objects.
- Đã có: **1/32** — `Keyframes_L21.zip`.
- Còn thiếu: **31/32**.
- `Keyframes_L21.zip`: 1,447,092,929 byte.
- SHA-256:
  `30412ab4c3c5f3bbd7cef0feb59e7670a6683d2d8d4a90b196cea9688d554221`.

## Kết luận vận hành

R1.1 chưa đạt. CSV chỉ chứa URL, không chứa ảnh/video. Các cảnh báo Q&A tại L26
và L28 là đúng vì máy chưa có archive tương ứng và chưa có JPG đã giải nén dưới
`data/raw/btc/keyframes` hoặc `data/derived/keyframes`.

Không chạy script chuyển đổi có thể ghi lại `frame_map.parquet` hoặc
`keyframes.parquet` chỉ để xử lý archive ảnh. Sau mỗi đợt tải, chạy lại audit,
tính hash, giải nén vào raw root rồi chạy `preflight_check.py --profile release`.
