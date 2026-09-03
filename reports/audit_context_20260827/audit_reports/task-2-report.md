# Task 2 report — entrypoint `solve_query` và trace thống nhất

## Trạng thái

Hoàn thành implementation và verification. `run.py` và evaluator cùng gọi
`backend.tasks.runner.solve_query()`; `run_minimal.py` giữ nguyên đúng phạm vi.

## Files

- `backend/tasks/runner.py` — thêm `QueryRun`, `SolveQueryError`,
  `solve_query()`, failure trace và runtime manifest/fingerprint không chứa secret.
- `run.py` — giữ `giai_mot_query()` làm compatibility wrapper; checkpoint khóa
  runtime fingerprint; ghi `trace.jsonl` append + flush + fsync cho cả success/failure.
- `dev_set/tools/run_evaluation.py` — bỏ dispatch KIS/QA/TRAKE riêng; scoring và
  GT failure classification vẫn ở dev_set; dùng raw rows của `QueryRun`, không
  search lần hai; `candidates.jsonl` trở thành trace đầy đủ và fsync từng query.
- `tests/test_task_runner.py` — contract/parity/shared-runner/fingerprint/trace/
  QA-TRAKE metadata tests, mock đúng search/QA/TRAKE external boundary.
- `tests/test_run.py` — kiểm trace production success/failure và checkpoint hết
  hạn khi model đổi.
- File report này.

## Interfaces

- `solve_query(query, total=100, *, runtime_fingerprint=None) -> QueryRun`
  nhận mapping hoặc object có field của `dev_set Query`, không import dev_set.
- `QueryRun` giữ answers, query plan, raw search rows, source ranks/contributions,
  placeholder `qa_hypotheses`, timings, status/failure class, runtime fingerprint,
  task metadata, `answer_text`, `qa_trace` và `n_trake`.
- `QueryRun.to_trace_dict()` trả record JSON-safe; failed run luôn có answers rỗng.
- `SolveQueryError.query_run` cho caller ghi failure trace rồi retry, không ghi
  checkpoint success.
- Failure class mới chỉ thuộc sáu nhãn spec: `retrieval_miss`, `wrong_frame`,
  `qa_reasoning`, `missing_evidence`, `trake_order`, `format`; success dùng
  `status="success"` và `failure_class=null`.

## TDD evidence

### RED 1 — runner contract

Lệnh:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_task_runner.py -q
```

Kết quả trước implementation: `12 failed in 1.66s`; cả 12 fail đúng vì
`ModuleNotFoundError: No module named 'backend.tasks.runner'`.

### GREEN 1

Lệnh như trên sau implementation.

Kết quả: `12 passed in 1.12s`.

### RED 2 — cache/runtime fingerprint

Lệnh:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_run.py::test_doi_model_thi_checkpoint_het_han -q --basetemp .pytest_tmp_task2_red2
```

Kết quả trước checkpoint guard: `1 failed`; lần chạy model-b gọi `[]` thay vì
`["q1", "q2"]`, chứng minh checkpoint đang trộn model.

### GREEN 2

Lệnh tương ứng với basetemp green: kết quả `1 passed in 0.81s`.

## Verification

