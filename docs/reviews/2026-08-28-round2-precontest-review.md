# Independent pre-contest release review — Round 2

Ngày review: 28/08/2026 (Asia/Saigon). Phạm vi chỉ gồm thay đổi sau
`b419f6e8114da5e3a045cb85e19a8b9dda0b6788` và evidence/runtime candidate hiện
hành. Đây là review chỉ-đọc; ngoại lệ duy nhất là file báo cáo này.

## Review surface

| Mục | Candidate được review |
|---|---|
| Baseline | `b419f6e8114da5e3a045cb85e19a8b9dda0b6788` |
| Branch | `codex/batch1-accuracy-repair` |
| HEAD | `d3eb66d7cf5c395ce6c607d3d078e5d6c73873f0` |
| Commit range | `8cad8e2` audit context; `38f6d45` bỏ `maxItems`; `d3eb66d` tắt multi-anchor cho Round 2 |
| Committed diff | 46 file, `+16.528/-2`; production chỉ đổi `backend/retrieval/multi_anchor.py` (xóa một dòng schema) và `data/config/multi_anchor.py` (`ENABLED=True -> False`), cộng test và gói audit |
| Staged diff | Không có |
| Unstaged diff | Không có |
| Untracked release-relevant | Ba run evaluator 27/08; run KIS multi-anchor; run KIS single-anchor cuối; P0 design freeze, gap triage, pre-repair baseline, hai báo cáo KIS và Q&A operational decision |
| Untracked không dùng làm release evidence | `dev_set/ground_truth/sotuyen1_p1_draft_gt.jsonl` còn draft/TODO |

Candidate state bao gồm các tài liệu và artefact untracked trên. Không có
production code/config untracked. Gói audit commit `8cad8e2` chứa một raw diff có
trailing whitespace; đây là nội dung snapshot lịch sử, không phải source chạy.

## Evidence và verification đã dùng

- Đã đọc đầy đủ các tài liệu được yêu cầu: master/eval 27/08, P0 design freeze,
  gap triage, pre-repair baseline, multi-anchor live measurement, rollback/final
  single-anchor check, Q&A operational decision, deployment/runbook, preflight,
  source/config/test và các snapshot/record tương ứng.
- Không chạy `batch1_holdout13`, không gọi live provider, không tạo promotion
  evidence mới.
- Current release preflight:
  `\.venv\Scripts\python.exe -B scripts\preflight_check.py --profile release`
  trả exit 0: **17 đạt, 0 hỏng, 2 bỏ qua**. Nó in
  `LLM_BACKEND=api`, `model=claude-sonnet-5`, `QA mode=legacy`; ES, Milvus,
  frame map, vector norm/COSINE, đường ZIP, latency search và 100-row constants
  đều đạt. Hai mục bỏ qua là Streamlit và API `/health`, đều không bắt buộc cho
  batch CLI.
- Full suite được chạy lại bằng temp cô lập trong workspace:
  `\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider --basetemp <isolated>`
  trả **815 passed, 1 skipped, 2 warnings in 43.24s**. Temp đã được xóa sau run.
  Lần chạy đầu không truyền `--basetemp` bị vô hiệu vì sandbox từ chối
  `C:\Users\lehon\AppData\Local\Temp\pytest-of-lehon`; không coi 186 setup error
  đó là source regression.
- So SHA-256 của 13 file config và 8 critical source hiện tại với snapshot
  `run_20260828_round2_single_anchor_final_01`: **0 mismatch**.
- Reproduction chỉ-đọc trên HEAD:
  `is_valid_qa_answer("Không đủ căn cứ xác định") == True`, và constructor
  `QAHypothesis` tạo object thành công với answer này.

## Kết luận theo 27 tiêu chí P0/P1

### P0 compatibility / maxItems

1. **YES.** Live diagnostic sau repair có `strategy=multi` 19/19,
   `planner_error=0/19`; lỗi provider 400 quan sát trước repair không còn xuất
   hiện.
2. **YES.** `maxItems` vẫn bị xóa ở HEAD trong
   `backend/retrieval/multi_anchor.py`.
