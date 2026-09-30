# AIC 2026 — Forensic appeal audit (15/09/2026)

## Verdict khẩn cấp

**Khuyến nghị: KHÔNG CÓ BẰNG CHỨNG ĐỂ YÊU CẦU TĂNG ĐIỂM.**

Không tìm được receipt BTC, response máy chủ, bảng điểm theo query, hoặc GT/cửa sổ
frame chính thức. Vì vậy không có chain bằng chứng đủ chuẩn `QUERY → bản nộp
được BTC nhận → điểm BTC theo query → lý do đúng → số điểm cần cộng`.

| Priority | Query | Type | Official score | Proposed score | Recoverable | Confidence | Evidence | Reason |
|---|---|---|---:|---:|---:|---|---|---|
| — | — | — | unavailable | — | +0.00 | PROVEN | Tổng điểm và maximum điều chỉnh tự khớp; thiếu score sheet/receipt | Không thể thiết lập sai sót tính điểm hay tính đúng của một đáp án đã nộp |

| Scenario | Recovery | Revised total |
|---|---:|---:|
| Proven | +0.00 | 61.65 |
| Proven + strong | +0.00 | 61.65 |
| Proven + strong + plausible | +0.00 | 61.65 |

Không có đoạn phúc khảo nào được khuyến nghị. Nộp khi không có bằng chứng trực
tiếp sẽ biến các suy luận nội bộ/hậu kiểm thành cáo buộc không kiểm chứng được.

## Phase 0 — evidence freeze

Freeze lúc `2026-09-15T19:45:32+07:00`:

| Item | Value |
|---|---|
| HEAD | `b2fb3961a6667f71d1676c2fd71ec912e38faf75` |
| Branch | `wip/codex-h01-20260912` |
| Worktree | Dirty trước audit: một số `reports/` modified/untracked; không thay đổi/xóa chúng |
| Relevant historical commits | `5280431` (R2 query set), `4bec845` (GT/eval nội bộ R1/R2), `e4233eb` (bộ đề/máy chấm nội bộ), `43c9adf` (R2 docs) |

Không sửa production code, config, ZIP, checkpoint, trace hay dữ liệu. File này
là artefact audit mới duy nhất.

### Inventory và phân loại provenance

