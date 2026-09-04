# Gói context cho audit — HCMAIC 2026 / batch1-accuracy-uplift

Ngày dựng: **27/08/2026**. Repo: `C:\dev\aic2026`.
Mọi số trong file này được đo lại tại thời điểm dựng gói, không chép từ báo cáo cũ.
Chỗ nào chưa đo được thì ghi rõ **"chưa đo"**, không suy đoán.

---

## ⚠️ Bốn điều cần đọc trước mọi thứ khác

**1. `0.82` KHÔNG phải điểm đã đo. Nó là NGƯỠNG trong config.**

```python
# data/config/release_gate.py:33-35
HOLDOUT_OVERALL_MIN = 0.82
HOLDOUT_KIS_MIN     = 0.82
HOLDOUT_QA_MIN      = 0.75
```

Không tồn tại bất kỳ artefact nào chứa điểm đo được trên `batch1_holdout13`.
Câu hỏi "độ tin cậy của 0.82" có câu trả lời dứt khoát: **không có gì để tin cậy
cả — chưa ai đo.**

**2. ĐÃ CÓ số đo — và số đó cho thấy Task 3 chưa bao giờ chạy.**

Chiều 27/08 người vận hành chạy `--split dress25` ba lần. **Đọc
`10_eval_20260827_results.md` — nó thay thế §N/§O của tài liệu này.**

Tóm tắt: overall `0.3520` (baseline 21/08) → `0.3040` hoặc `0.3627` tùy chọn
run nào. **Nhưng 19/19 câu KIS đều `fallback_reason: planner_error`** — multi-anchor
của Task 3 chưa từng thực thi một lần nào, vì `ANCHOR_SCHEMA` dùng keyword
`maxItems` mà API Anthropic từ chối bằng lỗi 400, và lỗi đó bị `except Exception`
nuốt im lặng. Đã tái lập trực tiếp và xác minh cách sửa.

**3. Toàn bộ verification hiện có là unit test, không phải hành vi hệ thống.**

`813 passed, 1 skipped` (`04_pytest_full.txt`). Tất cả test đều mock service.
Đây là bằng chứng về contract, không phải bằng chứng về accuracy — và §4 của
`10_eval_20260827_results.md` chứng minh điều đó bằng một trường hợp cụ thể:
39 test multi-anchor xanh trong khi tính năng chết hoàn toàn ở production.

**4. Holdout 13 câu ĐÃ bị nhìn và ĐÃ được dùng để tune — trước PLAN.**

Chi tiết ở mục M. Số đo cuối cùng thật sự có trên đúng 13 câu đó:
**overall 0.2154 · KIS 0.2800 · QA 0.0000** (20/08, GT legacy chưa verified).

---

## A. Trạng thái repository

Xem `01_git_state.txt`, `02_repo_tree.txt`, `03_implementation_b8090cd..HEAD.diff`,
`03b_implementation_diffstat.txt`.

| Mục | Giá trị |
|---|---|
| Branch hiện tại | `codex/batch1-accuracy-repair` |
| HEAD | `b419f6e8114da5e3a045cb85e19a8b9dda0b6788` |
| `main` | trỏ **cùng commit** với HEAD (đã fast-forward) |
| Baseline trước PLAN | `b8090cd85133433cbaa5a37d542abea48c778f5c` |
| `git status --short` | `?? dev_set/ground_truth/sotuyen1_p1_draft_gt.jsonl` (1 file untracked duy nhất) |

Lưu ý về tên nhánh: các review nội bộ nhắc `codex/batch1-accuracy-uplift`. Nhánh
đó đã được đổi tên/merge; nhánh làm việc hiện tại là `...-repair`. Nội dung commit
range không đổi.

**Commit đã implement PLAN** (baseline → HEAD, theo thứ tự):

```
b8090cd  (baseline, TRƯỚC PLAN)
0ea6ce7  feat: add verified evaluation foundation          ← Task 1
f5bb02b  docs: restore batch1 uplift acceptance spec       ← Task 1 fix
3af0dd4  docs: mark round1 scores unreproduced             ← Task 1 fix
0a9d3b9  refactor: unify query execution and traces        ← Task 2
8042414  fix: harden runner fingerprints and traces        ← Task 2 fix
edd6343  feat: add KIS multi-anchor retrieval              ← Task 3
3f50bfe  fix: fail closed on invalid KIS anchors           ← Task 3 fix
f9dcacb  fix: preserve anchor constraint relations         ← Task 3 fix
41609d0  fix: normalize anchor chronology safely           ← Task 3 fix
7dcd8db  fix: derive temporal order from anchor spans      ← Task 3 fix
4d28d93  feat: add evidence-specific QA hypotheses         ← Task 4
0853535  fix: harden QA evidence and cache identity        ← Task 4 fix
00a6c08  feat: add promotion and release rehearsal gates   ← Task 5
9b107cd  fix: bind release gates to verified provenance    ← Task 5 fix
c443903  fix: close release provenance gaps                ← final integration fix
b419f6e  docs: update architecture/testing, fix LLM adapter + runner fallback  ← ⚠ NGƯỜI DÙNG, sau PLAN
```

Diff `b8090cd..HEAD`: **40 file, +7.828 / −337 dòng.**

---

## B. PLAN và specification

| File trong gói | Nguồn trong repo |
|---|---|
| `docs/PLAN.md` | `docs/plans/2026-08-24-batch1-accuracy-uplift.md` |
| `docs/product-spec.md` | `docs/product-spec.md` — **đã tồn tại**, là sản phẩm của Task 1 |
| `docs/ARCHITECTURE.md` | `ARCHITECTURE.md` |
| `docs/testing.md`, `docs/deployment.md` | như tên |
| `docs/contest.md` | thể thức thi (nguồn của mọi ràng buộc format/chấm điểm) |
| `audit_reports/02_progress-ledger.md` | SDD ledger — implementation notes + decision log |

`product-spec.md` là nguồn acceptance chính đúng như PLAN yêu cầu, và nó **tự
nói rằng 6,8/13 và 8,6/13 là external/unreproduced** — không được dùng làm
acceptance evidence.

---

## C. Audit Report

Thư mục `audit_reports/`. Cấu trúc đầy đủ theo format bạn cần
(finding / severity / file:line / evidence tái lập / recommendation):

- `00_final-review.md` — **báo cáo chính**. Vòng 1: CHANGES REQUESTED, 3×P1 + 2×P2 + 1×P3.
  Vòng 2 (re-review `9b107cd..c443903`): APPROVED, sáu finding đều RESOLVED, có
  file:line của fix và test tương ứng.
- `01_integration-fix-report.md` — RED tái lập trước khi sửa + thay đổi + verification.
- `02_progress-ledger.md` — ledger từng task, các "Ruling" (quyết định kiến trúc + hệ quả nếu sai).
- `task-N-{brief,report,review}.md` — audit từng task, N=1..5. Task 3/4/5 có file
  `-review.md` riêng với finding chi tiết từng vòng fix.

Số vòng fix thực tế: Task 1: 2 vòng · Task 2: 1 vòng (+1 minor deferred) ·
Task 3: 4 vòng · Task 4: 1 vòng (7 finding) · Task 5: 1 vòng (7 finding) ·
Final integration: 1 vòng (6 finding).

---

## D. Unified runner — data flow thực tế

**File:** `backend/tasks/runner.py` (514 dòng, mới hoàn toàn).

