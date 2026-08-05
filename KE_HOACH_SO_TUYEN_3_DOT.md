# KẾ HOẠCH — AIC 2026 SƠ TUYỂN (3 ĐỢT THI TRỰC TIẾP)

**v2.0 · 01/08/2026** · Thay thế bản 6 tuần và bản 3 tuần trước đó
Nhóm: Thạch · Công Lý · Thi · Minh Hoàng · Quang Linh

---

## 0. ĐIỀU GÌ ĐÃ ĐỔI

| | Giả định cũ | Thực tế |
|---|---|---|
| Hình thức | Nộp file offline theo lô | **Thi trực tiếp, 3 giờ/buổi** |
| Số lần | 1 lần duy nhất | **3 đợt** — được thi thử 2 lần |
| Hạn | ~22/08 (đoán) | **21/08 · 28/08 · 04/09**, 19:30–22:30 |
| UI | "không cần nhanh" ❌ | **thông lượng quyết định điểm** |

**Hệ quả quan trọng nhất:** đợt 1 không còn là "hỏng là hết". Nó là **buổi diễn tập
có tính điểm**. Mục tiêu đợt 1 = *chạy trơn và học được nhiều nhất*, không phải điểm
cao nhất. Những thứ từng nằm trong danh sách cắt giờ có đường quay lại ở đợt 2–3.

---

## 1. TRỤC THỜI GIAN

```
01–02/08  W0  Nợ kỹ thuật + tải data + gửi câu hỏi BTC
03–09/08  W1  Nền móng + baseline chạy được          🚩 G1 · G2
10–16/08  W2  Ba dạng bài + tín hiệu                 🚩 G3
17–19/08  W3  Tối ưu + luyện thao tác  → ĐÓNG BĂNG 19/08
20/08         🎭 TỔNG DUYỆT (đúng giờ, đúng máy, đúng vị trí)
─────────────────────────────────────────────────────────
21/08     ⚔️ ĐỢT 1 · 19:30–22:30
22/08         📋 POST-MORTEM (trong 24h, bắt buộc)
22–27/08  W4  Sửa theo bài học đợt 1
─────────────────────────────────────────────────────────
28/08     ⚔️ ĐỢT 2 · 19:30–22:30
29/08         📋 POST-MORTEM
29/08–03/09 W5  Sửa tiếp + bổ sung tính năng đã hoãn
─────────────────────────────────────────────────────────
04/09     ⚔️ ĐỢT 3 · 19:30–22:30
```

**Runway thật: 34 ngày** với hai điểm kiểm tra bằng dữ liệu thật. Tốt hơn nhiều so
với giả định 3 tuần một lần ăn thua.

---

## 2. NGÂN SÁCH THỜI GIAN MỖI CÂU

Giả định 20–30 câu / 180 phút → **6–9 phút/câu**.

| Giai đoạn | Ngân sách |
|---|---|
| Đọc đề + gõ query | 30–60s |
| **Pipeline chạy xong, hiện kết quả** | **≤ 30s** ← mục tiêu cứng |
| Người duyệt + sửa thứ tự top | 60–120s |
| Nộp | 10s |
| Đệm / thử lại | phần còn lại |

**Luật 1 — Con người KHÔNG chọn 100 slot.** Máy sinh đủ 100, người chỉ **sửa phần đầu**.
R@1+R@5 = 40% điểm → 30 giây xác nhận top-5 là 30 giây giá trị nhất cả câu.

**Luật 2 — ⛔ Không gọi VLM trong đường chạy online của KIS.** Q&A buộc phải có VLM →
dạng tốn thời gian nhất, để làm sau nếu buổi thi tính giờ chung.

**Luật 3 — Mọi thay đổi phải đo lại độ trễ.** Tính năng làm pipeline vượt 30s là tính
năng làm **mất** điểm.

---

## 3. LỊCH CHI TIẾT

### W0 (01–02/08) — làm ngay cuối tuần này

| Ai | Việc |
|---|---|
| **Linh** | 🔴 **GỬI CÂU HỎI BTC HÔM NAY** (mục 6). Quan trọng nhất: thi cả 3 đợt hay 1 đợt · bao nhiêu câu/buổi · có internet không |
| **Công Lý** | 🔴 **TẢI DATA NGAY.** 20 video trước để cả nhóm có cái chạy thử, rồi tải tiếp |
| **Thạch** | W0.1 đổi tên `preprocessinga` · W0.3 `/health` deep check · W0.4 chuyển repo khỏi OneDrive · dựng `config.yaml` |
| **Minh Hoàng** | W0.2 xoá bug `frame_id` khỏi tầng format |

### W1 (03–09/08) — NỀN MÓNG + BASELINE

🎯 **09/08 phải có pipeline chạy đầu-cuối ra 100 slot hợp lệ.**
Dùng CLIP B/32 BTC cấp → **0 giờ GPU**. Không đặt job GPU nào lên đường găng tuần này.