| Source | Classification | What it can establish | Limitation / hash |
|---|---|---|---|
| Thông báo/tổng điểm trong yêu cầu người dùng | UNKNOWN | Các total hiện hành, exclusion và policy được audit | Không có URL/PDF/export/receipt để xác thực độc lập |
| `C:\\Users\\lehon\\Downloads\\Thanh Nghệ_round1 (8,6).zip` | SECONDARY, contemporaneous contents | 25 CSV và câu trả lời R1; entry timestamp `2026-08-21 22:25:48 +07` | Không có receipt BTC; SHA-256 `36F18D7EC153AD5CDE917914E7B45ACDADFB4FDC3AA3308FEFA77243184A1ACA` |
| `C:\\Users\\lehon\\Downloads\\submission_THANH_ NGHỆ.zip` | SECONDARY, contemporaneous contents | 30 CSV và câu trả lời R2; mtime `2026-08-28 22:26:38 +07` | Không có receipt BTC; SHA-256 `30753D4E28C1C50AA20F175794E56AC8A9011E767B7FD152A255D3DBFB3E3384` |
| `C:\\Users\\lehon\\Downloads\\THANH_NGHE_round3_v4.zip` | SECONDARY, contemporaneous contents | 36 CSV và câu trả lời R3; mtime `2026-09-04 22:26:29 +07` | Không có receipt BTC; SHA-256 `1E60426C118A2BDDFB4CB95D58148038E08C5B7B716B831076832971CFD7055E` |
| `submissions/round2/submission.zip` | SECONDARY / replay candidate | Đúng một bản nộp nội bộ R2 | Audit 09/09 map nó với candidate score 4.4, không phải ZIP final 13.6; SHA `79FE2540BD8C6BB97ABF1E6D684C494C42EC2CFB26A0F6B3E4BBDFD47BF1DED7` |
| `THANH_NGHE_round3.original.zip` | SECONDARY / intermediate | 26 KIS CSV của bản intermediate | Không phải gói đầy đủ; audit 09/09 label intermediate 11.4; SHA `219433E34C99E53A4D3EB38D43F3C31ECAEA2104812BF0FE77B8C1DECA5C7BD8` |
| Checkpoint/trace/run.log trong `submissions/` | SECONDARY | Quá trình chạy các bản nội bộ | Không chứng minh BTC đã nhận đúng ZIP final; không dùng thay thế ZIP final |
| `dev_set/ground_truth/official_r1r2.jsonl` + meta | POST-HOC | Một reconstruction R1/R2 để diagnostic | Meta ghi rõ confidence là prior, không phải xác minh từng query; không có window BTC; SHA `61F75B2CCE14615C39BC281F3EF53B94761F41E4F4C82D44543437E32B90E4CA` |
| `dev_set/ground_truth/round1_kis_findings.json` | POST-HOC | Các vị trí hình ảnh để điều tra nội bộ | File tự ghi `verification_status: unknown`, không phải GT/interval BTC; SHA `6957C74FBCA4095E44B49DD56F37E2D1F3312C4DDB42D9012C7987E411917C92` |
| `reports/internal_reporting_audit_20260909/score_labeled_artifacts.json` | POST-HOC | Nhận diện các ZIP final/candidate theo hash và tên file | Tự ghi: score evidence chỉ là filename-to-score mapping, **không có BTC receipt** |

Hash trace/checkpoint được freeze để có thể replay: R1 checkpoint
`7FFD27BC…740E400`, R2 checkpoint `7721FD02…AF9B26`, R2 trace
`B09047C3…B2F7EF`, R3 checkpoint `77E8FE0D…4323C8`, R3 trace
`D64767F4…67B983`.

### Contradictory score labels

Audit nội bộ 09/09 gắn filename với R1 `8.6/13`, R2 `13.6/15`, R3 `11.8`
trong khi thông báo trong yêu cầu nêu R1 `12.80/24`, R2 `23.65/29`, R3
`25.20/33`. Các label cũ không có receipt, khác thang điểm và không thể được
dùng để suy điểm BTC hiện hành. Đây là lý do phải coi thông báo tổng điểm là
`UNKNOWN` provenance, không phải score sheet.

## Phase 1 — arithmetic / effective maximum

| Round | Submission query count | Official exclusions stated | Effective max stated | Official total stated | Result |
|---|---:|---:|---:|---:|---|
| 1 | 25 | 1 duplicate member | 24 | 12.80 | Count and maximum reconcile |
| 2 | 30 | `query-p2-27-qa` | 29 | 23.65 | Count and maximum reconcile |
| 3 | 36 | `query-p2-5-qa`, `query-p2-6-qa`, `query-p2-9-kis` | 33 | 25.20 | Count and maximum reconcile |
| Total | — | — | 86 | **61.65** | `12.80 + 23.65 + 25.20 = 61.65` |

Không tồn tại score theo query, nên bảng bắt buộc
`query_id/submitted_answer/official_score/max_score/source_of_score` không thể
được dựng trung thực. Điền score giả định hoặc chạy máy chấm nội bộ sẽ là hậu
kiểm, không phải reconstruction BTC.

## Phase 5 — known problematic queries

### R1: `query-p1-8-kis` and `query-p1-14-kis`

- Nội dung hai query trong `data/queries/sotuyen1_p1.jsonl` là giống hệt nhau.
- Trong ZIP R1 secondary, dòng đầu của cả hai là `L26_V171,5504`.
- Nhưng toàn bộ CSV không giống byte: `p1-8` SHA `6C65A6C6…20DC7F`, `p1-14`
  SHA `BACA46DF…B1BE69`; mỗi file 1,390 bytes. Vì điểm KIS có thể phụ thuộc
  nhiều rank, không được suy rằng raw score bằng nhau từ dòng đầu.
