# PRE-CONTEST GAP TRIAGE — Round 2

Ngày triage: 27/08/2026. Round 2 bắt đầu lúc **19:30 ngày 28/08/2026**.
Tài liệu này chỉ phân loại gap; không phải implementation plan và không thay đổi
code. Trong cửa sổ freeze dưới 24 giờ, Bucket A chỉ nhận lỗi crash, format, mất
dữ liệu, sai frame mapping, P0 im lặng hoặc vấn đề làm đường chạy/nghiệm thu bài
nộp không dùng được vào ngày thi.

## Nguồn và trạng thái đọc-only

Nguồn đã đối chiếu:

- `reports/audit_context_20260827/00_MASTER.md`
- `reports/audit_context_20260827/10_eval_20260827_results.md`
- `reports/audit_context_20260827/docs/PLAN.md`
- `docs/product-spec.md`
- `docs/design/2026-08-27-round2-p0-design-freeze.md`
- `reports/audit_context_20260827/audit_reports/00_final-review.md`

`git status --short --branch` trước khi tạo tài liệu triage này:

```text
## codex/batch1-accuracy-repair
?? dev_set/ground_truth/sotuyen1_p1_draft_gt.jsonl
?? dev_set/results/run_20260827_153845_27d970c1/
?? dev_set/results/run_20260827_154331_27d970c1/
?? dev_set/results/run_20260827_154710_27d970c1/
?? docs/design/2026-08-27-round2-p0-design-freeze.md
```

Không có tracked change ở snapshot này. Các run, draft GT và design freeze đang
untracked phải được giữ nguyên.

Các ngưỡng `0.82 / 0.82 / 0.75` chỉ là ngưỡng cấu hình, **không phải điểm đã
đo**. `batch1_holdout13` đã bị dùng để tune trước PLAN và GT vẫn chưa được người
xác minh; vì vậy tài liệu này không coi nó là holdout không thiên vị, không đề
nghị dùng hai lượt còn lại, và không nâng `verification_status` khi thiếu
provenance người thật.

## Bucket A — MUST ADDRESS BEFORE ROUND 2

### A1. `maxItems` làm multi-anchor chết hoàn toàn

**Evidence.** Hai run `dress25` hoàn tất ngày 27/08 đều có 19/19 KIS
`strategy=single`, `fallback_reason=planner_error`, mặc dù 19/19 query đi qua
planner. Lời gọi Anthropic thật trả HTTP 400 vì schema array không hỗ trợ
`maxItems`. Khi bỏ keyword này chỉ trong bộ nhớ, 6/6 query thử tạo 3 anchor hợp
lệ. `_validated_anchors()` vẫn chặn payload quá `MAX_ANCHORS=3`. Đây là
occurrence production duy nhất và đã được đóng băng phạm vi trong
`docs/design/2026-08-27-round2-p0-design-freeze.md`.

**Exact failure mode.** `plan_query()` nuốt lỗi provider rồi âm thầm rơi về
single-anchor. Task 3 chưa từng chạy trong production, nên không thể có phép đo
multi-anchor thật; KIS đang chạy đường fallback cũ mà không báo lỗi. Đây là P0
silent failure đã xác nhận.

**Minimum action.** Giữ repair hoàn toàn cô lập: chỉ xóa một dòng
`"maxItems": MAX_ANCHORS` trong `ANCHOR_SCHEMA` và thêm đúng một regression test
hẹp trong `tests/test_multi_anchor.py`. Không sửa adapter, search, prompt,
validator, config, RRF, temporal, slot, QA, TRAKE, exporter hoặc `run_minimal.py`.

**Verification.** Chạy focused tests và full suite; quét schema production bảo
đảm không còn `maxItems`; smoke với đúng Anthropic backend/model ngày 27/08;
sau đó chạy mới `dress25` bằng fingerprint sạch. Chỉ dùng KIS query-level diff
và latency để quyết định: không còn schema `planner_error`, mọi plan có 2–3
anchor, không có KIS failure mới và KIS aggregate không dưới mốc single-path
`0.4000`. Không dùng `batch1_holdout13`, không tune RRF/threshold/heuristic trước
khi phép đo này hoàn tất.

