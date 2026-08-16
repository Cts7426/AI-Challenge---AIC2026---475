# 📋 Báo Cáo Kỹ Thuật — Task W0.2 + D0.2: Export & Validator

> **Ngày:** 06/08/2026 · **rà lại 10/08/2026**
>
> **Người thực hiện:** Minh Hoàng
>
> **Phạm vi:** Tầng sinh bài nộp — `data/config/submit_format.py` + `backend/export/` + `tests/`
>
> Đây là khâu **cuối cùng** của cả hệ thống: mọi công sức của 5 người kết thúc ở một file
> nộp cho BTC. Tầng này không tìm kiếm gì, nhưng nếu nó sai thì mọi thứ phía trước thành
> vô nghĩa — và sai kiểu **im lặng**: file vẫn mở được, vẫn đúng số dòng, chỉ là 0 điểm.

---

## Mục lục
1. [Tổng quan bài toán](#1-tổng-quan-bài-toán)
2. [Luồng hoạt động tổng thể](#2-luồng-hoạt-động-tổng-thể)
3. [Chi tiết từng bước đã thực hiện](#3-chi-tiết-từng-bước-đã-thực-hiện)
4. [Chi tiết từng hàm](#4-chi-tiết-từng-hàm)
5. [Bảy luật của validator](#5-bảy-luật-của-validator)
6. [Kết quả chạy thực tế](#6-kết-quả-chạy-thực-tế)
7. [`Answer.__post_init__` — chuẩn hoá `frame_ids`](#7-answer__post_init__--chuẩn-hoá-frame_ids-ở-cửa-vào)
8. [Đo độ trễ](#8-đo-độ-trễ)
9. [Đối chiếu với yêu cầu trong tài liệu](#9-đối-chiếu-với-yêu-cầu-trong-tài-liệu)
10. [Việc còn treo](#10-việc-còn-treo) — [10.1 ai gọi tầng này](#101-ai-gọi-tầng-này-và-gọi-thế-nào) · [10.2 phần đang giả định](#102-phần-đang-chạy-trên-giả-định--sẽ-phải-sửa) · [10.3 code thử nghiệm](#103--code-chỉ-để-thử-nghiệm--bỏ-khi-vào-thi)
11. [Kết luận](#11-kết-luận)

---

## 1. Tổng quan bài toán

### 1.1. Đầu ra cuối cùng của cả hệ thống

Mọi công sức của 5 người — tải data, trích keyframe, encode CLIP, search, RRF — đều
kết thúc ở một chỗ: **một file nộp cho BTC**. Tầng này là khâu cuối. Nó không tìm
kiếm gì, nhưng nếu nó sai thì mọi thứ phía trước thành vô nghĩa.

Theo tài liệu BTC *"Thông tin vòng Sơ tuyển"*, định dạng một câu trả lời:

| Dạng bài    | Định dạng trả lời (rᵢ)                      |
| :------------| :--------------------------------------------|
| Textual KIS | `<video_id>, <frame_id>`                    |
| Q&A         | `<video_id>, <frame_id>, <answer>`          |
| TRAKE       | `<video_id>, <frame_id₁>, ..., <frame_idₙ>` |

Mỗi truy vấn nộp **tối đa 100 câu trả lời**, và điểm là
`trung bình(R@1, R@5, R@20, R@50, R@100)`.

### 1.2. Ba vấn đề phải giải

**Vấn đề 1 — Bug `frame_id` (W0.2).** Bản cũ của `submit_format.py` suy `frame_id`
bằng cách cắt hậu tố `keyframe_id`:

```python
"L03_V001_0007".rsplit("_", 1)[-1]   →  "0007"
```

`0007` là **số thứ tự file keyframe trong thư mục**, không phải **frame index trong
video** mà BTC chấm. Keyframe thứ 7 có thể nằm ở frame 175 của video.

Đây là **lỗi im lặng** — loại nguy hiểm nhất: file nộp nhìn hợp lệ, không crash,
không cảnh báo, nhưng lệch hệ thống mọi câu → **0 điểm toàn giải dù tìm đúng video
đúng khoảnh khắc**.

**Vấn đề 2 — Chưa có tầng kiểm (D0.2).** Không có gì chặn giữa pipeline và file nộp.
Một bài nộp thiếu dòng, trùng dòng, hoặc `frame_id` vượt độ dài video sẽ đi thẳng
tới BTC.

**Vấn đề 3 — Chưa biết định dạng thật.** BTC chưa công bố CSV hay JSON, có header
không, `frame_id` đếm từ 0 hay 1. Không thể chờ, cũng không thể đoán rồi viết cứng.

---

## 2. Luồng hoạt động tổng thể

```mermaid
flowchart TD
    A["Slot allocator (D3.1)<br/>đẻ ra 100 Answer đã xếp hạng"] --> B["QuerySubmission<br/>query_id · task_type · answers"]
    B --> C{"validate_all()<br/>TẦNG NGỮ NGHĨA"}
    C -->|"đọc video_info.parquet"| D[("video_info<br/>873 video")]
    C -->|"có Issue"| E["❌ RAISE — KHÔNG ghi file"]
    C -->|"sạch"| F["to_submission()"]
    F --> G["answer_to_cells()<br/>sắp ô theo mục 2.1 BTC"]
    G --> H{"validate_format()<br/>TẦNG ĐỊNH DẠNG"}
    H -->|"sai cột/kiểu"| E
    H -->|"đúng"| I["_csv_text()<br/>CSV không header"]
    I --> J["write_text<br/>utf-8, newline=''"]
    J --> K{"validate_file()"}
    K -->|"có BOM / sai mã"| L["⚠️ báo lỗi"]
    K -->|"sạch"| M["✅ submissions/query_id.csv"]

    style A fill:#e1f5fe
    style M fill:#c8e6c9
    style E fill:#ffcdd2
```

**Nguyên tắc chia tầng**:

| Tầng | File | Biết gì | KHÔNG biết gì |
|:---|:---|:---|:---|
| **Định dạng** | `data/config/submit_format.py` | tên cột, thứ tự ô, CSV/JSON | video có thật không, dài bao nhiêu |
| **Cơ chế** | `backend/export/exporter.py` | 100 dòng, `video_info`, frame hợp lệ | tên cột, dấu phẩy |

Chiều phụ thuộc **một hướng**: `export.py` → `submit_format.py`. Không có chiều ngược.

---

## 3. Chi tiết từng bước đã thực hiện

### Bước 1 — Gỡ bug `frame_id` tận gốc (W0.2)

Đã xoá hàm `_answer_value()`. Tầng định dạng giờ **không còn khả năng** tự tính ra
`frame_id` — nó chỉ ghi ra đúng con số nhận được. Trách nhiệm cấp `frame_idx` thật
chuyển lên slot allocator (D3.1), nơi đã có `frame_map`.

Khác biệt so với "vá": sau khi tầng format mất khả năng tính toán, bug này **không
thể tái diễn về mặt cấu trúc** — kể cả khi sau này có người viết lại module.

### Bước 2 — Đổi interface

```python
build_submission(query_id, task_type, answers: list[Answer])

@dataclass(frozen=True)
class Answer:
    video_id:    str
    frame_ids:   tuple[int, ...]     # TRAKE có N phần tử; KIS/Q&A có 1
    answer_text: str | None = None   # chỉ Q&A
    keyframe_id: str | None = None   # giữ để debug, KHÔNG dùng để tính
```

Ba quyết định đi kèm:
- **Bỏ hẳn trường `rank`.** Thứ hạng = thứ tự phần tử trong list. Giữ thêm `rank` là
  tạo nguồn sự thật thứ hai, sớm muộn cũng lệch với thứ tự thật.
- **Một hàm chung cho cả 3 dạng bài**, không tách 3 hàm.
- **`query_id` không xuất hiện trong file** — tài liệu BTC mục 2.1 không có cột đó.
  Nó chỉ dùng để đặt tên file, vì mỗi truy vấn là một file riêng.

### Bước 3 — Một bộ ghi duy nhất: CSV không header

> **Cập nhật 16/08 — BTC đã chốt.** Bản trước có ba format đăng ký sẵn qua
> `@register` (`csv_v0`, `csv_header_v0`, `json_v0`) vì chưa biết BTC muốn CSV hay
> JSON, có header hay không. Trang thi Codabench đã trả lời: **CSV, không header,
> dấu phẩy, UTF-8**. Hai format kia là đường chưa bao giờ chạy → đã xoá cùng cả
> registry. Một nhánh code không ai chạy là một nhánh không ai kiểm, và để lại ba
> format là để lại ba cách nộp sai.

`build_submission()` giờ gọi thẳng `_csv_text(rows)`. Tầng định dạng vẫn tách rời
hoàn toàn khỏi pipeline — BTC đổi ý thì sửa đúng file này, không chỗ nào khác.

⚠️ Cố ý **không** cho chọn format bằng tham số hàm. `BUILD_TASKS` chốt chữ ký
`build_submission(query_id, task_type, answers)` — đúng ba tham số. Lúc thi chỉ có một
định dạng đúng; biến nó thành tuỳ chọn là mở đường cho việc nộp nhầm format mà không ai
biết. Test `test_build_submission_dung_3_tham_so` canh cho chữ ký không lệch lại.

### Bước 4 — Validator chia hai tầng


| Tầng | Kiểm gì | Ở đâu | Vì sao ở đó |
|:---|:---|:---|:---|
| Định dạng | đúng số cột, đúng kiểu dữ liệu | cạnh `submit_format.py` | không cần dữ liệu ngoài |
| Ngữ nghĩa | 100 dòng, frame hợp lệ, trùng lặp, TRAKE tăng dần | `export.py` | cần đọc `video_info.parquet` |

### Bước 5 — Ghi file an toàn trên Windows

```python
path.write_text(noi_dung, encoding="utf-8", newline="")
```

- `encoding="utf-8"` chứ **không phải** `utf-8-sig` → không chèn 3 byte BOM
- `newline=""` → Windows không đổi `\n` thành `\r\n`

### Bước 6 — Dựng hạ tầng test 

Đã dựng `tests/` ở gốc repo và thêm `pytest` vào `backend/requirements.txt`.

---

## 4. Chi tiết từng hàm

### 4.1. `data/config/submit_format.py`

| Hàm / lớp | Mô tả |
|:---|:---|
| `Answer` | Một câu trả lời. `frozen=True` → hashable → luật kiểm trùng lặp chỉ cần `set()`. |
| `Answer.__post_init__()` | **Chốt an toàn ở cửa vào.** Chuẩn hoá `frame_ids` về `tuple[int]` bằng `operator.index()`. |
| `answer_to_cells()` | `Answer` → list ô, đúng thứ tự cột BTC mục 2.1. Không tính toán, chỉ sắp xếp. |
| `_csv_text()` | Các ô → CSV không header. Bộ ghi DUY NHẤT (BTC chốt 16/08). |
| `build_submission()` | **Cửa vào duy nhất.** Sắp ô → kiểm định dạng → serialize. |
| `suggest_filename()` | `<query_id>.csv`. `query_id` phải gõ ĐÚNG tên gói BTC phát (`query-1-kis`). |
| `validate_format()` | Validator tầng định dạng: số cột nhất quán, `frame_id` là số nguyên, `video_id` khác rỗng. |

### 4.2. `backend/export/exporter.py`

| Hàm / lớp | Mô tả |
|:---|:---|
| `QuerySubmission` | Bài nộp của MỘT truy vấn: `query_id`, `task_type`, `answers`. Thứ tự = thứ hạng. |
| `Issue` | Một lỗi. `rule` là slug ổn định để test bám vào, không bám câu chữ tiếng Việt. `__str__` in `query_id` và `position` **độc lập nhau** — Issue chỉ có `position` vẫn giữ được số thứ hạng. |
| `_video_frames()` | `video_id → n_frames`, đọc `video_info.parquet`. `@lru_cache` → đọc đĩa đúng 1 lần cho cả tiến trình. |
| `all_video_ids()` · `n_frames_of()` | Hai hàm tra cứu công khai, dùng chung cache trên. |
| `validate_submission()` | Kiểm ngữ nghĩa một truy vấn. Trả `list[Issue]`, **không raise**. |
| `validate_all()` | Kiểm nhiều truy vấn, kèm phát hiện `query_id` trùng. |
| `_check_duplicates()` | Hai câu trả lời trùng nội dung = tiêu hai slot mà chỉ mua một cơ hội. |
| `_check_shape()` | Số frame theo dạng bài · TRAKE tăng dần ngặt · Q&A có `answer`. |
| `_check_video_and_frames()` | `video_id` tồn tại · `frame_id ∈ [0, n_frames)`. |
| `validate_file()` | Kiểm file đã ghi: UTF-8 · không BOM · **không CRLF** · không rỗng. Báo kèm số dòng dính CRLF. |
| `format_issues()` | Gom lỗi thành báo cáo đọc được, nhóm theo luật. |
| `to_submission()` | Uỷ quyền toàn bộ định dạng cho `submit_format`. |
| `write_submissions()` | Ghi **mỗi truy vấn một file**. Mặc định validate trước, sai thì không ghi. |
| `_demo_subs()` · `main()` | CLI `--demo`: lấy shot thật từ `shots.parquet` → **`backend.slot.allocate()`** cấp frame → tự kiểm. Xem mục 6.4. |

**Vì sao validator trả `list[Issue]` thay vì raise ngay lỗi đầu tiên:**

D6.1 (preflight check) cần in **toàn bộ** lỗi một lượt. Raise từng cái nghĩa là sửa
một lỗi → chạy lại → lòi lỗi tiếp → sửa → chạy lại. Trước hạn nộp thì đó là công
thức trượt hạn.

---

## 5. Chín luật của validator


| # | Luật | Tầng | Slug `Issue` |
|:---:|:---|:---|:---|
| 1 | Đúng 100 dòng mỗi truy vấn | ngữ nghĩa | `answer_count` |
| 2 | `video_id` tồn tại | ngữ nghĩa | `video_unknown` |
| 3 | `frame_id ∈ [0, n_frames)` | ngữ nghĩa | `frame_out_of_range` |
| 4 | Không dòng trùng lặp hoàn toàn | ngữ nghĩa | `duplicate_answer` |
| 5 | TRAKE đúng N frame, **tăng dần ngặt** | ngữ nghĩa | `trake_not_increasing`, `trake_n_inconsistent`, `trake_n_mismatch` |
| 6 | Q&A có `answer` không rỗng | ngữ nghĩa | `answer_empty` |
| 7 | Q&A `answer` **≤ 100 ký tự** *(mới 16/08)* | ngữ nghĩa | `answer_too_long` |
| 8 | File UTF-8, **không BOM** | file | `bom`, `not_utf8`, `cr_don_le` |
| 9 | Zip có lớp thư mục `submission/` *(mới 16/08)* | zip | `zip_no_submission_dir`, `zip_corrupt`, `zip_empty`, `zip_missing` |

Kèm bốn luật phụ phát sinh khi cài đặt: `task_type` hợp lệ · `query_id` không trùng ·
KIS/Q&A đúng 1 frame · dạng không phải Q&A thì không được có `answer`.

> [!NOTE]
> **Quyết định thiết kế:** gặp `video_id` không có trong `video_info.parquet` thì
> **báo lỗi**, tuyệt đối không lặng lẽ bỏ qua. Bỏ qua = cho trôi dòng sai mà không ai
> biết — đúng loại lỗi im lặng mà cả dự án đang phòng.

### Luật 7 — đếm KÝ TỰ, không đếm byte

BTC: *"Độ dài tối đa: 100 ký tự"*. `"ố" * 100` là 100 ký tự nhưng **200 byte** UTF-8 —
đếm byte thì mọi câu trả lời tiếng Việt có dấu đều bị báo nhầm. Con số này **không**
liên quan tới `MAX_ANSWER_LEN = 500` của `backend/common/answer_match.py` (đó là chặn
đầu vào cho `difflib`, thuộc tầng so khớp).

### Luật 8 — CRLF KHÔNG còn là lỗi *(sửa 16/08)*

Bản trước bắt CRLF là `Issue`. Trang BTC ghi rõ *"CRLF **or** LF line endings"* — cả
hai đều nhận, nên luật cũ là **báo động giả**. Preflight D6.1 chạy ngay trước giờ nộp
mà báo đỏ một file hợp lệ thì người vận hành đi sửa thứ không hỏng, đúng lúc không còn
thời gian.

Còn giữ `\r` **đơn lẻ** (không kèm `\n`) — newline kiểu Mac cổ, không nằm trong hai
kiểu BTC nhận, và không lộ ra khi mở file bằng mắt:

```
b"L21_V001,100\r\n..."   →  []           (CRLF: BTC nhận, im lặng)
b"L21_V001,100\n..."     →  []           (LF: im lặng)
b"L21_V001,100\r..."     →  cr_don_le: có 2 ký tự \r đơn lẻ
b"\xef\xbb\xbfL21_..."   →  bom          (vẫn là lỗi — làm hỏng ô đầu tiên)
```

### Luật 9 — vì sao phải đọc lại file zip vừa ghi

Kiểm cái mình vừa làm thì gần như vô nghĩa. Giá trị nằm ở chỗ `validate_zip()` chạy
được trên file **người khác nén tay** — đúng ca hay hỏng nhất: trên Windows, chọn 3
file CSV rồi *Send to → Compressed folder* tạo zip chứa **thẳng 3 file, không có lớp
`submission/`**. Mở ra vẫn thấy đủ tên đúng nội dung đúng, và BTC từ chối. Phải chọn
đúng **thư mục** rồi mới nén. Mỗi gói chỉ được nộp **3 lần**, nên một lần nộp hỏng vì
thao tác nén là mất 1/3 cơ hội.

---

## 6. Kết quả chạy thực tế

### 6.1. Bộ test

```
66 test của D0.2 — 100% xanh
  tests/test_validator.py : 34 test
  tests/test_export.py    : 32 test

(cả repo 106 test: + 40 test của D3.1, xem reports/D31_TECHNICAL_REPORT.md.
 3 test đỏ nằm ở D3.1, do backend/indexing/frame_map.py gãy — mục 10.1)
```

Mỗi luật có **1 ca đúng + ít nhất 1 ca sai**. Ca sai mới là thứ chứng minh validator
hoạt động — một hàm luôn trả `[]` cũng pass mọi ca đúng.

**Không dùng mock, không bịa số.** Toàn bộ dữ liệu test lấy từ parquet của Data Factory:

| Thành phần | Nguồn |
|:---|:---|
| `video_id`, `n_frames` | `video_info.parquet` — 873 video |
| `frame_id` | cột `frame_idx` (đã bù offset) của `frame_map.parquet` — 177.321 keyframe |
| TRAKE N frame | N keyframe **liên tiếp** thật, vốn đã tăng dần ngặt |
| **Thứ tự** 100 câu trả lời | `backend.slot.allocate()` của D3.1 — xem mục 6.4 |

### 6.2. Hai test quét toàn bộ dữ liệu thật

| Test | Phạm vi |
|:---|:---|
| `test_moi_keyframe_that_deu_qua_duoc_luat_bien` | **177.321 keyframe / 873 video** — không keyframe nào được vượt `n_frames` của video nó |
| `test_validator_khong_bao_nham_tren_20_video_that` | Dựng bài nộp thật từ 20 video, chạy đúng đường code lúc thi → validator phải im lặng hết |

Test đầu bắt được nếu Data Factory giao ra dữ liệu lệch. Test sau bắt được nếu
validator báo nhầm trên dữ liệu đúng — cả hai đều phải biết trước ngày nộp.

### 6.3. Kiểm chứng bằng cách phá code

Test chỉ đáng tin nếu nó **đỏ khi code sai**. Đã thử phá:

| Phá gì | Kết quả |
|:---|:---|
| Đổi `a >= b` thành `a > b` (bỏ "tăng dần **ngặt**") | 1 test đỏ |
| Tắt luật đếm 100 dòng (`if False:`) | 3 test đỏ |
| Phục hồi | 66 xanh |

Đổi **một ký tự** `=` mà test bắt được ngay.

### 6.4. File nộp sinh ra — cũng là phép thử đầu-cuối với D3.1

`--demo` không tự tính frame. Nó lấy shot thật từ `shots.parquet`, đưa qua
`backend.slot.allocate()` (D3.1), rồi mới kiểm và ghi. Nghĩa là mỗi lần chạy demo là
một lần **chạy thật cả hai tầng nối nhau**: allocator đẻ ra thứ mà chính validator của
mình từ chối thì lộ ngay tại đây, không phải đợi tới ngày nộp.

```
$ python -m backend.export --demo

== Kiểm ngữ nghĩa ==
HỢP LỆ — không phát hiện lỗi nào.

== Đã ghi 3 file vào submissions\demo_csv_v0 ==
   kis_001.csv    (1273 byte)
   qa_001.csv     (1473 byte)
   trake_001.csv  (2404 byte)
== Kiểm file ==
HỢP LỆ — không phát hiện lỗi nào.
```

Nội dung — khớp đúng mục 2.1 của BTC:

```
kis_001.csv     L21_V001,34        ← shot hạng 1
                L21_V001,350       ← shot hạng 2   (xen kẽ, không gom theo shot)
                L21_V002,46        ← shot hạng 4
qa_001.csv      L21_V001,34,5
trake_001.csv   L21_V001,34,35,350,388
```

Kiểm byte: `BOM: False` · `CRLF: False`.

> [!NOTE]
> Import `backend.slot` đặt **trong hàm** `_demo_subs()`, không ở đầu file: `allocator.py`
> import ngược lại `backend.export` (`REPO_ROOT`, `n_frames_of`), để ở đầu file là vòng
> import.

### 6.5. Validator bắt lỗi thật

Cố tình phá 4 chỗ trong dữ liệu:

```
[video_unknown]        video_id 'L99_V999' không có trong video_info.parquet
[frame_out_of_range]   frame_id -5 nằm ngoài [0, 37849) của video L21_V001
[trake_not_increasing] frame phải tăng dần ngặt, đang là (900, 100, 200, 300)
[answer_count]         có 99 câu trả lời, phải đúng 100
```

Bắt đủ 4, **báo một lượt** chứ không dừng ở lỗi đầu tiên.

---

## 7. `Answer.__post_init__` — chuẩn hoá `frame_ids` ở cửa vào

`Answer` nhận `frame_ids` từ slot allocator, mà allocator tính frame từ `shots.parquet`
bằng pandas. Hai kiểu dữ liệu đi vào đây mà nếu không chuẩn hoá sẽ hỏng:

| Đầu vào | Không chuẩn hoá thì |
|:---|:---|
| `[100, 103]` — `BUILD_TASKS` ghi kiểu là `list[int]` | `TypeError: unhashable type: 'list'` khi validator so trùng. Crash bẩn, vỡ đúng bất biến "không ném exception vì dữ liệu sai" |
| `numpy.int64(100)` | `isinstance(np.int64(100), int)` là `False` → báo "frame_id phải là số nguyên, đang là int64". Báo lỗi sai trên dữ liệu đúng |

```python
def __post_init__(self) -> None:
    chuan = tuple(operator.index(f) for f in self.frame_ids)
    object.__setattr__(self, "frame_ids", chuan)
```

| Đầu vào | Kết quả | |
|:---|:---|:---|
| `[100, 103]` (list) | `(100, 103)` | ✅ nhận |
| `numpy.int64(100)` | `100` (int thuần) | ✅ nhận |
| `100.7` (float) | `TypeError` | ✅ **từ chối** |

> [!WARNING]
> Dùng `operator.index()` chứ **không** dùng `int()`. `int(100.7)` sẽ âm thầm ra `100`
> — đó chính là "tầng format tự tính", điều W0.2 cấm tuyệt đối. `operator.index()` chỉ
> nhận thứ chuyển sang số nguyên **không mất mát**.

Ba test chốt: `test_nhan_frame_ids_dang_list`, `test_nhan_numpy_int`,
`test_tu_choi_float_khong_lam_tron_ho`.

---

## 8. Đo độ trễ

| Thao tác | Thời gian |
|:---|---:|
| Nạp `video_info.parquet` (1 lần cho cả tiến trình) | 0.95 – 1.9 s |
| Validate + sinh file, 1 truy vấn 100 dòng | **0.20 ms** |
| Validate + ghi đĩa, 3 truy vấn | 7 – 9 ms |

Con số nạp parquet dao động theo cache của hệ điều hành (đo 3 lần liên tiếp: 1286 /
1123 / 951 ms). Nó là chi phí **một lần**, trả lúc khởi động chứ không lúc bấm nộp —
`@lru_cache(maxsize=1)` khiến mọi lần gọi sau đọc thẳng từ RAM:

```
cache: misses=1, hits=980 · cùng một object trong RAM
```

Việc thực sự chạy mỗi lần nộp là **0.20 ms**. Tầng này không phải chỗ nghẽn.

---

## 9. Đối chiếu với yêu cầu trong tài liệu

### 9.1. `BUILD_TASKS.md` — D0.2

| Yêu cầu | |
|:---|:---:|
| `build_submission(query_id, task_type, answers: list[Answer])` | ✅ |
| `Answer` = `video_id`, `frame_ids`, `answer_text`, `keyframe_id` | ✅ |
| Thứ hạng = thứ tự phần tử, không truyền `rank` | ✅ |
| Một hàm chung cho cả 3 dạng bài | ✅ |
| Validator *định dạng* cạnh `submit_format.py` | ✅ |
| Validator *ngữ nghĩa* trong `export.py` | ✅ |
| 9 luật validator | ✅ |
| Format tách rời hoàn toàn khỏi pipeline | ✅ Trọn trong `submit_format.py` |

### 9.2. `BUILD_TASKS.md` — W0.2

| Yêu cầu | |
|:---|:---:|
| Xoá **hẳn** mọi phép tính khỏi tầng format | ✅ |
| Thiếu `frame_idx` → raise rõ ràng, tuyệt đối không đoán | ✅ |
| Trách nhiệm cấp `frame_idx` chuyển lên D3.1 | ✅ |

### 9.3. `CLAUDE.md`

| Yêu cầu | |
|:---|:---:|
| Bất biến 5 — `frame_id` là frame index trong video | ✅ |
| Comment "vì sao chọn cách này", tiếng Việt | ✅ |
| Thứ chưa chốt → để `data/config/` kèm `# TODO: BTC` | ✅ |
| Nợ kỹ thuật #5 — thêm `tests/` | ✅ |

### 9.4. Ba chỗ lệch so với chữ trong tài liệu

| Chỗ lệch | Lý do |
|:---|:---|
| `to_submission(rows, fmt)` → `to_submission(sub: QuerySubmission)` | Tài liệu BTC bắt mỗi truy vấn một file → hàm phải biết `query_id` và `task_type`. Bỏ `fmt` để `build_submission` giữ đúng 3 tham số như `BUILD_TASKS` chốt |
| `frame_ids: list[int]` → lưu thành `tuple` | `list` không hashable. Vẫn **nhận** list ở cửa vào (mục 7.3) |
| `keyframe_id: str` → `str \| None` | `BUILD_TASKS` D3.1 nói frame phát ra không cần là keyframe đã index → phần lớn dòng sẽ không có |

---

## 10. Việc còn treo

Task này làm sớm hơn tiến độ chung nên một số chỗ chạy trên giả định. Mục 10.2 nói rõ
chỗ nào có thể lệch khi BTC công bố định dạng thật.

| # | Việc | Chủ | Ảnh hưởng |
|:---:|:---|:---|:---|
| 1 | ~~`backend/indexing/frame_map.py` import module đã bị xoá khỏi git~~ | **Công Lý** | ✅ **Đã thông 13/08** — toàn bộ test xanh trở lại, xem `D31_TECHNICAL_REPORT.md` §10.5 |
| 2 | ~~Định dạng nộp thật của BTC~~ | **Linh** → BTC | ✅ **Đã có 16/08** từ trang thi Codabench — đối chiếu ở mục 10.2. Còn treo mỗi `frame_id` 0/1-based |
| 3 | Ai gọi tầng này thì phải đưa `list[QuerySubmission]`, không phải `dict` | — | 🟡 **đã xảy ra một lần** — `run_evaluation.py` gọi `write_submissions(dict)` và nổ ở dòng cuối cùng của cả lần chạy. Sửa 16/08, xem `D31_TECHNICAL_REPORT.md` §10.1 |

### 10.1. Ai gọi tầng này, và gọi thế nào

Tầng nộp bài có **hai đường vào**, cả hai đều đi qua `write_submissions()` chứ không gọi
thẳng `build_submission()` — nhờ vậy 7 luật validator và quy tắc "mỗi truy vấn một file"
chỉ cài đặt ở một chỗ.

| Đường | Ai gọi | Số dòng | Ai cấp `frame_idx` |
|:---|:---|:---:|:---|
| **Nộp thật** | orchestrator → slot allocator (D3.1) | ép đủ 100 | `allocate()` tra `frame_map` |
| **Thử tay** | `POST /submit` ← UI (`backend/api/main.py`) | vài dòng đã đánh dấu | endpoint tự tra `frame_map` rồi dựng `Answer` |

Điểm chung bắt buộc của cả hai: **tầng gọi tra bảng, tầng format thì không.** Đó là
thiết kế chống tái diễn bug W0.2 — `build_submission()` không nhận `frame_map` và sẽ
không bao giờ nhận, nên không đường nào có thể lén đưa việc suy `frame_id` xuống lại.

Đường thử tay được phép nộp **ít hơn 100 dòng** (`expect_answers=len(answers)`): người
vận hành chỉ đánh dấu vài frame để xem file trông ra sao. Đường nộp thật mới ép đủ 100 —
luật đó thuộc về allocator, không thuộc về tầng ghi file.

> [!WARNING]
> Ghi file trên Windows phải có `newline=""`, nếu không Python dịch `\n` → `\r\n`:
> ```
> write_text(..., encoding="utf-8")             → b'a\r\nb\r\n'
> write_text(..., encoding="utf-8", newline="") → b'a\nb\n'
> ```
> Đây là **lỗi im lặng** — file vẫn mở được bằng mắt. `write_submissions()` xử lý sẵn,
> và `validate_file()` bắt lại lần nữa (luật 7) cho những file do đường khác ghi ra.

### 10.2. Đối chiếu với trang thi Codabench của BTC *(đọc 16/08)*

Bảng "đang chạy trên giả định" của bản trước có 6 dòng. BTC đã trả lời 5, còn 1.

| Từng giả định | BTC nói gì | Kết quả |
|:---|:---|:---|
| CSV hay JSON, có header không | CSV, **không header**, dấu phẩy, UTF-8 | ✅ đoán đúng — đã xoá 2 format thừa |
| `video_id` có đuôi `.mp4` không | `L00_V000` — **không đuôi** | ✅ đoán đúng — không sửa gì |
| Quy ước đặt tên file | = tên gói BTC phát, đổi `.txt` → `.csv` | ✅ `suggest_filename()` đã đúng sẵn |
| Tối đa 100 dòng | đúng 100 | ✅ |
| Có gộp zip không | **có** — thư mục `submission/` trong `.zip` | 🔴 thiếu hẳn → đã bổ sung `write_submission_zip()` |
| `frame_id` đếm từ 0 hay 1 | *chưa trả lời bằng văn bản* | 🟠 **còn treo** — xem dưới |

Thêm hai luật mới BTC nêu mà bản trước chưa có: **answer ≤ 100 ký tự** và
**CRLF được chấp nhận** (luật 7, 8 ở mục 5).

#### 🟠 Còn treo — `frame_id` đếm từ 0 hay 1

Trang chính thức chỉ ghi *"Frame ID sẽ được so sánh dưới dạng số nguyên"*, **không
nói cơ số, không nói dung sai**. Ghi chú buổi họp nói BTC đếm từ 1 nhưng châm chước
lệch 1 frame.

Tầng này **chưa sửa** — vẫn ghi nguyên con số 0-based tầng trên đưa xuống
(`data/config/frame_convention.md`). Ước lượng thiệt hại nếu BTC thật sự 1-based và
KHÔNG châm chước: lệch 1 làm mất frame đầu cửa sổ nhưng lại được frame ngay sau cửa
sổ, nên xấp xỉ triệt tiêu — tỉ lệ chạm biên ≈ `1/w` với `w` là độ rộng cửa sổ.

- KIS / Q&A (cửa sổ rộng) → **~1%, coi như không đáng kể**
- TRAKE (cửa sổ **dưới 10 frame**, `docs/contest.md`) → **10–20% mỗi khoảnh khắc**

Cách sửa nếu chốt: thêm hằng `FRAME_ID_BASE = 1`, áp trong `answer_to_cells()`, nới
luật 3 thành `[1, n_frames]`. Nội bộ giữ nguyên 0-based. **Chờ Thạch duyệt** (quyền
phủ quyết schema) và chờ BTC xác nhận dung sai có văn bản.

---

### 10.3. 🧪 Code chỉ để thử nghiệm — bỏ khi vào thi

> Liệt kê để sau này không ai tưởng nhầm là code sản xuất.

| # | Chỗ | Là gì | Xử lý |
|:---:|:---|:---|:---|
| 1 | `_demo_subs()` + cờ `--demo` | Dựng shot ứng viên **giả lập** từ `shots.parquet` rồi đưa qua allocator thật | **Giữ tới G2** — chạy được cả hai tầng mà không cần Milvus/ES. Không nằm trong đường chạy lúc thi |
| 2 | `write_submissions(..., validate=False)` | Đường thoát ghi dữ liệu hỏng ra soi | ⚠️ **TUYỆT ĐỐI không dùng ngày nộp.** Mặc định `True`; đặt `False` là sinh ra file trông hợp lệ mà sai |
| 3 | ~~`csv_header_v0` · `json_v0`~~ | — | ✅ **Đã xoá 16/08** cùng cả registry `FORMATS`, sau khi BTC chốt CSV không header |
| 4 | `tests/conftest.py` — `build_sub()`, `frames_of()`, `replace_answer()`, `cat_bot()` | Dựng dữ liệu test | Nằm trong `tests/`, không bao giờ chạy lúc thi |

**Điểm 2 là chỗ dễ gây tai nạn nhất** — nó tạo ra file nộp *trông* hợp lệ mà sai.

---

---

## 11. Kết luận

| Hạng mục | Trạng thái |
|:---|:---|
| Bug `frame_id` (W0.2) | ✅ Gỡ tận gốc, không phải vá |
| Interface `build_submission` theo chốt của Thạch | ✅ |
| 9 luật validator | ✅ Đủ, chia đúng ba tầng (định dạng · ngữ nghĩa · file+zip) |
| Định dạng khớp trang thi BTC | ✅ CSV không header, `video_id` không đuôi — đối chiếu 16/08, mục 10.2 |
| **Đóng gói `.zip` có thư mục `submission/`** | ✅ `write_submission_zip()` + `validate_zip()` — mục 5 luật 9 |
| File nộp đúng mục 2.1 của BTC | ✅ Đã sinh và kiểm byte |
| UTF-8 không BOM | ✅ Luật nằm trong `validate_file()`, không chỉ nằm trong test — mục 5 |
| `frame_id` 0-based hay 1-based | 🟠 **Còn treo** — mục 10.2, chờ Thạch + BTC |
| Nối với slot allocator (D3.1) | ✅ `--demo` chạy thật cả hai tầng nối nhau — mục 6.4 |
| Hạ tầng test cho repo | ✅ 66 test (2 test quét toàn bộ 177.321 keyframe thật), kiểm chứng bằng cách phá code |
| Hai bug tiềm ẩn của D3.1 | ✅ Chặn trước khi nổ — mục 7 |

### Danh sách file được tạo / sửa

| File | Vai trò | Dòng |
|:---|:---|---:|
| `data/config/submit_format.py` | **Tầng định dạng** — viết lại toàn bộ | 235 |
| `backend/export/exporter.py` | **Tầng cơ chế** — tạo mới | 495 |
| `backend/export/__init__.py` · `__main__.py` | Đóng gói thành package, theo kiểu `backend/llm/` | 34 · 8 |
| `tests/conftest.py` | Dựng dữ liệu test từ `video_info` + `frame_map` thật | 178 |
| `tests/test_validator.py` | 34 test cho validator | 271 |
| `tests/test_export.py` | 32 test cho định dạng + ghi file | 296 |
| `backend/requirements.txt` | Thêm `pandas`, `pyarrow`, `pytest` | +6 |

### Sửa 16/08 — sau khi đọc trang thi Codabench của BTC

| File | Thay đổi |
|:---|:---|
| `data/config/submit_format.py` | Xoá registry `FORMATS` + `csv_header_v0` + `json_v0` + `_header_for()` · xoá 2 khối `TODO: BTC` đã có đáp án · thêm `ANSWER_MAX_CHARS = 100`, `SUBMIT_EXT` |
| `backend/export/exporter.py` | **Thêm `write_submission_zip()` + `validate_zip()`** · thêm luật `answer_too_long` · CRLF hết là lỗi, giữ `cr_don_le` · CLI `--demo` giờ xuất ra `.zip` |
| `backend/export/__init__.py` | Xuất thêm `write_submission_zip`, `validate_zip`, `SUBMISSION_DIR_NAME` |
| `tests/test_export.py` | Bỏ 4 test của 2 format đã xoá · thêm 15 test (zip · 100 ký tự · CRLF · tên file BTC) |

Bộ test: **425 → 437 pass**.

**Đã xoá:** `backend/frame_lookup.py`, `backend/validator.py` — gộp vào `export.py`
sau khi rà thấy 3/6 hàm không có nơi nào gọi.

### Cách chạy / kiểm

```powershell
python -m pytest tests/test_export.py tests/test_validator.py -q   # 66 passed (D0.2)
python -m pytest tests dev_set/tests -q                            # 409 passed (16/08)
python -m backend.export --demo              # sinh file nộp mẫu qua allocator thật
```

> Bản 10/08 ghi *"103 passed, 3 failed — 3 đỏ ở `backend/indexing/frame_map.py`"*. Đã
> thông. Lưu ý `python -m pytest -q` trần vẫn **gãy lúc thu thập** vì
> `preprocessing/test_opencv_parity.py` cần gói `yaml` chưa cài — không liên quan tầng
> nộp bài, nhưng nó chặn cả lượt chạy nên nhớ chỉ định thư mục như trên.

### Task tiếp theo

**D3.1 — Slot allocator**: xem `reports/D31_TECHNICAL_REPORT.md`. Đó là nơi chịu trách
nhiệm cấp `frame_idx` thật mà tầng format đã từ chối tự tính.

**D6.1 — Preflight check** (19→20/08) là chỗ tiêu thụ chính của tầng này: nó gọi
`validate_all()` + `validate_file()` lên toàn bộ bài nộp cuối cùng và in một bảng
ĐẠT/KHÔNG ĐẠT. Đó cũng là lý do validator trả `list[Issue]` thay vì raise.

Tiếp theo: **D4.1 — chỉnh bảng `SLOT_BUDGET` theo dev set** (17→19/08).
