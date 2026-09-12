# H02 work ledger — tiếp tục WIP, 2026-09-12

Authorization mới: attachment `32882d54-2873-44e7-b0b6-5ac60f6cea4a/pasted-text.txt`; ưu tiên hơn wording cũ trong context handoff. H01 infrastructure approved, performance baseline chưa promoted. H02 offline/replay được phép; API/H03–H05 không được phép.

Đã kiểm branch `wip/codex-h01-20260912`, HEAD `235414784b5ee80b9552fd7fe7ce898db1cbf35b`, status và diff H02 hiện hành. Không reset/checkout/revert hoặc rewrite. Đã đọc PLAN, shared contract, test H02, script freeze/replay và kết quả đã có. H01 ledger 15 file đã lưu riêng. Folder `reports/context_handoff_20260912` và mọi thay đổi H01/report ngoài H02 thuộc WIP khác, không đưa vào commit H02.

Đã có trước yêu cầu resume mới:

- RED gốc 17 ca thất bại, không tạo lại; 4 positive controls thất bại vì shared module chưa tồn tại, không phải bằng chứng code cũ từ chối zero/negative.
- Shared predicate, runner states, pipeline bỏ TODO fallback, candidate/evidence preservation, cache/resume, policy/export/release gates và API.
- Focused gần nhất 192 passed; full trước đó 4 failed / 941 passed / 1 skipped. Các lỗi đã sửa nhưng chưa chạy full mới.
- Replay input giữ nguyên 129 records / 66 CSV; manifest SHA-256 `c26b2dad1ec13e4d1b740f535de35afa7ac68f68365c646cc27663232533ce03`.
- Replay sơ bộ 14 record hạ review, không ghi lịch sử. Chưa là kết quả cuối vì attribution unknown chưa đủ chặt.
- Guard evidence rỗng vừa thêm, chưa được xác minh lại full.

Còn phải làm:

1. Sửa attribution explicit operator/autonomous/unknown; kiểm roundtrip và không đếm assisted/unknown thành autonomous.
2. Kiểm hard guard toàn bộ test/replay; bổ sung còn thiếu ở preflight, empty evidence, dependency-light, route minimal nếu cần.
3. Audit từng legacy test thay đổi; sửa hồi quy fixture bằng bằng chứng, không giảm assertion để lấy xanh.
4. Hoàn thiện replay record/unique-query/task/source/mode denominators, old provenance + reason, false rejection audit; không đổi manifest.
5. Focused → affected → full → dev preflight → release preflight → selfcheck; lưu command/exit và review diff.
6. H02 exact file/hash/patch/snapshot, clean scoped commit nếu an toàn; CHECKPOINT_H02.md mục A–T rồi dừng.

## Trạng thái chốt sau resume

Đã thực hiện đủ mục 1–6 ở trên. Audit legacy 27 mục, review độc lập không còn finding quan trọng. Focused 239 passed; full 981 passed/1 skipped; dev/release preflight 20/0/2; selfcheck exit 1 chỉ hai gap GT được phép. Replay cuối 129 records/80 unique IDs/66 CSV, 14 review records/9 IDs, payload giữ 14/14; false rejection 0; external dispatch/provider 0. Integrity 3.884 historical files không thay đổi.

Kiểm đóng gói sửa script snapshot để không lặp new-file patch sau stage; bỏ dòng trắng EOF trong contract, chạy lại 53 contract tests đều đạt. Hash source/snapshot được cập nhật và patch reverse-check đạt. Source commit sạch 25 file: `4fe4f2e0447a4946734adb04a59159b823e76271`. Không stage WIP khác. [CHECKPOINT_H02.md](CHECKPOINT_H02.md) chứa A–T và quyết định đề nghị PROMOTE H02 CORRECTNESS, giữ gap GT. Dừng tại H02.