3. **YES.** Python guard còn nguyên tại
   `backend/retrieval/multi_anchor.py:269`; `MAX_ANCHORS=3` tại
   `data/config/multi_anchor.py:4`. Regression test quá bốn anchor vẫn pass.
4. **NO change.** Repair không đổi adapter/provider/model/prompt/ranking. Diff
   baseline-to-HEAD không chạm `backend/llm/adapter.py`, search weights, slot
   budget hay QA inference constants.

### KIS execution và rollback Round 2

5. **YES.** Artefact `run_20260827_kis19_multi_anchor_01` gắn commit `38f6d45`,
   fingerprint `19b507d...`: 19/19 multi, 2–3 anchor, 0 fallback, 0 crash, 0
   mapping/output-row violation.
6. **YES.** Candidate có `data/config/multi_anchor.py:3` là `ENABLED=False`;
   `plan_query()` trả single trước planner tại
   `backend/retrieval/multi_anchor.py:287`.
7. **YES.** Artefact `run_20260828_round2_single_anchor_final_01` gắn đúng HEAD:
   19/19 single, planner call 0, `search_multi()` call 0, fallback `None` 19/19.
8. **YES.** `RRF_K`, source weights, temporal bonus, slot budget và các ranking
   constants không đổi trong range.
9. **NO crash regression.** Cả hai diagnostic KIS có crash count 0; full suite
   xanh.
10. **NO frame mapping/bounds violation.** Cả hai diagnostic ghi 0 violation.
11. **YES.** Final single-anchor Final `0.4000` khớp pre-fix single path và cao
    hơn multi-anchor `0.3263`; selection dựa trên measurement, không chỉ config.

### Q&A release path

12. **YES.** Selected mode vẫn là `legacy`, một full batch tuần tự với
    checkpoint/resume; runbook và operational decision cùng khóa hành vi này.
13. **YES.** `two_stage` còn implemented nhưng bị cấm cho release; default và
    lệnh operator đều là `legacy`.
14. **NO unsupported concurrency introduced.** `run.py` vẫn lặp query tuần tự;
    không có post-baseline async/process/thread batch path.
15. **PARTIAL / BLOCKING.** Khi không có hypothesis hợp lệ, Q&A vẫn fail
    `missing_evidence`, answers rỗng, retryable. Nhưng surface sentinel quan sát
    được lại bị coi là answer hợp lệ, nên bảo đảm “không guessed/sentinel” không
    đúng cho toàn bộ release path.
16. **NO.** Approved sentinel repair không tồn tại trong HEAD hay untracked
    source/test/report; exact surface vẫn tạo được `QAHypothesis`.
17. **Existing missing-evidence behaviour is preserved**, nhưng không có repair
    để đánh giá preservation sau repair. RUN 3 `DRESS_QA_04` và test hiện hành
    vẫn chứng minh zero-hypothesis fail closed.
18. **NO post-repair evidence.** Full suite xanh nhưng không có test exact string
    và không có post-repair diagnostic vì repair chưa xảy ra.
19. **NO.** `legacy`/checkpoint scheduling tự thân phù hợp, nhưng actual selected
    Q&A path chưa safe enough do sentinel blocker chưa giải quyết.

### Submission / fallback / operator safety

20. **YES, có risk trực tiếp từ Q&A sentinel.** Format validator không thể nhận
    biết negative-evidence answer mang đúng kiểu CSV; nó có thể đi vào ZIP hợp
    lệ về cú pháp.
21. **YES, partial ZIP vẫn không thể tạo qua production path.** `run.py:627-641`
    dừng export khi checkpoint thiếu query; exporter validate toàn batch trước
    khi ghi.
22. **YES.** `ANSWERS_PER_QUERY=100`, allocator/exporter/preflight cùng kiểm;
    KIS final diagnostic có 100 rows/query.
23. **YES.** Retry `--only` dùng lại checkpoint toàn query; record chỉ được reuse
    khi query hash và runtime fingerprint khớp.
24. **NO silent resume mixing found.** Backend/model, raw QA mode, mọi config và
    critical source nằm trong fingerprint; thay đổi làm record hết hạn và chạy
    lại. Operator vẫn phải giữ cùng process/env như runbook.
