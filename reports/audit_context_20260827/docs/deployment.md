# Triển khai và vận hành

Repo chạy local trên Windows 11 (hoặc môi trường Docker tương đương). Đây không
phải dịch vụ cloud triển khai liên tục: “release” là một batch tái lập được để
nộp BTC.

## Hạ tầng local

Milvus standalone và Elasticsearch single-node được định nghĩa trong
`docker-compose.yml`.

```powershell
docker compose up -d
docker compose ps
```

Milvus có thể cần khoảng 90 giây để healthy. Dừng dịch vụ mà giữ dữ liệu:

```powershell
docker compose down
```

`docker compose down -v` xoá named volume index; chỉ dùng khi đã chủ đích
rebuild index và xác minh target.

## Nạp dữ liệu

Raw BTC, parquet derived và index là ba lớp khác nhau. Loader có thể chạy lại
idempotent, nhưng không được xoá/recreate dữ liệu đợt trước nếu schema/model còn
tương thích.

```powershell
python -m backend.indexing.load_metadata
python -m backend.indexing.load_objects
python -m backend.indexing.load_clip
python -m backend.indexing.load_ocr
python -m backend.indexing.load_asr
```

Job OCR/ASR nặng chạy offline ở Colab/Kaggle, có checkpoint/resume; không cài
model GPU nặng vào máy vận hành local.

## Chạy batch release

Operator phải chọn backend/model LLM tường minh trong đúng process chạy batch.
Preflight chỉ in lại cấu hình, không tự chọn provider/model và không gọi thử API.

```powershell
$env:LLM_BACKEND = "api"
$env:LLM_API_MODEL = "<model-da-chon>"
$env:QA_INFERENCE_MODE = "legacy"
python scripts/preflight_check.py --profile release
python run.py queries.json --out submissions\round1 --zip --qa-submission-policy robust
```

Release Q&A luôn truyền `--qa-submission-policy`. Có thể dùng `all` để tạo các
portfolio từ cùng evidence, nhưng chỉ chọn một ZIP để nộp và lưu lại policy/SHA-256.

## Cổng release

1. Kiểm tra data manifest, schema/model/map và service bằng release preflight.
2. Chạy test, tune regression và holdout promotion theo `AGENTS.md`.
3. Chạy batch từ checkpoint sạch; không resume khi runtime fingerprint khác model.
4. Chạy validator, kiểm ZIP và checksum; chỉ nộp một gói đã chọn.
5. Lưu receipt, config snapshot, log, score/evidence và đóng băng theo thời gian
   quy định.

Quy trình thao tác theo mốc thời gian chi tiết nằm ở
[RUNBOOK_ROUND1.md](RUNBOOK_ROUND1.md).
