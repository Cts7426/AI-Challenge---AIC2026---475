# Task 1 report — Product spec và nền tảng đánh giá có provenance

## Đã làm gì

- Thay `docs/product-spec.md` bằng product spec có đầy đủ các mục acceptance:
  Problem, Goals, Non-goals, User stories, Functional requirements,
  Non-functional requirements, Constraints, Acceptance criteria, Risks.
- Mở rộng GT KIS/QA/TRAKE tương thích legacy bằng `verification_status`,
  `provenance`, `verified_by`, `verified_at`. GT thiếu metadata mặc định
  `unknown`; `verified` bắt buộc có đủ audit trail.
- Thêm gate promotion fail-closed. Chế độ phân tích in rõ GT legacy chưa đủ
  promotion; `--promotion` từ chối GT `unknown` hoặc query thiếu GT parse được
  trước khi kết nối ES/Milvus.
- Đóng băng đủ 25 query vòng 1 trong manifest có provenance tới HEAD/blob.
- Thêm `batch1_holdout13`: 10 KIS + 3 QA, 13 video ID khác nhau theo legacy
  holdout GT; mọi entry vẫn `unknown`, không chép/suy đoán đáp án hay GT mới.

## File đổi

- `docs/product-spec.md`
- `docs/plans/2026-08-24-batch1-accuracy-uplift.md`
- `dev_set/tools/schema.py`
- `dev_set/tools/scoring.py`
- `dev_set/tools/run_evaluation.py`
- `dev_set/tests/test_ground_truth_verification.py`
- `dev_set/manifests/batch1_round1_queries.json`
- `dev_set/manifests/batch1_holdout13.json`

## RED

1. `& .\.venv\Scripts\python.exe -m pytest dev_set/tests/test_ground_truth_verification.py -q`

   Kết quả ban đầu: `ImportError: cannot import name
   'assess_promotion_ground_truth'`. Đây là failure đúng vì gate chưa tồn tại.

2. `& .\.venv\Scripts\python.exe -m pytest
   dev_set/tests/test_ground_truth_verification.py::test_promotion_tu_choi_query_khong_co_gt_da_parse
   -q`

   Kết quả: `TypeError ... unexpected keyword argument 'expected_query_ids'`.
   Đây là failure đúng vì gate chưa kiểm query mất GT.

3. `& .\.venv\Scripts\python.exe -m pytest
   dev_set/tests/test_ground_truth_verification.py::test_entrypoint_promotion_chan_gt_legacy_truoc_khi_ket_noi_db
   -q --basetemp '.pytest-task1-tmp'`

   Kết quả: `Failed: không được chạm ES`, chứng minh entrypoint còn kết nối DB
   trước gate. Sau đó đã chuyển kết nối xuống sau gate.

## GREEN

`& .\.venv\Scripts\python.exe -m pytest dev_set/tests/test_ground_truth_verification.py dev_set/tests/test_schema.py dev_set/tests/test_scoring.py dev_set/tests/test_run_evaluation_runtime.py -q --basetemp '.pytest-task1-tmp'`

Kết quả: `19 passed in 1.26s`.

Kiểm manifest:

- `batch1_round1_queries`: 25/25 query bằng source; Git blob SHA-1 khớp
  `7c7726920406cd3e26703dd33179fa6350f7b507`.
- `batch1_holdout13`: 10 KIS, 3 QA, 13 `unknown`; 13 video ID legacy khác nhau.

## Full suite

`& .\.venv\Scripts\python.exe -m pytest -q --basetemp '.pytest-task1-tmp'`

Kết quả: `674 passed, 1 skipped, 2 warnings in 33.92s`. Hai warning là
deprecation của `starlette.testclient` và `google.genai.types`, không phải lỗi
Task 1.

## Self-review

- Gate đọc legacy GT mà không sửa file GT hiện hành và không gán `verified` cho
  dữ liệu cũ.
- Gate giữ query thiếu GT trong `missing_query_ids`, tránh skip parse biến thành
  promotion thiếu dữ liệu.
- Entry point chặn provenance trước ES/Milvus để báo lỗi đúng nguyên nhân.
- Không stage/sửa README, `backend/llm/adapter.py`, ảnh `.tmp_*`,
  ARCHITECTURE hay các tài liệu bị cấm.

## Concern

- `dev_set/ground_truth/holdout_gt.jsonl` vẫn là legacy/unverified; do đó
  `--promotion` phải và sẽ bị từ chối cho đến khi operator human-review cung
  cấp provenance thực.
- Cleanup `C:\dev\aic2026\.pytest-task1-tmp` đã được xác minh target riêng và
  thử xóa, nhưng lệnh bị interrupt; thư mục tạm còn lại để controller xử lý,
  không thuộc commit.

## Fix round 1/5

- Chỉ sửa `docs/product-spec.md` để khôi phục approved spec: mục tiêu tự động
  10–13/13, baseline 6,8/13 và manual lookup 8,6/13, runner/trace chung, KIS
  multi-anchor, Q&A candidate-specific hypotheses, mốc 3 ngày, release gates
  overall/KIS/QA và rủi ro Public chấm 50%.
- Không thay đổi implementation, test, manifest hay file ngoài product spec.

### Verification đọc lại

- Có đúng 9 headings bắt buộc: Problem, Goals, Non-goals, User stories,
  Functional requirements, Non-functional requirements, Constraints,
  Acceptance criteria, Risks.
- Goals/Acceptance criteria nêu rõ 10–13/13, baseline 6,8/13 và manual lookup
  8,6/13; Functional requirements nêu runner/trace, multi-anchor, hypotheses
  và các ngưỡng `overall >=0.82`, `KIS >=0.82`, `QA >=0.75`.
- Constraints nêu mốc 3 ngày; Risks nêu Public chỉ chấm 50%.
- Thử stage/commit focused `docs/product-spec.md` thất bại vì
  `fatal: Unable to create 'C:/dev/aic2026/.git/index.lock: Permission denied`;
  không có file nào được stage/commit trong lượt fix này.

## Fix round 2/5

- Chỉ sửa `docs/product-spec.md`: Problem ghi 6,8/13 automatic và 8,6/13
  combined/manual là báo cáo external/unreproduced của operator, thiếu evaluator
  artefact/config/runtime fingerprint và GT verified.
- Acceptance chỉ cho phép áp gate overall >=0.82, KIS >=0.82, QA >=0.75 khi
  `batch1_holdout13` đã verified; còn `unknown` phải fail closed. Hai số external
  không còn là acceptance/promotion evidence.

### Verification đọc lại

- Problem nêu đầy đủ nguồn và giới hạn evidence của 6,8/13 và 8,6/13.
- Acceptance criteria nêu gate conditional-on-verified và fail-closed cho unknown.
- Các requirement khôi phục ở fix round 1 vẫn giữ nguyên; chỉ `docs/product-spec.md`
  thay đổi trong lượt này.
- Thử stage/commit focused tiếp tục bị chặn bởi `.git/index.lock: Permission denied`;
  controller cần commit `docs/product-spec.md`.