25. **NO accidental runtime change found.** Post-baseline runtime diff chỉ là
    minimal schema compatibility fix và feature-gate rollback có measurement.
26. **YES mechanically.** Same-fingerprint resume, `--only`, full-checkpoint
    export và previous validated ZIP fallback còn hoạt động. Nó không giảm nhẹ
    HIGH sentinel vì sentinel bị checkpoint như success thay vì query hỏng.

### Runtime environment

27. **PARTIAL.** Backend/model, Q&A mode, checkpoint/output, fingerprint rule và
    release preflight có tài liệu. Tuy nhiên Round-2 KIS gate và cache expectation
    chưa được in/khóa trong một runbook/preflight Round-2 duy nhất; xem MEDIUM.

### CRITICAL

Không có finding CRITICAL.

### HIGH

#### H1 — Approved Q&A sentinel repair chưa có; invalid negative-evidence answer vẫn vào hypothesis/portfolio

- **Evidence:** Operational decision ghi repair bắt buộc trước contest tại
  `docs/plans/2026-08-28-round2-qa-operational-decision.md:331`. RUN 3 ghi
  `"Không đủ căn cứ xác định"` ở
  `dev_set/results/run_20260827_154710_27d970c1/DRESS_QA_01.csv:3` và `:6`.
  Candidate hiện tại chỉ có exact sentinel `"không đủ căn cứ"` cùng một tập
  continuation giới hạn tại `data/config/qa_hypotheses.py:28-43`;
  `backend/tasks/qa.py:444-460` trả valid cho surface quan sát. Reproduction hiện
  tại xác nhận cả validator và `QAHypothesis` constructor đều chấp nhận nó.
- **Affected path/artefact:** `data/config/qa_hypotheses.py`,
  `backend/tasks/qa.py`, `tests/test_qa_hypotheses.py`, RUN 3 Q&A CSV/evidence,
  và release preflight hiện hành.
- **Why Round 2 matters:** Answer này được coi là success, có thể được
  checkpoint, đủ 100 dòng, qua format validator và vào ZIP. Vì không trở thành
  `missing_evidence`, runbook `--only`/resume không tự retry nó. Đây là actual
  selected `legacy` release path, không phải tuning hay deferred architecture.
- **New after baseline:** **NO.** Post-baseline commits không chạm Q&A source;
  lỗi có trước baseline nhưng được observed/approved là release blocker trong
  post-baseline runtime evidence. Nó được review vì Q&A sentinel nằm explicit
  trong scope, không phải reopening kiến trúc cũ.
- **Existing mitigation:** Exact/configured sentinels vẫn bị chặn và zero-valid-
  hypothesis vẫn fail `missing_evidence`; partial ZIP cũng bị chặn. Các guard này
  không bắt exact observed surface. Current release preflight trả xanh nhưng
  không kiểm sentinel semantics, nên không phải mitigation. Không có operator
  workaround an toàn; quyết định hiện hành cũng cấm sửa CSV tay hoặc đoán answer.

### MEDIUM

#### M1 — Hợp đồng vận hành Round 2 còn phân tán và evidence quyết định vẫn untracked

- **Evidence:** `docs/deployment.md:49-52` còn model placeholder; committed
  `docs/RUNBOOK_ROUND1.md:25-29` khóa `api/claude-sonnet-5/legacy` nhưng mang tên
  Round 1. Round-2 Q&A decision và hai KIS decision/evidence đều untracked.
  `data/config/multi_anchor.py:3` là `ENABLED=False`, nhưng current preflight
  chỉ in backend/model/QA mode (`scripts/preflight_check.py:153-210`) và không
  in KIS gate hay `LLM_NO_CACHE`. Final KIS snapshot ghi QA mode và
  `LLM_NO_CACHE` là `<unset>` (`config_snapshot.json:12,41`), trong khi contest
  runbook yêu cầu set `QA_INFERENCE_MODE=legacy`; do đó contest fingerprint sẽ
  khác literal diagnostic fingerprint dù KIS-relevant source/config hash khớp.
