# Kết quả đo thật 27/08/2026 — before/after đầu tiên

Bổ sung cho `00_MASTER.md` §N/§O, vốn ghi "CHƯA ĐO". **Giờ đã có số.**
Người vận hành chạy `run_evaluation.py --split dress25` ba lần trong ngày 27/08.

---

## 1. Ba lần chạy

| Run | Giờ | Commit | Trạng thái |
|---|---|---|---|
| `run_20260827_153845_27d970c1` | 15:38–15:41 | `b419f6e` | hoàn tất; **0/5 QA sinh được CSV** |
| `run_20260827_154331_27d970c1` | 15:43 | `b419f6e` | **hỏng/bỏ dở** — mọi file rỗng, chỉ có `config_snapshot.json` |
| `run_20260827_154710_27d970c1` | 15:47–16:15 | `b419f6e` | hoàn tất; 4/5 QA sinh CSV (thiếu `DRESS_QA_04`) |

Cả ba cùng `runtime_fingerprint = f9b98636…`, cùng
`query_set_sha256 = a5f151dc…`, cùng `ground_truth_set_sha256 = 029ccb17…`,
cùng `scorer_source_sha256 = 12846d61…`, `promotion_ready: false`,
`verified_query_ids: []`.

Gate provenance hoạt động đúng: artefact mang đủ 11 field provenance mà baseline
21/08 hoàn toàn không có (baseline chỉ có `run_id`, `commit`, `split`).

---

## 2. Tổng hợp — baseline vs sau implement

| | Baseline 21/08 `0c4bf04` | RUN 1 27/08 | RUN 3 27/08 |
|---|---|---|---|
| **Overall** | **0.3520** | 0.3040 | **0.3627** |
| KIS (n=19) | 0.4211 | 0.4000 | 0.4000 |
| KIS R@1 | 0.1053 | 0.0526 | 0.0526 |
| QA (n=5) | 0.1200 | 0.0000 | 0.2000 |
| TRAKE (n=1) | 0.2000 | 0.0000 | 0.4667 |

**Không có kết luận "tốt lên" nào rút ra được từ bảng này.** Tùy chọn run nào:
`−0.0480` (run 1) hoặc `+0.0107` (run 3) so với baseline. Cả hai đều nhỏ hơn
nhiễu của một bộ 25 câu.

---

## 3. Diff từng câu (baseline → RUN 3)

```
query_id        task    base   run1   run3   Δ base→run3   failure_class(run3)
DRESS_KIS_01    KIS     1.00   0.80   0.80        -0.20 ↓   wrong_frame
DRESS_KIS_02    KIS     1.00   1.00   1.00        +0.00     None
DRESS_KIS_03    KIS     0.20   0.00   0.00        -0.20 ↓   retrieval_miss
DRESS_KIS_04..19        (16 câu KIS còn lại — KHÔNG ĐỔI một câu nào)
DRESS_QA_01     QA      0.60   0.00   0.00        -0.60 ↓   retrieval_miss
DRESS_QA_02     QA      0.00   0.00   0.00        +0.00     retrieval_miss
DRESS_QA_03     QA      0.00   0.00   1.00        +1.00 ↑   None
DRESS_QA_04     QA      0.00   0.00   0.00        +0.00     missing_evidence (status=failed)
DRESS_QA_05     QA      0.00   0.00   0.00        +0.00     retrieval_miss
DRESS_TRAKE_01  TRAKE   0.20   0.00   0.47        +0.27 ↑   trake_order
```

**KIS: 17/19 câu đứng yên nguyên xi, 2 câu giảm, 0 câu tăng.**
**QA: đổi chác — mất `QA_01` (0.60→0), được `QA_03` (0→1.00). 3 câu còn lại vẫn 0.**
**TRAKE: n=1, không kết luận được gì.**

---

## 4. ⛔ Phát hiện P0 — multi-anchor CHƯA BAO GIỜ CHẠY

Đọc `query_plan` của cả 19 câu KIS, cả hai run:

```
KIS strategy        : {'single': 19}
KIS fallback_reason : {'planner_error': 19}
```

**19/19 câu rơi về single-anchor.** Không một câu nào dùng multi-anchor.
`_needs_multiple()` trả True cho **19/19** câu — nghĩa là planner được gọi mọi
lần, và **thất bại mọi lần**.

### Nguyên nhân gốc — đã tái lập trực tiếp

`ANCHOR_SCHEMA` tại `backend/retrieval/multi_anchor.py:59-70` khai `maxItems`:

```python
ANCHOR_SCHEMA = {
    "type": "object",
    "properties": {
        "anchors": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": MAX_ANCHORS,        # ← API Anthropic KHÔNG hỗ trợ
        }
    },
    "required": ["anchors"],
    "additionalProperties": False,
}
```

Gọi thật `llm(prompt, json_schema=ANCHOR_SCHEMA, max_tokens=384)`:

