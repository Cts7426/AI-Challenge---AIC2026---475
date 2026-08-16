# CLAUDE.md — HCMAIC 2026 Multimedia Retrieval System

> **v4 · 01/08/2026** — cập nhật theo lịch thi 3 đợt.
> ⚠️ **Thay đổi lớn so với v3: sơ tuyển là THI TRỰC TIẾP, không phải nộp theo lô.**
> File ngữ cảnh cho Claude Code (Fable 5). Đọc TRƯỚC mọi task.
> Quy ước: **giải thích bằng tiếng Việt**, code (collection, field, hàm, biến) **giữ tiếng Anh**.

---

## 1. Bối cảnh & ràng buộc thời gian

Hệ thống truy xuất khoảnh khắc từ kho video (tin tức / lịch sử / bóng đá / đời sống)
cho **AI Challenge HCMC 2026**. Thể thức theo VBS/LSC.

**Đây là dự án học tập của sinh viên năm 2 ngành AI.** Người vận hành hệ thống lúc thi
chính là người viết ra nó — **hiểu được** quan trọng hơn **chạy được**.

### 📅 Sơ tuyển: BA ĐỢT THI TRỰC TIẾP

| Đợt | Ngày | Giờ |
|---|---|---|
| **Đợt 1** | **21/08/2026** | 19:30 – 22:30 |
| **Đợt 2** | **28/08/2026** | 19:30 – 22:30 |
| **Đợt 3** | **04/09/2026** | 19:30 – 22:30 |

**Mỗi buổi 3 giờ, thi trực tiếp.** Không phải nộp file offline.

> ⚠️ **Điều này đảo ngược giả định ở v3.** v3 ghi *"UI không cần nhanh"* — **SAI, đã bỏ.**
> R@k vẫn không trừ theo thời gian, nhưng **thông lượng** mới là thứ giết mình:
> không phải "chậm thì mất điểm", mà là **"chậm thì không kịp trả lời hết câu"**.
> Câu nào không kịp làm = 0 điểm, dù hệ thống giỏi tới đâu.

### Ba đợt = được thi thử hai lần với dữ liệu thật

Đây là lợi thế lớn nhất cho nhóm nhỏ. Đợt 1 **không phải** "hỏng là hết".

**Mục tiêu đợt 1 không phải điểm cao nhất — mà là chạy trơn và HỌC ĐƯỢC NHIỀU NHẤT.**
Sau mỗi đợt có 7 ngày để sửa. Những thứ trong danh sách cắt (SigLIP, caption VLM,
TRAKE DP) có đường quay lại ở đợt 2–3, không mất hẳn.

**Bắt buộc: post-mortem trong 24h sau mỗi đợt** — câu nào trượt, trượt vì retrieval hay
vì hết giờ, người thao tác kẹt ở đâu. Chốt đúng 3 việc cho tuần kế tiếp.

### ❓ Chưa rõ — hỏi BTC gấp
1. **Mỗi đội thi cả 3 đợt hay chỉ 1 đợt?** (800+ đội → rất có thể chia đợt.
   Nếu chỉ thi 1 đợt thì toàn bộ lợi thế "thi thử" biến mất, chiến lược đổi lại.)
2. **Điểm 3 đợt: cộng dồn / trung bình / lấy cao nhất?**
3. **Bao nhiêu câu mỗi buổi?** ← không có số này thì không tính được ngân sách thời gian
4. **Thi từ xa hay tới địa điểm? Có được dùng internet/API không?**
5. Đợt 2–3 có dùng batch dữ liệu mới không?

---

## 2. ⏱️ NGÂN SÁCH THỜI GIAN — ràng buộc thiết kế mới

Giả định 20–30 câu / 180 phút → **6–9 phút mỗi câu**, gồm cả đọc đề, chạy, duyệt, nộp.

**Phân bổ mục tiêu cho mỗi câu (~6 phút):**

| Giai đoạn                            | Ngân sách                 |
| --------------------------------------| ---------------------------|
| Đọc đề + gõ query                    | 30–60s                    |
| **Pipeline chạy xong, hiện kết quả** | **≤ 30s** ← mục tiêu cứng |
| Người duyệt + sửa thứ tự top         | 60–120s                   |
| Nộp                                  | 10s                       |
| Đệm / thử lại lần 2                  | phần còn lại              |

### Hai luật thiết kế rút ra

