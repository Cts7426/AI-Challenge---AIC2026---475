# Round-2 contest rehearsal — operational readiness

Ngày chạy: 28/08/2026 08:43 (+0700, Asia/Saigon).
Người chạy: rehearsal agent (read-only ngoài chính file báo cáo này).

## Phạm vi và giới hạn (đọc trước)

Đây là **operational readiness rehearsal**. Nó **KHÔNG** phải promotion gate và
**KHÔNG** được dùng để khẳng định chất lượng retrieval/answer không thiên lệch.

- Không dùng `batch1_holdout13`.
- Không đổi tuning parameter, ranking constant, provider, model, inference
  algorithm, feature policy, evidence policy hay production behaviour.
- Không sửa product code, production config hoặc test.
- **Không nộp gì ra ngoài.** `external submission performed: NO`
- `dress25` diagnostic score **không** phải promotion evidence.
- Ghi permitted duy nhất trong lần chạy này: chính file báo cáo này. Không có
  checkpoint/CSV/ZIP disposable nào được tạo, vì rehearsal dừng ở Phase 0.

## Kết quả tổng: DỪNG Ở PHASE 0

Phase 0 (release blocker gate) **KHÔNG ĐẠT**. Theo đúng chỉ dẫn rehearsal,
quá trình dừng lại trước khi khởi động dịch vụ và trước mọi live-provider smoke,
để không tiêu tốn chi phí provider chỉ để xác nhận lại một release blocker đã biết.

Phase 1–8 **không được thực thi**. Trạng thái của chúng là *chưa chạy*, không phải
*đạt* và cũng không phải *hỏng*.

---

## PHASE 0 — RELEASE BLOCKER GATE (KHÔNG ĐẠT)

### Candidate so với independent review

| Mục | Giá trị |
|---|---|
| Independent review | `docs/reviews/2026-08-28-round2-precontest-review.md` |
| Reviewed HEAD | `d3eb66d7cf5c395ce6c607d3d078e5d6c73873f0` |
| **Current HEAD** | `d3eb66d7cf5c395ce6c607d3d078e5d6c73873f0` |
| Branch | `codex/batch1-accuracy-repair` |
| Commit sau review | **KHÔNG CÓ** (`git log d3eb66d..HEAD` rỗng) |
| Staged changes | Không có |
| Unstaged changes | Không có |
| Verdict của review | `NOT READY — P0/P1 BLOCKER REMAINS` (H1 — Q&A sentinel) |

Candidate hiện tại **giống hệt** candidate đã bị review chặn. Không có repair
task, repair commit, hay post-repair report nào tồn tại — kể cả dạng untracked:

- `docs/release/` trước lần chạy này **không tồn tại**.
- File mới nhất trong `docs/` là chính bản review (mtime 28/08 08:25).
- `grep` toàn `tests/ backend/ data/config/ scripts/` cho chuỗi quan sát
  `Không đủ căn cứ xác định` → **không có kết quả nào**.

### Xác minh trạng thái blocker CRITICAL/HIGH của review

Review ghi **0 CRITICAL** và **1 HIGH (H1)**. H1 chưa được giải quyết:

| Yêu cầu Phase 0 | Kết quả trên CURRENT HEAD |
|---|---|
| Surface `Không đủ căn cứ xác định` không thể thành answer/hypothesis/portfolio item hợp lệ | ❌ **THẤT BẠI** |
| Configured negative-evidence sentinel tương đương vẫn bị reject | ✅ ĐẠT |
| Zero-valid-hypothesis vẫn fail closed thành `missing_evidence` | ✅ ĐẠT (không đổi) |
| Không có guessed answer thay thế | ✅ ĐẠT (không có synthetic fallback) |
| Không cần manual CSV workaround | ❌ **KHÔNG THOẢ** — không tồn tại workaround an toàn nào |
| Regression evidence cho đúng surface quan sát | ❌ **KHÔNG CÓ** |

### Bằng chứng đo trực tiếp (read-only, không gọi provider)

Reproduction chạy bằng `.venv\Scripts\python.exe -B` trên HEAD hiện tại:

```
EXACT OBSERVED SURFACE : 'Không đủ căn cứ xác định'
normalized             : 'không đủ căn cứ xác định'
is_valid_qa_answer     : True          <-- BLOCKER

--- configured sentinels still rejected? ---
  'insufficient evidence'                valid=False
  'không có thông tin'                   valid=False
  'không đủ căn cứ'                      valid=False
  'không đủ thông tin'                   valid=False
  'no information'                       valid=False
  'not enough information'               valid=False

--- prefix + continuation samples ---
  'Không đủ căn cứ xác định'             valid=True   <-- BLOCKER
  'Không đủ căn cứ để'                   valid=False
  'Không đủ căn cứ trong'                valid=False
  'Không đủ căn cứ rõ'                   valid=True   <-- cùng lỗ hổng
  'Không đủ căn cứ nào'                  valid=True   <-- cùng lỗ hổng
```

Guard ở tầng object cũng không chặn:

```
QAHypothesis CONSTRUCTED with sentinel surface: 'Không đủ căn cứ xác định'
__post_init__ guard did NOT reject it
```

### Cơ chế lỗi — BA chế độ hỏng độc lập, không phải một

`backend/tasks/qa.py:444-461` chỉ reject khi normalized answer **bằng đúng** một
sentinel trong `QA_SENTINEL_ANSWERS`, hoặc khi nó bắt đầu bằng sentinel **và**
token kế tiếp nằm trong `QA_SENTINEL_PREFIX_CONTINUATIONS`
(`data/config/qa_hypotheses.py:40-43`).

**Chế độ 1 — continuation không có trong allowlist.** Allowlist đóng gồm
`để, trong, từ, về, được, có, nhằm, is, was, to, in, from, about, available,
provided`. Token `xác` không có → surface quan sát lọt. Cùng cơ chế: `rõ`, `nào`,
`liên`, `cụ`.

**Chế độ 2 — stem sentinel KHÔNG được đăng ký.** `QA_SENTINEL_ANSWERS` chỉ có
`không đủ căn cứ`, `không có thông tin`, `không đủ thông tin` (+3 bản EN).
Nó **không có** `không có căn cứ` và **không có** `không có đủ thông tin`.
Vì vậy cả họ này bỏ qua toàn bộ kiểm tra prefix, bất kể continuation là gì:

```
valid=True   Không có căn cứ trong video
valid=True   Không có căn cứ để xác định      <-- 'để' TRONG allowlist mà vẫn lọt
valid=True   Không có đủ thông tin để xác định
```

Đây là bằng chứng quyết định rằng repair **không thể** chỉ là thêm token vào
allowlist: `Không có căn cứ để xác định` có continuation hợp lệ mà vẫn lọt vì
stem chưa đăng ký.

**Chế độ 3 — căng thẳng thiết kế có thật.** Không thể ban thẳng prefix, vì
`Không có thông tin liên lạc` và `No Information Technology` là answer **hợp lệ**
và test hiện có (`tests/test_qa_hypotheses.py:238-249`) khẳng định chúng phải
`True`. Repair phải phân biệt ngữ nghĩa "câu này từ chối trả lời" với "câu này
tình cờ trùng tiền tố", chứ không phải nới/siết một danh sách token.

Vì `QAHypothesis.__post_init__` (`backend/tasks/qa.py:199-203`) và portfolio guard
(`backend/tasks/qa_portfolio.py:86`) đều gọi cùng `is_valid_qa_answer()`, cả ba
tầng bảo vệ hỏng cùng lúc.

### Vì sao đây là blocker trên đúng đường release Round 2

Đường được chọn cho Round 2 là Q&A `legacy`, sequential full-batch, checkpoint/
resume — chính là đường bị ảnh hưởng.

1. Sentinel đi qua validator → `solve_query()` trả về bình thường.
2. `run.py` chỉ phân loại `missing_evidence` trong nhánh `except`
   (`run.py:556-560`). Answer trả về bình thường đi vào **success checkpoint**
   (`run.py:575-601`).
3. Vì được checkpoint là **thành công**, `--only` retry và resume **sẽ không**
   tự chạy lại query này. Operator không có tín hiệu để retry.
4. Format validator chỉ kiểm cú pháp CSV; nó không thể biết chuỗi này là
   negative-evidence. Answer đủ điều kiện đi vào ZIP hợp lệ.
5. Không được sửa bằng tay: quyết định vận hành đã cấm sửa CSV thủ công và cấm
   đoán answer (`docs/plans/2026-08-28-round2-qa-operational-decision.md:243,257`).