```
anthropic.BadRequestError: Error code: 400 - {'type': 'error', 'error':
{'type': 'invalid_request_error', 'message':
"output_config.format.schema: For 'array' type, property 'maxItems' is not supported"}}
```

`plan_query()` bắt bằng `except Exception` (`multi_anchor.py:301-302`) rồi trả
`_single_plan(..., "planner_error")`. Lỗi 400 bị nuốt hoàn toàn — không log,
không cảnh báo, không đếm. Đúng dạng "lỗi IM LẶNG" mà `CLAUDE.md` §12 cảnh báo.

### Vì sao 39 test không bắt được

`tests/test_multi_anchor.py` mock `llm()`. Schema chưa từng được đối chiếu với
provider thật. Đây là khoảng trống loại "integration với dịch vụ ngoài", không
phải lỗi logic — mọi bất biến anchor/token/fidelity/RRF đều đúng khi chạy.

### Đã xác minh cách sửa (chưa áp dụng vào repo)

Bỏ `maxItems` khỏi schema. **Không mất ràng buộc nào** vì
`_validated_anchors()` đã tự chặn trong Python:

```python
# multi_anchor.py:270-271
if len(raw_anchors) > MAX_ANCHORS:
    return None
```

Thử với schema đã bỏ `maxItems` trên 6 câu KIS đầu của `dress25`
(gọi API thật, chỉ sửa trong bộ nhớ, **không đụng file**):

```
dress25 KIS: 19 câu, _needs_multiple = 19 câu (100%)

DRESS_KIS_01: 3 anchor -> HỢP LỆ
DRESS_KIS_02: 3 anchor -> HỢP LỆ
DRESS_KIS_03: 3 anchor -> HỢP LỆ
DRESS_KIS_04: 3 anchor -> HỢP LỆ
DRESS_KIS_05: 3 anchor -> HỢP LỆ
DRESS_KIS_06: 3 anchor -> HỢP LỆ

>>> 6/6 qua validator (fidelity token/quantifier/color đều OK)
```

Nghĩa là sau khi bỏ một keyword, **19/19 câu dress25 sẽ dùng multi-anchor**.

⚠️ **Chưa đo được multi-anchor có làm điểm tốt lên hay không.** Nó mới chỉ
chuyển từ "không chạy" sang "chạy được". Phải chạy lại `--split dress25` sau khi
sửa mới biết. Đừng ship dựa trên giả định.

### Chỉ ảnh hưởng đúng schema này

Quét toàn repo: `maxItems` chỉ xuất hiện một lần (`multi_anchor.py:65`). Năm
schema còn lại (`EXPAND_SCHEMA`, `CONSTRAINTS_SCHEMA`, `PARSE_QUESTION_SCHEMA`,
`QA_RESULT_SCHEMA`, `PARSE_EVENTS_SCHEMA`) không dùng keyword không hỗ trợ nào.

---

## 5. ⛔ Phát hiện P0 — Q&A vượt ngân sách thời gian 30–60×

`timings.total_seconds` mỗi câu Q&A, RUN 3:

```
QA: [195.9, 210.6, 360.6, 404.2, 476.2]  giây
    = 3,3 · 3,5 · 6,0 · 6,7 · 7,9 phút
```

`CLAUDE.md` §2: ngân sách **≤30s** từ lúc gõ query tới lúc có kết quả, và
**~6 phút cho TOÀN BỘ một câu** gồm đọc đề, chạy, người duyệt, nộp.

Một câu Q&A hiện ăn hết **toàn bộ ngân sách của câu đó, có câu ăn gấp rưỡi** —
trước khi người thao tác kịp nhìn dòng đầu tiên.

KIS thì ổn: `total_seconds` median **0,9s**, max 15,2s (run 3). Chính là vì
multi-anchor không chạy — khi bật lên sẽ thành 3 lần gọi `search()` + 1 lần gọi
LLM planner + 3 lần dịch, phải đo lại độ trễ theo `CLAUDE.md` bất biến 10.

---

## 6. ⚠️ Phát hiện P1 — cùng fingerprint, khác kết quả

RUN 1 và RUN 3 cách nhau 9 phút, **cùng commit, cùng runtime_fingerprint, cùng
query set, cùng GT**, nhưng khác kết quả:

```
DRESS_QA_03     0.00 -> 1.00   status: failed -> success
DRESS_TRAKE_01  0.00 -> 0.47   top1 video: L21_V029 -> L22_V028
```

Toàn bộ phần "tốt lên" của run 3 so với baseline nằm đúng ở hai câu này.

### Nguyên nhân

RUN 1, Q&A hỏng sau ~11 giây:

```
DRESS_QA_01  status=failed  total_seconds=11.45
  error=QANoValidHypothesisError: Thử 16 shot (kể cả ứng viên nhánh text và
        mở rộng trong video) đều không suy luận được…
DRESS_QA_03  status=failed  total_seconds=11.73   (cùng lỗi)
```

