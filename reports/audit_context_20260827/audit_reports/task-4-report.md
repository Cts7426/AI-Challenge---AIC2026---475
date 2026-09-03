# Task 4 report — Q&A candidate-specific hypotheses

## Kết quả

Đã triển khai lát cắt end-to-end Q&A hypotheses mà không sửa
`backend/llm/adapter.py`, không đổi `QA_INFERENCE_MODE=legacy`, không chạm KIS,
TRAKE, vector/index hay `SLOT_BUDGET`.

## TDD RED → GREEN

1. RED đầu: `tests/test_qa_hypotheses.py` có **11 fail** đúng vì chưa có
   `answer_mode`, fallback schema, `QAHypothesis`, sentinel guard, portfolio,
   cache identity và runner retryable.
2. GREEN đầu: **11 passed**; focused QA/runner/run/API: **110 passed**.
3. RED vòng self-review: **2 fail** cho structured mode chưa điều khiển route và
   constructor hypothesis chưa fail-closed. GREEN: **13 passed**.
4. RED theo review controller: **5 fail** cho punctuation sentinel, production
   thiếu evidence digest, planner cache end-to-end và `hypotheses > total`.
   GREEN: **18 passed**.
5. RED provenance: **1 fail** khi image fallback không có output nhưng digest ảnh
   ghi đè digest text. Đã trả digest về đúng cohort text.
6. RED compatibility đúng nghĩa: **3 fail** chứng minh planner fallback đang làm
   lệch route `text_first`; thêm `planner_fallback` để giữ nguyên rule routing cũ.
7. Targeted cuối: **20 passed**.
8. Full suite fresh sau mọi refactor: **750 passed, 1 skipped,
   2 warnings, 36.73s**. Targeted cuối **20 passed** và `py_compile` xanh.

Hai warning là warning dependency có sẵn (`starlette.testclient` và
`google.genai.types`), không phát sinh từ Task 4.

## Files

- `backend/tasks/qa.py`
  - `QuestionParts.answer_mode` và `planner_fallback`.
  - frozen `QAHypothesis`, sentinel guard, pin exact `frame_map`.
  - thu mọi hypothesis hợp lệ trong candidate budget chính; winner mạnh nhất vẫn
    là `answer_text` compatibility.
  - evidence digest luôn tính; production thiếu digest fail-closed.
  - planner/inference cache có runtime fingerprint và trace hypotheses.
- `backend/tasks/qa_portfolio.py`
  - canonical của mọi hypothesis trước, round-robin mapped alternatives, rồi tail
    candidate chưa dùng bằng strongest supported answer; đủ `total` hoặc raise.
- `backend/tasks/runner.py`
  - truyền runtime fingerprint vào QA, deserialize hypotheses, dùng portfolio mới,
    ghi `qa_hypotheses`, `answer_mode`, `planner_fallback`, `retryable`.
- `data/config/qa_hypotheses.py`
  - enum, prompt/cache version, sentinel, cache dir và alternatives knob.
- `tests/test_qa_hypotheses.py`
  - 20 test cho planner, fallback, pin/hash/provenance, sentinel punctuation,
    canonical/alternative/tail, cache/fingerprint, retryable và runner output.

## Quyết định kỹ thuật

- `qa_pipeline()` giữ nguyên contract 2/3-tuple. Production trace luôn có khóa
  `hypotheses`; `hypotheses=[]` fail `missing_evidence` và retryable. Runner chỉ
  dùng allocator legacy khi trace cũ **không có** khóa này để các caller/mock cũ
  không vỡ trong giai đoạn chuyển tiếp.
- Structured `answer_mode` điều khiển evidence route. Khi planner lỗi/schema sai,
  `planner_fallback=True` buộc dùng nguyên `route_question()` hiện hành, nên
  `text_first` vẫn text-first chứ không bị đổi thành VLM.
- Cache inference identity gồm query SHA-256, backend/model, prompt version,
  snapshot config, evidence digest và runtime fingerprint. Planner cache dùng
  các chiều tương tự trừ evidence (planner chạy trước evidence). Fingerprint đổi
  tạo cache miss; record cùng key nhưng sai identity/schema bị từ chối.
- Production không có compatibility bridge hay synthetic digest. Thiếu
  `evidence_hash` luôn raise; test doubles phải ghi digest explicit vào
  `_qa_attempt_ctx`.
- `QA_HYPOTHESIS_ALTERNATIVES_PER_HYPOTHESIS=1` là knob mới; không sửa bảng
  `SLOT_BUDGET`. Nếu số canonical lớn hơn `total`, portfolio raise thay vì âm thầm
  bỏ hypothesis.

## Concern còn lại

- Chưa có GT `batch1_holdout13` verified và không gọi API/model release trong task
  này, nên chưa có bằng chứng tăng điểm hay đạt 10–13/13.
- Knob một alternative/hypothesis cần replay tune + holdout trên evidence cố định
  trước promotion; hiện chỉ chứng minh correctness/determinism.
- Compatibility fallback cho trace không có khóa `hypotheses` nên được bỏ sau khi
  mọi external caller đã chuyển sang schema trace mới.

## Fix round 1 sau code review

Đã xử lý toàn bộ 7 findings trong `task-4-review.md` theo RED → GREEN:

1. Thêm RED cho main hypothesis confidence `0.99` nhưng video expansion còn một
   hypothesis khác. Bỏ hoàn toàn confidence gate; expansion luôn thử đủ
   `MAX_VIDEOS_EXPANDED × VIDEO_EXPAND_SHOTS`, trừ generation budget cạn.
2. Thêm RED legacy/two-stage khi image escalation trả `frames=[]` và khi image
   inference không có output. Snapshot/restore đủ `evidence_hash`,
   `evidence_type`, `evidence_stage` về cohort text nếu results không chuyển sang
   cohort image.
3. Thêm `backend/tasks/qa_portfolio.py` vào critical source hash và test chứng minh
   thay hash file này làm runtime fingerprint đổi.
4. Thêm context hash của full query gốc; inference identity nay giữ cả
   `query_sha256` của planned question và `full_query_sha256`. Hai full query khác
   nhau nhưng cùng planned question/evidence không cache-hit lẫn nhau; context
   được reset sau `qa_pipeline()`.
5. Thêm single-flight per cache key cho planner và inference. Registry đếm waiter,
   xóa entry khi waiter cuối rời đi; hai thread cùng key chỉ gọi `llm()` một lần,
   key khác không bị global serialization.
6. Xóa bridge dựa trên identity `_try_shot`/`collect_evidence`. Wrapper/hot patch
   không thể tự bật synthetic digest; các test double legacy nay cấp digest
   explicit trong test.
7. Sentinel normalize NFKC + punctuation và dùng policy prefix/continuation trong
   config. Các surface như “Không đủ căn cứ để trả lời”, “No information is
   available” bị loại, còn “No Information Technology” và answer chỉ chứa phrase
   ở giữa vẫn được giữ.

Verification fix round 1:

- Focused QA/runner/run/API/evaluator: **194 passed, 1 warning, 3.59s**.
- Full suite fresh: **766 passed, 1 skipped, 2 warnings, 39.16s**.
- `py_compile` xanh cho QA, portfolio, runner và config; `git diff --check` sạch.
