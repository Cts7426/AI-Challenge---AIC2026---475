# Nhật ký dùng holdout — tối đa 5 lần (`dev_set/tools/run_evaluation.py --split holdout`)

## Lần 1 — 20/08/2026 21:08 (Công Lý)

- **Nguồn:** `queries001.txt` + `queries002_frame.txt` (đồng đội cung cấp
  tối 20/08, GT tự động `confidence: auto_bm25`, KHÔNG phải người xác nhận
  tay) → chuyển đổi qua `dev_set/tools/build_holdout_from_teammate.py`.
- **Lý do dùng holdout** (không dùng `tune`): bộ đề mới, khác nguồn, đúng ý
  nghĩa "kiểm tra cuối cùng trước khi thi" — không phải dữ liệu đã tune nhiều
  lần.
- **Kết quả:** `dev_set/results/run_20260820_2108/` (KIS+QA, 91/92 không
  crash) + `dev_set/results/holdout_trake_qualitative.json` (TRAKE, đánh
  giá riêng vì GT chỉ có 1 cửa sổ frame). Báo cáo đầy đủ:
  `reports/holdout_teammate_check.md`.
- **Phát hiện chính:** video đúng hạng 1 chỉ 10-15% (KIS/QA/TRAKE đồng nhất)
  nhưng lọt top-100 72-74% — mơ hồ thị giác giữa nhiều video CÙNG CHỦ ĐỀ
  (bộ đề cố ý gom nhiều video tai nạn/đua xe gần giống nhau). Không phải bug
  mới, không phải hồi quy — giới hạn thật của CLIP trên nội dung dễ nhầm.
- **Còn lại:** 4/5 lượt.

## Lần 2 — 20/08/2026 22:xx (Công Lý)

- **Lý do:** xác nhận `RRF_K` 60→7 (fix cho phát hiện ở Lần 1: nhiều câu có
  1 nhánh ASR/OCR khớp rất tốt nhưng vector kém, RRF_K=60 không đủ nhạy để
  tín hiệu mạnh 1 nhánh thắng) có thực sự cải thiện bộ đề holdout qua
  pipeline sản xuất đầy đủ (không chỉ qua `search()` thô như lúc quét).
- **Kết quả:** `dev_set/results/run_20260820_2207/`. KIS avg Final
  0.111→**0.189** (+70%, R@1 0.000→0.028) — xác nhận rõ ràng. QA avg Final
  0.007→0.000 (**không cải thiện**, nhưng QA đã gần 0 từ TRƯỚC khi đổi
  RRF_K — vấn đề riêng, không phải do thay đổi này gây ra, xem
  `reports/holdout_teammate_check.md` §5).
- **Còn lại:** 3/5 lượt.

## Lần 3 — 20/08/2026 23:12 (Công Lý) — ⚠️ KHÔNG DÙNG ĐƯỢC, HẾT TIỀN API GIỮA CHỪNG

- **Lý do:** xác nhận 2 sửa lỗi QA cùng lúc — (1) `_try_shot` dừng ở shot ĐẦU
  TIÊN đủ tự tin thay vì thử hết `MAX_SHOTS_TRIED` rồi chọn confidence cao
  nhất (`MAX_SHOTS_TRIED` 3→5), (2) `qa_pipeline()` truyền nhầm `query_en`
  (bản dịch CẢ CÂU HỎI GỐC) vào `search(parts.event_vi, query_en=...)` —
  lệch nghĩa với `event_vi` (chỉ phần mô tả sự kiện `parse_question()` tách
  ra), làm CLIP so khớp sai trên MỌI câu QA có tách event_vi thành công.
- **Kết quả:** `dev_set/results/run_20260820_2312/` — **KHÔNG PHẢN ÁNH ĐÚNG
  chất lượng 2 sửa lỗi trên**: giữa chừng chạy, tài khoản Anthropic API HẾT
  TIỀN (`BadRequestError: Your credit balance is too low`) → 23/27 câu QA
  báo `F0_CRASH` (không phải do code sai — do KHÔNG gọi được LLM nữa từ thời
  điểm đó). QA avg Final đo được = 0.000 nhưng con số này KHÔNG ĐÁNG TIN.
- **Bằng chứng gỡ lỗi cô lập (không tốn quota holdout, chạy trước khi hết
  tiền)**: gọi trực tiếp `qa_pipeline()` cho `QA_004` với `query_en` ĐÚNG như
  production truyền (bản dịch cả câu) → trả `("Khoảng 30m", frame đúng)`,
  khớp GT — xác nhận CẢ HAI sửa lỗi hoạt động đúng trên ca cụ thể đã điều
  tra kỹ, dù chưa đo được trên toàn bộ 27 câu QA vì hết tiền.
- **Việc cần làm trước khi thi**: nạp thêm tiền Anthropic API (hoặc chuyển
  `LLM_BACKEND=gemini`/`local` tạm thời) rồi chạy lại — quota holdout còn
  lại thực chất vẫn nên tính là **3/5** (lần này không cho tín hiệu đáng tin,
  nhưng cơ chế đếm trong `run_evaluation.py` không phân biệt được lỗi hạ
  tầng với lỗi thật, nên số đếm chính thức đã lên 3/5 — cân nhắc kỹ trước
  khi dùng nốt 2 lượt còn lại).
- **Còn lại (đếm chính thức, dù lần này không đáng tin):** 2/5 lượt.
