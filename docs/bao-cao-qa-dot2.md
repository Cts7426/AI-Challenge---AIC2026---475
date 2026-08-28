# Báo cáo sửa Q&A trước đợt 2 (28/08/2026)

Nhánh `fix/qa-round2`. Mọi con số dưới đây đo trên đề đợt 1, không phải ước lượng.

---

## 1. Tóm tắt

| Đo trên đề đợt 1 | Trước | Sau |
|---|---|---|
| Câu Q&A chạy xong | 2/4 (p1-3, p1-15 HỎNG) | **4/4** |
| `exam.py finalize` đóng được ZIP | **KHÔNG** — bị chặn vì thiếu câu | **có** |
| Đáp án hạng 1 là chuỗi từ chối | 3/4 câu | **0/4** |
| Video đúng của p1-3 trong 100 dòng | **vắng mặt** | 13 dòng |
| Frame gần đáp án nhất (p1-3, GT 26050) | không có | **26028 — lệch 22 frame**, hạng 88 |

Test: **779 passed / 2 failed**. Hai lỗi là `test_evidence.py`, đã hỏng từ trước, không liên quan.

---

## 2. Bốn lỗi tìm ra và cách sửa

### 2.1 Bộ lọc sentinel là danh sách đóng

`QA_SENTINEL_ANSWERS` có đúng 6 chuỗi. LLM đẻ biến thể vô hạn — đo thật chỉ bắt **1/5**:

| Chuỗi LLM trả về | Cũ |
|---|---|
| `Không có thông tin về động đất cấp độ 4` | bắt |
| `Không thể xác định từ bằng chứng` | **lọt** |
| `Không có cân hiển thị trong hình ảnh` | **lọt** |
| `Không thấy cân hoặc số trên cân trong hình` | **lọt** |
| `Không đủ bằng chứng` | **lọt** |

**Sửa:** dò HÌNH DẠNG thay vì liệt kê chuỗi — phủ định + từ nói về việc *nhìn/đọc được bằng chứng*, chỉ áp khi answer ≥ 3 từ.

Cố ý **không** dò theo `"thông tin"`/`"information"`: chúng có trong đáp án thật
(`"Không có thông tin liên lạc"`, `"No Information Technology"` — hai ca này có test bảo vệ).

Đo lại: **8/8 chuỗi từ chối bị loại, 9/9 đáp án thật giữ nguyên.**

### 2.2 Không kiểm KIỂU đáp án

p1-17 hỏi *"tên con đèo là gì"* → hạng 1 là `"Chồn Hương"` (tên con vật), còn
`"Đèo Bạch Mã"` nằm hạng 2. Hai bên hoà confidence 0.62, không có gì phá hoà.

**Sửa:** `QA_ANSWER_MODE_RULES` — câu đếm bắt buộc chứa chữ số, các mode khác giới hạn số từ.

### 2.3 Confidence bị đảo ngược, hạng retrieval bị vứt

Winner của p1-3 là shot **hạng 104**, p1-15 là **hạng 105** — chọn thuần theo
confidence tự khai. Mà confidence lại đảo ngược: câu từ chối `"không thấy cân"`
được **0.60** (khẳng định không thấy gì là quan sát dễ), còn đọc số mờ thật thì
model chỉ dám 0.30. Nên câu từ chối ở đáy bảng luôn thắng câu trả lời thật ở đầu.

**Sửa:** phạt log10 theo độ sâu — hạng 1 → 0 · hạng 10 → −0,15 · hạng 100 → −0,30.
Chỉ áp cho shot **đào thêm trong video** và phạt **một chiều**.

> Bản đầu phạt cả vòng chính và làm gãy
> `test_shot_dau_bang_du_nhanh_KHONG_duoc_cat_duong_ung_vien_text` — shot do nhánh
> text đề cử nối vào cuối `candidate_shots` nên chỉ số lớn, nhưng đó là ứng viên
> chọn có chủ đích chứ không phải mò sâu. Test đó bắt đúng.

### 2.4 Lọc sạch xong thì không còn gì để nộp

Sửa xong ba lỗi trên, p1-3 và p1-15 lọc hết mọi ứng viên → `QANoValidHypothesisError`
→ `finalize` chặn cả gói ZIP. Tệ hơn trước.

**Sửa:** hết đáp án thì nộp **12 video đầu bảng retrieval, mỗi video một dòng**,
đáp án chỗ trống (`"0"` cho câu đếm, `"TODO"` cho mode khác). Thà đoán còn hơn bỏ
trống — không có hình phạt cho câu sai, mà bỏ trống thì chặn cả gói.

Chỗ trống dùng digest riêng `placeholder-<sha256>`, **không** đi qua
`_evidence_hash_for_attempt` (hàm đó fail-closed vì mọi answer thật phải truy về
bằng chứng — chỗ trống thì đúng là không có bằng chứng).

Tìm `TODO` trong `submissions/` để biết câu nào cần người điền tay.

---

## 3. Lỗi lớn nhất: Q&A không có anchor

Đây mới là thứ làm trượt câu, ba lỗi trên chỉ chọn *trong số ứng viên đã có*.

**Đo trên p1-3** (đáp án thật `L21_V023` frame 26050), cùng video, cùng encoder
CLIP, chỉ đổi chữ đưa vào nhánh vector:

| Chữ đưa vào | Hạng |
|---|---|
| cả câu hỏi — **Q&A đang làm thế này** | 151 |
| bỏ câu hỏi, giữ mô tả dài | 192 |
| caption ngắn `a fish lying on a weighing scale` | **3** |

