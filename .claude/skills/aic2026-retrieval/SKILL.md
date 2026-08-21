---
name: aic2026-retrieval
description: Quy ước bắt buộc khi làm việc trên hệ thống truy xuất video AIC 2026 (Milvus + Elasticsearch + CLIP + OCR/ASR + task KIS/Q&A/TRAKE). BẮT BUỘC dùng skill này khi đụng tới bất cứ thứ gì sau đây, kể cả khi người dùng không nhắc tên skill - viết hoặc sửa code retrieval, index, embedding, vector search, CLIP, Milvus, FAISS, Elasticsearch, OCR, ASR, keyframe, frame_map, query expansion, gọi LLM, slot/submit, hoặc agent KISC. Skill này chứa các bất biến mà vi phạm sẽ gây lỗi IM LẶNG (không crash, chỉ trả kết quả sai).
---

# AIC 2026 — Quy ước hệ thống truy xuất

`AGENTS.md` ở gốc repo là **nguồn chuẩn** (`CLAUDE.md` soi gương nguyên văn file
đó). Đọc nó để biết kiến trúc, bất biến và quy trình release. File này chỉ chứa
phần **thủ tục dễ sai** mà `AGENTS.md` nói ngắn; khi lệch nhau thì `AGENTS.md`
thắng, sau đó kiểm lại `docs/contest.md` và code/config thật.

## Nguyên tắc bao trùm

Bài toán này có nhiều lỗi **im lặng**: code chạy, không exception, nhưng kết quả
sai hoàn toàn. Vì vậy: **mỗi khi viết code đụng vector hoặc frame id, luôn kèm
một phép kiểm chứng chạy được**, đừng chỉ viết logic rồi báo xong.

---

## Bất biến 1 — Không gian vector

- Query encoder **phải** dùng đúng model đọc từ `data/config/clip_model.py`.
  Không hardcode tên model ở bất kỳ đâu khác.
- **Chuẩn hóa L2 mọi vector trước khi index và trước khi query.** Đã chuẩn hóa
  thì cosine = dot product — nhưng chỉ đúng nếu **cả hai phía** đều chuẩn hóa.
- Metric Milvus hiện hành là **COSINE** (`backend/indexing/load_clip.py`,
  `METRIC = "COSINE"`). Index và search phải dùng cùng metric; không đổi metric
  ngầm ở một phía, không dùng L2 distance rồi diễn giải như cosine.

**Kiểm chứng bắt buộc:** code đụng vector phải kiểm `norm ≈ 1.0`. Khi có ảnh và
model đúng của BTC, encode lại chính ảnh đó và so cosine với feature BTC. ≈1.0
mới được đi tiếp. ~0 → dừng, báo người dùng ngay.

## Bất biến 2 — Khóa join

`keyframe_id` là khóa duy nhất nối Milvus ↔ Elasticsearch ↔ frame map. Format
thống nhất, không tự đặt lại ở từng module. Mọi bảng/collection/index liên quan
đều phải giữ khóa này.

## Bất biến 3 — Hai lớp ảnh và frame_id nộp

- Raw BTC là **ordinal**, ví dụ `L21_V001/001.jpg` — ordinal **không phải frame
  index**. Derived (`data/derived/keyframes/L21_V001/f0001234.jpg`) chỉ là cache.
- `frame_id` nộp = **frame index tuyệt đối** trong video, tra từ
  `data/derived/frame_map.parquet`. Tầng format (`data/config/submit_format.py`)
  chỉ ghi số được cấp, **không đoán, không chứa logic mapping**.
- Q&A, API và UI lấy đường dẫn ảnh qua
  `backend.common.frame_assets.resolve_frame_path()` (ưu tiên raw rồi derived).
  Không tự ghép path ở caller.
- **Cấm cắt hậu tố tên keyframe để suy ra frame index.** Frame index chỉ nhận từ
  tham số hoặc `frame_map`.

## Bất biến 4 — Kết nối service

ES qua `es_client.connect()`, Milvus qua `milvus_client.connect()`. Không tạo
client trực tiếp ở module khác. Mỗi nguồn retrieval bọc try/except trả rỗng để
một service chết không kéo sập toàn query.

## Bất biến 5 — Gọi LLM

Chỉ được gọi LLM qua `llm()` trong `backend/llm/adapter.py`. **Tuyệt đối không**
import SDK của nhà cung cấp ở chỗ khác. Lý do: đổi backend (API / Gemini /
local) chỉ bằng biến môi trường `LLM_BACKEND`, không sửa caller. Luật internet
vòng chung kết chưa được công bố và chưa thuộc phạm vi sơ tuyển.

## Bất biến 6 — Không hardcode

Mọi path, model, metric, weight, policy nằm trong `data/config/`, không hardcode
ở caller. Những thứ BTC **chưa** xác nhận đủ mạnh thì đọc từ config kèm ghi chú
`# TODO: BTC`:
- version/số chiều và preprocess model CLIP (`data/config/clip_model.py`)
- cách chấm answer Q&A (`data/config/qa_evaluation.py`)
- fps và mật độ keyframe; dữ liệu/lịch đợt 2–3

