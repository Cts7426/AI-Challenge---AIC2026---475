# D4.1 — Chỉnh bảng chia slot theo dữ liệu

> **19/08/2026 · Minh Hoàng** · dev set `tune` (23 KIS + 5 QA + 2 TRAKE)
> Nguyên liệu: `dev_set/results/run_20260818_1739/candidates.jsonl` (commit `5b7b10c`)
> Công cụ: `app/score_simulator.py` (D3.5)

**Kết luận:** `SLOT_BUDGET` đổi từ `[(1,6), (4,4), (10,2), (58,1)]` (phủ 73 shot)
sang **`[(100, 1)]`** — 100 shot, mỗi shot 1 slot.

---

## 1. Vì sao báo cáo này tồn tại

Commit `5b7b10c` mang message `tune(D4.1): expand SLOT_BUDGET` đã đổi bảng ngân sách
**trước khi có số đo nào**. Việc đầu tiên của D4.1 là trả món nợ đó: đo, rồi mới chốt.

---

## 2. Bằng chứng từ tài liệu BTC — cửa sổ đáp án HẸP hơn ta tưởng

Đọc `Thong tin vong So tuyen AIC2026.pdf` (mục 2.1). Ba con số duy nhất BTC đưa ra:

| Dạng bài | Cửa sổ trong ví dụ | Độ rộng |
|:---|:---|---:|
| Textual KIS | `[500, 510]` | **11 frame** |
| Q&A | `[800, 900]` | 101 frame |
| TRAKE | `[95,105] · [145,155] · …` + câu *"thường rất ngắn, thông thường **dưới 10 frame**"* | ~10 frame |

Đối chiếu: **shot median của mình là 69 frame** (đo trên `shots.parquet`, max 1795).

Nghĩa là với KIS, cửa sổ đáp án **hẹp hơn shot khoảng 6 lần**. "Trúng shot" KHÔNG
đồng nghĩa với "trúng đáp án". Đây là lần đầu ta có con số thay vì giả định — trước
đó `slot_budget.py` ghi `# TODO: BTC — độ rộng cửa sổ chưa công bố`.

> ⚠️ Vẫn chưa phải luật thành văn: BTC cho ví dụ, không cho quy tắc. Nhưng ví dụ có
> số vẫn hơn hẳn giả định không có gì.

---

## 3. Bằng chứng đo được — shot đúng nằm ở hạng nào

```
python -m app.score_simulator shotrank \
    --candidates dev_set/results/run_20260818_1739/candidates.jsonl \
    --gt dev_set/ground_truth/tune_gt.jsonl
```

Đây là câu hỏi đặc tả D4.1 bắt phải trả lời trước khi động vào bảng. Kết quả trên
23 câu KIS:

| Hạng của shot đúng | Số câu |
|:---|---:|
| 1 | 3 |
| 2 – 5 | 3 |
| 6 – 20 | 6 |
| 21 – 50 | 4 |
| 51 – 73 | 1 |
| **74 – 100** | **2**  ← K18 (hạng 80), K01 (hạng 95) |
| không có trong 100 ứng viên | 4 |

Trung vị **10**, lớn nhất **95**.

**Hai kết luận, hai địa chỉ khác nhau:**

1. **2 câu bị chính bảng ngân sách giết.** Bảng cũ phủ 73 shot → K18 và K01 có shot
   đúng nằm trong danh sách ứng viên nhưng **không được cấp slot nào**. Trượt chắc
   chắn, và không phải lỗi của tầng search.
2. **4 câu (K03, K06, K08, K11) không có shot đúng trong 100 ứng viên.** Bảng slot
   bất lực — đây là việc của tầng search, đừng tune slot cho chúng.

---

## 4. Số đo — 7 bảng, hai phương pháp độc lập

### 4.1 `replay` — chạy lại trên nguyên liệu thật của dev set

