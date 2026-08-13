# 📋 Báo Cáo Kỹ Thuật — Task D2.1: UI Debug

> **Ngày:** 10/08/2026 · **Hạn:** 13/08/2026
>
> **Người thực hiện:** Minh Hoàng
>
> **Phạm vi:** `app/` + `data/config/debug_ui.py` + `tests/`
>
> **Trạng thái: ĐÃ CHẠY ĐƯỢC ĐẦU-CUỐI ở chế độ `offline`.** Gõ truy vấn → tìm →
> chấm nhãn → nhãn ra file. Chế độ `live` mới kiểm được hợp đồng tĩnh, **chưa chạy
> thật lần nào** (§9.1b). Ba thứ trong đặc tả chưa có nguồn dữ liệu: ảnh keyframe,
> `objects`, `caption` mức frame (§9.0).

---

## Mục lục
1. [UI này giải quyết vấn đề gì](#1-ui-này-giải-quyết-vấn-đề-gì)
2. [Khảo sát trước khi làm — 5 thứ đã đo](#2-khảo-sát-trước-khi-làm--5-thứ-đã-đo)
3. [⚠️ Hợp đồng dữ liệu: HAI kiểu `kf_id`](#3-️-hợp-đồng-dữ-liệu-hai-kiểu-kf_id)
4. [Thứ đang CHẶN và thứ chỉ làm giảm chất lượng](#4-thứ-đang-chặn-và-thứ-chỉ-làm-giảm-chất-lượng)
5. [Quyết định thiết kế đã chốt](#5-quyết-định-thiết-kế-đã-chốt)
6. [Chi tiết từng hàm](#6-chi-tiết-từng-hàm)
7. [Kết quả chạy thực tế](#7-kết-quả-chạy-thực-tế)
8. [Kết quả chạy đầu-cuối](#8-kết-quả-chạy-đầu-cuối)
9. [Rà soát lại toàn bộ (13/08)](#9-rà-soát-lại-toàn-bộ-1308) — [đối chiếu đặc tả](#90-đối-chiếu-với-đặc-tả-d21-trong-build_tasksmd)
10. [Dùng chế độ nào, cần gì để chạy](#10-dùng-chế-độ-nào-cần-gì-để-chạy)

---

## 1. UI này giải quyết vấn đề gì

Hiện tại gõ một query thì nhận về danh sách kết quả và **không biết gì thêm**. Frame
hạng 3 lên cao nhờ CLIP thấy giống ảnh, nhờ trùng một chữ trong phụ đề, hay nhờ cái tên
trong `description` của video? Không nhìn được thì tuần sau sửa search thành đoán mò.

UI này trả lời ba câu:

| Câu hỏi | Nhìn vào đâu |
|:---|:---|
| Frame này lên hạng nhờ nguồn nào? | thứ hạng từng nhánh (`ranks` từ A2.2) |
| Frame này thật sự chứa gì? | OCR · ASR · `doc_text` (objects: xem §9.0) |
| Kết quả này đúng hay sai? | nút chấm nhãn → `dev_set/labels.<người>.jsonl` |

Câu thứ ba mới là lý do tồn tại chính. File nhãn sinh ra ở đây là **đề thi tự chấm** của
nhóm, và là đầu vào bắt buộc của hai task sau:

- **E4.2** (`eval.py`) — tính `Final Score` và tách R@1/R@5/R@20/R@50/R@100.
- **D3.5** (mô phỏng chấm điểm) — thử phân bổ slot khác mà không chạy lại pipeline.

Không có nhãn thì hai task đó không có gì để chấm.

---

## 2. Khảo sát trước khi làm — 5 thứ đã đo

Đo trên máy thật, 10/08, trước khi viết dòng code nào.

| # | Câu hỏi | Kết quả |
|:--:|:---|:---|
| 1 | Streamlit chạy được trên Python 3.14 không? | ✅ **đã cài sẵn, bản 1.59.1** — không phải rủi ro wheel như paddle/whisper |
| 2 | `search()` có dính module `frame_map` đang gãy không? | ✅ **không** — `grep frame_map backend/retrieval/search.py` rỗng |
| 3 | Bằng chứng (OCR/ASR/`doc_text`) có sẵn trên đĩa chưa? | ✅ có đủ, ví dụ `L21_V001`: 1.311 `doc_text` (0 dòng rỗng) · 306 OCR · 53 đoạn ASR |
| 4 | Ảnh keyframe và video gốc? | ❌ **không có trên máy** — `keyframes.path` và `video_info.path` chết 873/873 |
| 5 | Nạp bằng chứng theo video có đủ nhanh không? | ✅ `docs_bm25` 512 ms · `ocr` 89 ms cho 1 video (lần đầu, sau đó cache) |

Hệ quả của #4: UI phải **hữu ích khi không có ảnh**. Toàn bộ chữ nghĩa (OCR, ASR,
metadata, biên shot, `frame_idx`) đã nằm trong parquet — chỉ thiếu phần nhìn.

---

## 3. ⚠️ Hợp đồng dữ liệu: HAI kiểu `kf_id`

**Đây là phát hiện quan trọng nhất của đợt khảo sát, và nó không có trong kế hoạch ban đầu.**

Trong `data/derived/` đang tồn tại **hai cách đặt tên keyframe**, và chúng KHÔNG thay
thế cho nhau được:

| Kiểu | Ví dụ | Nghĩa | Bảng nào dùng |
|:---|:---|:---|:---|
| **BTC** | `L21_V001#k0001` | keyframe thứ 1 BTC cấp | `frame_map` · `ocr` · **Milvus** |
| **Tự trích** | `L21_V001_0000090` | keyframe tự cắt 1fps, hậu tố là `frame_idx` | `keyframes` · `docs_bm25` |

`search()` lấy id từ Milvus nên **luôn trả kiểu BTC**. Đo mức độ khớp:

```
clip_kf_id (kiểu BTC)  có trong ocr.kf_id        : 224.284 / 371.702
kf_id      (kiểu tự trích) có trong docs_bm25    : 371.702 / 371.702   ← khớp tuyệt đối
```

Nghĩa là:

- Tra **OCR** từ kết quả search → nối thẳng được.
- Tra **`doc_text` của BM25** từ kết quả search → **KHÔNG nối thẳng được.** Phải đi vòng
  qua `clip_kf_map.parquet`, bảng có cả hai cột `kf_id` và `clip_kf_id`.

> [!WARNING]
> Nếu `evidence.py` nối thẳng `keyframe_id` của search vào `docs_bm25` thì kết quả là
> **rỗng trắng** — không crash, không cảnh báo, chỉ là panel "vì sao frame này lên hạng"
> lúc nào cũng trống. Đúng loại lỗi im lặng cả dự án đang phòng.
>
> → `evidence.py` **bắt buộc** dựng bảng dịch `clip_kf_id ↔ kf_id` từ `clip_kf_map` và
> ghi rõ trong docstring rằng đây là điểm nối duy nhất giữa hai hệ tên.

Đo kèm: `clip_kf_map.frame_drift` — khoảng lệch giữa keyframe BTC và keyframe tự trích
của cùng một chỗ:

| | frame |
|:---|---:|
| median | **11** |
| p95 | 21 |
| max | 25 |

Lệch cỡ nửa giây. Không đủ để đổi kết luận "frame này chứa gì", nhưng panel chẩn đoán
nên hiện con số này để lúc soi một câu trượt còn biết mình đang nhìn frame nào.

### 3.1. Cầu nối là ánh xạ NHIỀU-VỀ-MỘT, không phải 1-1

Phát hiện lúc viết test, không lộ ra khi đọc dữ liệu bằng mắt. Keyframe tự trích dày
hơn (1 fps) keyframe BTC (0,38 kf/s), nên **nhiều keyframe tự trích cùng trỏ về một
keyframe BTC**:

```
keyframe BTC dịch được sang tự trích : 166.661
  ánh xạ 1-1                          :  91.537
  bị TRÙNG (>1 ứng viên)              :  75.124   ← 45%
  nhiều nhất                          :       6 ứng viên / 1 keyframe BTC
```

Ví dụ thật `L26_V367#k0130` có 6 ứng viên, `frame_drift` từ 2 tới 22 frame.

→ Phải chọn ứng viên có **`frame_drift` nhỏ nhất** (gần nhất về thời gian). Lấy bừa
"dòng cuối thắng" — cách viết dict tự nhiên nhất — thì bằng chứng hiển thị lệch tới
**22 frame** so với ảnh người ta đang nhìn. Gần một giây, đủ để đọc nhầm nội dung
frame, và **không có dấu hiệu gì**.

### 3.2. 6% keyframe BTC không có cầu nối

```
keyframe BTC             : 177.321
có cầu nối sang tự trích : 166.661  (94,0%)
KHÔNG có                 :  10.660  (6,0%)
```

Với 10.660 keyframe này, panel `doc_text` sẽ trống. Không sửa được từ phía UI — đó là
độ phủ của `clip_kf_map` do Data Factory sinh. UI xử lý bằng cách **ghi rõ một dòng
cảnh báo** thay vì để panel trống không giải thích.

---

## 4. Thứ đang CHẶN và thứ chỉ làm giảm chất lượng

### 4.1. 🟢 Không có gì chặn hẳn D2.1

Kết luận sau khảo sát: **D2.1 làm được ngay hôm nay.** Ba thứ tưởng là chặn thì không phải:

| Tưởng là chặn | Thực tế |
|:---|:---|
| `backend/indexing/frame_map.py` gãy | Không đụng tới. UI lấy `frame_idx` từ chính kết quả `search()` (A2.2 đã trả sẵn), còn panel bằng chứng đọc parquet trực tiếp |
| Streamlit không có wheel cho Py3.14 | Đã cài sẵn 1.59.1 |
| Chưa có ảnh keyframe | Làm giảm chất lượng, không chặn — xem 4.2 |

### 4.2. 🟡 Làm giảm chất lượng, có đường lui

| # | Vấn đề | Chờ ai | Đường lui |
|:--:|:---|:---|:---|
| 1 | **Không có ảnh keyframe** (`data/derived/keyframes/`) | Công Lý / tải data | Vẽ thẻ placeholder in `kf_id · frame_idx · timestamp`. Đường dẫn đọc từ env `KEYFRAMES_DIR` — có ảnh về thì set env, không sửa code |
| 2 | **Milvus/ES có thể chưa chạy** | hạ tầng | Chế độ `offline`: BM25 thuần pandas trên `docs_bm25.parquet`. Không cần Docker, không cần torch |
| 3 | **Index `ocr`/`asr`/`objects` trong ES có thể chưa nạp** | Thạch | Đọc thẳng parquet thay vì hỏi ES. Chỉ `objects` là buộc phải qua ES |
| 4 | **Rerank (A2.4) chưa có** | Thạch, tuần W3 | Cột thứ ba để sẵn khung, hiện thẻ xám. Bật rerank là tự có dữ liệu |

### 4.3. Bộ nhãn: KHÔNG gitignore, mỗi người một file

Ban đầu định thêm `dev_set/` vào `.gitignore` cho khỏi conflict — **bỏ ý đó**. Nhãn là
công sức người (chấm 200 nhãn là vài giờ ngồi soi). Giấu đi thì:

- mất máy là mất trắng;
- người khác chạy `eval.py` ra số khác, cãi nhau không có cơ sở;
- cả nhóm không góp nhãn chung được, mỗi người tự chấm lại từ đầu.

Đáp án chung phải được **chia sẻ**. Cách giải quyết conflict không phải là vứt dữ liệu
mà là tách file theo người:

```
dev_set/labels.minhhoang.jsonl
dev_set/labels.thach.jsonl
```

Mỗi người ghi file riêng → **không bao giờ đụng nhau**, mà vẫn commit được.
`load_labels()` đọc gộp `dev_set/*.jsonl`. Trường `labeler` giữ lại để sau còn soi được
"hai người chấm cùng một frame mà lệch nhau" — chỗ lệch thường là truy vấn mơ hồ.

---

## 5. Quyết định thiết kế đã chốt

### 5.1. Nhãn là một KHOẢNG, không phải một điểm

```jsonl
{"query_id":"q_3f2a1b0c","query_vi":"...","task_type":"KIS","video_id":"L21_V001",
 "frame_start":425,"frame_end":448,"kf_id":"L21_V001#k0042","shot_id":"L21_V001#s0012",
 "label":"correct","labeler":"minhhoang","ts":"...","source":"debug_ui","note":""}
```

Hai lý do, cả hai đều là ràng buộc cứng chứ không phải sở thích:

1. **BTC chấm `frame_id ∈ [s, e]`** — một khoảng, không phải trúng đúng một frame.
2. **Slot allocator phát ra frame KHÔNG phải keyframe.** Mức ②③④ rải frame bất kỳ trong
   shot. Nhãn chỉ ghi "keyframe số 42 đúng" thì D3.5 không chấm nổi frame 431 mà
   allocator đẻ ra, dù nó nằm ngay cạnh.

Bắt buộc có `frame_start`/`frame_end` **dạng số frame trong video**, không phải số thứ
tự keyframe — cùng một lý do đã gỡ bug W0.2: hai số đó lệch nhau trung vị **5.300 frame**
trên toàn bộ 177.321 keyframe.

### 5.2. Logic nằm NGOÀI Streamlit

| File | Vai | Test được? |
|:---|:---|:---:|
| `app/debug_ui.py` | chỉ vẽ | không (và không cần) |
| `app/labels.py` | đọc/ghi nhãn | ✅ |
| `app/evidence.py` | tra bằng chứng, cầu nối hai kiểu `kf_id` | ✅ |
| `app/offline_search.py` | BM25 thô khi không có Docker | ✅ |

Streamlit không chạy trong `pytest`. Nhét logic vào đó là vừa mất test, vừa khiến E4.2
và D3.5 phải **viết lại** hàm đọc nhãn — mà viết lại là lệch nhau.

`app/labels.py` sẽ xuất `is_correct(query_id, video_id, frame_idx) -> bool`. Đó **chính
là hàm chấm điểm** mà `eval.py` và `score_simulator` gọi. Viết một lần ở đây.

### 5.3. Lấy bảng xếp hạng từng nhánh bằng chính `search()`

`search(branches={...})` đã là tham số công khai. Muốn xem riêng nhánh CLIP thì gọi lại
với đúng nhánh đó bật. **Không viết lại logic truy xuất trong UI** — đúng nguyên tắc
"UI gọi search làm tool".

---

---

## 6. Chi tiết từng hàm

### 6.1. `app/labels.py` — bộ nhãn dev set

| Tên | Mô tả |
|:---|:---|
| `Label` | Một lượt chấm. `__post_init__` chặn dữ liệu sai **ngay lúc dựng**: nhãn lạ · id rỗng · frame âm · khoảng ngược. Tự đóng dấu `ts` để biết dòng nào mới hơn |
| `Label.chua()` | frame có nằm trong khoảng không (**gồm cả hai đầu**) |
| `duong_dan_nhan()` | `dev_set/labels.<người>.jsonl` — mỗi người một file |
| `ghi_nhan()` | Nối **một** dòng, `flush()` ngay. UTF-8 không BOM, LF |
| `load_labels()` | Đọc gộp mọi file, khử trùng theo khoá, `ts` mới nhất thắng |
| `_doc_mot_file()` | Dòng hỏng thì **báo rồi bỏ qua**, không kéo sập cả file |
| `BangNhan` | Chỉ mục tra nhanh — dựng một lần, hỏi bao nhiêu lần cũng được |
| `BangNhan.is_correct()` | **Hàm chấm điểm dùng chung** cho E4.2 và D3.5 |
| `BangNhan.nhan_cua_frame()` | Nhãn hiện tại của một frame; khoảng **hẹp nhất** thắng |

Ba quyết định đáng ghi lại:

**a) `flush()` từng dòng.** Streamlit nạp lại app mỗi lần sửa code. Ghi đệm thì nhãn
vừa bấm bay mất mà người chấm tưởng đã lưu.

**b) `wrong` không phủ định `correct` chồng lên nó.** `wrong` chỉ có nghĩa "chỗ này đã
soi, không phải" — nó không chứng minh được chỗ khác cũng sai. Nếu cho nó quyền phủ
định thì một lần khoanh hẹp sẽ vô hiệu hoá cả khoảng đúng đã chấm trước đó.

**c) `unsure` không bao giờ tính thành đúng.** Nghe hiển nhiên, nhưng nếu `is_correct`
viết kiểu `!= "wrong"` thì `unsure` lặng lẽ thành điểm. Có test riêng cho ca này.

### 6.2. `app/evidence.py` — gom bằng chứng của một keyframe

| Tên | Mô tả |
|:---|:---|
| `_doc()` | Đọc bảng derived, **lọc sẵn theo video** bằng `filters`. Thiếu file → rỗng, không raise |
| `_cau_noi()` | **Cầu nối hai hệ tên** (mục 3). Chiều BTC → tự trích chọn `frame_drift` nhỏ nhất |
| `_frame_map_video()` | `kf_id` BTC → `frame_idx` thật |
| `tach_id()` | id bất kỳ → `(video_id, id BTC, id tự trích)`. **Không ghép chuỗi**, phải tra bảng |
| `bang_chung()` | Gom tất cả. **Không bao giờ raise** vì thiếu dữ liệu — thành `canh_bao` |
| `keyframe_cung_shot()` | Dải ngữ cảnh trước/sau trong cùng shot |
| `xoa_cache()` | Quên bảng đã nạp khi Data Factory giao bản mới giữa phiên |

**ASR gán theo THỜI GIAN, không theo id**, và phân biệt hai mức: đoạn nói **chứa**
frame (`truc_tiep=True`) khác hẳn đoạn chỉ dính vì cửa sổ ±3s. Không phân biệt thì
người chấm tưởng câu nói đó phát ra ngay tại frame đang xem.

**`frame_idx` ưu tiên `frame_map`**, không lấy hậu tố của id tự trích — hậu tố đó cũng
là một `frame_idx` nhưng của keyframe **tự cắt**, lệch với keyframe BTC trung vị 11
frame. Có test riêng đối chiếu với `frame_map.parquet`.

---

### 6.3. `app/offline_search.py` — BM25 thô, đường lui khi không có Docker

| Tên | Mô tả |
|:---|:---|
| `tach_tu()` | Truy vấn → từ khoá, viết thường, bỏ trùng, bỏ từ < 2 ký tự |
| `tim()` | Một lượt quét theo lô: đếm tần suất + đo độ dài + đếm `df`, tính BM25 sau |
| `_trich_quanh()` | Cắt đoạn `doc_text` quanh từ khớp — nhìn phát biết vì sao lên hạng |
| `main()` | CLI: `python -m app.offline_search "tên riêng hiếm"` |

**Ba quyết định đều dựa trên số đo**, không phải cảm tính. Đo trên toàn kho 371.702
tài liệu (dài trung bình 1.977 ký tự):

| Cách làm                           | Chi phí mỗi truy vấn | Quyết định                        |
| :-----------------------------------| ---------------------:| :----------------------------------|
| Nạp cả cột `doc_text` vào RAM      | 845 MB               | ❌ quét theo lô, đỉnh = 1 lô       |
| Bỏ dấu tiếng Việt (NFD + regex)    | 40,4 s               | ❌ bỏ — chấp nhận phải gõ có dấu   |
| Đo độ dài bằng `str.count(r"\s+")` | 29,7 s               | ❌ đổi sang `str.len()`, còn 1,0 s |
| `str.lower()`                      | 6,2 s                | ✅ giữ                             |
| `str.count` chuỗi con, mỗi từ khoá | 0,8 s                | ⚠️ nhanh nhưng **SAI** — xem dưới  |
| `str.count` có `\b`, mỗi từ khoá   | 2,7 s                | ✅ dùng, nhưng chỉ cho ứng viên    |

Tổng thực tế: **~18 s cho truy vấn 5 từ**, ~15 s cho truy vấn 1 từ phổ biến. Chậm,
nhưng đây là đường lui — và 18 s vẫn hơn hẳn "không mở được UI".

### 6.3.1. Hai lỗi đếm từ, đều phát hiện từ một truy vấn thật

Tra **"tù nhân"** trả về toàn `nạn nhân là ông tùng`, không có tù nhân nào. Kho có
**26 keyframe chứa đúng cụm "tù nhân"** mà không cái nào lọt top-5. Lần lại ra hai
lỗi chồng lên nhau.

**Lỗi 1 — đếm chuỗi con thay vì đếm từ.**

`str.count("ba")` đếm cả những lần `ba` nằm **bên trong** một từ khác. Tiếng Việt đơn
âm nên từ khoá thường chỉ 2–3 ký tự, và mức thổi phồng đo được trên `L21_V001` là:

| Từ khoá | Đếm chuỗi con | Đếm đúng từ | Thổi phồng |
|:---|---:|---:|---:|
| `ba` | 1.078 | 24 | **×44,9** |
| `an` | 10.046 | 913 | ×11,0 |
| `hoa` | 273 | 49 | ×5,6 |
| `nam` | 2.793 | 1.482 | ×1,9 |

Hậu quả thật, quan sát được trước khi sửa: gõ `ba` thì hạng 1 là một tài liệu chứa
`#baothanhnien` — **không hề có chữ "ba" nào**. Không crash, không cảnh báo, chỉ là
bảng xếp hạng vô nghĩa.

Cách sửa (`_dem_dung_tu()`) **hai lượt**, vì đếm đúng ranh giới từ đắt hơn nhiều:

1. Lượt 1 — đếm chuỗi con (rẻ). Kết quả là **cận trên**: tài liệu chứa từ thật thì
   chắc chắn cũng chứa chuỗi con, nên không bỏ sót cái nào.
2. Lượt 2 — đếm đúng ranh giới từ, **chỉ trên số tài liệu lọt lượt 1**.

**Lỗi 2 — `\b` không dùng được cho tiếng Việt, và pandas âm thầm đổi công cụ regex.**

Bản sửa đầu tiên dùng `pandas.str.count(r"\btù\b")`. Vẫn sai, sai kiểu khác:

| Tài liệu | `\btù\b` cho ra | Đúng phải là |
|:---|---:|---:|
| `tù nhân bỏ trốn` | **0** | 1 |
| `nạn nhân là ông tùng` | **1** | 0 |

Sai **ngược hoàn toàn** — đúng lý do "tù nhân" trả về "ông tùng". Hai nguyên nhân
chồng nhau:

- **pandas 3.0 chọn backend regex theo dtype.** Cột đọc từ parquet có dtype `str` nên
  `str.count` chạy **RE2 của pyarrow**; cùng dữ liệu ấy `astype(object)` thì chạy
  module `re` và cho kết quả **khác**. pandas không hứa giữ nguyên cách chọn này.
- **`\b` của RE2 chỉ coi `[A-Za-z0-9_]` là chữ cái.** Với `ù`: trong `tù nhân`, sau
  `ù` là dấu cách — RE2 coi cả hai đều không-phải-chữ nên **không thấy ranh giới**,
  không khớp. Trong `tùng`, sau `ù` là `n` — RE2 thấy ranh giới, **khớp**.

Bản cuối gọi thẳng `pyarrow.compute.count_substring_regex` với ranh giới viết bằng
lớp chữ cái Unicode:

```python
_RANH_GIOI_TU = r"(?:^|[^\p{L}\p{N}_])%s(?:[^\p{L}\p{N}_]|$)"
```

Gọi thẳng pyarrow chứ không qua pandas là để **luôn biết mình đang chạy công cụ nào** —
mẫu regex chỉ đúng cho đúng một công cụ.

**Đối chiếu:** khớp module `re` của Python trên 11 ca biên (gồm chồng lấn `tù tù tù`,
ngăn cách bằng dấu câu, chữ hoa, số dính liền) và 400 ca sinh ngẫu nhiên — **411/411**.

**Đo lại:** 14,2 s cho 5 từ khoá trên toàn kho — bằng đúng bản đếm chuỗi con sai. Ba
cách khác đều bị loại: `\b` qua module `re` **46 s**, `astype(object)` **49 s**, cả hai
quá chậm để chấm nhãn bằng tay.

**Kết quả tra lại "tù nhân"** — 5 hạng đầu đều là tin về bạo loạn nhà tù ở Nga.

> [!NOTE]
> Bỏ dấu là đánh đổi **có chủ ý**, có test chốt lại (`test_tach_tu_KHONG_bo_dau`) để
> sau này không ai tưởng là quên làm. Đường thi có `VI_FOLDED_ANALYSIS` của
> Elasticsearch lo việc này; gõ thiếu dấu ở chế độ offline vẫn chạy, chỉ ít kết quả
> hơn — hụt chứ không sai.

### 6.4. `app/debug_ui.py` — màn hình

**Chỉ vẽ.** Không có logic dữ liệu nào, nên không có gì để test ngoài "trang có vẽ được
không" — và đúng thứ đó thì có test (mục 7).

| Vùng | Nội dung |
|:---|:---|
| **A · Sidebar** | truy vấn VI + EN · dạng bài · top-K · chọn `live`/`offline` · **5 ô bật/tắt nhánh** · gom-về-shot · tên người chấm |
| **B · Ba tab kết quả** | *Sau RRF* · *Từng nhánh riêng* · *Sau rerank* (khung xám chờ A2.4) |
| **C · Bằng chứng** | `frame_idx` in to nhất · dải shot · OCR (`text_raw` \| `text_clean` cạnh nhau) · ASR · `doc_text` · objects |
| **D · Chấm nhãn** | ✓ Đúng · ✗ Sai · ? Chưa chắc · **✓ Cả shot** |

Bốn chi tiết đáng ghi:

**a) Nút "✓ Cả shot".** Một cú bấm ra một khoảng ~69 frame (độ dài shot trung vị) thay
vì một frame. Nhãn dày lên nhanh hơn hàng chục lần, mà vẫn đúng ngữ nghĩa "khoảng đáp án".

**b) Tab "Từng nhánh riêng" gọi lại chính `search(branches={...})`** thay vì tự truy
xuất. Đúng nguyên tắc "UI gọi search làm tool, không viết lại logic tìm kiếm".

**c) `text_raw` và `text_clean` đặt CẠNH NHAU.** Bất biến B1.4 là giữ nguyên `text_raw`
vì LLM đôi khi "sửa" hỏng tên riêng — muốn thấy nó sửa gì thì phải nhìn được cả hai.

**d) ASR phân biệt "ngay tại frame" với "gần đó (±3s)".** Không phân biệt thì người
chấm tưởng câu nói đó phát ra đúng lúc frame đang xem.

---

---

## 7. Kết quả chạy thực tế

```
153 test toàn repo · 150 xanh
  tests/test_labels.py   : 27 test   (D2.1)
  tests/test_evidence.py : 16 test   (D2.1)
  … 110 test của D0.2 + D3.1
3 đỏ là backend/indexing/frame_map.py của Công Lý, không liên quan D2.1
```

Không mock. Bằng chứng lấy từ `clip_kf_map` · `frame_map` · `ocr` · `asr` ·
`docs_bm25` · `shots` · `video_info` thật.

Chạy thử trên `L21_V001#k0004`:

```
frame_idx=352  t=11.73s  shot=L21_V001#s0001  biên=(347, 385)  n_frames=37849
OCR: 1 mục  →  text_raw='06:30:22'  n_boxes=1  avg_conf=1.0
doc_text: 1308 ký tự  →  "[title] 60 giây sáng - ngày 01082024 - htv tin tức…"
ảnh: None (chưa tải keyframe về — vẽ thẻ xám)
cảnh báo: không có
```

Chú ý con số: `frame_map` cho `frame_idx=352`, còn id tự trích ghi `_0000375`. Lệch 23
frame — đúng dải `frame_drift` đã đo. Lấy nhầm là sai lệch gần một giây ở **mọi** dòng.

## 8. Kết quả chạy đầu-cuối

```
AIC_LABELER=e2e · chế độ offline
  gõ "60 giây sáng" → bấm Tìm kiếm  → 8,5 s, 20 kết quả, 0 exception
  bấm "✓ Đúng" ở hạng 1              → 0 exception
  dev_set/labels.e2e.jsonl:
    {"query_id":"q_b706044f","query_vi":"60 giây sáng","task_type":"KIS",
     "video_id":"L21_V018","frame_start":28380,"frame_end":28380,"label":"correct",
     "labeler":"e2e","ts":"2026-08-12T17:01:27+07:00","kf_id":"L21_V018_0028380",
     "shot_id":"L21_V018#s0343","source":"debug_ui"}
```

`frame_start = 28380` là **frame index trong video**, không phải số thứ tự keyframe —
đúng con số `eval.py` sẽ đối chiếu với file nộp.

### 8.1. Bộ test

```
176 test toàn repo · 173 xanh
  tests/test_labels.py         : 27 test   (D2.1)
  tests/test_evidence.py       : 16 test   (D2.1)
  tests/test_offline_search.py : 13 test   (D2.1)
  tests/test_debug_ui.py       : 10 test   (D2.1, dùng streamlit AppTest)
  … 110 test của D0.2 + D3.1
3 đỏ là backend/indexing/frame_map.py của Công Lý, không liên quan D2.1
```

`AppTest` chạy thật kịch bản Streamlit trong tiến trình pytest và thu exception — bắt
được đúng loại lỗi "đổi tên một trường là trang nổ giữa lúc đang chấm nhãn".

### 8.2. Ba lỗi test bắt được

| Lỗi | Hậu quả nếu lọt |
|:---|:---|
| `_cau_noi` giữ **dòng cuối** thay vì dòng gần nhất | Bằng chứng lệch tới 22 frame so với ảnh đang nhìn |
| `tach_id` nổ `TypeError` khi gặp `NAType` | Ô rỗng trong parquet làm sập UI |
| Trang **tự chạy search** khi chưa bấm nút | Đợi ~18 giây mỗi lần chạm bàn phím, kể cả lúc chỉ bấm nút chấm nhãn |

---

## 9. Rà soát lại toàn bộ (13/08)

### 9.0. Đối chiếu với đặc tả D2.1 trong `BUILD_TASKS.md`

Bốn gạch đầu dòng của đặc tả, đối chiếu từng cái:

| # | Đặc tả yêu cầu | Trạng thái |
|:--:|:---|:---|
| 1 | Nhập query → thấy kết quả **từng tầng cạnh nhau** (sau RRF / sau rerank) | 🟡 có 3 tab: RRF ✅ · từng nhánh riêng ✅ · **rerank là khung rỗng**, chờ A2.4 |
| 2 | Click frame → thấy **caption, OCR, ASR, object** của frame đó | 🟡 OCR ✅ ASR ✅ (+`doc_text`) · **caption ❌** · **object ❌** — xem dưới |
| 3 | Hiển thị **thứ hạng từng nhánh** cho mỗi kết quả | ✅ đủ 5 nhánh, đọc từ `ranks` của A2.2 |
| 4 | Nút đúng/sai ghi thẳng vào `dev_set/labels.jsonl` | ✅ có, nhưng **đổi tên file** — xem 9.0.2 |

#### 9.0.1. Hai thứ đặc tả đòi mà KHÔNG có nguồn dữ liệu

Đây không phải "chưa làm", mà là "chưa ai sinh ra thứ đó".

**`caption` mức frame — không có ai sản xuất.** Tìm khắp repo:

```
data/derived/*.parquet   → không bảng nào có cột caption
preprocessing/           → không job nào sinh caption
backend/indexing/        → không loader nào nạp caption
BUILD_TASKS.md           → không task nào giao việc này
```

Chữ "caption" trong `BUILD_TASKS.md` chỉ xuất hiện ở **C1.1**, và đó là caption của
**câu hỏi** (dịch query sang tiếng Anh cho CLIP), không phải mô tả nội dung frame.

→ Muốn có ô này phải chạy VLM sinh mô tả cho 177.321 keyframe — một job GPU cỡ OCR,
**chưa nằm trong kế hoạch của ai**. Cần chốt: bỏ hẳn khỏi D2.1, hay giao thành task
mới cho Data Factory. **Đây là việc cần hỏi Thạch/Linh, không tự quyết được.**

**`objects` mức frame — chưa có dữ liệu, kể cả bản mẫu.**

```
data/derived/objects.parquet   → không có
data/sample/objects.json       → không có (đường dẫn mặc định của load_objects.py)
```

`load_objects.py` tồn tại và nạp vào Elasticsearch, nhưng **file nguồn không tồn
tại**. Nên đây không chỉ là "cần Docker chạy" — có Docker cũng không nạp được gì.
Panel Objects trong UI hiện một dòng giải thích thay vì để trống.

#### 9.0.2. Một chỗ cố ý làm khác đặc tả

Đặc tả ghi `dev_set/labels.jsonl` (một file). Code ghi
**`dev_set/labels.<người>.jsonl`** (mỗi người một file).

Lý do: nhãn được commit lên git (§4.3). Năm người cùng `append` vào một file thì mỗi
lần pull là một conflict, và conflict trên file JSONL rất dễ giải quyết sai — mất
nhãn mà không ai biết. Tách theo người thì hai người không bao giờ đụng cùng một
dòng, mà `load_labels()` vẫn gộp lại thành một bộ duy nhất khi đọc.

→ Thay đổi này **không ảnh hưởng ai khác**: E4.2 và D3.5 gọi `load_labels()` /
`BangNhan`, không đọc thẳng file.

Đọc lại cả 4 file sau khi đã chạy thật. Sáu chỗ sai, **đã sửa hết**, mỗi chỗ có test
khoá lại.

| # | Chỗ sai | Hậu quả nếu để nguyên | Cách sửa |
|:--:|:---|:---|:---|
| 1 | **Đếm chuỗi con thay vì đếm từ** (`offline_search`) | Xếp hạng vô nghĩa với từ khoá ngắn — thổi phồng tới ×45, xem §6.3.1 | `_dem_dung_tu()` hai lượt |
| 2 | Ô bật/tắt 5 nhánh **vẫn bấm được ở chế độ offline** | Tắt `vector` thấy kết quả y hệt → kết luận "vector không đóng góp", trong khi nó chưa từng được gọi | `disabled=` khi offline |
| 3 | Nhãn không ghi **chấm từ chế độ nào** | Không phát hiện được lệch bộ nhãn (§10.3) | `source = "debug_ui/live"` hoặc `/offline` |
| 4 | Khoá widget OCR dùng `id(dict)` | `id()` là địa chỉ bộ nhớ, được cấp lại sau GC → hai lần vẽ khác nhau trùng khoá, Streamlit lỗi giữa lúc đang chấm | khoá theo `kf_id` + thứ tự |
| 5 | `bang_chung()` bị gọi **hai lần mỗi thẻ** | 20 kết quả = 40 lượt lọc DataFrame thừa | gọi một lần, dùng lại |
| 6 | `shot_id` rỗng thành chuỗi `"nan"` | `str(NaN)` ra `"nan"`, trôi thẳng vào file nhãn không ai nhận ra | `_chuoi_hoac_none()` |
| 7 | **`\b` sai với tiếng Việt + pandas đổi backend regex** | Xếp hạng sai NGƯỢC: "tù nhân" ra "ông tùng", xem §6.3.1 | gọi thẳng `pyarrow.compute` với `\p{L}` |
| 8 | UI mặc định chọn `live` trên máy chưa cài gì | `backend.retrieval.search` nạp lười nên import trót lọt; người dùng bấm Tìm kiếm rồi mới biết | kiểm từng gói bằng `find_spec`, báo tên gói + lệnh `pip install` |
| 9 | Thiếu `ANTHROPIC_API_KEY` + bỏ trống ô tiếng Anh | `search()` gọi LLM để dịch và ném lỗi **trước khi nhánh nào chạy** → chết cả 5 nhánh, stack trace không liên quan gì tới thao tác vừa bấm | chặn trước, đánh dấu ô tiếng Anh là BẮT BUỘC |

Ngoài ra: `insert(0, …)` trong vòng lặp làm **lật ngược** thứ tự cảnh báo lược đồ (đã
đổi thành ghép cả khối), và `dai_tb` không chặn `NaN` (đã thêm chặn).

### 9.1. ⚠️ Hai nguồn cùng nói về `frame_idx`

Phát hiện lúc rà soát, **chưa xử lý dứt điểm** vì không có cách xử lý đúng ở phía UI:

- `search()` trả `frame_idx` lấy từ **Milvus** (chế độ `live`) hoặc từ hậu tố kf_id tự
  trích (chế độ `offline`).
- `evidence.bang_chung()` tra `frame_idx` từ **`frame_map.parquet`**.

Hai số này **có thể lệch nhau**, và ở chế độ `offline` thì lệch là chuyện bình thường
— keyframe tự trích và keyframe BTC cách nhau trung vị 11 frame (§3). Nhãn ghi theo
số đang hiện trên thẻ, còn panel bằng chứng hiện số của `frame_map`.

Đã xử lý bằng cách **nói ra**: thẻ nào lệch thì hiện một dòng `⚠️ frame_map nói N
(lệch ±k)` kèm gợi ý bấm **✓ Cả shot**. Nhãn cả shot là một khoảng nên nuốt được cả
hai số, tránh hẳn vấn đề.

> [!WARNING]
> Đây là chỗ đáng soi lại khi có data thật. Nếu Milvus được nạp `frame_idx` từ nguồn
> khác `frame_map.parquet` thì đó là lỗi của A2.2/A1, không phải của D2.1 — nhưng
> chính UI này là nơi nhìn thấy nó đầu tiên.

### 9.1b. Chế độ `live` đã đúng hợp đồng tới đâu

Đã đối chiếu từng điểm với `backend/retrieval/search.py`, có test khoá lại:

| Điểm nối | Trạng thái |
|:---|:---|
| Chữ ký `search(query_vi, query_en, top_k, branches, group_by_shot)` | ✅ khớp |
| Tên 5 nhánh UI gửi đi so với `BRANCHES` | ✅ khớp — `test_ten_nhanh_KHOP_voi_search_weights` |
| Trường UI đọc (`keyframe_id/video_id/frame_idx/shot_id/score/ranks`) | ✅ có trong hợp đồng `search()`, neo bằng test |
| Thiếu gói → báo tên gói + lệnh cài | ✅ sau khi sửa lỗi #8 |
| Thiếu khoá API → chặn trước, không để nổ giữa chừng | ✅ sau khi sửa lỗi #9 |

> [!IMPORTANT]
> Tên nhánh là chỗ nguy hiểm nhất: `search()` gộp `{**BRANCHES, **branches}` nên gõ
> sai một khoá **không báo lỗi** — nó nằm im và nhánh thật vẫn bật theo mặc định.
> Bỏ tick `vector` thấy kết quả không đổi rồi kết luận "vector không đóng góp gì".
> Đó là lý do có test riêng cho việc này.

**Chưa kiểm được:** không có Milvus/ES chạy nên **chưa từng có một lượt `live` nào
chạy thật**. Những gì đã kiểm là hợp đồng tĩnh — chữ ký hàm, tên khoá, tên trường.
Thứ chỉ lộ ra lúc chạy (Milvus trả `frame_idx` kiểu gì, `ranks` có đủ 5 nhánh không,
`shot_id` có `None` không) thì phải đợi dựng xong hạ tầng mới biết.

### 9.2. Còn lại, chờ người khác

| Việc | Chờ ai |
|:---|:---|
| Ảnh keyframe → thay thẻ xám bằng ảnh thật | Data Factory (§4.2) |
| File `.npy` `clip-features-32` → nhánh `vector` mới chạy | Data Factory (§10.2) |
| Panel `objects` | **chưa có nguồn dữ liệu nào** (§9.0.1), không phải chỉ chờ Docker |
| Panel `caption` mức frame | **chưa ai được giao việc sinh ra nó** (§9.0.1) — cần chốt |
| Tab "Sau rerank" | A2.4 của Thạch |
| Một lượt `live` chạy thật | hạ tầng — xem 9.1b |

Một rủi ro để ngỏ tới lúc có ảnh: `_duong_dan_anh()` đang **thử hai quy ước tên file**
(`0000.jpg` đếm từ 0 và `0001.jpg` đếm từ 1) rồi lấy cái nào tồn tại. Nếu bộ ảnh thật
có cả hai thì nó chọn nhầm mà không báo. Có ảnh về là phải kiểm lại, không kiểm được
bằng test lúc này.

---

## 10. Dùng chế độ nào, cần gì để chạy

### 10.1. Lúc THI thì dùng gì

**Không dùng cái nào trong hai cái này.** UI debug không phải công cụ nộp bài.

| Việc | Chạy bằng gì |
|:---|:---|
| **Nộp bài lúc thi** | `backend/retrieval/search.py` → `backend/slot/allocate()` → `backend/export/exporter.py`. Tức là **đường `live`**, nhưng gọi từ pipeline chứ không qua Streamlit |
| Chấm nhãn dev-set trước khi thi | `app/debug_ui.py`, chế độ nào cũng được |
| Đo `Final Score` của nhóm | E4.2 `eval.py`, ăn file nhãn |

Sơ tuyển 8/2026 nộp **lô**, không trừ thời gian → không ai ngồi bấm UI lúc thi. UI này
là để **trước ngày thi**, sinh ra bộ nhãn và soi xem search sai chỗ nào.

### 10.2. `live` cần gì

`live` **cần cả Docker lẫn dữ liệu đã nạp** — Docker chỉ dựng cái thùng rỗng.

| Lớp | Thiếu thì mất gì |
|:---|:---|
| `pip install elasticsearch pymilvus` | không kết nối được, `live` báo lỗi ngay |
| `pip install torch open_clip_torch` | không encode được câu hỏi → mất nhánh `vector` |
| Docker Desktop **đang chạy** + `docker compose up -d` | ES/Milvus không tồn tại |
| `python -m backend.indexing.load_{metadata,ocr,asr,objects}` | 4 nhánh chữ trả rỗng |
| **File `.npy` của BTC** (`data/raw/clip-features-32`) + `load_clip` | Milvus rỗng → **nhánh `vector` trả rỗng**, đây là nhánh lõi |

Trạng thái máy này (đo 12/08): 4 gói pip **thiếu cả 4**; Docker CLI có (29.4.2) nhưng
**daemon chưa chạy**; **không có file `.npy` nào**. `torch 2.13.0+cpu` có wheel cho
Py3.14 — không dính rủi ro như paddle/whisper.

→ Cài pip + bật Docker vẫn **chưa đủ**: phải xin `clip-features-32` từ Data Factory.

### 10.3. `offline` cần gì

Chỉ cần `data/derived/docs_bm25.parquet`, đã có sẵn. Không Docker, không torch, không
ES. Đổi lại: **chỉ có BM25 trên chữ** — không nhánh vector, không RRF, không rerank.

Nên dùng `offline` khi: chấm nhãn cho câu hỏi mà lời giải nằm trong OCR/ASR, hoặc lúc
Docker chưa lên mà không muốn ngồi đợi.

> [!WARNING]
> Chấm nhãn **chỉ** từ kết quả `offline` sẽ làm lệch bộ nhãn: nhãn tập trung vào frame
> mà BM25 tìm ra được. Lúc E4.2 chấm `live`, điểm sẽ **thấp hơn thực tế** vì frame
> đúng do nhánh vector tìm ra chưa từng được ai chấm. Muốn số tin được thì phải có
> nhãn từ cả hai chế độ.
