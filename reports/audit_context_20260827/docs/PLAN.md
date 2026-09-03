# Kế hoạch triển khai Batch 1 accuracy uplift

## Global constraints

- Mục tiêu là pipeline tự động; không dò dataset hoặc sửa CSV thủ công.
- Không đổi CLIP, reindex ES/Milvus, tải raw video, thêm generic KIS VLM rerank
  hoặc dense-frame TRAKE.
- Không sửa `backend/llm/adapter.py`; giữ nguyên dirty worktree của người dùng.
- Mọi LLM/VLM chỉ qua `llm()`, mọi frame nộp tra từ `frame_map`, mọi tham số
  chiến thuật nằm trong `data/config/`.
- Từng thay đổi hành vi phải theo TDD: test đỏ đúng nguyên nhân, code tối thiểu,
  test xanh rồi mới refactor.
- Không bịa ground truth. Nhãn chưa được người vận hành xác minh phải mang trạng
  thái `unknown` và không được dùng trong promotion gate.

## Task 1: Product spec và nền tảng đánh giá có provenance

- Thay nội dung `docs/product-spec.md` bằng đặc tả đã duyệt với đúng các mục:
  Problem, Goals, Non-goals, User stories, Functional requirements,
  Non-functional requirements, Constraints, Acceptance criteria, Risks.
- Mở rộng schema ground truth bằng metadata `verification_status`, `provenance`,
  `verified_by`, `verified_at` theo cách tương thích dữ liệu cũ.
- Scorer promotion chỉ nhận nhãn `verified`; chế độ phân tích legacy vẫn đọc
  được GT cũ nhưng phải báo rõ không đủ điều kiện promotion.
- Đóng băng đủ 25 query vòng 1 từ artefact/HEAD mà không sửa file query đang dùng.
- Chọn 10 KIS + 3 QA từ Batch 1 holdout hiện có làm manifest
  `batch1_holdout13`; giữ nhãn `unknown` nếu chưa xác minh, không bịa đáp án.
- Thêm test schema/gate trước khi sửa production code.

## Task 2: Một entrypoint solve_query và trace thống nhất

- Thêm `backend/tasks/runner.py` với `solve_query(query, total=100) -> QueryRun`.
- `QueryRun` chứa answers, query plan, source ranks/contributions, QA hypotheses,
  timing, lỗi phân loại và runtime fingerprint.
- Chuyển `run.py` và `dev_set/tools/run_evaluation.py` sang entrypoint chung mà
  không đổi CLI, checkpoint hoặc định dạng submission.
- Trace JSONL phải đủ dữ liệu phân loại retrieval_miss, wrong_frame,
  qa_reasoning, missing_evidence, trake_order và format.
- Thêm test parity và fingerprint/cache trước khi refactor.

## Task 3: KIS multi-anchor trên search hiện tại

- Thêm `QueryPlan`/`QueryAnchor`, tối đa ba anchor, tối đa 60 token CLIP thực tế.
- Query ngắn dùng single-anchor; planner lỗi hoặc anchor không trung thành phải
  fallback về dịch hiện tại.
- Validator chặn màu, số và số lượng mới không xuất hiện trong query gốc.
- Gọi `search()` độc lập cho từng anchor rồi hợp nhất ở shot/video bằng RRF k=7;
  query ordered nhận soft temporal bonus mặc định 1.25, không hard-filter.
- Mọi knob nằm trong `data/config/`; không đổi vector/index/search branch.
- Thêm test anchor/token/fidelity/fallback/RRF/temporal trước code.

## Task 4: Q&A candidate-specific hypotheses

- Mở rộng question plan với answer_mode: visual_count, visual_read, ocr, asr,
  metadata, visual_attribute; structured planner lỗi thì fallback rule hiện tại.
- Thêm `QAHypothesis` gắn answer với video/shot/keyframe/frame, confidence,
  evidence_hash và provenance.
- Thu thập mọi hypothesis hợp lệ trong candidate budget, thay vì chỉ giữ một
  global answer.
- Portfolio round-robin canonical evidence của từng hypothesis trước frame thay
  thế; chỉ phần đuôi mới dùng best-supported answer cho candidate chưa dùng.
- Loại sentinel answer; không hypothesis hợp lệ thì trả failure/retryable và
  không tạo ZIP một phần.
- Cache key gồm query/model/prompt/config/evidence; không đổi provider tự động.
- Thêm test answer mode, evidence pinning, sentinel và portfolio trước code.

## Task 5: Release gates, replay và tài liệu vận hành

- Thêm gate zero-crash, GT verified, overall >=0.82, KIS >=0.82, QA >=0.75,
  regression không giảm; không tuyên bố đạt nếu thiếu nhãn verified.
- Release artefact gồm commit, config snapshot, trace, evidence cache, runtime
  fingerprint, scorer policy, ZIP checksum và lệnh tái lập.
- Validator phải chặn batch thiếu query/evidence, không sinh ZIP một phần.
- Chạy targeted tests, full suite, preflight development, CLIP guard không chạm
  vector/index và release rehearsal offline phù hợp môi trường.
- Ghi kết quả đo thật và blocker còn lại; Public chỉ là xác nhận bên ngoài.
