# Review Task 3 — KIS multi-anchor

## Kết luận

CHANGES REQUESTED. Focused tests hiện có pass (`28 passed`), nhưng còn hai lỗi
material so với brief và một lỗ hổng validator chưa được test.

## Findings

### [P1] Anchor không trung thành bị bỏ riêng thay vì fallback toàn bộ plan

- File: `backend/retrieval/multi_anchor.py:120-151`
- `_validated_anchors()` lọc bỏ anchor không trung thành, rồi `plan_query()` vẫn
  trả `strategy="multi"` nếu còn ít nhất hai anchor hợp lệ. Chính test
  `test_reject_anchor_bia_so_luong_chu_so_hoac_mau` đang khóa hành vi này.
- Brief yêu cầu **planner lỗi hoặc anchor không trung thành phải fallback về dịch
  hiện tại**. Với payload ba anchor có một anchor bịa màu/số lượng, code hiện vẫn
  thay đổi đường retrieval thay vì chạy đúng một single search như fallback.
- Cần coi sự xuất hiện của bất kỳ item sai type/rỗng/trùng/không trung thành (và
  payload vượt giới hạn nếu adapter không enforce schema) là plan invalid; trả
  single plan với lý do rõ ràng. Test phải xác nhận chỉ một `search()` và giữ
  nguyên `query_en` caller.

### [P2] Nhận diện thứ tự bỏ sót cú pháp có dấu câu rất phổ biến

- File: `backend/retrieval/multi_anchor.py:79-88`
- File: `data/config/multi_anchor.py:13-32`
- Logic dùng substring có khoảng trắng hai bên. Vì vậy query tuần tự rõ ràng
  `Đầu tiên, người đàn ông mở cửa. Sau đó, anh ấy bước vào.` trả
  `_is_ordered(...) == False`; `sau đó,` và `đầu tiên,` không khớp các marker
  `" sau đó "`, `" đầu tiên "`. Query đủ dài vẫn được planner tách multi nhưng
  mất soft temporal bonus, trái yêu cầu query tuần tự phải `ordered=true`.
- Nên match theo biên từ/phrase không phụ thuộc punctuation và thêm test cho dấu
  phẩy/chấm. Marker chỉ mang nghĩa vị trí như “phía trước” không được làm ordered.

### [P2] Validator “màu/số lượng mới” có thể bị bypass ngoài danh sách đóng

- File: `backend/retrieval/multi_anchor.py:91-111`
- File: `data/config/multi_anchor.py:34-43`
- Validator chỉ nhận diện term có sẵn trong hai tuple. Ví dụ
  `_is_faithful("Nhóm người mặc áo màu rêu đứng cạnh quầy", "Người đứng cạnh quầy")`
  hiện trả `True`: cả số lượng “nhóm” và màu “rêu” đều mới nhưng không có trong
  vocabulary. Điều này không thỏa contract tuyệt đối “chặn màu/số lượng mới”, và
  prompt LLM không phải validation boundary.
- Cần mở rộng/đổi representation của constraint detection để ít nhất bao phủ các
  dạng nhóm/đám/hàng loạt/duy nhất và cụm `màu <term>`; thêm mutation test cho các
  bypass này. Nếu không thể xác minh an toàn, phải fallback single.

## Evidence

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_multi_anchor.py tests\test_task_runner.py -q --basetemp <writable-dir>
# 28 passed in 1.13s

