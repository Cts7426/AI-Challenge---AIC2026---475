# Task 5 report — promotion gates và release rehearsal

## Kết quả

Đã triển khai gate fail-closed và đường rehearsal opt-in mà không sửa retrieval,
Q&A/KIS/TRAKE logic, `backend/llm/adapter.py`, CLIP/index hay dữ liệu.

- Promotion gate chỉ đọc JSON/manifest, kiểm provenance trước score và không
  import/kết nối retrieval.
- Score promotion nay bắt buộc được sinh bằng `--promotion`, ghi exact query-set
  hash, map GT verified/hash, runtime fingerprint, scorer policy và hash source.
  Gate khóa đúng 13/25 ID cùng nội dung frozen; artefact legacy, bộ câu thay thế
  hoặc GT hash không khớp đều bị chặn.
- Gate bắt đúng `batch1_holdout13` (10 KIS + 3 QA), regression 25 câu, zero
  crash, score/task/ID/runtime/scorer contract, không giảm từng query/aggregate,
  cùng các ngưỡng overall `0.82`, KIS `0.82`, QA `0.75`.
- `run.py --release-rehearsal --zip --promotion-audit ...` dừng trước
  preflight/search nếu audit chưa ELIGIBLE. `--zip` cũ giữ nguyên hành vi.
- Release batch chặn trace thiếu/failed/retryable, fingerprint trộn, submission
  thiếu query, validator lỗi và Q&A thiếu hypothesis/canonical pin/cache inference
  đúng `evidence_digest` + runtime + `query_sha256` + `full_query_sha256`.
- Audit ELIGIBLE mang runtime/scorer đã promotion. `run.py` và primitive release
  băm lại runtime cùng `dev_set/tools/scoring.py`, so scorer policy, rồi so tiếp
  fingerprint trong trace trước khi gọi ZIP writer.
- Batch gate parse, so và băm cùng byte snapshot trace; file RAM/stale khác trace
  receipt hoặc thay đổi sau gate không thể nhận receipt.
- Promotion audit băm đủ năm input (hai manifest + ba score artefact); receipt
  xác minh lại checksum nên audit bị sửa hoặc thiếu artefact không thể release.
- ZIP writer chỉ được gọi sau các gate trên. ZIP hậu kiểm lỗi không có receipt;
  ZIP có thể còn trên đĩa nhưng không mang receipt và không được xem là usable.
- Receipt atomic lưu commit, full config snapshot/hash, trace/hash, evidence cache
  manifest/hash, fingerprint, policy, query/GT manifest, ZIP/hash, validator,
  UTC timestamp và reproduction command; checksum promotion audit được tính lại,
  không tin cờ `eligible` tự khai.

## Files

- `data/config/release_gate.py`
- `dev_set/manifests/batch1_holdout13.json`
- `dev_set/tools/promotion_provenance.py`
- `dev_set/tools/promotion_gate.py`
- `backend/export/release_rehearsal.py`
- `dev_set/tools/run_evaluation.py`
- `run.py`
- `dev_set/tests/test_promotion_gate.py`
- `tests/test_release_rehearsal.py`
- `tests/test_run.py`
- file report này

## TDD RED → GREEN

### RED đầu

```powershell
.\.venv\Scripts\python.exe -m pytest `
  dev_set/tests/test_promotion_gate.py tests/test_release_rehearsal.py -q
```

Kết quả: 2 collection error đúng nguyên nhân:

- `ModuleNotFoundError: dev_set.tools.promotion_gate`
- `ModuleNotFoundError: backend.export.release_rehearsal`

### RED integration `run.py`

Hai test rehearsal đầu đều fail `argparse: unrecognized arguments` cho
`--release-rehearsal` và `--promotion-audit`, chứng minh CLI chưa nối gate.

### GREEN cuối focused (sau fix review)

```powershell
.\.venv\Scripts\python.exe -m pytest `
  dev_set/tests/test_promotion_gate.py `
  tests/test_release_rehearsal.py `
  tests/test_run.py::test_release_rehearsal_tao_receipt_khi_promotion_va_batch_sach `
  tests/test_run.py::test_release_rehearsal_promotion_blocked_khong_tao_zip `
  -q
```

Kết quả: **29 passed**.

Covering suite runner/export/evaluator/schema: **195 passed**.

Fix round từ `task-5-review.md` thêm test cho exact frozen ID/content, artefact
legacy/GT hash, runtime/scorer binding, cache query identity, trace file/RAM,
missing/malformed input không traceback và post-write validator thật sự gọi
writer. Lệnh focused + evaluator liên quan đạt **50 passed**; riêng hai integration
`run.py` đạt **2 passed**.

## Full verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp <isolated-temp>
```

Kết quả fresh sau fix review: **805 passed, 1 skipped, 2 warnings in
42.31s**. Hai warning là deprecation từ Starlette/httpx và `google.genai`, không
phải Task 5.

`py_compile` cho toàn bộ module Task 5 và `git diff --check` đều exit `0`.

```powershell
.\.venv\Scripts\python.exe scripts/preflight_check.py --profile development
.\.venv\Scripts\python.exe scripts/preflight_check.py --profile release
```

Cả hai profile: exit `0`, **17 đạt, 0 hỏng, 2 bỏ qua**. Hai mục chưa kiểm là
`streamlit` optional và API `/health` chưa chạy; Elasticsearch/Milvus, parquet,
frame map, runtime Q&A, vector, validator ZIP và latency đều đạt. Release
preflight không fail trong môi trường hiện tại, nhưng hai SKIP vẫn không được
diễn giải là đã kiểm.

```powershell
.\.venv\Scripts\python.exe scripts/verify_clip_space.py --n 10
```

Kết quả: **ĐẠT**, cosine trung bình `0.9999`, nhỏ nhất `0.9993`; không reindex.

## Gate thật trên manifest hiện tại

```powershell
.\.venv\Scripts\python.exe -m dev_set.tools.promotion_gate `
  --output <outside-repo>/task5_actual_promotion.json
```

Kết quả: exit `1`, `status=BLOCKED`, `eligible=false`, `metrics={}`,
`public_score_used=false`. Có 13 holdout và 25 regression query chưa `verified`.
Gate dừng trước khi cần score artefact và không gọi ES/Milvus/LLM.

CLI với `--holdout-manifest dev_set/manifests/does-not-exist.json` cũng trả exit
`1`, JSON `BLOCKED`, `input_sha256.holdout_manifest="missing"` và không traceback.

Vì vậy hiện chưa có evidence để tuyên bố overall/KIS/QA đạt `0.82/0.82/0.75`
hay mục tiêu 10–13/13. Bước vận hành tiếp theo là human-verify GT/provenance,
chạy baseline/current bằng scorer contract mới rồi mới có thể tạo audit
ELIGIBLE và chạy release rehearsal.

## Lệnh vận hành sau khi có artefact verified

```powershell
python -m dev_set.tools.promotion_gate `
  --holdout-scores <holdout-current>/scores.json `
  --regression-baseline <regression-baseline>/scores.json `
  --regression-current <regression-current>/scores.json `
  --output <release>/promotion-audit.json

python run.py --queries <batch.json> --out <release> --zip `
  --release-rehearsal --promotion-audit <release>/promotion-audit.json `
  --gt-manifest <verified-gt-manifest.json> `
  --scorer-policy semantic --qa-submission-policy robust
```

Không có audit ELIGIBLE thì lệnh thứ hai trả nonzero trước retrieval và không tạo ZIP.
