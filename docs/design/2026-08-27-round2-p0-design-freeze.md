# Round 2 P0 design freeze — 27/08/2026

Freeze này chỉ áp dụng cho lỗi KIS multi-anchor trước HCMAIC Batch 1 Round 2.
Bằng chứng runtime ngày 27/08 được ưu tiên hơn nhận định trước đó. Snapshot lúc
review: branch `codex/batch1-accuracy-repair`, HEAD
`8cad8e2239e2a452348082438f3188f4a8553e05`; không có tracked change. Các thư
mục run 27/08 và bản nháp GT đang untracked là artefact của người dùng, phải giữ
nguyên.

## Current P0

Hai run dress25 hoàn tất ngày 27/08 đều ghi 19/19 KIS là
`strategy=single`, `fallback_reason=planner_error`, dù 19/19 query cần planner
multi-anchor. Vì vậy Task 3 chưa chạy trong production; số KIS hiện tại là số
của đường single-anchor fallback, không phải bằng chứng đánh giá multi-anchor.

## Reproduced root cause

- `backend/retrieval/multi_anchor.py::ANCHOR_SCHEMA` hiện chứa
  `"maxItems": MAX_ANCHORS` trong schema của array `anchors`.
- Anthropic đã tái lập lỗi 400: array schema không hỗ trợ keyword `maxItems`.
  `plan_query()` bắt lỗi bằng `except Exception` và trả single plan với
  `planner_error`, nên lỗi trở thành silent fallback.
- Quét toàn bộ file Python trong repo cho thấy đây là occurrence `maxItems` duy
  nhất. Các provider schema còn lại, kể cả schema production và công cụ dev,
  không dùng keyword này. Các occurrence khác trong HEAD chỉ là báo cáo/diff
  audit lịch sử, không phải schema được gửi tới provider.

## Minimal intended change

Production diff phải đúng một dòng xóa khỏi `ANCHOR_SCHEMA`:

```python
"maxItems": MAX_ANCHORS,
```

Không đổi prompt, `MAX_ANCHORS`, validator, fallback, translation, token guard,
RRF, temporal bonus hay downstream. Thêm tối đa một regression test trong test
file hiện có để chứng minh schema gửi provider không còn `maxItems` và payload
bốn anchor vẫn fail closed ở Python.

## Invariants preserved

- `_validated_anchors()` vẫn kiểm `len(raw_anchors) > MAX_ANCHORS` và trả
  `None`; `MAX_ANCHORS` vẫn bằng 3.
- Mọi output provider trong production đi qua `json.loads()` rồi
  `_validated_anchors()` trước khi dịch hoặc tạo `QueryPlan`. Payload quá ba
  anchor vẫn về `strategy=single`, `fallback_reason=invalid_anchors`.
- Các guard string/list/schema shape, rỗng, trùng, fidelity màu/số/lượng và
  giới hạn 60 CLIP token không đổi.
- `ANCHOR_SCHEMA` chỉ được dùng làm tham số `json_schema` của `llm()`.
  `runner.py`, `search_multi()` và các downstream chỉ đọc `QueryPlan`/anchors;
  không code nào đọc hoặc phụ thuộc `maxItems`.
- Khẳng định `<=3` áp dụng cho production path
  `solve_query() -> plan_query()`. Việc dựng `QueryPlan` trực tiếp vốn không
  được schema bảo vệ trước repair và không bị thay đổi bởi repair này.
- `multi_anchor.py` nằm trong runtime fingerprint. Repair sẽ invalidate
  checkpoint/cache cũ theo thiết kế; một run không được trộn hai fingerprint.

## Files allowed to change

- `backend/retrieval/multi_anchor.py`: chỉ xóa một dòng `maxItems`.
- `tests/test_multi_anchor.py`: chỉ thêm regression test hẹp nêu trên.

## Files forbidden to change

- `backend/llm/adapter.py`
- `backend/retrieval/search.py`
- `backend/slot/allocator.py`
- `backend/tasks/trake.py`
- `backend/export/exporter.py`
- `run_minimal.py`
- `backend/tasks/runner.py`, `run.py`, `backend/tasks/qa.py`,
  `backend/tasks/qa_portfolio.py`
- Mọi file production, config, prompt, query, GT, index và exporter khác không
  nằm trong danh sách allowed ở trên.

## Verification plan

### Before repair

1. Ghi lại HEAD/status và giữ nguyên toàn bộ untracked artefact hiện có.
2. Baseline đã chạy:
   `.\.venv\Scripts\python.exe -m pytest tests\test_multi_anchor.py tests\test_task_runner.py -q -p no:cacheprovider`
   — `53 passed`.
3. Thêm một RED test bắt đúng nguyên nhân: schema của `anchors` không được có
   `maxItems`; cùng test cho provider trả bốn anchor faithful và yêu cầu
   `single/invalid_anchors` mà không gọi translation.

### After repair

1. `git diff --check`; diff chỉ được chạm hai file allowed, với production diff
   đúng một dòng xóa. Quét provider schema production phải không còn
   `maxItems`.
2. Chạy lại focused tests ở trên và full suite
   `.\.venv\Scripts\python.exe -m pytest -q`; không chấp nhận failure mới.
3. Với đúng backend/model Anthropic đã dùng ngày 27/08, chạy smoke qua schema
   thực sau repair trên ít nhất một KIS dress25: không còn lỗi 400, output qua
   `_validated_anchors()`, và multi plan chỉ có 2–3 anchor.
4. Chạy mới `python -m dev_set.tools.run_evaluation --split dress25 --out <new-run-dir>`
   với một runtime fingerprint sạch. Trước khi dùng cho Round 2, bắt buộc xác
   nhận: không còn `planner_error` do schema; không plan nào vượt ba anchor;
   không có KIS failure mới; KIS aggregate không thấp hơn mốc single-path ngày
   27/08 là `0.4000`; lưu query-level diff và latency. Không dùng biến động Q&A
   hoặc TRAKE trong run này để quyết định repair KIS.

## Rollback condition

Không dùng repaired commit cho Round 2 nếu diff vượt scope, focused/full tests
không xanh, Anthropic vẫn từ chối schema, bất kỳ multi plan nào vượt ba anchor,
hoặc dress25 sinh KIS failure mới hay KIS aggregate dưới `0.4000`. Rollback chỉ
hoàn nguyên repair/test này về HEAD đã ghi; không sửa adapter/search/config để
“cứu” repair. Do fingerprint đổi ở cả hai chiều, không resume checkpoint tạo từ
fingerprint của phiên bản còn lại.

## Explicit deferred items

- Mâu thuẫn thiết kế đã biết: PLAN nói TRAKE nên hưởng multi-anchor cho chọn
  event/video, nhưng TRAKE hiện tại không dùng multi-anchor và return qua nhánh
  riêng trước KIS planner. Đây là việc sau Round 2; không cần cho P0 hiện tại và
  không sửa bây giờ.
- Logging nguyên nhân thật của `planner_error`, taxonomy runtime failure và
  permanent live-provider contract test được hoãn sau Round 2.
- Mọi tuning prompt/anchor count/token/RRF/temporal/slot, mở multi-anchor sang
  task khác, hoặc findings audit không trực tiếp cần cho lỗi schema này đều
  nằm ngoài repair.

APPROVE MINIMAL P0 REPAIR