.\.venv\Scripts\python.exe -c "from backend.retrieval.multi_anchor import _is_ordered,_is_faithful; ..."
# ('Đầu tiên, ... Sau đó, ...', False)
# _is_faithful('Nhóm người mặc áo màu rêu đứng cạnh quầy', 'Người đứng cạnh quầy') == True
```

Không thấy thay đổi ngoài phạm vi ở `search.py`, vector/index hoặc
`backend/llm/adapter.py`. Outer-RRF k=7, equal anchor weights, deterministic outer
tie-break và trace aliases đúng theo implementation hiện tại.

---

## Re-review commit `3f50bfe`

### Trạng thái ba finding cũ

1. **ADDRESSED** — `_validated_anchors()` nay fail toàn plan khi item rỗng, sai
   type, trùng, không faithful hoặc vượt ba; test xác nhận fallback giữ
   `query_en` caller và chỉ gọi một `search()`.
2. **ADDRESSED** cho case đã nêu — marker được match theo token nên
   `Đầu tiên, ... Sau đó, ...` nay có `ordered=True`; query dài không có marker
   trong test vẫn `ordered=False`.
3. **ADDRESSED** cho bypass bằng token hoàn toàn mới — token-subset chặn được
   `nhóm`, `đám`, `hàng loạt`, `duy nhất`, `màu rêu` khi chúng không xuất hiện
   trong original.

### Findings mới

#### [P1] Token-set subset vẫn cho phép bịa lại quan hệ màu/số lượng

- File: `backend/retrieval/multi_anchor.py:106-117`
- Kiểm tra theo **set** chỉ chứng minh từng token xuất hiện ở đâu đó, không chứng
  minh constraint gắn đúng đối tượng. Case thực tế:

  ```python
  original = (
      "Lúc hai giờ, một người mặc áo trắng đứng cạnh chiếc xe màu đỏ "
      "rồi bước vào cửa hàng."
  )
  _is_faithful("Hai người bước vào cửa hàng", original)       # True
  _is_faithful("Người mặc áo đỏ bước vào cửa hàng", original) # True
  ```

  Anchor thứ nhất đổi “hai giờ” thành hai người; anchor thứ hai chuyển màu đỏ
  của xe sang áo người. Cả hai là detail mới làm thu hẹp retrieval sai, đúng lỗi
  fidelity mà plan yêu cầu chặn. Test “đổi trật tự token” hiện còn khóa một policy
  quá rộng. Cần kiểm context/local relation của number/color/count (hoặc dùng một
  representation extractive an toàn hơn); không thể coi bag-of-words subset là
  entailment.

#### [P2] Marker `đầu tiên/cuối cùng` bật temporal cho thứ tự đối tượng, không phải sự kiện

- File: `backend/retrieval/multi_anchor.py:91-103`
- File: `data/config/multi_anchor.py:22-31`
- `_is_ordered("Người cuối cùng trong hàng đang đứng cạnh quầy cùng nhiều hành khách chờ mua vé ở khu vực rộng phía trước")`
  hiện trả `True`. “Cuối cùng trong hàng” là vị trí một người, không mô tả chuỗi
  sự kiện; nếu planner tách query dài này, mọi row của video tình cờ có timestamp
  tăng sẽ nhận 1,25 sai. Yêu cầu là chỉ bonus khi quan hệ thời gian rõ ràng.
- Cần loại marker đơn nghĩa mơ hồ hoặc đòi cấu trúc nhiều mốc/clause đủ chứng minh
  tuần tự. Thêm negative test có chính token marker, không chỉ query hoàn toàn
  không chứa marker.

#### [P2] Fail-closed chưa bao phủ đầy đủ schema và bản dịch rỗng

- File: `backend/retrieval/multi_anchor.py:119-172`
- Payload có `additionalProperties` vẫn được nhận dù `ANCHOR_SCHEMA` cấm, ví dụ
  `{"anchors": [<2 anchors hợp lệ>], "extra": "schema violation"}`. Không nên
  giả định mọi backend luôn enforce JSON schema khi code đã đặt boundary
  fail-closed.
- `translate()` trả chuỗi rỗng/whitespace không raise; token count của empty CLIP
  caption vẫn nhỏ hơn 60 nên plan multi được chấp nhận và vector branch encode
  prompt rỗng. Cần kiểm output là `str` không rỗng trước tokenizer và fallback.

### Evidence re-review

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_multi_anchor.py tests\test_task_runner.py -q --basetemp <writable-dir>
# 38 passed in 1.17s
```

**Verdict: CHANGES REQUESTED.** Không thấy regression mới ở RRF/runner trong diff
scoped, nhưng ba case trên vẫn làm temporal/fidelity hoặc schema fail-open.

---

## Re-review fix round 2 commit `f9dcacb`

### Trạng thái bốn finding vòng trước

