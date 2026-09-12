# Review H02

Review độc lập read-only bởi agent `h02_review`, theo skill requesting-code-review đang khả dụng lúc dispatch. Không gọi provider, không sửa file, không đổi HEAD. Root cũng đọc toàn bộ diff và chạy `git diff --check` (exit0).

| Finding | Sửa | Kiểm |
|---|---|---|
| Mọi attempt lỗi bị hạ thành needs_review | All-attempt-error ném task failure, giữ qa_review | `test_all_attempt_errors_are_task_failure_with_candidates` |
| Minimal giữ supplied answer khi inference unsupported | `_solve_qa` dùng runner chung và append trace, không dùng q.answer thay output | `test_minimal_does_not_reuse_supplied_answer` |
| Bỏ explicit manual provenance ở Answer | Aggregate answer/hypothesis/manual marker | `test_manual_answer_provenance_overrides_autonomous_hypothesis` |
| Mất operator origin sau answers chuyển review_answers | Đọc provenance của review_answers ở mọi roundtrip | assertion reconcile roundtrip; reviewer repro xác nhận |
| Review chỉ có text chuyển thành abstain lần hai | `has_review` tính review_answer_text | roundtrip trong cùng test |
| API lỗi vứt candidate/evidence | HTTP503 có task_failure/process_status/qa_trace | `test_api_task_failure_retains_review_payload` |
| Autonomous exporter chỉ bind text | Bind video/frame/keyframe/provenance/hash + surface form được phép | 5 trường thay đổi độc lập trong `test_autonomous_export_binds_full_evidence_row`; reviewer repro cuối xác nhận blocked, control sạch |

Reviewer đã xác nhận finding cuối đóng; không còn finding quan trọng chưa xử lý trong phạm vi review. Shared import không kéo QA/LLM/DB/torch được kiểm bằng Python subprocess.

Giới hạn: review/test là correctness offline, không xác nhận answer đúng về ngữ nghĩa. Release gate vẫn kiểm frame map/cache/evidence identity độc lập.
