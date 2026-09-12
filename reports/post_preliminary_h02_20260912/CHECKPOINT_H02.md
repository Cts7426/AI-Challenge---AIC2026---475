# CHECKPOINT H02 — QA result contract, offline/replay

Ngày 2026-09-12. Đề nghị **PROMOTE H02 CORRECTNESS** trong phạm vi sửa hợp đồng kết quả QA. Không phải promotion chất lượng truy xuất hoặc đáp án. Selfcheck vẫn exit 1 do hai gap GT đã được người dùng cho phép ghi nhận.

## A. Authorization/scope

Theo [resume_authorization.txt](resume_authorization.txt) và [approval.txt](approval.txt): tiếp tục WIP H02 hiện có; chỉ offline/replay correctness. H01 infrastructure APPROVED, performance baseline NOT PROMOTED. Không gọi API trả phí, đổi provider/model, chạy H03/H04/H05, tạo report v2 hoặc sửa kế hoạch validation/held-out. Không reset/revert/checkout hay viết lại lịch sử.

## B. Starting source state

Branch `wip/codex-h01-20260912`; base HEAD `235414784b5ee80b9552fd7fe7ce898db1cbf35b`, tree `55a354bcc82e603dbcb0806a0b757bac9658ab13`. Đây là mixed WIP commit, không gán toàn bộ cho H01/H02. Trạng thái tiếp nhận và việc đã làm được giữ trong [WORK_LEDGER.md](WORK_LEDGER.md), [starting_git_status.txt](starting_git_status.txt).

Commit source H02 riêng: **`4fe4f2e0447a4946734adb04a59159b823e76271`**, tree `ec28fb9e7634bace2e1892054c844510f680cdbd`; đúng 25 file source/test đã kiểm hash và staged paths. WIP H01 và `reports/context_handoff_20260912/` được giữ nguyên ngoài commit.

## C. H01 change ledger reference

[H01_SOURCE_LEDGER.md](H01_SOURCE_LEDGER.md), [H01_change_ledger.json](H01_change_ledger.json), [H01_exact_changes.patch](H01_exact_changes.patch) phân định 15 file production/test/config H01 với toàn bộ mixed history. H01 cache-only có 30 query khóa, 5 exportable, 25 blocked, 132 cache misses, 0 hits và 0 provider calls: chỉ nhận hạ tầng, không nhận performance baseline. Trạng thái process `success` trong replay H02 không thay thế export/cache gate H01.

## D. H02 file/change ledger

[H02_SOURCE_LEDGER.md](H02_SOURCE_LEDGER.md) và [H02_change_ledger.json](H02_change_ledger.json) ghi đủ 25 file source/test, hash trước/sau, 10 report tools và các thay đổi ngoài phạm vi. [H02_exact_changes.patch](H02_exact_changes.patch) đã qua `git apply --reverse --check` chỉ đọc; [H02_source_snapshot.zip](H02_source_snapshot.zip) chứa đúng source, không credential/data/cache. Snapshot SHA-256: `1257e62170a967adbeab2de2ee90df223f237dcf725c35fea86c888a70b48048`.

Nhóm thay đổi: contract/config chung; QA/portfolio/runner; API; exporter/variants/rehearsal; run/minimal/checkpoint; evaluator/promotion/baseline harness; manual provenance; preflight và tests. Không đổi retrieval weight, model, vector, mapping, GT hoặc dữ liệu thi.

## E. RED evidence summary

[RED.log](RED.log) gốc giữ nguyên: 17 failed trước implementation. Bốn positive/replay controls thất bại vì shared module chưa tồn tại, không chứng minh code cũ từ chối zero/negative. Exporter assertion ban đầu dùng nhầm `Issue.code`; sau implementation mới lộ lỗi fixture và sửa thành `Issue.rule`. [GREEN_initial.log](GREEN_initial.log), các log focused/full trung gian vẫn được giữ để truy vết; không tạo lại RED. Chi tiết giới hạn: [DELIVERY_NOTES.md](DELIVERY_NOTES.md).

## F. Shared contract design

`backend/common/qa_contract.py` phụ thuộc thư viện chuẩn và config; không import QA/retrieval/LLM/DB/torch. Predicate kiểm text, provenance và cấu trúc evidence được dùng chung. Test subprocess xác nhận dependency nhẹ.

