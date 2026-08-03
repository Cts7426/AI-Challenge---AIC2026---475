# Thể thức AI Challenge HCMC 2026 — tài liệu tham chiếu

> Đọc file này khi làm task đụng tới: submit, kis/qa/trake, chiến lược retrieval,
> chấm điểm. CLAUDE.md chỉ giữ phần rút gọn.

## Hai vòng — luật chơi KHÁC NHAU

| | Sơ tuyển (8/2026) | Chung kết onsite (12–26/9) |
|---|---|---|
| Hình thức | Online, **nộp theo lô** | Trực tiếp, tương tác |
| Dạng bài | Textual KIS, Q&A, **TRAKE** | Chưa công bố (có thể thêm AVS/KISC) |
| Chấm | R@k, **không trừ thời gian** | Trừ theo thời gian, UI được cộng điểm |
| Ưu tiên | **Chất lượng danh sách 100 kết quả** | Tốc độ thao tác + UI |

→ Mọi quyết định ưu tiên cho SƠ TUYỂN trước. Code AVS đã viết: giữ, ngừng đầu tư.

## Ba dạng bài vòng sơ tuyển

### Textual KIS
- Nộp: `<video_id>, <frame_id>` — đúng khi khớp video VÀ `frame_id ∈ [s, e]` (khoảng hẹp).

### Q&A
- Nộp: `<video_id>, <frame_id>, <answer>` — cả 3 điều kiện phải đúng CÙNG LÚC
  (đúng frame mà sai answer vẫn 0 điểm). Answer VI hoặc EN đều được, chấm ngữ nghĩa.
- Pipeline: thu bằng chứng (OCR + ASR + Objects + metadata) → `llm()` suy luận.

### TRAKE (khó nhất)
- Nộp: `<video_id>, <frame_id₁>, ..., <frame_idₙ>` — 2 giai đoạn: tìm đúng 1 video,
  rồi định vị N khoảnh khắc.
- Sai video → 0 điểm ngay. Đúng video → điểm = tỉ lệ khoảnh khắc khớp (3/4 → 0.75).
- ⚠️ Mỗi khoảnh khắc rộng < 10 frame → keyframe BTC (I-frame thưa) nhiều khả năng
  KHÔNG rơi vào khoảng đáp án → bắt buộc trích frame dày quanh vùng ứng viên.
- Có điểm từng phần → LUÔN nộp đủ N khoảnh khắc, đoán còn hơn bỏ trống.

## Cách chấm — quyết định chiến thuật

Mỗi truy vấn nộp tối đa 100 câu. `R@k` = R-Score cao nhất trong k câu đầu.
`Final = trung bình(R@1, R@5, R@20, R@50, R@100)`. Giá trị theo hạng câu đúng đầu tiên:

| Hạng | 1 | 2–5 | 6–20 | 21–50 | 51–100 | >100 |
|---|---|---|---|---|---|---|
| Điểm | 1.00 | 0.80 | 0.60 | 0.40 | 0.20 | 0 |

**Hai quy tắc bắt buộc:**
1. **LUÔN nộp đủ 100 câu** — không có hình phạt cho câu sai ở sơ tuyển. (Quy tắc
   "nộp dư bị trừ" chỉ áp dụng cho AVS — không có ở sơ tuyển.)
2. **Thứ hạng là tất cả**: đẩy câu đúng từ hạng 2 lên 1 = +0.20, ngang cứu một câu
   từ trượt lên hạng 51 → đầu tư re-ranking đáng giá ngang đầu tư recall.

## Dữ liệu BTC cung cấp

⚠️ Dữ liệu thi CHÍNH THỨC là VIDEO — Keyframes/Objects/CLIP features/Metadata chỉ là
tài liệu hỗ trợ → ĐƯỢC PHÉP tự trích frame dày hơn và tự encode bằng model mạnh hơn.

| Nguồn | Cấu trúc | Vào đâu |
|---|---|---|
| Videos | `L01_V001.mp4` | nguồn chuẩn; trích frame khi cần |
| Keyframes | `L01_V001/0000.jpg`, thứ tự tăng dần | Milvus (id) + hiển thị |
| Objects | 1 JSON/keyframe, Faster R-CNN OpenImages V4 | Elasticsearch |
| CLIP features | `.npy`, model `clip-ViT-B-32` (512d), hàng i = keyframe i | Milvus |
| Metadata | 1 JSON/video (title, description, keywords...) | Elasticsearch |

- Một số video KHÔNG có metadata → mọi logic metadata phải có đường lui.
- Data hiện tại là batch 1 (= data AIC 2025); batch 2 có sau → code phải nạp thêm
  không index lại từ đầu (loader upsert idempotent đáp ứng sẵn).
- Cách gói `.npy` (1 file/tất cả hay 1 file/video) — kiểm lại khi tải data về.

### ⚠️ frame_map — dễ mất điểm nhất
Tên file keyframe (`0007.jpg`) là SỐ THỨ TỰ, còn BTC chấm theo FRAME INDEX trong
video. Phải nạp bảng `keyframe_id → frame_idx` (các mùa trước: file `map-keyframes`
CSV gồm n, pts_time, fps, frame_idx — tìm ngay khi tải data). Nhầm = 0 điểm dù đúng video.

## Chiến lược 2 tầng (cho TRAKE + nâng chất lượng)

1. **Tầng thô**: features BTC (ViT-B-32) quét toàn kho → danh sách video/vùng ứng viên.
2. **Tầng tinh**: chỉ vùng ứng viên → trích frame dày (ffmpeg/decord) + encode model
   mạnh hơn (ViT-L/14, SigLIP) → định vị chính xác.

⚠️ Nếu tự encode: ảnh và query PHẢI cùng model — không trộn không gian vector
trong cùng collection.

## Chung kết (làm SAU, khi qua sơ tuyển)
- KISC: agent hỏi lại người dùng, siết dần bộ lọc (thời gian → địa điểm → đối tượng
  → cảnh vật — thứ tự loại nhiều ứng viên nhất trước). UI tối giản.
- Track tự động: tái dùng agent, bỏ phần hỏi người.
- Luật internet chưa công bố → `llm()` giữ 2 backend (env `LLM_BACKEND=api|local`).
