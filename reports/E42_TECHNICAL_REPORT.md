# 📋 Báo Cáo Kỹ Thuật — Task E4.2: `eval.py`

> **Ngày:** 13/08/2026 · **Hạn:** 13/08/2026
>
> **Người thực hiện:** Minh Hoàng (Linh đặc tả — chưa nhận được, đã tự dựng từ tài liệu BTC)
>
> **Phạm vi:** `app/eval.py` + `data/config/scoring.py` + mở rộng `app/labels.py`
> và `app/debug_ui.py` + `tests/test_eval.py`
>
> **Trạng thái: CHẠY ĐƯỢC ĐẦU-CUỐI cho cả ba dạng bài.** 233 test xanh.
> Chưa dùng thật được vì `dev_set/` còn rỗng — xem §7.

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
| `answer_dung` | người chấm phán: đúng ngữ nghĩa? `None` = chưa chấm | Q&A |
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
| `K_MOC = (1,5,20,50,100)` | năm mốc BTC chấm |
| `SO_CAU_TOI_DA = 100` | cắt phần nộp dư |
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
| `cham_query()` | chấm 100 dòng của một truy vấn |
| `cham_lo()` | chấm nhiều truy vấn, tách câu chưa có nhãn |
| `doc_runs()` | đọc file JSONL kết quả chạy |
| `tu_submissions()` | `QuerySubmission` (D0.2) → `LoNop` |
| `in_bao_cao()` | ba mức: theo dạng · tổng · câu tệ nhất |

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

`eval.py` gọi `BangNhan.is_correct()` của `app/labels.py`. D3.5 (mô phỏng chấm điểm,
16/08) gọi **đúng hàm đó**. Hai chỗ tự định nghĩa là hai con số khác nhau, và lúc cãi
nhau sẽ không có cơ sở nào để phân xử.

### 5.2. Sai video ra 0 **tự nhiên**, không cần nhánh `if`

`is_correct()` tra theo khoá `(query_id, video_id)`. Nộp sai video thì không nhãn nào
khớp → mọi khoảnh khắc đều `False` → `R-Score = 0`.

Đúng luật BTC *"sai video → 0 điểm ngay lập tức"* mà **không viết thêm dòng nào** — và
quan trọng hơn: không quên được. Nhánh `if` riêng là thứ người sau refactor sẽ xoá.

### 5.3. TRAKE — mẫu số lấy từ ĐÁP ÁN, không lấy `len(frame_ids)`

```python
n = bn.so_khoanh_khac(query_id) or len(dong.frame_ids)
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

### 7.1. 🔴 `dev_set/` đang RỖNG — chưa dùng thật được

`find dev_set -name "*.jsonl"` → **0 file**. `eval.py` chạy đúng nhưng chưa có gì để chấm.

Chấm nhãn tử tế cần **ảnh keyframe** (đang chờ Công Lý, W0.5). Không có ảnh thì chỉ
chấm được câu nào lời giải nằm trong OCR/ASR — mà chấm kiểu đó làm **lệch bộ nhãn**,
xem `D21_TECHNICAL_REPORT.md` §10.3.

### 7.2. 🔴 Hai dạng bài chưa có gì để đo

| Task | Người | Hạn | Trạng thái |
|:---|:---|:---|:---|
| C3.1 — pipeline Q&A | Thi | 14/08 | ❌ `backend/tasks/` chưa tồn tại |
| C3.2 — TRAKE giai đoạn 1 | Thi | 16/08 | ❌ |
| C4.4 — fallback TRAKE | Thi | 16/08 | ❌ |

`eval.py` đo được cả ba dạng, nhưng **hai trong ba dạng chưa có ai sinh ra câu trả
lời**. Mốc 🚩G3 ngày 16/08 hỏi *"ba dạng bài đều có điểm chưa?"*.

Ghi ở đây không phải để đổ lỗi mà để **thước đo sẵn sàng trước**: lúc C3.1 ship là đo
được ngay, không mất thêm một vòng.

### 7.3. 🟡 Cách so khớp `answer` là so CHUỖI, BTC so NGỮ NGHĨA

BTC chấm `aᵢ = GTₐ` theo **ngữ nghĩa** — `"5"` và `"Năm"` đều được tính đúng.

`BangNhan.answer_dung()` so chuỗi sau khi chuẩn hoá khoảng trắng + viết thường. Nghĩa
là người chấm phán trên **một chuỗi cụ thể**; hệ sinh ra chuỗi khác về nghĩa giống
nhau sẽ bị coi là "chưa chấm" (`None`), không phải "sai".

Chọn cách này có chủ ý: nới rộng thay BTC (bỏ dấu, so gần đúng, hỏi LLM) là **tự cho
mình điểm** mà lúc thi không có. Báo "chưa chấm" rồi để người phán là an toàn hơn.

Đường nâng cấp nếu bộ nhãn phình to: cho `answer_dung()` gọi `llm()` để so ngữ nghĩa,
nhưng phải là **tuỳ chọn tắt được** và kết quả ghi lại thành nhãn, không phán lại mỗi
lần chạy.

### 7.4. 🟡 Chưa có ai gọi `eval.py` trong pipeline

`run_minimal.py` chưa xuất file `runs.jsonl`. Hiện phải tự dựng file đó, hoặc gọi
`tu_submissions()` từ script.

Thêm ~5 dòng vào `run_minimal.py` là xong, nhưng đó là **file của Thạch** — cùng chỗ
với vấn đề `run_minimal.py` không gọi `allocate()` đã ghi ở `D31_TECHNICAL_REPORT.md`
§10.1. Nên gộp hai việc vào một lần sửa.

---

## 8. Đối chiếu với đặc tả

`BUILD_TASKS.md` E4.2:

| Yêu cầu | Trạng thái |
|:---|:---|
| Một lệnh ra đúng `Final Score` theo công thức thể lệ | ✅ `python -m app.eval runs.jsonl` |
| Tách theo dạng bài | ✅ ba dòng KIS / QA / TRAKE riêng |
| **Xuất riêng R@1, R@5, R@20, R@50, R@100** | ✅ năm cột |
| Biết đang yếu ở recall hay ranking | ✅ §6 — ví dụ thật cho ra chẩn đoán "bệnh ranking" |
| *"Linh đặc tả"* | ⚠️ **chưa nhận được đặc tả**. Đã tự dựng từ tài liệu BTC gốc, mọi con số đều neo vào ví dụ của BTC (§6). Linh nên rà lại |

### Ba việc cần người khác

1. **Công Lý** — tải data (ảnh keyframe) để chấm nhãn được.
2. **Thi** — C3.1/C3.2/C4.4, nếu không thì Q&A và TRAKE mãi không có gì để đo.
3. **Thạch** — cho `run_minimal.py` xuất `runs.jsonl`, gộp với việc gọi `allocate()`.

### Việc tiếp theo của Minh Hoàng

**D3.5 — mô phỏng chấm điểm** (14→16/08). Nó ăn thẳng `BangNhan` và `scoring.py` của
task này, trả lời được: *"đổi từ 3 shot × 8 frame sang 5 × 5 thì điểm đổi thế nào"* —
mà không cần chạy lại pipeline.

`BUILD_TASKS.md` ghi D3.5 là **task có tỉ lệ điểm/giờ cao nhất cả dự án**.
