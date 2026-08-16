# 📋 Báo Cáo Kỹ Thuật — Task E4.2: `eval.py`

> **Ngày:** 13/08/2026 · **Hạn:** 13/08/2026
>
> **Người thực hiện:** Minh Hoàng (Linh đặc tả — đặc tả về 16/08, đối chiếu **khớp
> tuyệt đối** cả ba ví dụ có đáp số của BTC, xem §8)
>
> **Phạm vi:** `app/eval.py` + `data/config/scoring.py` + mở rộng `app/labels.py`
> và `app/debug_ui.py` + `tests/test_eval.py`
>
> **Trạng thái: CHẠY ĐƯỢC ĐẦU-CUỐI cho cả ba dạng bài.** 233 test xanh (toàn repo
> 16/08: **409 xanh**).
>
> **Cập nhật 15/08** — §7 đã viết lại. Ba pipeline phần C đã ship, và cách so khớp
> `answer` **đã sửa** để dùng chung `backend/common/answer_match.py` với tầng chấm
> dev_set và majority voting của Q&A.
>
> 🔴 **Chặn cứng còn lại: `dev_set/` vẫn rỗng trên thực tế** — 3 dòng dữ liệu giả trong
> đường chạy thật (§7.1). Bộ đo *chạy được và ra số*, nhưng số đó vô nghĩa. D3.5 và
> D4.1 đứng sau nút thắt này.

---

