# Task 3 report — KIS multi-anchor trên search hiện tại

## Trạng thái và interfaces

Đã triển khai KIS multi-anchor mà không đổi vector encoder/index/metric hay logic
năm nhánh trong `search.py`. Interfaces mới:

- `plan_query(query_vi, query_en=None) -> QueryPlan`: query ngắn trả single plan;
  query phức tạp gọi đúng một structured `llm()`, validate fidelity rồi dịch từng
  anchor bằng `query_understanding.translate()` và đếm bằng tokenizer CLIP hiện có.
- `search_multi(plan, top_k=100) -> list[dict]`: single plan pass-through một
  `search()`; multi plan gọi `search(..., group_by_shot=True)` riêng từng anchor,
  outer-RRF k=7 theo shot và soft temporal bonus 1,25 ở video đủ anchor/timestamp
  tăng không giảm.
- `QueryAnchor`/`QueryPlan` là frozen dataclass; `QueryPlan.to_dict()` đưa cấu
  trúc serializable vào `QueryRun.query_plan`.
- Row multi giữ contract cũ và thêm `anchor_ranks`, `anchor_contributions`,
  `temporal_order_match`, `query_anchors`; alias `ranks`/`contrib` là outer fusion
  để `QueryRun.source_*` không lẫn inner branch trace.

## Files

- `data/config/multi_anchor.py`: toàn bộ enable/anchor/token/RRF/bonus/pool và
  marker heuristic; fidelity dùng lexical entailment tổng quát trong module.
- `backend/retrieval/multi_anchor.py`: planner, validator, translation/token guard,
  shot fusion, representative metadata, temporal scoring và deterministic sort.
- `backend/tasks/runner.py`: chỉ nhánh KIS dùng plan mới; single/fallback giữ đúng
  một search với `query_en` caller; runtime fingerprint hash module mới.
- `tests/test_multi_anchor.py`, `tests/test_task_runner.py`: planner/fusion/runner
  integration; không gọi provider thật.
- File report này.

## RED → GREEN evidence

1. Single/fallback: RED `2 failed` do thiếu module; GREEN `2 passed in 1.27s`.
2. Max-3/token/fidelity/error fallback: RED `3 failed, 5 passed`; GREEN
   `8 passed in 1.35s`.
3. Outer RRF/temporal: RED `2 failed, 8 passed` do `NotImplementedError`; GREEN
   `10 passed in 1.04s` (một literal test được sửa từ 1/8 thành 1/11 vì fixture
   đặt candidate ở rank 4).
4. Runner trace/no duplicate retrieval: RED `1 failed` vì runner search lại query
   gốc; GREEN `1 passed in 1.19s`, đúng hai search cho hai anchor.
5. Ordered heuristic: RED `1 failed` vì query dài không thứ tự vẫn bật bonus;
   GREEN trong focused `25 passed`.
6. Mutation fidelity/representative: RED bắt được `vài`, `bạc` chưa chặn và row
   rank cao thiếu frame được giữ; GREEN cuối:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_multi_anchor.py tests/test_task_runner.py tests/test_load_clip_guard.py -q --basetemp .pytest-tmp-task3-final
```

Kết quả mới nhất: `34 passed in 5.47s`, exit code 0.

## Full suite và CLIP guard

Lượt full suite đầu không hợp lệ vì sandbox từ chối pytest temp mặc định:
`544 passed, 1 skipped, 1 failed, 157 errors`; toàn bộ fail/error hiển thị cùng
`PermissionError` ở `C:\Users\lehon\AppData\Local\Temp\pytest-of-lehon`.
Chạy lại đúng môi trường writable:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp .pytest-tmp-task3-run
```

Kết quả: `702 passed, 1 skipped, 2 warnings in 35.70s`, exit code 0. Hai warning
từ Starlette/httpx và google.genai dependency.

Guard không reindex:

```powershell
.\.venv\Scripts\python.exe scripts\verify_clip_space.py --n 10 --data-root data\raw\btc
```

Kết quả: 10/10 `ĐẠT`, cosine trung bình `0.9999`, nhỏ nhất `0.9993`; model
`ViT-B-32-quickgelu / openai`, 512 chiều. `py_compile` và `git diff --check`
focused đều exit code 0.

## Self-review và concerns

- Không sửa README, adapter LLM, search/vector/index, QA, TRAKE, evaluator, docs,
  manifest Task 1 hay ảnh `.tmp_*`; không gọi provider thật và không reindex.