Các chiều độc lập: `process_status`, `status`/`result_state`, `output_origin`, `autonomous_eligible`. `supported_answer` là đủ hợp đồng cấu trúc, không xác nhận đúng GT. `needs_review` giữ candidate/evidence/answer cũ cùng lý do; `abstain` biểu diễn không có output được hỗ trợ; `task_failure` giữ lỗi thực thi và phần evidence đã có. Nếu mọi inference attempt lỗi, không biến lỗi thành review thông thường.

Chỉ provenance rõ ràng mới tạo `autonomous` hoặc `operator_assisted`; thiếu/không rõ giữ `unknown`. Đọc cả answer, hypothesis, review payload và marker manual tường minh; reconcile không làm mất origin khi resume nhiều lần. QA không còn tạo TODO hoặc zero giả để hoàn thành. Zero và câu phủ định có evidence hợp lệ vẫn được giữ.

## G. Legacy-test-change audit

[LEGACY_TEST_AUDIT.md](LEGACY_TEST_AUDIT.md), [legacy_test_change_audit.json](legacy_test_change_audit.json): 27 mục, từng tên test/fixture liên đới có kỳ vọng cũ, lý do, kỳ vọng mới và cơ sở không làm yếu kiểm thử.

- A: TODO-success và thiếu evidence nay thành review; contract cũ được thay có chủ đích.
- B: fixture success bổ sung evidence/provenance; budget 42 và các assertion về durability/export giữ nguyên. Test durability độc lập dùng hai KIS để không giả QA success rỗng.
- C: manual override giữ hành vi hiện có và thêm assertion operator provenance.

## H. Replay input manifest

[replay_input_manifest.json](replay_input_manifest.json) khóa **129 records và 66 CSV**, SHA-256 **`c26b2dad1ec13e4d1b740f535de35afa7ac68f68365c646cc27663232533ce03`**. Giữ toàn bộ record, kể cả retry/failure; không chọn lại mẫu sau kết quả. Hash nguồn được kiểm trước/sau replay. Kết quả cuối nằm riêng ở [replay_final](replay_final/replay_summary.json); output replay trước đó vẫn giữ.

## I. Replay transition results

[replay_final/replay_summary.json](replay_final/replay_summary.json) và [replay_final/replay_query_changes.json](replay_final/replay_query_changes.json) ghi theo source/query: status, answer/provenance cũ, state/origin mới, lý do và payload được giữ.

| Nguồn | QA mode (record) | Transition toàn bộ record |
|---|---|---|
| H01_CACHE_ONLY | legacy 5 | success → success 25; success → needs_review 5 |
| TUNE_LEGACY | unknown 5 | legacy_implicit_success giữ nguyên 25; → needs_review 5 |
| ROUND2_OPERATOR_HISTORY | legacy 8, unknown 4 | success → success 29; → needs_review 1; failed → failed 3 |
| ROUND3_OPERATOR_HISTORY | legacy 8 | success → success 33; → needs_review 3 |

Trong riêng 30 QA records: **13 supported autonomous**, **14 needs_review**, **3 failed giữ nguyên**; 0 abstain trong corpus này. Chín explicit success và năm legacy implicit success chuyển review. Origin QA: autonomous 13, operator_assisted 1, unknown 16; tất cả giữ attribution gốc, không suy từ tên thư mục hay đáp án. Record operator rõ ràng vẫn operator_assisted, nhưng thiếu cấu trúc evidence nên cần review. UNKNOWN không đổi thành autonomous/operator.

Có **800 hàng answer placeholder đã đăng ký, 0 còn được nhận làm autonomous output**. Tổng QA answer rows 2.700 → 1.300; 1.400 hàng chuyển review gồm 800 placeholder và 600 thiếu provenance/evidence cấu trúc. Không gọi 600 hàng này là đáp án sai. Giữ payload **14/14** record review; answer còn được hỗ trợ không bị sửa. Mapping violations trước/sau đều 0; replay crashes 0. CSV audit riêng phát hiện 300 hàng TODO trong 3/66 CSV sẽ bị text gate chặn; không sửa CSV gốc. CSV không có provenance nên không suy zero là placeholder.

