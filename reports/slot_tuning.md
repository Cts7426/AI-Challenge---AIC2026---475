# D4.1 — Chỉnh bảng chia slot theo dữ liệu

> **19/08/2026 · Minh Hoàng** · dev set `tune` (23 KIS + 5 QA + 2 TRAKE)
> Nguyên liệu: `dev_set/results/run_20260818_1739/candidates.jsonl` (commit `5b7b10c`)
> Công cụ: `app/score_simulator.py` (D3.5)

**Kết luận:** `SLOT_BUDGET` **giữ nguyên** `[(1,6), (4,4), (10,2), (58,1)]` (phủ 73 shot).

Số đo dưới đây nghiêng về việc phủ trọn 100 shot (`[(100, 1)]`, Final dev `0.470 → 0.487`),
nhưng chúng chỉ đo được **một trục** — bề rộng. Trục còn lại (đào sâu trong shot) thì dev
set hiện tại **không đo được** vì cửa sổ ground truth được dựng từ chính keyframe (§5).
Đổi một bảng đang chạy dựa trên bằng chứng nửa vời là đánh đổi rủi ro không cần thiết
trước đợt 1, nên báo cáo này **ghi số lại và không đổi bảng**.

> 20/08 — bảng từng bị đổi sang `[(100, 1)]` ở commit `973e397` rồi hoàn lại. Bảng
> hiện tại là của Công Lý (`5b7b10c`); đổi nó phải báo Công Lý trước.

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

## 5b. Lỗi tìm được khi đo chiều sâu — `_spread_evenly` rải vào hai mép

**Đã sửa 20/08, `backend/slot/allocator.py`.** Đây là lỗi thật, không phải chuyện tune.

Đi tìm câu trả lời cho "đào sâu có đáng không" thì lộ ra chuyện đào sâu đang **hỏng**.
Bản cũ rải `m` điểm bằng `a + round(i·(b-a)/(m-1))` — công thức này **luôn gồm cả hai
mép** vùng rải. Với `m == 2` nó cho đúng `[a, b]`: hai mép, **bỏ trống nguyên khúc
giữa** — chỗ dễ chứa khoảnh khắc nhất.

Đo trên shot 69 frame (median thật của `shots.parquet`), vùng rải `[6, 62]`, cửa sổ
đáp án rơi đều trong shot:

| m | bản cũ | w=11 | w=20 | w=35 |
|---|---|---|---|---|
| 1 | `[34]` | 0.19 | 0.40 | 1.00 |
| 2 | `[6, 62]` | 0.24 | **0.28** | **0.40** |

**Cấp thêm một slot mà bài nộp KÉM đi.** Không exception, không log, validator vẫn
xanh — chỉ mất điểm. Và nó nằm trên đường chạy thật: bảng ngân sách hiện tại cấp
**2 slot cho hạng 6–15**, đúng vùng `shotrank` đo được là nơi shot đúng hay nằm
(trung vị hạng 10).

### Sửa: rải theo TÂM Ô thay vì hai mép

```python
span = b - a + 1
return [a + (2 * i + 1) * span // (2 * m) for i in range(m)]
```

Chia `[a, b]` thành `m` ô bằng nhau, lấy tâm mỗi ô. Không điểm nào chạm mép.

| m | tâm ô | w=11 | w=20 | w=35 |
|---|---|---|---|---|
| 1 | `[34]` | 0.19 | 0.40 | 1.00 |
| 2 | `[20, 48]` | **0.37** | **0.80** | **1.00** |
| 3 | `[15, 34, 53]` | 0.56 | 1.00 | 1.00 |
| 4 | `[13, 27, 41, 55]` | 0.75 | 1.00 | 1.00 |
| 6 | `[10, 20, 29, 39, 48, 58]` | 1.00 | 1.00 | 1.00 |

Thắng ở **mọi `m` và mọi độ rộng cửa sổ**. `m == 1` cho cùng giá trị với bản cũ nên
ca một-slot-mỗi-shot không đổi hành vi.

### Đo đầu-cuối, qua cả `_frames_of_shot`

Shot 69 frame, có keyframe thật ở frame 20 (đường chạy thật — search luôn đưa xuống
`best_keyframe_id`):

