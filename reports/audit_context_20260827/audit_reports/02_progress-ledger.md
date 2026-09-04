# SDD ledger — plan: docs/plans/2026-08-24-batch1-accuracy-uplift.md

## Preflight

- Branch: `codex/batch1-accuracy-uplift`; triển khai tại workspace duy nhất
  `C:\dev\aic2026` theo AGENTS.md và yêu cầu giữ dirty worktree.
- Baseline commit: `b8090cd`.
- Spec authority: `docs/product-spec.md` sau Task 1; trước đó plan đã duyệt là
  nguồn yêu cầu.

| Task A | Task B | Interface/file dùng chung | Kết quả quét |
|---|---|---|---|
| 1 | 2 | GT schema và evaluator | Task 2 phải giữ metadata/gate Task 1, không tự coi legacy GT là verified. |
| 2 | 3 | `QueryRun.query_plan` và `solve_query()` | Task 2 tạo contract mở; Task 3 điền plan/rank trace, không đổi CLI. |
| 2 | 4 | `QueryRun.qa_hypotheses` và lỗi phân loại | Task 2 tạo contract; Task 4 điền hypothesis/evidence, không trả sentinel. |
| 2 | 5 | trace/fingerprint/release artefact | Task 5 kiểm và đóng gói contract đã có, không tạo đường chạy thứ hai. |
| 3 | 4 | search candidate pool | Q&A tiếp tục dùng retrieval hiện có; không bắt buộc generic KIS multi-anchor cho route Q&A. |
| 3 | 5 | config snapshot/gate | Các hằng multi-anchor phải nằm trong config và xuất hiện trong snapshot. |
| 4 | 5 | evidence/portfolio/export | Batch thiếu hypothesis hợp lệ phải chặn ZIP, không đệm answer giả. |

- Task 1 tự nhất quán: tài liệu không cần test; schema/gate phải TDD.
- Task 2 tự nhất quán: refactor giữ output, parity test phải đỏ trước refactor.
- Task 3 tự nhất quán: multi-anchor không sửa vector encoder/index.
- Task 4 tự nhất quán: hypothesis là candidate-specific; phần đuôi chỉ dùng
  answer có evidence, không dùng sentinel.
- Task 5 tự nhất quán: gate số chỉ chạy khi GT verified; không thể chứng minh
  0.82 bằng nhãn unknown.

Ruling: Không tạo linked worktree — AGENTS.md quy định workspace duy nhất và kế
hoạch yêu cầu bảo toàn dirty worktree trên branch mới — nếu quyết định này sai,
thay đổi Codex và Claude có thể khó tách hơn nhưng vẫn truy được bằng path/diff.

Ruling: Đóng băng query nhưng giữ ground truth chưa xác minh là `unknown` — không
bịa nhãn để đạt gate — nếu quyết định này sai, chưa thể báo điểm holdout cho tới
khi Thạch hoàn tất label ledger.

Task 1: fix round 1/5 (phần batch uplift trong product spec được khôi phục; commit `f5bb02b`).
Task 1: fix round 2/5 (số 6,8/8,6 được đánh dấu external/unreproduced; commit `3af0dd4`).
Task 1: complete (commits `b8090cd..3af0dd4`, review clean).

Task 2: minor (deferred): `run.py` early-return khi `--only` có ID lạ không đóng
`Log`; final review quyết định có cần sửa trước merge.
Task 2: fix round 1/5 (3 finding fingerprint/JSON-safe/env restore addressed;
commit `8042414`).
Task 2: complete (commits `3af0dd4..8042414`, review clean; 1 minor deferred).

Task 3: fix round 1–4 (fail-closed fidelity/schema, relation-preserving
count/color guards và chronology theo anchor span; commits
`3f50bfe`, `f9dcacb`, `41609d0`, `7dcd8db`).
Task 3: complete (commits `8042414..7dcd8db`, review APPROVED; focused
`53 passed`, full suite gần nhất trước fix rounds `702 passed, 1 skipped`, CLIP
guard 10/10 avg `0.9999`, min `0.9993`; full suite sẽ chạy lại ở Task 5).

Task 4: fix round 1/5 (7 findings về candidate budget, evidence cohort,
fingerprint, full-query cache, single-flight, synthetic digest và sentinel đã
addressed; commit `0853535`).
Task 4: complete (commits `7dcd8db..0853535`, review APPROVED; focused reviewer
`144 passed`, full suite implementer `766 passed, 1 skipped`).

Task 5: fix round 1/5 (7 findings về frozen-set/GT provenance, runtime/scorer
binding, query-specific cache, trace snapshot, lỗi input CLI, post-write test và
whitespace đã addressed; commit `9b107cd`).
Task 5: complete (commits `0853535..9b107cd`, review APPROVED; focused reviewer
`40 passed`, full suite implementer `805 passed, 1 skipped`; gate thật `BLOCKED`
vì đủ 38 nhãn vẫn `unknown`, không dùng Public và không gọi retrieval).

Final integration: fix round 1/5 (frozen evaluator producer, canonical
submission↔trace, detector cache, atomic ZIP transaction, canonical scorer
digest và đóng Log đã addressed; commit `c443903`).
Final integration: complete (review `b8090cd..c443903` APPROVED, không còn P0–P2;
focused reviewer `129 passed`; controller full suite `813 passed, 1 skipped`,
preflight development/release đều `17 đạt, 0 hỏng, 2 bỏ qua`, CLIP 10/10 avg
`0.9999`, min `0.9993`).