Đây là **hai cửa tử** của dạng Q&A: answer sai = 0 điểm cho câu đó dù frame đúng.

### Bằng chứng đã thực sự xảy ra trong runtime

`dev_set/results/run_20260827_154710_27d970c1/DRESS_QA_01.csv` (RUN 3), dòng 3 và 6:

```
L22_V006,35655,"Không đủ căn cứ xác định"
L22_V006,35592,"Không đủ căn cứ xác định"
```

Đếm trên toàn bộ QA CSV của RUN 3: `DRESS_QA_01.csv` = 2 dòng; `_02/_03/_05` = 0.

### Quét toàn bộ cache — phạm vi thật rộng hơn nhiều so với một surface

Quét 677 file trong `data/cache/llm/` (499) và `data/cache/qa_hypotheses/` (179),
bóc 1.396 chuỗi `answer`, rồi phân loại bằng **validator hiện tại**:

| Nhóm | Occurrences | Distinct | Files |
|---|---|---|---|
| Negative-evidence **ĐƯỢC CHẤP NHẬN** (sẽ vào CSV nộp) | **75** | **39** | 48 |
| Negative-evidence bị chặn đúng | 927 | 70 | — |

Tức khoảng **7,5%** số lần model từ chối trả lời lọt qua guard, trải trên **39
surface khác nhau** — không phải một chuỗi cá biệt.

Các surface lọt nhiều nhất:

```
  8x  Không đủ căn cứ xác định tên đèo
  5x  Không có căn cứ trong video
  4x  Không có căn cứ để xác định
  4x  Không có thông tin liên quan trong video
  4x  Không có thông tin cụ thể
  4x  Không đủ căn cứ xác định            <-- exact surface trong review
  3x  Không có đủ thông tin để xác định
  3x  Không có căn cứ trong video về tên con đèo
```

Guard vẫn chặn đúng các biến thể phổ biến nhất (`Không đủ căn cứ để xác định`
404x, `Không đủ căn cứ` 234x), nên đây là lỗ hổng hẹp về tỉ lệ nhưng rộng về
hình thái.

Một mẫu đáng lo riêng, vừa là sentinel vừa là **answer đoán**:

```
Không đủ căn cứ xác định tên đèo (có thể là đèo Ô Quy Hồ, đoạn Sa Pa - Lai Châu)
```

Chuỗi này qua validator, và nó vi phạm luôn cả quy tắc "không đoán answer".

⚠️ **Giới hạn diễn giải:** cache là lịch sử nhiều lần chạy, có thể gồm HEAD cũ và
mode khác. Nó **không** dự đoán chính xác một contest run Round 2 sẽ sinh ra gì.
Điều nó chứng minh chắc chắn là: model + prompt hiện tại sinh ra lớp chuỗi này
thường xuyên và đa dạng, và **validator hiện tại** cho 39 dạng trong số đó đi qua.

### Cache replay KHÔNG phải rủi ro bổ sung (đã kiểm)

`_qa_cache_get` (`backend/tasks/qa.py:1103-1122`) tra theo key = sha256 của
identity dict, trong đó có `runtime_fingerprint`. Fingerprint tính được:

```
QA_INFERENCE_MODE=<unset>  -> 29bd614623abbe72f11dcc253fc23a81f46e01a6ea3085613fb9c5c5b75ea75e
QA_INFERENCE_MODE=legacy   -> ca0f59bb1e8ecf4aaaaa54e7804b602a861f6b3f6020e0dd0f539cbc94060a3b
cache entries bị nhiễm     -> f9b986361ce69683e9c0b013858baba6d87d127d707f8f2c44e0461a6f2119db
```

Fingerprint của cache **không khớp** cả cấu hình contest (`legacy`) lẫn cấu hình
diagnostic (`<unset>`), nên các entry nhiễm sẽ sinh key khác → cache miss → sinh
lại. **Không có rủi ro replay.** Đồng thời cũng **không có lá chắn**: sinh lại sẽ
tạo ra đúng lớp chuỗi đó.

Ghi chú phụ: `<unset>` cho ra đúng `29bd614...` của snapshot diagnostic, xác nhận
môi trường reproduction trong rehearsal này trung thực với snapshot. `data/cache/`
nằm trong `.gitignore:56` nên là local-only.

### Repair đã được phê duyệt nhưng chưa tồn tại

