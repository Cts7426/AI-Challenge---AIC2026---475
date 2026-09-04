# Đêm trước Đợt 3 — gộp nhánh, A/B holdout, chốt cấu hình

**Ngày** 03/09/2026 · **Nhánh** `integrate/dot3` → `main` · **Bộ đo**
`official_r1r2.jsonl`, bản dịch `llm()` đóng băng (`claude-opus-5`).

---

## 0. Kết luận một dòng

Cấu hình Đợt 3 **khái quát được**, đã xác nhận trên holdout chưa từng mở.
Không lùi gì cả. **Hết hạn mức holdout — từ đây đóng băng.**

---

## 1. Câu hỏi phải trả lời tối nay

Chiến dịch Đợt 3 tune toàn bộ trên 20 câu p1 và đạt Final mức video 0,80. Lượt
holdout đầu cho thấy p2 chỉ 0,6421 — thấp hơn hẳn. Hai cách giải thích:

- **(a)** cấu hình Đợt 3 học thuộc 20 câu p1 → phải lùi trước khi thi
- **(b)** p2 vốn khó hơn, cấu hình nào cũng tụt → giữ nguyên

Đây không phải chuyện học thuật. Nếu (a) đúng mà không phát hiện ra thì tối
04/09 chạy một cấu hình tệ hơn cả cấu hình Đợt 2 mà không ai biết.

### Đã loại trừ trước một cách giải thích rẻ tiền

Báo cáo 02/09 §1.2 cảnh báo cột frame thiên vị CLIP vì `frame_exact` của GT lấy
từ bài nộp đã chấm đúng, mà bài nộp đó chạy CLIP trên keyframe BTC. Nếu p1 trùng
keyframe BTC nhiều hơn p2 thì khoảng cách chỉ là hiện vật đo đạc. Kiểm bằng code:

| | trùng khít keyframe BTC |
|---|---|
| p1 | 8/20 (40%) |
| p2 | 7/19 (37%) |

Gần như nhau → **không giải thích được khoảng cách**. Phải đo thật.

## 2. Phép đo phân xử

Ba arm, chọn **trước** khi nhìn kết quả. Đây là phép CHỌN GIỮA CÁC CẤU HÌNH ĐÃ
ĐÓNG BĂNG, không phải quét tham số — quét trên holdout là biến holdout thành
tune set và mất luôn thứ duy nhất còn ước lượng được năng lực thật.

`scripts/ab_dot2_vs_dot3.sh` · artefact `dev_set/results/run_20260903_ab_{p1,p2}/`

| arm | pool | dual vector | ocr_probe | rerank | slot |
|---|---|---|---|---|---|
| `dot2` | 500 | không | không | không | `1x2,2x2,94x1` |
| `dot3` | 1500 | **có** | **có** | **có** | `50x2` |
| `dot3_slotcu` | 1500 | có | có | có | `1x2,2x2,94x1` |

### Kết quả — p1 (20 câu, tập ĐÃ TUNE)

| arm | Final_vid | R@1 | R@5 | ±5 | ±15 | ±40 |
|---|---|---|---|---|---|---|
| `dot2` | 0,6800 | 0,300 | 0,450 | 0,190 | 0,190 | 0,240 |
| `dot3` | **0,8000** | 0,550 | 0,700 | **0,250** | **0,300** | **0,330** |
| `dot3_slotcu` | 0,8000 | 0,550 | 0,700 | 0,170 | 0,190 | 0,270 |

### Kết quả — p2 (19 câu, HOLDOUT chưa từng mở) ← phép đo thật

| arm | Final_vid | R@1 | R@5 | R@20 | ±5 | ±15 | ±40 | video |
|---|---|---|---|---|---|---|---|---|
| `dot2` | 0,3895 | 0,105 | 0,210 | 0,368 | 0,042 | 0,074 | 0,084 | 15/19 |
| `dot3` | **0,6421** | 0,210 | 0,526 | 0,789 | 0,032 | **0,095** | **0,190** | 16/19 |
| `dot3_slotcu` | 0,6526 | 0,210 | 0,526 | 0,789 | 0,000 | 0,084 | 0,179 | 17/19 |

## 3. Đọc kết quả

**Giả thuyết (b) đúng. Không phải overfit.** Trên dữ liệu chưa từng thấy, cấu
hình Đợt 3 hơn cấu hình Đợt 2 ở mọi thước đáng kể:

- Final mức video **0,3895 → 0,6421** (+65%)
- R@5 **0,210 → 0,526** (+150%)
- ±40 **0,084 → 0,190** (+126%)

Khoảng cách p1 (0,80) ↔ p2 (0,64) là **độ khó câu hỏi**, không phải học thuộc.

**Bảng slot `50x2` cũng khái quát được:** thắng bảng cũ ở CẢ BA dung sai frame
trên CẢ p1 lẫn p2. Đánh đổi đã biết và chấp nhận: bảng cũ tìm ra nhiều hơn một
video (17/19 vs 16/19) và Final mức video nhỉnh hơn 0,01 — nhưng BTC chấm
`frame_id ∈ [s,e]`, đúng video mà sai frame vẫn 0 điểm.

### ⚠️ Điểm yếu thật, ghi ra để không tự lừa mình

Mức frame trên dữ liệu chưa từng thấy vẫn **thấp**: ±5 = 0,032. Máy tìm đúng
VIDEO khá tốt (16/19) nhưng **định vị FRAME trong video thì kém**. Đó chính xác
là chỗ bước Claude soi ảnh tối 04/09 tạo ra giá trị lớn nhất — đo được từ trước:
đầu bảng tự động đúng 7/17, Claude soi ảnh đúng 17/20. **Đừng cắt bước đó.**

Cũng vì thế: con số 0,6421 là **SÀN**, không phải dự báo điểm thi. Đợt 2 thật
đội đạt 13,6/15 là điểm SAU khi soi ảnh.

## 4. Câu hỏi 🔴 §7.1 — bản dịch của production

Báo cáo 02/09 lo production dùng `llm()` sẽ rơi về khoảng 0,37 (mức tiếng Việt
thô), và gọi đây là "con số quan trọng nhất còn thiếu". Đo thật, cùng 20 câu p1:

| nguồn `query_en` | Final_vid | R@1 | R@5 | ±5 | ±15 | ±40 |
|---|---|---|---|---|---|---|
| dịch TAY (bản đóng băng cũ) | 0,8300 | 0,400 | 0,900 | 0,230 | 0,270 | 0,340 |
| **dịch `llm()` claude-opus-5** | 0,8000 | **0,550** | 0,700 | **0,250** | **0,300** | 0,330 |

**Không phải thảm hoạ.** Mức video thấp hơn 0,03, nhưng R@1 **cao hơn** (11/20
đúng hạng 1 thay vì 8/20) và mức frame — thứ thật sự tính điểm — ngang hoặc
nhỉnh hơn. Mục 🔴 này đóng lại được.

## 5. Gộp nhánh Q&A của Thạch

`origin/codex/qa-last-3h` → `integrate/dot3`. 6 file xung đột, tất cả ở làn Q&A:
hai người sửa trùng cùng lô lỗi một cách độc lập trong cùng ngày 28/08.

Lấy bản `dot3` làm nền ở cả 6 file (siêu tập: `qa.py` +312 dòng so với +27;
`eval_official.py` 465 dòng so với 317 và chỉ bản này mới có các cờ chiến dịch
Đợt 3). Nhập lại ba thứ Thạch làm tốt hơn:

1. **Matcher câu từ chối.** Đo bằng code trước khi gộp: bản `dot3` để LỌT 9
   surface ngắn ("không biết", "we don't know") và **LOẠI NHẦM 2 đáp án thật**
   ("Không thấy mưa", "Không có người trong ảnh") vì lưới từ khoá quá rộng.
   Đổi sang thuật toán Thạch: phủ định phải đứng ĐẦU + từ bằng chứng hẹp + danh
   sách ngắn/đích danh. Hợp đồng test hợp nhất 22 ca (15 chặn / 7 giữ), qua trọn.
   *Loại nhầm đắt hơn bỏ sót: bỏ sót thì nộp một câu từ chối, loại nhầm thì vứt
   một đáp án ĐÚNG.*
2. `tests/test_manual_qa_override.py` — 3 test bản `dot3` không có.
3. `BUILD_TASKS.md` bản 887 dòng có phần "Chiến dịch Đợt 3" (bản trên `main` chỉ
   535 dòng, không có) → giờ mới tick được R3.K1–K5.

**Hai lỗi trong code Thạch đã sửa khi gộp:** test gắn cứng
`.venv/Scripts/python.exe` (layout Windows) → chết khi thu thập trên macOS; và
fixture tự ghép đường dẫn keyframe, thiếu một cấp `keyframes_L30/` mà kho BTC
thật có → đổi sang `resolve_frame_path()` đúng như AGENTS.md quy định.

