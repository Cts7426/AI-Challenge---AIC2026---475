# CLAUDE.md — HCMAIC 2026 Multimedia Retrieval System

> File ngữ cảnh cho Claude Code (Fable 5). Đọc file này TRƯỚC mọi task.
> Quy ước: **giải thích bằng tiếng Việt**, nhưng mọi thứ trở thành code
> (tên collection, field, hàm, biến) **giữ tiếng Anh**.

---

## 1. Mục tiêu

Xây một hệ thống truy xuất khoảnh khắc từ kho video lớn (~1000 giờ, tin tức /
lịch sử / bóng đá / đời sống) cho cuộc thi **AI Challenge HCMC 2026**. Thể thức
theo VBS/LSC: người dùng mô tả một khoảnh khắc, hệ thống tìm đúng keyframe.

**Chấm điểm:** có **trừ theo thời gian** (tốc độ quan trọng) và **UI đẹp được
cộng điểm**. Vòng sơ tuyển online (tháng 8), chung kết onsite (12–26/9).

---

## 2. Kiến trúc (BẮT BUỘC tuân theo)

Hệ thống chia làm 3 tầng. **Search engine là nền, Agent là lớp mỏng bọc trên.**

```
                 ┌─────────────────────────────────────┐
   (Tầng 3)      │  AGENT LAYER  (KISC + track tự động) │  ← làm SAU
                 │  gọi search engine bên dưới làm tool │
                 └───────────────┬─────────────────────┘
                                 │
   (Tầng 2)      ┌───────────────▼─────────────────────┐
   RETRIEVAL     │ Query → llm() dịch/mở rộng → search  │
                 │ song song (vector + text) → fuse →   │
                 │ re-rank → UI hiển thị → người chọn → │
                 │ submit                               │
                 └───────────────┬─────────────────────┘
                                 │
   (Tầng 1)      ┌───────────────▼─────────────────────┐
   INDEXING      │ Milvus  ← CLIP features (BTC cấp)    │
                 │ Elasticsearch ← Objects, Metadata,  │
                 │                 OCR, ASR             │
                 └─────────────────────────────────────┘
```

### `llm()` adapter — nguyên tắc SỐNG CÒN
Mọi lần gọi LLM (dịch query, mở rộng, não agent) phải đi qua **một hàm duy nhất**
`llm(prompt) -> str` trong `backend/llm/`. Hàm này có thể trỏ tới:
- **API** (`claude-fable-5`) khi vòng thi cho internet;
- **model local** (Qwen 2.5 3B/7B hoặc Llama 3.2 3B quantize) khi cấm internet.

**KHÔNG** được gọi thẳng API ở bất kỳ chỗ nào khác. Đổi backend chỉ sửa 1 file.
(Máy dev có 16GB RAM → model local phải là bản quantize nhỏ.)

---

## 3. Dữ liệu BTC cung cấp (schema cố định)

| Nguồn | Nội dung | Vào đâu |
|-------|----------|---------|
| `Videos` | File video gốc | lấy thumbnail/xem lại |
| `Keyframes` | I-frame, kèm vị trí (frame index + timestamp ms) | Milvus (id) + hiển thị ảnh |
| `Objects` | FasterRCNN + InceptionResNetV2, OpenImages V4, tối đa 100 object / 600 loại mỗi frame | Elasticsearch |
| `CLIP Features` | Vector CLIP tính sẵn cho từng keyframe | **Milvus** |
| `Metadata` | Từ YouTube: `title`, `description`, `keywords`, `publish_date`, `length`, `author`, `channel_id`, `watch_url`... | Elasticsearch (full-text) |

**Tự làm thêm (BTC KHÔNG cấp — đây là lợi thế cạnh tranh):**
- **OCR** tiếng Việt trên keyframe (chữ chạy dưới màn, tên, ngày, tỉ số bóng đá)
- **ASR** tiếng Việt trên audio (bình luận, lời thoại tài liệu)
→ cả hai đẩy text vào Elasticsearch.