**Luật 1 — Con người KHÔNG chọn 100 slot.**
Không ai chọn tay 100 đáp án trong 6 phút. **Máy sinh đủ 100, người chỉ sửa phần đầu
danh sách.** R@1 + R@5 = 40% điểm → 30 giây người thao tác dành xác nhận top-5 là 30
giây có giá trị nhất cả câu.

**Luật 2 — Độ trễ ≤ 30s từ lúc gõ query tới lúc có kết quả trên màn hình.**
Vượt quá → chuyển sang chạy offline hoặc cắt.
- ⛔ **KHÔNG gọi VLM trong đường chạy online của KIS.**
- Q&A buộc phải có VLM → là dạng câu tốn thời gian nhất, tính ngân sách riêng, và
  người thao tác nên để dành câu Q&A làm sau nếu buổi thi tính giờ chung.

**Kịch bản sự cố (bắt buộc có):** hệ thống treo giữa buổi thi thì làm gì?
`run_minimal.py` phải **bấm là chạy được ngay**, chỉ CLIP + BM25 + slot allocator.

---

## 3. Kiến trúc

```
   (Tầng 3)   AGENT LAYER (KISC + track tự động)   ← CHUNG KẾT, KHÔNG ĐỤNG
                          │
   (Tầng 2)   RETRIEVAL: query → llm() dịch/mở rộng → search song song
              (vector + text) → RRF → rerank → TOP 100 → người sửa top → nộp
                          │
   (Tầng 1)   INDEXING: CLIP features · Objects · Metadata · OCR · ASR
                        + frame_map (keyframe → frame_idx)
```

### `llm()` adapter — nguyên tắc SỐNG CÒN
Mọi lần gọi LLM/VLM đi qua **một hàm duy nhất**
`llm(prompt, images=None, json_schema=None, n=1, temperature=0)` trong `backend/llm/`.
Có retry, cache theo hash prompt, đếm chi phí.
Đổi backend API ↔ local bằng **một dòng config**.
**KHÔNG** import SDK nhà cung cấp ở bất kỳ chỗ nào khác.

> ⚠️ Câu hỏi #4 với BTC (có được dùng internet khi thi không) giờ là **gấp**, không còn
> là chuyện của chung kết. Nếu cấm → phải có model local sẵn sàng trước 21/8.

---

## 4. Dữ liệu BTC

> ⚠️ **Dữ liệu thi chính thức là VIDEO.** Keyframes / Objects / CLIP features /
> Metadata chỉ là tài liệu hỗ trợ → ta ĐƯỢC PHÉP tự trích frame và tự encode.

| Nguồn           | Cấu trúc                                                        | Ghi chú                     |
| -----------------| -----------------------------------------------------------------| -----------------------------|
| `Videos`        | `L01_V001.mp4`                                                  | nguồn chuẩn                 |
| `Keyframes`     | `L01_V001/0000.jpg`, `0001.jpg`...                              | I-frame, thưa               |
| `Objects`       | `L01_V001/0000.json` — Faster R-CNN, OpenImages V4              | tối đa 100 obj / 600 loại   |
| `CLIP features` | `.npy`, **`clip-ViT-B-32`, 512 chiều**                          | **lõi ở sơ tuyển**          |
| `Metadata`      | `L01_V001.json` (title, description, keywords, publish_date...) | ⚠️ **một số video KHÔNG có** |

- Batch 1 = dữ liệu AIC 2025. **Batch 2 sẽ có sau** → job phải **nạp tăng dần**.
- Cách gói `.npy` (một file cho tất cả hay một file mỗi video) **kiểm lại khi tải về**.

### ⚠️ frame_map — cấu trúc dữ liệu LÕI

**Tên file keyframe ≠ frame_id nộp bài.**
`L01_V001/0007.jpg` → `0007` là **số thứ tự keyframe**; BTC chấm theo **frame index
trong video** (đáp án kiểu ∈ `[500, 510]`).

Tìm file `map-keyframes` khi tải data (mùa trước: CSV `n`, `pts_time`, `fps`, `frame_idx`).

**Xác thực bắt buộc:** 20 keyframe ngẫu nhiên → dùng ánh xạ trích frame từ video gốc
bằng ffmpeg → so pixel. Lệch > 1 frame → **chặn toàn bộ tiến độ**.

```bash
ffmpeg -i video.mp4 -vf "select=eq(n\,1234)" -vsync 0 -frames:v 1 out.png
```

