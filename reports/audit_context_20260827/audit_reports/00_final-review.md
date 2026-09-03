# Final integration review — `b8090cd..9b107cd`

## Verdict

**CHANGES REQUESTED.** Không thấy P0, nhưng còn ba finding P1 và hai finding P2
trực tiếp ở các giao tuyến Task 1–5. Full suite xanh không bắt các contract này.

Phạm vi review là commit range `b8090cd85133433cbaa5a37d542abea48c778f5c`
đến `9b107cd7e0c6af948f4e6869b9b5fb67b86b7e19` trên
`codex/batch1-accuracy-uplift`. Dirty worktree ngoài range được giữ nguyên.

## Findings

### [P1] Evaluator không thể sinh artefact cho đúng hai frozen set mà gate bắt buộc

- File: `dev_set/tools/run_evaluation.py:236`
- File: `dev_set/tools/run_evaluation.py:263-269`
- File: `data/config/release_gate.py:10-38`
- File: `dev_set/tools/promotion_gate.py:222-250`

`run_evaluation` chỉ nhận năm split cố định và luôn đọc toàn bộ ba file
`dev_set/queries/{split}_{kis,qa,trake}.jsonl`. Không có option manifest/ID để
chạy đúng `batch1_holdout13`; split `holdout` hiện có 92 query, không phải 13.
Tương tự, không split nào là 25 query `batch1_round1_queries`: `dress25` cũng có
25 câu nhưng ID/nội dung khác. Trong khi đó gate bắt exact ID, query-set hash,
verified-ID map và GT hash của đúng hai manifest.

Kiểm chứng fresh trên mọi split evaluator hỗ trợ:

```text
tune    30  567dda74...  holdout13=False round1=False
holdout 92  97e64ec6...  holdout13=False round1=False
dress25 25  a5f151dc...  holdout13=False round1=False
gen10   20  ade08a05...  holdout13=False round1=False
gen2     4  1dddae11...  holdout13=False round1=False
```

Hệ quả còn mạnh hơn ở holdout: dù operator human-verify đủ 13 nhãn trong
manifest, `run_evaluation --split holdout --promotion` vẫn đòi toàn bộ 92 GT của
split verified trước khi chạy. Vì vậy không có đường CLI/provenance chính thức
để tạo ba score artefact mà promotion gate có thể nhận; chỉ còn cách handcraft
hoặc post-process JSON, trái mục tiêu pipeline tự động và provenance fail-closed.

Cần cho evaluator nhận frozen manifest (lọc exact ID sau khi kiểm query content
hash, GT verified/hash), hoặc thêm hai split chính thức được dựng từ manifest;
sau đó có integration test đi từ evaluator `scores.json` thật tới
`assess_promotion(...).eligible=True`.

### [P1] Receipt chấp nhận ZIP có answers khác hoàn toàn trace/evidence đã gate

- File: `backend/export/release_rehearsal.py:525-544`
- File: `backend/export/release_rehearsal.py:547-565`
- File: `backend/export/release_rehearsal.py:589-658`
- File: `run.py:643-674`

`create_release_package()` chỉ so `submissions` với query manifest theo
`query_id` và `task_type`. `assess_release_batch()` kiểm success, hypothesis và
canonical pin trên `trace.answers`, nhưng không so nội dung `submissions` sắp
được đưa vào writer với trace. Trong đường CLI, trace đến từ `trace.jsonl` còn
submission đến từ `checkpoint.jsonl`; sửa/corrupt checkpoint sang một
video/frame/answer khác nhưng vẫn giữ `query_hash` + fingerprint sẽ qua gate.
Receipt sau đó băm cả trace sạch và ZIP đã đổi, tạo vẻ như hai artefact có quan
hệ provenance trong khi thực tế không có.

Tái lập read-only bằng fixture release hiện có: giữ trace Q&A canonical
`L01_V001, frame 10, đỏ`, nhưng truyền submission KIS/QA đã đổi sang video thật
`L21_V001`, frame hợp lệ `1`/`2` và QA answer `sai`, vẫn cùng IDs/task. Bộ
submission đổi này được chạy qua `validate_all(..., expect_answers=1)` thật và
không có issue; writer hậu kiểm thành công. Kết quả:

```text
VALIDATOR_ISSUES 0
MISMATCH_ACCEPTED True
```

