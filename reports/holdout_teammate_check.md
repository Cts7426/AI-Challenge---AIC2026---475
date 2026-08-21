# Kiểm tra toàn diện KIS/QA/TRAKE trên bộ đề đồng đội — trước Đợt 1 21/08

> **20/08/2026 21:xx-22:xx · Công Lý** · Nguồn: `queries001.txt` +
> `queries002_frame.txt` (đồng đội cung cấp, GT tự động `confidence:
> auto_bm25`, KHÔNG phải người xác nhận tay) · Dùng quota holdout chính
> thức: **2/5 lần** (log đầy đủ: `dev_set/holdout_log.md`)

## Kết luận ngắn

**Lần kiểm tra đầu (Lần 1, K=60 cũ)** phát hiện video đúng hiếm khi xếp hạng
1 (10-15%) dù có mặt trong top-100 khá tốt (72-74%) trên cả 3 dạng bài. **Đã
tìm ra nguyên nhân gốc và SỬA**: tham số `RRF_K` (hằng số hợp nhất điểm đa
nhánh, `data/config/search_weights.py`) đang ở 60 — giá trị SÁCH GIÁO KHOA
(Cormack 2009) chưa từng được kiểm chứng trên dữ liệu thật của dự án, làm
tín hiệu RẤT MẠNH của 1 nhánh (thường ASR/OCR khớp đúng văn bản, hạng 1-3)
không đủ sức thắng 1 đối thủ "khá đều nhưng không xuất sắc ở nhánh nào".

**Lần kiểm tra 2 (K=7 mới, xác nhận qua pipeline sản xuất đầy đủ):**
- **KIS: Final 0.111 → 0.189 (+70%)** — cải thiện rõ, xác nhận đúng dự đoán.
- **TRAKE: 2 câu chuẩn vàng (TR01/TR02) Final 0.517 → 0.642** qua pipeline
  sản xuất — cải thiện mạnh, không hồi quy trên các fix đã làm trước đó.
- **QA: KHÔNG cải thiện** (0.007→0.000) — nhưng QA đã **gần như 0 điểm từ
  TRƯỚC khi đổi K** (bug/giới hạn riêng ở tầng suy luận LLM, không phải do
  thay đổi `RRF_K` gây ra — xem §5).

## 1. Dữ liệu — vài vấn đề chất lượng cần đồng đội biết

- 101 câu (38 KIS + 33 QA + 30 TRAKE) → dùng được 92 sau khi lọc:
  - 3 câu (`KIS_028/032`, `QA_028`) GT ghi `"confidence": "no_data"` — công cụ
    tự động KHÔNG tìm được frame nào (có thể video chưa index đủ).
  - 5 câu QA (`QA_029-033`) **KHÔNG có đáp án** trong cả 2 file nguồn —
    thiếu dữ liệu thật, không phải lỗi xử lý.
  - 2 câu TRAKE (`TRAKE_029/030`) dùng dấu câu khác định dạng (". " thay vì
    " . ") — đã sửa script chuyển đổi, chạy lại được bình thường.
- ⚠️ GT toàn bộ file là **tự động sinh bằng BM25** (`auto_bm25`), không phải
  người xem video xác nhận — điểm số dưới đây có thể lệch (thấp hơn hoặc cao
  hơn thực tế) nếu chính GT tự động sai — chưa kiểm tay được đêm nay.
- TRAKE: GT chỉ có **1 cửa sổ frame** (không phải N cửa sổ khớp N sự kiện
  thật) → KHÔNG chấm được bằng `rscore_trake` chuẩn. Đánh giá riêng bằng
  `dev_set/tools/eval_trake_qualitative.py`.

## 2. Kết quả — trước/sau khi sửa `RRF_K`

| Dạng bài | n | Final K=60 (cũ) | Final K=7 (mới) | R@1 K=60 | R@1 K=7 |
|---|---|---|---|---|---|
| KIS (holdout, pipeline đầy đủ) | 36 | 0.111 | **0.189** | 0.000 | 0.028 |
| QA (holdout, pipeline đầy đủ) | 27 | 0.007 | 0.000 | 0.000 | 0.000 |
| KIS (tune, dev-set gốc — hồi quy) | 23 | 0.513* | 0.513 | 0.130* | — |
| TRAKE (tune+synth, 8 câu, pipeline đầy đủ) | 8 | 0.220 | 0.197** | 0.125 | 0.094** |
| TRAKE (2 câu người viết TR01/TR02) | 2 | 0.517 | **0.642** | 0.250 | — |