`docs/plans/2026-08-28-round2-qa-operational-decision.md:329-331` ghi rõ:

- `Code/config repair required before contest: **YES**`
- Repair task phải: chặn surface này **trước khi** tạo `QAHypothesis`/portfolio;
  thêm regression test đúng chuỗi quan sát; giữ fail-closed `missing_evidence`;
  chạy lại bộ test Q&A/export và diagnostic `dress25` (không dùng làm promotion).

Cùng tài liệu, dòng 272 và 278, đặt đây là **gate bắt buộc**: chỉ bắt đầu
candidate release sau khi repair sentinel được duyệt.

### Repair không thể gắn vào current HEAD

So SHA-256 của 13 config + 8 critical source hiện tại với snapshot
`dev_set/results/run_20260828_round2_single_anchor_final_01/config_snapshot.json`:

```
TOTAL checked=21 mismatch=0
  OK  data/config/qa_hypotheses.py      2d3b4e2ff3cec06481cda34164431962b44f3f108d910606c035e145a1f36511
  OK  backend/tasks/qa.py               d38abae8c33bb7405351802a131faf5f2a9ddb3ba8aa561dca60209e004acc6f
  OK  data/config/multi_anchor.py       c9d3dac0f0e2c1f1c9afd1342b2b5d79d5075c37ab82a4b37fb1869c9b383f23
  OK  backend/retrieval/multi_anchor.py 72dcce33a50450a7d2c1fb4454b58cfd21df065538e948d0d543e958a78c758a
```

0 mismatch nghĩa là hai file Q&A liên quan **giống hệt** bản đã bị review chặn.
Không có repair nào để gắn vào HEAD.

### Kết luận Phase 0

**KHÔNG ĐẠT.** Rehearsal dừng tại đây.

---

## Candidate identity đã ghi được trong Phase 0 (KHÔNG phải Phase 1 hoàn chỉnh)

Các giá trị dưới đây thu thập read-only, không khởi động dịch vụ, không gọi
provider. Ghi lại để lần rehearsal sau không phải làm lại — **không** coi đây là
một Phase 1 freeze đã hoàn tất.

| Mục | Giá trị |
|---|---|
| HEAD | `d3eb66d7cf5c395ce6c607d3d078e5d6c73873f0` |
| Branch | `codex/batch1-accuracy-repair` |
| Staged / unstaged | Không có |
| Untracked release-relevant | 5 thư mục run diagnostic + P0 design freeze, gap triage, 3 evaluation report, Q&A operational decision, independent review |
| Untracked KHÔNG dùng làm evidence | `dev_set/ground_truth/sotuyen1_p1_draft_gt.jsonl` (còn draft) |
| `LLM_BACKEND` | `api` (từ `.env`; shell hiện `<unset>` → runbook yêu cầu set explicit) |
| Exact LLM model | `claude-sonnet-5` (`LLM_API_MODEL` trong `.env`) |
| `QA_INFERENCE_MODE` | shell `<unset>` → default `legacy` (`data/config/qa_inference.py:12`); runbook yêu cầu set explicit |
| Selected Q&A mode | `legacy`, sequential full-batch, checkpoint/resume |
| `data/config/multi_anchor.py::ENABLED` | `False` ✅ (gate Round 2 đúng) |
| Selected KIS mode | single-anchor (measured release path) |
| `LLM_NO_CACHE` | `<unset>` trong shell và trong final snapshot (`llm_no_cache`) |
| Config hashes | 13 file, khớp snapshot, 0 mismatch |
| Critical source hashes | 8 file, khớp snapshot, 0 mismatch |
| Runtime fingerprint (diagnostic) | `29bd614623abbe72f11dcc253fc23a81f46e01a6ea3085613fb9c5c5b75ea75e` |
| Python | 3.14.0 (MSC v.1944 64-bit) |

⚠️ Lưu ý fingerprint (đã nêu trong review, M1): snapshot diagnostic ghi
`qa_inference_mode = "<unset>"`, còn runbook contest yêu cầu set
`QA_INFERENCE_MODE=legacy`. Hai giá trị này cho **fingerprint khác nhau** dù
hành vi suy luận giống nhau (default = `legacy`). Không được resume checkpoint
diagnostic bằng môi trường contest và ngược lại.

Chính sách vận hành Round 2 kỳ vọng — **khớp** với config thực tế đọc được:

- KIS: single-anchor đã đo ✅
- Q&A: `legacy`, sequential full-batch, checkpoint/resume ✅
- không `two_stage` ✅ (còn implemented nhưng không được chọn)
- không concurrent worker ghi cùng checkpoint/output ✅ (`run.py` lặp tuần tự)
- không partial ZIP ✅ (`run.py:627-641` chặn export khi checkpoint thiếu query)

Không phát hiện config nào mâu thuẫn với quyết định Round 2 đã duyệt. **Không có
config nào bị sửa trong rehearsal này.**

---

## PHASE 1–8 — KHÔNG THỰC THI

| Phase | Trạng thái | Lý do |
|---|---|---|
| 1 — Freeze | Chưa chạy (một phần identity đã ghi ở trên) | Chặn bởi Phase 0 |
| 2 — Services | Chưa chạy | Không khởi động Docker/ES/Milvus theo chỉ dẫn STOP |
| 3 — Tests / preflight | Chưa chạy trong rehearsal này | Xem ghi chú kế thừa bên dưới |
| 4 — Production-path smoke | Chưa chạy | Không gọi live provider để xác nhận lại blocker đã biết |
| 5 — Checkpoint / retry | Chưa chạy | Chặn bởi Phase 0 |
| 6 — Export rehearsal | Chưa chạy | Chặn bởi Phase 0 |
| 7 — Emergency fallback | Chưa chạy | Chặn bởi Phase 0 |
| 8 — Final operator runbook | Chưa phát hành | Runbook Round-2 chỉ nên phát hành sau khi candidate hợp lệ |

**Evidence kế thừa từ independent review** (28/08, cùng HEAD — ghi để tham chiếu,
KHÔNG phải kết quả rehearsal):

- Full suite: `815 passed, 1 skipped, 2 warnings in 43.24s`
- Release preflight `--profile release`: exit 0, `17 đạt, 0 hỏng, 2 bỏ qua`
  (bỏ qua: Streamlit, API `/health` — không bắt buộc cho batch CLI); in
  `LLM_BACKEND=api`, `model=claude-sonnet-5`, `QA mode=legacy`.

⚠️ Preflight xanh **không** chứng minh Q&A sentinel semantics an toàn. Preflight
không kiểm sentinel semantics; điều đó được gate độc lập ở Phase 0 và đang hỏng.

---

## PHASE 9 — FINDINGS

### CRITICAL

Không có.

### HIGH

#### H1 — Q&A sentinel surface `Không đủ căn cứ xác định` vẫn được chấp nhận là answer hợp lệ

- **Trạng thái:** CHƯA GIẢI QUYẾT. Xác nhận lại trực tiếp trên HEAD `d3eb66d`.
- **Đường bị ảnh hưởng:** đúng đường release Round 2 đã chọn (Q&A `legacy`).
- **Vị trí:** `backend/tasks/qa.py:444-461`,
  `data/config/qa_hypotheses.py:28-43`, lan sang
  `backend/tasks/qa.py:199-203` và `backend/tasks/qa_portfolio.py:86`.
- **Hệ quả:** answer negative-evidence được checkpoint là thành công, không bị
  `--only` retry, qua format validator, vào ZIP hợp lệ → câu đó chắc chắn 0 điểm.
- **Mitigation an toàn cho operator:** **KHÔNG CÓ.** Sửa CSV tay và đoán answer
  đều bị quyết định vận hành cấm.
- **Regression evidence cho đúng surface:** không tồn tại. Test hiện có
  (`tests/test_qa_hypotheses.py:205-235`) chỉ phủ exact sentinel và bốn
  continuation nằm trong allowlist.
- **Phạm vi thực đo (mới, phát hiện trong rehearsal này):** quét 677 file cache
  cho thấy **39 surface negative-evidence khác nhau** (75 occurrences) lọt qua
  validator hiện tại — không phải một chuỗi. Ba chế độ hỏng độc lập: continuation
  ngoài allowlist; **stem `không có căn cứ` / `không có đủ thông tin` chưa được
  đăng ký trong `QA_SENTINEL_ANSWERS`**; và căng thẳng với answer hợp lệ trùng
  tiền tố. Bằng chứng dứt điểm: `Không có căn cứ để xác định` lọt **dù** `để` nằm
  trong allowlist, vì stem chưa đăng ký.
