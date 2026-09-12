# H01 source ledger / H02 starting point

Commit `235414784b5ee80b9552fd7fe7ce898db1cbf35b`, tree `55a354bcc82e603dbcb0806a0b757bac9658ab13`. H01 infrastructure được operator phê duyệt; cache-only không được nhận là performance baseline.

15 file production/test/config H01 được định danh chính xác trong `H01_change_ledger.json` và `H01_exact_changes.patch`. Không viết lại hai commit WIP trộn thay đổi; không bỏ file người dùng.

| File | H01 family |
|---|---|
| `backend/llm/adapter.py` | H01A, H01D |
| `backend/retrieval/search.py` | H01A, H01C |
| `backend/tasks/runner.py` | H01A, H01D |
| `backend/tasks/trake.py` | H01C |
| `scripts/preflight_check.py` | H01A |
| `scripts/selfcheck.py` | H01A |
| `dev_set/tests/test_run_evaluation_runtime.py` | H01A |
| `backend/common/resource_identity.py` | H01B |
| `data/config/experiment.py` | H01B, H01D |
| `backend/common/retrieval_trace.py` | H01C |
| `scripts/run_reproducible_baseline.py` | H01C, H01D |
| `tests/test_h01_contracts.py` | H01A, H01D |
| `tests/test_resource_identity.py` | H01B |
| `tests/test_retrieval_trace.py` | H01C |
| `tests/test_baseline_harness.py` | H01C, H01D |

Các file `scripts/make_qa_trake_review.py`, `scripts/txt_to_run_queries.py`, `tests/test_qa_trake_review.py`, `tests/test_txt_to_run_queries.py`, `.claude/launch.json`, dữ liệu query vòng thi và report/audit ngoài H01 không được gán là sửa production của H01. Ledger JSON phân loại toàn bộ diff, không chỉ file Python.

Các report H01 đang dirty/untracked từ lượt trước được giữ nguyên trong starting_git_status.txt. Source/config/test đã khớp commit bắt đầu; không cần rewrite lịch sử để có attribution.