### ⚠️ Gotcha quan trọng
Query text phải được encode bằng **ĐÚNG model CLIP mà BTC dùng** để tạo features.
Sai model → vector không cùng không gian → search vô nghĩa. **Xác nhận version CLIP
của BTC trước khi code phần query encoder.** (Xem mục 7.)

---

## 4. Bốn bài toán & module phục vụ

- **KIS** — tìm đúng 1 khoảnh khắc (vật nhỏ, hành động 1–2 giây).
  → CLIP search + lọc theo `Objects` + UI duyệt nhanh.
- **AVS** — tìm **tất cả** khoảnh khắc khớp, trả danh sách xếp theo tương đồng.
  → embedding tốt + khử trùng lặp + UI **chọn cụm** nhanh.
  ⚠️ Nộp dư bị trừ (vd đúng 2–6 nhưng thêm 1,7,13 → sai). Ưu tiên **precision**.
- **Video QA** — trả lời + suy luận (có đếm, temporal).
  → OCR + ASR + Metadata + một VLM/LLM đọc & suy luận.
- **KISC** (mới 2026) — hội thoại: mô tả mơ hồ → agent **tự hỏi lại** → siết dần.
  → tầng Agent bọc trên search engine. Mục tiêu: **giao diện tối giản**.

---

## 5. Tech stack

- Backend: **Python + FastAPI**
- Vector DB: **Milvus** (nếu cần đơn giản lúc đầu, có thể start bằng **Faiss**)
- Text/metadata: **Elasticsearch**
- Frontend: web UI (React hoặc HTML/JS thuần) — ưu tiên **duyệt nhanh, bàn phím**
- OCR: PaddleOCR / VietOCR + hậu xử lý qua `llm()`
- ASR: PhoWhisper hoặc faster-whisper (chạy trên Colab/Kaggle, KHÔNG trên máy dev)
- Hạ tầng: `docker-compose` cho Milvus + Elasticsearch

---

## 6. Cấu trúc thư mục

```
/
├── CLAUDE.md                 # file này
├── BUILD_TASKS.md            # lộ trình task (dán từng cái vào Claude Code)
├── docker-compose.yml        # Milvus + Elasticsearch
├── backend/
│   ├── indexing/             # nạp CLIP features, objects, metadata, ocr, asr
│   ├── retrieval/            # search + fusion + rerank
│   ├── llm/                  # ADAPTER llm() — điểm tháo lắp duy nhất
│   ├── agent/                # KISC + track tự động (làm SAU)
│   └── api/                  # FastAPI endpoints
├── frontend/                 # UI search-and-submit
├── preprocessing/            # job OCR, ASR (chạy Colab/Kaggle)
└── data/
    ├── sample/               # data mẫu để test
    └── config/               # submit_format.py, clip_model.py (thứ CHƯA chốt)
```

---

## 7. Điều CHƯA chốt — KHÔNG hardcode

Để những thứ sau trong `data/config/` và đọc từ config, đừng nhét cứng vào logic:

- **Format submit**: `frame_id` (vd `001`) hay `timestamp ms`? (chờ buổi tập huấn sau)
- **Version model CLIP** của BTC (phải khớp query encoder — xem mục 3)
- **Cơ chế track tự động** (agent đấu agent) — chưa rõ
- **FPS / mật độ keyframe** mỗi video (BTC công bố sau)

Nếu một task đụng tới thứ chưa chốt → tạo một hàm/biến config có ghi chú `# TODO: BTC`
và dùng giá trị giả định hợp lý, ĐỪNG chặn tiến độ.

---

## 8. Nguyên tắc làm việc cho AI (Fable 5)


1. **Giải thích lý do** mỗi đoạn code (tại sao chọn cách này) — ngắn gọn, tiếng Việt.
2. Làm **từng task nhỏ**, chạy được rồi mới sang task sau. KHÔNG viết cả hệ thống 1 lần.
3. Giữ **`llm()` tháo lắp được**. Không gọi API trực tiếp ngoài `backend/llm/`.
4. Ưu tiên **code thông minh, tối ưu**.
5. Sau mỗi task: nói rõ **cách chạy/test** và **task tiếp theo** là gì.
