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

> Nguồn: *Thông tin vòng Sơ tuyển AIC2026* của BTC, mục 2. Chép lại nguyên công thức
> — mục này từng chỉ có bảng rút gọn ở cuối, đủ dùng cho KIS/Q&A nhưng **sai với
> TRAKE**. Đọc phần định nghĩa trước khi dùng bảng.

Mỗi truy vấn nộp tối đa 100 câu. **Mỗi câu** được chấm một `R-Score ∈ [0, 1]`, cách
tính **khác nhau theo dạng bài**:

| Dạng | `R-Score(rᵢ)` |
|:---|:---|
| **KIS** | `I(vᵢ = GTᵥ ∧ idᵢ ∈ [s, e])` — nhị phân 0 hoặc 1 |
| **Q&A** | `I(vᵢ = GTᵥ ∧ idᵢ ∈ [s, e] ∧ aᵢ = GTₐ)` — nhị phân. Ba điều kiện cùng lúc; `answer` chấm theo **ngữ nghĩa**, VI hay EN đều được |
| **TRAKE** | `0` nếu sai video. Đúng video → `(1/N) · Σⱼ I(idᵢⱼ ∈ [sⱼ, eⱼ])` — **điểm từng phần** |

⚠️ TRAKE khớp **theo vị trí**: frame thứ *j* phải rơi vào khoảng `[sⱼ, eⱼ]` của khoảnh
khắc thứ *j*. Không phải khớp bất kỳ thứ tự nào. Mỗi khoảng thường **dưới 10 frame**.

Rồi mới tới bước gộp:

```
R@k   = max{ R-Score(r₁ … r_k) }          k ∈ {1, 5, 20, 50, 100}
Final = trung bình 5 giá trị R@k
```

**Ví dụ của BTC:** câu 1 được 0.5 · câu 3 được 0.8 (cao nhất) · câu 15 được 0.6.
→ `R@1 = 0.5`, còn `R@5 = R@20 = R@50 = R@100 = 0.8`
→ `Final = (0.5 + 0.8 + 0.8 + 0.8 + 0.8) / 5 = 0.74`

**Bảng rút gọn — CHỈ đúng cho KIS và Q&A** (vì `R-Score` nhị phân), theo hạng câu
đúng đầu tiên. Suy ra từ công thức trên, không phải một luật riêng:

| Hạng | 1 | 2–5 | 6–20 | 21–50 | 51–100 | >100 |
|---|---|---|---|---|---|---|
| Final | 1.00 | 0.80 | 0.60 | 0.40 | 0.20 | 0 |

> [!WARNING]
> **Đừng dùng bảng này cho TRAKE.** TRAKE có điểm lẻ (khớp 3/4 khoảnh khắc → 0.75)
> nên phải chạy thẳng công thức `max` rồi `trung bình`. Ví dụ: hạng 1 được 0.5, hạng
> 3 được 0.75 → `Final = (0.5 + 0.75×4)/5 = 0.70`, không có ô nào trong bảng ra số đó.

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
| Objects | 1 JSON/keyframe, tên khớp tên keyframe (`L01_V001/0000.json`), Faster R-CNN OpenImages V4 | Elasticsearch |
| CLIP features | **MỘT file `.npy` duy nhất cho toàn bộ keyframe**, model `clip-ViT-B-32`, hàng i = keyframe thứ i (thứ tự tăng dần) | Milvus |
| Metadata | 1 JSON/video (title, description, keywords...) | Elasticsearch |

- Một số video KHÔNG có metadata → mọi logic metadata phải có đường lui.
- Data hiện tại là batch 1 (= data AIC 2025); batch 2 có sau → code phải nạp thêm
  không index lại từ đầu (loader upsert idempotent đáp ứng sẵn).
- ✅ Cách gói `.npy` **đã rõ**: BTC nói rõ là MỘT file duy nhất cho tất cả keyframe, thứ tự
  tăng dần theo chỉ số keyframe. `load_clip.py` phải đọc theo kiểu đó, không phải 1 file/video.

### ⚠️ frame_map — dễ mất điểm nhất
Tên file keyframe (`0007.jpg`) là SỐ THỨ TỰ, còn BTC chấm theo FRAME INDEX trong
video. Phải nạp bảng `keyframe_id → frame_idx`. Nhầm = 0 điểm dù đúng video.

⚠️ **Tài liệu BTC nói frame index nằm trong "file metadata"**, không nhắc file
`map-keyframes` CSV như các mùa trước. Chưa rõ là metadata YouTube của video hay một
file riêng cho keyframe — **kiểm ngay lúc tải data**, đây là thứ dễ mất điểm nhất.

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
