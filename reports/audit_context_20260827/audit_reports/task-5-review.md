# Review Task 5 — commit `00a6c08`

## Kết luận

**CHANGES REQUESTED.** Promotion/release gate đã fail-closed đúng ở nhiều nhánh
cơ bản, nhưng còn hai lỗ hổng provenance P1 cho phép một audit hợp lệ được tạo
từ score không gắn GT verified/frozen hoặc được tái dùng cho runtime release khác.

## Findings

### [P1] Score artefact chưa được ràng buộc với GT verified và đúng frozen set

- `dev_set/tools/run_evaluation.py:642-651`
- `dev_set/tools/promotion_gate.py:87-107`
- `dev_set/tools/promotion_gate.py:110-164`
- `dev_set/tests/test_promotion_gate.py:39-66`

Evaluator chỉ thêm chuỗi `scorer_contract`; `scores.json` không ghi run có chạy
`--promotion`, trạng thái GT verified, hash GT/query input hay hash manifest được
gate. Sau đó promotion gate kiểm provenance trên **một manifest độc lập**, còn
score chỉ cần trùng ID/task với chính manifest đó. `_validate_manifest_identity()`
chỉ kiểm `manifest_id`, số lượng và uniqueness; không khóa danh sách ID frozen.
Test ELIGIBLE hiện còn dùng regression giả `R01..R25`, chứng minh gate không buộc
25 ID thật trong `batch1_round1_queries`.

Hậu quả: score sinh từ run legacy không có `--promotion`/GT unknown, hoặc một bộ
13/25 câu khác nhưng tự khai cùng `manifest_id`, vẫn có thể được ghép với manifest
đánh dấu verified và trở thành ELIGIBLE. Đây là vi phạm trực tiếp yêu cầu
“scorer chính thức chỉ nhận nhãn verified” và frozen holdout/regression.

Cần đưa provenance vào score artefact (ít nhất promotion-ready, hash query/GT
input, scorer policy/contract) và buộc gate so các hash đó với manifest frozen;
đồng thời khóa exact ID/content của hai tập thay vì chỉ tin `manifest_id` tự khai.

### [P1] Audit ELIGIBLE không được ghim vào runtime/scorer policy của batch release

- `dev_set/tools/promotion_gate.py:287-292`
- `dev_set/tools/promotion_gate.py:367-374`
- `backend/export/release_rehearsal.py:68-101`
- `backend/export/release_rehearsal.py:430-438`
- `run.py:408-420`

Gate có so fingerprint của holdout với regression-current nhưng bỏ giá trị đó
khỏi `PromotionGateResult`/audit. `promotion_audit_is_valid()` không yêu cầu
runtime hay scorer policy, còn `create_release_package()` chỉ kiểm các trace đồng
nhất với nhau, không so fingerprint batch với runtime đã được promotion. Tương
tự, `--scorer-policy` trong `run.py` là giá trị người chạy tự khai và không có
liên kết với score/audit (trong khi top-level `final` của evaluator hiện là
semantic).

Vì vậy một audit đạt ở model/config/source A có thể mở khóa ZIP của batch chạy ở
B; receipt vẫn trông hợp lệ. Audit cần mang `current_runtime_fingerprint` và
`scorer_policy`, checksum phải bao phủ chúng, release phải so bằng với batch và
ghi đúng các giá trị đã bind vào receipt.

### [P2] Evidence cache release chưa chứng minh inference thuộc đúng query

- `backend/export/release_rehearsal.py:248-256`
- `backend/export/release_rehearsal.py:297-306`

Manifest đã trích `query_sha256`/`full_query_sha256`, nhưng gate chỉ match
`evidence_digest + runtime_fingerprint`. Cache directory là global và runtime
fingerprint không chứa nội dung query, nên cache còn sót của câu hỏi khác trên
cùng evidence có thể làm query hiện tại pass dù cache inference của nó đã mất.
Điều này làm receipt không đủ replay đúng answer. Cần match thêm query identity
(và cache kind/prompt/config nếu cần) với query/trace tương ứng, đồng thời test
case hai câu khác nhau dùng cùng evidence.

### [P2] Trace được gate và trace được hash vào receipt có thể là hai dữ liệu khác nhau

- `backend/export/release_rehearsal.py:171-198`
- `backend/export/release_rehearsal.py:430-436`
- `backend/export/release_rehearsal.py:498-501`