**Rollback trigger.** Diff vượt hai file đã freeze; production diff khác một
dòng xóa; focused/full test không xanh; Anthropic vẫn từ chối schema; plan vượt
3 anchor; có KIS failure mới; hoặc KIS `dress25` dưới `0.4000`. Rollback chỉ
hoàn nguyên repair/test này và không resume checkpoint của fingerprint phía kia.

**Estimated risk: low.** Repair một dòng, có Python guard độc lập và rollback
boundary rõ; rủi ro còn lại nằm ở chất lượng/latency multi-anchor chưa đo.

### A2. Q&A mất 196–476 giây mỗi query

**Evidence.** Run 3 đo các Q&A lần lượt khoảng `195.9, 210.6, 360.6, 404.2,
476.2` giây/query; chỉ 4/5 Q&A sinh CSV. Run 1 hoàn tất nhưng 0/5 Q&A sinh CSV.
Khoảng 3,3–7,9 phút cho riêng pipeline đã ăn hết hoặc vượt ngân sách vận hành
một câu trước thời gian đọc, kiểm và nộp.

**Exact failure mode.** Đường Q&A có thể chiếm phần lớn cửa sổ thi, gặp retry
provider rồi không tạo đủ output. Vì export fail-closed khi thiếu query, một Q&A
không hoàn tất có thể chặn toàn bộ ZIP, làm đường production không dùng được vào
ngày mai dù không có exception ở retrieval.

**Minimum action.** Không đổi code hay các knob shot/heuristic trong freeze.
Thực hiện một quyết định vận hành bằng phép chạy Q&A timed trên production path
với `QA_INFERENCE_MODE=legacy`, backend/model cố định và checkpoint/cache được
ghi lại: xác định thứ tự chạy, quỹ thời gian thực tế và điểm cắt trước giờ nộp.
Nếu đường chính không nằm trong quỹ thời gian, dùng `run_minimal.py` đúng vai trò
emergency fallback đã định; không refactor fallback này trước Round 2.

**Verification.** Rehearsal cold-cache và warm/resume phải ghi wall time,
fingerprint, checkpoint/trace và tạo output Q&A đầy đủ qua validator trong quỹ
thời gian đã dành, đồng thời chừa thời gian kiểm và nộp. Không được suy kết quả
từ cache-warm run sang cold run.

**Rollback trigger.** Bất kỳ run đại diện nào vượt quỹ thời gian, timeout/rate
limit, thiếu CSV, sinh partial checkpoint không resume được hoặc làm validator
chặn ZIP. Khi trigger xảy ra, dừng thử thay đổi Q&A và kích hoạt fallback vận
hành; chỉ mở repair mới nếu bằng chứng mới thuộc đúng nhóm crash/format/data
loss/frame mapping/P0.

**Estimated risk: medium.** Hành động tối thiểu không đổi code, nhưng phụ thuộc
provider, trạng thái cache và thời gian thi nên vẫn có biến thiên vận hành lớn.

### A3. Đường submission/release chưa từng được rehearsal thật

**Evidence.** Không có release directory, receipt, checksum, trace production
hay `runtime-fingerprint.json`. Preflight từng xanh và release code có test,
nhưng `--release-rehearsal` chưa chạy thật; promotion gate hiện dừng ở GT
`unknown`. Các run 27/08 là evaluator artefact, không phải bằng chứng tạo gói
nộp production.

**Exact failure mode.** Chưa có bằng chứng runtime rằng môi trường ngày thi đi
trọn chuỗi query → checkpoint/trace → validator → ZIP bằng policy Q&A tường minh.
Lỗi CLI, service, path, cache hoặc artefact chỉ xuất hiện ở lần chạy thật có thể
làm thiếu ZIP hợp lệ hoặc khiến operator phát hiện quá muộn. Đây là gap
end-to-end/submission, không phải claim rằng code release hiện đã sai.

**Minimum action.** Không đổi code và không bypass promotion gate. Chạy một
production submission dry-run trong output directory mới với backend/model cố
định, preflight phù hợp, checkpoint sạch, `--qa-submission-policy robust`,
validator và ZIP. Nếu rehearsal có promotion bị chặn vì GT chưa human-verified,
ghi đúng trạng thái blocked và vẫn kiểm chứng đường export không-promotion; tuyệt
đối không handcraft audit hoặc nâng GT để mở gate.

