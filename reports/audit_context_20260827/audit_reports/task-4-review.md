# Review Task 4 — Q&A candidate-specific hypotheses

## Verdict

**CHANGES REQUIRED.** Focused suite đã chạy xanh (`128 passed`), nhưng diff còn
các lỗi correctness/determinism có thể làm trace hợp lệ bề ngoài trong khi
hypothesis hoặc checkpoint không còn đúng evidence/runtime.

## Findings

### [P1] Vẫn early-stop toàn bộ video expansion khi một main candidate tự báo confidence cao

- File: `backend/tasks/qa.py:1616`
- Điều kiện `best is None or best[4] < HIGH_CONFIDENCE_EARLY_STOP` khiến toàn bộ
  budget `VIDEO_EXPAND_SHOTS × MAX_VIDEOS_EXPANDED` không được thử nếu một shot
  main/text trả lời plausibly nhưng sai với confidence >= 0.9. Đây chính là dạng
  lỗi candidate-specific hypotheses cần giảm: một đáp án sai tự tin tiếp tục ngăn
  các shot khác trong đúng video tạo hypothesis. Plan/review brief yêu cầu thu
  mọi hypothesis hợp lệ trong candidate budget và không để early-stop còn sót.
- Cần làm budget expansion cố định/deterministic và thử hết budget đó (trừ
  generation budget thật sự cạn), hoặc loại expansion khỏi budget bằng một gate
  cấu hình/acceptance rõ ràng; không dùng confidence tự khai của LLM để bỏ cả
  cohort candidate.
- Thiếu test: main candidate confidence cao nhưng expansion candidate tạo một
  hypothesis hợp lệ thứ hai; trace phải giữ cả hai.

### [P1] Image fallback không có frame gắn answer text vào sai evidence digest

- File: `backend/tasks/qa.py:1194-1213`
- `_infer_legacy()` lưu `original_evidence_hash`, nhưng chỉ khôi phục hash text ở
  nhánh `ev_img.frames` có thật và `with_images` rỗng. Khi lần
  `collect_evidence(..., needs_images=True)` trả `frames=[]`, nó vẫn cập nhật
  `_qa_attempt_ctx["evidence_hash"]`; hàm sau đó vote cohort text cũ mà không
  restore digest. Hypothesis vì vậy khai provenance của một capture image-request
  rỗng dù answer thực tế đến từ text.
- Đã tái lập read-only: answer là `red`, `actual_hash='i'*64`, trong khi hash
  cohort text đúng là `'t'*64`.
- Cần restore hash text cho mọi đường không thay `results` bằng cohort image; nên
  lưu/ghi rõ stage (`text`/`image`) trong attempt/provenance và thêm test riêng
  cho `ev_img.frames == []`.

### [P1] Runtime fingerprint bỏ sót code allocator portfolio mới

- File: `backend/tasks/runner.py:236-245`
- `runtime_manifest().critical_sources_sha256` hash `qa.py` và `runner.py` nhưng
  không hash `backend/tasks/qa_portfolio.py`. Chỉ sửa thứ tự canonical,
  alternative hoặc tail trong file mới này sẽ không đổi fingerprint; `run.py`
  có thể coi checkpoint cũ là hợp lệ và xuất lại answers theo code portfolio cũ.
  Điều này vi phạm FR7/deterministic resume.
- Cần thêm `backend/tasks/qa_portfolio.py` vào critical source snapshot và test
  chứng minh fingerprint đổi khi content/hash của module portfolio đổi.

### [P1] Inference cache identity chưa chứa hash của full query gốc

- File: `backend/tasks/qa.py:1015-1040`, `backend/tasks/qa.py:1120-1129`
- Identity hiện hash duy nhất `question_vi` sau planner. Hai query gốc khác nhau
  có thể được planner rút về cùng câu hỏi ngắn, gặp cùng evidence digest và cùng
  runtime, rồi dùng chung inference output. Functional requirement yêu cầu cache
  key gồm query/model/prompt/config/evidence; hash planner của full query không
  được truyền xuống inference identity.
- Cần đóng băng full `query_vi` trong context của `qa_pipeline`, đưa hash đó vào
  inference identity (bên cạnh hash question/prompt nếu hữu ích), và test hai full
  query khác nhau nhưng cùng `question_vi` + evidence không cache-hit lẫn nhau.

### [P2] Cache file atomic nhưng chưa thread-safe/single-flight cho cùng key

- File: `backend/tasks/qa.py:1048-1086`, `backend/tasks/qa.py:1131-1139`
- Temp file theo pid/thread và `replace()` tránh file rách, nhưng chuỗi
  get→LLM→put không có lock theo key. Hai request đồng thời cùng identity đều có
  thể miss, gọi LLM hai lần, dùng hai output khác nhau rồi last-writer-wins. Kết
  quả hai QueryRun trong cùng runtime không còn deterministic dù cache cuối hợp lệ.