⚠️ **fps phải ở dạng phân số** (`fps_num`/`fps_den`). 29.97 = 30000/1001; làm tròn
thành 30 thì sau 10 phút lệch ~18 frame, đủ trượt mọi cửa sổ đáp án.

**Đây là lỗi duy nhất làm điểm bằng 0 mà không báo lỗi.**

---

## 5. Ba dạng bài SƠ TUYỂN

> Sơ tuyển **KHÔNG có AVS, KHÔNG có KISC**. Code AVS: giữ lại, **ngừng đầu tư**.

**5.1 Textual KIS** — nộp `<video_id>, <frame_id>`
Đúng khi: khớp video **VÀ** `frame_id ∈ [s, e]`

**5.2 Q&A** — nộp `<video_id>, <frame_id>, <answer>`
Đúng khi: khớp video **VÀ** `frame_id ∈ [s, e]` **VÀ** answer khớp ngữ nghĩa (VI hoặc EN)
- ⚠️ **Hai cửa tử độc lập:** answer đúng + frame sai = 0; frame đúng + answer sai = 0
- **Định tuyến bằng chứng:** tên/chức danh → OCR · lời nói → ASR ·
  **đếm → detector, KHÔNG hỏi VLM** (VLM đếm rất tệ và tự tin sai) · số/tỉ số → OCR
- Answer **ngắn nhất mà vẫn đủ**: `"5"` không phải `"khoảng 5 người"`
- ⏱️ Dạng tốn thời gian nhất trong buổi thi — tính ngân sách riêng

**5.3 TRAKE** — nộp `<video_id>, <frame_id₁>, ..., <frame_idₙ>`
- Hai giai đoạn: (1) chắc **video** → (2) định vị **N khoảnh khắc**
- **Sai video = 0 tuyệt đối.** Đúng video → điểm = tỉ lệ khoảnh khắc khớp (3/4 → 0.75)
- ⚠️ "Semantic keyframe" ≠ I-frame; cửa sổ **dưới 10 frame**
- Có điểm từng phần → **luôn nộp đủ N**, đoán còn hơn bỏ trống

---

## 6. Cách chấm

**Tối đa 100 câu trả lời mỗi truy vấn.**
`Final = trung bình(R@1, R@5, R@20, R@50, R@100)` · `R@k` = R-Score cao nhất trong k đầu

| Hạng của câu đúng | 1 | 2–5 | 6–20 | 21–50 | 51–100 | >100 |
|---|---|---|---|---|---|---|
| **Điểm** | **1.00** | 0.80 | 0.60 | 0.40 | 0.20 | 0 |

### Ba quy tắc bắt buộc

**1. LUÔN nộp đủ 100 slot.** Không có hình phạt cho câu sai. Bỏ trống ô 51–100 là vứt
điểm miễn phí. Slot allocator **KHÔNG BAO GIỜ** trả < 100 dòng.
> ⚠️ Quy tắc *"nộp dư bị trừ"* chỉ đúng cho AVS — **AVS không có ở sơ tuyển**.

**2. Thứ hạng là tất cả.** Hạng 2 → hạng 1 = **+0.20**, ngang giá trị với cứu một câu
từ trượt lên hạng 51.

**3. Thứ tự nộp XEN KẼ theo shot, không gom.** R@1 + R@5 = 40% điểm. 8 slot đầu cùng
một shot mà shot đó sai → mất trắng cả R@1 lẫn R@5.

---

## 7. ⚠️ frame_id KHÔNG cần là keyframe đã index

Đáp án nộp là cặp **số nguyên** `(video_id, frame_id)`, `frame_id ∈ [0, n_frames)`.
**Không cần có ảnh, không cần được index, không cần embedding.**

- Keyframe chỉ để **tìm đúng shot** → mật độ **1 fps là đủ**
- Slot allocator **phát ra frame_idx bất kỳ** trong shot thắng cuộc
- **Độ sâu của slot là miễn phí**

Cắt 4× chi phí embedding mà không mất điểm nào.

---

## 8. Tech stack

**Giữ nguyên thứ đang có. Không rewrite dưới áp lực thời gian.**

