# 📋 Báo Cáo Kỹ Thuật — Task D6.1 (Preflight check) + D4.1 (Chỉnh slot theo dữ liệu)

> **Ngày:** 19/08/2026 · **Hạn:** 19–20/08/2026 · **Đóng băng:** 20/08 · **Thi đợt 1:** 21/08
>
> **Người thực hiện:** Minh Hoàng
>
> **Phạm vi:**
> - D6.1 — `scripts/preflight_check.py` (mới) + `tests/test_preflight.py` (mới, 26 test)
> - D4.1 — `reports/slot_tuning.md` (mới) + `data/config/slot_budget.py` +
>   `app/score_simulator.py` (thêm chế độ `shotrank`) + `tests/test_score_simulator.py`
> - Kèm theo (cùng phiên): `app/debug_ui.py` + `tests/test_debug_ui.py` — xem §8
>
> **Trạng thái: CHẠY ĐƯỢC ĐẦU-CUỐI cả hai task.** 499 test xanh (33 test mới).
> Preflight chạy thật trên hạ tầng thật, exit code 0. D4.1 đã chốt bảng bằng số đo,
> có báo cáo riêng ở `reports/slot_tuning.md`.
>
> **Preflight bắt được 2 lỗi thật ngay lần chạy đầu** — xem §3. Một trong hai là
> Elasticsearch chết câm 4/5 nhánh search mà không ai biết.

---