- **Affected path/artefact:** `docs/deployment.md`, `docs/RUNBOOK_ROUND1.md`,
  `scripts/preflight_check.py`, `data/config/multi_anchor.py`, các untracked
  Round-2 decision/evaluation files và final config snapshot.
- **Why Round 2 matters:** Một clean clone/cleanup hoặc handoff chỉ từ HEAD không
  mang theo final decision/evidence; operator cũng không có một output duy nhất
  xác nhận feature gate/cache state. Rủi ro là vận hành nhầm hoặc không chứng
  minh được exact candidate, không phải lỗi ranking/runtime hiện tại.
- **New after baseline:** **YES.** Rollback feature gate và toàn bộ final
  decision/evidence được tạo sau baseline; gap xuất hiện khi mode Round 2 đổi
  nhưng runbook/preflight chưa được hợp nhất.
- **Existing mitigation:** HEAD hardcode `ENABLED=False`, fingerprint hash toàn
  config, final snapshot khớp current source/config 0 mismatch, và committed
  runbook có exact provider/model/QA mode. Mitigation an toàn cho rehearsal là
  giữ nguyên workspace hiện tại, kiểm bằng mắt `ENABLED=False`, giữ cache state
  như đã chốt, set explicit `api/claude-sonnet-5/legacy`, lưu preflight output và
  không resume qua fingerprint khác. MEDIUM này tự nó không chặn rehearsal.

### DEFERRED

- Five-source rank trace redesign, runtime taxonomy redesign, dependency lock,
  deterministic replay architecture, TRAKE multi-anchor, unifying
  `run_minimal.py` và clean verified holdout vẫn là post-Round-2.
- Raw audit snapshot trailing whitespace và committed audit-bundle size không
  tác động runtime candidate.
- Không finding deferred nào bị post-baseline change biến thành direct Round-2
  blocker.

## Final release checklist

- maxItems live-provider blocker resolved: **YES**
- Python `<=3 anchors` guard intact: **YES**
- repaired multi-anchor execution previously demonstrated: **YES**
- multi-anchor disabled for selected Round-2 KIS mode: **YES**
- final single-anchor KIS evidence supports release mode: **YES**
- ranking/config constants unchanged: **YES**
- crash regression found: **NO**
- frame mapping violation found: **NO**
- Q&A sentinel blocker resolved: **NO**
- Q&A fail-closed `missing_evidence` preserved: **YES**
- selected Q&A mode matches approved operational decision: **YES**
- partial ZIP remains impossible: **YES**
- fallback/resume plan verified: **YES**
- service/model/environment requirements explicit: **NO**
- accidental out-of-scope change found: **NO**

## Verdict