Thủ phạm là **văn phong và độ dài**, không phải model. CLIP học trên chú thích
ảnh, không học trên câu hỏi hay đoạn kể chuỗi. Bỏ dấu chấm hỏi thôi còn **tệ hơn**
(151 → 192) — phải ngắn và đúng kiểu caption.

Nguyên nhân gốc: `exam.py prepare` chỉ sinh mục plan cho câu KIS. Bốn câu Q&A
không có anchor nào nên luôn phải dùng nguyên câu hỏi.

**Sửa:**
1. `prepare` sinh mục plan cho **cả câu Q&A** (TRAKE vẫn không).
2. Mỗi anchor **tìm riêng rồi xen kẽ theo thứ hạng**, không gộp RRF — đúng bài học
   đã đo ở KIS (gộp làm R@1 tụt 6/17 → 1/17). Ở p1-3, anchor
   `"a person holding a large fish by its tail"` **không có trong 300 kết quả đầu**;
   gộp là dìm anchor tốt, xen kẽ thì nó chỉ tốn slot.
3. Chặn `build_kis_submission` nhận mục Q&A — nếu không nó ghi đè file Q&A có
   answer bằng bảng KIS không answer, và sẽ im lặng.

Kết quả: `L21_V023` từ **vắng mặt** → **hạng 9**.

---

## 4. Trần cứng: shot không có keyframe

Sau khi có anchor, video đúng vào được top-10 nhưng shot vẫn lệch **1035 frame
(~35 giây)** — cảnh khác hẳn, người soi không nhận ra được.

Đào tiếp thì ra nguyên nhân **không phải xếp hạng**:

```
keyframe 25495   ← gần nhất phía trước
frame    26050   ← ĐÁP ÁN
keyframe 26906   ← gần nhất phía sau
```

Khoảng trống **1411 frame (~47 giây) không có một vector nào trong index**. Shot
chứa đáp án `L21_V023#s0250` [25996, 26059] **có** trong `shots.parquet` nhưng
không có ảnh nào để encode. Tìm kiếm vector không thể đề cử nó — không phải xếp
hạng thấp mà là **không tồn tại để mà xếp**.

**Sửa** theo `CLAUDE.md` §7 (*frame nộp không cần là keyframe đã index*): tự phát
shot cho vùng trống, allocator cấp frame thật bên trong.

- Chỉ shot **không có keyframe nào**, xếp theo khoảng cách tới shot đã đề cử.
- Điểm bám ngay **dưới video mẹ**, không dìm xuống đáy — dìm thì 100 ứng viên thật
  ăn hết slot và shot vùng trống không bao giờ được nộp.
- Đặt **sau** khi `thu_de_suy_luan` đã chốt → **không tốn một lượt LLM nào**.
- Bọc try/except: tính năng phụ, không được kéo sập câu hỏi.

Kết quả cuối: frame **26028**, lệch **22 frame (~0,7 giây)**, nằm gọn trong đúng
shot chứa đáp án.

---

## 5. Còn thiếu — đọc kỹ trước khi tin

1. **Hạng 88 chỉ đáng 0.20 điểm** (bậc 51–100). Từ 0 lên 0.20 là thật, nhưng chưa
   ngon. Muốn lên đầu bảng phải có keyframe ở vùng đó — việc trích frame dày hơn
   của Data Factory, không phải việc của `qa.py`.
2. **Answer vẫn phải đúng.** Q&A có hai cửa tử độc lập; frame lệch 22 mà answer
   sai thì vẫn 0.
3. **Bù vùng trống chỉ chạy khi video đã lọt vào ứng viên** (12 video đầu, 12 shot
   mỗi video). Video đúng không vào được thì vẫn chịu — anchor tốt vẫn là điều
   kiện cần.
4. **Bước 3 `review` chưa dựng lưới ảnh cho Q&A** — `make_exam_review.py` chỉ làm
   cho KIS. Q&A vẫn phải soi tay bằng `contact_sheet.py`.
5. **Anchor của 3 câu p1-9, p1-15, p1-17 chưa ai kiểm bằng ảnh.** Chỉ p1-3 có
   ground truth để đối chiếu.
6. **`0/25 có GT` cho đề đợt 1.** Mọi con số ngoài p1-3 đều không kiểm chứng được.
   Đây là việc đáng làm nhất tiếp theo.

---

## 6. File đã đổi

| File | Đổi gì |
|---|---|
| `backend/tasks/qa.py` | dò từ chối · cổng kiểu · phạt độ sâu · chỗ trống · anchor · bù vùng trống |
| `backend/tasks/qa_portfolio.py` | truyền `answer_mode` vào bộ lọc |
| `backend/tasks/runner.py` | truyền `anchors` xuống `qa_pipeline()` |
| `data/config/qa_hypotheses.py` | toàn bộ ngưỡng/luật mới, không hardcode |
| `scripts/exam.py` | sinh plan cho Q&A · chặn `build_kis_submission` nhận mục Q&A |

## 7. Cách chạy

Không có đường riêng cho Q&A — vẫn bốn bước như KIS:

```bash
python scripts/exam.py prepare <thư-mục-đề>
# bước 1b: Claude điền exam_plan.json (giờ có cả mục Q&A)
python scripts/exam.py run
python scripts/exam.py review
python scripts/exam.py finalize
```

Anchor Q&A viết theo đúng nguyên tắc đã đo: **ngắn, tả cảnh, bỏ hẳn phần hỏi.**