`assess_release_batch()` kiểm sequence `traces` trong RAM nhưng chỉ kiểm
`trace_path.is_file()`. Receipt sau đó băm file ở `trace_path` mà không chứng minh
nội dung file chính là sequence đã gate. Caller có thể truyền trace sạch trong
RAM và file rỗng/stale; thậm chí test hiện có từng dùng file `{}\n` với `_traces()`
khác. Đường `run.py` hiện load từ cùng path nên giảm khả năng xảy ra, nhưng
contract của primitive release và receipt vẫn fail-open trước thay đổi/race.
Cần load/gate/hash cùng một byte snapshot (hoặc so canonical records/hash trước
writer).

### [P2] CLI input-read error không tạo audit BLOCKED như contract

- `dev_set/tools/promotion_gate.py:409-430`

Lỗi đọc JSON được catch thành `input_read_error`, nhưng ngay sau đó
`_input_sha256()` lại đọc chính path thiếu ngoài `try` và ném
`FileNotFoundError`. Lệnh kiểm chứng với `--holdout-manifest ...does-not-exist.json`
trả traceback thay vì JSON `BLOCKED`. Cần hash fail-closed (`missing`/read-error
được ghi rõ) hoặc gom load+hash trong cùng error handling, rồi thêm test CLI.

### [P2] Test hậu kiểm writer không đi tới writer

- `tests/test_release_rehearsal.py:227-250`

Test tên `test_writer_tra_ve_validator_failure...` ghi cache file
`{"entries":[{"path":"x"}]}` nhưng truyền `_cache_manifest()` khác nội dung.
`create_release_package()` dừng ở `cache_manifest_mismatch` trước khi gọi
`bad_writer`, nên test không khóa hành vi “writer trả post-write issues thì không
có receipt”. Hãy dùng cùng cache manifest và assert writer được gọi đúng một lần.

### [P3] Diff còn whitespace lỗi

- `data/config/release_gate.py:22`

`git diff --check 0853535 00a6c08` báo `new blank line at EOF`.

## Verification đã chạy

```text
29 passed in 1.13s
```

Lệnh focused gồm `dev_set/tests/test_promotion_gate.py`,
`tests/test_release_rehearsal.py` và hai integration test rehearsal trong
`tests/test_run.py`.

Gate thật trên manifest hiện tại trả exit 1, `status=BLOCKED`, `eligible=false`,
`metrics={}`, `public_score_used=false` và liệt kê đủ 38 query chưa verified;
điểm này đúng yêu cầu và không gọi retrieval.

`git diff --check` không sạch do finding P3. Ngoài ra, lệnh CLI với manifest
không tồn tại tái lập finding input-read error bằng traceback `FileNotFoundError`.

---

## Re-review fix commit `9b107cd`

**APPROVED.** Không còn finding P1/P2 trực tiếp trong phạm vi Task 5.

Bảy finding trước đã được xử lý:

1. Gate khóa exact ID và content hash của 13 holdout/25 regression; score artefact
   bắt buộc `promotion_ready`, exact query-set hash, verified query IDs và map/hash
   GT trùng manifest.
2. Audit checksum mang runtime fingerprint, scorer policy và scorer source hash;
   `run.py` kiểm context trước preflight/search, primitive release kiểm lại context
   cùng fingerprint trace trước writer.
3. QA cache match thêm `query_sha256` và `full_query_sha256`; test cùng evidence
   nhưng khác query identity bị chặn.
4. Batch parse/gate/hash cùng byte snapshot trace, so với trace RAM và băm lại file
   sau writer trước receipt.
5. Missing/malformed manifest trả JSON `BLOCKED`, exit 1, không traceback; input
   hash ghi `missing`/`read_error` fail-closed.
6. Test post-write validator nay dùng cache/query/trace hợp lệ, assert writer được
   gọi đúng một lần rồi xác nhận không có receipt.
7. `git diff --check 00a6c08 9b107cd` và `git diff --check 0853535 9b107cd`
   đều sạch.

Verification re-review:

```text
40 passed in 2.71s
```

Focused suite gồm toàn bộ promotion gate, release rehearsal và hai integration
test `run.py`. Ca CLI thật với manifest không tồn tại trả exit 1 và JSON
`status=BLOCKED`, `eligible=false`, `input_sha256.holdout_manifest="missing"`,
không có traceback.