```
run.py:396  giai_mot_query()  ──┐
                                ├──> backend.tasks.runner.solve_query(query, total=100)
dev_set/tools/run_evaluation.py:306 ──┘                    │
                                                            ▼
                                        ┌───────────────────┼───────────────────┐
                                        ▼                   ▼                   ▼
                                  task_type=KIS       task_type=QA        task_type=TRAKE
                                        │                   │                   │
                            multi_anchor.plan_query()  qa.qa_pipeline()   trake.trake_search()
                                        │                   │                   │
                       strategy=single ─┴─ strategy=multi   │              to_answers()
                       search()          search_multi()     │              pad_answers()
                                        │                   │                   │
                                  slot.allocate()   qa_portfolio.            │
                                        │           allocate_qa_portfolio()  │
                                        └───────────────────┼───────────────┘
                                                            ▼
                                                        QueryRun
```

**Evaluator có đi qua đúng `solve_query()` không? — CÓ.**
`dev_set/tools/run_evaluation.py:303-308` là wrapper mỏng duy nhất, truyền thêm
`runtime_fingerprint` đã tính sẵn. Không còn path riêng.

Bằng chứng đây là refactor thật chứ không phải thêm lớp: diff `run.py` cho thấy
toàn bộ 60 dòng dispatch cũ bị xoá, thay bằng 3 dòng wrapper
(`03_implementation...diff`, hunk `run.py:@@ -382,70 +392,9 @@`). Comment cũ trong
run.py tự thú nhận đây từng là "BẢN SAO THỨ BA" của dispatch.

**⚠️ Còn một path thứ ba KHÔNG được gộp:** `run_minimal.py` (241 dòng, không nằm
trong diff). Đây là kịch bản dự phòng khi hệ thống treo giữa buổi thi — có
dispatch riêng, cố ý giữ độc lập. Nó **không** dùng `solve_query()`, nên mọi fix
trong runner không áp dụng cho nó.

**`QueryRun`** (`runner.py:127-196`) — field: `query_id, task_type, answers,
query_plan, search_rows, source_ranks, source_contributions, qa_hypotheses,
timings, failure_class, status, runtime_fingerprint, task_metadata, answer_text,
qa_trace, n_trake, error, retryable`.

Invariant được ép ở `__post_init__` (`runner.py:155-163`):
`status=failed` ⇒ bắt buộc có `failure_class` ∈ 6 nhãn spec, và
**`answers` phải rỗng** — không cho checkpoint partial/fake answers.

---

## E. KIS — thứ tự fusion (câu hỏi kiến trúc quan trọng nhất của bạn)

**Trả lời: five-source weighted RRF chạy TRƯỚC (bên trong), multi-anchor RRF chạy SAU (bên ngoài).**

```
plan_query(query_vi)                          # multi_anchor.py:286
   │  llm() tách ≤3 anchor → validate fidelity → translate → count_clip_tokens
   ▼
QueryPlan(strategy="multi", anchors=(a1,a2,a3), ordered=bool)
   │
   ├── search(a1)  ─┐
   ├── search(a2)   ├─ MỖI LẦN GỌI: 5 nhánh song song (vector/metadata/objects/ocr/asr)
   └── search(a3)  ─┘   → RRF_K=7 × BRANCH_WEIGHTS → group-by-shot → top-100
   │                    (search.py:415  contrib = W[branch] * 1/(7 + rank))
   ▼
search_multi(): OUTER RRF trên shot        # multi_anchor.py:393-403
   score = Σ_anchor 1/(RRF_K + rank_anchor),  RRF_K=7
   nếu video khớp thứ tự thời gian: score *= TEMPORAL_BONUS (1.25, soft, không hard-filter)
   ▼
top_k rows → ShotHit → slot.allocate()
```

Hai `RRF_K` là **hai hằng số khác nhau ở hai file config khác nhau**, tình cờ
cùng bằng 7: `data/config/search_weights.py:36` (inner) và
`data/config/multi_anchor.py:6` (outer). Đổi một cái không đổi cái kia.

**Invariant — đã verify bằng đọc code:**

| Invariant | Nơi ép | Cơ chế |
|---|---|---|
| `anchors <= 3` | `multi_anchor.py:270` + `ANCHOR_SCHEMA.maxItems` | quá 3 → `_validated_anchors` trả None → fallback |
| `CLIP tokens <= 60` | `multi_anchor.py:314-316` | đếm **thật** bằng `count_clip_tokens(anchor_en)`, vượt → fallback `token_limit` |
| không invent color | `_preserves_color_context` (`:176-203`) | màu phải xuất hiện cạnh đúng head noun trong query gốc |
| không invent number/quantity | `_preserves_quantifier_context` (`:143-173`) | quantifier + classifier + head noun phải là chuỗi token liên tiếp có trong query gốc |
| token không có trong query gốc | `_is_faithful` (`:242-258`) | `set(anchor_tokens) ⊆ set(original_tokens)` |
| invalid planner → single-anchor | `plan_query` (`:288-319`) | 5 lý do fallback: `planner_error`, `invalid_anchors`, `translation_error`, `token_limit`, + `not _needs_multiple` |

Fail-closed: **bất kỳ** anchor nào không trung thành → **cả plan** bị bỏ, quay về
single-anchor. Không có chuyện giữ lại 2/3 anchor hợp lệ.

**⚠️ Quan sát để bạn xét (không phải claim bug):** `search_multi()` ghi đè
`ranks`/`contrib` của row đại diện bằng **anchor ranks** (`multi_anchor.py:414-415`).
Hệ quả: với query multi-anchor, `QueryRun.source_ranks` chứa
`{anchor_1: 3, anchor_2: 17}` chứ **không** chứa `{vector: 3, ocr: 5, metadata: 476}`.
Thứ hạng từng nhánh retrieval biến mất khỏi trace. Code có comment thừa nhận
việc này là cố ý, nhưng nó làm yếu bất biến số 7 của `CLAUDE.md`
("Log thứ hạng từng nhánh trong RRF") đúng ở nhóm query khó nhất, và làm việc
phân loại `retrieval_miss` mất một chiều dữ liệu.

**File cần đọc:** `backend/retrieval/multi_anchor.py` (426, mới),
`backend/retrieval/search.py` (488, **không đổi**),
`backend/retrieval/query_understanding.py` (255, **không đổi** — chứa `translate()`
và `count_clip_tokens()`), `backend/slot/allocator.py` (683, **không đổi**),
`data/config/multi_anchor.py`, `data/config/search_weights.py`.

`SLOT_BUDGET = [(1,2), (2,2), (94,1)]` (`data/config/slot_budget.py:58`)
→ 2 + 4 + 94 = 100 dòng. Không đổi trong PLAN này.

---

## F. Q&A — candidate-specific hay không?

**Trả lời: ĐÚNG là candidate-specific.** Sơ đồ thứ hai trong câu hỏi của bạn
("one answer → nhiều candidate") đã bị thay.

```
qa_pipeline()                                    # qa.py:1867 → _qa_pipeline_impl:1533
   │
   ├─ parse_question()  → QuestionParts(event_vi, question_vi, answer_mode, planner_fallback)
   │                      answer_mode ∈ {visual_count, visual_read, ocr, asr, metadata, visual_attribute}
   │                      planner lỗi → fallback rule cũ, cờ planner_fallback=True
   │
   ├─ search(event_vi) → top-K shot candidate
   │
   └─ VỚI MỖI candidate:                          # qa.py:1666-1725, 1788-1806
         collect_evidence(shot)  → Evidence(ocr, asr, metadata, object_count, frames, evidence_hash)
         _try_shot()             → answer riêng cho candidate đó
         build_qa_hypothesis()   → QAHypothesis                # qa.py:463
                                     · pin keyframe qua _keyframe_id_for_frame()
                                     · assert load_frame_map()[keyframe_id] == evidence_frame_idx
                                       → sai thì raise QANoValidHypothesisError, KHÔNG im lặng
                                     · sentinel → trả None, không tạo object được
         dedupe theo (video_id, evidence_frame_idx, normalize(answer))
   │
   ▼
allocate_qa_portfolio(hypotheses, hits, total=100)   # qa_portfolio.py:64
   Vòng 1: canonical của MỌI hypothesis  (bắt buộc, trước mọi alternative)
   Vòng 2: round-robin 1 frame thay thế/hypothesis  (QA_HYPOTHESIS_ALTERNATIVES_PER_HYPOTHESIS=1)
   Vòng 3 (đuôi): candidate retrieval chưa dùng + answer của hypothesis mạnh nhất
```