`NOT READY — P0/P1 BLOCKER REMAINS`  
> ⚠️ **Đã bị thay thế 01/09/2026 — xem [Addendum H1](#addendum-01092026--h1-resolved) ở cuối file.**
> H1 đã được sửa ở `fe7faca`; verdict cập nhật: `READY — H1 RESOLVED` (M1 vẫn mở, không chặn).

Lý do duy nhất làm verdict bị block là H1 trên actual Q&A release path. MEDIUM
M1 có safe operator mitigation và không tự nó chặn contest rehearsal.


---

## Addendum 01/09/2026 — H1 RESOLVED

> Phần trên là bản ghi tại thời điểm 28/08/2026 và **giữ nguyên** làm lịch sử.
> Mục này ghi trạng thái đã xác minh lại trên HEAD `4372069`
> (branch `codex/qa-last-3h`), ngày 01/09/2026.

### Fix đã landed

Commit `fe7faca` (28/08/2026) — *fix(qa): reject evidence-refusal answers*:
`backend/tasks/qa.py` (+28), `data/config/qa_hypotheses.py` (+35),
`tests/test_qa_hypotheses.py` (+108).

RUN 3 CSV trong evidence của H1 chạy ngày **27/08**, tức **trước** fix một ngày.
Đó là lý do artifact cũ vẫn chứa sentinel — không phải vì code hiện tại còn lọt.

### Cơ chế chặn

H1 yêu cầu chặn ở **cả hai chỗ**; cả hai đều đã chặn:

| Chốt chặn | Vị trí | Trạng thái |
|---|---|---|
| `is_valid_qa_answer()` | `backend/tasks/qa.py:470` | ✅ trả `False` |
| `QAHypothesis.__post_init__` | `backend/tasks/qa.py:208` | ✅ raise `ValueError` |

Không dựa vào việc thêm surface vào danh sách sentinel (danh sách đó không bao
giờ đủ). Matcher `_la_cau_tu_choi()` bắt **cấu trúc** câu từ chối: answer bắt đầu
bằng token phủ định (`QA_REFUSAL_PREFIXES`) *và* có nhắc tới khả năng
xác định/bằng chứng (`QA_REFUSAL_EVIDENCE_PHRASES`, ở đây khớp `căn cứ` và
`xác định`), với `QA_REFUSAL_MIN_WORDS` chặn dưới.

Điều này giữ được đáp án phủ định **hợp lệ** — `"Không có người trong ảnh"`,
`"Không thấy mưa"`, `"Không"` — vì chúng không chứa cụm evidence.

### Bằng chứng đã chạy (01/09/2026)

```
is_valid_qa_answer("Không đủ căn cứ xác định")  -> False
is_valid_qa_answer("Nguyễn Minh Châu")          -> True
```

Test dùng **đúng chuỗi đã quan sát** trong RUN 3:

- `tests/test_qa_hypotheses.py:297` — chặn tại validator
- `tests/test_qa_hypotheses.py:327` — chặn tại constructor `QAHypothesis`

```bash
python -m pytest tests/test_qa_hypotheses.py tests/test_run.py tests/test_task_runner.py -q
```

→ **118 passed**.

### Hệ quả với `--only` / resume

Mối lo trong H1 (*"vì không thành `missing_evidence`, runbook `--only`/resume
không tự retry"*) đã hết: answer bị loại → không còn valid hypothesis →
pipeline fail-closed với `failure_class = "missing_evidence"`
(`tests/test_qa_hypotheses.py:203`, `:699-730`), nên resume **tự chạy lại** câu đó.

### Còn mở (không chặn verdict)

1. ~~Export/preflight chưa kiểm sentinel semantics.~~ **ĐÃ ĐÓNG 01/09** — xem
   *Addendum 2* bên dưới.
2. ~~Artifact cũ vẫn bẩn.~~ **ĐÃ CHẠY LẠI 01/09** — xem *Addendum 2* bên dưới.
   Artifact cũ `run_20260827_154710_27d970c1/` vẫn giữ nguyên làm bằng chứng
   lịch sử của H1; **không dùng nó cho rehearsal/freeze nữa**.
3. **M1** (hợp đồng vận hành phân tán) — nguyên trạng, có mitigation an toàn.

### Verdict cập nhật

`READY — H1 RESOLVED`

Lý do duy nhất chặn verdict 28/08 là H1 trên actual Q&A release path. H1 đã đóng
bằng code + regression test dùng đúng surface quan sát. M1 vẫn ở mức MEDIUM và
tự nó không chặn rehearsal.


---

## Addendum 2 — 01/09/2026: defense-in-depth + artifact sạch

### 1. Sentinel validation đã có ở tầng export và preflight

H1 chỉ yêu cầu hai chốt chặn thượng nguồn, nhưng sentinel là chuỗi **không rỗng,
dưới 100 ký tự, không có khoảng trắng thừa** → lọt sạch mọi luật answer khác của
tầng nộp. Nay bịt thêm hai chỗ:

| Tầng | Vị trí | Luật |
|---|---|---|
| Export validator | `backend/export/exporter.py` | Issue `answer_refusal` |
| Release preflight | `backend/export/release_rehearsal.py:183` `_valid_hypothesis` | reason `qa_evidence_invalid` |

Chỗ thứ hai mới là lỗ thật sự: `_valid_hypothesis` trước đây chỉ đòi
`answer_text` là **string không rỗng**, mà nó đọc **trace JSONL** — trace có thể
là của lần chạy CŨ, sinh ra trước fix `fe7faca`. Nghĩa là một trace 27/08 vẫn
qua được release assessment.

### 2. Một predicate duy nhất, không có bản sao

`is_valid_qa_answer()` / `_normalize_answer()` / `_la_cau_tu_choi()` đã chuyển từ
`backend/tasks/qa.py` sang `data/config/qa_hypotheses.py` (module thuần, không
import Milvus/LLM/search — tầng export không được kéo cả pipeline retrieval vào).
`backend/tasks/qa.py` re-export nên **không call site nào phải đổi**.

Hai bản sao danh sách sentinel lệch nhau còn tệ hơn không kiểm, nên có test bám
thẳng vào identity:

```python
assert exporter.is_valid_qa_answer is is_valid_qa_answer
```

### 3. Test chứng minh ZIP không được sinh ra

Test khẳng định tính chất mạnh (không tồn tại file nộp được), không chỉ "có báo lỗi":

```python
with pytest.raises(ValueError, match="KHÔNG ghi file"):
    write_submission_zip([ban_loi], tmp_path)
assert list(tmp_path.glob("*.zip")) == []
```

Đã kiểm test **không rỗng nghĩa**: tạm vô hiệu luật (`elif False:`) → **10 test
fail**; khôi phục → xanh lại. Kèm regression guard cho đáp án phủ định hợp lệ
(`"Không có người trong ảnh"`, `"Không"`, `"0"`).

**Full suite: 803 passed, 2 skipped.**

### 4. Chạy lại RUN 3 trên HEAD hiện tại

```bash
python -m dev_set.tools.run_evaluation --split dress25
```

Artifact mới: `dev_set/results/run_20260901_182905_bb0188df/` (commit `4372069`).

| | RUN 3 cũ (27/08) | RUN mới (01/09) |
|---|---|---|
| commit | `b419f6e` | `4372069` |
| QA answer rows | 400 | 400 |
| **Dòng sentinel/từ chối** | **2** (`DRESS_QA_01.csv:3`, `:6`) | **0** |
| Export gate | **REJECTED** (`answer_refusal` ×2) | accepted |
| QA final avg | 0.200 | 0.200 |
| Overall final avg | 0.363 | 0.363 |

Quét bằng đúng predicate production trên cả hai artifact: bản cũ lòi ra **đúng
hai dòng review đã ghi**, bản mới sạch. Cho luôn hai artifact qua export gate mới:
bản cũ bị chặn đúng vị trí 3 và 6, bản mới đi qua.

**Điểm không đổi** (0.363 / 0.200) vì hai dòng sentinel vốn đã bị chấm 0 —
`DRESS_QA_01` là `retrieval_miss` ở cả hai lần chạy. Sửa H1 **không** làm đẹp số;
nó chỉ ngăn một bài nộp trông hợp lệ mà chắc chắn 0 điểm.

### 5. `DRESS_QA_04` fail — KHÔNG phải hồi quy

`DRESS_QA_04` fail `missing_evidence` ở lần chạy mới, và **cũng fail y hệt ở RUN 3
cũ**. Đây là lỗi có sẵn, không do thay đổi 01/09. Fail-closed hoạt động đúng:
không có CSV `DRESS_QA_04.csv` nào được sinh ra, và vì là `missing_evidence` nên
`--only`/resume sẽ tự chạy lại.

### 6. Cảnh báo khi so hai run

Sửa `data/config/qa_hypotheses.py` làm đổi `config_sha256` → đổi
`runtime_fingerprint` (`f9b98636…` → `95e17525…`). Đây là **đúng**: hành vi có
thay đổi thật. Hệ quả: cache hypothesis cũ bị vô hiệu (run mới tính lại từ đầu,
không tái dùng câu trả lời 27/08), và **so khớp fingerprint giữa hai run sẽ lệch
theo thiết kế**, không phải do hỏng.

### 7. Phạm vi — promotion gate KHÔNG nằm trong đây

`promotion_ready` vẫn là `false` ở **cả hai** run, và lần chạy này **không** dùng
cờ `--promotion`. Addendum này chỉ khẳng định đúng một điều: **H1 đã đóng và
artifact dùng cho rehearsal/freeze đã sạch sentinel.** Nó không khẳng định gì về
promotion eligibility, chất lượng ground truth, hay hiệu năng — promotion gate là
việc riêng, xử lý tách bạch.