- **Công Lý:** B0.1 audit + `frame_map` (🔒 gác cổng) → B1.1 shot segmentation
- **Thạch:** A1.0 nạp CLIP + kiểm chứng cosine ≈ 1.0 → A2.1/A2.2 search + RRF
- **Thi:** C0.1 `llm()` adapter → C1.1 hiểu truy vấn
- **Minh Hoàng:** D0.2 export + validator → D3.1 slot allocator
- **Linh:** E0.1 theo đuổi BTC · E4.1a dev set 25 câu KIS

> 🚩 **G1 (06/08)** — `frame_map` xanh chưa? Ba người xác thực độc lập chưa?
> 🚩 **G2 (09/08)** — CÓ FILE 100 SLOT HỢP LỆ CHƯA?
> G2 không đạt → cắt sạch P2, cả nhóm dồn vào ghép ống.

### W2 (10–16/08) — BA DẠNG BÀI + TÍN HIỆU

🎯 **Cả KIS, Q&A, TRAKE đều có điểm đo được.**

- **Công Lý:** B1.2 keyframe 1fps → B1.3 ASR → B1.4 OCR → B1.7 `docs_bm25`
- **Thi:** C3.1 Q&A → C3.2 TRAKE giai đoạn 1 → C4.4 fallback TRAKE (**làm sớm**)
- **Minh Hoàng:** D2.1 UI + E4.2 `eval.py` → D3.5 mô phỏng chấm điểm
- **Thạch:** tinh chỉnh RRF, hỗ trợ ghép Q&A/TRAKE
- **Linh:** dev set đủ 25 KIS + 15 Q&A + 10 TRAKE

> 🚩 **G3 (16/08)** — ba dạng bài đều có điểm chưa?
> ★ 20:00 phiên phân tích lỗi — xem 10 câu sai tệ nhất, chốt 3 việc cho W3

### W3 (17–19/08) — TỐI ƯU + LUYỆN THAO TÁC

⚠️ Ngắn hơn bản cũ 1 ngày để dành chỗ cho tổng duyệt.

- **Thạch:** A2.4 rerank text (đo nDCG@20, không tăng thì tắt) · A6.0 orchestrator
- **Minh Hoàng:** D4.1 chỉnh slot theo dữ liệu · D6.1 preflight check
- **Công Lý:** ⬆️ **UI điều hướng bàn phím** — một phím nộp, không click chuột
- **Thi:** C4.1 TRAKE DP (**P2, cắt được** — không đạt R-Score 0.3 thì dùng C4.4)
- **Linh:** ⬆️ **luyện thao tác có bấm giờ**, 6 phút/câu, ít nhất 3 buổi

**19/08 — ĐÓNG BĂNG.** Sau mốc này chỉ sửa lỗi.

### 20/08 — 🎭 TỔNG DUYỆT

Cả nhóm ngồi **đúng vị trí, đúng máy, đúng khung giờ 19:30–22:30**.
Chạy thử **20 câu trong 60 phút**. Mục tiêu không phải điểm cao — mà là:
- Đo thời gian thật mỗi câu, đối chiếu ngân sách
- Tìm chỗ nghẽn trong thao tác của người, không phải trong code
- Diễn tập **kịch bản sự cố**: rút mạng, tắt Docker giữa chừng → `run_minimal.py` có
  bấm là chạy không?
- Chốt ai ngồi đâu, ai gõ, ai đọc đề, ai bấm nộp

### 21/08 — ⚔️ ĐỢT 1

Mục tiêu: **chạy trơn, ghi chép đầy đủ.** Không mạo hiểm với tính năng chưa chắc.
Cử một người **chỉ ghi chép** — câu nào mất bao lâu, kẹt ở đâu, hệ thống gãy chỗ nào.

### 22/08 — 📋 POST-MORTEM (bắt buộc, trong 24h)

Trả lời bằng **số liệu**, không bằng cảm giác:
1. Làm được bao nhiêu câu / tổng số câu? Câu nào **không kịp làm**?
2. Câu trượt là do **retrieval sai** hay do **hết giờ**? (hai bệnh, hai thuốc)
3. Thời gian thật mỗi câu vs ngân sách 6 phút — nghẽn ở giai đoạn nào?
4. Người thao tác kẹt ở thao tác gì?
5. Đề thật khác dev set của Linh ở chỗ nào? → cập nhật dev set ngay

**Chốt đúng 3 việc cho W4.** Không nhiều hơn.

### W4 (22–27/08) — SỬA THEO BÀI HỌC ĐỢT 1

Nội dung phụ thuộc post-mortem. Nếu không có bài học đặc thù thì theo thứ tự:
1. Sửa nghẽn thao tác (thường lời nhất, rẻ nhất)
2. Caption VLM trên `rep_kf` (~60–80h GPU)
3. TRAKE DP nếu W3 chưa kịp