`QAHypothesis` (`qa.py:184-235`) mang: `answer_text, video_id, shot_id,
keyframe_id, evidence_frame_idx, confidence, evidence_hash, provenance,
evidence_type, answer_mode`.

**Sentinel filtering:** 3 lớp — `is_valid_qa_answer()` (`qa.py:444`) chặn ở
`QAHypothesis.__post_init__`; `build_qa_hypothesis` trả None; `allocate_qa_portfolio`
raise nếu lọt (`qa_portfolio.py:86-87`). Danh sách sentinel + prefix continuation
ở `data/config/qa_hypotheses.py`.

**Không partial:** `allocate_qa_portfolio` raise `RuntimeError` nếu không đủ
`total` dòng (`qa_portfolio.py:136-139`), nếu không có hypothesis nào (`:80`),
hoặc nếu `total` < số canonical (`:81-85` — từ chối âm thầm bỏ evidence).

**Ranking hypothesis** (`qa_portfolio.py:16-31`): confidence giảm dần, tie-break
bằng thứ tự input (giữ provenance retrieval), rồi `shot_id`. Deterministic.

---

## G. TRAKE

**`backend/tasks/trake.py` (992 dòng) KHÔNG nằm trong diff — không sửa một dòng nào.**
`data/config/search_weights.py` (các hằng `TRAKE_*`) và `data/config/slot_budget.py`
(`TRAKE_ALT_BUDGET`, `TRAKE_BREADTH_ROWS`...) cũng không đổi.

Thứ **có** đổi: TRAKE giờ đi qua `solve_query()` (`runner.py:342-387`) thay vì
dispatch riêng trong `run.py`. Chuỗi gọi giữ nguyên: `parse_events` →
`trake_search(events, top_videos=total)` → `to_answers()` → `pad_answers()` nếu
thiếu → cắt `[:total]`. Kiểm tra `n_events` cũng giữ nguyên, chỉ đổi
`RuntimeError` → `ValueError` (nên failure_class thành `format` thay vì `trake_order`).

Multi-anchor **không** áp dụng cho TRAKE — nhánh TRAKE return trước khi tới
`plan_query()`. Đúng như PLAN yêu cầu.

Temporal DP / alternative slots: nằm trong `_align_events_in_video`,
`_repair_strictly_increasing`, `_alternative_frame_sets` — tất cả không đổi.

---

## H. Cache, checkpoint, resume, fingerprint

### Cache key Q&A — đúng dạng PLAN yêu cầu, và nhiều hơn

`backend/tasks/qa.py:1068-1101`:

```python
identity = {
  "query_sha256":       sha256(question_vi),      # phần câu hỏi
  "full_query_sha256":  sha256(query gốc đầy đủ), # chống trộn query khác cùng câu hỏi
  "llm":                {"backend": ..., "model": ...},   # KHÔNG có api key
  "prompt_version":     QA_INFERENCE_PROMPT_VERSION,      # "qa-evidence-v2"
  "config_snapshot":    {qa_inference, qa_hypotheses, n, effort, max_tokens, usage_tag},
  "evidence_digest":    ev.evidence_hash,
  "runtime_fingerprint": <fingerprint>,
}
cache_key = sha256(json.dumps(identity, sort_keys=True, separators=(",",":")))
```

Planner có identity riêng (`:1053-1065`, `cache_kind="question_planner"`, không có
evidence). Ghi bằng temp-file + `replace()` (atomic), có single-flight lock per key
(`:142-170`) để cùng key chỉ gọi provider một lần.

**Cache mismatch = LỖI, không phải miss:** `_qa_cache_get` (`:1103-1123`) raise
`QAEvidenceCaptureError` khi schema/identity không khớp — cố ý fail loud thay vì
âm thầm gọi lại provider.

### Runtime fingerprint

`backend/tasks/runner.py:218-263`. Nội dung:
- `llm.backend` + `llm.model` (chỉ đọc biến của backend đang chọn)
- `qa_inference_mode`
- sha256 của **mọi** `data/config/*.py`
- sha256 của 8 critical source: `multi_anchor.py`, `search.py`, `answer_match.py`,
  `allocator.py`, `qa.py`, `qa_portfolio.py`, `trake.py`, `runner.py`

### Resume khi fingerprint khác — **INVALIDATE, không cảnh báo, không silently continue**

`run.py:506`: checkpoint record bị bỏ nếu `rec.get("runtime_fingerprint") != current`.
Câu đó chạy lại từ đầu. Checkpoint legacy (không có field này) → invalidate toàn bộ,
đúng như thiết kế.

Checkpoint legacy có key: `answer_text, answers, at, n_answers, n_real, n_trake,
qa_trace, query_hash, query_id, seconds, task_type` — thiếu `runtime_fingerprint`
(mẫu: `submissions/dienlap_20260821/checkpoint.jsonl`).

### Scorer contract digest

`dev_set/tools/scorer_contract.py` (27 dòng) — digest canonical phủ `scoring.py` +
`backend/common/answer_match.py` + `data/config/qa_evaluation.py`. Được evaluator,
promotion gate và release cùng dùng. Có mutation test
(`dev_set/tests/test_scorer_contract.py`).

---

## I. LLM/VLM path

**File:** `backend/llm/adapter.py` (566 dòng). Entrypoint công khai duy nhất:
`llm(prompt, images=None, json_schema=None, n=1, ...)`.

**Provider selection: KHÔNG có fallback tự động.** Backend chọn bằng `LLM_BACKEND`
∈ `{api, gemini, local}`. Provider lỗi → retry trong cùng provider → raise.
Không có đường `provider A fail → provider B`.

| Backend | Client | Retry |
|---|---|---|
| `api` (Anthropic) | `Anthropic(max_retries=4, timeout=120.0)` (`:212`) | SDK tự retry 429/5xx, backoff mũ |
| `gemini` | `genai.Client(http_options=HttpOptions(timeout=120_000))` (`:297`) | **lớp retry tự viết** (`:387-402`): `ServerError` → backoff `2**n`; 429 → backoff dài `RATE_LIMIT_BACKOFF` (15s/30s/60s vì free-tier reset theo phút); 4xx khác → **raise ngay, không retry** |
| `local` (Ollama) | urllib, `timeout=300` (`:452`) | không |

Comment `:358-362` ghi rõ đã đọc source `google.genai._api_client.retry_args()`
v2.18.1 và xác nhận SDK **không** retry khi không truyền `retry_options` — nên
lớp retry đó là bắt buộc, không thừa.

**Structured output:** `json_schema` → parse JSON; JSON hỏng có retry riêng
(`:529-548`), tách khỏi retry mạng.

**Model mặc định:** `DEFAULT_API_MODEL = "claude-opus-5"`,
`DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"` (cố định, cố ý không dùng `-latest`),
`DEFAULT_LOCAL_MODEL = "qwen2.5:7b-instruct"`.