## J. Unique-query vs record denominators

| Nguồn | Records | Unique query IDs | KIS / QA / TRAKE records |
|---|---:|---:|---|
| H01_CACHE_ONLY | 30 | 30 | 23 / 5 / 2 |
| TUNE_LEGACY | 30 | 30 | 23 / 5 / 2 |
| ROUND2_OPERATOR_HISTORY | 33 | 30 | 19 / 12 / 2 |
| ROUND3_OPERATOR_HISTORY | 36 | 36 | 26 / 8 / 2 |
| Tổng union | **129** | **80** | **91 / 30 / 8** |

Unique task/query pairs = 80; unique KIS/QA/TRAKE = 54/21/5. **14 review records tương ứng 9 unique query IDs**. Không cộng unique từng nguồn thành unique toàn bộ; 66 CSV là mẫu artifact riêng, không cộng vào 129 records. Transition là phân loại hợp đồng, không phải đo accuracy.

## K. False-rejection audit

[false_rejection_audit.json](false_rejection_audit.json): 9 valid fixtures được nhận, 24 unsupported fixtures bị chặn; **false rejection 0, false accept 0**. Có zero visual count, phủ định hợp lệ, câu chứa từ gần sentinel nhưng có nghĩa khác, answer có evidence và manual zero trong policy assisted. Unsupported gồm refusal/sentinel cũ, TODO/placeholder provenance, zero giả, thiếu evidence và origin unknown cho autonomous policy. Đây là fixture controls, không tự đánh dấu ground truth verified.

## L. Provider-call audit

[offline_guard/sitecustomize.py](offline_guard/sitecustomize.py) chặn external DNS/socket dispatch trước khi gửi; phát sinh attempt sẽ fail run và ghi audit. Loopback chỉ dành cho service local. [run_check.py](run_check.py) áp guard, cache-only và chế độ model đã chọn `api/claude-sonnet-5`; không đổi provider/model thay thế. Unit inference/provider dùng mocks, không có egress thực.

Các command JSON của focused/full/preflight/selfcheck/replay/false-rejection/packaging đều ghi **external_dispatch_attempts = 0, external_provider_calls_completed = 0**. **Provider calls = 0**. Không gọi API để kiểm key/credit, không lưu giá trị secret. `LLM_API_MODEL` là model; không dùng tên model làm API key.

## M. Focused tests

[focused_gate_command.json](focused_gate_command.json), [focused_gate.log](focused_gate.log): **239 passed**, 1 warning, exit 0. H02 contract + affected QA/hypotheses/runner/run/rehearsal/API/baseline/manual/frozen evaluator.

Coverage có test cụ thể trong `tests/test_h02_contract.py`: legacy/two-stage cached và mocked inference; missing/empty evidence; runner failure/review; API review và HTTP503 giữ payload; stale checkpoint/harness/evaluator resume; portfolio/all policies; release gate/preflight; minimal; batch unsupported QA vẫn chạy query tiếp; origin roundtrip; exporter bind toàn bộ video/frame/keyframe/provenance/hash/answer thay vì chỉ so text. Test dependency-light chạy subprocess. Review độc lập và việc đóng finding: [REVIEW_H02.md](REVIEW_H02.md).

Sau kiểm đóng gói chỉ bỏ dòng trắng cuối file contract: [packaging_contract.log](packaging_contract.log) **53 passed**, exit 0; không thay đổi ngữ nghĩa. `git diff --cached --check` và patch reverse-check exit 0 trước commit.

## N. Full suite

[full_gate_command.json](full_gate_command.json), [full_gate.log](full_gate.log): **981 passed, 1 skipped, 2 warnings**, exit 0. Không còn regression chưa giải thích; các lỗi fixture trung gian và cách xử lý giữ trong legacy audit/log. Warning deprecation từ Starlette/httpx và google-genai, không phải provider call.

Lệnh lặp lại có guard từ gốc repo, dùng tên log mới để giữ log cũ:

```powershell
.venv\Scripts\python.exe reports/post_preliminary_h02_20260912/run_check.py verify_full -m pytest tests dev_set/tests -q
.venv\Scripts\python.exe reports/post_preliminary_h02_20260912/run_check.py verify_contract -m pytest tests/test_h02_contract.py -q
```

## O. Development/release preflight

[preflight_development_command.json](preflight_development_command.json) và [preflight_release_command.json](preflight_release_command.json), kèm log cùng stem: cả hai **20 đạt / 0 hỏng / 2 bỏ qua**, exit 0. Hai skip là Streamlit debug UI chưa cài và API health khi local API server không chạy; không phải lỗi mới H02. Preflight mới kiểm shared QA contract offline; model chỉ được in, không probe provider.

```powershell
.venv\Scripts\python.exe reports/post_preliminary_h02_20260912/run_check.py verify_development scripts/preflight_check.py --profile development
.venv\Scripts\python.exe reports/post_preliminary_h02_20260912/run_check.py verify_release scripts/preflight_check.py --profile release
```

## P. Selfcheck

[selfcheck_command.json](selfcheck_command.json), [selfcheck.log](selfcheck.log): **exit 1**, không tuyên bố hệ thống đã hoàn tất mọi gate. Bên trong selfcheck: suite 981 passed/1 skipped; preflight 20/0/2; LLM config đạt. Hai mục thiếu duy nhất: holdout **6/13 verified**, round1 **0/25 có GT**. Đây là gap người dùng cho phép ghi nhận trong H02, không sửa GT để lấy xanh.

```powershell
.venv\Scripts\python.exe reports/post_preliminary_h02_20260912/run_check.py verify_selfcheck scripts/selfcheck.py
```

## Q. Remaining gaps

GT cần người xác minh: holdout KIS_004, KIS_005, KIS_009, KIS_010, QA_011, QA_012, QA_013; round1 chưa có GT 25 câu. H02 không khẳng định đáp án đúng bằng contract structural. Historical trace thiếu provenance vẫn cần review; không bổ sung attribution suy đoán. Live-provider correctness và performance chưa đo vì API không được phép. Two-stage chỉ có coverage offline, chưa promotion làm release inference mode. Không thay policy/retrieval config ngoài H02.

## R. Semantic behavior changes

Process hoàn tất có thể trả needs_review/abstain thay vì success; lỗi thực thi vẫn failure. Batch giữ record và candidate/evidence, tiếp tục query khác, nhưng unsupported QA không tạo checkpoint thành công hoặc ZIP trông như thành công toàn bộ.

Autonomous evaluator/harness/exporter yêu cầu supported contract và explicit autonomous origin. Exporter còn bind từng hàng vào đúng evidence tuple; placeholder/refusal/unsupported/review không thành submission hợp lệ. Assisted/manual workflow có thể giữ dữ liệu và xuất theo policy cho phép với explicit provenance, nhưng không được tính autonomous success. Format validator mặc định không thay thế autonomous policy. Supported zero/negative giữ nguyên; lịch sử thi không bị tái ghi.

## S. Historical artifacts integrity statement

[historical_evidence_integrity.json](historical_evidence_integrity.json): **3.884 file** trong manifest evidence trước H02 đã kiểm, `changed_or_missing = []`. Hash tất cả replay sources và 66 CSV khớp lock trước/sau; manifest lock giữ nguyên SHA ở H. Không ghi checkpoint/cache/CSV/ZIP lịch sử, không đổi GT manifests. Output replay và annotations chỉ nằm ở thư mục H02. WIP khác được giữ, không đưa vào source commit.

## T. Decision

**PROMOTE H02 CORRECTNESS — đề nghị nhận thay đổi hợp đồng QA**, với gap GT ở P/Q được ghi rõ. Các gate correctness đã đạt: placeholder/refusal bị chặn; stale data revalidated; zero/negative có evidence được nhận; review payload và provenance giữ qua lỗi/resume; batch isolation; autonomous export gate; focused/full/preflight đạt; provider 0; lịch sử và denominator nguyên vẹn; false rejection 0 trong fixture audit.

Không suy ra accuracy/recall/điểm thi/latency tốt hơn. H01 performance baseline vẫn NOT PROMOTED. **Dừng tại checkpoint H02 để người vận hành review; không bắt đầu H03.**