## Mục lục
1. [Vì sao hai task này đi chung một báo cáo](#1-vì-sao-hai-task-này-đi-chung-một-báo-cáo)
2. [D6.1 — Thiết kế preflight](#2-d61--thiết-kế-preflight)
3. [⭐ D6.1 — Hai lỗi thật bắt được ngay lần chạy đầu](#3--d61--hai-lỗi-thật-bắt-được-ngay-lần-chạy-đầu)
4. [D6.1 — Khuyết điểm tự tìm ra khi chạy, và bản sửa](#4-d61--khuyết-điểm-tự-tìm-ra-khi-chạy-và-bản-sửa)
5. [D4.1 — Tóm tắt kết luận](#5-d41--tóm-tắt-kết-luận)
6. [D4.1 — Điều dev set KHÔNG đo được](#6-d41--điều-dev-set-không-đo-được)
7. [Đo độ trễ](#7-đo-độ-trễ)
8. [Việc kèm theo — UI debug định tuyến sai dạng bài](#8-việc-kèm-theo--ui-debug-định-tuyến-sai-dạng-bài)
9. [Phần KHÔNG đụng — báo cho chủ file](#9-phần-không-đụng--báo-cho-chủ-file)
10. [Đối chiếu đặc tả](#10-đối-chiếu-đặc-tả)
11. [Cách chạy · việc tiếp theo](#11-cách-chạy--việc-tiếp-theo)

---

## 1. Vì sao hai task này đi chung một báo cáo

Chúng ăn vào nhau ở đúng một điểm: **cả hai đều là "đo rồi mới tin"**.

- D4.1 hỏi *"bảng chia slot nào đúng?"* → trả lời bằng số đo trên dev set, không bằng
  cảm giác.
- D6.1 hỏi *"hệ thống có thật sự sẵn sàng không?"* → trả lời bằng cách CHẠY THẬT từng
  mục, không bằng cách tick tay.

Và chúng gặp nhau ở nhóm G của preflight: mục `bảng slot đủ 100` kiểm chính hằng mà
D4.1 vừa đổi. Đổi bảng mà quên kiểm tổng là bài nộp thiếu dòng — mất điểm miễn phí,
không có gì crash.

Thêm một lý do thực tế: D4.1 **không cần Docker** (chỉ đọc parquet + candidates đã
lưu), còn D6.1 thì cần. Nên làm song song được — D4.1 chạy trong lúc chờ hạ tầng.

---

## 2. D6.1 — Thiết kế preflight

### 2.1. Nguyên tắc lõi: KHÔNG viết lại phép kiểm nào

Mọi mục đều gọi lại code đã có và đã có test:

| Nhóm | Kiểm gì | Gọi lại cái gì |
|:---|:---|:---|
| A. Môi trường | interpreter + 5 thư viện lõi + 5 tuỳ chọn | `importlib` |
| B. Hạ tầng | ES ping + đếm doc từng index · Milvus + đếm vector · API `/health` | `es_client.connect`, `milvus_client.connect` |
| C. Dữ liệu | 5 parquet lõi · `.meta.json` · frame_map 2 dạng khoá · video_info | `backend.export._read_columns`, `load_frame_map`, `n_frames_of` |
| D. Vector | index cùng không gian · vector chuẩn hoá L2 | `assert_index_meta(strict=True)`, `verify_norms()` |
| E. Đường nộp | 3 dạng bài × 100 dòng → validate → .zip → validate_zip | `backend.slot.allocate`, `backend.export` |
| F. Độ trễ | 1 truy vấn KIS end-to-end, đối chiếu 30s | `backend.retrieval.search` |
| G. Cấu hình | bảng slot đủ 100 · Final Score khớp ví dụ BTC · hằng định dạng nộp | `data.config.*` |

Viết lại ở đây = có **bản thứ hai** của cùng một luật, và hai bản sẽ lệch nhau đúng
vào hôm cần nhất. Script chỉ GHÉP và IN.

### 2.2. Ba trạng thái, không phải hai

```
PASS  — đã chạy thật và đúng
FAIL  — đã chạy thật và sai   → exit code 1
SKIP  — chưa chạy được (thiếu Docker/thư viện), KÈM LÝ DO
```

Gộp SKIP vào PASS là điều tệ nhất một preflight có thể làm: nó biến *"chưa kiểm"*
thành màu xanh — đúng cái cảm giác an toàn giả mà script này sinh ra để phá. Nên khi
exit 0 mà vẫn còn mục SKIP, output in riêng một khối:

```
CHƯA KIỂM (không phải đã đạt):
  - A. Môi trường / thư viện tuỳ chọn: fastapi → mất API /search + /submit
```

### 2.3. Ngoại lệ không được giết cả script

Một mục ném lỗi mà làm sập script thì các mục phía sau không bao giờ chạy — người vận
hành sửa xong lỗi đầu lại phát hiện lỗi thứ hai, sửa xong lại lỗi thứ ba. Ba vòng như
vậy lúc 2 giờ sáng là hết đêm. `run_check()` nuốt mọi ngoại lệ → FAIL kèm tên lỗi, rồi
đi tiếp, và đưa **toàn bộ** danh sách việc phải sửa trong một lượt.

Ngoại lệ duy nhất được hạ xuống SKIP: lỗi **kết nối** ở mục `needs_infra=True`.

### 2.4. Test: mỗi mục phải FAIL được

Một preflight không bao giờ đỏ thì tệ hơn không có preflight. Nên 26 test trong
`tests/test_preflight.py` phần lớn là **làm hỏng có chủ đích** rồi khẳng định mục
tương ứng chuyển đỏ:

| Test | Làm hỏng gì | Phải ra |
|:---|:---|:---|
| `test_none_becomes_skip` | hàm trả `None` | SKIP, **không** PASS |
| `test_exception_does_not_kill_script` | hàm ném `ValueError` | FAIL, không ném ra ngoài |
| `test_parquet_missing_file_is_fail` | trỏ `REPO_ROOT` vào thư mục rỗng | FAIL + tên người đi hỏi |
| `test_slot_budget_fails_when_allocation_is_short` | `budget_per_shot` trả thiếu | FAIL |
| `test_scoring_formula_fails_when_thresholds_drift` | đổi `K_THRESHOLDS` | FAIL |
| `test_latency_over_budget_is_fail` | `search()` chậm hơn ngân sách | FAIL |
| `test_main_json_keeps_exit_code` | `--json` | vẫn exit 1 |

---

## 3. ⭐ D6.1 — Hai lỗi thật bắt được ngay lần chạy đầu

### 3.1. 🔴 Elasticsearch chết câm — 4/5 nhánh search không chạy

```
B. Hạ tầng
  HỎNG  Elasticsearch    http://127.0.0.1:9200 đang sống nhưng client không dùng được
                         — Elasticsearch ĐANG CHẠY nhưng từ chối client: lệch phiên bản.
```

Nguyên nhân: **client python `9.5.0` vs server `8.13.4`** → `media_type_header_exception`.
`backend/requirements.txt` ghi đúng ràng buộc `elasticsearch>=8.13,<9`; môi trường bị
nâng cấp lệch sau đó.

**Vì sao đây là ca đắt nhất trong cả báo cáo:** `search()` bọc từng nhánh trong
try/except để một nhánh chết không kéo sập cả câu (đúng thiết kế). Hậu quả là cả bốn
nhánh `metadata` · `objects` · `ocr` · `asr` **chết câm**, hệ chạy bằng mỗi nhánh
vector, kết quả vẫn ra, độ trễ vẫn đẹp, **và không có gì báo đỏ**. Đúng loại lỗi im
lặng mà CLAUDE.md §12 nói tới.

Đã vá về đúng ràng buộc repo đã khai (`8.19.3`). Sau khi vá:

```
  ĐẠT   Elasticsearch    133ms  metadata=873 · objects=177,321 · ocr=160,393 · asr=13,415
```

> **Bài học ghi lại:** mục này cố tình **đếm doc từng index** chứ không chỉ ping. Một
> ES sống nhưng index rỗng cũng cho ra `search()` "chạy bình thường, không kết quả".

### 3.2. 🟡 `fastapi` chưa cài — API `/search` + `/submit` không chạy được

Không chặn nộp (đường nộp offline vẫn đủ), nhưng chặn thao tác qua UI lúc thi. Đang ở
trạng thái SKIP kèm lý do, không bị giấu thành xanh.

---

## 4. D6.1 — Khuyết điểm tự tìm ra khi chạy, và bản sửa

Bản đầu của `run_check()` xếp **mọi** `ConnectionError` ở mục `needs_infra` vào SKIP.
Chạy thật thì lộ ra: ca ES §3.1 bị xếp nhầm thành *"chưa kiểm được"* — tức preflight
nhìn thẳng vào một hệ thống hỏng nặng rồi im lặng. Chính xác cái nó sinh ra để phá.

**Sửa:** thêm `_port_responds()` để phân biệt hai ca trông giống hệt nhau:

| Hiện tượng | Nghĩa là | Trạng thái |
|:---|:---|:---|
| cổng 9200 im lặng | chưa bật Docker | SKIP |
| cổng 9200 trả lời, client vẫn bị từ chối | **lỗi cấu hình thật, sửa được ngay** | FAIL |

Không so chuỗi thông điệp lỗi (dễ vỡ) — probe cổng là tín hiệu thật. Chốt bằng 3 test
(`test_elasticsearch_down_is_skip`, `test_elasticsearch_alive_but_client_rejected_is_fail`,
`test_port_responds_treats_http_error_as_alive`).

---

## 5. D4.1 — Tóm tắt kết luận

> Chi tiết đầy đủ + toàn bộ bảng số: **`reports/slot_tuning.md`** (đây là file mà
> BUILD_TASKS D4.1 chỉ đích danh). Mục này chỉ tóm tắt.

```python
# data/config/slot_budget.py — GIỮ NGUYÊN bảng của Công Lý
SLOT_BUDGET = [(1, 6), (4, 4), (10, 2), (58, 1)]      # phủ 73 shot
```

> **20/08 — đã đảo lại.** Bảng từng được đổi sang `[(100, 1)]` (commit `973e397`) rồi
> hoàn về nguyên trạng. Lý do ở §5.5: số đo chỉ phủ **một** trục (bề rộng), còn trục
> chiều sâu — thứ bảng này đang cược — dev set hiện tại không đo được. Đổi một bảng
> đang chạy dựa trên bằng chứng nửa vời, ngay trước đợt 1, là rủi ro không cần thiết.
>
> Kết quả thật của D4.1 vì vậy **không phải** một bảng mới, mà là: (a) đo được phân bố
> hạng shot lần đầu, (b) chỉ ra dev set không đo được cái gì, (c) **tìm và sửa một lỗi
> thật trong `allocator.py`** (§5.6).

### 5.1. Trả nợ trước khi đo

Commit `5b7b10c` mang message `tune(D4.1): expand SLOT_BUDGET` đã đổi bảng **trước khi
có số đo nào**. Việc đầu tiên của task là trả món nợ đó.

Kèm theo, sửa một nhãn gõ tay đã lệch: `CANDIDATE_TABLES` ghi cứng `"hiện tại 3×8"`
trong khi `SLOT_BUDGET` đã đổi từ lâu — nhãn sai đó đi thẳng vào bảng so sánh, tức báo
cáo tune slot ghi tên một bảng **không phải bảng vừa đo**. Giờ nhãn sinh ra từ hằng.

### 5.2. Thêm chế độ `shotrank` — câu hỏi đặc tả bắt trả lời trước

Đặc tả D4.1: *"shot đúng thường xếp hạng bao nhiêu trên dev set?"*. Trước đó không có
công cụ nào trả lời được. Kết quả trên 23 câu KIS:

- trung vị **10**, lớn nhất **95**, chỉ 3/23 câu ở hạng 1
- **2 câu (K18 hạng 80, K01 hạng 95) không được cấp slot nào** với bảng cũ phủ 73 shot
  → trượt chắc chắn **vì bảng ngân sách**, không phải vì search kém
- 4 câu không có shot đúng trong 100 ứng viên → việc của tầng search, slot bất lực

### 5.3. Bằng chứng từ tài liệu BTC

Đọc `Thong tin vong So tuyen AIC2026.pdf` mục 2.1 — lần đầu có **con số** thay vì giả
định (`slot_budget.py` trước đó ghi `# TODO: BTC — chưa công bố`):

| Dạng bài | Cửa sổ trong ví dụ | Độ rộng |
|:---|:---|---:|
| Textual KIS | `[500, 510]` | **11 frame** |
| Q&A | `[800, 900]` | 101 frame |
| TRAKE | *"thường rất ngắn, thông thường **dưới 10 frame**"* | ~10 frame |

Shot median của mình là **69 frame** → cửa sổ KIS hẹp hơn shot ~6 lần. "Trúng shot"
KHÔNG đồng nghĩa "trúng đáp án".

### 5.4. Kết quả

| | Bảng đang dùng (73 shot) | Nếu phủ 100 shot |
|:---|---:|---:|
| Final (replay, 23 câu KIS) | 0.470 | 0.487 |
| R@100 | 0.739 | 0.826 |
| R@1 / R@5 / R@20 / R@50 | 0.130 / 0.261 / 0.522 / 0.696 | **giống hệt** |

Toàn bộ chênh lệch nằm ở R@100 — đúng hai câu ở §5.2. `sweep` (phương pháp độc lập,
quét trên shot thật tại đúng phân bố hạng đo được) cho kết luận cùng chiều ở mọi giả
định độ rộng cửa sổ.

**Nhưng cột phải KHÔNG được áp dụng** — xem §5.5.

### 5.5. Vì sao đo xong mà không đổi bảng

Cột phải chỉ trả lời câu hỏi *"phủ rộng có đáng không"*. Nó **không** trả lời câu hỏi
đối ngẫu *"đào sâu có đáng không"* — và bảng đang dùng cược vào đúng câu hỏi thứ hai
(6 slot cho hạng 1, 4 slot cho hạng 2–5).

Dev set không thể trả lời câu thứ hai, vì lý do ở §6: cửa sổ ground truth được dựng từ
chính keyframe. Đổi bảng lúc này là **bỏ một canh bạc chưa kiểm chứng để lấy một canh
bạc khác cũng chưa kiểm chứng** — chỉ khác là canh bạc mới chưa từng chạy trên dữ liệu
thật lần nào, và đợt 1 còn 1 ngày.

Thêm nữa, đo lại độ phủ TRONG shot (§5.6) cho thấy chiều sâu **đáng giá hơn tao tưởng**
khi cửa sổ hẹp: shot 69 frame, cửa sổ 11 frame (đúng con số BTC) — 6 slot phủ **0.95**,
1 slot chỉ **0.19**. Bảng của Công Lý cấp 6 slot cho đúng hạng 1, và `shotrank` cho
trung vị hạng 10, tức chiều sâu rơi gần vùng shot đúng hay nằm.

Điều kiện đổi sang `[(100,1)]` ghi tường minh trong `slot_budget.py` và
`reports/slot_tuning.md §6`.

### 5.6. ⭐ Lỗi thật tìm được khi đo chiều sâu — `_spread_evenly`

**Đã sửa, `backend/slot/allocator.py`.** Đây mới là kết quả có giá trị nhất của D4.1.

Đi tìm câu trả lời cho "đào sâu có đáng không" thì lộ ra đào sâu đang **hỏng**. Bản cũ
rải `m` điểm bằng `a + round(i·(b-a)/(m-1))` — công thức này **luôn gồm cả hai mép**
vùng rải. Với `m == 2` nó cho đúng `[a, b]`: hai mép, bỏ trống nguyên khúc giữa.

Vùng rải `[6, 62]` trong shot 69 frame:

| m | bản cũ | w=11 | w=20 | w=35 |
|---:|:---|---:|---:|---:|
| 1 | `[34]` | 0.19 | 0.40 | 1.00 |
| 2 | `[6, 62]` | 0.24 | **0.28** | **0.40** |

**Cấp thêm một slot mà bài nộp KÉM đi.** Không exception, không log, validator vẫn
xanh — đúng loại lỗi im lặng cả dự án đang phòng. Và nó nằm trên đường chạy thật: bảng
hiện tại cấp **2 slot cho hạng 6–15**, đúng vùng quanh trung vị hạng 10.

Sửa thành rải theo **tâm ô** (`a + (2i+1)·span // (2m)`), thắng ở mọi `m` và mọi độ
rộng: `m=2` → `[20, 48]` (0.37 / 0.80 / 1.00). `m == 1` không đổi giá trị.

Đo đầu-cuối qua `_frames_of_shot`, shot 69 frame có keyframe thật ở frame 20:

| quota | trước | w=11 | sau | w=11 |
|---:|:---|---:|:---|---:|
| 3 | `[6, 20, 62]` | 0.42 | `[6, 20, 48]` | **0.49** |
| 4 | `[6, 20, 34, 62]` | 0.61 | `[15, 20, 34, 53]` | **0.64** |
| 6 | `[6, 7, 20, 34, 48, 62]` | 0.81 | `[11, 20, 23, 34, 45, 57]` | **0.95** |

Bản cũ ở quota 6 còn nhả `6` và `7` **dính nhau** — hai slot mua một cửa.

Thêm 2 test giữ bất biến, quan trọng là `test_spread_evenly_do_phu_don_dieu`: **thêm
một điểm không bao giờ làm độ phủ giảm**, đo trên `w ∈ {5,11,20,35}`, `m ∈ [1,8]`.
Bản cũ HỎNG test này. Bất biến đó đúng bất kể cửa sổ rộng bao nhiêu hay phân bố thế
nào — nó không phụ thuộc giả định, khác với các con số tuyệt đối ở trên.

> ⚠️ **Về độ tin cậy của các số trong §5.6:** đây là **mô phỏng**, không phải phép đo
> trên ground truth. `L=69` và `_frames_of_shot` là thật; `w` và giả thiết *"cửa sổ rơi
> đều trong shot"* là giả định. Chúng chứng minh được đúng một điều — `[6,62]` kém hơn
> `[20,48]` với mọi phân bố hợp lý, vì nó bỏ trống khúc giữa — chứ không định lượng
> được điểm thật tăng bao nhiêu.

---

## 6. D4.1 — Điều dev set KHÔNG đo được

Trước khi tin bảng §5.4, kiểm một giả thiết: **cửa sổ ground truth của dev set được
dựng từ đâu?**

| query | frame của keyframe | cửa sổ GT | lệch |
|:---|---:|:---|---:|
| Q1 | 5336 | 5286–5386 | **0** (đúng tâm) |
| Q2 | 13710 | 13660–13760 | **0** |
| K02 | 14812 | **14812**–14875 | = `frame_start` |
| K04 | 13083 | **13083**–13234 | = `frame_start` |
| K15 | 14127 | **14127**–14225 | = `frame_start` |

18/19 câu K* có keyframe đúng bằng `frame_start`; Q1–Q5 đúng tâm. **Cửa sổ GT được
sinh ra TỪ chính keyframe.**

**Hệ quả:** trên dev set này, hễ tìm đúng shot thì frame của keyframe *chắc chắn* nằm
trong cửa sổ — 19/19 câu, khớp đúng `R@100 = 0.826 = 19/23`. Đó là **hệ quả của cách
dựng dev set**, không phải kết quả đo.

Nên báo cáo tách đôi độ tin cậy của hai kết luận:

- ✅ Kết luận về **độ phủ** vẫn đứng vững — shot nhận 0 slot là trượt chắc, không phụ
  thuộc cửa sổ dựng kiểu gì.
- ❌ Kết luận về **chiều sâu** thì dev set **không nói được gì**.

Đây chính là lý do bảng **không** bị đổi (§5.5): nửa bằng chứng thì không đủ để thay
một bảng đang chạy. `slot_budget.py` ghi lại cả hai vế cùng điều kiện đổi tường minh,
để lần tune sau khỏi đo lại từ đầu.

**Việc cho Linh (§8 của `slot_tuning.md`):** dev set hiện tại không dùng tune được bất
cứ thứ gì bên trong shot. Cần **10 câu** có cửa sổ `[s,e]` xác định bằng mắt theo **sự
kiện**, không theo keyframe gần nhất, độ rộng cỡ BTC dùng (~11 frame KIS, <10 TRAKE).
10 câu như vậy giá trị hơn 30 câu dựng theo cách cũ.

---

## 7. Đo độ trễ

Lần đầu dự án có con số này (CLAUDE.md bất biến 10 yêu cầu, nhưng grep cả repo trước
đó chỉ có `search.py` CLI và `query_understanding.py` đo thời gian).

| | Đo được | Ngân sách |
|:---|---:|---:|
| 1 truy vấn KIS end-to-end, top_k=100, gom shot | **2.9 – 3.1 s** | 30 s |

Truyền sẵn `query_en` để **không** tính thời gian gọi LLM dịch — mục này đo đường ống
search (Milvus + 4 nhánh ES + RRF + gom shot). Nghĩa là con số này là **cận dưới**;
vượt 30s ở đây thì lúc thi chắc chắn vượt.

Bản thân preflight `--quick` chạy ~7s, bản đầy đủ ~12s.

---

## 8. Việc kèm theo — UI debug định tuyến sai dạng bài

Không nằm trong D6.1/D4.1, nhưng làm cùng phiên nên ghi lại.

`app/debug_ui.py::run_search()` luôn gọi `search(cfg["query"])` cho **cả ba dạng bài**
— tức ném nguyên câu multi-event của TRAKE vào search như một câu KIS đơn:

- vi phạm giới hạn 77 token của CLIP (CLAUDE.md bất biến 4)
- **không hề gọi** `parse_events()` / `trake_search()` — thứ đang chạy lúc thi
- UI hiện kết quả của một pipeline **khác hẳn** đường thi → nhãn chấm ở đây đo nhầm hệ
  thống, mà `eval.py` (E4.2) và `score_simulator` (D3.5) lại ăn theo bộ nhãn đó

Q&A cũng vậy: đường thật search trên phần **mô tả sự kiện đã tách khỏi câu hỏi**
(`qa_pipeline`), không phải nguyên văn câu hỏi.

Đây là **đúng con bug đã bị bắt một lần** ở `dev_set/tools/run_evaluation.py` (sửa
16/08 — comment còn ghi *"bản cũ KHÔNG hề gọi pipeline TRAKE thật"*), còn sót lại ở
file này.

**Sửa:** định tuyến theo `task_type` **y hệt `backend/api/main.py::post_search`** — copy
từng trường một, không tự chế. Ba thứ gắn thêm đều dựa trên contract có sẵn:

1. lọc theo `event_index` khớp ô *"Đang soạn khoảnh khắc thứ"* đã có sẵn ở sidebar
2. cảnh báo `is_interpolated` — frame nội suy, không có bằng chứng thật
3. khoá ô bật/tắt nhánh khi task ≠ KIS (pipeline riêng không nhận tham số `branches`)

**+7 test**, quan trọng nhất là bẫy: thay `search()` bằng hàm ghi lại lời gọi rồi
khẳng định **TRAKE và QA không gọi tới nó**. Bug quay lại lần thứ ba là test đỏ ngay.

> ⚠️ **Chưa nghiệm thu end-to-end.** Q&A/TRAKE trong UI bắt buộc gọi `llm()`, mà cái
> đó đang kẹt ở §9. Mới test được bằng monkeypatch.

### 8.2. `app/eval.py` im lặng khi lô nộp THIẾU dòng

Tìm ra khi rà lại toàn bộ code tooling (20/08). Dựng một lô chỉ có **3 dòng** thay vì
100:

```
Final = 1.0  |  n_rows = 3        ← báo cáo không hé một chữ
```

`r_at_k` lấy max của tập nhỏ hơn là **đúng công thức** — nộp ít nghĩa là ít cơ hội,
không phải bị trừ điểm. Nhưng hệ quả là một lô hỏng giữa chừng vẫn ra điểm đẹp, và đó
đúng là loại lệch mà **chính đầu file `eval.py` cảnh báo**: *"thước đo sai lệch về
phía CAO thì không ai đi soi"*.

Đường tới được: batch runner hỏng giữa chừng · allocator raise rồi bị ai đó bắt ·
chạy thử với `--limit`. Cả ba đều để lại file runs trông bình thường.

**Sửa:** `format_report()` thêm cảnh báo, cùng lối với 3 cảnh báo sẵn có
(`answer_unjudged`, `trake_n_inferred`, `skipped`) — **công thức không đổi**, chỉ nói
ra. +2 test, trong đó một test khẳng định **không** báo động giả khi đủ 100 dòng.

### 8.3. `app/evidence.py::split_id` cắt thừa `video_id` khi id có `#`

Nhánh lui của `split_id` (dùng khi id không khớp hệ nào) luôn `rsplit("_", 1)` **sau
khi** đã `split("#")`, tức cắt hai lần:

```
"L21_V001#s0006".split("#")[0]      → "L21_V001"
                .rsplit("_", 1)[0]  → "L21"        ← cắt thừa
```

`_BTC_ID` chỉ khớp `#k`, nên **mọi `shot_id`** (`#s0006`) rơi vào đây. Nhánh này sinh
ra để *"cố lấy video_id cho panel khỏi trống trơn"* — mà lại trả về một video **không
tồn tại**, mọi bảng tra ra rỗng, panel vẫn trống. Không crash, không log: đúng thứ nó
định tránh.

**Sửa:** tách hai phép cắt cho hai kiểu id, `#` thì lấy phần trước `#`, `_` thì bỏ hậu
tố số. +5 ca test tham số hoá.

### 8.4. Rà soát không ra lỗi — ghi lại để khỏi soi hai lần

Các ca đã thử và **đạt**, nên không sửa gì:

| Ca thử | Kết quả |
|:---|:---|
| CSV escape: answer chứa `,` `"` xuống dòng, khoảng trắng đầu/cuối | đúng cả 4, `csv.writer` khớp quy chuẩn BTC |
| `suggest_filename` với `../evil`, `a\nb`, chuỗi rỗng | chặn cả 3 |
| `frame_id` âm · KIS có `answer` · `frame_ids` rỗng | validator bắt hết |
| zip nén tay thiếu lớp `submission/` · file lạ sót lại · BOM | bắt hết |
| 1 / 2 / 3 / 31 shot ứng viên | luôn đủ 100 dòng |
| TRAKE chỉ 1 shot ứng viên | 100 dòng × 4 frame, tăng dần ngặt |
| 5 dòng đầu có phải 5 shot khác nhau | đúng |
| TRAKE nộp thừa frame so với N | chỉ tính N đầu, không thổi điểm |
| Unicode tiếng Việt NFC vs NFD trong answer | khớp cả hai dạng |
| answer 99 ký tự có dấu (198 byte) | không báo nhầm — đếm ký tự, không đếm byte |
| Q&A chấm lại frame sau khi đã phán answer | không xoá phán quyết cũ |
| `ts` lệch múi giờ (`+00:00` vs `+07:00`) | so mốc thời gian thật, không so chuỗi |
| dòng JSONL hỏng giữa file nhãn | báo rồi bỏ qua, không kéo sập cả file |
| `evidence_of` với id rỗng / `None` / rác | không sập |
| chéo `shots.parquet` ↔ `video_info.parquet` ↔ `frame_map` | 0 lệch trên 100.810 shot |
| TRAKE trên shot 12 / 69 / 1795 frame | 100 dòng, tăng dần ngặt, trải đều |
| dựng zip nộp thật cho cả 3 dạng bài | không BOM, không `\r`, đúng 100 dòng/file |

**Một câu hỏi thiết kế đã đo và quyết định KHÔNG đổi:** allocator xen kẽ theo *shot*,
không theo *video* — nên search dồn nhiều shot cùng một video vào top-5 thì các dòng
đầu cùng video, và video sai là mất cả R@1 lẫn R@5. Đo trên 23 câu KIS dev: 21 câu có
3–5 video khác nhau trong top-5; 2 câu dồn ≥4/5 vào một video (K15 `L29_V001`×5, K17
`L30_V028`×4) — và **cả hai đều dồn ĐÚNG video**. Không có bằng chứng nào ủng hộ việc
ép đa dạng theo video, nên giữ nguyên.

---

## 9. Phần KHÔNG đụng — báo cho chủ file

### 9.1. 🔴 `backend/llm/adapter.py` — Haiku không gọi được (chủ file: Thi)

```
model claude-haiku-4-5 → HTTP 400 invalid_request_error
"This model does not support the effort parameter."
request_id: req_011CeCggQWgpevvEzeKEuYCC
```

`_call_api()` luôn gửi `output_config={"effort": effort}`. `effort` chỉ có ở dòng Opus
4.5+ và dòng 5; **Haiku 4.5 và Sonnet 4.5 không nhận**. Nên đặt `LLM_BACKEND=api` +
Haiku thì **mọi** lệnh gọi `llm()` chết ngay lệnh đầu — dịch query, Q&A, TRAKE parse.

Ghi chú kèm: model ID đúng là `claude-haiku-4-5`, **không thêm hậu tố ngày**.

Đây là file của Thi nên tao không sửa. Nhưng nó đang chặn:
- chạy lại `run_evaluation --split tune` (Q&A tới giờ **chưa được chấm lần nào**)
- nghiệm thu Q&A/TRAKE trong UI debug (§8)

### 9.2. 🟡 `backend/api/main.py::/health` vẫn chưa deep check (W0.3, chủ file: Thạch)

Vẫn trả `{"status":"ok"}` cứng, không chạm Milvus/ES. Preflight vì thế **không dựa vào
nó** — ping thẳng ES/Milvus ở hai mục riêng, và mục `/health` ghi rõ nó chỉ chứng minh
FastAPI còn sống.

### 9.3. 🟡 TRAKE không đi qua `allocate()`

`run_evaluation.py` dựng 100 dòng TRAKE bằng `to_answers()` / `pad_answers()`, không
gọi `allocate()` lần nào → bảng chia slot **không tác động gì** tới điểm TRAKE.
`score_simulator` giờ báo đúng chuyện đó thay vì `bỏ qua dòng hỏng — KeyError:
'shot_id'` (thông điệp cũ khiến người đọc đi sửa nhầm chỗ).

---

## 10. Đối chiếu đặc tả

### D6.1 — BUILD_TASKS

| Yêu cầu | Trạng thái |
|:---|:---|
| "một lệnh tự kiểm toàn bộ checklist" | ✅ `python scripts/preflight_check.py` — 17 mục, 7 nhóm |
| "in ĐẠT/KHÔNG ĐẠT" | ✅ và thêm trạng thái thứ ba **BỎ QUA** kèm lý do (§2.2) |
| "exit code khác 0 nếu có mục fail" | ✅ có test chốt, cả ở chế độ `--json` |
| Kiểm frame_map trên mẫu MỚI (B2.3) | ⚠️ **chưa** — xem §11 |

### D4.1 — BUILD_TASKS

| Yêu cầu | Trạng thái |
|:---|:---|
| "Dùng `score_simulator`" | ✅ cả 3 chế độ: `shotrank` (mới), `replay`, `sweep` |
| "shot đúng thường xếp hạng bao nhiêu?" | ✅ trung vị 10, max 95 — §5.2 |
| "hay ở hạng 1 → dịch về SÂU · phân tán → dịch về RỘNG" | ✅ phân tán → chọn RỘNG |
| "Ghi bảng thử vào `reports/slot_tuning.md`" | ✅ |

---

## 11. Cách chạy · việc tiếp theo

```powershell
# D6.1
python scripts/preflight_check.py            # đầy đủ — cần Docker cho nhóm B/D/F
python scripts/preflight_check.py --quick    # chạy được ở mọi máy
python scripts/preflight_check.py --json     # cho E6.1 nhét vào log diễn tập

# D4.1
python -m app.score_simulator shotrank --candidates dev_set/results/run_20260818_1739/candidates.jsonl --gt dev_set/ground_truth/tune_gt.jsonl
python -m app.score_simulator replay   --candidates dev_set/results/run_20260818_1739/candidates.jsonl --gt dev_set/ground_truth/tune_gt.jsonl
python -m app.score_simulator sweep --scenarios 50 --shots 100 --ranks 1,3,5,6,8,10,16,20,29,31,39,40,73,80,95 --widths 5,11,20,50,101

# Test
python -m pytest tests dev_set/tests -q      # 499 passed
```

> ⚠️ `tests/test_api_search.py` và `tests/test_llm_adapter.py` **không collect được**
> trên máy này (thiếu `fastapi`, `google-genai`) — phải `--ignore` hai file đó. Đây
> chính là thứ nhóm A của preflight báo.

### File tạo / sửa

| File | Vai trò | Dòng |
|:---|:---|---:|
| `scripts/preflight_check.py` | Tạo mới — D6.1 | 656 |
| `tests/test_preflight.py` | Tạo mới — 26 test | 320 |
| `reports/slot_tuning.md` | Tạo mới — báo cáo D4.1 | 305 |
| `app/debug_ui.py` | Sửa — định tuyến theo dạng bài (§8) | +159 −13 |
| `app/score_simulator.py` | Sửa — thêm `shotrank`, sửa nhãn, sửa cảnh báo TRAKE | +136 −3 |
| `tests/test_debug_ui.py` | Sửa — +7 test định tuyến | +120 |
| **`backend/slot/allocator.py`** | **Sửa — `_spread_evenly` rải tâm ô (§5.6)** | **+35 −4** |
| **`tests/test_allocator.py`** | **Sửa — +2 test bất biến độ phủ** | **+43 −1** |
| `data/config/slot_budget.py` | Sửa — **giữ nguyên bảng**, ghi lại số đo | +26 −28 |
| `tests/test_score_simulator.py` | Sửa — bỏ nhãn gõ tay | +10 −4 |

Tổng: **510 test pass** (`pytest tests dev_set/tests -q`).

### Việc tiếp theo, xếp theo mức khẩn

1. 🔴 **Sửa `adapter.py` (Thi)** — §9.1. Chặn cả việc chạy lại dev set lẫn nghiệm thu
   UI. Còn 2 ngày.
2. 🔴 **Chạy lại `run_evaluation --split tune`** ngay sau đó. Q&A chưa từng được chấm,
   và ES vừa sống lại nên số liệu KIS cũng sẽ khác §5.4 — bảng slot có thể phải xem
   lại (`shotrank` chạy lại là biết ngay).
3. 🟡 **Thêm mục kiểm `frame_map` trên 20 mẫu MỚI** vào preflight (B2.3 yêu cầu, hiện
   preflight chỉ kiểm frame_map nạp được và có đủ 2 dạng khoá).
4. 🟡 `pip install fastapi uvicorn` nếu tối thi thao tác qua UI.
5. 🟡 **Dev set (Linh)** — cần ~10 câu có cửa sổ dựng **độc lập với keyframe**, rộng
   ~11 frame theo cỡ BTC. Không có nó thì không ai tune được gì bên trong shot (§6).