Đã chốt, **không** còn là TODO: submit là frame tuyệt đối tra `frame_map`.

## Bất biến 7 — Giới hạn 77 token của CLIP

Mở rộng query = **nhiều câu ngắn, encode riêng từng câu, rồi hợp nhất**.
Không bao giờ nối thành một đoạn dài rồi encode một lần.

Prompt mở rộng phải cấm LLM thêm chi tiết không có trong query gốc (thêm màu,
thêm số lượng → thu hẹp sai → trượt mục tiêu).

---

## Quy tắc theo tầng

### Indexing
- Job nặng (OCR/ASR) **phải checkpoint và resume được** — phiên Colab/Kaggle tự
  tắt sau ~9–12h. Append + flush theo lô và skip phần đã xong.
- Chia việc song song bằng `hash(video_id) % NUM_WORKERS` (xác định, không trùng).
- Loader dùng natural key (`video_id`, `keyframe_id`), chạy lại không sinh trùng;
  nạp delta idempotent, không recreate dữ liệu đợt cũ nếu schema/model còn hợp.
- Lọc frame đen/mờ **trước** khi OCR để khỏi đốt GPU.
- Text OCR/ASR có độ tin cậy thấp thì đừng đẩy vào index chính — nhiễu làm
  hỏng điểm BM25. Text Việt trong ES dùng `VI_FOLDED_ANALYSIS` + `searchable_text()`.

### Retrieval
- Fusion là **weighted RRF đọc từ `data/config/search_weights.py`**, log rank
  từng nguồn. Chỉnh trọng số không cần sửa code.
- **Đừng đặt ngưỡng cosine cứng.** Cosine thực tế của CLIP thường chỉ quanh
  0.2–0.3 (case study slide BTC: 0.233 / 0.251 / 0.224). Ngưỡng kiểu
  `score > 0.8` sẽ loại sạch kết quả đúng.
- VLM/Whisper/Paddle local nặng **không** nằm trong `/search` — máy vận hành là
  Windows 16 GB RAM, torch CPU. (Sơ tuyển nộp lô, **không** trừ thời gian; đừng
  viện lý do độ trễ để biện minh cho thiết kế.)
- Q&A batch **được** dùng LLM/VLM qua adapter, nhưng phải lưu cache/evidence để
  replay lại được cùng một answer.

### Slot và submit
- Bảng chia 100 slot nằm ở `data/config/slot_budget.py`; đổi bảng phải kèm số đo
  (xem `reports/slot_tuning.md`), không đổi theo cảm tính.
- Release Q&A **luôn** truyền `--qa-submission-policy`; không phụ thuộc default.
  Cấu hình vận hành đợt 1 là `robust`.

### Theo loại bài toán
- **KIS**: ưu tiên precision, mở rộng query ít (1–2 caption).
- **Video Q&A**: thu thập bằng chứng (OCR + ASR + metadata) rồi mới cho `llm()`
  suy luận. Không đoán khi không có bằng chứng. Replay semantic/exact trên cùng
  answer/evidence; không so hai lần gọi LLM ngẫu nhiên.
- **TRAKE**: đúng **thứ tự** các khoảnh khắc mới tính; kiểm lại thứ tự trước khi
  ghi ra file nộp.
- **AVS/KISC**: chưa đầu tư trước khi qua sơ tuyển. Code cũ giữ nguyên nếu không
  gây lỗi; đừng mở rộng khi chưa được yêu cầu.

---

## Nhận hay bỏ một thay đổi

- `tune` dùng để phát triển và phân tích query-level; `holdout` **chỉ** dùng
  promotion.
- Sửa correctness/invariant: nhận khi test + regression qua.
- Tuning: chỉ nhận khi tăng ít nhất 0.02 trên tune **hoặc** cải thiện ít nhất
  hai query holdout, không giảm holdout và không tạo failure mới.
- Một thử nghiệm = **một** thay đổi config/code có baseline và query-level diff.
  Không tune trên worktree trộn nhiều thay đổi chưa truy nguồn được.
- Mọi run/release lưu commit, config snapshot, data manifest, scorer policy,
  log, scores và checksum ZIP.

---

## Cách trình bày khi làm xong một task

1. Nói **ngắn gọn bằng tiếng Việt** đã làm gì và **tại sao chọn cách đó**
   (đây là dự án học tập — người dùng cần hiểu, không chỉ cần code chạy).
2. Đưa **lệnh cụ thể để chạy/test**.
3. Nếu task đụng tới vector hoặc frame id: kèm luôn phép kiểm chứng và kết quả
   thực tế. **Không tick task hoàn thành nếu chưa có lệnh kiểm và artefact.**
4. Nói rõ **task tiếp theo** nên là gì (theo `BUILD_TASKS.md`).

Làm **từng task nhỏ, chạy được rồi mới sang task sau**. Không viết cả hệ thống một lần.
