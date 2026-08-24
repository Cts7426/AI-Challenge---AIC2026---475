# Product specification — HCMAIC 2026 Batch 1 accuracy uplift

## Problem

Batch 1 cần tìm đúng khoảnh khắc video, trả lời Q&A đúng evidence và nộp đúng
frame tuyệt đối. Baseline tự động hiện đạt 6,8/13 trên `batch1_holdout13`, trong
khi cùng evidence có manual lookup đạt 8,6/13; khoảng cách này chỉ ra lỗi còn ở
planning, candidate/evidence và phân bổ kết quả, không phải lý do để bịa GT.
GT legacy chưa human-verified không được biến thành tín hiệu promotion.

## Goals

- Trong mốc triển khai 3 ngày, nâng pipeline tự động lên 10–13/13 trên
  `batch1_holdout13` đã đóng băng, với trace/evidence có thể replay.
- Dùng một entrypoint `solve_query()` và trace thống nhất cho KIS, Q&A, TRAKE;
  trace đủ phân loại `retrieval_miss`, `wrong_frame`, `qa_reasoning`,
  `missing_evidence`, `trake_order` và `format`.
- Với KIS, tăng độ phủ bằng multi-anchor trung thành query; với Q&A, giữ
  candidate-specific hypotheses gắn evidence thay vì một đáp án global.
- Chỉ promotion bằng GT `verified` có provenance; GT legacy chỉ dùng phân tích.

## Non-goals

- Không tạo, suy đoán hay nâng trạng thái ground truth chưa human-verified.
- Không đổi CLIP, reindex ES/Milvus, tải raw video, thêm generic KIS VLM rerank
  hoặc dense-frame TRAKE.
- Không đầu tư AVS/KISC/UI thi đấu, tự chọn provider/model LLM, hoặc dự báo điểm
  thi từ regression nội bộ.

## User stories

- Operator chạy một query bất kỳ qua runner chung, xem answers, query plan,
  source ranks/contributions, Q&A hypotheses, timing, failure class và runtime
  fingerprint trong trace.
- Operator chạy KIS có mô tả phức tạp, nhận tối đa ba anchor ngắn, trung thành
  với query; planner lỗi phải fallback đường hiện hành.
- Operator chạy Q&A, nhận portfolio theo evidence canonical của từng hypothesis;
  không có hypothesis hợp lệ thì fail/retryable, không sinh ZIP một phần.
- Operator chạy phân tích trên GT legacy và thấy rõ không đủ promotion; cờ
  promotion từ chối nhãn `unknown`, provenance thiếu hoặc GT parse bị mất.

## Functional requirements

- Schema GT hỗ trợ `verification_status`, `provenance`, `verified_by`,
  `verified_at`; GT cũ thiếu field đọc là `unknown`, còn `verified` cần đủ audit
  trail. Promotion fail-closed khi còn nhãn chưa verified hoặc query thiếu GT.
- Đóng băng đủ 25 query vòng 1 từ `HEAD:data/queries/sotuyen1_p1.jsonl` và
  manifest `batch1_holdout13` gồm 10 KIS + 3 QA. Nhãn chưa xác minh giữ
  `unknown`; video-disjoint chỉ được khẳng định ở mức provenance dữ liệu có sẵn.
- `backend/tasks/runner.py::solve_query(query, total=100)` là entrypoint chung;
  `run.py` và evaluator dùng nó mà không đổi CLI, checkpoint hay submission.
- KIS planner có tối đa 3 anchor, tối đa 60 token CLIP thực tế; chặn màu/số/số
  lượng mới, encode từng anchor riêng, hợp nhất RRF k=7 ở shot/video và chỉ áp
  temporal bonus mềm mặc định 1,25 cho query có thứ tự.
- Q&A planner phân loại `visual_count`, `visual_read`, `ocr`, `asr`, `metadata`,
  `visual_attribute`; mỗi `QAHypothesis` phải gắn answer, video/shot/keyframe/frame,
  confidence, evidence hash và provenance. Cache key gồm query/model/prompt/config/evidence.
- Release gate kiểm zero-crash, GT verified, overall >=0.82, KIS >=0.82,
  QA >=0.75 và regression không giảm; release artefact giữ commit, config,
  trace, evidence cache, runtime fingerprint, scorer policy, ZIP checksum và
  lệnh tái lập.

## Non-functional requirements

- Không gọi LLM/DB để xác minh manifest/gate; metadata UTF-8, deterministic,
  replay được và các job vẫn checkpoint/resume an toàn.
- Mọi thay đổi hành vi có TDD, baseline và query-level diff; lỗi một nguồn search
  không kéo sập toàn query.
- Không đổi provider/model tự động; runtime fingerprint chặn resume trộn model,
  mode Q&A hay config.

## Constraints

- `frame_id` nộp chỉ lấy từ `frame_map`; ordinal raw không được suy thành frame.
- LLM chỉ qua `backend/llm/adapter.py`; vector vẫn L2-normalize/COSINE và mọi
  trọng số/knob nằm trong `data/config/`.
- CLIP tối đa 77 token; anchor/query expansion không được thêm chi tiết không có
  trong query gốc. Q&A release giữ `QA_INFERENCE_MODE=legacy` đến khi two-stage
  replay qua tune + holdout trên evidence cố định.
- Thời hạn 3 ngày chỉ cho phép thay đổi có evidence; khi còn dưới 24 giờ chỉ sửa
  crash, format, mất dữ liệu, sai mapping hoặc P0.

## Acceptance criteria

- Product run tự động đạt 10–13/13 trên `batch1_holdout13`, thay vì baseline
  6,8/13, và giải thích được khoảng cách với mức 8,6/13 khi manual lookup.
- Test schema/gate chứng minh GT legacy là `unknown`, audit trail của `verified`
  là bắt buộc, và promotion chặn GT unknown/missing trước ES/Milvus.
- KIS có test anchor/token/fidelity/fallback/RRF/temporal; Q&A có test answer
  mode, evidence pinning, sentinel và portfolio; runner có test parity,
  fingerprint/cache; release có zero-crash/GT/threshold/regression test.
- Mọi ZIP release qua validator, không thiếu query/evidence, có đủ receipt và
  SHA-256; chỉ một portfolio Q&A được chọn để nộp.

## Risks

- GT legacy có thể sai/incomplete; không được dùng nó promotion hay diễn giải
  score nội bộ như dự báo điểm thi.
- Public chỉ chấm 50% đáp án nên dao động nhỏ không đủ promotion; cần giữ replay
  và gate đầy đủ thay vì tối ưu theo Public.
- 10–13/13 là mục tiêu vận hành, không phải xác nhận đã đạt khi GT chưa verified;
  manual lookup 8,6/13 chỉ là evidence về headroom, không phải hành vi tự động.
- LLM/evidence không xác định, service lỗi hoặc mapping sai có thể làm kết quả
  không replay được; trace, cache và runtime fingerprint là phòng vệ bắt buộc.
