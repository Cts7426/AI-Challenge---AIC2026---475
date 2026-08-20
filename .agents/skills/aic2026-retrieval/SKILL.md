---
name: aic2026-retrieval
description: Quy ước bắt buộc khi làm việc trên hệ thống truy xuất video AIC 2026 (Milvus + Elasticsearch + CLIP + OCR/ASR + agent KISC). BẮT BUỘC dùng skill này khi đụng tới bất cứ thứ gì sau đây, kể cả khi người dùng không nhắc tên skill - viết hoặc sửa code retrieval, index, embedding, vector search, CLIP, Milvus, FAISS, Elasticsearch, OCR, ASR, keyframe, query expansion, gọi LLM, agent KISC, hoặc submit kết quả. Skill này chứa các bất biến mà vi phạm sẽ gây lỗi IM LẶNG (không crash, chỉ trả kết quả sai).
---

# AIC 2026 — Quy ước hệ thống truy xuất

Đọc `AGENTS.md` ở gốc repo để biết kiến trúc tổng thể. File này chứa phần
**thủ tục dễ sai** mà `AGENTS.md` không nói hết.

## Nguyên tắc bao trùm

Bài toán này có nhiều lỗi **im lặng**: code chạy, không exception, nhưng kết quả
sai hoàn toàn. Vì vậy: **mỗi khi viết code đụng vector, luôn kèm một phép kiểm
chứng chạy được**, đừng chỉ viết logic rồi báo xong.

---

## Bất biến 1 — Không gian vector

- Query encoder **phải** dùng đúng model đọc từ `data/config/clip_model.py`.
  Không hardcode tên model ở bất kỳ đâu khác.
- **Chuẩn hóa L2 mọi vector trước khi index và trước khi query.** Đã chuẩn hóa
  thì cosine = dot product (nhanh hơn) — nhưng chỉ đúng nếu **cả hai phía** đều
  chuẩn hóa.
- Metric của Milvus phải khớp: đã normalize thì dùng inner product (IP),
  **không** dùng L2 distance rồi diễn giải như cosine.

**Kiểm chứng bắt buộc:** khi có feature BTC cấp, encode lại chính ảnh đó và so
cosine với vector BTC. ≈1.0 mới được đi tiếp. ~0 → dừng, báo người dùng ngay.

## Bất biến 2 — Khóa join

`keyframe_id` là khóa duy nhất nối Milvus ↔ Elasticsearch. Format thống nhất,
không tự đặt lại ở từng module. Mọi bảng/collection đều phải có nó.

## Bất biến 3 — Gọi LLM

Chỉ được gọi LLM qua `llm()` trong `backend/llm/`. **Tuyệt đối không** import
SDK của nhà cung cấp ở chỗ khác. Lý do: vòng chung kết có thể cấm internet, khi
đó phải đổi sang model local bằng biến môi trường mà không sửa code khác.

## Bất biến 4 — Không hardcode thứ BTC chưa công bố

Ba thứ sau **luôn** đọc từ `data/config/`, kèm ghi chú `# TODO: BTC`:
- format submit (frame_id vs timestamp ms)
- version/số chiều model CLIP
- fps và mật độ keyframe

## Bất biến 5 — Giới hạn 77 token của CLIP

Mở rộng query = **nhiều câu ngắn, encode riêng từng câu, rồi hợp nhất**.
Không bao giờ nối thành một đoạn dài rồi encode một lần.

Prompt mở rộng phải cấm LLM thêm chi tiết không có trong query gốc (thêm màu,
thêm số lượng → thu hẹp sai → trượt mục tiêu).

---

## Quy tắc theo tầng

### Indexing
- Job nặng (OCR/ASR) **phải checkpoint và resume được** — phiên Kaggle tự tắt
  sau ~9–12h.
- Chia việc song song bằng `hash(video_id) % NUM_WORKERS` (xác định, không trùng).
- Lọc frame đen/mờ **trước** khi OCR để khỏi đốt GPU.
- Text OCR/ASR có độ tin cậy thấp thì đừng đẩy vào index chính — nhiễu làm
  hỏng điểm BM25.

### Retrieval
- Trọng số fusion vector/text để trong config, chỉnh được không cần sửa code.
- **Đừng đặt ngưỡng điểm cứng.** Cosine thực tế của CLIP thường chỉ quanh
  0.2–0.3 (xem case study slide BTC: 0.233 / 0.251 / 0.224). Ngưỡng kiểu
  `score > 0.8` sẽ loại sạch kết quả đúng.
- Model nặng (VLM) chỉ chạy offline, **không** đặt trong đường chạy online —
  cuộc thi trừ điểm theo thời gian.

### Theo loại bài toán
- **KIS**: ưu tiên precision, mở rộng query ít (1–2 caption).
- **AVS**: ưu tiên recall khi *tìm*, nhưng ưu tiên precision khi *nộp* — nộp dư
  bị trừ điểm. Dedup để duyệt cho gọn, nhưng khi submit phải **mở lại cụm
  frame liền kề**, đừng nộp mỗi cụm một frame.
- **Video QA**: thu thập bằng chứng (OCR + ASR + metadata) rồi mới cho `llm()`
  suy luận. Không đoán khi không có bằng chứng.
- **KISC**: giao diện **tối giản** — BTC yêu cầu can thiệp ít nhất có thể.
  Hỏi lại theo thứ tự loại được nhiều ứng viên nhất trước (thời gian → địa điểm
  → đối tượng → cảnh vật).

### Agent
Agent **gọi search engine làm tool**, không tự viết lại logic tìm kiếm.
Ưu tiên độ trễ thấp: mỗi vòng lặp thừa là điểm bị trừ.

---

## Cách trình bày khi làm xong một task

1. Nói **ngắn gọn bằng tiếng Việt** đã làm gì và **tại sao chọn cách đó**
   (đây là dự án học tập — người dùng cần hiểu, không chỉ cần code chạy).
2. Đưa **lệnh cụ thể để chạy/test**.
3. Nếu task đụng tới vector: kèm luôn phép kiểm chứng và kết quả thực tế.
4. Nói rõ **task tiếp theo** nên là gì.

Làm **từng task nhỏ, chạy được rồi mới sang task sau**. Không viết cả hệ thống một lần.