**Một hợp đồng đổi có chủ ý:** Thạch đòi ném `QANoValidHypothesisError` khi hết
đáp án; `dot3` cố ý bỏ đường đó vì nó để CẢ CÂU trống trong gói ZIP. Giữ `dot3`
— CLAUDE.md §6 luật 1: luôn nộp đủ 100 slot, bỏ trống là 0 chắc chắn.

Kiểm trực tiếp: **mọi file trên đường chạy KIS giống HỆT bản trước gộp.** Merge
chỉ đụng Q&A, test và tài liệu. Xác nhận thêm bằng phép đo — p1 tái hiện chính
xác từng chữ số so với commit `d54335a`.

Test: **826 → 851 passed**, 2 skipped.

## 6. Ba việc hạ tầng

1. **Bẫy `.venv/bin/python` — đã dẹp.** Nó trỏ về Python **3.9.6**
   (CommandLineTools) thiếu `pymilvus`/`elasticsearch`, trong khi thư viện thật
   nằm ở `.venv/lib/python3.14`. Chạy preflight bằng `python` ra **ĐẠT 9 · HỎNG 8**
   — kể cả một lỗi giả `write_text() newline` vốn chỉ là API 3.9 không có.
   Mà `exam.py` truyền `sys.executable` xuống mọi subprocess nên chọn sai một
   lần là hỏng cả buổi. Đã trỏ lại `python`/`python3` → `python3.14` và sửa
   `pyvenv.cfg`. Giờ `python` và `python3.14` cho kết quả như nhau: **ĐẠT 18 · HỎNG 0**.

2. **`scripts/warmup.py`.** Đo được: CLIP 2,8s · **SigLIP2 22,4s** · làn KIS 1,4s.
   SigLIP2 chiếm gần hết chi phí nạp nguội.
   ⚠️ Ghi rõ để không hiểu nhầm: script này **không** làm lô KIS thật nhanh hơn.
   `exam.py run` chạy cả lô trong MỘT subprocess `run.py` nên nó tự trả phí nạp
   model **một lần cho cả buổi** rồi ~1,4s/câu. Giá trị thật là biết TRƯỚC 19:30
   rằng Milvus / ES / cả hai encoder còn sống.

3. **Holdout** — xem §2. Đã cạn.

## 7. Một lỗi nguồn gốc đã sửa

`eval_official.py` ghi `"rerank_top50": bool(args.rerank)` — tức ghi **cờ dòng
lệnh**, không phải **giá trị thực thi**. Không truyền cờ nào thì nó ghi `false`
trong khi `search()` nhận `None` rồi đọc `data/config/rerank.py`, mà file đó
`ENABLED=True` từ 02/09. Nghĩa là artefact khai "rerank tắt" cho những lượt
rerank **thực sự chạy**. Số thì đúng, nhãn thì sai — đúng lớp lỗi im lặng mà bất
biến 8 sinh ra để chặn. Đã đổi sang ghi giá trị thực thi, cho cả
`video_prior_alpha`.

## 8. Cấu hình chốt cho tối 04/09 — KHÔNG ĐỔI NỮA

```
VECTOR_BACKEND       clip            (SigLIP2 là nhánh phụ, không thay chính)
branches             vector_siglip2=True · ocr_probe=True
RRF_K                7
KIS_CANDIDATE_MULT   15              (pool 1500/nhánh)
BRANCH_WEIGHTS       vector_siglip2 = 1.0
rerank top-50        BẬT
SLOT_BUDGET          [(50, 2)]
video_prior          TẮT             ← đạt top-10 1,00 mức video nhưng ±40 tụt
                                       0,36 → 0,14. Đừng bật.
```

Nút quay đầu: `docs/evaluation/2026-09-02-kis-r3-k1-k5.md` §8. Collection
`keyframes` (CLIP) không suy suyển một vector nào.

## 9. Việc cho tối 04/09

1. Trước 19:30: `.venv/bin/python scripts/warmup.py` → phải ra SẴN SÀNG.
2. Gõ đủ đường dẫn `.venv/bin/python`, đừng `activate` rồi gõ `python` trần.
3. **Dành thời gian cho bước soi ảnh.** Đó là chỗ mức frame được cứu, và mức
   frame là chỗ đang yếu nhất trên dữ liệu chưa từng thấy.
4. Không chỉnh tham số. Hết holdout rồi.
