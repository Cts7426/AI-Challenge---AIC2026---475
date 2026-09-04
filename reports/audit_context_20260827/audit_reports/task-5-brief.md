## Task 5: promotion gates và release rehearsal

- Gate chỉ chạy trên GT `verified`; nhãn `unknown` phải chặn trước retrieval.
- So regression 25 câu với baseline artefact có cùng scorer/runtime contract;
  không giảm điểm, zero crash/failure mới.
- Holdout 13 câu: overall >= 0.82, KIS >= 0.82, Q&A >= 0.75; thiếu
  verified GT phải trả trạng thái BLOCKED/NOT_ELIGIBLE, không suy điểm.
- Không ZIP nếu bất kỳ QueryRun failed/retryable, Q&A thiếu hypothesis/evidence,
  validator lỗi hoặc fingerprint/resume mismatch.
- Rehearsal receipt lưu commit, config snapshot, trace path/hash, evidence cache
  path/hash, runtime fingerprint, scorer policy, query/GT manifest hashes, ZIP
  SHA-256, validator result và lệnh tái lập.
- Thêm test fail-closed cho partial batch, unknown GT, threshold thấp, regression
  giảm, artefact thiếu, checksum/receipt deterministic.
- Chạy full suite, preflight development/release và CLIP space guard. Không bịa
  score: nếu holdout chưa verified thì báo gate chưa thể chứng minh.