Tức receipt thật đã được tạo cho ZIP khác trace. Cần dựng submission trực tiếp
từ latest trace đã băm, hoặc canonical-compare mọi row với `trace.answers` trước
writer. Với Q&A, chỉ cho phép đúng phép biến đổi deterministic của
`apply_qa_submission_policy()` rồi so lại toàn bộ video/frame/keyframe/answer.

### [P1] Hypothesis `visual_count` hợp lệ không thể qua release evidence-cache gate

- File: `backend/tasks/qa.py:784-809`
- File: `backend/tasks/qa.py:1381-1405`
- File: `backend/tasks/qa.py:1217-1219`
- File: `backend/export/release_rehearsal.py:361-377`
- File: `run.py:481-538`

Nhánh detector count trả answer trực tiếp và chỉ gọi `_capture_inference_output()`;
nó không đi qua `_qa_cached_outputs()`, nên không tạo file trong
`QA_HYPOTHESIS_CACHE_DIR`. Capture inference lại chỉ được ghi khi
`QA_EVIDENCE_LOG_PATH` đã bật; evaluator bật biến này nhưng production `run.py`
không bật và release receipt cũng không nhận capture đó. Dù vậy release gate bắt
mọi hypothesis, không phân biệt provenance `detector`, phải có cache entry với
`evidence_digest + runtime + query_sha256 + full_query_sha256`.

Tái lập với một `Evidence(object_count=3, best_frame_idx=10,
evidence_hash=<sha256>)`:

```text
DETECTOR_RESULT ('3', 10, 1.0)
CACHE_JSON_COUNT 0
```

Do đó một answer mode được Task 4 yêu cầu có thể solve thành công nhưng Task 5
luôn chặn release nếu detector thực sự trả count. Cần persist detector result
vào cache identity/replay contract tương đương, hoặc để release xác minh một
evidence-capture snapshot đầy đủ cho provenance detector. Nếu dùng capture, production
release phải bật, validate và đưa chính snapshot đó vào receipt.

### [P2] Writer lỗi/hậu kiểm lỗi vẫn để lại `submission.zip` không dùng được

- File: `backend/export/release_rehearsal.py:589-603`
- File: `backend/export/exporter.py:559-565`
- File: `tests/test_release_rehearsal.py:262-288`

Writer hiện ghi trực tiếp vào tên cuối `submission.zip`. Khi writer trả issues,
release chỉ không tạo receipt rồi raise; không xóa/cách ly ZIP. Nếu exception xảy
ra giữa lúc `ZipFile(..., "w")`, file truncated cùng tên cũng nằm lại. Test hiện
chỉ assert không có receipt và bỏ qua file ZIP còn sót.

Tái lập với writer ghi `b"not usable"` rồi trả `zip_corrupt`:

```text
BLOCKED ZIP vừa ghi không qua validator; không tạo receipt
ZIP_LEFT_BEHIND True
RECEIPT_EXISTS False
```

Điều này lệch trực tiếp acceptance “validator lỗi thì không sinh ZIP một phần”
và dễ làm operator chọn nhầm đúng tên file nộp. Cần ghi ZIP vào path staging duy
nhất, validate staging, rồi atomic replace tên cuối; mọi exception/issues phải
dọn staging và không được đè một ZIP tốt có sẵn.

### [P2] Scorer hash không bao phủ dependency định nghĩa semantic matching

- File: `dev_set/tools/scoring.py:2`
- File: `dev_set/tools/run_evaluation.py:85-91`
- File: `dev_set/tools/run_evaluation.py:658-662`
- File: `backend/export/release_rehearsal.py:114-135`

`rscore_qa()` import `answer_matches()`/`exact_answer_matches()` từ
`backend/common/answer_match.py`, nhưng `scorer_source_sha256` chỉ là hash của
`dev_set/tools/scoring.py`. `release_context_reasons()` cũng chỉ băm lại đúng
file đó. Sửa thuật toán semantic/exact trong dependency sẽ không đổi scorer
hash; baseline/current có thể bị so bằng hai định nghĩa điểm khác nhau, và audit
cũ vẫn mở khóa release nếu query runtime fingerprint không đổi. Runner critical
source list hiện cũng không chứa `answer_match.py`.