| Vai trò | Dùng | Ghi chú |
|---|---|---|
| Vector | **Milvus** (đã có loader) | xem điều kiện chuyển bên dưới |
| Text | **Elasticsearch** (đã có loader) | |
| Backend | Python + FastAPI | |
| **UI thi đấu** | **Streamlit** | ⚠️ **điều hướng bàn phím, không click chuột** |
| OCR | PaddleOCR / VietOCR + `llm()` sửa dấu | giữ cả `text_raw` và `text_clean` |
| ASR | PhoWhisper / faster-whisper | **tách audio trước khi upload** |
| Fusion | **RRF**, k=60 | không cần tune trọng số |
| Trích frame | `ffmpeg` | |

### 🔀 Điều kiện chuyển sang FAISS + bm25s
`docker compose up` **không ổn định trong 2 ngày đầu** trên máy 16GB (restart loop,
RAM > 6GB, ES chết âm thầm) → chuyển. Loader mỏng nên migration ~nửa ngày.

```yaml
environment:
  - "ES_JAVA_OPTS=-Xms1g -Xmx1g"
  - discovery.type=single-node
```

---

## 9. Ngân sách GPU

| Job | Ước lượng | Khi nào |
|---|---|---|
| CLIP B/32 (BTC cấp) | **0h** | W1 |
| ASR | 40–70h | W2 |
| OCR (đã lọc text-region) | 15–25h | W2 |
| Caption VLM `rep_kf` | 60–80h | **sau đợt 1** |
| SigLIP re-encode | 40–60h | **sau đợt 1** |

- Kaggle **cấm một người tạo nhiều tài khoản** — mỗi người dùng tài khoản của mình
- Chia việc bằng `hash(video_id) % 5` — xác định, không trùng
- Mọi job **checkpoint + resume** (phiên tự tắt sau 9–12h), ghi `manifest.json`
- **Tải kết quả về ngay sau mỗi lô**
- Sao lưu `derived/` ở nơi thứ hai — video tải lại được, dữ liệu dẫn xuất thì không

---

## 10. Cấu trúc thư mục

```
/
├── CLAUDE.md · BUILD_TASKS.md · REVIEW_GATES.md
├── docker-compose.yml · config.yaml
├── backend/
│   ├── indexing/     # clip, objects, metadata, ocr, asr, frame_map
│   ├── retrieval/    # search + RRF + rerank + top-100
│   ├── llm/          # adapter — điểm tháo lắp duy nhất
│   ├── tasks/        # kis.py, qa.py, trake.py
│   ├── slot/         # allocator.py
│   ├── agent/        # CHUNG KẾT, KHÔNG ĐỤNG
│   └── api/
├── frontend/         # UI thi đấu (Streamlit)
├── preprocessing/    # ⚠️ đang gõ sai là "preprocessinga" → ĐỔI TÊN
├── tests/            # ⚠️ CÒN THIẾU
└── data/
    ├── config/       # clip_model.py, submit_format.py, search_weights.py
    └── sample/
```

### 🔧 Nợ kỹ thuật — trả trong W0–W1
1. **Đổi tên `preprocessinga` → `preprocessing`**
2. **Xoá bug frame_id khỏi `submit_format.py`** — tầng format không được tự suy ra gì;
   slot allocator cấp `frame_idx` thật (chi tiết ở `BUILD_TASKS.md` W0.2)
3. **`/health` thành deep check** — ping thật Milvus + ES
4. **Chuyển repo ra khỏi OneDrive** — dataset về sẽ xung đột sync, hỏng Docker volume
5. **Thêm `tests/`** — tối thiểu: vector sau index có norm ≈ 1

---

## 11. Đã chốt / Chưa chốt

**✅ ĐÃ CHỐT:**
- Ngày thi: **21/08 · 28/08 · 04/09**, mỗi buổi **19:30–22:30**, **thi trực tiếp**
- Model CLIP: `clip-ViT-B-32`, 512 chiều
- Format nộp: `<video_id>, <frame_id>` (+ `answer` Q&A, nhiều frame TRAKE)
- `frame_id` = **frame index trong video**

**❓ CHƯA CHỐT — để trong `data/config/` kèm `# TODO: BTC`:**
- 🔴 Mỗi đội thi cả 3 đợt hay 1 đợt · điểm 3 đợt tính thế nào
- 🔴 **Số câu mỗi buổi** — quyết định ngân sách thời gian mỗi câu
- 🔴 **Thi ở đâu, có internet không** — quyết định `llm()` chạy API hay local
- 🔴 **Độ rộng cửa sổ `[s,e]` của KIS** — quyết định slot nghiêng *sâu* hay *rộng*.
  Chênh lệch giữa hai giả định này lớn hơn mọi cải tiến model.