```
  BẢNG             n   Final     R@1     R@5    R@20    R@50   R@100
  ──────────────────────────────────────────────────────────────────
  đỉnh2 97sh      23   0.487   0.130   0.261   0.522   0.696   0.826
  rất rộng 1×     23   0.487   0.130   0.261   0.522   0.696   0.826
  đỉnh4 94sh      23   0.478   0.130   0.261   0.522   0.696   0.783
  hiện tại 73sh   23   0.470   0.130   0.261   0.522   0.696   0.739   ← bảng cũ
  cân    5×5      23   0.461   0.130   0.261   0.522   0.696   0.696
  rộng  10×3      23   0.461   0.130   0.261   0.522   0.696   0.696
  sâu    2×20     23   0.365   0.130   0.261   0.478   0.478   0.478
```

**R@1 → R@50 GIỐNG HỆT NHAU ở cả 7 bảng.** Toàn bộ chênh lệch nằm ở R@100, tức đúng
hai câu ở mục 3. Đọc thẳng: trên dev set này, bảng slot chỉ mua được **độ phủ**,
không mua được gì khác.

### 4.2 `sweep` — quét giả định trên shot THẬT, không cần dev set

Chạy tại **đúng phân bố hạng đo được ở mục 3** (`--ranks 1,3,5,6,8,10,16,20,29,31,39,40,73,80,95`),
50 kịch bản, 100 shot ứng viên:

```
  BẢNG                w=5     w=11     w=20     w=50    w=101
  ───────────────────────────────────────────────────────────
  sâu    2×20       0.103    0.142    0.241    0.266    0.284
  hiện tại 73sh     0.100    0.211    0.332    0.375    0.411   ← bảng cũ
  cân    5×5        0.109    0.194    0.326    0.366    0.401
  rộng  10×3        0.094    0.174    0.320    0.359    0.394
  đỉnh4 94sh        0.097    0.276    0.342    0.392    0.431
  đỉnh2 97sh        0.095    0.281    0.349    0.400    0.439
  rất rộng 1×       0.100    0.328    0.355    0.407    0.450
```

`w=11` là cột quan trọng nhất — đó là độ rộng trong ví dụ KIS của BTC (mục 2).
Phủ rộng thắng ở **mọi** cột trừ `w=5`, nơi cả 7 bảng nằm trong khoảng nhiễu
(0.094–0.109).

---

## 5. ⚠️ Điều dev set KHÔNG đo được — và vì sao phải viết ra

Trước khi tin mục 4.1, kiểm một giả thiết: **cửa sổ ground truth của dev set được
dựng từ đâu?**

| query | frame của keyframe | cửa sổ GT | lệch tâm |
|:---|---:|:---|---:|
| Q1 | 5336 | 5286–5386 | **0** |
| Q2 | 13710 | 13660–13760 | **0** |
| Q3 | 8007 | 7957–8057 | **0** |
| K02 | 14812 | **14812**–14875 | = `frame_start` |
| K04 | 13083 | **13083**–13234 | = `frame_start` |
| K15 | 14127 | **14127**–14225 | = `frame_start` |

Q1–Q5 có keyframe **đúng tâm** cửa sổ; K01–K18 có keyframe **đúng bằng `frame_start`**
(18/19 câu). Cửa sổ GT được sinh RA TỪ chính keyframe.

**Hệ quả:** trên dev set này, hễ tìm đúng shot là frame của keyframe *chắc chắn* nằm
trong cửa sổ — 19/19 câu, khớp đúng `R@100 = 0.826 = 19/23`. Đó là **hệ quả của cách
dựng dev set**, không phải kết quả đo. Nên:

- Kết luận về **độ phủ** vẫn đứng vững (shot 0 slot là trượt chắc, không phụ thuộc
  cửa sổ dựng thế nào).
- Kết luận về **chiều sâu** thì dev set **không nói được gì**. Phải dựa vào `sweep`
  (giả định cửa sổ rơi đều trong shot) và vào ví dụ 11 frame của BTC.

Đây là lý do báo cáo này không kết luận "đào sâu vô dụng" — nó kết luận "chưa có bằng
chứng nào cho thấy đào sâu đáng giá, trong khi có bằng chứng rõ ràng rằng độ phủ đáng
giá".

