# TRAKE — vá lưới an toàn C4.4 + mở rộng bộ đề + tune công thức xếp hạng

> **20/08/2026 · Công Lý** (theo yêu cầu kiểm tra toàn diện TRAKE trước Đợt 1
> 21/08) · dev set `tune` gốc (2 câu TR01/TR02) + bộ đề tổng hợp mới 6 câu
> (STR01-06) · Kế hoạch đầy đủ: `dev_set/tools/sweep_trake_config.py`
>
> ⚠️ **Cập nhật 22:xx cùng đêm**: `RRF_K` (search.py, dùng chung cho TRAKE)
> đổi 60→7 sau khi kiểm tra bộ đề KIS/QA/TRAKE của đồng đội (xem
> `reports/holdout_teammate_check.md`) — TRAKE_MIN_BLEND_LAMBDA/
> TRAKE_ASR_CONTEXT_BONUS_WEIGHT bên dưới đã được QUÉT LẠI cho khớp K=7 mới
> (`TRAKE_ASR_CONTEXT_BONUS_WEIGHT` đổi 0.5→1.0). Số liệu λ/w trong báo cáo
> này là của K=60 (đã lỗi thời cho riêng phần trọng số) — số liệu K=7 mới
> nhất nằm trong comment trực tiếp ở `data/config/search_weights.py` và
> `reports/holdout_teammate_check.md`. TR01/TR02 SAU khi đổi K=7: Final
> 0.517→**0.642** (tốt hơn nữa, không hồi quy).

**Kết luận:**
1. Vá xong lưới an toàn C4.4 (đã bị xoá khỏi git khi gộp DP 16/08) — gọn
   trong `backend/tasks/trake.py`, không đụng file đã đóng băng (`run.py`,
   `run_minimal.py`, `dev_set/tools/run_evaluation.py`).
2. Mở rộng dev-set TRAKE từ 2 → 8 câu (giữ 2 câu người viết làm chuẩn vàng,
   6 câu tổng hợp bằng VLM để có mẫu đủ lớn kiểm chứng thay đổi công thức).
3. Đổi `TRAKE_CANDIDATES_PER_EVENT` 6→20 và thêm trộn "điểm vị trí yếu nhất"
   vào công thức xếp hạng (`TRAKE_MIN_BLEND_LAMBDA=2.0`) — đo thật: Final
   trung bình 2 câu người viết **0.450 → 0.517** (TR02: hạng video 7→5,
   R@5 0.0→0.667), tập 8 câu gộp **0.172 → 0.209**. Không câu nào tệ đi.
4. `TRAKE_MIN_FRAME_GAP` giữ nguyên 30 — quét 10/20/30 không thấy khác biệt
   trên dev-set hiện có (xem §4, làm rõ nhầm lẫn với "cửa sổ đáp án <10 frame"
   của đề thật — hai tham số khác nhau).
5. **Bug phát hiện khi thử 1 câu tin tức thật (§6) — ĐÃ SỬA XONG.** DP chọn
   nhầm frame ở video ĐÚNG khi câu sự kiện quá chung chung, trùng với 1 tin
   KHÁC trong cùng video (bản tin nhiều mục). "Phạt khoảng cách frame" —
   KHÔNG dùng được (đo thử: sẽ phá TR01, xem §6.3). Fix đúng: cộng bonus
   "cộng hưởng nội dung ASR" có trọng số IDF (`TRAKE_ASR_CONTEXT_BONUS_WEIGHT=0.5`,
   `backend/tasks/trake.py::_apply_asr_context_bonus`) — chỉ ảnh hưởng bước
   DP CHỌN FRAME trong 1 video, KHÔNG ảnh hưởng điểm XẾP HẠNG GIỮA CÁC VIDEO
   (tách 2 việc bằng `_orig_score`, xem §6.4-6.6). Đo thật bằng code sản
   xuất (không mock): cả 4 frame của câu tai nạn giao thông giờ nằm ĐÚNG
   trong đoạn ASR xác nhận [11691,13343] (trước đó sự kiện 4 = frame 14760,
   thuộc 1 tin khác hẳn). Tập 8 câu dev-set CẢI THIỆN (Final 0.209→0.220,
   R@1 0.094→0.125), 2 câu người viết TR01/TR02 GIỮ NGUYÊN 0.517 (không đổi).

---

## 1. Vì sao làm việc này