**Cấu hình đang chạy** (`.env`, đã redact):
```
ANTHROPIC_API_KEY=<REDACTED>
LLM_BACKEND=api
LLM_API_MODEL=claude-sonnet-5
GEMINI_API_KEY=<REDACTED>
```
Chú ý: `.env` đặt `claude-sonnet-5`, khác `DEFAULT_API_MODEL = claude-opus-5`.

---

## J. Configuration

Xem `09_architecture_constants.txt` (trích nguyên văn từ source).

| Tham số | Giá trị | File | PLAN yêu cầu | Khớp? |
|---|---|---|---|---|
| RRF k (inner, 5 nguồn) | `7` | `search_weights.py:36` | (không nhắc) | — |
| RRF k (outer, anchor) | `7` | `multi_anchor.py:6` | `k=7` | ✅ |
| anchor count | `MAX_ANCHORS=3` | `multi_anchor.py:4` | tối đa 3 | ✅ |
| CLIP token limit | `MAX_CLIP_TOKENS=60` | `multi_anchor.py:5` | tối đa 60 | ✅ |
| temporal bonus | `1.25` | `multi_anchor.py:7` | mặc định 1,25 soft | ✅ |
| per-anchor pool | `100` | `multi_anchor.py:8` | (không nhắc) | knob mới |
| ngưỡng query ngắn | `SHORT_QUERY_MAX_WORDS=18`, `COMPLEX_MARKER_MIN=1` | `multi_anchor.py:11-12` | "query ngắn dùng single" | knob mới |
| source weights | vector 1.0 · objects 0.7 · ocr 0.6 · asr 0.6 · metadata 0.4 | `search_weights.py:51` | (không đổi) | ✅ |
| `CANDIDATE_MULTIPLIER` | `5` | `search_weights.py:62` | — | — |
| `SLOT_BUDGET` | `[(1,2),(2,2),(94,1)]` = 100 | `slot_budget.py:58` | — | — |
| answer modes | 6 mode | `qa_hypotheses.py:9-16` | đúng 6 mode | ✅ |
| alternatives/hypothesis | `1` | `qa_hypotheses.py:26` | 1 vòng alternatives | ✅ |
| prompt versions | `qa-planner-v2`, `qa-evidence-v2` | `qa_hypotheses.py:19-20` | có versioning | ✅ |
| gate thresholds | `0.82 / 0.82 / 0.75` | `release_gate.py:33-35` | `>=0.82/0.82/0.75` | ✅ |
| QA inference mode | `legacy` (default) | `qa_inference.py:12` | giữ legacy tới khi replay xong | ✅ |
| timeout/retry LLM | 120s API/Gemini, 300s local; retry 4 | `adapter.py` | — | — |

**Hardcode còn sót?** Các knob chiến thuật đều ở `data/config/`. Hằng số vận hành
Q&A (`N_EVIDENCE_FRAMES=8`, `TOP_K_SHOTS=5`, `SELF_CONSISTENCY_N=3`,
`LOW_CONFIDENCE=0.5`, `MAX_SHOTS_TRIED`, `VIDEO_EXPAND_SHOTS=3`,
`MAX_VIDEOS_EXPANDED=3`, `OBJECT_COUNT_MIN_SCORE=0.5`) **vẫn nằm trong
`backend/tasks/qa.py:98-137`**, không ở config. Đây là code cũ trước PLAN, PLAN
không yêu cầu chuyển — nhưng nó ảnh hưởng ranking/runtime, nên bạn nên biết.

---

## K. Test suite

`04_pytest_full.txt`. Chạy lại 27/08 bằng `.venv/Scripts/python.exe -m pytest -q`:

```
813 passed, 1 skipped, 2 warnings in 125.06s
```

Hai warning là deprecation của Starlette/httpx và `google.genai` — không phải
failure của repo. `pytest.ini` giới hạn `testpaths = tests dev_set/tests`.

**Test mới trong implementation** (file thêm mới, tổng ~2.500 dòng):

| File | #test | Phủ |
|---|---|---|
| `tests/test_multi_anchor.py` | 39 | anchor count, token limit, color/number fidelity, fallback, RRF, temporal |
| `tests/test_qa_hypotheses.py` | 37 | answer mode, evidence pinning, sentinel, portfolio, detector cache |
| `tests/test_release_rehearsal.py` | 23 | zero-crash, ZIP transaction/rollback, submission↔trace |
| `dev_set/tests/test_promotion_gate.py` | 18 | GT verified, threshold, regression, frozen ID |
| `tests/test_task_runner.py` | 14 | parity, fingerprint, JSON-safe trace, failure class |
| `dev_set/tests/test_ground_truth_verification.py` | 5 | schema `verification_status`/provenance |
| `dev_set/tests/test_run_evaluation_runtime.py` | 5 | runtime fingerprint evaluator |
| `dev_set/tests/test_scorer_contract.py` | 1 | mutation test dependency digest |
| `dev_set/tests/test_frozen_evaluator_integration.py` | 1 | evaluator thật → `assess_promotion() == ELIGIBLE` |

**Đối chiếu danh sách test bạn yêu cầu:**

| Bạn cần | Có? | Ở đâu |
|---|---|---|
| anchor count | ✅ | `test_multi_anchor.py` |
| CLIP token limit | ✅ | `test_multi_anchor.py` |
| invented colors/numbers | ✅ | `test_multi_anchor.py` |
| planner fallback | ✅ | `test_multi_anchor.py` |
| multi-anchor RRF | ✅ | `test_multi_anchor.py` |
| temporal bonus | ✅ | `test_multi_anchor.py` |
| evidence pinning | ✅ | `test_qa_hypotheses.py` |
| sentinel filtering | ✅ | `test_qa_hypotheses.py` |
| cache key | ✅ | `test_qa_hypotheses.py` |
| fingerprint | ✅ | `test_task_runner.py`, `test_run_evaluation_runtime.py` |
| runner/evaluator parity | ✅ | `test_task_runner.py` |
| retryable API errors | ⚠️ **một phần** | `test_llm_adapter.py` chỉ 4 test; không có test cho backoff 429/503 của Gemini |
| deterministic replay | ⚠️ **một phần** | có test cache hit/identity; **không** có test chạy 2 lần cùng input → cùng output end-to-end |

---

## L. Evaluation datasets

### `batch1_round1_queries` (25 câu, regression set)

`manifests/batch1_round1_queries.json`. Nguồn:
`HEAD:data/queries/sotuyen1_p1.jsonl` @ `b8090cd`, blob `7c7726920406...`,
25 record. **Đã verify:** blob sha của b8090cd, HEAD và worktree đều bằng nhau
→ file query không bị sửa sau khi đóng băng.

Phân bố (đếm lại từ manifest): **20 KIS · 4 QA · 1 TRAKE**.
QA = `query-p1-3-qa`, `query-p1-9-qa`, `query-p1-15-qa`, `query-p1-17-qa`.
TRAKE = `query-p1-16-trake`. Xem `release_gate.py:REGRESSION_EXPECTED_QUERY_IDS`.

**GT:** `dev_set/ground_truth/sotuyen1_p1_draft_gt.jsonl` — **untracked, 25 dòng,
tất cả `status: "TODO"`, `video_id: null`, `frame_start/end: null`.** Đây là bản
nháp label tay đang làm dở. Không dùng được để chấm.

### `batch1_holdout13` (13 câu)

`manifests/batch1_holdout13.json`. 10 KIS (`KIS_001..010`) + 3 QA (`QA_011..013`).
Nguồn: `dev_set/queries/holdout_{kis,qa}.jsonl` + `holdout_gt.jsonl` legacy.