Cần dùng một scorer-contract digest canonical bao phủ ít nhất `scoring.py`,
`backend/common/answer_match.py` và config policy liên quan, rồi lưu/so digest đó
ở evaluator, promotion gate và release.

## Minor / deferred

### [P3] `--only` ID lạ không đóng `Log` tường minh

- File: `run.py:481-490`

Finding deferred Task 2 là có thật: `Log` mở file ở dòng 481, nhánh ID lạ ghi
log rồi `return 2` mà không gọi `log.dong_lai()`. Dòng vừa ghi đã `flush()`, và
CLI process/CPython hiện sẽ thu hồi handle khi frame kết thúc, nên đây không phải
data-loss hay blocker merge độc lập. Vẫn nên sửa bằng `try/finally` quản lý Log
(không chỉ thêm một close riêng) để test gọi `main()` nhiều lần và interpreter
khác không giữ handle. Với các P1/P2 ở trên, branch chưa nên merge dù minor này
có deferred tiếp hay không.

## Những phần đã kiểm và không có finding material mới

- `run.py` và evaluator đều dispatch qua `solve_query()`; KIS multi-anchor giữ
  fallback single, max 3 anchor, token guard, relation/color/count fidelity,
  outer RRF k=7, chronology fail-safe và deterministic tie-break như review Task 3.
- `QueryRun.to_trace_dict()` xử lý numpy/parquet/container/path/time và non-finite
  JSON; production/evaluator đều ghi trace từ cùng QueryRun. Không thấy secret env
  được serialize.
- Q&A hypothesis pin qua `frame_map`, loại sentinel, giữ candidate-specific
  canonical trước alternatives/tail, cache full-query/runtime và single-flight.
  Các finding ở trên nằm tại integration với release, không phủ nhận các guard này.
- Promotion gate tự thân khóa exact frozen IDs/content, verified GT map/hash,
  runtime/scorer fields, zero crash, thresholds và regression diff. Blocker P1
  đầu tiên là thiếu producer artefact tương thích, không phải gate đã nới lỏng.
- Commit range không sửa `backend/llm/adapter.py`. Worktree hiện có bản sửa
  unstaged ở file đó và `README.md` cùng artefact khác của người dùng; tất cả nằm
  ngoài `b8090cd..9b107cd` và không bị review này chỉnh.
- CLI `run.py` và checkpoint schema cũ vẫn giữ các option/field cốt lõi; checkpoint
  legacy thiếu runtime fingerprint bị invalidate có chủ đích như plan.

## Verification fresh

```text
.\.venv\Scripts\python.exe -m pytest -q --basetemp .pytest-final-review
806 passed, 1 skipped, 2 warnings in 58.72s

git diff --check b8090cd..9b107cd
exit 0, không có output

git diff --name-only b8090cd..9b107cd -- backend/llm/adapter.py
không có output
```

Hai warning full suite là deprecation từ Starlette/httpx và `google.genai`,
không phải failure của branch. Thư mục pytest tạm do review tạo đã được xóa sau
verification.

---

# Re-review integration fix — `9b107cd..c443903`

## Verdict

**APPROVED.** Không còn finding P0–P2 trực tiếp sau khi re-review commit
`c443903eab3e19604250cf31d9390ba20b37bac5` và đối chiếu lại toàn nhánh
`b8090cd85133433cbaa5a37d542abea48c778f5c..c443903eab3e19604250cf31d9390ba20b37bac5`.
Sáu finding của vòng trước đều đã được xử lý đúng contract và fail-closed.

## Disposition sáu finding

1. **Frozen evaluator — RESOLVED.** `dev_set/tools/run_evaluation.py:175-272`
   nạp đúng manifest chính thức, kiểm exact query-set digest, query/task content,
   GT hash và audit metadata. CLI mới ở `dev_set/tools/run_evaluation.py:351-387`
   giữ nguyên đường `--split` legacy; score artefact ở
   `dev_set/tools/run_evaluation.py:802-823` chứa đủ frozen/runtime/scorer/GT
   provenance mà promotion gate nhận. Integration test
   `dev_set/tests/test_frozen_evaluator_integration.py:80` chạy ba artefact qua
   evaluator thật (chỉ mock service/solver) rồi đạt `assess_promotion() == ELIGIBLE`.