Focused regression cuối cùng:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_task_runner.py tests/test_run.py tests/test_eval.py tests/test_qa.py tests/test_trake.py -q --basetemp .pytest_tmp_task2_verify1
```

Kết quả mới nhất: `178 passed in 2.90s`.

Full suite:

```powershell
.\.venv\Scripts\python.exe -m pytest --lf --last-failed-no-failures none -q --basetemp .pytest_tmp_task2_lastfailed
```

Kết quả: `687 passed, 1 skipped, 2 warnings in 34.42s`, exit code 0. Hai warning
đều từ dependency (`StarletteDeprecationWarning`, `google.genai` deprecation),
không phải code Task 2.

Kiểm syntax/diff:

```powershell
.\.venv\Scripts\python.exe -m py_compile backend/tasks/runner.py run.py dev_set/tools/run_evaluation.py
git diff --check -- run.py dev_set/tools/run_evaluation.py tests/test_run.py
```

Kết quả: exit code 0, không có output lỗi.

## Self-review

- Không sửa `README.md`, `backend/llm/adapter.py`, `run_minimal.py`, ảnh `.tmp_*`,
  docs/manifest/GT Task 1 hay file ngoài Task 2.
- Search vẫn qua engine hiện hữu; không đổi vector/model/metric/frame mapping và
  không gọi service thật trong test.
- Evaluator lấy KIS ranks/contributions và mọi candidate row từ chính QueryRun;
  QA/TRAKE giữ candidate rows mà pipeline hiện có thể cung cấp, không chạy search
  debug lần hai.
- Trace production và evaluator đều append-only; failure trace có typed status
  nhưng không có partial/fake answers. Checkpoint success vẫn giữ format cũ và
  chỉ thêm runtime fingerprint.
- Runtime manifest chỉ chứa backend/model đang hoạt động, QA mode và SHA-256 của
  config/critical source; API key và secret env không được đọc hoặc serialize.
- Mutation checks được phủ: bỏ raw rows sẽ fail runner/evaluator test; giữ dispatch
  cũ sẽ fail parity/shared runner; đổi model mà reuse checkpoint sẽ fail resume
  test; dùng nhãn F0 sẽ fail failure-class validation.

## Concerns

- Commit focused đã thử đúng một lần nhưng sandbox từ chối ghi Git index:
  `fatal: Unable to create 'C:/dev/aic2026/.git/index.lock': Permission denied`.
  Không có file Task 2 nào được stage/commit; controller cần commit ngoài sandbox.
- Checkpoint legacy chưa có `runtime_fingerprint` sẽ bị coi hết hạn và compute
  lại có chủ đích (fail closed để không trộn model/runtime).
- `qa_hypotheses` mới là placeholder rỗng theo Task 2; Task Q&A hypothesis/evidence
  sau sẽ điền schema này.
- Không chạy regression chất lượng có service thật vì Task 2 là correctness/
  orchestration và brief cấm service thật trong tests; full unit suite đã xanh.

---

## Fix round 1/5 — fingerprint, JSON-safe trace, env restore

### Findings và root cause

1. Evaluator từng băm `split` + source evaluator rồi truyền hash đó vào
   `solve_query`; vì vậy cùng query runtime lại có identity khác production và
   khác giữa tune/holdout. Đã tách `query_runtime_fingerprint` lấy trực tiếp từ
   `backend.tasks.runner` và `evaluation_artifact_fingerprint` chứa split,
   evaluator/scorer cùng query/GT input hashes.
2. `QueryRun.to_trace_dict()` từng trả thẳng numpy/parquet scalar/container,
   Path và datetime; exception serialize xảy ra sau solve success. Đã thêm
   normalization đệ quy: mapping giữ mapping, sequence/set/container thành list,
   numpy `tolist()`/`item()`, parquet `as_py()`, Path POSIX, datetime ISO-8601;
   NaN/Infinity có policy rõ là JSON `null`, unknown type fail explicit thay vì
   stringify tùy tiện.
3. Env evidence chỉ `pop()` ở normal path. Đã bọc toàn bộ `run_evaluation()` bằng
   decorator `try/finally`, lưu và restore cả giá trị cũ lẫn trạng thái unset cho
   `LLM_RUN_ID`, `LLM_QUERY_ID`, `QA_EVIDENCE_LOG_PATH` trên mọi exception/SystemExit.

### Files sửa trong round

- `backend/tasks/runner.py`
- `dev_set/tools/run_evaluation.py`
- `tests/test_task_runner.py`
- `dev_set/tests/test_run_evaluation_runtime.py`

Không sửa handle leak `run.py` hay file ngoài Task 2/tests.

### RED evidence

Fingerprint:

```powershell
.\.venv\Scripts\python.exe -m pytest dev_set/tests/test_run_evaluation_runtime.py::test_query_fingerprint_dung_runner_va_khong_doi_theo_split -q --basetemp .pytest_tmp_task2_fix1_red_fp
```

Kết quả: `1 failed in 1.47s`; manifest trả `None` thay vì runner fingerprint.

JSON-safe trace:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_task_runner.py::test_trace_json_normalize_numpy_container_path_datetime_va_non_finite -q --basetemp .pytest_tmp_task2_fix1_red_json
```

Kết quả: `1 failed in 0.20s`; `TypeError: Object of type int64 is not JSON serializable`.

Env restore:

```powershell
.\.venv\Scripts\python.exe -m pytest dev_set/tests/test_run_evaluation_runtime.py::test_run_evaluation_restore_env_khi_exception_sau_khi_setup -q --basetemp .pytest_tmp_task2_fix1_red_env
```

Kết quả: `1 failed in 1.54s`; `LLM_RUN_ID` còn `resume-run` thay vì `before-run`.

### GREEN evidence

- Fingerprint test: `1 passed in 1.27s`.
- JSON test lần đầu còn phát hiện Path Windows dùng backslash; sửa normalization
  sang `Path.as_posix()`, lần chạy kế: `1 passed in 0.14s`.
- Env restore test: `1 passed in 1.31s`.

Covering suite theo yêu cầu, không chạy full suite:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_task_runner.py tests/test_run.py dev_set/tests/test_run_evaluation_runtime.py dev_set/tests/test_ground_truth_verification.py -q --basetemp .pytest_tmp_task2_fix1_cover
```

Kết quả: `64 passed in 2.37s`.

Syntax/diff check:

```powershell
.\.venv\Scripts\python.exe -m py_compile backend/tasks/runner.py dev_set/tools/run_evaluation.py tests/test_task_runner.py dev_set/tests/test_run_evaluation_runtime.py
git diff --check -- backend/tasks/runner.py dev_set/tools/run_evaluation.py tests/test_task_runner.py dev_set/tests/test_run_evaluation_runtime.py
```

Kết quả: exit code 0, không có lỗi.

### Self-review fix round

- QueryRun/evaluator record dùng query fingerprint chung; run directory và
  snapshot lưu hai fingerprint với tên tường minh. Hai key legacy
  `runtime_fingerprint`/`runtime_manifest` nay trỏ query identity để cache consumer
  cũ không tiếp tục dùng artifact identity.
- Resume kiểm cả query runtime và evaluation artifact; split/scorer/GT đổi vẫn
  từ chối nối artefact, nhưng không làm thay QueryRun/cache identity.
- Normalizer không import numpy/pyarrow vào production và không thêm dependency;
  chỉ dùng protocol của object, vẫn fail rõ với type không hỗ trợ.
- Env restore giữ đúng giá trị caller có trước, không chỉ xóa; test ép exception
  sau setup thực của evaluator và không gọi service thật.

### Concerns fix round

- Snapshot schema vẫn là v2 để đọc key legacy, nhưng artefact v2 cũ không có
  `evaluation_artifact_fingerprint` sẽ bị resume fail closed; cần tạo run mới.
- Không chạy full suite đúng chỉ dẫn fix round; covering suite 64 test đã xanh.