11 giây cho 16 shot = LLM **không thực sự chạy**, nó lỗi ngay. RUN 3 cùng câu đó
mất 360s và 476s — tức lần này LLM chạy thật (và cache do run 1 làm ấm).

TRAKE khác kiểu: `event_descs` giống hệt nhau (lấy từ file query, không qua LLM),
nhưng thứ hạng video khác. TRAKE gọi `search()` cho từng sự kiện, mà `search()`
có hai đường suy giảm im lặng:

- `search.py:313-320` — dịch VI→EN lỗi thì **dùng nguyên tiếng Việt**, in cảnh
  báo ra stdout rồi chạy tiếp. Nhánh vector/objects yếu hẳn vì CLIP là model
  tiếng Anh.
- `search.py:326-334` `_an_toan()` — một nhánh chết thì trả `[]` và chạy tiếp.

Cả hai đều **cố ý** (điểm giảm còn hơn mất trắng), nhưng **không thứ nào được ghi
vào trace**. Kết quả: hai run "thành công" với chất lượng khác hẳn nhau mà
artefact không phân biệt được.

### Hệ quả cho audit

`runtime_fingerprint` pin **config + model + code**, không pin **kết quả thật của
lời gọi LLM**. Hai artefact cùng fingerprint **không** đảm bảo cùng điểm. Mọi so
sánh before/after phải kèm bằng chứng rằng dịch thuật và các nhánh search đều
sống trong cả hai lần chạy — hiện chưa có trường nào để kiểm.

Đây chính là khoảng trống `deterministic replay` đã đánh dấu "⚠️ một phần" ở
`00_MASTER.md` §K, nay có bằng chứng vận hành.

---

## 7. ✅ Đính chính `00_MASTER.md` §Q

Bản đầu tôi viết *"`wrong_frame` và `qa_reasoning` không có đường nào tự động
gán"*. **Sai.** Đúng là runner (`solve_query`) không gán chúng, nhưng
**evaluator có**, ở `dev_set/tools/run_evaluation.py:640-674`:

```python
if fin >= 1.0:            fc = None
elif task == "QA":        fc = "qa_reasoning" if retrieval_success else "retrieval_miss"
elif task == "TRAKE":     fc = "trake_order"  if đúng video có mặt else "retrieval_miss"
else:                     fc = "wrong_frame"  if đúng video có mặt else "retrieval_miss"
```

Bằng chứng vận hành: run 3 gán `wrong_frame` 14 lần, `retrieval_miss` 7 lần,
`trake_order` 1 lần.

Hai điểm cần lưu ý khi đọc số:

1. `failure_class` nghĩa là **"vì sao chưa đạt 1.0"**, không phải "câu này hỏng".
   `DRESS_KIS_01` đạt 0.80 vẫn mang nhãn `wrong_frame`. 14 `wrong_frame` **không**
   phải 14 câu thất bại.
2. Phần còn lại của §Q vẫn đúng: **runtime failure vẫn chưa có taxonomy riêng**
   (`timeout` / `rate_limit` / `provider_error` / `invalid_response`), và §6 ở
   trên cho thấy đó là khoảng trống có hậu quả thật.

---

## 8. Đề xuất phân loại theo cửa sổ deadline

| # | Việc | Rổ | Lý do |
|---|---|---|---|
| 1 | Bỏ `maxItems` khỏi `ANCHOR_SCHEMA` | **A — trước 28/08** | một dòng, đã xác minh với API thật, không mất ràng buộc; hiện là silent failure |
| 2 | Chạy lại `--split dress25` sau khi sửa (1) | **A** | bắt buộc — chưa ai biết multi-anchor làm điểm tăng hay giảm |
| 3 | Ghi cờ `translation_fallback` / `dead_branches` vào trace | **A nếu kịp** | không có nó thì không so được hai run, cũng không biết đêm thi có bị suy giảm im lặng không |
| 4 | Quyết định Q&A cho đợt 2 (3–8 phút/câu) | **A — quyết định vận hành** | để cuối buổi, hoặc giảm `TOP_K_SHOTS`/`MAX_SHOTS_TRIED`, hoặc bỏ Q&A nếu tính giờ chung |
| 5 | `planner_error` phải log lý do thật thay vì nuốt | B | `except Exception` trần che mất lỗi 400 suốt 3 ngày |
| 6 | Test schema đối chiếu provider thật (không mock) | B | đúng loại lỗi mà 39 test mock bỏ lọt |
| 7 | Taxonomy runtime failure | B | §6 |
| 8 | Rank 5 nguồn trong trace multi-anchor | B | `00_MASTER.md` §E |
| 9 | Dependency lock | B | `00_MASTER.md` §T |

**Không** đề xuất tune ngưỡng/trọng số nào trước đợt 2. Chưa có số sạch để tune.