2. **Submission ↔ latest trace/Q&A policy — RESOLVED.** Canonical identity ở
   `backend/export/release_rehearsal.py:476-538` so toàn bộ ordered rows gồm
   video, frames, answer và keyframe; QA được transform bằng đúng policy
   deterministic trước khi so. Gate gọi phép so này trước writer tại
   `backend/export/release_rehearsal.py:633-640`. Reproduction đổi checkpoint
   nhưng giữ query ID/task nay bị `submission_trace_mismatch`, writer không được
   gọi (`tests/test_release_rehearsal.py:300`).

3. **Detector `visual_count` cache — RESOLVED.** Nhánh detector tại
   `backend/tasks/qa.py:1381-1444` đi qua cùng primitive cache, identity chứa
   question hash, full-query hash, evidence digest, runtime fingerprint, config,
   cache kind và provenance; output detector được ghi/replay mà không gọi provider.
   Manifest release mang provenance và gate vẫn bind query/full-query/evidence/runtime.
   Reproduction tại `tests/test_qa_hypotheses.py:646` xác nhận record detector và
   các identity này khớp hypothesis trace.

4. **ZIP fail-closed/rollback — RESOLVED.** Config, ZIP và receipt đều được ghi
   vào staging duy nhất (`backend/export/release_rehearsal.py:662-752`); chỉ sau
   hậu kiểm mới backup/replace và mọi exception khôi phục artefact tốt cũ
   (`backend/export/release_rehearsal.py:754-786`). Focused tests xác nhận writer
   trả issue không để ZIP hỏng/receipt và lỗi replace giữ nguyên ZIP, receipt,
   config tốt cũ (`tests/test_release_rehearsal.py:266`,
   `tests/test_release_rehearsal.py:373`).

5. **Scorer contract digest — RESOLVED.** Digest canonical tại
   `dev_set/tools/scorer_contract.py:10-27` bao phủ `scoring.py`,
   `answer_match.py` và `qa_evaluation.py`; evaluator và release cùng gọi helper
   này, promotion gate bắt ba artefact cùng digest. Runner runtime fingerprint
   cũng thêm `answer_match.py` tại `backend/tasks/runner.py:218-248`. Mutation
   test tại `dev_set/tests/test_scorer_contract.py:8` chứng minh dependency đổi
   thì digest đổi.

6. **`--only` ID lạ đóng Log — RESOLVED.** `run.py:489-491` đóng file trước
   exit 2; `tests/test_run.py:392` kiểm trực tiếp handle đã `closed` khi gọi
   `main()` lặp trong cùng process. Minor deferred của vòng trước không còn cần
   giữ trước merge.

## Ghi chú không-blocking

- Manifest GT thật trong repo vẫn mang trạng thái chưa verified nên promotion
  thực tế tiếp tục `BLOCKED` trước DB/retrieval. Đây là fail-closed đúng thiết kế,
  không phải regression của fix.
- Transaction bảo đảm rollback đối với exception được bắt trong process; không
  tuyên bố atomic đa-file trước power loss. ZIP tên cuối chỉ xuất hiện sau khi
  staging đã qua validator, đáp ứng acceptance trực tiếp “không ZIP partial”.
- Dirty worktree của người dùng (`README.md`, `backend/llm/adapter.py` và các
  artefact ngoài commit range) được giữ nguyên. Commit range không sửa
  `backend/llm/adapter.py`; CLI/checkpoint legacy vẫn tương thích.

## Verification fresh

```text
.\.venv\Scripts\python.exe -m pytest dev_set/tests/test_frozen_evaluator_integration.py dev_set/tests/test_scorer_contract.py dev_set/tests/test_promotion_gate.py dev_set/tests/test_run_evaluation_runtime.py tests/test_release_rehearsal.py tests/test_qa_hypotheses.py tests/test_run.py -q --basetemp .pytest-final-rereview
129 passed in 7.07s

git diff --check 9b107cd..c443903
exit 0, không có output

git diff --check b8090cd..c443903
exit 0, không có output

git diff --name-only b8090cd..c443903 -- backend/llm/adapter.py
không có output
```

Không lặp full suite ở vòng re-review theo chỉ dẫn controller; report fix đã ghi
full suite `813 passed, 1 skipped`. Thư mục pytest tạm của vòng này đã được xóa.
