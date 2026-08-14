# BLOCKERS

## 1. ✅ ĐÃ XONG (14/08) — Bridge ShotHit

File này từng ghi "không có module nào làm bridge, đang mượn `_chia_slot` của
`run_minimal.py`" — **đã lỗi thời**. `dev_set/tools/run_evaluation.py` giờ có
sẵn `_to_shot_hits()` (dòng 43) chuyển thẳng kết quả `search()` (đã có
`shot_id` từ `group_by_shot=True`) sang `ShotHit`, rồi gọi `allocate()` đúng
chuẩn D3.1 — không còn bypass allocator, không còn mượn `run_minimal.py`.

## 2. ✅ ĐÃ SỬA (14/08) — hai bug tìm được qua code review, xem
`reports/C31_C32_C44_TECHNICAL_REPORT.md` §12 để biết chi tiết + kết quả kiểm
chứng sống:

- `dev_set/tools/scoring.py::recall_at_k()` nhân nhầm với bảng rút gọn theo
  hạng (`_score_for_rank`) — Final Score sai cho MỌI dạng bài, đo trên ví dụ
  CÓ ĐÁP SỐ của BTC (docs/contest.md dòng 60-62): code cũ ra 0.612 thay vì
  0.74. Đã sửa về đúng công thức 2 tầng (`R@k = max R-Score`, `Final = trung
  bình 5 R@k`), có test chốt (`test_final_score_VI_DU_CO_DAP_SO_cua_BTC`).
- `dev_set/tools/run_evaluation.py` — nhánh QA gán thẳng
  `answer_text = gt.answer_text` (so đáp án với chính nó, R-Score QA LUÔN 1.0
  bất kể hệ thật trả lời gì; `backend/tasks/qa.py` — 482 dòng — chưa từng
  được đo qua bộ này). Đã sửa gọi `backend.tasks.qa.qa_pipeline()` thật.