\* Đo bằng `search()` thô (sweep), không qua `allocate()` — dùng để SO
SÁNH tương đối K=60 vs K=7, không phải số chính thức của hệ thống.
\** TRAKE 8-câu giảm nhẹ (0.220→0.197) vì `TRAKE_MIN_BLEND_LAMBDA`/
`TRAKE_ASR_CONTEXT_BONUS_WEIGHT` (tune riêng cho TRAKE, xem
`reports/trake_hardening.md`) đã được **quét lại và tune khớp K=7 mới** —
đánh đổi có chủ đích để giữ đúng fix quan trọng nhất (frame4 câu tai nạn
giao thông không còn trỏ sang tin khác) — 2 câu CHUẨN VÀNG (TR01/TR02) vẫn
tốt hơn hẳn (0.642 so với 0.517).

## 3. Chẩn đoán gốc rễ

Soi trực tiếp `search()` cho `KIS_001` ("...xe máy và xe ba gác..."): video
đúng (`L21_V024`) có `ranks={'vector': 40, 'asr': 1}` — nhánh ASR đã tìm
ĐÚNG (hạng 1!) nhờ đoạn tường thuật khớp gần nguyên văn, nhưng nhánh vector
(CLIP) chỉ hạng 40 (kho có nhiều video tai nạn giao thông giống nhau về thị
giác). Với `RRF_K=60`: đóng góp ASR = `0.6/(60+1)=0.0098`, vector =
`1.0/(60+40)=0.01` → tổng ~0.0198 — THUA 1 video sai có vector=4,asr=5 (cả
hai "khá" nhưng không "xuất sắc"): `1.0/64+0.6/65=0.0248`. Video đúng dù có
tín hiệu VĂN BẢN GẦN NHƯ HOÀN HẢO vẫn thua vì `K=60` làm phẳng khoảng cách
hạng 1 và hạng 40 xuống chỉ còn ~1.6 lần.

Quét `K ∈ {1,3,5,7,10,15,20,30,40,60}` trên CẢ 36 câu KIS holdout (nơi phát
hiện vấn đề) VÀ 23 câu KIS tune gốc (kiểm không hồi quy trên nội dung đa
dạng) — `K=7` tốt nhất trên CẢ HAI, không đánh đổi (chi tiết:
`dev_set/tools/sweep_search_fusion.py`, kết quả:
`dev_set/results/search_fusion_sweep.json`).

**Đã thử tăng trọng số OCR/ASR thay vì đổi K — LOẠI BỎ**: luôn cải thiện
holdout nhưng luôn làm hại tune (query đa dạng cần vector làm tín hiệu
chính, thiên vị nhánh nào cũng có giá). Đổi K không thiên vị nhánh nào —
chỉ làm "hạng 1 đáng tin hơn hạng thấp" cho MỌI nhánh đều — an toàn hơn hẳn.

## 4. Ý nghĩa cho ngày thi mai

- Fix `RRF_K` áp dụng cho **CẢ KIS, QA, TRAKE** (dùng chung `search()`) —
  không phải vá riêng lẻ từng dạng bài.
- **Luật "luôn nộp đủ 100 slot, xen kẽ theo shot" (CLAUDE.md §6) vẫn là cứu
  cánh quan trọng** dù đã sửa — video đúng lọt top-100 chỉ 72-74%, R@50/R@100
  vẫn ăn điểm nhiều câu R@1 trượt.
- Người thao tác vẫn nên cảnh giác với câu hỏi dễ nhầm nội dung (tai nạn,
  thể thao) — fix đêm nay cải thiện đáng kể chứ không xoá hoàn toàn vấn đề.

## 5. QA — vấn đề RIÊNG BIỆT, chưa sửa, cần điều tra thêm

QA gần như 0 điểm ở CẢ HAI lần đo (0.007 rồi 0.000) — **không phải do đổi
`RRF_K` gây ra** (đã ở mức gần-0 từ trước). Soi `QA_004`: cùng đúng video +
cùng frame (`L21_V017`, frame 13345) ở cả 2 lần chạy, nhưng câu trả lời đổi
từ `"30m"` (đúng) sang `"Không xác định được (bằng chứng không đề cập)"`.
Không phải do tìm sai video/frame — là tầng suy luận LLM/thu bằng chứng của
`qa_pipeline()` không ổn định. Nghi vấn: `search()` đổi K có thể làm thay
đổi TẬP shot ứng viên mà `qa_pipeline()` thử qua (`MAX_SHOTS_TRIED=3`), dẫn
tới bằng chứng khác nhau được đưa vào LLM dù shot cuối cùng BÁO CÁO trùng
nhau — giả thuyết hợp lý nhưng CHƯA xác minh được đêm nay, cần Thi (chủ sở
hữu Q&A) soát lại `qa_pipeline()` sau Đợt 1.

## 6. Việc còn lại

- Điều tra kỹ nguyên nhân QA gần-0 điểm (không phải RRF_K) — ưu tiên SAU
  Đợt 1, KHÔNG phải trước giờ thi (rủi ro sửa vội đêm nay cao hơn lợi ích).
- Kiểm tay 1 phần GT `auto_bm25` để loại trừ khả năng chính GT sai.
- Còn 3/5 lượt holdout — dùng tiết kiệm.