- Cần lock/single-flight theo key bao quanh lần kiểm tra thứ hai + inference + put
  (không giữ global lock cho các key khác), và test concurrent cùng key chỉ gọi
  inference một lần. Corrupt/mismatch hiện đã fail closed đúng yêu cầu.

### [P2] Compatibility bridge có thể tổng hợp evidence hash ngoài test

- File: `backend/tasks/qa.py:1312-1341`, `backend/tasks/qa.py:1573-1576`,
  `backend/tasks/qa.py:1665-1668`
- Quyết định cho phép synthetic digest dựa vào identity của function
  (`_try_shot is not _ORIGINAL_TRY_SHOT or collect_evidence is not ...`), không
  dựa vào một test-only dependency explicit. Bất kỳ wrapper/instrumentation hoặc
  hot patch production nào cũng bật đường `legacy_test_double`; digest synthetic
  sau đó không được đánh dấu trong `QAHypothesis.provenance` và có thể đi tới CSV.
- Production runner phải luôn fail closed khi attempt thiếu digest thật. Test
  doubles nên tự cấp evidence hash hợp lệ hoặc dùng dependency/context test-only
  explicit không thể bật ngầm bởi việc wrap function.

### [P2] Sentinel guard chỉ chặn exact phrase sau trim punctuation

- File: `backend/tasks/qa.py:397-412`, `data/config/qa_hypotheses.py:27-35`
- Các câu sentinel tự nhiên như `"Không đủ căn cứ để xác định"` hoặc
  `"Không có thông tin trong bằng chứng"` vẫn qua `is_valid_qa_answer()` và có
  thể vào submission. Normalizer cũng chưa chuẩn hóa Unicode composition.
- Cần policy cấu hình cho prefix/variant an toàn (và NFC/NFKC), kèm negative test
  để không loại một answer thật chỉ vì chứa chuỗi gần giống.

## Checks performed

- Đọc đầy đủ `AGENTS.md`, skill retrieval, Task 4 brief/report,
  `docs/product-spec.md` và diff `7dcd8db..4d28d93`.
- `git diff --check 7dcd8db 4d28d93`: sạch.
- Focused integration suite:
  `128 passed, 1 warning` cho QA hypotheses, QA legacy/text fallback, runner,
  run.py, API và evaluator runtime.
- Xác nhận không sửa `backend/llm/adapter.py`, không đổi `SLOT_BUDGET` hay default
  `QA_INFERENCE_MODE=legacy`; không thấy provider-switch mới.

---

## Scoped re-review — fix commit `0853535`

### Verdict

**APPROVED.** Bảy finding của vòng đầu đều đã được xử lý trong scope; không thấy
regression mới trực tiếp từ fix.

### Finding disposition

1. **Early-stop expansion — ADDRESSED.** Gate theo confidence đã bị bỏ;
   `backend/tasks/qa.py:1697-1767` thử hết video-expansion budget xác định, chỉ
   dừng khi generation budget thực sự cạn. Test mới khóa trường hợp main `.99`
   vẫn thu hypothesis expansion.
2. **Sai evidence cohort khi image fallback — ADDRESSED.** Snapshot/restore đủ
   `evidence_hash`, `evidence_type`, `evidence_stage` cho cả legacy và two-stage;
   nhánh không có frame và nhánh image không có output đều quay về cohort text.
3. **Fingerprint thiếu portfolio — ADDRESSED.** `backend/tasks/runner.py` đã đưa
   `backend/tasks/qa_portfolio.py` vào `critical_sources_sha256`, có test chứng
   minh fingerprint đổi khi hash module đổi.
4. **Cache thiếu full query — ADDRESSED.** `qa_pipeline()` đặt SHA-256 full query
   trong `ContextVar`, inference identity giữ cả `query_sha256` của planned
   question và `full_query_sha256`; token được reset trong `finally`, có test
   tách hai full query và test không leak context.
5. **Concurrent cache race — ADDRESSED.** Per-key single-flight thực hiện
   double-check cache dưới lock, các key khác không bị serialize; `finally` dọn
   registry sau waiter cuối. Test planner và inference đồng thời xác nhận đúng
   một provider call và registry về 0.
6. **Synthetic test-double digest — ADDRESSED.** Bridge dựa function identity đã
   bị xóa. `_evidence_hash_for_attempt()` luôn fail closed; test doubles phải gắn
   digest explicit vào attempt context.
7. **Sentinel variants/false positives — ADDRESSED.** Normalizer dùng NFKC;
   prefix chỉ bị reject khi token tiếp theo nằm trong continuation allowlist cấu
   hình. Test bao phủ các biến thể sentinel và giữ hợp lệ các answer như
   `No Information Technology`/`Không có thông tin liên lạc`.

### Checks

- `git diff --check 4d28d93 0853535`: sạch.
- Focused QA/runner/run/API/evaluator suite: **144 passed, 1 warning**.
- Không có thay đổi mới ở adapter, `SLOT_BUDGET` hoặc default legacy.