---

## 6. Chốt

```python
SLOT_BUDGET: list[tuple[int, int]] = [(100, 1)]
```

**Ba lý do, xếp theo độ chắc chắn:**

1. Cứu được **2/23 câu** đang trượt chắc vì bảng ngân sách (đo được, không phụ thuộc
   giả định nào). Final trên dev: `0.470 → 0.487`.
2. Thắng hoặc hoà ở **mọi** giả định độ rộng cửa sổ trong `sweep`.
3. Không có bằng chứng nào ủng hộ chiều sâu. Không cược vào thứ chưa đo được.

**Hệ quả có lợi kèm theo:** mỗi shot đúng 1 slot nên **mọi dòng nộp đều là frame của
keyframe thật** (mức ưu tiên ① của allocator) — không dòng nào là frame rải suy đoán.

**Chiều sâu tự quay lại khi cần:** search trả ít hơn 100 shot thì `budget_per_shot()`
rải phần dư thành chiều sâu (71 shot → 29 shot đầu được 2 slot). Không cần bảng riêng.
Trên dev set hiện tại, số ứng viên dao động 71–100 (trung vị 99).

### Đảo lại khi nào

Đổi ngược về bảng có chiều sâu **chỉ khi** cả hai điều sau cùng đúng:
- cửa sổ đáp án thật sự hẹp (~10 frame) **và**
- shot đúng thường ở hạng ≤ 5 (tức tầng search khá lên nhiều so với hôm nay).

Và chỉ đổi sau khi chạy lại `shotrank` + `replay` trên **dev set có cửa sổ dựng ĐỘC
LẬP với keyframe**. Đổi bằng cảm giác thì không.

---

## 7. TRAKE nằm ngoài phạm vi task này

`dev_set/tools/run_evaluation.py` dựng 100 dòng TRAKE bằng `trake.to_answers()` /
`pad_answers()` và **không gọi `allocate()`** lần nào. Nên bảng chia slot không tác
động gì tới điểm TRAKE trên đường đo hiện tại.

`score_simulator` giờ báo đúng chuyện đó (`[bỏ qua] TR01 (TRAKE): điểm TRAKE không đi
qua allocate()`) thay vì `bỏ qua dòng hỏng — KeyError: 'shot_id'` như trước — thông
điệp cũ khiến người đọc đi sửa nhầm chỗ.

**Việc cho người sở hữu TRAKE (Thi):** BTC nói cửa sổ TRAKE *"thường dưới 10 frame"*.
Đó là ràng buộc chặt nhất trong cả ba dạng bài, và nó nằm ở tầng `trake.py`, không
nằm ở tầng slot.

---

## 8. Việc tiếp theo cho dev set (Linh)

Dev set hiện tại **không thể dùng để tune bất cứ thứ gì bên trong shot**. Muốn đo
được chiều sâu, cần cửa sổ đáp án dựng độc lập với keyframe:

1. Xem video, xác định khoảnh khắc bằng mắt → ghi `[s, e]` theo **sự kiện**, không
   theo keyframe gần nhất.
2. Lấy độ rộng theo cỡ BTC dùng: **~11 frame cho KIS**, **<10 frame cho TRAKE**.

Chỉ cần 10 câu như vậy là đủ để trả lời câu hỏi "đào sâu có đáng không" — nhiều giá
trị hơn 30 câu dựng theo cách cũ.

---

## Lệnh chạy lại

```powershell
python -m app.score_simulator shotrank --candidates dev_set/results/run_20260818_1739/candidates.jsonl --gt dev_set/ground_truth/tune_gt.jsonl
python -m app.score_simulator replay   --candidates dev_set/results/run_20260818_1739/candidates.jsonl --gt dev_set/ground_truth/tune_gt.jsonl
python -m app.score_simulator sweep --scenarios 50 --shots 100 --ranks 1,3,5,6,8,10,16,20,29,31,39,40,73,80,95 --widths 5,11,20,50,101
python -m pytest tests/test_score_simulator.py tests/test_allocator.py -q
```