- Định dạng file cụ thể · TRAKE có biết trước N không · batch 2 khi nào

Task đụng thứ chưa chốt → tạo config + `# TODO: BTC`, dùng giá trị giả định hợp lý,
**ĐỪNG chặn tiến độ**.

---

## 12. Bất biến kỹ thuật (vi phạm → lỗi IM LẶNG, không crash)

1. **Chuẩn hóa L2 mọi vector** trước index và trước query. Metric khớp: đã normalize →
   inner product, **không** dùng L2 rồi diễn giải như cosine.
2. **Kiểm chứng không gian vector:** encode lại keyframe BTC đã có feature, so cosine
   → **phải ≈ 1.0**. Ra ~0 → sai model → **dừng ngay**.
3. **`keyframe_id` là khóa join** duy nhất giữa vector ↔ text ↔ `frame_map`.
4. **Giới hạn 77 token của CLIP:** mở rộng query = **nhiều câu ngắn, encode riêng, hợp
   nhất**. Kiểm độ dài **bằng code**.
5. **Đừng đặt ngưỡng điểm cứng.** Cosine CLIP thực tế chỉ quanh 0.2–0.3 (case study
   BTC: 0.233 / 0.251 / 0.224). `if score > 0.8` lọc sạch kết quả đúng.
6. **Prompt mở rộng phải cấm LLM thêm chi tiết** không có trong query gốc.
7. **Log thứ hạng từng nhánh** trong RRF. Không có thì phân tích lỗi thành đoán mò.
8. **Mọi `.npy`/`.faiss`/`.parquet` đi kèm `.meta.json`** và **assert lúc load**.
9. **VLM chỉ chạy offline**, không đặt trong đường chạy online (trừ Q&A).
10. ⏱️ **Mọi thay đổi phải đo lại độ trễ.** Thêm tính năng làm pipeline vượt 30s là
    thêm tính năng làm mất điểm.

---

## 13. Ai sở hữu gì

| Người | Sở hữu | Không đụng |
|---|---|---|
| **Thạch** — Retrieval Core, Tech Lead | vector index, RRF, search API, orchestrator, `CLAUDE.md`, schema. **Quyền phủ quyết schema.** | UI, dev set |
| **Công Lý** — Data Factory **+ UI thi đấu** ⬆️ | tải data, audit, `frame_map`, shot, keyframe, ASR, OCR, **UI điều hướng bàn phím** | retrieval, LLM |
| **Thi** — Query & Answer | `llm()`, hiểu truy vấn, Q&A, TRAKE | hạ tầng dữ liệu |
| **Minh Hoàng** — Tooling | `export.py` + `submit_format.py` + validator, slot allocator, `eval.py`, batch runner | model, prompt |
| **Quang Linh** — Operator **có bấm giờ** ⬆️ | quan hệ BTC, **nội dung** dev set, vận hành job Kaggle, **luyện thao tác 6 phút/câu**, bảng điểm | code pipeline |

⬆️ = vai trò được nâng ưu tiên sau khi biết sơ tuyển là thi trực tiếp.

**Backup:** Thạch↔Thi · Công Lý↔Minh Hoàng · **Linh←Thạch (operator dự bị)**

---

## 14. Nguyên tắc làm việc cho AI (Fable 5)

1. **Giải thích lý do** mỗi đoạn code — ngắn gọn, tiếng Việt.
2. Làm **từng task nhỏ**, chạy được rồi mới sang task sau.
3. Giữ **`llm()` tháo lắp được**. Không gọi API ngoài `backend/llm/`.
4. **Ưu tiên code đơn giản, dễ đọc hơn là "thông minh".** Người vận hành lúc thi phải
   hiểu được mọi phần. Chỉ tối ưu khi đã **đo** được chỗ chậm.
5. **Hỏi trước khi:** cài dependency nặng, đổi kiến trúc, hardcode thứ ở mục 11.
6. Code đụng tới vector → **kèm phép kiểm chứng chạy được**.
7. Code đụng tới đường chạy online → **báo độ trễ đo được**, đối chiếu ngân sách 30s.
8. Sau mỗi task: nói rõ **cách chạy/test** và **task tiếp theo**.
9. **Không hardcode.** Model name, ngưỡng, trọng số, đường dẫn đọc từ `config.yaml`.