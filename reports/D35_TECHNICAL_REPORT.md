# 📋 Báo Cáo Kỹ Thuật — Task D3.5: Mô phỏng chấm điểm

> **Ngày:** 16/08/2026 · **Hạn:** 16/08/2026
>
> **Người thực hiện:** Minh Hoàng
>
> **Phạm vi:** `app/score_simulator.py` + `tests/test_score_simulator.py` + 4 dòng ghi
> nguyên liệu vào `dev_set/tools/run_evaluation.py`
>
> **Trạng thái: CHẠY ĐƯỢC ĐẦU-CUỐI cả hai chế độ.** 423 test xanh (14 test mới).
> Chế độ `sweep` đã cho ra kết luận dùng được ngay — xem §6. Chế độ `replay` mới chạy
> trên nguyên liệu dựng tay, **chưa chạy trên dev set thật vì dev set còn rỗng** (§8).

---

## Mục lục
1. [Vấn đề phải giải](#1-vấn-đề-phải-giải)
2. [Hai chế độ, hai câu hỏi khác nhau](#2-hai-chế-độ-hai-câu-hỏi-khác-nhau)
3. [Nguyên liệu: cái phải giữ lại mà trước giờ vứt](#3-nguyên-liệu-cái-phải-giữ-lại-mà-trước-giờ-vứt)
4. [Chi tiết từng hàm](#4-chi-tiết-từng-hàm)
5. [Ba quyết định thiết kế](#5-ba-quyết-định-thiết-kế)
6. [⭐ Kết quả chạy thực tế — và kết luận cho D4.1](#6--kết-quả-chạy-thực-tế--và-kết-luận-cho-d41)
7. [Đo độ trễ](#7-đo-độ-trễ)
8. [Phần TREO](#8-phần-treo)
9. [Đối chiếu đặc tả](#9-đối-chiếu-đặc-tả)
10. [Cách chạy · việc tiếp theo](#10-cách-chạy--việc-tiếp-theo)

---

## 1. Vấn đề phải giải

`eval.py` (E4.2) chấm bộ **100 dòng đã đóng gói xong** và trả về một con số. Nhưng câu
hỏi của D4.1 là câu khác:

> *"Đổi từ 3 shot × 8 frame sang 5 shot × 5 frame thì điểm đổi thế nào?"*

`eval.py` không trả lời được, vì lúc nó nhận hàng thì hàng đã đóng gói rồi. Muốn biết
thì phải **mở gói ra đóng lại** — mà nguyên liệu (danh sách shot ứng viên do `search()`
trả về) đã bị vứt ngay sau khi `allocate()` chạy xong.

Chênh lệch chi phí mới là lý do task này tồn tại:

| Cách làm | Chi phí một lần thử bảng |
|:---|:---|
| Chạy lại cả pipeline | hàng chục phút — dịch bằng LLM + Milvus + ES, ×20 câu, cần Docker |
| Giữ nguyên liệu, đóng gói lại | **~1 giây** |

`BUILD_TASKS` gọi đây là *"công cụ có tỉ lệ điểm/giờ cao nhất cả dự án"*, và lý do nằm
đúng ở dòng chênh lệch đó: tune là việc phải thử nhiều lần, mà thử nhiều lần chỉ khả
thi khi một lần thử tốn vài giây.

---

## 2. Hai chế độ, hai câu hỏi khác nhau

| Chế độ | Câu hỏi trả lời được | Cần gì |
|:---|:---|:---|
| `replay` | *"Trên bộ đề CỦA MÌNH, bảng nào cho điểm cao hơn?"* | dev set thật + một lần chạy đo |
| `sweep` | *"Nếu cửa sổ đáp án của BTC rộng w frame và shot đúng hay ở hạng r, bảng nào hơn?"* | **không cần gì** — chạy trên `shots.parquet` |

`sweep` sinh ra vì một lý do rất cụ thể: **độ rộng cửa sổ `[s,e]` của KIS là ẩn số của
BTC, không phải của bộ đề.** Có dev set cũng không biết được nó. `CLAUDE.md` mục 11 xếp
đây là thứ *"chênh lệch giữa hai giả định này lớn hơn mọi cải tiến model"*. Nên thay vì
đoán một con số rồi tune theo nó, `sweep` **quét cả dải** và xem bảng nào bền.

Và nhờ không phụ thuộc dev set, `sweep` chạy được **ngay hôm nay** — trong khi dev set
còn rỗng (§8).

---

## 3. Nguyên liệu: cái phải giữ lại mà trước giờ vứt

`run_evaluation.py` trước đây chỉ ghi hai file:

```
scores.jsonl    điểm từng câu
answers.jsonl   100 dòng ĐÃ đóng gói  ← không lùi lại được
```

Thiếu đúng thứ simulator cần. Đã thêm **file thứ ba**, ghi ngay trong cùng vòng lặp:

```jsonc
// candidates.jsonl — mỗi dòng một truy vấn
{"query_id": "K01", "task_type": "KIS", "answer_text": null, "n_trake": null,
 "candidates": [{"shot_id": "L21_V001#s0006", "score": 0.031,
                 "best_keyframe_id": "L21_V001#k0007"}, ...]}
```

Ba trường `shot_id · score · best_keyframe_id` là **toàn bộ** thứ `allocate()` cần. Cố
ý không lưu cả kết quả `search()` thô: tầng search đổi trường thì chỗ nạp phải sửa, còn
hợp đồng này thì không.

> [!IMPORTANT]
> Ghi nguyên liệu **cùng lần chạy** với điểm, không tách ra job riêng. Ghi sau thì tầng
> search có thể đã đổi và nguyên liệu không còn khớp bộ điểm nằm cạnh nó — mà lệch kiểu
> đó không có dấu hiệu gì, chỉ làm mọi kết luận tune sai một cách êm ái.
>
> **Hệ quả về thứ tự việc:** phải merge 4 dòng này **trước** lần chạy đo thật đầu tiên.
> Chạy trước rồi mới thêm là mất trắng một vòng search.

---

## 4. Chi tiết từng hàm

### `app/score_simulator.py` (444 dòng)

| Hàm | Vào → Ra | Ghi chú |
|:---|:---|:---|
| `load_candidates(path)` | `candidates.jsonl` → `list[QueryCandidates]` | Dòng hỏng thì BÁO rồi bỏ qua, không kéo sập cả file |
| `load_ground_truth(path)` | jsonl → `{query_id: GroundTruth*}` | Dùng lại lược đồ `dev_set/tools/schema.py`, không dựng kiểu thứ ba |
| `r_scores_of(answers, gt, task)` | 100 dòng → 100 R-Score | Gọi thẳng `rscore_kis/qa/trake` của dev_set — luật BTC mục 2.1 |
| `winner_ranks(r_scores)` | → `{k: hạng dòng ăn điểm}` | **Con số điểm tổng không nói ra** — xem §5.2 |
| `simulate_query(qc, gt, table)` | → `QueryResult` | Gọi ĐÚNG `allocate()` của đường nộp thật |
| `compare_tables(qcs, gts, tables)` | → điểm trung bình mỗi bảng | Truy vấn thiếu đáp án bị BỎ QUA, không tính 0 |
| `expected_final(answers, vid, bounds, w)` | → điểm kỳ vọng | Quét **mọi** vị trí đặt cửa sổ, không bốc ngẫu nhiên |
| `sweep(tables, widths, ranks, ...)` | → ma trận bảng × độ rộng | `allocate()` chạy 1 lần / (kịch bản, bảng) — xem §5.3 |
| `format_slots` · `format_comparison` · `format_sweep` | → chuỗi in ra | Trình bày tách khỏi tính toán |

### Năm bảng đem so

Xếp từ **đào sâu** tới **rải rộng**, cả năm cộng đúng 100 slot:

| Tên | Bảng | Phủ bao nhiêu shot |
|:---|:---|---:|
| `sâu 2×20` | `[(2,20), (4,10), (10,2)]` | **16** |
| `hiện tại 3×8` | `[(3,8), (7,5), (10,3), (11,1)]` | 31 |
| `cân 5×5` | `[(5,5), (15,3), (30,1)]` | 50 |
| `rộng 10×3` | `[(10,3), (20,2), (30,1)]` | 60 |
| `rất rộng 1×` | `[(100,1)]` | 100 |

Chúng nằm trong `score_simulator.py` chứ **không** nằm trong `data/config/slot_budget.py`:
đây là chỗ **thử**, không phải chỗ cấu hình. Bảng nào thắng thì **chép tay** sang
`slot_budget.py`. Để allocator đọc thẳng danh sách thí nghiệm là mở đường cho việc lúc
thi không ai biết đang chạy bảng nào.

---

## 5. Ba quyết định thiết kế

### 5.1. Không tự định nghĩa công thức chấm — tái dùng cả ba tầng

Đây là file **thứ ba** trong repo đụng tới chấm điểm. Hai file trước đã trùng nhau một
lần rồi (xem `E42_TECHNICAL_REPORT.md` §7.4), nên file này không viết lại dòng công
thức nào:

| Việc | Lấy từ |
|:---|:---|
| R-Score từng dòng (BTC mục 2.1) | `dev_set/tools/scoring.py` |
| R@k và Final Score (BTC mục 2.2) | `data/config/scoring.py` |
| Chia 100 slot | `backend/slot/allocator.py` |

Nó chỉ **ghép ba thứ đó lại và in ra**. Ba nơi cùng chấm là ba con số khác nhau, mà một
trong ba sẽ là con số nhóm nhìn vào để quyết định.

Cùng lý do, `simulate_query()` gọi đúng `allocate()` của đường nộp thật thay vì mô phỏng
lại phép chia: mô phỏng lại là đo một hệ **khác** với hệ lúc thi, và sai lệch đó không
có dấu hiệu gì.

### 5.2. `winner_ranks()` — thứ điểm tổng không nói ra

Final Score cho biết **bao nhiêu**, không cho biết **sửa ở đâu**. Hai câu cùng được
0.60 có thể cần hai thuốc ngược nhau:

| Dòng đúng nằm ở hạng | Bệnh | Thuốc |
|:---|:---|:---|
| 3 | ranking — gần rồi | đẩy shot lên đầu, **thêm slot vô ích** |
| 40 | R@1 và R@5 bỏ trắng | đổi thứ hạng shot ở tầng search |
| không có trong 100 dòng | recall — search trượt hẳn | **tune slot là công cốc** |

Nên mỗi truy vấn báo kèm **hạng của dòng ăn điểm ở từng ngưỡng**. Một dòng thường thắng
nhiều ngưỡng cùng lúc (hạng 3 ăn cả R@5, R@20, R@50, R@100) → giữ **ngưỡng nhỏ nhất**,
vì đó là chỗ nó bắt đầu ăn điểm và cũng là khoảng cách còn lại tới R@1. Giữ ngưỡng lớn
nhất thì dòng nào cũng hiện "thắng R@100", vô nghĩa. *(Bug này có thật ở bản đầu, test
`test_format_slots_bao_nguong_NHO_NHAT` khoá lại.)*

### 5.3. `sweep` quét **mọi** vị trí cửa sổ, và `allocate()` chỉ chạy một lần

Hai chi tiết làm `sweep` vừa nhanh vừa lặp lại được:

**Quét mọi vị trí, không bốc ngẫu nhiên.** Chạy lại phải ra **đúng một con số**, không
thì lần tune sau không so được với lần trước. Shot dài nhất 1795 frame nên có trần
`MAX_WINDOW_POSITIONS = 400` điểm rải đều — hằng **chi phí**, không phải hằng chiến thuật.

**`allocate()` chạy 1 lần cho mỗi (kịch bản, bảng).** 100 dòng nộp ra sao **không phụ
thuộc** việc shot nào là shot đúng. Nên chỉ định shot đúng rồi tính điểm chỉ là phép số
học trên kết quả đã có. Nhờ vậy 5 bảng × 5 độ rộng × 3 hạng × 30 kịch bản chạy trong
**1,8 giây**.

---

## 6. ⭐ Kết quả chạy thực tế — và kết luận cho D4.1

### 6.1. Quét trung bình trên hạng 1 · 3 · 10 (30 kịch bản shot thật)

```
  BẢNG                w=5     w=10     w=20     w=50    w=100
  ───────────────────────────────────────────────────────────
  sâu    2×20       0.259    0.334    0.597    0.648    0.684
  hiện tại 3×8      0.250    0.309    0.586    0.652    0.690
  cân    5×5        0.250    0.316    0.582    0.650    0.693
  rộng  10×3        0.250    0.324    0.580    0.645    0.697
  rất rộng 1×       0.236    0.333    0.577    0.641    0.696
```

**Phát hiện 1 — bảng slot ảnh hưởng ÍT hơn nhiều so với ẩn số của BTC.**
Đọc theo **hàng**: chọn bảng nào cũng chỉ chênh nhau **~0,02**. Đọc theo **cột**: độ
rộng cửa sổ từ 5 lên 100 kéo điểm từ **0,25 lên 0,69** — gấp **hai mươi lần** khoảng
chênh giữa các bảng.

Đây là **con số xác nhận** cho câu trong `CLAUDE.md` mục 11 (*"chênh lệch giữa hai giả
định này lớn hơn mọi cải tiến model"*), và nó nói thẳng một điều khó chịu: **hỏi BTC độ
rộng cửa sổ có giá trị hơn cả tuần tune bảng slot.** Đó là việc của Linh, không phải
việc của code.

### 6.2. Nhưng tách theo hạng shot đúng thì bức tranh đảo ngược

```
shot đúng ở HẠNG 1                    shot đúng ở HẠNG 10               shot đúng ở HẠNG 25
  BẢNG           w=5    w=20            BẢNG           w=5    w=20        BẢNG           w=5    w=20
  ──────────────────────────            ──────────────────────────        ──────────────────────────
  sâu    2×20  0.297   0.702  ★         sâu    2×20  0.130   0.431        sâu    2×20  0.000   0.000  ☠
  hiện tại 3×8 0.242   0.673            hiện tại 3×8 0.231   0.458  ★     hiện tại 3×8 0.077   0.283
  cân    5×5   0.244   0.665            cân    5×5   0.228   0.457        cân    5×5   0.077   0.283
  rộng  10×3   0.246   0.653            rộng  10×3   0.228   0.457        rộng  10×3   0.112   0.280  ★
  rất rộng 1×  0.246   0.653            rất rộng 1×  0.187   0.448        rất rộng 1×  0.112   0.280
```

**Phát hiện 2 — bảng tốt nhất phụ thuộc HOÀN TOÀN vào chất lượng search.**

- Search **giỏi** (shot đúng ở hạng 1): `sâu 2×20` thắng đậm — `0.702` so với `0.653`.
- Search **trung bình** (hạng 10): `sâu` thành **tệ nhất** — `0.130` so với `0.231`.
- Search **kém** (hạng 25): `sâu` ra **0,000 tuyệt đối**.

**Phát hiện 3 — `sâu 2×20` có một cửa tử.** Nó chỉ phủ **16 shot** (2+4+10). Mọi truy
vấn mà shot đúng nằm ngoài top-16 nhận **0 điểm**, dù tầng search đã tìm ra nó và xếp
nó ở hạng 17. Không phải điểm thấp — là **0 tuyệt đối**, do bảng chứ không do hệ thống.

Bảng `hiện tại 3×8` phủ 31 shot; các bảng rộng phủ 50–100. Đây là tính chất **an toàn**
của bảng, và nó không hiện ra trong con số trung bình ở §6.1.

### 6.3. Kết luận cho D4.1 — bằng số, không bằng cảm giác

| Câu hỏi | Trả lời |
|:---|:---|
| Tune bảng slot có đáng không? | **Đáng, nhưng ít** — ~0,02 điểm nếu chọn đúng, **nhưng tới 0,2–0,7 nếu chọn SAI kiểu `sâu` mà search kém** |
| Chốt được bảng chưa? | **Chưa.** Bảng thắng lật hoàn toàn theo hạng shot đúng, mà hạng đó chỉ dev set mới đo được |
| Nếu buộc phải chốt mù? | **Giữ `hiện tại 3×8`.** Nó không thắng ở đâu nhưng cũng không sập ở đâu — thua bảng tốt nhất ~0,03 ở mọi cột, trong khi `sâu` thua tới 0,28 khi search kém |
| Việc nào đáng hơn tune? | **Hỏi BTC độ rộng cửa sổ** (§6.1) và **làm dev set** (§6.2) |

> [!IMPORTANT]
> Đây chính là **bằng chứng bằng số** cho việc dev set là chặn cứng của D4.1, chứ không
> phải lời than. Không có phân bố hạng của shot đúng thì mọi lựa chọn bảng đều là tung
> đồng xu giữa `0.702` và `0.000`.

---

## 6.4. ⚠️ File này KHÔNG chạy lúc thi

Cùng loại với `--demo` của D0.2/D3.1: **công cụ trước ngày thi, không nằm trên đường
nộp bài.** Đường nộp lúc thi là `search()` → `allocate()` → `export`.

Nhưng thứ nó **đẻ ra** thì có đi vào phòng thi: một dòng số trong
`data/config/slot_budget.py`. Nên nó không cần chạy nhanh lúc thi, mà cần **đúng** —
sai ở đây là chọn nhầm bảng rồi mang bảng đó đi thi, không có dấu hiệu gì.

Sau đợt 1 vẫn giữ (D4.1 lặp lại ở đợt 2 và 3 với dữ liệu mới), nhưng **không** đưa vào
`run_minimal.py` và không để tầng nào trên đường nộp import nó.

---

## 7. Đo độ trễ

| Việc | Thời gian |
|:---|:---|
| `sweep` — 5 bảng × 5 độ rộng × 3 hạng × 30 kịch bản | **1,8 s** |
| `replay` — 3 truy vấn × 5 bảng | **1,1 s** |
| So sánh: chạy lại pipeline cho một bảng | hàng chục phút |

**Không nằm trên đường chạy online**, nên không tính vào ngân sách 30 giây của
`CLAUDE.md` bất biến 10. Nhưng tốc độ vẫn là tính năng: tune là việc thử nhiều lần, mỗi
lần 2 giây thì thử được 6 bảng trong một lần ngồi; mỗi lần 20 phút thì thử được một.

---

## 8. Phần TREO

| # | Việc | Chờ ai | Ảnh hưởng |
|:---:|:---|:---|:---|
| 1 | **Dev set thật** (đang là 3 dòng dữ liệu mẫu) | **Linh** | `replay` chưa chạy trên đề thật lần nào. D4.1 không chốt được — §6.3 |
| 2 | **Độ rộng cửa sổ `[s,e]` của KIS** | **Linh → BTC** | Ẩn số ảnh hưởng mạnh nhất, gấp 20 lần việc chọn bảng — §6.1 |
| 3 | Merge 4 dòng ghi `candidates.jsonl` **trước** lần chạy đo đầu tiên | — | Chạy trước rồi mới thêm là mất trắng một vòng search — §3 |
| 4 | Hai tầng chấm điểm song song | **Linh + Minh Hoàng** | File này tái dùng cả hai (`dev_set/tools/scoring.py` cho R-Score, `data/config/scoring.py` cho Final). Gộp lại thì đây là chỗ phải sửa theo |

**Giới hạn đã biết của `sweep`, không phải bug:**

- Chỉ mô phỏng **một** shot đúng mỗi truy vấn. Thực tế một sự kiện có thể trải nhiều shot.
- Giả định cửa sổ đáp án **nằm gọn trong shot**. Nếu shot bị cắt lệch thì cửa sổ nằm vắt
  qua biên và mức ④ của allocator (nới ra ngoài biên) mới ăn điểm — `sweep` đang **đánh
  giá thấp** các bảng sâu ở ca này.
- Coi **mọi vị trí cửa sổ trong shot là như nhau**. Nếu BTC hay chọn khoảnh khắc ở giữa
  shot thì bảng sâu có lợi hơn số quét ra.

---

## 9. Đối chiếu đặc tả

`BUILD_TASKS.md` D3.5:

| Yêu cầu | Trạng thái |
|:---|:---|
| Với mỗi query dev: hiện 100 slot đã nộp, đánh dấu slot nào đúng | 🟡 `--detail` hiện `--slots N` dòng đầu **+ mọi dòng có điểm**. In đủ 100 × 20 câu × 5 bảng = 10.000 dòng thì không ai đọc; cần đủ thì `--slots 100` |
| Chỉ ra slot thắng cho từng ngưỡng R@1/R@5/R@20/R@50/R@100 | ✅ `winner_ranks()`, hiện ngưỡng nhỏ nhất |
| **Thử lại phân bổ khác NGAY LẬP TỨC**, không chạy lại pipeline | ✅ 1,1 s cho 5 bảng |
| Trả lời được *"3 shot×8 sang 5 shot×5 thì điểm đổi thế nào"* | ✅ §6 — và trả lời được cả câu quan trọng hơn: *"đổi thế nào TÙY vào search giỏi hay kém"* |

**Một chỗ vượt đặc tả:** chế độ `sweep`. Đặc tả giả định đã có dev set; thực tế chưa có,
và ẩn số lớn nhất (độ rộng cửa sổ) **không nằm trong dev set**. `sweep` cho ra kết luận
dùng được ngay hôm nay mà không chờ ai — xem §6.

---

## 10. Cách chạy · việc tiếp theo

```powershell
# Không cần dev set, không cần Docker — chạy được ngay
python -m app.score_simulator sweep
python -m app.score_simulator sweep --ranks 1 --widths 5,10,20

# Khi có dev set thật + một lần chạy đo
python -m app.score_simulator replay `
    --candidates dev_set/results/run_XXXX/candidates.jsonl `
    --gt dev_set/ground_truth/tune_gt.jsonl --detail

python -m pytest tests/test_score_simulator.py -q    # 14 passed
python -m pytest tests dev_set/tests -q              # 423 passed
```

### File tạo / sửa

| File | Vai trò | Dòng |
|:---|:---|---:|
| `app/score_simulator.py` | Tạo mới — mô phỏng chấm điểm | 444 |
| `tests/test_score_simulator.py` | Tạo mới — 14 test | 195 |
| `dev_set/tools/run_evaluation.py` | Sửa — ghi thêm `candidates.jsonl` | +20 |

### Việc tiếp theo

1. **Merge sớm** phần ghi `candidates.jsonl`, trước lần chạy đo thật đầu tiên (§3).
2. **D4.1 (17→19/08)** — chạy `replay` khi có dev set. Nếu 17/08 vẫn chưa có đề thì
   **giữ `hiện tại 3×8`** theo §6.3 và ghi vào post-mortem, đừng tune mù.
3. **D6.1 (19→20/08)** — preflight check, không phụ thuộc gì đang treo.
