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

- 2026-09-03 22:38 +0700 · `eval_official.py --part p2` · 19 câu · chiến dịch Đợt 3 (hạn mức 2 lượt)

  - **Cấu hình đo:** làn KIS production sau khi gộp nhánh Thạch — dual vector
    (CLIP + SigLIP2), pool 1500, `RRF_K=7`, rerank top-50 BẬT, `SLOT_BUDGET=[(50,2)]`,
    `video_prior` TẮT, `ocr_probe` BẬT. Bản dịch đóng băng bằng `llm()`
    (`claude-opus-5`, `official_r1r2.en.json`) — KHÔNG phải bản dịch tay.
  - **Kết quả (19 câu KIS p2):** Final mức video **0,6421** · R@1 0,2105 ·
    R@5 0,5263 · R@100 0,8421 · tìm ra video 16/19 · frame ±5/±15/±40 =
    0,0316 / 0,0947 / 0,1895 · độ trễ trung vị 1,674s.
    Artefact: `dev_set/results/run_20260903_merge_p2_holdout.json`.
  - **So với p1 (đã tune, cùng cấu hình, cùng nguồn dịch):** Final 0,8000 →
    0,6421 · R@1 0,55 → 0,21 · ±40 0,33 → 0,19.
  - **Đã loại trừ một cách giải thích:** thiên vị "frame_exact trùng keyframe
    BTC" (báo cáo 02/09 §1.2) KHÔNG giải thích được khoảng cách — p1 trùng
    8/20 (40%), p2 trùng 7/19 (37%), gần như nhau.
  - **Chưa loại trừ được:** đây là overfit lên 20 câu p1, hay p2 vốn khó hơn.
    Phân xử được bằng một lượt A/B cấu hình CŨ (một nhánh vector, pool 500,
    bảng slot cũ) trên chính p2 — CHƯA CHẠY, cần lượt holdout cuối.
  - **Đọc con số này cho đúng:** đây là pipeline TỰ ĐỘNG THUẦN, chưa qua bước
    Claude soi ảnh. Đợt 2 thật đội đạt 13,6/15 (`official_r1r2.meta.json`) là
    điểm SAU khi soi. Nên 0,6421 là SÀN, không phải dự báo điểm thi.
  - **Còn lại:** 1/5 lượt.

- 2026-09-03 23:01 +0700 · `eval_official.py --part p2` · 19 câu · chiến dịch Đợt 3 (hạn mức 2 lượt)

- 2026-09-03 23:02 +0700 · `eval_official.py --part p2` · 19 câu · chiến dịch Đợt 3 (hạn mức 2 lượt)

- 2026-09-03 23:03 +0700 · `eval_official.py --part p2` · 19 câu · chiến dịch Đợt 3 (hạn mức 2 lượt)

## Lần 5 — 03/09/2026 ~23:00 (Claude, theo yêu cầu Công Lý) — A/B PHÂN XỬ

- **Lý do:** Lần 4 cho thấy p2 (0,6421) thấp hơn hẳn p1 (0,8000) cùng cấu hình.
  Hai cách giải thích chưa phân biệt được: (a) cấu hình Đợt 3 overfit lên 20 câu
  p1, hay (b) p2 vốn khó hơn. Chỉ một phép đo phân xử được: chạy cấu hình CŨ
  trên CHÍNH p2. Ba arm chọn TRƯỚC khi nhìn kết quả, không quét tham số.
  Script: `scripts/ab_dot2_vs_dot3.sh` · artefact `dev_set/results/run_20260903_ab_p2/`.

- **Kết quả (19 câu KIS p2, bản dịch `llm()` claude-opus-5):**

  | arm | Final_vid | R@1 | R@5 | R@20 | R@100 | ±5 | ±15 | ±40 | video |
  |---|---|---|---|---|---|---|---|---|---|
  | `dot2` (Đợt 2 nguyên bản) | 0,3895 | 0,105 | 0,210 | 0,368 | 0,789 | 0,042 | 0,074 | 0,084 | 15/19 |
  | `dot3` (đang chạy) | **0,6421** | 0,210 | 0,526 | 0,789 | 0,842 | 0,032 | **0,095** | **0,190** | 16/19 |
  | `dot3_slotcu` | 0,6526 | 0,210 | 0,526 | 0,789 | 0,895 | 0,000 | 0,084 | 0,179 | 17/19 |

- **KẾT LUẬN — giả thuyết (b), KHÔNG phải overfit.** Cấu hình Đợt 3 thắng cấu
  hình Đợt 2 trên dữ liệu chưa từng thấy ở mọi thước đáng kể: Final mức video
  0,3895 → 0,6421 (+65%), R@5 0,210 → 0,526 (+150%), ±40 0,084 → 0,190 (+126%).
  Chiến dịch Đợt 3 KHÁI QUÁT ĐƯỢC. Khoảng cách p1↔p2 là độ khó câu hỏi.
  **Không lùi gì cả — giữ nguyên cấu hình đang chạy cho Đợt 3.**

- **Bảng slot `50x2` cũng khái quát được:** thắng bảng cũ ở CẢ BA dung sai frame
  trên CẢ p1 lẫn p2. Đánh đổi đã biết và chấp nhận: bảng cũ tìm ra nhiều hơn
  1 video (17/19 vs 16/19) và Final mức video nhỉnh hơn 0,01 — nhưng BTC chấm
  `frame_id ∈ [s,e]`, đúng video mà sai frame vẫn 0 điểm. Chọn theo cột frame.

- **Điểm yếu thật còn lại — ghi ra để không tự lừa mình:** mức frame trên dữ liệu
  chưa từng thấy vẫn thấp (±5 = 0,032). Pipeline tự động tìm đúng VIDEO tốt
  (16/19) nhưng định vị FRAME trong video thì kém. Đó chính xác là chỗ bước
  Claude soi ảnh tối 04/09 tạo ra giá trị lớn nhất — đừng cắt bước đó để tiết
  kiệm thời gian.

- **Còn lại: 0/5 lượt. HẾT HOLDOUT.** Mọi quyết định sau đây không còn tập nào
  độc lập để kiểm chứng — đừng chỉnh thêm tham số nào trước giờ thi.
## Official R1R2 · lượt 1/2 — 03/09/2026 22:50 (Thạch)

- **Lý do:** R3.T2 đo A/B thay đổi độ sâu TRAKE R3.T1 trên đủ 3 câu official;
  phần p2 gồm 2 câu holdout và được mở đúng một lần.
- **Cách chống nhiễu:** 11 truy vấn sự kiện chỉ gọi ES/Milvus một lần rồi chia
  cùng cache hit cho `HEAD` trước R3.T1 và working tree sau R3.T1.
- **Kết quả:** exact/±5/±15 `0,000→0,000`; ±40 `0,250→0,250`; không có mức
  dung sai nào tăng hoặc giảm. Artefact:
  `dev_set/results/r3t2_official_trake_20260903.json`.
- **Caveat:** ba event p1 dùng fallback tiếng Việt do dịch VI→EN lỗi kết nối;
  A/B vẫn chung hit, nhưng điểm tuyệt đối p1 chưa đại diện cho release có dịch.
- **Còn lại của hạn mức official Đợt 3:** 1/2 lượt.
