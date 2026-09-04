# Integration fix report

## Phạm vi

Đã xử lý toàn bộ finding của `final-review.md`, không sửa `README.md` hay
`backend/llm/adapter.py`, không stage/commit và không đổi provider/model.

## RED đã tái lập trước khi sửa

- Submission giữ đúng query ID/task nhưng đổi video/frame/answer vẫn tới ZIP writer.
- ZIP writer lỗi ghi đè `submission.zip` tốt cũ và để file hỏng lại.
- `visual_count` trả detector answer nhưng không có cache record.
- `run.py --only <id-lạ>` trả về khi `Log.f` còn mở.
- Chưa có scorer-contract digest bao phủ dependency.
- Evaluator không nhận `--manifest/--ground-truth/--out`, nên không thể tạo score
  artefact của frozen 13/25 cho promotion gate.
- Atomic replace lỗi lúc backup có thể xóa ZIP/receipt tốt cũ.

## Thay đổi

- `run_evaluation` nhận frozen manifest + GT JSONL, kiểm exact query-set digest,
  per-query content hash (khi manifest khai), task, verified metadata và GT hash
  trước khi kết nối DB; legacy `--split` giữ nguyên. Score artefact sinh ra có
  provenance mà `assess_promotion()` nhận trực tiếp.
- Thêm scorer digest canonical bao phủ `scoring.py`, `answer_match.py` và
  `qa_evaluation.py`; evaluator/release dùng chung, runner fingerprint cũng bao
  phủ `answer_match.py`.
- `visual_count` ghi/replay cache detector với query/full-query/evidence/runtime,
  config snapshot và provenance; không gọi provider.
- Release canonical-compare toàn bộ rows với latest trace; Q&A chỉ chấp nhận đúng
  transform deterministic của policy.
- ZIP/config/receipt ghi staging; ZIP chỉ thay tên cuối sau hậu kiểm. Transaction
  backup/rollback giữ release tốt cũ khi writer, validator hay replace lỗi.
- Nhánh `--only` ID lạ đóng log trước khi trả exit 2.

## Verification

```text
Focused integration: 134 passed
Full suite: 813 passed, 1 skipped, 2 dependency deprecation warnings
py_compile: exit 0
git diff --check (chỉ file phạm vi): exit 0
```

Actual promotion trên manifest repo hiện tại vẫn fail-closed:

```text
status=BLOCKED, eligible=false, metrics={}
reason=ground_truth_unverified (đủ 13 + 25 query unknown)
exit=1
```

Evaluator frozen promotion hiện tại cũng dừng trước DB vì manifest chưa có
`ground_truth_sha256` verified; không tạo output directory.