- **Hệ quả cho repair:** thêm token vào allowlist **không đủ** và sẽ tạo cảm giác
  an toàn sai. Repair phải xử lý cả stem set lẫn ngữ nghĩa từ chối trả lời, đồng
  thời giữ `Không có thông tin liên lạc` / `No Information Technology` hợp lệ.
- **Mẫu nghiêm trọng kèm theo:** `Không đủ căn cứ xác định tên đèo (có thể là đèo
  Ô Quy Hồ, đoạn Sa Pa - Lai Châu)` vừa là sentinel vừa là answer đoán, và vẫn
  qua validator.

### MEDIUM

#### M1 — Hợp đồng vận hành Round 2 phân tán; preflight không in KIS gate và cache state

- Kế thừa nguyên trạng từ independent review; rehearsal không làm nặng thêm.
- `docs/deployment.md:49-52` còn model placeholder; runbook đã khóa
  `api/claude-sonnet-5/legacy` nhưng mang tên `RUNBOOK_ROUND1.md`.
- `scripts/preflight_check.py:153-210` in backend/model/QA mode nhưng **không**
  in `multi_anchor.ENABLED` và `LLM_NO_CACHE`.
- Toàn bộ quyết định/evidence Round 2 vẫn untracked → clean clone từ HEAD sẽ
  không mang theo chúng.
- **Mitigation an toàn có tồn tại:** giữ nguyên workspace hiện tại; kiểm bằng mắt
  `data/config/multi_anchor.py:3` là `ENABLED = False`; set explicit
  `LLM_BACKEND=api`, `LLM_API_MODEL=claude-sonnet-5`, `QA_INFERENCE_MODE=legacy`;
  giữ nguyên cache state; lưu output preflight; không resume qua fingerprint khác.
- M1 **không** tự chặn Round 2.

#### M2 — Fingerprint diagnostic khác fingerprint contest

- Snapshot diagnostic có `qa_inference_mode = "<unset>"`; contest runbook set
  `legacy`. Fingerprint sẽ khác dù hành vi giống.
- **Mitigation:** không resume checkpoint diagnostic trong contest; coi contest
  run là checkpoint mới hoàn toàn. Đây đúng là hành vi mong muốn (fail-safe
  invalidation), chỉ cần operator biết trước để không tưởng là lỗi.

### DEFERRED (không chặn Round 2)

- Unify `run_minimal.py` với `solve_query()` — vẫn hoãn, **không** mở lại.
- Five-source rank trace redesign, runtime taxonomy redesign, dependency lock,
  deterministic replay architecture, TRAKE multi-anchor.
- Clean verified holdout ground truth (`sotuyen1_p1_draft_gt.jsonl` còn draft).
- Trailing whitespace trong raw audit snapshot; kích thước audit bundle.

---

## Báo cáo trạng thái trước verdict

- **current HEAD:** `d3eb66d7cf5c395ce6c607d3d078e5d6c73873f0` (branch `codex/batch1-accuracy-repair`, clean)
- **full-suite status:** không chạy trong rehearsal; kế thừa `815 passed, 1 skipped` trên cùng HEAD từ independent review
- **release preflight status:** không chạy trong rehearsal; kế thừa exit 0 (`17 đạt, 0 hỏng, 2 bỏ qua`) trên cùng HEAD
- **selected KIS mode:** single-anchor; `multi_anchor.ENABLED = False` đã xác minh
- **selected Q&A mode:** `legacy`, sequential full-batch, checkpoint/resume
- **Q&A sentinel repair verified:** **NO — repair không tồn tại; blocker tái xác nhận trên HEAD, và phạm vi rộng hơn báo cáo trước: 39 surface lọt qua validator, ba chế độ hỏng độc lập**
- **production-path KIS smoke:** NOT RUN (chặn bởi Phase 0)
- **production-path Q&A smoke:** NOT RUN (chặn bởi Phase 0)
- **production-path TRAKE smoke:** NOT RUN (chặn bởi Phase 0)
- **checkpoint/resume rehearsal:** NOT RUN (chặn bởi Phase 0)
- **complete export rehearsal:** NOT RUN (chặn bởi Phase 0)
- **partial-ZIP guard:** không thực thi trong rehearsal; source-level guard còn nguyên tại `run.py:627-641`
- **emergency fallback classification:** NOT ASSESSED (chặn bởi Phase 0; `run_minimal.py` không bị chạm)
- **exact runtime environment captured:** PARTIAL — HEAD/branch/backend/model/Q&A mode/KIS gate/cache/hash/fingerprint đã ghi ở trên; chưa có xác minh service-level
- **external submission performed:** **NO**