1. **ADDRESSED cho case khóa** — “hai giờ” → “hai người” bị chặn nhờ local
   quantifier context; màu `xe màu đỏ` → `áo đỏ` cũng bị chặn.
2. **ADDRESSED cho case khóa** — một mình `cuối cùng trong hàng` không còn bật
   ordered; cặp `đầu tiên` + `sau đó/cuối cùng` vẫn bật.
3. **ADDRESSED** — payload chỉ được có chính xác key `anchors`.
4. **ADDRESSED** — translation không phải string hoặc chỉ whitespace fallback
   trước tokenizer, giữ `query_en` single path.

### Findings mới

#### [P1] Color/count context vẫn fail-open với cách diễn đạt phổ biến không có `màu`

- File: `backend/retrieval/multi_anchor.py:122-195`
- `_preserves_color_context()` chỉ khám phá color token đứng sau literal `màu`.
  Query AIC tự nhiên thường viết `áo trắng`, `xe đỏ`; khi đó `declared_colors`
  rỗng và bag-of-token lại cho phép chuyển thuộc tính:

  ```python
  _is_faithful(
      "Người mặc áo đỏ bước vào cửa hàng",
      "Người mặc áo trắng đứng cạnh xe đỏ rồi bước vào cửa hàng",
  )  # True
  ```

- Tương tự, `đôi`/`cặp` chỉ nằm trong `COUNT_CLASSIFIERS` chứ không phải
  `QUANTIFIER_TERMS`, nên khi đứng độc lập chúng không được kiểm context:

  ```python
  _is_faithful("Cặp người đứng cạnh xe",
               "Một cặp vợ chồng đứng cạnh xe rồi người cầm cặp sách")  # True
  ```

- Đây vẫn là đúng failure mode “gắn màu/số lượng sang head noun khác”. Cần nhận
  diện color thường gặp kể cả không có marker và coi classifier có nghĩa
  quantifier độc lập (`đôi`, `cặp`, cùng mutation tương tự) là context-bearing.

#### [P1] Ordered pair không kiểm vị trí; `sau khi` còn đảo chronology so với anchor ordinal

- File: `backend/retrieval/multi_anchor.py:87-95`
- `ORDER_MARKER_PAIRS` chỉ kiểm hai phrase cùng tồn tại. Hai câu sau đều trả
  `True`:

  ```python
  _is_ordered("Đầu tiên người mở cửa, cuối cùng người bước ra")
  _is_ordered("Cuối cùng người bước ra, đầu tiên người mở cửa")
  ```

  Nhưng planner được yêu cầu trả anchor theo **original order**, nên case thứ hai
  sẽ bonus timestamp `cuối cùng <= đầu tiên`, ngược chronology.
- `Người rời đi sau khi đóng cửa` cũng có cùng lỗi: original anchor order là
  `[rời đi, đóng cửa]`, còn thứ tự thời gian đúng là `[đóng cửa, rời đi]`.
  Boolean `ordered` không đủ nếu marker có semantics đảo clause; temporal scoring
  hiện luôn dùng ordinal tăng.
- Cần chỉ bật bonus khi thứ tự anchor thực sự là chronological (kiểm vị trí pair,
  hoặc planner trả explicit chronological order đã validate). Thêm negative test
  pair đảo và case `A sau khi B`; nếu chưa biểu diễn được, fail safe bằng không
  bonus thay vì bonus ngược.