| quota | trước | w=11 | sau | w=11 |
|---|---|---|---|---|
| 2 | `[20, 34]` | 0.37 | `[20, 34]` | 0.37 |
| 3 | `[6, 20, 62]` | 0.42 | `[6, 20, 48]` | **0.49** |
| 4 | `[6, 20, 34, 62]` | 0.61 | `[15, 20, 34, 53]` | **0.64** |
| 6 | `[6, 7, 20, 34, 48, 62]` | 0.81 | `[11, 20, 23, 34, 45, 57]` | **0.95** |

Ở quota 6 bản cũ còn nhả ra `6` và `7` **dính nhau** — hai slot mua đúng một cửa. Xảy
ra vì điểm rải trùng keyframe đã phát ở mức ①, mức ③ nhảy vào quét từ đầu vùng.

### Bất biến mới, có test giữ

`tests/test_allocator.py` thêm 2 test:
- `test_spread_evenly_khong_bao_gio_cham_mep` — điểm rải không trùng biên vùng
- `test_spread_evenly_do_phu_don_dieu` — **thêm một điểm không bao giờ làm độ phủ
  giảm**, đo trên `w ∈ {5, 11, 20, 35}`, `m ∈ [1, 8]`. Bản cũ HỎNG test này.

Đây là bất biến đáng giữ hơn cả con số cụ thể: nó chặn đúng loại lỗi vừa mắc.

---

## 6. Chốt

```python
SLOT_BUDGET: list[tuple[int, int]] = [(1, 6), (4, 4), (10, 2), (58, 1)]   # giữ nguyên
```

**Cái đo được ủng hộ phủ rộng hơn:**

1. Bảng hiện tại bỏ rơi **2/23 câu** — K18 (shot đúng hạng 80) và K01 (hạng 95) nhận
   0 slot, tức trượt chắc chắn vì bảng ngân sách chứ không phải vì search kém.
   Replay nếu phủ trọn 100: Final `0.470 → 0.487`, toàn bộ chênh lệch ở R@100.
2. `sweep` cho phủ rộng thắng hoặc hoà ở **mọi** giả định độ rộng cửa sổ.

**Cái không đo được — và là lý do chưa đổi:**

3. Bảng hiện tại đang cược 6 slot vào shot hạng 1, tức cược rằng **đào sâu trong shot
   mua được điểm**. Dev set không xác nhận cũng không phủ nhận được điều đó (§5), nên
   đổi đi là bỏ một canh bạc chưa kiểm chứng để lấy một canh bạc khác cũng chưa kiểm
   chứng — chỉ khác là canh bạc mới chưa từng chạy trên dữ liệu thật lần nào.

**Được gì khi giữ:** phần lớn dòng nộp vẫn là frame của keyframe thật (mức ưu tiên ①
của allocator), và 5 shot đầu vẫn có nhiều hơn 1 cửa nếu cửa sổ `[s, e]` hẹp thật.

**Mất gì khi giữ:** đúng 2 câu trong 23 câu dev, và bất kỳ câu nào có shot đúng ở
hạng 74–100 lúc thi.

### Đổi sang `[(100, 1)]` khi nào

Khi có **một** trong hai điều sau:
- **BTC công bố độ rộng `[s, e]` là rộng** (≳ nửa shot median, tức ~35 frame) — lúc đó
  đào sâu hết ý nghĩa, phủ rộng thắng chắc.
- **Dev set có cửa sổ dựng độc lập với keyframe** (§8) cho thấy chiều sâu không mua
  thêm được câu nào.

Và trước khi đổi thì **báo Công Lý** — bảng này là của nó (`5b7b10c`).

### Việc rẻ nhất, làm được ngay

Nếu chỉ muốn cứu 2 câu hạng 74–100 mà không đụng chiều sâu: bỏ 6 slot của hạng 1
xuống còn 4, lấy 2 slot đó nối đuôi thành `[(5, 4), (10, 2), (60, 1)]` → phủ 75 shot.
Vẫn chưa tới hạng 95, nhưng là bước nhỏ có thể đo lại sau đợt 1 mà không đảo lộn gì.

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