**Verification.** Tất cả query dự định nộp có output, không status failed/partial;
CSV đúng format; ZIP có top-level `submission/`; validator không có issue; policy
Q&A được ghi tường minh; lưu trace, log, config/fingerprint và SHA-256 của đúng
ZIP đã kiểm. Operator phải mở lại artefact từ đường dẫn cuối, không chỉ staging.

**Rollback trigger.** Preflight không qua; thiếu query/evidence; trace và
checkpoint lệch; validator báo lỗi; ZIP/receipt/checksum thiếu hoặc không khớp;
hoặc output cuối không mở được. Khi trigger xảy ra, không dùng release wrapper
đó trong Round 2; giữ toàn bộ evidence và chuyển sang emergency fallback đã định
thay vì vá thêm kiến trúc trong freeze.

**Estimated risk: low.** Đây chủ yếu là rehearsal/quan sát, không thay đổi hành
vi; rủi ro là chi phí thời gian/provider và phát hiện blocker muộn.

## Bucket B — AFTER ROUND 2, BEFORE 04/09

| Known finding | Concise backlog entry |
|---|---|
| Same fingerprint nhưng kết quả run khác materially | Tách fingerprint cấu hình khỏi replay identity; lưu/cố định provider outputs và chứng minh replay end-to-end trước khi dùng hai run để so promotion. |
| Translation/search-branch degradation không hiện trong trace | Thêm cờ `translation_fallback`, dead branch và lỗi theo từng nguồn vào trace; giữ fallback fail-soft hiện hành. |
| Multi-anchor ghi đè five-source rank trace | Giữ đồng thời rank/contribution theo anchor và theo năm nguồn thay vì thay thế một lớp bằng lớp kia. |
| Runtime failure taxonomy thiếu | Phân loại `timeout`, `rate_limit`, `provider_error`, `invalid_response`, cache/evidence error và retryability theo nguyên nhân thật. |
| KIS deterministic replay coverage thiếu | Thêm replay test hai lần trên input/cache cố định và so plan, ranked results, answers cùng trace; không dùng nó để tune trước Round 2. |
| Dependency lock thiếu | Tạo lock tái lập cho đúng Windows/Python 3.14 và kiểm bootstrap sạch sau Round 2. |
| Secondary execution paths | Inventory, document và kiểm parity các path phụ; chỉ hợp nhất khi có bằng chứng, không refactor trong freeze. |
| TRAKE thiếu multi-anchor event/video selection mà PLAN yêu cầu | Thiết kế và đo riêng sau Round 2; không mượn kết quả KIS hoặc tune RRF trước khi có baseline TRAKE phù hợp. |
| `run_minimal.py` cố ý còn pre-PLAN | Giữ nguyên như emergency fallback; sau Round 2 thêm smoke/format test và tài liệu rõ capability gap, chỉ sửa nếu chứng minh nó hỏng. |
| `batch1_holdout13` bị contaminated | Hạ vai trò xuống development/regression descriptive; không coi là unbiased holdout và không dùng hai lượt còn lại để tuning. Dựng evaluation set sạch mới sau Round 2. |
| GT chưa verified | Tiếp tục `unknown` cho tới khi có human provenance thật; tổ chức quy trình verify sau Round 2, không suy đoán hay nâng trạng thái bằng code. |
| Provider integration test gap | Thêm live contract smoke có kiểm soát cho schema/retry của từng provider sau Round 2. Live smoke của A1 chỉ là verification repair, không thay thế backlog integration lâu dài. |

## Ranh giới quyết định

- A có đúng ba mục trên; 12 finding còn lại thuộc B, mỗi finding chỉ xuất hiện
  trong một bucket.
- Không đề xuất tune RRF, threshold, anchor heuristic, temporal bonus hoặc slot
  trước khi multi-anchor chạy thật và có query-level measurement.
- Không dùng hai lượt holdout còn lại cho tuning; không diễn giải
  `batch1_holdout13` như holdout không thiên vị.
- Không coi ngưỡng `0.82` là score; không thay đổi GT verified nếu thiếu human
  provenance; không revert `backend/llm/adapter.py`.
- `run_minimal.py` tiếp tục là fallback khẩn cấp trừ khi một smoke cụ thể chứng
  minh nó hỏng.