Mọi entry: `verification_status: "unknown"`, `verified_by: null`, `verified_at: null`.
Manifest tự ghi: *"không phải ground truth đã xác minh và không được dùng promotion"*.
Video-disjointness chỉ được khẳng định ở mức "13 video_id khác nhau trong
`holdout_gt.jsonl` hiện có" — provenance là legacy, chưa human-verified.

**Cách chọn:** 13 câu này là **tập con** của split `holdout` cũ (63 query có GT,
92 query có đề). Manifest được tạo **24/08/2026**, tức ngày bắt đầu PLAN.

### Trạng thái GT toàn bộ

```
dress25_gt.jsonl            n= 25   verification_status: <field absent> ×25
gen10_gt.jsonl              n= 20   <field absent> ×20
gen2_gt.jsonl               n=  4   <field absent> ×4
holdout_gt.jsonl            n= 63   <field absent> ×63
sotuyen1_p1_draft_gt.jsonl  n= 25   <field absent> ×25
synth_gt.jsonl              n=  6   <field absent> ×6
tune_gt.jsonl               n= 30   <field absent> ×30
```

**Không một file GT nào có field `verification_status`.** Schema mới đọc chúng
thành `unknown` → promotion fail-closed. Đây là hành vi đúng thiết kế, không phải bug.

### Scorer

`dev_set/tools/scoring.py` — `Final = mean(R@1, R@5, R@20, R@50, R@100)`, bảng
R-Score theo hạng đúng `docs/contest.md`. QA match dùng
`backend/common/answer_match.py`, policy `semantic` (mặc định) hoặc `exact`.

---

## M. Holdout contamination — **CASE 3, có bằng chứng**

Trả lời thẳng: **13 câu holdout ĐÃ bị xem kết quả VÀ đã có quyết định tune dựa
trên chúng — nhưng chuyện đó xảy ra TRƯỚC PLAN (20/08), không phải trong lúc
implement.**

### Bằng chứng (`08_holdout13_history.txt` + `manifests/holdout_log.md`)

Đúng 13 query của `batch1_holdout13` đã được chấm **3 lần**:

| Run | Ngày | Commit | overall | KIS | QA |
|---|---|---|---|---|---|
| `run_20260820_2108` | 20/08 21:08 | `c7f68ad` | 0.1385 | 0.1800 | 0.0000 |
| `run_20260820_2207` | 20/08 22:07 | `c7f68ad` | **0.2154** | **0.2800** | 0.0000 |
| `run_20260820_2312` | 20/08 23:12 | `0c4bf04` | 0.2154 | 0.2800 | 0.0000 |

`holdout_log.md` "Lần 2" ghi rõ mục đích của run 2207: **xác nhận đổi `RRF_K`
60→7**. Tức là: nhìn kết quả lần 1 → đổi hằng số → chạy lại trên cùng bộ → giữ
thay đổi vì điểm tăng. Đó chính xác là định nghĩa Case 3.

`RRF_K = 7` hiện vẫn là giá trị đang chạy, và multi-anchor cũng chọn `RRF_K = 7`.

"Lần 3" (run 2312) xác nhận thêm 2 fix Q&A (`MAX_SHOTS_TRIED` 3→5, và bug
`query_en` truyền nhầm) — nhưng run đó **hết tiền API giữa chừng**, 23/27 câu QA
thành `F0_CRASH`, nên số QA=0.0000 không đáng tin.

### Phân biệt cho rõ

| | Trạng thái |
|---|---|
| Split `holdout` (superset 63–92 câu) | **Case 3** — đã dùng để tune `RRF_K`, `MAX_SHOTS_TRIED` |
| Manifest `batch1_holdout13` (13 câu) | Đóng băng 24/08, tất cả nhãn `unknown`, **chưa từng được chấm sau khi đóng băng** |
| Trong cửa sổ implement (24–25/08) | **Case 1** — không ai chạy, không ai nhìn, không tune theo |

Nhưng: 13 câu đó **không sạch**, vì chúng thuộc bộ đã bị tune, và hằng số rút ra
từ lần tune đó (`RRF_K=7`) vẫn đang chạy. Nếu sau này có điểm trên
`batch1_holdout13`, điểm đó **không phải** ước lượng không thiên vị.

### Con số "before" gần nhất có thật cho 13 câu

**overall 0.2154 · KIS 0.2800 · QA 0.0000**, chấm bằng GT legacy chưa verified.
Mục tiêu gate là 0.82. Khoảng cách này lớn hơn nhiều so với những gì một lần
refactor + multi-anchor có thể hứa hẹn.

### Quota holdout

`holdout_log.md` khai chính sách tối đa 5 lần dùng; đã dùng 3, **còn 2**.

---

## N. Baseline TRƯỚC implementation

> ⚠️ **CẬP NHẬT 27/08 chiều:** đã có số "after" thật.
> Đọc `10_eval_20260827_results.md` trước, rồi mới đọc §N/§O bên dưới.

**Baseline duy nhất tái lập được từ artefact trong repo:**
`06_baseline_dress25_scores_20260821.json` = `dev_set/results/run_20260821_0021/`.

```
split   : dress25 (25 query: 19 KIS + 5 QA + 1 TRAKE)
commit  : 0c4bf04         ← trước b8090cd
KIS     : avg Final 0.4211  (n=19)
QA      : avg Final 0.1200  (n=5)
TRAKE   : avg Final 0.2000  (n=1)
failure : SUCCESS 12 · F_UNKNOWN 8 · F_QA_REASONING_FAILED 4 · F_QA_RETRIEVAL_FAILED 1
crashes : 0 F0_CRASH trong run này
```

Baseline cho **holdout 13**: xem mục M (0.2154 / 0.2800 / 0.0000, run `20260820_2207`).

**Về `6,8/13` và `8,6/13` trong PLAN:** hai số này **không tái lập được** từ repo.
Không có score artefact, config snapshot, trace hay runtime fingerprint đi kèm.
`docs/product-spec.md` cũng tự ghi chúng là external/unreproduced. Chúng là báo
cáo miệng của người vận hành về một phiên làm tay, không phải hành vi tự động.

`test suite` baseline: không có số của riêng `b8090cd` trong repo. Ledger ghi
`702 passed, 1 skipped` ở giữa Task 3 và `766` ở Task 4 — nhưng đó là các mốc
trung gian, không phải baseline `b8090cd`.

---

## O. Kết quả SAU implementation

> **ĐÃ ĐO — xem `10_eval_20260827_results.md` để có bảng đầy đủ, diff từng câu,
> nguyên nhân gốc và phân loại theo deadline.**

```
Current implementation (HEAD = b419f6e), split dress25, n=25

overall : 0.3627  (RUN 3)  ·  0.3040 (RUN 1)   vs baseline 0.3520
KIS     : 0.4000  (n=19)   R@1 0.0526          vs baseline 0.4211 / R@1 0.1053
Q&A     : 0.2000  (n=5)                        vs baseline 0.1200
TRAKE   : 0.4667  (n=1)                        vs baseline 0.2000
crashes : RUN 1 5/5 QA failed · RUN 3 1/5 QA failed (DRESS_QA_04)
tests   : 813 passed, 1 skipped
runtime : KIS median 0,9s · QA 196–476s/câu  ← vượt ngân sách 30s của CLAUDE.md §2
```

Ba cảnh báo bắt buộc khi đọc bảng này:
1. **Multi-anchor chưa từng chạy** (19/19 `planner_error`) — nên đây KHÔNG phải
   phép đo Task 3, mà là phép đo đường single-anchor cũ trên code mới.