- Không có raw score cho từng query, score sheet BTC, hoặc cửa sổ frame BTC.

**Disposition: UNUSABLE, không phải P0.** Không thể chứng minh `max(score8,
score14)` đã bị áp sai, cũng không thể tính missing points. Việc đề trùng đã
được phản ánh đúng ở maximum `25 - 1 = 24`.

### R2: `query-p2-27-qa`

ZIP R2 chứa answer đầu `L24_V016,0,5`; file query tồn tại. Rule trong yêu cầu
nói query bị loại toàn cục và maximum `30 - 1 = 29` đúng. Không có score theo
query để kiểm tra query này còn được tính hay không; không có bằng chứng rằng
team bị bất lợi riêng. **UNUSABLE.**

### R3: `query-p2-5-qa`, `query-p2-6-qa`, `query-p2-9-kis`

ZIP R3 final có các entry tương ứng; dòng đầu lần lượt là
`L25_V024,22950,13`, `L25_V018,14150,Tây Bắc`, `L22_V005,11530`.
Ba loại trừ khớp `36 - 3 = 33`. Các query này không thể là nguồn tăng điểm
theo rule. Không có score sheet để kiểm chứng việc loại trừ ở phép tính BTC.
**UNUSABLE.**

## Phase 3–4 and Phase 6 — answer/event review

Các ZIP secondary khôi phục được answer/frame đã nộp, nhưng không đủ để phân
biệt câu nào mất điểm, vì thiếu official per-query score. `official_r1r2` và
`round1_kis_findings` là reconstruction hậu kỳ; chính metadata cảnh báo không
có interval BTC và chưa visual-verified. Chúng không được dùng làm chứng cứ cho
đáp án đúng.

Các quan sát sau bị loại khỏi appeal vì không appeal-safe:

- GT nội bộ R1/R2 chứa answer/video lấy từ các ZIP team; nó không phải reference
  answer BTC độc lập.
- Diagnostic KIS có cùng video hoặc frame gần một finding hậu kiểm không chứng
  minh sự kiện nằm trong interval BTC.
- Bất kỳ cải tiến, corrected ZIP hoặc rerun sau 04/09 đều là POST-HOC và không
  nói được đã nộp gì trong contest.
- Không có GT R3 độc lập hay evidence video/frame đã xác minh dành cho appeal.

Không có duplicate khác, alias QA, sự kiện không tồn tại, parser mismatch hay
GT thiếu được chứng minh bởi nguồn độc lập. Không nâng bất kỳ observation nào
lên `PLAUSIBLE`.

## Phase 7 — chain-of-custody conclusion

| Required link | Status |
|---|---|
| Query → candidate ZIP contents | STRONG (đối với ba ZIP named above) |
| Candidate ZIP → accepted by BTC | WEAK (không có receipt/server response) |
| Accepted submission → official per-query score | UNUSABLE (không có score sheet) |
| Submitted answer/frame → independent correct reference/interval | UNUSABLE cho appeal (chỉ có GT/finding hậu kiểm) |
| Corrected score → total | UNUSABLE (không có missing raw score) |

Chuỗi đứt ở hai liên kết trung tâm. Không có candidate `PROVEN`, `STRONG` hay
`PLAUSIBLE` có recoverable points.

## Evidence still needed before any appeal

Chỉ nên đảo verdict nếu có ít nhất một trong các artefact BTC sau: receipt có
ZIP hash/ID, export dashboard score theo query, response upload, hoặc GT/score
explanation chính thức cho một query. Khi đó đối chiếu ZIP hash trước, rồi mới
kiểm tra answer/frame đúng vào query đó; không rerun hệ thống hiện tại để tạo
bằng chứng.
