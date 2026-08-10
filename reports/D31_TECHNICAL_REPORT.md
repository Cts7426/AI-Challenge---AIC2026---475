# 📋 Báo Cáo Kỹ Thuật — Task D3.1: Slot Allocator

> **Ngày:** 07/08/2026 · **Hạn:** 09/08/2026
>
> **Người thực hiện:** Minh Hoàng
>
> **Phạm vi:** `backend/slot/` + `data/config/slot_budget.py` + `tests/test_allocator.py`
>
> ⚠️ **Đọc mục 10 trước khi tin bất cứ con số nào ở đây.** Task này làm sớm hơn tiến độ
> chung, nên một số đầu vào còn là giả lập — mục 10 nói rõ chỗ nào.
>
> 🔄 **Cập nhật 07/08 (chiều):** Data Factory giao bản dữ liệu mới và **đổi schema**
> (`video_info.n_frames` → `nb_frames_decoded`; `frame_map.btc_kf_ordinal` → `btc_ordinal`,
> `frame_idx_corrected` → `frame_idx`). Code đã sửa theo và thêm `_doc_cot()` — assert
> cột lúc nạp, để lần đổi sau báo được tên cột thiếu thay vì ném `ArrowInvalid`.
> Chi tiết ở mục 10.3 · phần mới `rep_kf_id` ở mục 10.5.

---