## Mục lục
1. [Vấn đề phải giải](#1-vấn-đề-phải-giải)
2. [Công thức của BTC — hai tầng, đừng trộn](#2-công-thức-của-btc--hai-tầng-đừng-trộn)
3. [Tờ đáp án phải ghi đủ thứ BTC kiểm](#3-tờ-đáp-án-phải-ghi-đủ-thứ-btc-kiểm)
4. [Chi tiết từng hàm](#4-chi-tiết-từng-hàm)
5. [Bốn quyết định thiết kế](#5-bốn-quyết-định-thiết-kế)
6. [Kết quả chạy thực tế](#6-kết-quả-chạy-thực-tế)
7. [Phần TREO và phần chờ người khác](#7-phần-treo-và-phần-chờ-người-khác)
8. [Đối chiếu với đặc tả](#8-đối-chiếu-với-đặc-tả)

---

## 1. Vấn đề phải giải

Nhóm nộp 100 dòng cho mỗi truy vấn. Không ai biết bộ 100 dòng đó được mấy điểm.

Không có thước đo thì mọi quyết định về sau là mò: đổi trọng số fusion — tốt hơn hay
tệ hơn? Đổi bảng ngân sách slot từ `3 shot × 8 frame` sang `5 × 5` — được gì? Tuần
cuối sẽ tune bằng cảm giác.

Nguy hơn: **lỗi trong thước đo tệ hơn lỗi trong search**. Search sai thì điểm thấp và
mình đi sửa. Thước đo sai thì mình sửa nhầm chỗ suốt hai tuần mà vẫn thấy số đẹp.

`eval.py` trả lời ba câu, theo thứ tự quan trọng tăng dần:

| Câu hỏi | Nhìn vào đâu |
|:---|:---|
| Nhóm đang được mấy điểm? | dòng `CHUNG` |
| Dạng bài nào đang hỏng? | ba dòng KIS / QA / TRAKE tách riêng |
| **Yếu ở recall hay ở ranking?** | so `R@1` với `R@100` |

Câu thứ ba là lý do phải tách 5 mốc thay vì in mỗi `Final`. `R@1` thấp mà `R@100` cao
= **tìm ra rồi nhưng xếp sai chỗ** → đầu tư rerank. Cả hai cùng thấp = **không tìm ra**
→ đầu tư recall. Hai bệnh, hai thuốc, và chỉ một con số `Final` thì không phân biệt được.

---

## 2. Công thức của BTC — hai tầng, đừng trộn

Nguồn: *Thông tin vòng Sơ tuyển AIC2026*, mục 2. Đã chép nguyên văn vào
`docs/contest.md` vì trước đó file đó chỉ có bảng rút gọn.

### Tầng 1 — mỗi câu trả lời một `R-Score ∈ [0,1]`, KHÔNG dính thứ hạng

| Dạng | `R-Score(rᵢ)` | Tính chất |
|:---|:---|:---|
| **KIS** | `I(vᵢ = GTᵥ ∧ idᵢ ∈ [s,e])` | nhị phân |
| **Q&A** | `I(vᵢ = GTᵥ ∧ idᵢ ∈ [s,e] ∧ aᵢ = GTₐ)` | nhị phân, **ba cửa tử** |
| **TRAKE** | `0` nếu sai video, ngược lại `(1/N)·Σⱼ I(idᵢⱼ ∈ [sⱼ,eⱼ])` | **điểm lẻ** |

### Tầng 2 — gộp theo thứ hạng

```
R@k   = max{ R-Score(r₁ … r_k) }     k ∈ {1, 5, 20, 50, 100}
Final = trung bình 5 giá trị R@k
```

### ⚠️ Bảng rút gọn là HỆ QUẢ, không phải luật

Bảng hay gặp — *hạng 1 → 1.00, hạng 2–5 → 0.80, 6–20 → 0.60…* — **không phải một quy
tắc riêng**. Nó là kết quả của hai tầng trên khi `R-Score` nhị phân:

> Câu đúng ở hạng 3 → lọt các mốc 5/20/50/100, trượt mốc 1 → `Final = 4/5 = 0.80`

Chép thẳng bảng đó vào code thì **TRAKE sai ngay**, vì TRAKE có điểm lẻ mà bảng chỉ
có 6 ô. Ví dụ thật: hạng 1 được 0.5, hạng 3 được 0.75 →
`Final = (0.5 + 0.75×4)/5 = `**`0.70`** — không ô nào của bảng ra được số này.

> [!NOTE]
> Có test riêng chốt cả hai chiều: `test_bang_rut_gon_la_HE_QUA_cua_cong_thuc` bắt
> 9 mốc hạng phải **tự ra** từ công thức, và `test_trake_diem_le_KHONG_co_trong_bang_rut_gon`
> chứng minh bảng không đủ cho TRAKE.

---

## 3. Tờ đáp án phải ghi đủ thứ BTC kiểm

`dev_set/labels.*.jsonl` là **đáp án tự soạn**. Nó chỉ chấm đúng nếu ghi lại được
**mọi điều kiện** BTC kiểm — mà ba dạng bài kiểm ba thứ khác nhau:

| Dạng | Số điều kiện | Tờ đáp án cần ghi |
|:---|:---:|:---|
| KIS | 1 | `video` + `[s, e]` |
| Q&A | 3 | + **câu trả lời đúng là gì** |
| TRAKE | N | + **N khoảng, mỗi khoảnh khắc một khoảng** |

`Label` của D2.1 thiết kế cho KIS nên chỉ có một ô khoảng và không có ô nào cho
answer. Hệ quả nếu để nguyên:

### 3.1. Q&A — ca tệ nhất

Ví dụ của BTC: đáp án `L05_V005`, `[800,900]`, answer `"màu xanh"`.
Hệ nộp `L05_V005, 888, "màu trắng"`.

| | Chấm ra |
|:---|:---|
| BTC | **0** — sai answer |
| `eval.py` với `Label` cũ | **1.0** — frame 888 nằm trong khoảng đã chấm đúng |

Vì sao đây là ca tệ nhất chứ không phải một sai số nhỏ: `run_minimal.py` — đường nộp
thật hiện tại — đang điền answer thế này:

```python
txt = (answer_text or "CHUA_CO_ANSWER") if task_type == "QA" else None
```

**Mọi câu Q&A đang nộp chuỗi `"CHUA_CO_ANSWER"`. Điểm thật là 0 tuyệt đối.** Thước đo
thiếu ô answer sẽ báo Q&A được 0.6–0.7, và cả nhóm kết luận "Q&A chạy được rồi".

### 3.2. TRAKE — không tạo nổi con số đúng

Đáp án `[95,105]`, `[145,155]`, `[195,205]`, `[245,255]`. Nộp `101, 156, 203, 251` →
khớp 3/4 → `R-Score = 0.75`.

Với một ô khoảng duy nhất, `eval.py` **không sinh ra được 0.75**. Nó chỉ có hai lựa
chọn, cả hai đều sai:

- đúng nếu **có frame nào** khớp → ra `1.0` (thổi phồng 33%)
- đúng nếu **tất cả** khớp → ra `0` (dìm mất 0.75)

### 3.3. Ba trường đã thêm

| Trường | Ghi gì | Cho dạng |
|:---|:---|:---|
| `answer_text` | câu trả lời hệ sinh ra | Q&A |
| `answer_correct` | người chấm phán: đúng ngữ nghĩa? `None` = chưa chấm | Q&A |
| `moment_idx` | dòng này là đáp án của khoảnh khắc thứ mấy | TRAKE |

TRAKE ghi **N dòng** cho một truy vấn thay vì nhét N khoảng vào một dòng — giữ nguyên
được luật append-only và khoá gộp của D2.1. `moment_idx` được đưa **vào khoá gộp**, để
sửa khoảnh khắc 2 không ghi đè khoảnh khắc 1.

Cả ba đều có mặc định `None` → dòng nhãn KIS viết trước đó đọc lại vẫn hợp lệ, có test
chốt (`test_doc_duoc_dong_nhan_CU_thieu_ba_truong_moi`).

---

## 4. Chi tiết từng hàm

### `data/config/scoring.py` — công thức thuần

| Thứ | Vai trò |
|:---|:---|
| `K_THRESHOLDS = (1,5,20,50,100)` | năm mốc BTC chấm |
| `MAX_ANSWERS = 100` | cắt phần nộp dư |
| `r_at_k(r_scores, k)` | `max` trong k câu đầu |
| `final_score(r_scores)` | trung bình 5 giá trị `R@k` |

Để riêng khỏi `search_weights.py` / `slot_budget.py` vì đây là **hằng số của cuộc thi**,
không phải tham số tune. Trộn chung là mở đường cho ai đó "thử chỉnh xem điểm có lên
không".

### `app/eval.py`

| Hàm | Việc |
|:---|:---|
| `r_score_kis()` | nhị phân, chỉ xét frame đầu tiên |
| `r_score_qa()` | trả `(điểm, answer_chưa_chấm)` — cờ thứ hai để báo riêng |
| `r_score_trake()` | khớp theo vị trí, mẫu số lấy từ đáp án |
| `score_query()` | chấm 100 dòng của một truy vấn |
| `score_runs()` | chấm nhiều truy vấn, tách câu chưa có nhãn |
| `read_runs()` | đọc file JSONL kết quả chạy |
| `from_submissions()` | `QuerySubmission` (D0.2) → `QueryRun` |
| `format_report()` | ba mức: theo dạng · tổng · câu tệ nhất |

**Định dạng file `runs`** — JSONL, mỗi dòng một truy vấn:

```json
{"query_id":"q_ab12","task_type":"KIS","query_vi":"…",
 "answers":[{"video_id":"L21_V001","frame_ids":[123],"answer_text":null}]}
```

Không đọc thẳng file nộp: file nộp (CSV theo `submit_format`) **đã bị tước** `query_id`
và `task_type` — đúng như thiết kế tầng đó — nên không đủ để chấm. Đây là định dạng
của khâu **đo**, không phải khâu **nộp**.

---

## 5. Bốn quyết định thiết kế

### 5.1. Không tự định nghĩa "thế nào là đúng"

`eval.py` gọi `LabelIndex.is_correct()` của `app/labels.py`. D3.5 (mô phỏng chấm điểm,
16/08) gọi **đúng hàm đó**. Hai chỗ tự định nghĩa là hai con số khác nhau, và lúc cãi
nhau sẽ không có cơ sở nào để phân xử.

### 5.2. Sai video ra 0 **tự nhiên**, không cần nhánh `if`

`is_correct()` tra theo khoá `(query_id, video_id)`. Nộp sai video thì không nhãn nào
khớp → mọi khoảnh khắc đều `False` → `R-Score = 0`.

Đúng luật BTC *"sai video → 0 điểm ngay lập tức"* mà **không viết thêm dòng nào** — và
quan trọng hơn: không quên được. Nhánh `if` riêng là thứ người sau refactor sẽ xoá.

### 5.3. TRAKE — mẫu số lấy từ ĐÁP ÁN, không lấy `len(frame_ids)`

```python
n = bn.n_moments(query_id) or len(dong.frame_ids)
```

Nộp thiếu khoảnh khắc mà chia cho số mình nộp thì trúng 1/1 ra `1.0` thay vì `0.25` —
**nộp càng ít điểm càng cao**. Vô lý, nhưng chạy vẫn ra số và không ai nhận ra.

Có test chốt: `test_trake_nop_THIEU_khoanh_khac_van_chia_cho_N_that`.

### 5.4. "Chưa chấm" ≠ "sai" — hai chỗ, cùng một lý do

| Ca | Xử lý |
|:---|:---|
| Truy vấn **chưa có nhãn nào** | **BỎ QUA**, ghi vào `bo_qua`, không tính 0 |
| Q&A **frame đúng, answer chưa ai phán** | tính 0 nhưng **ĐẾM và BÁO** riêng |

Tính 0 im lặng thì `Final` tụt xuống theo số nhãn còn thiếu. Con số đó trông như hệ
thống dở, thật ra là bộ nhãn chưa xong — và người đọc sẽ đi sửa search trong khi thứ
thiếu là nhãn. Đúng loại lỗi im lặng cả dự án đang phòng, mà lần này nó nằm ngay
trong cái thước đo.

---

## 6. Kết quả chạy thực tế

Chạy đầu-cuối với đáp án tự soạn (2 KIS + 1 Q&A + 1 TRAKE N=4) và 5 truy vấn × 100 dòng:

```
TỔNG (4 truy vấn có nhãn) Final   R@1    R@5    R@20   R@50   R@100
  KIS (2 câu)            0.600   0.500  0.500  0.500  0.500  1.000
  QA (1 câu)             0.800   0.000  1.000  1.000  1.000  1.000
  TRAKE (1 câu)          0.700   0.500  0.750  0.750  0.750  0.750
  ──────────────────────────────────────────────────────────
  CHUNG                  0.675   0.375  0.688  0.688  0.688  0.938

⚠️  1 dòng Q&A có frame ĐÚNG nhưng answer CHƯA AI CHẤM → đang tính 0.
⚠️  1 truy vấn chưa có nhãn nào → BỎ QUA, không tính 0: q_chua_cham

4 CÂU TỆ NHẤT
  q_kis2         0.20  "người đàn ông áo đỏ trên bãi biển"    — đúng đầu tiên ở hạng 87
  q_tr1          0.70  "4 khoảnh khắc cú nhảy cao"            — đúng đầu tiên ở hạng 1
  q_qa1          0.80  "người phụ nữ cầm ly màu gì"           — đúng đầu tiên ở hạng 2
  q_kis1         1.00  "thủ môn cản phá penalty"              — đúng đầu tiên ở hạng 1
```

**Kiểm tay từng dòng:**

| Truy vấn | Diễn biến | Final | Khớp? |
|:---|:---|---:|:---:|
| `q_kis1` | đúng ở hạng 1 | 1.00 | ✅ |
| `q_kis2` | đúng ở hạng 87 → chỉ lọt mốc 100 → 1/5 | 0.20 | ✅ |
| `q_qa1` | hạng 1 answer `"CHUA_CO_ANSWER"` (chưa chấm → 0), hạng 2 đúng → 4/5 | 0.80 | ✅ |
| `q_tr1` | hạng 1 khớp 2/4 = 0.5 · hạng 3 khớp 3/4 = 0.75 → `(0.5+0.75×4)/5` | 0.70 | ✅ |

Dòng `q_tr1` là bằng chứng chạy được rằng bảng rút gọn không dùng cho TRAKE — **0.70
không nằm trong sáu ô của bảng**.

Dòng `KIS` cho thấy đúng thứ §1 nói: `R@1 = 0.500` mà `R@100 = 1.000`. Cả hai câu đều
tìm ra, một câu xếp ở hạng 87. Đây là **bệnh ranking**, thuốc là rerank chứ không phải
mở rộng recall.

**Độ trễ:** 4 truy vấn × 100 dòng trong **39,9 ms**. Không phải chỗ cần tối ưu.

### Test

```
tests/test_eval.py      37 test
tests/test_labels.py     4 test thêm cho ba trường mới
────────────────────────────────
toàn bộ dự án          233 xanh, 0 đỏ
```

Phần lớn test chạy lại **đúng những ví dụ có số trong tài liệu BTC** — nguồn ngoài,
không phải tự nghĩ ra rồi tự khớp:

| Test | Ví dụ gốc |
|:---|:---|
| `test_vi_du_CO_SO_cua_BTC_ra_dung_074` | mục 2.2 — 0.5/0.8/0.6 → 0.74 |
| `test_kis_SAI_VIDEO_thi_0_du_frame_dung` | mục 2.1.1 — `L02_V003, 505` |
| `test_qa_frame_dung_ma_ANSWER_SAI_thi_0` | mục 2.1.2 — `"màu trắng"` |
| `test_trake_vi_du_BTC_ra_dung_075` | mục 2.1.3 — `101,156,203,251` |

Một test đáng nói riêng: `test_trake_khop_THEO_VI_TRI_khong_phai_bat_ky_thu_tu_nao`.
Nộp đủ 4 frame đúng nhưng **đảo thứ tự** → phải ra 0. Cách viết tự nhiên nhất (kiểm
"frame này có nằm trong khoảng nào không") sẽ ra 1.0 — sai hoàn toàn mà nhìn code
không thấy gì lạ.

---

## 7. Phần TREO và phần chờ người khác

> **Cập nhật 16/08.** Ba trong bốn mục dưới đã được code đồng đội pull về gỡ. Mục 7.3
> đã **sửa xong trong code**; 7.1 và 7.2 đã thông nhưng đổi hình dạng — đọc kỹ, phần
> còn lại không giống phần cũ.

### 7.1. 🔴 `dev_set/` VẪN RỖNG — có file, nhưng nội dung là dữ liệu giả

Bản 13/08 ghi *"`find dev_set -name "*.jsonl"` → 0 file"*. Nay **có file**, nhưng mở ra
xem thì đây là toàn bộ nội dung:

```jsonl
{"query_id": "Q1", "task_type": "KIS", "query_vi": "Query hợp lệ", "split": "tune"}
{"query_id": "Q2", "task_type": "KIS", "query_vi": "Query ngoài biên video", "split": "tune"}
{"query_id": "Q3", "task_type": "KIS", "query_vi": "Query có cửa sổ rộng", "split": "tune"}
```

Ba dòng, cả ba là **mô tả ca kiểm thử chứ không phải câu hỏi**, đáp án đều trỏ vào
`L21_V001` với cửa sổ tròn trịa `[10,20] · [30,40] · [50,60]`. Không có file
`tune_qa.jsonl` lẫn `tune_trake.jsonl` nào, dù commit tạo ra chúng ghi *"thêm bộ đề và
ground truth cho KIS/Q&A"*.

Đây là **chặn cứng và bị nguỵ trang**: `dev_set/queries/` là đúng đường mà
`run_evaluation.py:112` đọc, nên bộ đo *chạy được* và *ra số* — chỉ là số đó vô nghĩa.
Đối chiếu `dev_set/README.md` tự đặt ra: **KIS 25/10 · QA 20/8 · TRAKE 15/6**
(tune/holdout). Đang có **3/25 câu KIS, 0 câu QA, 0 câu TRAKE**.

Hệ quả dây chuyền: **D3.5 và D4.1 không có gì để chạy**. Tune bảng `SLOT_BUDGET` trên
3 câu giả là tự lừa — mỗi câu đổi ±1 hạng là Final nhảy 0.33.

**Việc của Linh (nội dung dev set) + Công Lý (GT), không tự gỡ được từ phần D/E.**

Còn treo tiếp: **ảnh keyframe để chấm nhãn bằng mắt**. Công Lý đã có bộ ảnh trên máy
mình (bản vá 15/08 cho `app/evidence.py` nhắc tới lớp bọc `keyframes_L21/`), nhưng máy
này chưa có `data/keyframes/`.

> [!NOTE]
> Ngay cả khi có đề thật, `python -m app.eval` vẫn báo *"chưa có nhãn nào"* — bộ đáp án
> của dev_set theo `dev_set/tools/schema.py` (`GroundTruthKIS/QA/TRAKE`), khác
> `app/labels.py::Label` mà `eval.py` đọc. **Hai định dạng đáp án song song**, xem §7.4.

### 7.2. ✅ Ba pipeline đã ship — đo được cả ba dạng bài

| Task | Người | Trạng thái 16/08 |
|:---|:---|:---|
| C3.1 — pipeline Q&A | Thi | ✅ `backend/tasks/qa.py` |
| C3.2 — TRAKE giai đoạn 1 | Thi | ✅ `backend/tasks/trake.py` |
| C4.4 — fallback TRAKE | Thi | ✅ `backend/tasks/trake_fallback.py` |

Mốc 🚩G3 16/08 (*"ba dạng bài đều có điểm chưa?"*) đã có đủ nguồn sinh câu trả lời.

> [!WARNING]
> **Một cửa tử mới lộ ra khi đo Q&A.** `qa_pipeline()` **raise `RuntimeError`** khi
> không suy luận được câu trả lời đủ tin cậy (`backend/tasks/qa.py:457`). Trên đường
> chạy của `run_evaluation.py` thì câu đó thành `F0_CRASH` và **không nộp dòng nào** —
> tức 0 điểm, trong khi retrieval có thể đã trúng shot.
>
> Luật số 1 của cách chấm (`CLAUDE.md` §6) là *"LUÔN nộp đủ 100 slot, câu sai không bị
> trừ điểm"*. Không trả lời được thì vẫn nên nộp 100 dòng với một answer đoán — 100
> dòng có frame đúng mà answer sai được 0, y hệt bỏ trống, **nhưng không mất gì cả**,
> còn nếu answer đoán trúng thì được điểm. Thuộc file của **Thi**, không sửa từ đây.

### 7.3. ✅ ĐÃ SỬA — `answer` khớp theo LUẬT CHUNG của nhóm, không so chuỗi nguyên văn

Bản 13/08: `LabelIndex.is_answer_correct()` so chuỗi sau khi chuẩn hoá khoảng trắng +
viết thường, và ghi rằng nới rộng thay BTC là "tự cho mình điểm".

**Điều đã đổi:** nhóm nay đã có `backend/common/answer_match.py` — một nguồn sự thật
DUY NHẤT cho *"thế nào là hai câu trả lời giống nhau"*, đang được dùng ở hai chỗ khác:

| Nơi dùng | Việc |
|:---|:---|
| `dev_set/tools/scoring.py::rscore_qa` | chấm câu Q&A so với ground truth |
| `backend/tasks/qa.py` (majority voting) | gom phiếu self-consistency |

Nên `is_answer_correct()` **đã chuyển sang gọi đúng module đó**. Đây không còn là "tự
nới rộng thay BTC": ba tầng khớp (chuẩn hoá → số ↔ chữ → fuzzy 0.85) là luật nhóm đang
dùng để chấm, và một tầng đo mà định nghĩa "giống nhau" khác tầng chấm thì hai con số
sẽ trôi xa nhau, mà một trong hai là con số nhóm nhìn để ra quyết định.

Vẫn giữ nguyên hai bất biến cũ:

- **Phán quyết vẫn là của NGƯỜI.** Module chỉ trả lời "câu vừa sinh ra có phải câu
  người ta đã phán không", không tự phán đúng/sai.
- **Ba giá trị True/False/None.** Chưa ai chấm vẫn là `None`, `eval.py` vẫn đếm riêng.

Cái được: người chấm phán một lần trên `"5"`, hệ trả `"5 người"` hay `"Năm"` thì phán
quyết đó **được nhận ra**. Trước đây rơi hết vào "chưa chấm" → `eval.py` tính 0 → điểm
Q&A tụt theo số cách diễn đạt chứ không theo chất lượng hệ thống.

Thêm chốt chặn: tra theo **tầng khớp tăng dần** (khớp nguyên văn thắng khớp gần đúng),
không theo thứ tự dòng nhãn — nếu không, bộ nhãn có cả `"màu xanh"=Đúng` lẫn
`"màu xanh lá"=Sai` thì kết quả phụ thuộc dòng nào đọc trước, tức phụ thuộc thứ tự file
trên đĩa. 3 test khoá lại trong `tests/test_labels.py`.

### 7.4. 🔴 Đã có đường đo — nhưng nhóm đang có HAI tầng chấm điểm song song

`run_evaluation.py` (dev_set) nay chạy đủ vòng: search → `allocate()` → chấm → ghi file
nộp. Nhưng nó **không gọi `app/eval.py`**; nó dùng `dev_set/tools/scoring.py`.

| | `app/eval.py` + `data/config/scoring.py` (E4.2) | `dev_set/tools/scoring.py` |
|:---|:---|:---|
| Nguồn đáp án | `app/labels.py::Label` — người chấm qua UI debug | `ground_truth/*.jsonl` — soạn tay theo schema riêng |
| Công thức Final | `mean(R@k)` ✅ | `mean(R@k)` ✅ — **hai bên khớp nhau** |
| TRAKE nộp thiếu khoảnh khắc | chấm từng phần, mẫu số lấy từ đáp án | trả thẳng `0.0` nếu `len(frames) != N` |
| Q&A chưa ai phán | `None` → đếm riêng, báo ra | không có khái niệm này (đáp án có sẵn) |
| Báo cáo | tách theo dạng bài, liệt kê câu tệ nhất, chẩn đoán recall/ranking | `scores.json` thô + `failure_class` |

Công thức gốc thì **khớp** — cả hai đều đã sửa cùng một bug "bảng rút gọn" (E4.2 từ
đầu, dev_set sửa 14/08).

### 7.4.1. Đo lại 16/08 — phần trùng NHỎ hơn nhiều so với bản ghi hôm 15/08

> Bản trước ghi *"hai tầng chấm song song, gộp lại mất nửa ngày"*. Rà bằng `grep` từng
> chỗ import thì con số thật khác hẳn. Ghi lại cho đúng.

Tầng chấm chia làm **hai lớp**, và chỉ **một** lớp trùng:

| Lớp | `data/config/scoring.py` | `dev_set/tools/scoring.py` | Trùng? |
|:---|:---|:---|:---|
| **Công thức R@k + Final** (BTC mục 2.2) | `r_at_k` · `final_score` | `recall_at_k` · `final_score` | 🔴 **TRÙNG THẬT — ~26 dòng** |
| **R-Score từng dòng** (BTC mục 2.1) | — | `rscore_kis/qa/trake` (nhận `GroundTruth*`) | 🟢 không trùng — `app/eval.py` có bản nhận `LabelIndex`, **hai định dạng đáp án khác nhau** |

Nghĩa là việc phải làm chỉ là: **`dev_set/tools/scoring.py` import `r_at_k`/`final_score`
từ `data/config/scoring.py` thay vì tự viết.** Khoảng 26 dòng, không phải nửa ngày. Phần
`rscore_*` giữ nguyên — nó bám định dạng ground truth của dev set, không phải bản sao.

### 7.4.2. 🔴 Sự thật khó chịu hơn: `app/eval.py` hiện KHÔNG ai gọi

```
grep "from app.eval import" → chỉ tests/test_eval.py
```

Đường chấm đang sống là `run_evaluation.py` → `dev_set/tools/scoring.py`. `app/eval.py`
không nằm trên đó, vì nó đọc nhãn từ `app/labels.py` mà **chưa ai chấm nhãn nào**
(`dev_set/labels.*.jsonl` → 0 file), do chưa có ảnh keyframe để chấm bằng mắt.

**Không xoá**, vì hai đường phục vụ hai việc khác nhau:

| Đường | Nguồn đáp án | Sống khi nào |
|:---|:---|:---|
| `run_evaluation.py` + `dev_set/tools/scoring.py` | đề soạn sẵn + GT | **đang chạy** |
| `app/eval.py` + `app/labels.py` + UI debug | người ngồi chấm từng frame | khi có ảnh keyframe (W0.5) |

Nhưng **ngừng đầu tư vào `app/eval.py`** cho tới khi ảnh về. Mọi tính năng đo mới thêm
vào đường đang chạy, không thêm vào đường chưa có dữ liệu.

---

## 8. Đối chiếu với đặc tả

`BUILD_TASKS.md` E4.2:

| Yêu cầu | Trạng thái |
|:---|:---|
| Một lệnh ra đúng `Final Score` theo công thức thể lệ | ✅ `python -m app.eval runs.jsonl` |
| Tách theo dạng bài | ✅ ba dòng KIS / QA / TRAKE riêng |
| **Xuất riêng R@1, R@5, R@20, R@50, R@100** | ✅ năm cột |
| Biết đang yếu ở recall hay ranking | ✅ §6 — ví dụ thật cho ra chẩn đoán "bệnh ranking" |
| *"Linh đặc tả"* | ✅ **Đóng 16/08** — đặc tả chính là tài liệu BTC *"Thông tin vòng Sơ tuyển"*, đã có. Đối chiếu xong, xem dưới |

#### ✅ Đối chiếu với tài liệu BTC — cả ba ví dụ CÓ ĐÁP SỐ đều khớp tuyệt đối (16/08)

Tài liệu BTC cho ba ví dụ kèm đáp số. Chạy thẳng bằng code của nhóm:

| Ví dụ của BTC | BTC nói | Code ra | |
|:---|:---|:---|:--:|
| Mục 2.2 — câu 1 = 0.5, câu 3 = 0.8, câu 15 = 0.6 | Final = **0.74** | `final_score()` → **0.74** | ✅ |
| Mục 2.1.3 — TRAKE `(101, 156, 203, 251)` khớp 3/4 | R-Score = **0.75** | `rscore_trake()` → **0.75** | ✅ |
| Mục 2.1.3 — TRAKE sai video | R-Score = **0** | `rscore_trake()` → **0.0** | ✅ |

Trung gian cũng khớp: `R@1 = 0.5` · `R@5 = R@20 = R@50 = R@100 = 0.8`, đúng như tài liệu
mô tả (*"câu số 3 vẫn là cao nhất trong mọi ngưỡng từ 5 trở lên"*).

Ba thứ khác trong tài liệu cũng đã xác nhận: **tối đa 100 câu** mỗi truy vấn (mục 2),
**answer chấp nhận tiếng Việt hoặc tiếng Anh** (mục 1.2), và **hai cửa tử độc lập** của
Q&A (mục 2.1.2) — cả ba đều đã cài đúng từ đầu.

Nên phần *"chưa nhận được đặc tả"* của bản 13/08 **không còn là rủi ro**: thứ tự dựng
ngược (code trước, tài liệu sau) hoá ra không sinh sai lệch nào.

### Ba việc cần người khác — cập nhật 16/08

| # | Việc | Ai | Trạng thái |
|:--:|:---|:---|:---|
| 1 | Ảnh keyframe để chấm nhãn bằng mắt | Công Lý | 🟡 có trên máy Lý, máy này chưa có `data/keyframes/` |
| 2 | C3.1 / C3.2 / C4.4 sinh câu trả lời Q&A + TRAKE | Thi | ✅ xong — §7.2 |
| 3 | `run_minimal.py` xuất `runs.jsonl` + gọi `allocate()` | Thạch | 🟡 `run_evaluation.py` đã đi đường `allocate()`, `run_minimal.py` thì chưa — xem `D31_TECHNICAL_REPORT.md` §10.1 |
| 4 | **Chốt một tầng chấm điểm** thay vì hai | Linh + Minh Hoàng | 🔴 mới — §7.4, làm trước D4.1 |

### Việc tiếp theo của Minh Hoàng

**D3.5 — mô phỏng chấm điểm** (14→16/08). Nó ăn thẳng `LabelIndex` và `scoring.py` của
task này, trả lời được: *"đổi từ 3 shot × 8 frame sang 5 × 5 thì điểm đổi thế nào"* —
mà không cần chạy lại pipeline.

`BUILD_TASKS.md` ghi D3.5 là **task có tỉ lệ điểm/giờ cao nhất cả dự án**.