2. RUN 1 và RUN 3 **cùng fingerprint nhưng khác điểm**; toàn bộ phần "tốt lên"
   nằm đúng ở hai câu không tái lập được.
3. n=19 KIS / n=5 QA / n=1 TRAKE — chênh lệch một câu đã đổi aggregate.

Lý do: evaluator gần nhất chạy 21/08; PLAN bắt đầu 24/08; ES/Milvus/Docker hiện
đang tắt. Muốn có "after" phải: bật Docker → `docker compose up` → chạy
`dev_set/tools/run_evaluation.py` với manifest → nhưng gate vẫn chặn vì GT chưa
verified (mục M/L).

**Trạng thái promotion gate đo thật hôm nay** (`05_promotion_gate_actual.json`):

```json
{ "eligible": false,
  "metrics": {},
  "reasons": [{ "code": "ground_truth_unverified",
                "message": "holdout/regression còn nhãn chưa verified",
                "query_ids": ["KIS_001", ... 38 ID ...] }] }
```

Fail-closed đúng thiết kế. Nhưng hệ quả: **acceptance criteria của PLAN chưa có
một dòng nào được chứng minh bằng số đo.**

---

## P. Trace thực tế

**Không có trace nào để gửi.** Đã tìm toàn repo: không tồn tại `trace.jsonl`,
receipt, `runtime-fingerprint.json` hay checksum nào.

`run.py` **có** ghi trace (`TRACE_NAME = "trace.jsonl"`, ghi từ
`QueryRun.to_trace_dict()`), nhưng chưa có lần chạy nào sau khi tính năng này ra đời.

Artefact chạy thật gần nhất là checkpoint 21/08
(`submissions/dienlap_20260821/checkpoint.jsonl`) — schema cũ, **không có**
`runtime_fingerprint`, `query_plan`, `source_ranks`, `qa_hypotheses`.

**Schema trace mới sẽ chứa gì** (từ `runner.py:174-196`) — để bạn biết trước
cần đọc gì khi có trace: `query_id, task_type, status, failure_class, error,
retryable, runtime_fingerprint, query_plan, source_ranks, source_contributions,
search_rows, qa_hypotheses, timings, task_metadata, answer_text, qa_trace,
n_trake, answers`.

Nếu bạn cần trace thật để audit sâu, việc cần làm là: bật Docker, chạy
`python run.py --queries data/queries/sotuyen1_p1.jsonl --out <dir>` trên vài
query. Tôi chưa làm việc này vì nó gọi LLM API thật (tốn tiền) và cần dịch vụ đang tắt.

---

## Q. Error / failure taxonomy — **có HAI bộ, chưa hợp nhất**

### Bộ 1 — evaluation failure (mới, product spec)

`backend/tasks/runner.py:18-33`, 6 nhãn đúng như PLAN:
`retrieval_miss` · `wrong_frame` · `qa_reasoning` · `missing_evidence` ·
`trake_order` · `format`.

Được ép bằng `__post_init__` và `failure_trace()`; nhãn ngoài danh sách → `ValueError`.
Có test chặn hồi quy về `F0_CRASH` (`tests/test_task_runner.py:251`).

Cách gán hiện tại (`runner.py:309-314, 499-513`):
```
ValueError            → "format"
QA + lỗi khác         → "missing_evidence",  retryable=True
TRAKE + lỗi khác      → "trake_order"
KIS + lỗi khác        → "retrieval_miss"
```

⚠️ Đây là gán **theo task type**, không phải theo nguyên nhân thật. Một lỗi
timeout ES trong KIS vẫn được dán nhãn `retrieval_miss`. `wrong_frame` và
`qa_reasoning` **không có đường nào tự động gán** — chúng chỉ xuất hiện nếu
scorer/người gán khi so với GT.

### Bộ 2 — legacy, còn trong artefact cũ

`SUCCESS` · `F_UNKNOWN` · `F_QA_REASONING_FAILED` · `F_QA_RETRIEVAL_FAILED` ·
`F0_CRASH`. Có trong `dev_set/results/*/scores.json` và `scratch_run_qa_paced.py:84`.
`run_evaluation.py:276-279` vẫn phải đọc được `F0_CRASH` để tương thích ngược.

### Runtime failure — **CHƯA phân biệt**

Không có taxonomy riêng cho `timeout` / `rate_limit` / `provider_error` /
`invalid_response` / `missing_cache` / `invalid_evidence`. Toàn bộ nén vào một
cờ boolean `retryable`, và cờ đó chỉ bật cho QA:

```python
# runner.py:512
retryable = task_type == "QA" and not isinstance(error, ValueError)
```

Nghĩa là 429 rate-limit trong lúc dịch query KIS → `retryable=False`. Đây là
khoảng trống thật so với yêu cầu của bạn ở mục Q.

Ngoại lệ có phân loại riêng: `QAGenerationBudgetExceeded`,
`QAEvidenceCaptureError`, `QANoValidHypothesisError` (`qa.py:263-273`) — nhưng
chúng bị nuốt vào `missing_evidence` khi lên tới runner.

---

## R. Submission / export pipeline

| Thành phần | File |
|---|---|
| exporter, CSV, ZIP | `backend/export/exporter.py` (683) — **không đổi trong PLAN** |
| validator | `exporter.py::validate_submission / validate_all / validate_file / validate_zip` |
| QA policy transform | `backend/export/qa_variants.py::apply_qa_submission_policy` |
| release gate + receipt | `backend/export/release_rehearsal.py` (786, **mới**) |
| orchestration | `run.py:623-760` |

**Điều kiện "một query lỗi → KHÔNG có ZIP một phần" — CÓ, hai lớp:**

1. `run.py:626-641`: dựng bài nộp **từ checkpoint**, không phải từ RAM. Nếu
   `missing_for_full_export` khác rỗng → log "DỪNG XUẤT GÓI", `return 1`,
   **không ghi CSV lẫn ZIP**. Lý do ghi trong code: subset có thể bị nộp nhầm
   như submission đầy đủ.
2. `exporter.py:476-481`: `write_submissions` chạy `validate_all` trước, có issue
   → `raise ValueError`, không ghi file.

**ZIP transaction** (`release_rehearsal.py:662-786`, kết quả của finding P2 vòng 1):
config + ZIP + receipt ghi vào staging duy nhất → hậu kiểm → backup + atomic
replace. Mọi exception khôi phục artefact tốt cũ. ZIP tên cuối chỉ xuất hiện sau
khi staging qua validator.

Giới hạn được tuyên bố rõ trong review: đảm bảo rollback với exception bắt được
trong process; **không** tuyên bố atomic đa-file trước power loss.

**Checksum:** SHA-256 trong receipt (`RELEASE_RECEIPT_SCHEMA_VERSION = 1`).
**Naming:** `data/config/submit_format.py::suggest_filename` — CSV không header,
UTF-8, `video_id` không đuôi `.mp4`, tên file = tên gói BTC đổi `.txt` → `.csv`.

**Submission ↔ trace binding** (fix của finding P1 vòng 1): canonical-compare
toàn bộ ordered rows (video, frames, answer, keyframe) giữa submission sắp ghi và
`trace.answers` mới nhất; Q&A chỉ chấp nhận đúng transform deterministic của
`apply_qa_submission_policy()`. Sửa checkpoint mà giữ query ID/task → bị chặn
bằng `submission_trace_mismatch`.

---

## S. Release artefact

```
release rehearsal CHƯA THỰC HIỆN
```

Không có thư mục release nào trong repo. Không có `receipt`, `runtime-fingerprint.json`,
`checksum.sha256`, `trace.jsonl`.

