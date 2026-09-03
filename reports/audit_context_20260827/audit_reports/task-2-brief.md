## Task 2: Một entrypoint solve_query và trace thống nhất

- Thêm `backend/tasks/runner.py` với `solve_query(query, total=100) -> QueryRun`.
- `QueryRun` chứa answers, query plan, source ranks/contributions, QA hypotheses,
  timing, lỗi phân loại và runtime fingerprint.
- Chuyển `run.py` và `dev_set/tools/run_evaluation.py` sang entrypoint chung mà
  không đổi CLI, checkpoint hoặc định dạng submission.
- Trace JSONL phải đủ dữ liệu phân loại retrieval_miss, wrong_frame,
  qa_reasoning, missing_evidence, trake_order và format.
- Thêm test parity và fingerprint/cache trước khi refactor.