### Evidence vòng 2

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_multi_anchor.py tests\test_task_runner.py -q --basetemp <writable-dir>
# 44 passed in 1.23s
```

**Verdict: CHANGES REQUESTED.** Bốn regression case trực tiếp đã xanh, nhưng hai
mutation trên vẫn vi phạm fidelity/temporal semantics và có thể tăng sai rank
không phát lỗi.

---

## Final scoped re-review fix round 3 commit `41609d0`

### Trạng thái finding vòng trước

- **ADDRESSED** — màu phổ biến không có marker được bind với local head noun;
  `Người mặc áo đỏ` không còn faithful khi đỏ thuộc `xe đỏ`.
- **ADDRESSED** — `đôi`/`cặp` nay cũng là quantifier và giữ local context.
- **ADDRESSED cho pair `đầu tiên` → `cuối cùng`** — vị trí marker được so sánh,
  pair đảo không còn bật bonus.
- **ADDRESSED cho đúng hai mẫu test `sau khi` không có tiền tố** — `A sau khi B`
  được đảo thành B→A, `Sau khi B, A` giữ B→A; case ba anchor tắt bonus.

### Finding còn lại

#### [P1] Chronology vẫn bị đảo sai khi `sau khi` có tiền tố; pair với `sau đó` bỏ qua position gate

- File: `backend/retrieval/multi_anchor.py:87-96,197-213`
- `_chronological_anchors()` dùng điều kiện `after_positions[0] == 0` để phân biệt
  `Sau khi B, A` với `A sau khi B`. Marker không ở token 0 không đồng nghĩa clause
  A đứng trước marker. Câu tự nhiên có tiền tố bị đảo sai:

  ```python
  anchors = ("Đóng cửa", "Người rời đi")  # original surface order
  "Vào buổi tối, sau khi đóng cửa, người rời đi"
  # code hiện đổi thành: Người rời đi → Đóng cửa, ordered=True
  # chronology đúng:       Đóng cửa → Người rời đi
  ```

  Vì `search_multi()` dùng ordinal này để nhân 1,25, video đúng chronology sẽ
  không được thưởng còn video đảo chronology có thể được thưởng — lỗi rank im
  lặng, không chỉ là false negative.
- Ngoài ra `ORDER_MARKER_PAIRS` có `("đầu tiên", "sau đó")`, nhưng `sau đó`
  đã nằm trong `ORDER_MARKERS` và làm `_is_ordered()` return sớm. Do đó
  `Sau đó người bước ra, đầu tiên người mở cửa` vẫn trả `True` dù pair đảo; anchor
  giữ surface order và bonus ngược.
- Cần suy clause/anchor span quanh marker thay vì dùng marker-at-zero, hoặc tắt
  temporal bonus khi không chứng minh được chronology. Generic transition marker
  cũng phải qua direction/position validation nếu query chứa boundary pair đảo.
  Thêm đúng hai mutation trên và test tới `temporal_order_match`, không chỉ bool.

### Evidence vòng 3

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_multi_anchor.py tests\test_task_runner.py -q --basetemp <writable-dir>
# 51 passed in 1.25s
```

Các phần còn lại của brief scoped (fallback một search + giữ `query_en`, giới hạn
anchor/token, fail-closed payload/translation, outer-RRF, trace, config và không
đụng search/vector/index/adapter) không có finding P1/P2 mới.

**Verdict: CHANGES REQUESTED** do temporal bonus vẫn có đường thưởng ngược rõ ràng.

---

## Re-review fix round 4 commit `7dcd8db`

### Xác nhận findings cuối

- **ADDRESSED** — `_chronological_anchors()` không còn suy hướng từ việc marker
  có ở token 0 hay không. Nó định vị duy nhất từng anchor quanh span `sau khi`:
  `A sau khi B` được chuẩn hóa B→A; `[tiền tố], sau khi B, A` giữ B→A. Nếu anchor
  không định vị duy nhất hoặc cấu trúc vượt parser hẹp, temporal bonus tắt.
- **ADDRESSED** — boundary pairs được xét trước generic transition marker. Query
  `Sau đó B, đầu tiên A` nay `ordered=False` và các row không nhận
  `temporal_order_match`; pair thuận vẫn hoạt động.

### Verification

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_multi_anchor.py tests\test_task_runner.py -q --basetemp <writable-dir>
# 53 passed in 1.22s
```

Kiểm trực tiếp `[tiền tố], sau khi B, A` trả anchors `(B, A), ordered=True` và
pair đảo `Sau đó B, đầu tiên A` trả `False`. Không thấy regression P1/P2 mới do
span-location hoặc pair priority. Các fallback mơ hồ theo hướng tắt bonus phù hợp
soft temporal contract; phần còn lại của brief Task 3 vẫn giữ nguyên.

**Verdict: APPROVED.**