**Code đường release đã tồn tại và có test** (`run.py --release-rehearsal --zip
--promotion-audit <file>`, `tests/test_release_rehearsal.py` 23 test), nhưng chưa
chạy thật vì `promotion_gate` trả `BLOCKED` (mục O) nên `run.py:455-473` dừng
trước cả preflight.

Ledger có ghi "preflight development/release đều `17 đạt, 0 hỏng, 2 bỏ qua`" —
đó là `scripts/preflight_check.py`, kiểm môi trường, **không** phải release rehearsal
sinh artefact.

---

## T. Runtime environment — đo thật 27/08

`07_runtime_env.txt`.

| | Thực tế | PLAN giả định | Khớp? |
|---|---|---|---|
| OS | Windows-11-10.0.26200-SP0 | Windows 11 | ✅ |
| Python | **3.14.0** (MSC v.1944, 64-bit) | 3.14 | ✅ |
| CPU | Intel64 Family 6 Model 154 Stepping 3 (Alder Lake-H) | — | — |
| RAM | **15,7 GB total · 3,2 GB free** lúc đo | 16 GB | ✅ |
| torch | **2.13.0+cpu** | torch CPU | ✅ |
| CLIP | `open_clip_torch 3.3.0`, model `ViT-B-32-quickgelu` / pretrained `openai`, dim 512 | — | — |
| Milvus client | `pymilvus 3.0.1` | — | server **KHÔNG chạy** |
| Elasticsearch client | `elasticsearch 8.19.3` | — | server **KHÔNG chạy** |
| Anthropic SDK | `anthropic 0.125.0` | — | — |
| Google GenAI SDK | `google-genai 2.19.0` | — | — |
| pytest | 9.1.1 | — | — |
| numpy / pandas / pyarrow | 2.5.2 / 3.0.5 / 25.0.1 | — | — |

**Dịch vụ:** `docker` daemon không chạy · ES:9200 CLOSED · Milvus:19530 CLOSED.

**Không có dependency lock** (`requirements.txt` / `poetry.lock` / `uv.lock`)
trong repo — chỉ có `.venv` cục bộ. Đây là rủi ro tái lập thật sự.

---

## U. External services

```
LLM   : Anthropic — model claude-sonnet-5  (.env: LLM_BACKEND=api, LLM_API_MODEL=claude-sonnet-5)
        gọi qua backend/llm/adapter.py::llm() — điểm gọi DUY NHẤT
VLM   : cùng model, cùng adapter (llm(prompt, images=[...]))
        chỉ dùng trong Q&A; KIS online không gọi VLM
Backup: Google Gemini — gemini-3.6-flash (LLM_BACKEND=gemini), KHÔNG tự động fallback
Local : Ollama qwen2.5:7b-instruct (LLM_BACKEND=local), HTTP localhost:11434
Milvus: pymilvus 3.0.1 → localhost:19530, collection theo backend/indexing/milvus_client.py  [ĐANG TẮT]
ES    : elasticsearch 8.19.3 → localhost:9200, index: metadata/objects/ocr/asr  [ĐANG TẮT]
other : không có
```

Không có API key/token nào trong gói này.

---

## V. Dirty work / parallel development

| Câu hỏi | Trả lời |
|---|---|
| Còn file dirty không? | **Một** file untracked: `dev_set/ground_truth/sotuyen1_p1_draft_gt.jsonl`. Không có file modified/staged. |
| File đó của ai? | **Của người dùng** — bản nháp label GT tay cho 25 query vòng 1, tất cả `status: TODO`. Đính kèm ở `manifests/`. |
| `backend/llm/adapter.py` có bị thay đổi không? | **CÓ**, ở commit `b419f6e` — commit **sau** khi PLAN hoàn tất. |
| Ai sửa? | Người dùng (commit cuối, cùng lượt với `ARCHITECTURE.md` / `docs/testing.md` / `docs/deployment.md`). Commit range của PLAN (`b8090cd..c443903`) **không** chạm file này — review đã verify bằng `git diff --name-only`. |
| Conflict / merge tay? | Không có trong cửa sổ PLAN. Có merge tay **trước đó** (`5de46ca`, `bcee061`, `e9e3f63` — merge nhánh của Công Lý), đều trước `b8090cd`. |

**Chi tiết `b419f6e` sửa gì trong adapter** (để bạn không quy nhầm cho PLAN):
1. `DEFAULT_GEMINI_MODEL`: `gemini-2.5-flash` → `gemini-3.6-flash` (bản cũ trả
   404 với key mới).
2. Tách `_nap_dotenv()` ra khỏi `_anthropic_client()`: `.env` giờ chỉ **vá chỗ
   trống**, không ghi đè biến operator đã export; và gọi được từ mọi backend.
3. `runner.py:225`: `LLM_BACKEND` mặc định `"<unset>"` → `"api"` (làm fingerprint
   khớp với hành vi thật của adapter khi không set biến).

Thay đổi (3) **đổi giá trị runtime fingerprint** so với lúc PLAN được review —
mọi cache/checkpoint tạo trước `b419f6e` đều bị invalidate.

---

## W. Quyết định khác PLAN

Đối chiếu từng hằng số PLAN chỉ định với code (mục J): **RRF k=7, 3 anchor,
60 token, temporal bonus 1.25, 6 answer mode, gate 0.82/0.82/0.75, alternatives=1
— tất cả khớp đúng.** Không có deviation kiểu "PLAN nói 7, implement 10".

Các sai lệch thật sự là:

```
PLAN: "Không sửa backend/llm/adapter.py"
THỰC TẾ: đã sửa ở b419f6e — SAU khi PLAN xong, do người dùng, lý do:
         gemini-2.5-flash trả 404 với API key mới ("chạy được trên máy người khác"),
         và .env ghi đè biến export gây lệch preflight ↔ adapter.
         → không vi phạm trong cửa sổ PLAN, nhưng HEAD hiện tại khác trạng thái được review.

PLAN: (không nói) — knob mới tự thêm
THỰC TẾ: PER_ANCHOR_POOL=100, SHORT_QUERY_MAX_WORDS=18, COMPLEX_MARKER_MIN=1,
         COMPLEX_MARKERS, ORDER_MARKERS, ORDER_MARKER_PAIRS, QUANTIFIER_TERMS,
         COUNT_CLASSIFIERS, COMMON_COLOR_TERMS
         → cần thiết để "query ngắn dùng single-anchor" và validator fidelity chạy được,
           nhưng chúng là heuristic tiếng Việt hardcode-trong-config, chưa ai tune.

PLAN: "gộp entrypoint"
THỰC TẾ: gộp 2/3. run_minimal.py giữ dispatch riêng (cố ý — kịch bản dự phòng khi
         hệ thống treo giữa buổi thi, CLAUDE.md §2 yêu cầu "bấm là chạy được ngay").

PLAN: Task 3 "hợp nhất ở shot/video bằng RRF k=7"
THỰC TẾ: hợp nhất ở shot; nếu thiếu clip_kf_map thì rơi về group theo keyframe
         (multi_anchor.py:362-364). Không có mức "video".
```

**Ruling được ghi lại trong ledger** (`audit_reports/02_progress-ledger.md`) —
hai quyết định có ghi kèm hệ quả nếu sai:
- không tạo linked worktree (workspace duy nhất theo AGENTS.md);
- đóng băng query nhưng giữ GT `unknown`, không bịa nhãn để đạt gate.

---

## X. Code không muốn sửa / frozen