- Planner lỗi/malformed, ít hơn hai anchor hợp lệ, lỗi dịch/tokenizer hoặc >60
  token đều fallback single, không giữ multi bán phần. Không có planner cache,
  nên không có cache identity mới hay cache hai query giống nhau cần kiểm.
- Temporal chỉ là multiplier, không filter; missing/reversed/incomplete video vẫn
  còn nguyên. Tie-break và representative metadata có test literal.
- Heuristic là config vận hành, cần tune bằng regression theo luật
  promotion; chưa có score acceptance vì task này cấm gọi service thật và GT
  holdout chưa được xác minh đầy đủ.

---

## Fix round 1 — fail-closed fidelity và ordered punctuation

### Findings và root cause

1. `_validated_anchors()` từng lọc riêng item sai rồi tiếp tục multi nếu còn hai
   item hợp lệ. Nay payload chỉ hợp lệ khi có tối đa ba item, mọi item là string
   không rỗng, unique và faithful; bất kỳ vi phạm nào trả single plan toàn bộ,
   giữ `query_en` caller và không dịch/search multi bán phần.
2. Marker từng chứa space literal (`" sau đó "`), nên dấu phẩy/chấm hoặc marker
   đầu-cuối câu không match. Nay marker phrase được so trên token Unicode liên
   tiếp, punctuation không ảnh hưởng; dấu `;`/`→` vẫn được xử lý tường minh.
3. Tuple màu/count đóng bỏ sót `màu rêu`, `nhóm`, `đám`, `hàng loạt`, `duy nhất`.
   Nay anchor phải là tập con token đã NFKC + casefold của query gốc. So theo tập
   cho phép tách, lặp chủ thể và đổi thứ tự token nhỏ, nhưng mọi token modifier,
   màu, chữ số hay số lượng mới đều fail closed.

### RED evidence

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_multi_anchor.py -q --basetemp .pytest-tmp-task3-fix1-red
```

Kết quả trước fix: `13 failed, 11 passed in 1.43s`. Failure đúng ba nhóm:
anchor sai vẫn `multi`, malformed bị lọc tới bước dịch, vocab bypass và query
`Đầu tiên, ... Sau đó, ...` không được nhận là multi/ordered.

### GREEN và phạm vi

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_multi_anchor.py tests\test_task_runner.py -q --basetemp .pytest-tmp-task3-fix1-green
```

Kết quả: `38 passed in 1.18s`, exit code 0. Fix round chỉ sửa:
`backend/retrieval/multi_anchor.py`, `data/config/multi_anchor.py`,
`tests/test_multi_anchor.py` và report này; không sửa/stage/commit file nào.

---

## Fix round 2 — bảo toàn quan hệ constraint và siết schema/translation

### Findings và cách sửa

1. Token-subset vẫn cho phép đổi `hai giờ` thành `hai người` hoặc chuyển `đỏ`
   từ `xe màu đỏ` sang `áo đỏ`. Validator nay giữ token-subset tổng quát và thêm
   local relation guard: cụm quantifier/digit + classifier/head phải xuất hiện
   liên tiếp trong query gốc; color value được phát hiện động qua marker `màu`
   và phải giữ đúng cụm head–`màu`–value hoặc head–value. Không quay lại danh
   sách tên màu đóng.
2. `cuối cùng`/`đầu tiên` đứng riêng bị loại khỏi transition markers. Temporal
   chỉ bật với marker rõ (`rồi`, `sau đó`, `trước/sau khi`, `tiếp/kế tiếp`, `→`)
   hoặc đủ cặp boundary `đầu tiên` + `cuối cùng`; punctuation vẫn không ảnh hưởng.
3. Planner payload phải có chính xác key `anchors`; extra property fail closed.
   Mỗi bản dịch phải là string sau `strip()` còn nội dung; empty/whitespace trả
   single plan với `translation_error` trước khi gọi tokenizer.

### RED evidence

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_multi_anchor.py -q --basetemp .pytest-tmp-task3-fix2-red
```

Kết quả đầu: `4 failed, 26 passed in 1.34s`, đúng hai relation case, `cuối cùng`
và extra property. Test translation rỗng ban đầu dùng exception bị production
catch nên chưa chứng minh boundary; đã sửa mock thành recorder, chạy riêng thu
được `2 failed in 1.32s` vì empty/whitespace vẫn tạo multi plan.

### GREEN và phạm vi

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_multi_anchor.py tests\test_task_runner.py -q --basetemp .pytest-tmp-task3-fix2-green
```

