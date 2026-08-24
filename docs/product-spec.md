# Product specification — HCMAIC 2026 Batch 1 accuracy uplift

## Problem

Hệ thống phải truy xuất đúng khoảnh khắc video và nộp đúng định dạng cho Batch
1. Một thay đổi có số đo tốt trên GT chưa được con người xác minh có thể dẫn đến
promotion sai; một frame tuyệt đối hoặc bằng chứng Q&A sai cũng có thể mất điểm.

## Goals

- Duy trì retrieval, Q&A và TRAKE có thể replay với evidence, provenance và
  runtime fingerprint.
- Chỉ promotion khi GT đã được xác minh, còn GT legacy chỉ phục vụ phân tích.
- Đóng băng input 25 query vòng 1 và manifest `batch1_holdout13` để so sánh
  thay đổi mà không sửa query đang vận hành.

## Non-goals

- Không tạo hoặc suy đoán ground truth mới.
- Không đổi CLIP, reindex ES/Milvus, tải raw video, hay thêm VLM rerank KIS.
- Không phát triển AVS/KISC/UI thi đấu trước khi qua sơ tuyển.

## User stories

- Với vai trò operator, tôi chạy đánh giá phân tích trên GT legacy và thấy rõ
  nó chưa đủ điều kiện promotion.
- Với vai trò operator, tôi không thể chạy promotion khi còn một nhãn `unknown`
  hoặc thiếu provenance xác minh.
- Với vai trò operator, tôi có thể truy lại đúng 25 query vòng 1 và 13 query
  holdout đã chọn từ artefact có provenance.

## Functional requirements

- Schema GT hỗ trợ `verification_status`, `provenance`, `verified_by` và
  `verified_at`; dữ liệu cũ thiếu các field này phải đọc được là `unknown`.
- Giá trị `verified` phải có đủ provenance, người xác minh và thời điểm xác minh.
- `python -m dev_set.tools.run_evaluation --promotion` phải từ chối nếu bất kỳ
  GT đã nạp nào không `verified`; chạy không có cờ này là phân tích và phải in
  trạng thái không đủ điều kiện khi dùng GT legacy.
- Artefact query vòng 1 phải chứa đủ 25 query từ `HEAD:data/queries/sotuyen1_p1.jsonl`
  cùng commit, blob hash và số bản ghi nguồn.
- Manifest `batch1_holdout13` phải có đúng 10 KIS và 3 QA; mỗi entry mang
  `unknown` đến khi human verification hoàn tất.

## Non-functional requirements

- Gate phải fail closed, có thông báo nêu rõ query chưa xác minh.
- Metadata và manifest là UTF-8, deterministic, dễ audit, không gọi LLM hay DB.
- Tương thích với tất cả GT legacy và không thay đổi cách tính metric phân tích.

## Constraints

- `frame_id` nộp chỉ lấy từ `frame_map`; ordinal raw không được suy thành frame.
- LLM chỉ qua `backend/llm/adapter.py`; model release do operator đặt bằng biến
  môi trường và fingerprint không được trộn khi resume.
- Tất cả query/label chưa human-verified là `unknown`; không dùng chúng để
  promotion hoặc suy đoán đáp án.

## Acceptance criteria

- Test schema chứng minh GT legacy thành `unknown`, `verified` thiếu audit trail
  bị từ chối, và promotion chỉ nhận toàn bộ GT `verified`.
- Chạy focused test và full suite xanh trong `.venv` của repo.
- `dev_set/manifests/batch1_round1_queries.json` có đúng 25 query, provenance
  tới commit `b8090cd85133433cbaa5a37d542abea48c778f5c` và blob
  `7c7726920406cd3e26703dd33179fa6350f7b507`.
- `dev_set/manifests/batch1_holdout13.json` có 10 KIS, 3 QA, và ghi rõ phép
  kiểm video-disjoint chỉ dựa trên GT legacy, không phải xác minh con người.

## Risks

- GT legacy có thể chứa frame/video/answer sai hoặc không đầy đủ; gate phải giữ
  chúng ngoài promotion cho đến khi có provenance human review.
- Video-disjoint từ GT legacy là bằng chứng cấu trúc tạm thời, không xác nhận
  nội dung đúng; manifest giữ trạng thái `unknown` để tránh diễn giải quá mức.
- Score nội bộ không dự báo Public/điểm thi; chỉ dùng để phát hiện regression.