| Vùng | Trạng thái |
|---|---|
| `backend/llm/adapter.py` | PLAN cấm sửa. HEAD **đã** sửa (mục V). Nếu repair tiếp: xin xác nhận trước. |
| `backend/agent/` | CHUNG KẾT — `CLAUDE.md` §3 ghi "KHÔNG ĐỤNG" |
| `backend/retrieval/search.py` | không đổi trong PLAN; là nhánh retrieval lõi, `CLAUDE.md` giao cho Thạch, có quyền phủ quyết schema |
| `backend/slot/allocator.py` | không đổi; 79 test; sở hữu bởi Minh Hoàng |
| `backend/tasks/trake.py` | không đổi; PLAN yêu cầu giữ nguyên |
| `backend/export/exporter.py` | không đổi; format nộp đã chốt theo Codabench BTC |
| `data/config/submit_format.py` | format đã chốt từ trang thi BTC — sửa = sai format nộp |
| `run_minimal.py` | kịch bản dự phòng, cố ý giữ độc lập |
| CLI + checkpoint schema của `run.py` | PLAN yêu cầu **không đổi**; đã giữ (chỉ thêm option mới) |
| Code của đồng đội | `frontend/`, `preprocessing/`, `scripts/audit/` — Công Lý sở hữu |

**API compatibility bắt buộc:** `giai_mot_query()` giữ chữ ký cũ
`-> tuple[list[Answer], dict]` qua `QueryRun.compatibility_metadata()`;
`run_evaluation.py --split` legacy vẫn chạy; checkpoint cũ vẫn parse được (chỉ bị
invalidate vì thiếu fingerprint, không crash).

---

## Y. Mục tiêu / priority hiện tại

**Đã xác nhận bởi chủ dự án (27/08/2026):**

```
1. Có số đo thật          ← chặn mọi thứ khác; hiện KHÔNG có "after" nào
2. No crashes / submission chạy được
3. KIS accuracy
4. Q&A accuracy
5. Reproducibility
6. Architecture cleanliness
```

Lý do đặt (1) lên đầu: kiến trúc provenance/gate đã rất chặt (813 test, fail-closed
đúng chỗ), nhưng nó đang bảo vệ một hệ thống **chưa ai biết chạy tốt hay không**.
Mọi finding kiến trúc còn lại đều rẻ hơn việc không có số.

**Hệ quả cho audit:** finding chỉ ảnh hưởng thẩm mỹ/kiến trúc mà không đụng tới
khả năng đo được, khả năng nộp bài, hay accuracy thì **xin xếp vào backlog sau
04/09**, đừng đề xuất sửa ngay. Ngược lại, bất kỳ thứ gì chặn đường "chạy được
một lần đo end-to-end" đều là P0.

---

## Z. Deadline

**Đã xác nhận bởi chủ dự án (27/08/2026): còn khoảng MỘT NGÀY.**

- Đợt 2 sơ tuyển: **28/08/2026, 19:30–22:30** (tối mai).
- Điều này đặt repo vào đúng chế độ mà `docs/product-spec.md` §Constraints mô tả:
  *"khi còn dưới 24 giờ chỉ sửa crash, format, mất dữ liệu, sai mapping hoặc P0."*

Mốc tiếp theo sau đó: đợt 3 ngày **04/09/2026** — sau đợt 2 còn 7 ngày để sửa,
và `CLAUDE.md` §1 bắt buộc post-mortem trong 24h sau mỗi đợt.

**Hệ quả cho repair strategy — xin auditor tách rõ hai rổ:**

| Rổ | Cửa sổ | Tiêu chí |
|---|---|---|
| **A — trước 28/08 19:30** | ~1 ngày | chỉ crash · sai format nộp · mất dữ liệu · sai frame mapping · P0 chặn việc chạy được một lần đo |
| **B — 29/08 → 04/09** | 7 ngày | mọi thứ còn lại: gap kiến trúc, taxonomy runtime failure, rank 5 nguồn trong multi-anchor trace, dependency lock, deterministic replay test |

Lưu ý rủi ro cho rổ A: hiện Docker/ES/Milvus đang tắt và `run_minimal.py` là
đường dự phòng **không** đi qua `solve_query()` — nên nó không nhận bất kỳ fix nào
của PLAN. Nếu tối mai phải dùng `run_minimal.py`, hệ thống chạy sẽ là bản
trước-PLAN, không phải bản vừa được audit.

---

## Tóm tắt cho auditor: PLAN → CODE traceability

| Yêu cầu PLAN | Trạng thái | Bằng chứng |
|---|---|---|
| T1 · product-spec 9 mục | **correct** | `docs/product-spec.md` đủ 9 heading |
| T1 · GT schema verification_status | **correct** | `dev_set/tools/schema.py` +122 dòng; 5 test |
| T1 · promotion chỉ nhận `verified` | **correct** | gate thật trả `ground_truth_unverified` (`05_...json`) |
| T1 · đóng băng 25 query vòng 1 | **correct** | blob sha b8090cd == HEAD == worktree |
| T1 · manifest `batch1_holdout13` | **correct** | 10 KIS + 3 QA, nhãn `unknown`, không bịa |
| T2 · `solve_query()` entrypoint chung | **correct** | run.py:396 + run_evaluation.py:306; dispatch cũ bị xoá |
| T2 · trace đủ 6 failure class | **partial** | 6 nhãn có; nhưng gán theo task type, `wrong_frame`/`qa_reasoning` không có đường tự động |
| T2 · không đổi CLI/checkpoint/submission | **correct** | chỉ thêm option; legacy checkpoint vẫn parse |
| T3 · ≤3 anchor, ≤60 token | **correct** | có test đếm token thật |
| T3 · fallback khi planner lỗi | **correct** | 5 lý do fallback, fail-closed toàn plan |
| T3 · validator chặn màu/số/lượng | **correct** | `_preserves_color_context` + `_preserves_quantifier_context` |
| T3 · RRF k=7 outer + temporal 1.25 soft | **correct** | `multi_anchor.py:393-403` |
| T3 · knob trong `data/config/` | **correct** | `data/config/multi_anchor.py` |
| T3 · log rank từng nhánh | **⚠️ regression** | `search_multi` ghi đè `ranks` bằng anchor rank; mất rank 5 nguồn ở multi-anchor |
| T4 · 6 answer_mode + fallback | **correct** | `ANSWER_MODES`, `planner_fallback` |
| T4 · QAHypothesis gắn evidence | **correct** | pin qua `frame_map`, assert khớp, raise nếu lệch |
| T4 · portfolio round-robin | **correct** | `qa_portfolio.py:99-135` |
| T4 · loại sentinel, không ZIP một phần | **correct** | 3 lớp chặn + raise thay vì đệm |
| T4 · cache key đủ chiều | **correct** (vượt yêu cầu) | thêm `full_query_sha256`, single-flight |
| T5 · gate zero-crash/GT/threshold/regression | **correct** | `promotion_gate.py` 578 dòng, 18 test |
| T5 · release artefact đầy đủ | **unverifiable** | code + 23 test có; **chưa chạy thật lần nào** |
| T5 · validator chặn batch thiếu | **correct** | 2 lớp (run.py + exporter) |
| T5 · "ghi kết quả đo thật" | **❌ missing** | không có số đo nào sau implement |
| Toàn cục · không sửa adapter.py | **violation (ngoài phạm vi PLAN)** | sửa ở `b419f6e`, sau khi PLAN xong, do người dùng |
| Toàn cục · TDD | **correct** | ledger ghi từng vòng RED→GREEN; 6 vòng fix có finding cụ thể |
| Toàn cục · không bịa GT | **correct** | 0/38 nhãn được nâng trạng thái; gate vẫn BLOCKED |
```