## Mục lục
1. [Vấn đề phải giải](#1-vấn-đề-phải-giải)
2. [Luồng hoạt động](#2-luồng-hoạt-động)
3. [Chia vai: chiến thuật và cơ chế](#3-chia-vai-chiến-thuật-và-cơ-chế)
4. [Máy phát frame — bốn mức ưu tiên](#4-máy-phát-frame--bốn-mức-ưu-tiên)
5. [Vòng tròn xen kẽ](#5-vòng-tròn-xen-kẽ)
6. [Ba dạng bài](#6-ba-dạng-bài)
7. [Chi tiết từng hàm](#7-chi-tiết-từng-hàm)
8. [Kết quả chạy thực tế](#8-kết-quả-chạy-thực-tế)
9. [Đo độ trễ](#9-đo-độ-trễ)
10. [⚠️ Phần TREO và phần có thể LỆCH](#10-️-phần-treo-và-phần-có-thể-lệch) — kèm [10.5 `rep_kf_id`](#105--rep_kf_id-đã-có--phao-dự-phòng-cho-rủi-ro-số-2) · [**10.6 vấn đề còn trong code**](#106--vấn-đề-còn-trong-code--rà-lại-0708) · [**10.7 hậu quả lần pull**](#107--hậu-quả-của-lần-pull-0708-chiều--chưa-sửa)
11. [🧪 Code chỉ để thử nghiệm — bỏ khi vào thi](#11--code-chỉ-để-thử-nghiệm--bỏ-khi-vào-thi)
12. [Đối chiếu với yêu cầu](#12-đối-chiếu-với-yêu-cầu)
13. [Kết luận](#13-kết-luận)

---

## 1. Vấn đề phải giải

Tầng search đưa xuống một danh sách shot đã xếp hạng. Nhiệm vụ: biến nó thành **đúng
100 dòng đáp án**, đã xếp hạng, sẵn sàng nộp.

Ba ràng buộc mâu thuẫn nhau, và bảng dưới là chỗ chúng gặp nhau:

**1. Đúng shot chưa chắc đúng đáp án.** BTC chấm `frame_id ∈ [s, e]` — một cửa sổ hẹp
**bên trong** shot, không phải cả shot. Số thật từ `shots.parquet`:

| | frame |
|:---|---:|
| shot ngắn nhất | 12 |
| median | **69** |
| dài nhất | 1795 |

Đặt đúng 1 frame vào một shot 69 frame là tìm ra rồi mà vẫn có thể trượt.

**2. Nhưng chiều sâu thì miễn phí.** `frame_id` chỉ là số nguyên trong `[0, n_frames)`,
không cần ảnh, không cần embedding, không cần được index (`BUILD_TASKS` D3.1). Đào sâu
không tốn GPU, không tốn gì.

**3. Thứ tự nộp quyết định gần một nửa số điểm.** `R@1 + R@5 = 40%` tổng điểm. Dồn 8
slot đầu vào shot hạng 1 mà shot đó sai là mất trắng cả hai.

→ Bài toán: **chia 100 slot cho bao nhiêu shot, mỗi shot mấy slot, và phát ra theo
thứ tự nào.**

---

## 2. Luồng hoạt động

```mermaid
flowchart TD
    A["Tầng search (A2.1)<br/>top-K shot đã xếp hạng"] --> B["ShotHit<br/>shot_id · score · best_keyframe_id"]
    B --> C["budget_per_shot()<br/>CHIẾN THUẬT: shot nào mấy slot"]
    C --> D["_frames_of_shot() × N<br/>mỗi shot 1 máy phát frame"]
    D -->|"tra biên shot"| E[("shots.parquet<br/>100.810 shot")]
    D -->|"keyframe → frame_idx"| F[("frame_map<br/>hàm của Công Lý")]
    D -->|"kẹp [0, n_frames)"| G[("video_info<br/>873 video")]
    D --> H{"_quay_vong()<br/>XEN KẼ theo shot"}
    H --> I["100 Answer đã xếp hạng"]
    I --> J["QuerySubmission → export.py (D0.2)"]

    style A fill:#e1f5fe
    style I fill:#c8e6c9
    style J fill:#c8e6c9
```

**Đây là nơi cuối cùng còn biết `frame_idx` thật.** Tầng định dạng đã bị tước hết khả
năng tra bảng ở W0.2 — nó chỉ ghi ra con số nhận được. Nghĩa là file này cấp sai frame
thì **không còn chốt chặn nào phía sau**.

---

## 3. Chia vai: chiến thuật và cơ chế

| File | Vai | Nhịp thay đổi |
|:---|:---|:---|
| `data/config/slot_budget.py` | **CHIẾN THUẬT** — cược bao nhiêu slot vào shot hạng mấy | đổi nhiều lần (D4.1 có hẳn task tune) |
| `backend/slot/allocator.py` | **CƠ CHẾ** — rút frame, xen kẽ, bảo đảm đủ 100 | viết một lần là xong |

Tách ra vì hai thứ này đổi với nhịp khác nhau. Lúc tune chỉ sửa **một dòng số**, không
đụng logic, không sợ làm hỏng phần cấp phát.

### Bảng ngân sách

```python
SLOT_BUDGET = [(3, 8), (7, 5), (10, 3), (11, 1)]   # 24+35+30+11 = 100, phủ 31 shot
```

| Hạng shot | Slot/shot | Ý đồ |
|:---|:---:|:---|
| 1–3 | 8 | tin nhất → đào sâu, gần như chắc trúng cửa sổ |
| 4–10 | 5 | khá tin |
| 11–20 | 3 | phòng hờ |
| 21–31 | 1 | vé số — nhưng ô 51–100 bỏ trống cũng là vứt điểm miễn phí |

`budget_per_shot(n_shots)` trải bảng này ra thành hạn mức từng shot, và nuốt luôn hai ca
lệch để `allocator.py` không phải biết:

- **Ít shot hơn bảng** (search chỉ ra 3 shot) → thiếu 76 slot, rải **vòng tròn** cho đủ
  100 → `[34, 33, 33]`. Rải vòng tròn chứ không dồn hết vào shot 1: dồn hết là quay lại
  đúng cái sai mà luật xen kẽ đang tránh.
- **Nhiều shot hơn bảng** → shot thứ 32 trở đi nhận 0.

> [!NOTE]
> Bất biến: `sum(budget_per_shot(n)) == 100` với **mọi** n. Đã quét n = 1…499.

---

## 4. Máy phát frame — bốn mức ưu tiên

Trái tim của file. Mỗi shot có một **generator**, xả frame theo độ tin cậy giảm dần:

| Mức | Nguồn | Vì sao đứng ở vị trí đó |
|:---:|:---|:---|
| ① | `frame_map[best_keyframe_id]` | Frame mình **thực sự có bằng chứng**, không phải điểm giữa tính ra |
| ② | rải đều trong vùng đã **thụt 10%** hai đầu | Frame sát biên shot hay dính chuyển cảnh — mờ, hoặc lẫn hai cảnh |
| ③ | mọi frame còn lại trong shot | Khi ② hết vì shot được cấp nhiều slot |
| ④ | nới dần ra ngoài biên shot, kẹp `[0, n_frames)` | **Chốt chặn cuối** |

Hai chi tiết quyết định tính đúng:

**a) Mức ④ là thứ làm bất biến "luôn đủ 100 dòng" thành đúng.** Shot 12 frame vẫn đẻ
được 100 frame khác nhau vì nó nới ra ngoài. Không cần viết nhánh `if` riêng cho ca
biên — độ sâu tự lo.

**b) Máy phát TỰ khử trùng.** Bốn mức chồng lấn nhau (mức ③ quét cả vùng mức ② đã phát).
Khử trùng đặt ngay trong generator, không đẩy cho chỗ gọi.

> [!WARNING]
> Đây là **bug thật gặp lúc code**. Ban đầu generator lặp lại chính nó. KIS không lộ vì
> `_quay_vong` có khử trùng riêng, còn TRAKE rút thẳng nên đẻ ra dòng trùng và chết ở
> dòng 80/100. Sửa bằng cách đưa khử trùng **vào hợp đồng của generator**, không vá chỗ
> gọi — chỗ gọi thứ ba sẽ lại quên.

**c) Mức ① không bị kẹp về biên shot.** Nếu `frame_map` và `shots.parquet` lệch nhau thì
tin `frame_map` — đó mới là con số BTC chấm.

---

## 5. Vòng tròn xen kẽ

```python
while len(ket_qua) < can:
    for i, (video_id, gen) in enumerate(nguon):
        if quotas[i] <= vong:      # shot này hết hạn mức ở vòng này
            continue
        for f in gen:              # rút tới khi được frame CHƯA dùng
            if (video_id, f) not in da_dung:
                ket_qua.append((video_id, f)); break
    vong += 1
```

Vòng `r` phát frame thứ `r` của **mọi** shot còn hạn mức:

| Vòng | Shot tham gia | Cộng dồn |
|:---:|:---|---:|
| 0 | cả 31 | 31 |
| 1–2 | 20 shot đầu | 71 |
| 3–4 | 10 shot đầu | 91 |
| 5–7 | 3 shot đầu | **100** |

Kết quả thật (31 shot ứng viên):

```
hạng 1: L21_V001, 34     ← shot 1
hạng 2: L21_V001, 350    ← shot 2
hạng 3: L21_V001, 388    ← shot 3
hạng 4: L21_V001, 415    ← shot 4
hạng 5: L21_V001, 463    ← shot 5
```

Năm slot đầu là **năm shot khác nhau** → shot hạng 1 sai vẫn còn nguyên cửa R@5.

Hai chi tiết:
- **Khử trùng theo cặp `(video_id, frame)`**, không phải theo `frame`. Frame 500 của hai
  video khác nhau là hai câu trả lời khác nhau.
- Vòng `for f in gen` bên trong: frame trùng **không tốn slot**, chỉ đẩy generator đi
  tiếp. Đó là lý do luôn ra đúng 100 chứ không phải "khoảng 100".

---

## 6. Ba dạng bài

| Dạng | Cách làm |
|:---|:---|
| **KIS** | như trên, 1 frame mỗi dòng |
| **Q&A** | y hệt KIS, đóng `answer_text` do module Q&A cấp vào cả 100 dòng. Thiếu `answer_text` → **raise**, tầng slot không bịa câu trả lời |
| **TRAKE** | xếp hạng theo **VIDEO**, không theo shot |

### Vì sao TRAKE xếp theo video

Tài liệu BTC, dạng bài TRAKE: **sai video = 0 tuyệt đối**; đúng video thì được điểm **từng phần**
theo tỉ lệ khoảnh khắc khớp (3/4 → 0.75). Nên 100 dòng đầu phải phủ **nhiều video**,
không phải nhiều phương án của cùng một video.

Mỗi video có N máy phát, một cho mỗi khoảnh khắc, lấy từ N shot điểm cao nhất của nó.
Dòng thứ j = frame thứ j của từng máy, sắp tăng dần. Video ít shot hơn N → dùng lại
shot tốt nhất, khoảnh khắc lấy sâu hơn.

Sau khi sắp vẫn có thể hai khoảnh khắc trùng frame → đẩy lên 1 đơn vị. Thà lệch 1 frame
còn hơn nộp dòng bị validator loại vì không tăng dần ngặt.

---

## 7. Chi tiết từng hàm

### 7.1. `data/config/slot_budget.py`

| Tên | Mô tả |
|:---|:---|
| `SLOT_BUDGET` | Bảng cược. `TODO: BTC` — phụ thuộc độ rộng cửa sổ `[s,e]` |
| `ANSWERS_PER_QUERY` | 100 — **nhập từ `submit_format.py`**, không khai báo lại. Luật BTC thì chỉ được có một nơi giữ |
| `SHOT_EDGE_INSET` | 0.10 — thụt mỗi đầu shot, tránh frame chuyển cảnh |
| `TRAKE_DEFAULT_N` | 4. `TODO: BTC` — chưa rõ đề có công bố N không |
| `budget_per_shot()` | Trải bảng → hạn mức từng shot. Tổng **luôn** = 100 |

### 7.2. `backend/slot/allocator.py`

| Tên | Mô tả |
|:---|:---|
| `ShotHit` | Đầu vào: `shot_id` · `score` · `best_keyframe_id`. `score` chỉ để **xếp hạng**, không so ngưỡng — cosine CLIP thực tế quanh 0.2–0.3 (CLAUDE.md bất biến 6) |
| `_shots()` | `shot_id → (video_id, start, end)`. `@lru_cache` → đọc đĩa 1 lần cho cả tiến trình |
| `_frame_of_keyframe()` | Gọi `load_frame_map()` **của Công Lý**, không tự đọc parquet. Trả `None` khi không có — mất mức ① của một shot không đáng làm hỏng cả bài nộp |
| `_rai_deu()` | m điểm rải đều trên `[a, b]`, gồm cả hai đầu |
| `_frames_of_shot()` | **Máy phát frame** — bốn mức ở mục 4. Tự khử trùng |
| `_quay_vong()` | **Xen kẽ** — mục 5 |
| `allocate()` | API công khai. Kiểm đầu vào → sắp theo `score` → cấp hạn mức → quay vòng → bọc `Answer` |
| `_bounds_of()` · `_video_of()` · `_gen_of()` | Ba hàm tra cứu nhỏ, dùng chung cache của `_shots()` |
| `_allocate_trake()` · `_mot_dong_trake()` | Nhánh TRAKE — mục 6 |
| `main()` | 🧪 CLI demo — xem mục 11 |

Trả về thẳng `list[Answer]` (class của `submit_format.py`) → cắm vào `QuerySubmission`
là nộp được, không cần tầng dịch ở giữa.

---

## 8. Kết quả chạy thực tế

### 8.1. Bộ test

```
99 test · 96 xanh — 3 đỏ do lỗi import NGOÀI (mục 10.7.A), không phải logic allocator
  tests/test_validator.py : 34 test   (D0.2, +2 canh schema)
  tests/test_export.py    : 28 test   (D0.2)
  tests/test_allocator.py : 37 test   (D3.1, +4 canh guard 09/08)
```

**Không mock.** Shot lấy từ `shots.parquet`, keyframe từ `frame_map.parquet`, độ dài
video từ `video_info.parquet` — đều là dữ liệu Data Factory đã giao.

| Nhóm test | Kiểm gì |
|:---|:---|
| Bất biến 1 — đủ 100 | 1/2/3/7/31/60 shot · **shot ngắn nhất dataset (12 frame)** vẫn ra 100 frame khác nhau |
| Bất biến 2 — xen kẽ | 5 slot đầu = 5 shot khác nhau · slot 1 là shot điểm cao nhất (test cố tình đảo thứ tự truyền vào) |
| Bất biến 3 — frame thật | frame ∈ `[0, n_frames)` · frame đầu mỗi shot = đúng `frame_map[best_keyframe_id]` · không frame nào rơi vào 10% mép |
| Ba dạng bài | KIS 1 frame · Q&A **từ chối khi thiếu answer** · TRAKE N=3/4/5 tăng dần ngặt · TRAKE 5 dòng đầu = 5 video |
| Chốt cuối | output cắm thẳng vào `validate_submission()` của D0.2 → phải rỗng |

### 8.2. Kiểm chứng bằng cách phá code

| Phá gì | Kết quả |
|:---|:---|
| Gom theo shot thay vì xen kẽ | **20 test đỏ** |
| Bỏ mức ① (không dùng keyframe thật) | 2 đỏ |
| Bỏ mức ④ (không nới ra ngoài shot) | 2 đỏ |
| Bỏ thụt biên 10% | 1 đỏ |
| Bỏ bù slot khi ít shot hơn bảng | 2 đỏ |
| Phục hồi | **96 xanh** (3 đỏ là lỗi ngoài, mục 10.7.A) |

### 8.3. Quét ngẫu nhiên 120 kịch bản

Ngoài test cố định, đã chạy 40 lần bốc ngẫu nhiên × 3 dạng bài:
- số shot ứng viên: 1 … 55
- số video: 1 … 12
- TRAKE N: 2 … 6

Kết quả: **120/120 ra đúng 100 dòng và validator im lặng.**

### 8.4. Ca biên xấu nhất

```
1 shot, 12 frame — shot NGẮN NHẤT toàn bộ dataset [10008, 10019]
→ 100 dòng, 100 frame KHÁC NHAU, trải 9964 … 10063
→ validator: HỢP LỆ
```

Đây là lúc mức ④ làm việc: 12 frame không đủ, generator nới ra ngoài biên shot.

---

## 9. Đo độ trễ

CLAUDE.md v3 mục *Coding convention*: mỗi tối ưu phải kiểm chứng/đo được.

| Thao tác | Thời gian |
|:---|---:|
| Nạp `shots.parquet` (100.810 shot) — **1 lần/tiến trình** | 1042 ms |
| Nạp `frame_map` của Công Lý — **1 lần/tiến trình** | 1105 ms |
| Nạp `video_info` — **1 lần/tiến trình** | 12 ms |
| **Cấp phát 100 slot — KIS** | **1.31 ms** |
| Cấp phát 100 slot — Q&A | 1.48 ms |
| Cấp phát 100 slot — TRAKE | 2.34 ms |

~2.2 s là chi phí **một lần lúc khởi động**, không phải lúc bấm nộp. Việc chạy mỗi query
là **1–2 ms**. Ngân sách 30s: tầng này chiếm 0.007%.

```
cache _shots: misses=1, hits=39.999 · cùng một object trong RAM
```

> [!NOTE]
> 2.2 s đó phải trả lúc **khởi động server**, không phải lúc người vận hành bấm nút.
> `run_minimal.py` (A6.2-early của Thạch) nên gọi warm sẵn `_shots()` và `n_frames_of()`
> lúc boot.

---

## 10. ⚠️ Phần TREO và phần có thể LỆCH

> Task này làm **trước** tiến độ chung. Bảng dưới là những chỗ đang chạy trên giả định,
> sẽ phải sửa khi người khác giao hàng. **Đọc kỹ trước khi tin kết quả.**

### 10.1. 🔴 CHẶN — chưa nối được vào pipeline

| # | Việc | Chờ ai | Ảnh hưởng |
|:---:|:---|:---|:---|
| 1 | **`search()` trả về KEYFRAME, allocator nhận SHOT.** `BUILD_TASKS` A2.1 giao Thạch *"gom về shot, lấy điểm max mỗi shot"* — chưa làm. `backend/retrieval/search.py:288` đang trả `{keyframe_id, video_id, score}` | **Thạch** | Allocator chạy đúng nhưng **chưa cắm được vào search thật**. G2 (09/08) cần cả ống thông |

Hàm gom `keyframe_id → shot_id` qua `shots.parquet` khoảng 20 dòng. Tôi **không viết** vì
đó là phần A2.1 của Thạch — nhưng nếu 09/08 chưa có thì phải quyết ai làm.

### 10.2. 🟡 CHẠY ĐƯỢC nhưng đang giả định — sẽ phải sửa

| # | Chỗ | Đang giả định gì | Chờ ai | Nếu sai thì sao |
|:---:|:---|:---|:---|:---|
| 2 | `ShotHit.best_keyframe_id` | Tầng search sẽ đưa xuống keyframe điểm cao nhất mỗi shot | **Thạch** | Không có → **mức ① không bao giờ chạy**, frame đầu mỗi shot thành điểm giữa tính ra thay vì frame có bằng chứng. Vẫn ra 100 dòng, nhưng **chất lượng R@1 kém hẳn** |
| 3 | Định dạng `keyframe_id` | Milvus dùng cùng format với `kf_id` của `frame_map` | **Thạch + Công Lý** | `load_frame_map()` của Lý đã trả **cả hai** format (`L21_V001#k0001` và `L21_V001_0001`) nên khả năng cao là khớp. Nhưng chưa có `keyframes.json` thật để xác nhận |
| 4 | `SLOT_BUDGET = [(3,8),(7,5),(10,3),(11,1)]` | Cửa sổ `[s,e]` của BTC vừa phải | **Linh → BTC** | CLAUDE.md v3 mục *Điều CHƯA chốt* liệt đây là thứ BTC phải trả lời. Cửa sổ rộng → nên rải rộng; hẹp → nên đào sâu. **D4.1 (17/08) là task tune bảng này** |
| 5 | `TRAKE_DEFAULT_N = 4` | Đề TRAKE không công bố N | **Linh → BTC** | Sai N → validator bắt được (`trake_n_mismatch`), không phải lỗi im lặng |
| 6 | `SHOT_EDGE_INSET = 0.10` | 10% mỗi đầu là đủ tránh frame chuyển cảnh | tôi | Con số cảm tính, chưa đo. D4.1 tune cùng bảng ngân sách |

### 10.3. 🟠 RỦI RO DỮ LIỆU — đã đo, biên độ nhỏ

| # | Vấn đề | Số thật | Chờ ai | Đánh giá |
|:---:|:---|:---|:---|:---|
| 7 | **Không còn cách nào biết frame nào đã kiểm chứng.** Bản `frame_map` 07/08 **xoá** hai cột `offset_verified` và `frame_idx_status` | `frame_map` từ 14 cột còn 6 | **Công Lý** | Giá trị `frame_idx` vẫn là bản đã bù offset (kiểm: 19.380/177.321 dòng bằng `floor(pts×fps)+1`, nhiều hơn bản cũ 81 dòng → Lý sửa thêm chứ không bớt). Mất **hồ sơ**, không mất **dữ liệu**. Nhưng sau đợt thi, soi một câu trượt sẽ không trả lời được "số này đã so pixel hay đang giả định" |
| 8 | `path` trong `video_info` chết **873/873** | trỏ `data/raw/videos/...` không tồn tại | **Công Lý** | Không ảnh hưởng allocator (không đọc video). Nhưng `scripts/verify_frame_map.py` sẽ gãy |

### 10.4. 🔵 CHỦ Ý ĐỂ SAU

| # | Việc | Khi nào |
|:---:|:---|:---|
| 9 | **TRAKE mới là v1** — xếp hạng theo video + N shot cao điểm nhất. Chưa có DP theo trình tự thời gian (khoảnh khắc 1 phải trước khoảnh khắc 2 về mặt *ngữ nghĩa*, không chỉ về số frame) | CLAUDE.md xếp "TRAKE DP" vào danh sách cắt, có đường quay lại **sau đợt 1** |
| 10 | **`rep_kf_id` đã có (07/08) nhưng allocator CHƯA dùng** | Xem mục 10.5 — đây là phao dự phòng cho rủi ro số 2, nên cân nhắc lại |

---

### 10.5. 🎁 `rep_kf_id` đã có — phao dự phòng cho rủi ro số 2

Bản `shots.parquet` 07/08 có thêm cột `rep_kf_id`. Nó **giải đúng** rủi ro số 2 ở trên.

**Nhắc lại rủi ro số 2:** slot đầu của mỗi shot lấy từ mức ① — frame của keyframe mà
CLIP thực sự chấm điểm cao nhất. Nếu tầng search không đưa `best_keyframe_id` xuống,
mức ① bị bỏ qua và slot đầu rơi xuống mức ② — một điểm rải đều **tính ra**.

Đo xem "điểm tính ra" lệch bao xa so với keyframe thật:

| | frame |
|:---|---:|
| median | **22** |
| p75 | 35 |
| p95 | 58 |
| lệch > 10 frame | **79%** số shot |
| lệch > 30 frame | 32% số shot |

(shot median chỉ dài 69 frame)

Nguy ở chỗ **không có dấu hiệu gì**: vẫn đủ 100 dòng, validator vẫn xanh, file vẫn hợp
lệ — chỉ là R@1 thấp hơn đáng lẽ được mà không ai biết tại sao.

**Chất lượng của `rep_kf_id`:**

```
(cập nhật sau pull 812a555 — Data Factory đã lấp hết NULL)

100.810/100.810 shot có rep_kf_id   ← trước đó còn hổng 6.713
  89.718  rep_source='btc'             → tra qua frame_map
  11.092  own_1fps / video_fallback /  → tra qua keyframes.parquet
          exact_shot_center
       0  không tra được ở đâu cả

rep_kf_id nằm ngoài biên shot của nó: 0/89.718
```

→ Phao này giờ **phủ 100% shot**, không còn lỗ 6,7% như bản sáng.

**Thứ tự ưu tiên đề xuất cho mức ①:**

| | Nguồn | Vì sao xếp ở đó |
|:---:|:---|:---|
| 1 | `best_keyframe_id` từ search | frame thật **và** biết query |
| 2 | `rep_kf_id` của Data Factory | frame thật, nhưng chọn tĩnh — không biết query |
| 3 | điểm rải đều (mức ②) | không phải frame thật |

Hiện tại thiếu (1) là rơi thẳng xuống (3). Có (2) thì đỡ được một bậc.

⚠️ Nếu làm: phải tra **cả hai bảng**. Chỉ tra `frame_map` là hụt 4.379 shot có
`rep_source='own_1fps'` — rep của chúng nằm ở `keyframes.parquet`.

**Chưa làm** — đây là thay đổi thiết kế, không phải sửa lỗi.

---

### 10.6. 🐞 Vấn đề CÒN TRONG CODE

> Rà `allocator.py` + `slot_budget.py` ngày 07/08 tìm được 3 chỗ. **09/08 đã sửa 2** —
> xoá khỏi đây. Chỗ còn lại `BUILD_TASKS` không nhắc tới nên để nguyên.

#### ✅ Đã sửa 09/08 — cả hai đều có căn cứ trong `BUILD_TASKS` D3.1

**1. `allocate()` chặn `total < 1`**

```
allocate(hits,"KIS",total=0)   →  ValueError: total phải >= 1, nhận 0. Lúc thi luôn là 100.
allocate(hits,"KIS",total=-5)  →  ValueError
```

Trước đó trả `[]` **lặng lẽ**. `BUILD_TASKS` D3.1 ghi *"⚠️ KHÔNG BAO GIỜ trả < 100
dòng"* — một biến chưa gán ở tầng trên sẽ thành bài nộp TRẮNG mà không ai biết.

**2. `allocate()` chặn `n_trake < 2`**

```
allocate(hits,"TRAKE",n_trake=1)  →  ValueError: TRAKE phải có ít nhất 2 khoảnh khắc
allocate(hits,"TRAKE",n_trake=0)  →  ValueError
```

Trước đó allocator đẻ ra 100 dòng × 1 frame, rồi chính `_check_shape()` của D0.2 từ chối
(`frame_count`). Hai module cùng một người mà không thống nhất.

> 🐞 **Bắt thêm một bug lúc sửa:** `n = n_trake or TRAKE_DEFAULT_N` nuốt mất số 0 —
> `n_trake=0` bị âm thầm thay bằng 4 thay vì báo lỗi. Đổi sang `is None`. Đúng kiểu
> thay số lặng lẽ mà W0.2 cấm. Đã có test riêng cho ca `n=0`.

**4 test mới** canh hai luật này (`total=0/-5`, `n_trake=0/1`).

#### 🔵 Còn lại — *ngoài phạm vi `BUILD_TASKS`*

`score = NaN` không bị chặn: `sorted(hits, key=score)` với NaN cho thứ tự tuỳ ý → thứ
hạng shot thành ngẫu nhiên. Chưa nổ vì tầng search không sinh NaN, nhưng RRF chia cho 0
thì có thể. `BUILD_TASKS` không nhắc → để lại, chờ Thạch chốt hợp đồng của `score`.

---

### 10.7. 🔻 Hậu quả của lần pull 07/08 (chiều)

> Pull về `812a555`. Không ai đụng file của tôi (`backend/export/`, `backend/slot/`,
> `data/config/submit_format.py`, `slot_budget.py`, `tests/` — diff rỗng), nhưng **ba
> thứ bên ngoài đập vào** — B và C đã xử lý xong, A và D vẫn chờ người khác.

#### 🔴 A. `backend/indexing/frame_map.py` gãy → chặn mức ① của allocator

Commit `6f53aaa` (*"revert: Xóa sạch thư mục preprocessing khỏi git tracking"*, Công Lý)
xoá `preprocessing/common/frame_map.py`. Nhưng `backend/indexing/frame_map.py:15` vẫn:

```python
from preprocessing.common.frame_map import load_frame_map as load_frame_map_df
→ ModuleNotFoundError: No module named 'preprocessing.common.frame_map'
```

**3 test đỏ** (`tests/test_allocator.py`). Kéo theo `/submit` của Thạch
(`backend/api/main.py:142`) cũng chết — nay là lý do thứ hai, ngoài 11 điểm lệch cũ.

⚠️ **Nguy hơn cái đỏ: demo vẫn xanh.**

```
KHÔNG có best_keyframe_id (giống --demo)  →  100 dòng, "HỢP LỆ" ✅
CÓ  best_keyframe_id (đường chạy lúc thi) →  🔴 ModuleNotFoundError
```

`python -m backend.slot --demo` không truyền `keyframe_id` nên không chạm hàm đó. Nhìn
CLI thì tưởng lành; chỉ nổ đúng lúc Thạch nối search vào — tức lúc thi.

**File của Công Lý, không tự sửa.** Fix đã kiểm: wrapper đó vốn chỉ để đổi tên
`frame_idx_corrected` → `frame_idx`, mà parquet mới đã có sẵn `frame_idx`, nên bỏ hẳn
phụ thuộc `preprocessing` là xong — chạy thử ra đúng **354.642 key**, giữ cả hai định
dạng `#k` và `_`.

#### ✅ B. `backend/requirements.txt` — **đã khôi phục 07/08**

Commit `5784ff8` gỡ 3 gói tôi thêm ở `f882a62` (`pandas` · `pyarrow` · `pytest`). Đã
thêm lại kèm ghi chú chống gỡ nhầm. Thiếu chúng thì máy clone mới không chạy được
`backend/export/` lẫn `backend/slot/`.

#### ✅ C. Trích dẫn CLAUDE.md v4 → v3 — **đã sửa hết 09/08**

Commit `2932ac4` đưa CLAUDE.md về v3 (108 dòng), đánh số khác hẳn v4. Đã sửa **11 chỗ**:

| Trích dẫn cũ (v4) | Sửa thành | Vì sao |
|:---|:---|:---|
| `bất biến 5` (không đặt ngưỡng cứng) | **`bất biến 6`** | v3 #5 là *frame_id = frame index trong video*, lệch một bậc |
| `bất biến 8` (assert `.parquet` lúc load) | **bỏ hẳn** | **Luật này chỉ có ở v4.** `_doc_cot()` vẫn giữ vì nó cứu đúng sự cố đổi schema, nhưng không được trích một điều luật không tồn tại |
| `mục 5` · `5.2` · `5.3` (dạng bài, cách chấm) | **tài liệu BTC** | v3 không mô tả dạng bài |
| `mục 6 quy tắc 1` · `mục 7` (đủ 100 slot, frame_id tự do) | **`BUILD_TASKS` D3.1** | luật nằm ở đó, đã kiểm còn nguyên |
| `mục 11` · `mục 14.7` | **tên mục v3** (*Điều CHƯA chốt*, *Coding convention*) | v3 dùng `##` không đánh số |
| `mục 2` (kiến trúc) trong `backend/slot/__init__.py` | **`BUILD_TASKS` D3.1** | |

> [!IMPORTANT]
> **Các LUẬT không đổi** — chúng nằm ở `BUILD_TASKS.md` (đã kiểm: D3.1 vẫn có
> *"XEN KẼ theo shot"* và *"KHÔNG BAO GIỜ trả < 100 dòng"*) và tài liệu BTC. Chỉ địa chỉ
> trích dẫn hỏng, không phải yêu cầu.

#### 🔵 D. CLAUDE.md v3 vẫn ghi bug `frame_id` như giả định hiện hành

```
| Format submit | data/config/submit_format.py | frame_id = hậu tố keyframe_id |
```

Đúng cái W0.2 đã xoá khỏi code. Tôi từng báo Thạch dòng này ở bản v4; revert về v3 thì
nó quay lại. Ai đọc CLAUDE.md lần đầu sẽ hiểu ngược hoàn toàn.

---

## 11. 🧪 Code chỉ để thử nghiệm — bỏ khi vào thi

> Những thứ dưới đây **không thuộc đường chạy lúc thi**. Liệt kê ra để sau này không ai
> tưởng nhầm là code sản xuất.

| # | Chỗ | Là gì | Xử lý |
|:---:|:---|:---|:---|
| 1 | `allocator.main()` + `backend/slot/__main__.py` | CLI `--demo`: dựng `ShotHit` **giả lập** từ `shots.parquet` (bốc 3 shot mỗi video) rồi cấp phát | **Giữ tới G2**, tiện xem tận mắt 100 dòng mà không cần Milvus/ES. Sau đó xoá hoặc để nguyên — nó không nằm trong đường chạy |
| 2 | `allocator.py` tham số `--shots` | Số shot ứng viên giả lập | Chỉ có ở CLI demo |
| 3 | `exporter._demo_subs()` + `--demo` | Sinh bài nộp giả từ video thật (D0.2) | Như trên |
| 4 | `write_submissions(..., validate=False)` | Đường thoát để ghi dữ liệu hỏng ra soi | ⚠️ **TUYỆT ĐỐI không dùng ngày nộp.** Mặc định là `True`; nếu ai đó đặt `False` thì bài nộp sai vẫn ra file trông hợp lệ |
| 5 | `csv_header_v0` · `json_v0` | Hai trong ba format là **phỏng đoán dự phòng** | BTC chốt format → **xoá hai cái không dùng**, giữ đúng một. Để lại ba cái là để lại ba cách nộp sai |
| 6 | `SUBMIT_FORMAT = "csv_v0"` | Đang chọn đại một trong ba | Sửa đúng dòng này khi BTC trả lời |
| 7 | `allocate(total=...)` | Tham số cho phép khác 100 | Chỉ dùng để test. Lúc thi **luôn 100** (`BUILD_TASKS` D3.1). Từ 09/08 `total < 1` bị raise |
| 8 | `allocate(table=...)` | Cho truyền bảng ngân sách khác | Dùng ở D4.1 để tune. Lúc thi để mặc định |
| 9 | `tests/conftest.py`: `hits_of()`, `build_sub()`, `shots_of()` | Dựng dữ liệu test | Nằm trong `tests/`, không bao giờ chạy lúc thi |

**Điểm 4 và 5 là hai chỗ dễ gây tai nạn nhất** — cả hai đều tạo ra file nộp *trông* hợp
lệ mà sai.

---

## 12. Đối chiếu với yêu cầu

### 12.1. `BUILD_TASKS.md` — D3.1

| Yêu cầu | |
|:---|:---:|
| `backend/slot/allocator.py`, nhận top-K shot + `query_type`, trả đúng 100 dòng | ✅ |
| Bảng khởi điểm `3×8 + 7×5 + 10×3 + 11×1 = 100`, **để trong config** | ✅ |
| ⚠️ XEN KẼ theo shot, KHÔNG gom | ✅ 5 slot đầu = 5 shot |
| `frame_idx` không cần là keyframe đã index | ✅ mức ②③④ phát frame bất kỳ |
| Frame ĐẦU TIÊN mỗi shot = keyframe điểm cao nhất | ✅ mức ①, có test |
| Frame tiếp theo rải đều, **thụt 10% mỗi đầu**, ép `int`, khử trùng | ✅ |
| Slot allocator chịu trách nhiệm cấp `frame_idx` THẬT | ✅ qua `load_frame_map()` của Công Lý |
| ⚠️ **KHÔNG BAO GIỜ trả < 100 dòng**, kể cả khi chỉ có 3 shot | ✅ mức ④; test tới ca 1 shot × 12 frame |
| Unit test cả ba dạng bài, gồm ca biên | ✅ 33 test |

### 12.2. `CLAUDE.md`

| Yêu cầu | |
|:---|:---:|
| `BUILD_TASKS` D3.1 — luôn nộp đủ 100 slot | ✅ |
| Mục 6 quy tắc 3 — thứ tự XEN KẼ theo shot | ✅ |
| Mục 7 — `frame_id` không cần là keyframe đã index | ✅ |
| Bất biến 5 — **không đặt ngưỡng điểm cứng** | ✅ `score` chỉ dùng để sắp xếp |
| Mục 14.7 — báo độ trễ đo được | ✅ mục 9 |
| Mục 14.9 — không hardcode, đọc từ config | ✅ `slot_budget.py` |
| Mục 12.8 — mọi `.parquet` assert lúc load | ✅ thiếu file → báo rõ tên file và ai phải giao |

### 12.3. Chỗ lệch so với chữ trong tài liệu

| Chỗ | Lý do |
|:---|:---|
| `ShotHit` chỉ có `shot_id` + `score` + `best_keyframe_id`, **không có `start_frame`/`end_frame`** | Biên shot tra thẳng từ `shots.parquet`. Bắt tầng search truyền xuống là tạo nguồn sự thật thứ hai |
| Không dùng `rep_kf_id` | Spec ghi frame đầu là keyframe **điểm cao nhất từ search** — thứ đó phụ thuộc query nên `rep_kf_id` không thay thế được. Nhưng làm **dự phòng** thì được: mục 10.5 |

---

## 13. Kết luận

| Hạng mục | Trạng thái |
|:---|:---|
| Luôn đủ 100 dòng, mọi ca biên | ✅ tới ca 1 shot × 12 frame |
| Xen kẽ theo shot | ✅ 5 slot đầu = 5 shot, phá code thì 20 test đỏ |
| `frame_idx` thật qua `frame_map` của Công Lý | ✅ không tự đọc parquet, một nguồn sự thật |
| Ba dạng bài | ✅ KIS + Q&A đầy đủ · TRAKE v1 |
| Chiến thuật tách khỏi cơ chế | ✅ tune = sửa một dòng số |
| Nối vào validator D0.2 | ✅ output nộp được ngay |
| Độ trễ | ✅ 1–2 ms mỗi query |
| **Nối vào search thật** | 🔴 **chờ A2.1 của Thạch** |
| Chốt an toàn khi Data Factory đổi schema | ✅ `_doc_cot()` + 2 test (thêm 07/08) |
| `n_trake=1` và `total=0` bị chặn ở cửa vào | ✅ Sửa 09/08 + 4 test — mục 10.6 |
| Dùng `rep_kf_id` làm dự phòng cho mức ① | 🔒 **Kẹt** — tra keyframe đi qua module đang gãy (mục 10.7.A) |
| `backend/indexing/frame_map.py` chạy được | 🔴 **GÃY sau pull** — mục 10.7.A, chờ Công Lý |
| Trích dẫn CLAUDE.md khớp bản v3 | ✅ Sửa 11 chỗ (09/08) — mục 10.7.C |

### Danh sách file được tạo / sửa

| File | Vai trò | Dòng |
|:---|:---|---:|
| `backend/slot/allocator.py` | Cơ chế cấp phát — tạo mới | 400 |
| `backend/slot/__init__.py` | Re-export `allocate`, `ShotHit` | 7 |
| `backend/slot/__main__.py` | `python -m backend.slot --demo` | 5 |
| `data/config/slot_budget.py` | Chiến thuật — tạo mới | 78 |
| `tests/test_allocator.py` | 33 test trên shot thật | 274 |
| `tests/conftest.py` | Thêm `_shots_df()`, `shots_of()`, `hits_of()` | 178 |

**Dọn kèm:** `backend/export.py` → package `backend/export/`
(`__init__.py` + `__main__.py` + `exporter.py`), theo đúng kiểu `backend/llm/` của Thạch.
Đường import `backend.export` **không đổi** nên không file nào phải sửa theo.

### Cách chạy / kiểm

```powershell
python -m pytest -q      # 96 passed, 3 failed  ← 3 đỏ do mục 10.7.A (frame_map của Công Lý)
python -m backend.slot --demo --task KIS
python -m backend.slot --demo --task TRAKE
python -m backend.export --demo              # D0.2, vẫn chạy như cũ
```

### Task tiếp theo

**D4.1 — Chỉnh slot theo dữ liệu** (17→19/08): chạy dev set, thử vài bảng `SLOT_BUDGET`,
ghi vào `reports/slot_tuning.md`. `BUILD_TASKS` gọi đây là *"điểm miễn phí, không cần
model mạnh hơn"*.

Nhưng trước đó, thứ chặn thật là **A2.1 của Thạch** (mục 10.1) — không có nó thì G2
(09/08) không có ống thông.