---

## VERDICT

`NOT READY FOR ROUND 2 — Q&A sentinel release blocker remains`

Đây **không** phải `PROMOTION ELIGIBLE`. Không có khẳng định nào về hiệu năng
không thiên lệch: không có verified ground truth sạch và promotion gate thật
chưa chạy độc lập.

---

## Điều kiện để mở khoá (không thực hiện trong rehearsal này)

Rehearsal không sửa code. Để rehearsal kế tiếp vượt được Phase 0, cần một repair
task riêng có phê duyệt, theo đúng spec đã duyệt ở
`docs/plans/2026-08-28-round2-qa-operational-decision.md:331`:

1. Chặn surface negative-evidence **trước khi** tạo `QAHypothesis`/portfolio.
   Phải xử lý **cả ba** chế độ hỏng, không chỉ thêm `xác` vào allowlist:
   - continuation ngoài allowlist (`xác`, `rõ`, `nào`, `liên`, `cụ`, …);
   - stem chưa đăng ký — tối thiểu `không có căn cứ`, `không có đủ thông tin`;
   - phân biệt ngữ nghĩa từ chối trả lời với answer trùng tiền tố.
2. Thêm regression test cho **đúng** chuỗi quan sát `Không đủ căn cứ xác định`,
   và cho ít nhất các đại diện của hai chế độ còn lại
   (`Không có căn cứ để xác định`, `Không có đủ thông tin để xác định`).
3. Dùng 39 surface đã liệt kê được từ cache làm bộ test liệu thật; mục tiêu là
   0/39 lọt sau repair. Script phân loại chạy lại được (xem mục lệnh).
4. Giữ nguyên fail-closed `missing_evidence`; không thay bằng answer đoán.
5. Giữ nguyên answer hợp lệ trùng tiền tố (`No Information Technology`,
   `Không có thông tin liên lạc`) — test hiện có phải vẫn pass.
6. Chặn luôn dạng sentinel-kèm-phỏng-đoán (`… (có thể là …)`).
7. Chạy lại full suite + bộ test Q&A/export, chạy lại preflight release.
8. Chạy lại diagnostic `dress25`; **không** dùng nó làm promotion evidence.
9. Chạy lại rehearsal này từ Phase 0 trên HEAD sau repair.

Ngoài ra, đóng M1 bằng cách in `multi_anchor.ENABLED` và `LLM_NO_CACHE` trong
release preflight, và hợp nhất runbook Round 2 — nên làm nhưng không chặn.

---

## Lệnh đã chạy trong rehearsal (tất cả read-only)

```
git log --oneline b419f6e..HEAD ; git rev-parse HEAD ; git status --porcelain
grep -rn "is_valid_qa_answer|SENTINEL" backend/ data/config/ tests/
grep -rn "Không đủ căn cứ xác định" tests/ backend/ data/config/ scripts/
grep -rn "Không đủ căn cứ xác định" data/cache/          # phát hiện phạm vi rộng
.venv\Scripts\python.exe -B -c "<reproduction is_valid_qa_answer / QAHypothesis>"
.venv\Scripts\python.exe -B -c "<so sánh sha256 config+critical source với snapshot>"
.venv\Scripts\python.exe -B -c "<runtime_fingerprint() dưới 2 giá trị QA_INFERENCE_MODE>"
.venv\Scripts\python.exe -B <scratch>\classify_cache.py   # phân loại 1.396 answer
head -8 dev_set/results/run_20260827_154710_27d970c1/DRESS_QA_01.csv
```

`classify_cache.py` nằm ở scratchpad phiên chạy (disposable, ngoài repo). Nó chỉ
đọc `data/cache/`, parse JSON lồng hai tầng, và gọi `is_valid_qa_answer()`. Nên
chép lại vào repair task để đo 0/39 sau khi sửa.

Fingerprint được tính trong subprocess với env riêng; **không** đổi env hay config
của candidate thật.

Không khởi động dịch vụ. Không gọi provider. Không sinh checkpoint/CSV/ZIP.
Không sửa product code, production config hoặc test.
