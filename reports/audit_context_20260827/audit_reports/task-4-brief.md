## Task 4: Q&A candidate-specific hypotheses

- Mở rộng question plan với answer_mode: visual_count, visual_read, ocr, asr,
  metadata, visual_attribute; structured planner lỗi thì fallback rule hiện tại.
- Thêm `QAHypothesis` gắn answer với video/shot/keyframe/frame, confidence,
  evidence_hash và provenance.
- Thu thập mọi hypothesis hợp lệ trong candidate budget, thay vì chỉ giữ một
  global answer.
- Portfolio round-robin canonical evidence của từng hypothesis trước frame thay
  thế; chỉ phần đuôi mới dùng best-supported answer cho candidate chưa dùng.
- Loại sentinel answer; không hypothesis hợp lệ thì trả failure/retryable và
  không tạo ZIP một phần.
- Cache key gồm query/model/prompt/config/evidence; không đổi provider tự động.
- Thêm test answer mode, evidence pinning, sentinel và portfolio trước code.