Bug Minh Hoàng báo cáo (ảnh keyframe) đã fix riêng (xem commit trước). Khi
kiểm tra toàn diện TRAKE để "đảm bảo tối đa điểm số" trước Đợt 1, phát hiện
thêm 2 vấn đề không liên quan tới bug đó:

- **`backend/tasks/trake_fallback.py` (C4.4 — lưới an toàn bắt buộc theo
  BUILD_TASKS, "LÀM SỚM, ĐỪNG ĐỢI THẤT BẠI") đã bị xoá** khi gộp code thành
  DP hợp nhất (commit `638495d`, 16/08). Xác nhận trực tiếp trong
  `run.py::main()`: nếu `parse_events()` (gọi LLM) hoặc mọi search sự kiện
  đều lỗi lúc thi thật → `giai_mot_query()` raise → **query đó không được
  ghi checkpoint, biến mất hoàn toàn khỏi bài nộp** (0 tuyệt đối mọi R@k).
- Dev-set TRAKE chỉ có **2 câu** (TR01/TR02) — không đủ để kiểm chứng bất kỳ
  thay đổi công thức/tham số nào.

## 2. Lưới an toàn C4.4 — gọn trong `backend/tasks/trake.py`

Kiến trúc đã đổi từ 16/08 (1 DP hợp nhất thay vì stage1/stage2 tách rời) nên
bản `trake_fallback.py` cũ (dùng `filter_video_id`, giả định có video hạng 1
sẵn) không còn khớp — viết lưới an toàn MỚI, gọn trong chính `trake.py`:

- `parse_events()`: LLM lỗi (mạng/API/JSON hỏng) hoặc tách <2 sự kiện → rơi
  về `_split_events_heuristic()` — tách bằng dấu câu/liên từ tuần tự tiếng
  Việt (". ", "rồi", "sau đó", "tiếp theo", "kế đó/tiếp", "xong", "cuối
  cùng", ";", ",", cuối cùng chẻ đôi theo số từ). **Không bao giờ raise cho
  câu không rỗng.** Kiểm thật: TR01/TR02 tách **khớp 100%** với
  `event_descs` gốc kể cả khi giả lập LLM mất mạng hoàn toàn.
- `trake_search()`: nếu **toàn bộ** N search sự kiện trả rỗng (ES/Milvus
  chết hoàn toàn) → thử 1 lần search cứu cánh bằng câu ghép toàn bộ sự kiện
  (chấp nhận CLIP có thể cắt cụt do >77 token — có ứng viên còn hơn 0 tuyệt
  đối). Chỉ kích hoạt khi rỗng hoàn toàn, không đụng đường chạy bình thường.
- 8 test mới (`tests/test_trake.py`), 569/569 test toàn repo xanh.

**Không đụng** `run.py`/`run_minimal.py`/`dev_set/tools/run_evaluation.py`
(mốc đóng băng tự ghi trong docstring `giai_mot_query()`), `backend/slot/
allocator.py::_allocate_trake` (đã xác nhận bị bypass hoàn toàn trên đường
chạy thật TRAKE, sửa không đổi điểm).

## 3. Mở rộng bộ đề: 2 → 8 câu

Không thể xem video trực tiếp để viết câu như người thật. Bù bằng cách sinh
câu TỔNG HỢP có GT **chắc chắn đúng**: dùng 49GB keyframe ảnh thật đã trích +
`shots.parquet` (ranh giới frame chính xác tuyệt đối) + VLM (`llm()` với
ảnh) tự mô tả từng shot.

`dev_set/tools/generate_trake_synthetic.py`: chọn 6 video L26 khác TR01/TR02
(cùng batch video nấu ăn), mỗi video 2-5 shot cách đều **sau 20 giây đầu**
(lần chạy thử đầu tiên phát hiện 20 giây đầu là logo/bumper chương trình lặp
lại y hệt nhau giữa các video — bỏ qua để tránh câu vô nghĩa), gọi VLM sinh
caption ngắn mỗi shot → ghép thành câu TRAKE, GT = chính xác ranh giới shot.

Ghi riêng `dev_set/queries/synth_trake.jsonl` +
`dev_set/ground_truth/synth_gt.jsonl` — **KHÔNG động vào `tune_trake.jsonl`/
`tune_gt.jsonl`** (2 câu người viết giữ nguyên làm chuẩn vàng). CLI
`run_evaluation.py --split` chỉ nhận `tune`/`holdout` (không sửa file đã
đóng băng để thêm lựa chọn) — lúc đo phải **tạm gộp** 2 file trên vào bản
sao lưu của `tune_trake.jsonl`/`tune_gt.jsonl` (namespace `STR*` rõ ràng),
chạy `--split tune`, rồi **khôi phục lại nguyên trạng** 2 file gốc ngay sau
khi lấy xong số đo — xác nhận bằng `git diff` sạch.

⚠️ **Rủi ro đã ghi nhận, KHÔNG như dự đoán ban đầu**: lo ban đầu là câu VLM tự
mô tả sẽ "dễ" hơn câu thi thật. Đo thật cho thấy NGƯỢC LẠI — 3/6 câu tổng hợp
(STR01/02/05) chấm 0 điểm dù **video đúng xếp hạng 1**, vì show nấu ăn có
nhiều khoảnh khắc THỊ GIÁC GIỐNG NHAU lặp lại (gà sống xuất hiện nhiều lần
trong 1 tập) — CLIP tìm ra MỘT khoảnh khắc khớp caption nhưng không phải
ĐÚNG khoảnh khắc tôi chọn làm GT. Đây là hạn chế thật của phương pháp sinh
GT tự động (không phải bug hệ thống) — nhưng đồng thời cũng lộ ra vấn đề
RECALL trong-video của pipeline (xem §4). Mọi số liệu trong báo cáo tách
riêng nhóm **người viết (n=2)** và **gộp (n=8)**, không gộp mập mờ.

## 4. Chẩn đoán + tune

### 4.1 TR02: video đúng hạng 8/100

`L26_V458` (đúng) score=0.167, trong khi 7 video SAI cũng đạt
`has_full_order=True, n_hit_events=3` nhưng **tổng điểm cao hơn** (0.29→0.17)
— video sai thắng vì 1 vị trí khớp rất mạnh, các vị trí khác yếu, nhưng
TỔNG vẫn thắng video khớp đều cả 3 vị trí. (Đính chính: "điểm" ở đây là điểm
**hợp nhất RRF** — `1/(RRF_K+rank)` — KHÔNG phải cosine CLIP thô như mô tả
ban đầu trong kế hoạch.)

### 4.2 STR01/02/05: video đúng hạng 1 nhưng frame sai hoàn toàn

Kiểm trực tiếp bằng `search()`: với STR01, GT window sự kiện 1 là
`[644,751]` nhưng **top-6 ứng viên trong đúng video KHÔNG có cái nào rơi vào
khoảng đó** (gần nhất: frame 3840-5638, điểm 0.017-0.024). Đây là vấn đề
**recall trong video** — GT frame chưa từng lọt vào rổ ứng viên của DP, không
phải lỗi thuật toán xếp chuỗi.

### 4.3 Quét tham số (`dev_set/tools/sweep_trake_config.py`)

Fetch raw hits 1 lần (đỡ tốn mạng), quét cục bộ 45 tổ hợp
(`candidates_per_event` × `min_gap` × công thức điểm):

| Tham số | Giá trị quét | Kết quả |
|---|---|---|
| `TRAKE_CANDIDATES_PER_EVENT` | 6 / 12 / 20 | 20 tốt nhất (nới rổ ứng viên → giảm bớt vấn đề §4.2) |
| `TRAKE_MIN_FRAME_GAP` | 10 / 20 / 30 | **Không khác biệt** trên dev-set hiện có |
| công thức điểm | sum (gốc) / min_blend λ∈{0.5,1,2} / geomean | `min_blend λ=2.0` tốt nhất |

Cấu hình cuối (không tệ hơn baseline trên tập người viết, tối đa điểm tập gộp):

| | k=6,gap=30,sum (**baseline cũ**) | k=20,gap=30,min_blend λ=2.0 (**mới**) |
|---|---|---|
| Final trung bình — người viết (n=2) | 0.450 | **0.517** |
| R@1 trung bình — người viết (n=2) | 0.250 | 0.250 |
| Final trung bình — gộp (n=8) | 0.172 | **0.209** |

Xác nhận lại bằng code THẬT (không phải sweep song song): chạy
`run_evaluation.py --split tune` (gồm cả STR*) trước/sau — khớp đúng dự
đoán của sweep. TR02: hạng video 7→5, R@5 0.0→0.667, Final 0.4→0.533.
Không câu nào tệ đi.

### 4.4 Làm rõ nhầm lẫn `MIN_FRAME_GAP` vs "cửa sổ đáp án <10 frame"

`reports/slot_tuning.md` từng ghi đề thật có cửa sổ đáp án TRAKE "thường
dưới 10 frame", nghi vấn `TRAKE_MIN_FRAME_GAP=30` quá lớn. Quét thực tế cho
thấy đây là **2 tham số khác nhau, cùng đơn vị "frame" nên dễ nhầm**:

- `TRAKE_MIN_FRAME_GAP` — khoảng cách tối thiểu giữa 2 VỊ TRÍ SỰ KIỆN mà DP
  chọn, để tránh CLIP nhầm 2 sự kiện khác nhau thành cùng 1 khoảnh khắc.
- "Cửa sổ đáp án <10 frame" — ĐỘ RỘNG `[s,e]` mà BTC chấm đúng/sai cho MỖI
  vị trí, một con số **do BTC quyết định**, không phải tham số code nào điều
  chỉnh được.

Không đổi `MIN_FRAME_GAP`. Ghi nhận rủi ro thật: GT dev-set hiện có (kể cả
mới sinh) đều rộng hơn nhiều mức "<10 frame" của đề thật (55-320 frame) —
**R-score dev-set có thể lạc quan hơn thực tế thi**, không phải bug, cần ghi
nhớ khi diễn giải số liệu.

## 5. Rủi ro còn lại (chưa xử lý, để đợt sau)

- Bộ đề vẫn nhỏ (n=8) — 6/8 là tổng hợp, chỉ 2 là chuẩn vàng người viết.
  Nên tiếp tục thu thập câu TRAKE thật ở Đợt 2-3.
- Vấn đề recall trong-video (§4.2) chưa có hướng sửa rõ ràng đêm nay — tăng
  `TRAKE_CANDIDATES_PER_EVENT` giúp một phần nhưng gốc rễ là chất lượng
  embedding/caption cho khoảnh khắc lặp lại thị giác, cần "tầng tinh" khác
  (vd OCR/ASR neo thời gian) — để Thi cân nhắc sau Đợt 1.
- Heuristic split (`_split_events_heuristic`) chưa từng chạy thật lúc LLM
  lỗi lúc thi — chỉ kiểm bằng giả lập. Nên theo dõi log `[cảnh báo]
  parse_events()` nếu xảy ra trong buổi thi thật.
- Bonus cộng hưởng ASR (§6, `TRAKE_ASR_CONTEXT_BONUS_WEIGHT=0.5`) mới tune
  trên n=8+1, đánh đổi thật (STR06 -0.16), và video ĐÚNG có thể rớt hạng dù
  frame đã đúng (bằng chứng yếu hơn nhưng trung thực hơn) — theo dõi thêm ở
  Đợt 2-3 khi có nhiều câu TRAKE tin tức thật hơn để tune lại `w` chắc chắn hơn.

## 6. Vấn đề phát hiện + ĐÃ SỬA — DP nhảy sang tin/đoạn KHÁC trong cùng video

Thử 1 câu TRAKE thật do người dùng cung cấp (4 sự kiện, video nghi ngờ
`L21_V024`, nội dung tai nạn giao thông) — kết quả: hạng 8/100, 4 frame chọn
hầu như sai.

### 6.1 Chẩn đoán bằng ASR — xác nhận video ĐÚNG, chỉ 1/4 frame sai

`L21_V024` **CHÍNH LÀ video đúng**: đoạn ASR frame 11691–13343 khớp gần như
nguyên văn 4 sự kiện trong câu hỏi (số liệu cụ thể, biển số, tên nạn nhân,
tên đường — không thể là trùng hợp). 3/4 frame DP chọn (12630, 12888, 13239)
nằm sát/trong đoạn ASR này. **Frame thứ 4 (14760) sai hoàn toàn** — thuộc
đoạn ASR về MỘT TIN KHÁC (vụ tịch thu hàng hoá tỉnh Phú Yên), vì sự kiện 4
("Lực lượng chức năng có mặt tại hiện trường để điều tiết giao thông") dùng
cụm từ quá chung chung, lặp lại ở nhiều tin trong cùng video bản tin nhiều
mục ("60 giây" — mỗi video là NHIỀU câu chuyện độc lập nối lại, khác hẳn
video nấu ăn L26 chỉ có MỘT câu chuyện xuyên suốt).

Kiểm trực tiếp rổ 20 ứng viên sự kiện 4 của `L21_V024`: ứng viên ĐÚNG (frame
12888, điểm 0.0101) **có sẵn trong rổ**, nhưng DP chọn frame 14760 (điểm
0.0185, cao hơn) vì DP chỉ tối đa **tổng điểm**, không có khái niệm "gắn với
mạch nội dung của các vị trí đã chọn".

### 6.2 Hạng 8/100 — mơ hồ thị giác thật, không phải bug

Video hạng 1 (`L21_V005`) **cũng là một bản tin tai nạn giao thông ban đêm
khác, cùng kênh HTV9, cùng chương trình "60 giây"** (xác nhận bằng VLM đọc
trực tiếp 4 keyframe). Kho L21/L22 có nhiều bản tin tai nạn nhìn giống nhau
về thị giác (xe máy đổ, cảnh sát, ban đêm) — CLIP thuần thị giác không đủ để
phân biệt "đúng vụ này" với "một vụ tương tự". Đây là giới hạn thật của tìm
kiếm thị giác trên loại nội dung này, không sửa được bằng công thức xếp hạng.

### 6.3 Vì sao KHÔNG sửa bằng "phạt khoảng cách" trong DP

Ý tưởng đầu tiên: thêm số hạng phạt vào DP khi khoảng cách giữa 2 vị trí
liên tiếp quá lớn, để tránh nhảy sang đoạn xa. Đo thử trước khi code:

| | Khoảng cách các vị trí (frame) | % độ dài video |
|---|---|---|
| TR01 (nấu ăn, ĐÚNG) | 1720 / 499 / 211 | **22.5%** / 6.5% / 2.8% |
| L21_V024 sự kiện 4 (SAI) | 258 / 351 / 1521 | 0.9% / 1.2% / **5.1%** |

Khoảng cách "sai" (5.1% video) **nhỏ hơn** khoảng cách hợp lệ lớn nhất của
TR01 (22.5% video). Bất kỳ ngưỡng phạt nào đủ mạnh để chặn 5.1% sẽ phá luôn
TR01 (video nấu ăn có sự kiện cách xa nhau hợp lệ). **Kết luận: đây không
phải vấn đề khoảng cách, mà là vấn đề MẠCH NỘI DUNG** — video nấu ăn là MỘT
câu chuyện xuyên suốt (khoảng cách xa vẫn hợp lệ), bản tin nhiều mục là
NHIỀU câu chuyện độc lập nối lại (nhảy sang đoạn khác dù gần vẫn sai). Không
có ngưỡng khoảng cách đơn thuần nào phân biệt được 2 trường hợp này —
**KHÔNG áp dụng phương án này.**

### 6.4 Hướng sửa — vì sao KHÔNG dùng `seg_id`, dùng nội dung ASR trực tiếp

Ý định ban đầu: ưu tiên ứng viên nằm cùng đoạn ASR (`seg_id` trong
`asr.parquet`). Kiểm tra thật trước khi code: `seg_id` chỉ là **đoạn CẮT
TRANSCRIPT kỹ thuật** (~500-600 frame/đoạn, đếm liên tục 0..N cho cả video),
KHÔNG phải ranh giới chủ đề — đúng đoạn tai nạn thật trải dài qua NHIỀU
`seg_id` liền nhau (16,17,18), còn tin Phú Yên nằm ở `seg_id` 21. "Cùng
`seg_id`" sẽ SAI cả 2 chiều: coi 16 với 18 là khác đoạn (dù cùng 1 chuyện),
và không có gì ngăn 1 tin ngắn trùng khít 1 `seg_id`.

**Fix thật dùng NỘI DUNG văn bản ASR trực tiếp, không dùng ranh giới `seg_id`:**
với mỗi ứng viên, đếm (có trọng số IDF) từ khoá của CÁC SỰ KIỆN KHÁC xuất
hiện trong văn bản ASR bao phủ frame đó — tín hiệu "cộng hưởng nội dung",
không phụ thuộc ranh giới đoạn nào cả.

- `_significant_tokens()`: bỏ dấu, hạ thường, lọc hư từ + từ <3 ký tự.
- `_build_token_weight()`: trọng số IDF **tính trên chính rổ ứng viên của
  câu hỏi này** (không cần bảng tần suất toàn kho dữ liệu) — từ xuất hiện ở
  càng nhiều ứng viên (chung chung trong NGỮ CẢNH câu hỏi, vd "cắt"/"nước"
  lặp khắp video nấu ăn) → trọng số càng thấp.
  - ⚠️ Đo thật: đếm thô (không IDF) làm SẬP điểm 8/8 câu (R@1→0.000) —
    buộc phải có bước này, không phải tinh chỉnh thêm.
- `_cross_event_bonus()`: tổng trọng số từ khoá trùng, LOẠI từ khoá của
  chính sự kiện đang xét (`own_position`).
- **Tách 2 việc — quan trọng nhất**: bonus chỉ cộng vào điểm DÙNG ĐỂ DP CHỌN
  FRAME trong 1 video (`c["score"]`), điểm DÙNG ĐỂ XẾP HẠNG GIỮA CÁC VIDEO
  vẫn dùng điểm GỐC chưa cộng bonus (`c["_orig_score"]`). Đo thật: gộp chung
  cả 2 việc làm TR02 dao động hạng qua đúng ranh giới R@5 (5↔6) vì bonus
  tình cờ ưu ái 1 video SAI khác nhiều hơn — bonus chỉ nên "chọn đúng frame
  trong video này", việc "video nào thắng video nào" đã có
  `TRAKE_MIN_BLEND_LAMBDA` lo riêng.

Quét `TRAKE_ASR_CONTEXT_BONUS_WEIGHT` trên 8 câu dev-set + câu tai nạn giao
thông thật (`dev_set/tools/sweep_trake_asr_bonus.py`):

| w | Final 8 câu | R@1 8 câu | Final người viết (2) | frame4 tai nạn |
|---|---|---|---|---|
| 0.0 (tắt) | 0.209 | 0.094 | 0.517 | 14760 — SAI (tin khác) |
| 0.3 | 0.209 | 0.094 | 0.517 | 13239 — ĐÚNG, nhưng hạng video rớt 8→23 |
| **0.5 (chọn)** | **0.220** | **0.125** | **0.517** | 13239 — ĐÚNG |
| 0.8+ | 0.200 | 0.125 | 0.392 (giảm) | 13239 — ĐÚNG |

Chọn **w=0.5**: cải thiện tập 8 câu, KHÔNG đổi 2 câu người viết (chuẩn
vàng), sửa đúng frame4. Đánh đổi thật (không giấu): trong 8 câu, STR04 cải
thiện mạnh (+0.25) nhưng STR06 giảm (-0.16) — soi kỹ STR06 không thấy bug
mới, chỉ là cùng cơ chế đôi khi ưu ái nhầm 1 video khác ở mức nhẹ hơn TR02
trước đó. Hạng của video tai nạn giao thông RỚT (8→21) dù frame đã đúng —
đây là đánh đổi có chủ đích: sửa xong, video này dùng đúng điểm GỐC (yếu
hơn) của frame4 thay vì điểm bị thổi phồng bởi bằng chứng sai — "đúng nhưng
hạng thấp hơn" nhất quán hơn "sai nhưng hạng cao", dù không phải lúc nào
cũng cho R-score cao hơn tuỳ vị trí GT thật (không có GT chính xác cho câu
này để tính rscore đầy đủ, chỉ đánh giá định tính theo đoạn ASR).

Xác nhận lại bằng `trake_search()` thật (không mock gì): cả 4 frame
(12630, 12888, 13067, 13239) đều nằm trong đúng đoạn ASR [11691,13343].

Chạy lại `run_evaluation.py --split tune` với cấu hình CUỐI CÙNG (kết quả
lưu `dev_set/results/run_20260820_2101/`, 0/36 lỗi) — khớp đúng dự đoán của
sweep: TR01 Final=0.500 (hạng 1), TR02 Final=0.533 (hạng 5, giữ nguyên mức
đã sửa buổi sáng), avg Final 8 câu TRAKE = **0.220**, avg R@1 = **0.125**.

### 6.5 Test mới

12 test thêm vào `tests/test_trake.py` (tổng 39 test file này, 579 test
toàn repo) — `_significant_tokens`, `_build_token_weight` (kiểm đúng công
thức 1/df), `_cross_event_bonus` (từ hiếm đóng góp nhiều hơn từ chung
chung), `_apply_asr_context_bonus` (tắt khi weight=0/không có events, không
mutate dict gốc, tách `_orig_score`), `_localize_in_video` (ưu tiên đúng
ứng viên cộng hưởng thay vì điểm thô cao hơn — mô phỏng ĐÚNG kịch bản bug
thật).