Kết quả: `44 passed in 1.20s`, exit code 0. Fix round chỉ sửa
`backend/retrieval/multi_anchor.py`, `data/config/multi_anchor.py`,
`tests/test_multi_anchor.py` và report này; không stage/commit.

---

## Fix round 3 — màu không marker, quantifier classifier và chronology

### Findings và cách sửa

1. Guard marker-derived không thấy `xe đỏ`/`áo trắng`. Config nay có danh sách
   màu Việt phổ biến làm guard phụ, còn màu tùy ý sau `màu` vẫn được khám phá
   động. Mọi color phrase dùng trong anchor phải giữ exact local head phrase ở
   query gốc; vì vậy `xe đỏ` không thể bị gắn lại thành `áo đỏ`.
2. `đôi`/`cặp` được đưa vào `QUANTIFIER_TERMS` ngoài vai trò classifier. Cụm
   `đôi/cặp + head` trong anchor phải xuất hiện nguyên dạng ở query, chặn
   `đôi giày`/`cặp vé` thành `đôi người`/`cặp người`.
3. Ordered boundary pair nay so token offset `first < last`, không chỉ presence.
   `Cuối cùng..., đầu tiên...` vì vậy không bật bonus.
4. Parser chronology chỉ xử lý đúng một cấu trúc hẹp: một `sau khi` với đúng hai
   anchor. `A sau khi B` đảo anchors và đánh lại ordinal thành B→A; `Sau khi B, A`
   giữ surface order. Nhiều hơn hai anchor hoặc nhiều marker là mơ hồ nên
   `ordered=false`; search vẫn chạy đủ anchor và không hard-filter.

### RED evidence

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_multi_anchor.py -q --basetemp .pytest-tmp-task3-fix3-red
```

Kết quả trước fix: `7 failed, 30 passed in 1.48s`, đúng màu không marker,
`đôi/cặp`, pair đảo, plan/fusion chronology và ba-anchor mơ hồ.

### GREEN và phạm vi

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_multi_anchor.py tests\test_task_runner.py -q --basetemp .pytest-tmp-task3-fix3-green
```

Kết quả: `51 passed in 1.35s`, exit code 0. Fix round chỉ sửa
`backend/retrieval/multi_anchor.py`, `data/config/multi_anchor.py`,
`tests/test_multi_anchor.py` và report này; không stage/commit.

---

## Fix round 4 — locate anchors quanh `sau khi` và pair precedence

### Findings và cách sửa

1. Không còn dùng `after_positions[0] == 0`. Với đúng hai anchor và một marker
   `sau khi`, planner locate exact token phrase của từng anchor trong query. Nếu
   marker nằm giữa hai spans, anchor sau marker được đưa trước; nếu marker nằm
   trước cả hai spans (kể cả có tiền tố), anchors được sort theo surface position.
   Không locate unique/chắc chắn thì `ordered=false`.
2. `_is_ordered()` kiểm mọi boundary pair hiện diện trước `ORDER_MARKERS`. Vì
   vậy `Sau đó..., đầu tiên...` fail direction gate thay vì được `sau đó` bật
   sớm; valid `Đầu tiên, ... Sau đó, ...` vẫn true.

### RED → GREEN evidence

```powershell
.\.venv\Scripts\python.exe -m pytest \
  tests\test_multi_anchor.py::test_sau_khi_co_tien_to_locate_anchor_va_giu_chronology_dung \
  tests\test_multi_anchor.py::test_pair_sau_do_truoc_dau_tien_uu_tien_gate_va_khong_bonus \
  -q --basetemp .pytest-tmp-task3-fix4-red
```

RED: `2 failed in 1.29s`; prefix plan bị đảo và pair đảo vẫn `ordered=true`.

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_multi_anchor.py tests\test_task_runner.py -q --basetemp .pytest-tmp-task3-fix4-green
```

GREEN: `53 passed in 1.23s`, gồm regression valid punctuation, direct
`A sau khi B` → B→A và ba-anchor mơ hồ `ordered=false`. Fix round chỉ sửa
`backend/retrieval/multi_anchor.py`, `tests/test_multi_anchor.py` và report;
không stage/commit.