**26/08 đóng băng · 27/08 duyệt lại nhanh.**

### 28/08 — ⚔️ ĐỢT 2 · 29/08 — 📋 POST-MORTEM

### W5 (29/08–03/09) — BỔ SUNG TÍNH NĂNG ĐÃ HOÃN

1. SigLIP re-encode (~40–60h GPU) — nếu đo thấy CLIP B/32 là nghẽn chất lượng
2. Rerank nâng cao
3. Tinh chỉnh cuối theo hai lần post-mortem

**03/09 đóng băng.**

### 04/09 — ⚔️ ĐỢT 3

---

## 4. PHÂN CÔNG (đã điều chỉnh)

| Người | Sở hữu | Đổi so với bản cũ |
|---|---|---|
| **Thạch** | Retrieval core, RRF, orchestrator, `CLAUDE.md`, schema | — |
| **Công Lý** | Data factory + **UI thi đấu** | ⬆️ thêm UI, nâng ưu tiên |
| **Thi** | `llm()`, hiểu truy vấn, Q&A, TRAKE | — |
| **Minh Hoàng** | `export.py` + `submit_format.py` + validator, slot allocator, `eval.py` | ⬆️ nhận thêm W0.2 |
| **Linh** | BTC, dev set, vận hành job, **operator luyện có bấm giờ** | ⬆️ luyện thao tác thành việc chính |

**Backup:** Thạch↔Thi · Công Lý↔Minh Hoàng · **Linh←Thạch (operator dự bị)**

⚠️ **Operator dự bị là bắt buộc.** Một người ốm đúng tối 21/08 mà không ai thay được
là rủi ro không chấp nhận nổi.

---

## 5. THỨ TỰ CẮT NẾU TRỄ

1. SigLIP re-encode → đẩy sang W5
2. Caption VLM → đẩy sang W4
3. TRAKE DP → dùng fallback C4.4
4. Rerank text
5. OCR (giữ ASR + metadata)

**Không bao giờ bỏ:** `frame_map` đúng · slot allocator đủ 100 dòng · export + validator ·
`run_minimal.py` · **tổng duyệt 20/08**.

---

## 6. CÂU HỎI GỬI BTC — LINH GỬI HÔM NAY

1. 🔴 **Mỗi đội thi cả 3 đợt hay chỉ 1 đợt?** (800+ đội → có thể chia đợt.
   Nếu chỉ 1 đợt thì toàn bộ chiến lược "học từ đợt 1" không còn.)
2. 🔴 **Điểm 3 đợt: cộng dồn / trung bình / lấy cao nhất?**
3. 🔴 **Bao nhiêu câu mỗi buổi?** Tỉ lệ KIS / Q&A / TRAKE?
4. 🔴 **Thi từ xa hay tới địa điểm? Có được dùng internet và API ngoài không?**
5. **Cửa sổ đáp án `[s,e]` của KIS rộng bao nhiêu?** Thể lệ nêu ví dụ `[500,510]` = 11
   frame. Nếu hẹp thật thì shot 10 giây (250 frame) chỉ có ~4% diện tích trúng → slot
   phải nghiêng mạnh về **độ sâu**. Nếu là cả đoạn sự kiện thì ngược lại.
   **Chênh lệch giữa hai giả định này lớn hơn mọi cải tiến model.**
6. Định dạng nộp cụ thể: CSV hay JSON · `frame_id` đếm từ 0 hay 1 · TRAKE ghi N frame
   cùng dòng hay nhiều dòng
7. TRAKE có biết trước số khoảnh khắc N và mô tả từng khoảnh khắc không?
8. Đợt 2–3 có dùng batch dữ liệu mới không? Batch 2 khi nào công bố?

**Câu 1, 3, 4 quan trọng nhất** — cả ba đều đổi chiến lược nếu câu trả lời khác dự đoán.

---

## 7. NHỊP LÀM VIỆC

- **Họp đứng 20:30 hằng ngày, 15 phút.** Hôm qua xong gì · hôm nay làm gì · ai đang chặn mình
- **Chỉ được nói "hệ yếu ở X" khi có số chứng minh.** Cảm giác không tính.
- **Merge tối thiểu 2 lần/tuần.** Branch phân kỳ quá 3 ngày là tự chuốc địa ngục merge.
- **Không hardcode.** Model name, ngưỡng, trọng số, đường dẫn đọc từ `config.yaml`.
- **Mọi `.npy`/`.faiss`/`.parquet` đi kèm `.meta.json`** (model, version, ngày, commit)
  và assert lúc load.
- **Dùng Claude Code để build, nhưng bắt nó giải thích lý do.** Ai không hiểu code tầng
  mình thì không debug được lúc gấp — mà tối 21/08 thì lúc nào cũng gấp.
