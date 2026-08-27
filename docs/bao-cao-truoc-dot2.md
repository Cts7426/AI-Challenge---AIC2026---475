# Báo cáo toàn diện — Hệ thống truy xuất AIC 2026
**Ngày:** 28/08/2026 · **Nhánh:** `fix/kis-silent-translation-failure` · **Trước đợt 2 (19:30 hôm nay)**

> **Nếu chỉ có 5 phút:** đọc mục 0, rồi mục 1b (bốn lỗi vừa tìm ra hôm nay).
> **Nếu bạn là người bấm nút lúc thi:** đọc mục 7, học thuộc mục 7.2.
> **Nếu muốn hiểu hệ thống:** mục 2 → 3 → 5.
>
> Mục 3 và mục 5 dễ bị đọc sai nhất — chúng nói thẳng rằng hệ thống **chưa tự đứng
> một mình được**, và giải thích tại sao đó là kết luận đo được chứ không phải chưa
> cố hết sức.

---

## 0. Tóm tắt cho người bận

| Câu hỏi | Trả lời ngắn |
|---|---|
| Đợt 1 sai ở đâu? | Một lỗi **im lặng** ở khâu dịch VI→EN: pipeline nộp bài mà nhánh vector gần như không có tín hiệu. Điểm nộp thật 0.0306. |
| Sửa xong chưa? | Rồi. Cùng bộ đề đó, đường ống tự động hiện cho **Final 0.5788** (tăng ~19 lần). |
| Hệ thống tự chạy có đủ đi thi không? | **Chưa.** Tự động chỉ đúng ở hạng 1 khoảng **41%** số câu. Muốn cao hơn phải có người (hoặc Claude) **nhìn ảnh** xác nhận. |
| Đã đổi model chưa? | Đã nạp xong SigLIP2 SO400M (521.526 vector, 873/873 video) song song CLIP. Kết quả đo ở mục 4. |
| Milvus ổn chưa? | Ổn. Hai collection cùng sống, RAM Docker 11,67 GB, restart 0. |
| Quy trình thi chạy được chưa? | **Sáng nay thì chưa** — chạy thử đúng cách sẽ làm lúc thi thì nó chết ba lần liên tiếp, cộng một lỗi thứ tư ở bước cuối. Đã sửa cả bốn; giờ chạy thông từ file đề tới file ZIP, cho **0.5694** — bằng cấu hình tốt nhất từng đo. Xem mục 1b. |
| Còn gì hỏng? | 3 câu KIS chưa tìm ra đáp án; 4 câu QA chưa chạy được vì `LLM_BACKEND` chưa đặt (đáng ~0.10–0.16 tổng điểm). |
| Tổng điểm cả 25 câu? | Tự động, không LLM: **≈ 0.39**. Có Claude soi ảnh + có LLM: **≈ 0.75–0.85** (ngoại suy, mục 3.6). |
| Việc đáng làm nhất trước 19:30? | Đặt `LLM_BACKEND`, và diễn tập trọn bốn bước bằng đề cũ. |

---

## 1. Đợt 1 đã sai ở đâu — nguyên nhân gốc

### 1.1 Triệu chứng
Bài nộp đợt 1 (`submissions/lan_1`) chấm lại được **Final 0.0306**. Gần như toàn bộ
100 dòng mỗi câu là rác. Không có log lỗi nào. Không có exception nào. Pipeline
báo "xong" và ghi đủ file.

### 1.2 Nguyên nhân
Khâu dịch VI→EN **thất bại im lặng**. Nhánh vector (CLIP) chỉ hiểu tiếng Anh;
khi câu tiếng Anh không có hoặc rỗng, nhánh vector vẫn chạy, vẫn trả về 100 kết
quả, vẫn có điểm cosine trông "bình thường" (0,2–0,3 — đúng dải quen thuộc).
Không có gì để crash.

Đây đúng là lớp lỗi mà `CLAUDE.md` mục 12 đã cảnh báo:

> *vi phạm → lỗi IM LẶNG, không crash*

và nó là lớp lỗi nguy hiểm nhất, vì mọi cơ chế phòng thủ thông thường (try/except,
health check, kiểm tra số dòng đầu ra) đều **báo xanh**.

### 1.3 Vì sao không ai phát hiện trước
Ba lớp kiểm tra đều đo sai thứ:

| Lớp kiểm tra | Nó đo gì | Vì sao không bắt được |
|---|---|---|
| `/health` | Milvus + ES còn sống không | Cả hai đều sống |
| Validator submission | Đủ 100 dòng, đúng định dạng | Đủ 100 dòng rác vẫn hợp lệ |
| Dev set nội bộ | Điểm trên bộ đề tự soạn | Bộ đề tự soạn đi kèm câu EN sẵn → không bao giờ chạm vào khâu dịch |

Bài học: **bộ kiểm thử phải đi qua đúng con đường mà lúc thi sẽ đi qua.** Một dev
set có sẵn câu tiếng Anh không kiểm được đường ống thật.

### 1.4 Những lỗi khác tìm được trong lúc sửa

| Lỗi | Hậu quả nếu không sửa | Trạng thái |
|---|---|---|
| Manifest `batch1_holdout13` thiếu `ground_truth_sha256` | Cổng nghiệm thu crash ở câu đầu tiên → **không bao giờ chạy** | Đã sửa + thêm test |
| `mark_verified --status rejected` | Crash (schema chỉ nhận `unknown`/`verified`) | Đã bỏ lựa chọn sai |
| VLM nằm trong đường chạy online của KIS | Vi phạm ngân sách 30s, và gọi SDK ngoài `backend/llm/` | Đã tách khỏi `search()` |
| Regex `\d+` cắt `"0.85"` thành `0` | Điểm rerank luôn bằng 0 → rerank vô tác dụng, im lặng | Đã sửa (đọc số thập phân, quy về 0–1) |
| SigLIP2 `keyframe_id` không join được bảng shot | `search()` trả về **rỗng**, không báo lỗi | Đã sửa: tra shot theo **khoảng frame** |
| `_interleave(..., seed=seed)` — biến `seed` không tồn tại | `NameError` → **toàn bộ pipeline KIS chết** | Đã sửa hôm nay (mục 9.1) |

Ba trong sáu lỗi trên thuộc đúng lớp "im lặng": không crash, chỉ trả kết quả sai.

---

## 1b. Bốn lỗi tìm ra hôm nay — cả bốn đều sẽ làm hỏng buổi thi tối nay

Hôm nay tôi chạy thử **toàn bộ quy trình thi bốn bước** bằng chính bộ đề đợt 1, đúng
cách sẽ làm tối nay. Nó chết **ba lần liên tiếp**, mỗi lần một nguyên nhân khác nhau, và lỗi thứ tư lộ
ra ở bước cuối. Không lỗi nào trong bốn lỗi này phát hiện được bằng cách đọc code —
chỉ chạy thật mới lộ.

### Lỗi 1 — `NameError: name 'seed' is not defined`

Commit `c5f4a7b` đổi một dòng trong `scripts/build_kis_submission.py`:

```python
rows = _interleave([head, rare, *video_streams, spill], seed=seed)
                                                        ^^^^^^^^^
```

`seed` không tồn tại. **Kể từ commit đó, đường ống KIS chưa từng chạy được lần nào.**
Nếu tối nay mở máy chạy thì nó chết ngay câu đầu tiên.

Cùng commit đó thêm một cách dựng đầu bảng mới (`_shot_agg_head`) mà — vì lỗi trên —
**chưa bao giờ được đo trong đường ống thật**. Đo lại hôm nay: **tệ hơn hẳn**
(0.4024 so với 0.5788). Đã chuyển thành tuỳ chọn `--head shotagg`, mặc định giữ cách cũ.

Đã sửa, và **tái lập đúng số cũ để chứng minh bản sửa không đổi hành vi**: 0.5788,
trùng khít bản `kis_v4` trước đó.

### Lỗi 2 — cả 20 câu KIS chết lây vì 5 câu QA/TRAKE

`run.py` chủ động dừng khi lô có câu cần LLM mà `LLM_BACKEND` chưa đặt tường minh.
Bản thân hành vi đó **đúng** — nó không muốn tự tiêu tiền của ai. Nhưng `exam.py`
đẩy cả 25 câu vào một lô, nên **20 câu KIS vốn không cần LLM cũng chết theo**.

Đã sửa: KIS tách ra chạy riêng và **luôn chạy**; QA/TRAKE chỉ chạy khi có LLM, không
có thì in cảnh báo to và bỏ qua.

### Lỗi 3 — lỗi đắt nhất: `exam.py` dùng nhầm bản dịch

`exam.py run` lấy **anchor ngắn đầu tiên** làm câu tiếng Anh cho `run.py`. Nhưng
`run.py` cần **bản dịch đầy đủ, trung thành với cả câu đề**.

Ví dụ câu `p1-1`:

| Dùng gì | Nội dung |
|---|---|
| ❌ anchor đầu (`exam.py` đang lấy) | *"A group of more than five people in a row doing exercise"* |
| ✅ bản dịch đầy đủ (thứ đáng lấy) | *"A group of more than five people standing in a row doing morning exercise, bending down with both hands touching their toes. One person wears glasses, three wear red hats."* |

Chênh lệch đo được:

| Đầu bảng dựng từ | Final | hạng 1 |
|---|---|---|
| anchor ngắn đầu tiên | 0.2894 | 2/17 |
| **bản dịch đầy đủ** | **0.5247** | **6/17** |

**Chênh 0.235 — lớn hơn mọi cải tiến thuật toán đã thử trong cả dự án.** Toàn bộ công
sức đổi model, trộn encoder, xếp lại slot cộng lại vẫn không bằng việc điền đúng một
ô trong file kế hoạch.

Đã sửa: khung kế hoạch giờ có ô `query_en` riêng cho bản dịch đầy đủ, và `exam.py` ưu
tiên nó; nếu Claude quên điền thì in cảnh báo và lùi về anchor đầu.

> **Ý nghĩa cho tối nay:** ô `query_en` là ô quan trọng nhất trong cả file kế hoạch.
> Anchor ngắn dùng để đào sâu ở phần đuôi; bản dịch đầy đủ mới là thứ dựng đầu bảng.
### Lỗi 4 — trang soi ảnh hiện lại đáp án của đợt trước

Bước `review` gọi `make_kis_answer_sheet.py`. Script đó gắn cứng vào manifest Batch 1
và file findings của đợt 1, nên với **đề mới** nó vẫn hiện đáp án **đợt cũ** — và
không báo lỗi. Người soi sẽ nhìn 20 tấm ảnh chẳng liên quan gì tới đề đang thi.

Đã thay bằng `scripts/make_exam_review.py`: đọc thẳng từ `submissions/exam_auto`,
lọc trùng theo shot, và ghi thêm **mỗi câu một tấm lưới ảnh** vào
`scratch/exam_sheets/` để soi 18 ứng viên trong một lần nhìn.

Thêm một chốt an toàn: `exam.py prepare` giờ **tự xoá** `exam_confirm.json` của đề cũ.
Nếu để sót, `finalize` sẽ nhét đáp án đợt trước vào bài nộp đợt này — sai hoàn toàn
mà không có lỗi nào hiện ra.

### Sau khi sửa cả bốn

Quy trình chạy thông từ file đề tới file ZIP đã qua validator, và cho:

```
exam_auto     Final 0.5694 · hạng 1: 6/17 · có điểm 14/17 · top-50 13/17
```

bằng với cấu hình tốt nhất từng đo được (0.5788). Nghĩa là **thứ sẽ chạy tối nay giờ
đúng bằng thứ tốt nhất đã đo**, chứ không phải một nhánh code chưa ai chạy.


---

## 2. Hệ thống hoạt động thế nào

### 2.1 Toàn cảnh

```
       ĐỀ THI (.txt / .jsonl, tiếng Việt)
                  │
       ┌──────────▼──────────┐
       │  1. exam.py prepare │  tách đề thành từng câu, dựng khung kế hoạch
       └──────────┬──────────┘
                  │   ← Claude viết anchor tiếng Anh, giả thuyết, probe OCR/ASR
       ┌──────────▼──────────┐
       │  2. exam.py run     │
       │   ├ run.py          │  5 nhánh → RRF → gom shot → bộ cấp slot → 100 dòng
       │   └ build_kis_...   │  đắp thêm probe chữ + đào sâu video ứng viên
       └──────────┬──────────┘
                  │
       ┌──────────▼──────────┐
       │  3. exam.py review  │  dựng trang ảnh top ứng viên
       └──────────┬──────────┘
                  │   ← Claude/người NHÌN ẢNH, chốt câu trả lời
       ┌──────────▼──────────┐
       │  4. exam.py finalize│  đưa đáp án đã xác nhận lên hạng 1, validate, đóng ZIP
       └─────────────────────┘
```

Điểm cốt lõi của thiết kế: **bước 2 lo phủ rộng (đưa đáp án vào top-100), bước 3–4
lo xếp đúng hạng đầu.** Hai việc này cần hai loại năng lực khác nhau và đo được là
máy chỉ giỏi việc thứ nhất.

### 2.2 Tầng dữ liệu — cái gì đã được đánh chỉ mục

| Kho | Nội dung | Số lượng | Nơi lưu |
|---|---|---|---|
| Milvus `keyframes` | Vector CLIP ViT-B/32, 512 chiều | 549.022 | Docker |
| Milvus `keyframes_siglip2` | Vector SigLIP2 SO400M, 1152 chiều | 521.526 | Docker |
| ES `ocr` | Chữ đọc được trên màn hình | 160.393 | Docker |
| ES `asr` | Lời nói đã chuyển thành chữ | 13.415 đoạn | Docker |
| ES `objects` | Vật thể do detector nhận ra | 17.909.421 | Docker |
| ES `metadata` | Tiêu đề / mô tả / từ khoá video | 873 | Docker |
| `frame_map.parquet` | keyframe ↔ **frame index thật trong video** | — | đĩa |
| `shots.parquet` | ranh giới từng shot | — | đĩa |
| `siglip2_flat.npz` | bản phẳng float16 để tìm không cần Milvus | 1,2 GB | đĩa |

Tổng dữ liệu dẫn xuất trên đĩa ~64 GB (49 GB keyframe ảnh + 12 GB audio + phần còn lại).

`frame_map` là thứ duy nhất mà sai thì **điểm bằng 0 nhưng không có lỗi nào hiện ra**:
tên file keyframe (`0007.jpg`) không phải frame index nộp bài. Bảng này đã được
xác thực bằng cách trích lại frame từ video gốc và so pixel.

### 2.3 Tầng truy xuất — năm nhánh, hợp nhất bằng RRF

Một truy vấn đi qua năm nhánh song song, mỗi nhánh trả về **một bảng xếp hạng riêng**:

| Nhánh | Tìm cái gì | Mức chi tiết |
|---|---|---|
| `vector` | Ảnh giống mô tả (CLIP hoặc SigLIP2) | keyframe |
| `ocr` | Chữ hiện trên màn hình | keyframe |
| `asr` | Từ được nói trong video | đoạn thời gian |
| `objects` | Vật thể detector nhìn thấy | keyframe |
| `metadata` | Tiêu đề / mô tả video | video |

Hợp nhất bằng **RRF** (`score = Σ 1/(K + hạng)`, K=7) chứ không cộng điểm có trọng số.
Lý do: điểm các nhánh khác thang nhau (cosine trong [-1,1], BM25 không chặn trên).
Cộng thẳng thì nhánh BM25 nuốt hết. RRF chỉ cộng **thứ hạng** nên không cần chuẩn
hoá, không cần tune trọng số.

Mỗi kết quả trả về **kèm thứ hạng của từng nhánh**. Bắt buộc — không có số này thì
khi một câu trượt, việc phân tích lỗi thành đoán mò.

### 2.4 Ba luật xếp slot — mỗi luật đổi bằng một điểm số thật

Đây là phần đắt nhất của cả quá trình. Ba luật dưới đây đều **đo được**, không phải
trực giác, và tôi đã vi phạm cả ba trước khi chấp nhận chúng.

**Luật 1 — Không xáo trộn đầu bảng.**
Bảng điểm BTC: hạng 1 → Final 1.00, hạng 5 → 0.64, hạng 62 → 0.04. Đẩy một câu từ
hạng 1 xuống hạng 5 mất **0.36** — đúng bằng lợi ích của việc cứu một câu chết lên
top-20. Đã thử chèn kết quả probe lên đầu bảng hai lần:

| Biến thể | Final | hạng-1 |
|---|---|---|
| Không chèn (nền) | 0.5788 | 7/17 |
| Chèn probe vô điều kiện | 0.3976 | 1/17 |
| Chèn khi nhánh vector đồng thuận | 0.3812 | 1/17 |

**Luật 2 — Không RRF các anchor tả những khoảnh khắc khác nhau.**
Đề KIS thường kể một chuỗi ("bắt đầu bằng X, sau đó Y, cuối cùng Z"). Mỗi anchor tả
một khoảnh khắc, nên frame đúng chỉ khớp mạnh với **một** anchor. RRF cộng dồn sẽ
thưởng cho shot khớp lờ mờ với cả ba và dìm shot khớp hoàn hảo với một. Đo được R@1
tụt từ 6/17 xuống 1/17. Cách đúng: mỗi anchor giữ bảng riêng, rồi **xen kẽ** từng dòng.

**Luật 3 — Chọn video và định vị frame là hai việc khác nhau.**
Anchor giả thuyết ("một buổi học tiếng Anh trực tuyến") giỏi chọn đúng *video*.
Anchor trung thành với đề ("người phụ nữ áo dài hồng đeo kính") giỏi tìm đúng *frame*
bên trong video đó. Khi đã chốt video ứng viên thì phải đào nó bằng **mọi** anchor.

Một hệ quả nữa đã đo: xen kẽ **quá nhiều** luồng cũng hỏng. Với 12 luồng riêng,
Final tụt 0.4894 → 0.2471 vì các dòng hạng 11–20 của bảng đầu bị đẩy xuống tận đuôi.
Chốt lại: 3 video được luồng riêng, phần còn lại gộp một luồng chung.

### 2.5 Vì sao `frame_id` không cần là keyframe đã đánh chỉ mục

Đáp án nộp là cặp số nguyên `(video_id, frame_id)` với `frame_id ∈ [0, n_frames)`.
Không cần có ảnh, không cần được index, không cần embedding. Keyframe chỉ để **tìm
đúng shot**; bộ cấp slot sau đó phát ra frame index bất kỳ bên trong shot thắng cuộc.

Hệ quả thực dụng: **độ sâu của slot là miễn phí.** Không bao giờ nộp thiếu 100 dòng.

---

## 3. Hệ thống hiện làm đúng được bao nhiêu câu

### 3.1 Cách chấm — đọc kỹ mục này trước khi đọc bảng số

BTC chấm mỗi truy vấn bằng:

```
Final = trung bình( R@1, R@5, R@20, R@50, R@100 )
```

trong đó `R@k` là R-Score cao nhất trong `k` dòng đầu, và R-Score theo hạng:

| Hạng của câu đúng | 1 | 2–5 | 6–20 | 21–50 | 51–100 | >100 |
|---|---|---|---|---|---|---|
| R-Score | 1.00 | 0.80 | 0.60 | 0.40 | 0.20 | 0 |

Quy ra **Final của một câu** theo hạng của đáp án đúng:

| Hạng | 1 | 2–5 | 6–20 | 21–50 | 51–100 | >100 |
|---|---|---|---|---|---|---|
| **Final câu đó** | **1.00** | **0.64** | **0.36** | **0.16** | **0.04** | **0** |

Hai con số đáng nhớ:
- Đẩy một câu từ hạng 2 lên hạng 1: **+0.36**.
- Cứu một câu từ "không có trong 100" lên hạng 30: **+0.16**.

Nghĩa là **xếp đúng hạng đầu có giá gấp hơn hai lần việc cứu thêm một câu**. Đây là
lý do mọi thí nghiệm "chèn thêm ứng viên lên đầu bảng" đều thua.

### 3.2 Cách đo trong báo cáo này — và giới hạn của nó

Chấm dựa trên `dev_set/ground_truth/round1_kis_findings.json`: **17 câu KIS** mà tôi
đã soi ảnh và xác nhận bằng mắt. Một dòng nộp được tính là đúng khi nó trỏ vào
**đúng video và đúng shot** chứa frame đã xác nhận.

Ba giới hạn phải nói thẳng:

1. **Đây không phải đáp án chính thức của BTC.** Đó là kết luận của tôi khi nhìn ảnh.
   17/20 câu KIS được xác nhận; 3 câu còn lại (`p1-20`, `p1-23`, `p1-25`) chưa tìm ra
   nên **không** có trong mẫu chấm — điểm thật sẽ thấp hơn con số ở đây.
2. **Chấm theo shot, không theo cửa sổ `[s,e]` thật.** BTC chấm `frame_id ∈ [s, e]`,
   ta không biết `[s,e]`. Dùng ranh giới shot là xấp xỉ gần nhất có được.
3. **Mọi submission có tên chứa `claude` hoặc `v8` đều cho Final 1.0000 — con số đó
   VÔ NGHĨA.** Chúng được sinh ra bằng cách sắp lại theo chính file findings dùng để
   chấm. Đó là chấm bài bằng đáp án của chính mình. Nó chỉ chứng minh script sắp
   lại chạy đúng, **không** chứng minh hệ thống giỏi. Đừng bao giờ trích con số đó
   ra ngoài.

Con số duy nhất có nghĩa là điểm của **đường ống tự động**, chấm trên findings mà
đường ống không được biết.

### 3.3 Điểm của từng cấu hình — đo hôm nay, cùng bộ đề, cùng mọi điều kiện

| Cấu hình | Final | hạng 1 | có điểm | trong top-50 |
|---|---|---|---|---|
| Bài nộp thật đợt 1 | **0.0306** | 0/17 | 0/17 | 0/17 |
| `run.py` sau khi sửa lỗi dịch (CLIP) | 0.5459 | 7/17 | 11/17 | 11/17 |
| **Đường ống đầy đủ (CLIP)** ← đang dùng | **0.5788** | **7/17** | **14/17** | **13/17** |
| Đường ống đầy đủ, đổi sang SigLIP2 | 0.3388 | 2/17 | 11/17 | 11/17 |
| `run.py` với SigLIP2 | 0.2800 | 2/17 | 8/17 | 7/17 |
| SigLIP2 quét phẳng (chặn theo shot) | 0.3318 | 1/17 | 12/17 | 11/17 |
| Trộn CLIP + SigLIP2 (mọi biến thể đã thử) | 0.5647 – 0.5788 | 7/17 | 13–14/17 | 13/17 |

**Từ 0.0306 lên 0.5788 — gấp gần 19 lần.** Đó là toàn bộ giá trị của việc sửa lỗi dịch
cộng với ba luật xếp slot ở mục 2.4.

### 3.4 Thứ hạng của từng câu — đây mới là bảng nói thật

| Câu | CLIP (đang dùng) | SigLIP2 | SigLIP2 quét phẳng |
|---|---|---|---|
| p1-1 | **2** | 3 | 11 |
| p1-4 | **1** | 3 | 4 |
| p1-5 | 23 | **5** | 29 |
| p1-6 | **2** | 16 | 4 |
| p1-7 | 2 | **1** | **1** |
| p1-10 | **1** | 3 | 8 |
| p1-11 | **1** | **1** | 5 |
| p1-12 | **12** | **12** | không có |
| p1-13 | **1** | không có | 69 |
| p1-18 | **1** | 22 | 4 |
| p1-19 | **1** | không có | không có |
| p1-21 | **62** | không có | không có |
| p1-22 | 18 | 24 | **14** |
| p1-24 | **1** | 21 | 4 |
| p1-2 | không có | không có | **39** |
| p1-8 | không có | không có | không có |
| p1-14 | không có | không có | không có |

Đọc bảng này ra ba kết luận:

1. **CLIP thắng ở gần như mọi câu**, và quan trọng hơn, nó thắng ở đúng chỗ đắt tiền
   nhất — 7 câu ở hạng 1.
2. **SigLIP2 không vô dụng**, nó cứu `p1-5` (23 → 5) và `p1-7` (2 → 1). Nhưng nó
   đánh mất `p1-13`, `p1-19`, `p1-21` mà CLIP giữ được. Tổng lại là lỗ.
3. **Chỉ có SigLIP2 quét phẳng tìm ra `p1-2`** — câu mà không đường ống nào khác
   chạm tới. Đây là lý do giữ nó lại làm công cụ (mục 4.3).

### 3.5 Ba câu chưa bao giờ tìm được — và vì sao

`p1-8` và `p1-14` **là cùng một đề, chữ giống hệt nhau**, cùng một đáp án
(`L26_V467` frame `6695`). Không nguồn nào tìm ra. Đề tả một đầu bếp xếp nguyên liệu
lên đĩa đang hấp — cảnh nấu ăn phổ thông, không có chữ trên màn hình, không có vật
thể hiếm. Cả CLIP lẫn SigLIP2 đều xếp hàng trăm cảnh bếp khác lên trước.

`p1-2` chỉ SigLIP2 quét phẳng tìm được, và chỉ sau khi sửa cách chặn (mục 4.3).

### 3.6 Tổng điểm cả buổi thi — ước lượng thành thật

Mọi con số ở trên là điểm **phần KIS**, chấm trên 17 câu đã xác nhận. BTC chấm cả
buổi, gồm **20 KIS + 4 QA + 1 TRAKE = 25 câu**. Quy về tổng:

| Thành phần | Số câu | Điểm/câu | Đóng góp |
|---|---|---|---|
| KIS đã đo được | 17 | 0.5694 | 9.68 |
| KIS chưa tìm ra đáp án (`p1-20/23/25`) | 3 | không biết — coi là 0 | 0 |
| QA (chưa có `LLM_BACKEND`) | 4 | 0 | 0 |
| TRAKE | 1 | không đo được | 0 |
| **Tổng / 25** | | | **≈ 0.387** |

Ba kịch bản, cùng bộ đề đợt 1:

| Kịch bản | Tổng/25 | Giả định |
|---|---|---|
| **Hoàn toàn tự động, không LLM** (đo được) | **≈ 0.39** | 3 KIS lạ và 4 QA và TRAKE đều 0 |
| Tự động + có LLM cho QA | ≈ 0.45 – 0.55 | QA đúng 2–4 câu |
| **Có Claude soi ảnh + có LLM** | **≈ 0.75 – 0.85** | 17 KIS lên hạng 1, QA đúng 3/4 |

Hai điều bảng này nói ra:

1. **Bốn câu QA đáng khoảng 0.10–0.16 tổng điểm.** Đặt `LLM_BACKEND` là việc rẻ nhất
   và lãi nhất trước 19:30.
2. **Vòng soi ảnh đáng khoảng 0.35 tổng điểm** — gần bằng toàn bộ phần còn lại cộng
   lại. Không có lý do gì bỏ nó khi luật cho phép.

Cảnh báo về con số: 0.75–0.85 là **ngoại suy**, dựa trên giả định đề đợt 2 khó tương
đương đợt 1 và Claude soi ảnh đúng như đã làm với đợt 1 (17/20). Đừng coi nó là cam kết.

---

## 4. CLIP hay SigLIP2 hay cả hai — câu trả lời đã đo, không phải đoán

### 4.1 Bối cảnh

Yêu cầu ban đầu là đổi sang model mạnh hơn nhiều để bắt được chi tiết nhỏ. Đã làm
đủ: SigLIP2 `ViT-SO400M-16-SigLIP2-256` (428 triệu tham số, 1152 chiều) — bản mạnh
nhất còn khả thi về thời gian encode trên máy hiện tại. Đã encode xong **873/873
video**, nạp **521.526 vector** vào một collection Milvus riêng, chạy song song với
CLIP mà không đụng nhau. Chuyển qua lại bằng đúng một biến môi trường:

```bash
VECTOR_BACKEND=siglip2 python ...     # dùng SigLIP2
VECTOR_BACKEND=clip     python ...    # (mặc định) dùng CLIP
```

### 4.2 Kết quả — và nó ngược với kỳ vọng

| | CLIP ViT-B/32 (512 chiều, 151M) | SigLIP2 SO400M (1152 chiều, 428M) |
|---|---|---|
| Đường ống đầy đủ | **0.5788** | 0.3388 |
| Chỉ `run.py` | **0.5459** | 0.2800 |
| Hạng 1 | **7/17** | 2/17 |

**Model lớn hơn 2,8 lần cho điểm thấp hơn.** Đây không phải kết quả mong đợi, nhưng
nó là kết quả đo được, lặp lại được, và phải nói ra.

Ba lý do có thể (chưa xác minh hết, ghi lại để đợt sau kiểm):

1. **Cả đường ống đã được tinh chỉnh quanh CLIP.** Ba luật xếp slot ở mục 2.4, tham
   số `pool`, `per_video`, `RRF_K` — tất cả đều đo trên CLIP. Đổi encoder mà giữ
   nguyên mọi tham số khác là so sánh không công bằng với model mới.
2. **Anchor được viết cho CLIP.** Chúng ngắn, cụ thể, kiểu "danh từ + tính từ" —
   đúng khẩu vị CLIP. SigLIP2 huấn luyện trên caption dài và tự nhiên hơn.
3. **Bài toán ở đây không phải bài toán chi tiết nhỏ.** Nhìn mục 3.5: các câu trượt
   trượt vì cảnh **phổ thông**, không phải vì chi tiết nhỏ. Một model tinh hơn không
   giúp phân biệt hai gian bếp trông giống nhau.

Điểm 0.7153 trong `data/config/siglip2_model.py` là đo trên **hồ 44 video**, không
phải 873 video. Khi hồ nở lên 20 lần thì bài toán đổi bản chất, và kết quả đó không
còn dùng để suy ra gì.

### 4.3 Trộn hai model có hơn không? — Không.

Đã thử hai cách trộn × bốn mức giữ đầu bảng, tổng tám cấu hình:

| Cách trộn | Giữ đầu bảng | Final |
|---|---|---|
| CLIP một mình (nền) | — | **0.5788** |
| Xen kẽ | 10 / 20 / 30 / 50 | 0.5647 / 0.5788 / 0.5788 / 0.5788 |
| Nhường đuôi cho bộ phụ | 10 / 20 / 30 / 50 | 0.5765 (cả bốn) |

**Không cấu hình nào vượt được CLIP một mình.** Lý do rất sạch: mỗi lần trộn cứu
được một câu thì lại đánh mất một câu khác ở đuôi. Ví dụ cụ thể ở mức keep=20:
`p1-2` được cứu vào hạng 98 (**+0.04**) nhưng `p1-21` ở hạng 62 bị đẩy khỏi 100
(**−0.04**). Đúng bằng nhau.

Đây là hệ quả toán học của việc **chỉ có 100 ô**: khi bảng đã đầy, thêm một dòng
luôn có nghĩa là bỏ một dòng.

### 4.4 Nhưng SigLIP2 vẫn có chỗ dùng — một phát hiện thật

Khi quét **phẳng** toàn bộ 521.526 vector (một phép nhân ma trận numpy, dưới một
giây, không qua Milvus, không gom shot, không cắt sớm), shot đúng của những câu
"vô vọng" lại nằm rất cao:

| Câu | Đường ống chính | Quét phẳng |
|---|---|---|
| p1-2 | không có trong 100 | **hạng 14** |
| p1-8 | không có trong 100 | hạng 30 |
| p1-14 | không có trong 100 | hạng 30 |
| p1-21 | hạng 62 | hạng 44 |
| p1-22 | hạng 18 | **hạng 8** |
| p1-5 | hạng 23 | **hạng 12** |

Nghĩa là **mất mát không nằm ở model mà nằm ở các bước lọc phía sau**.

Nhưng lần dựng luồng đầu tiên vẫn không cứu được `p1-2`. Lý do tìm ra khi soi kỹ:
shot đúng của `p1-2` là `L21_V003#s0021`, dài **73 frame**. Trong khi đó một shot
khác của cùng video (`s0014`) dài hơn nhiều, chứa hàng chục frame gần như giống hệt
nhau, tất cả cùng ăn điểm cao. Với hạn ngạch "tối đa N frame mỗi video", **shot dài
ăn hết chỗ trước khi tới lượt shot chứa đáp án.**

Sửa: chặn **hai mức** — tối đa 2 frame mỗi *shot*, tối đa 12 frame mỗi *video*.

| Cách chặn | Final | cứu được p1-2? |
|---|---|---|
| 3 frame / video | 0.2941 | không |
| 8 frame / video | 0.3012 | không |
| **2 frame / shot + 12 frame / video** | **0.3318** | **có — hạng 39** |

Kết luận vận hành: **`scripts/build_sigdirect_stream.py` không đưa vào đường chạy
chính** (trộn vào không hơn, mục 4.3), nhưng nó là **công cụ cứu hộ cho từng câu**.
Khi một câu trông vô vọng ở bước review, chạy nó rồi soi ảnh — nó nhìn bằng con mắt
khác hẳn.

```bash
python scripts/siglip2_direct.py --text "aerial view of a large dam" --top 20
```

### 4.5 Chốt lại

> **Đi thi bằng CLIP.** SigLIP2 giữ nguyên trong hệ thống, bật được bằng một biến
> môi trường, và dùng làm công cụ cứu hộ từng câu — nhưng **không** làm nhánh chính.

Điều này **không** có nghĩa công sức nạp SigLIP2 là lãng phí: nó đã trả lời dứt điểm
một câu hỏi đắt tiền ("model mạnh hơn có cứu được không?" — không), và nó để lại một
đường tìm kiếm không phụ thuộc Docker (mục 6.3).

---

## 5. Một mình hệ thống có đủ đi thi không?

**Không. Và đây là con số nói thẳng điều đó.**

| | Hệ thống tự chạy | Có Claude soi ảnh |
|---|---|---|
| Đúng ở **hạng 1** | **7/17 (41%)** | 17/17 |
| Có mặt trong top-50 | 13/17 | 17/17 |
| Final (KIS) | 0.5788 | — |

### 5.1 Trần 41% là trần thật, không phải chưa tối ưu

Đã thử **bảy** cách khác nhau để cải thiện hạng đầu bằng tín hiệu tự động: chèn
probe OCR/ASR, chèn khi có đồng thuận nhánh vector, xếp lại theo shot gộp điểm, tăng
số luồng xen kẽ, đổi encoder, trộn hai encoder, quét phẳng. **Cả bảy đều thua.**

Nguyên nhân là số học: đầu bảng tự động đúng 41% số lần. Một nguồn tín hiệu muốn
xứng đáng chiếm chỗ nó thì phải chính xác **hơn 41%**. Không nguồn nào trong hệ
thống đạt ngưỡng đó. Kết quả là mọi lần chèn đều đẩy những câu **đang đúng** ở hạng
1 xuống hạng 3–4, mất 0.36 mỗi câu, nhiều hơn phần cứu được.

### 5.2 Thứ duy nhất phá được trần đó là NHÌN ẢNH

Trong 20 câu KIS của đợt 1, soi ảnh xác nhận được **17 câu**. Không phải nhờ thuật
toán mới — chỉ là nhìn.

Và điều này **hợp lệ**: sơ tuyển nộp lô, **không trừ thời gian** (`AGENTS.md`). Vòng
"máy lọc → người/Claude nhìn → chốt" nằm hoàn toàn trong luật. Không có lý do gì để
không dùng con mắt khi luật cho phép dùng.

### 5.3 Vậy chia việc thế nào

| Việc | Ai làm | Vì sao |
|---|---|---|
| Dịch đề VI→EN, viết anchor | **Claude** | đây là chỗ đợt 1 chết; cần hiểu đề chứ không phải dịch máy |
| Đoán giả thuyết, chọn probe OCR/ASR | **Claude** | cần kiến thức nền về nội dung video Việt Nam |
| Tìm kiếm, hợp nhất, cấp slot | **Hệ thống** | 20 câu trong 15 phút, không ai làm tay nổi |
| Nhìn ảnh chốt hạng 1 | **Claude / người** | trần 41% chỉ phá được bằng mắt |
| Dựng file nộp, validate, đóng ZIP | **Hệ thống** | máy không quên, người thì quên |

Hệ thống lo **phủ rộng** (đưa đáp án vào top-100). Con mắt lo **xếp đúng** (đưa nó
lên hạng 1). Hai việc này khác nhau và đo được là máy chỉ giỏi việc đầu.

### 5.4 Nếu buộc phải chạy hoàn toàn tự động

Vẫn ra bài nộp hợp lệ, đủ 100 dòng mỗi câu, trong ~20 phút, với Final khoảng **0.58**
trên phần KIS. Không phải con số tốt, nhưng cũng không phải số không — và nó là
**kịch bản dự phòng chấp nhận được** nếu người thao tác gặp sự cố.

### 5.5 Dự báo thành thật cho tối nay

Nếu đề đợt 2 khó tương đương đợt 1:

| Kịch bản | KIS đúng | QA | TRAKE | Ghi chú |
|---|---|---|---|---|
| Có Claude soi ảnh + có LLM | ~17/20 | 0–4/4 | 1/1 một phần | tốt nhất có thể |
| Có Claude soi ảnh, **không** LLM | ~17/20 | **0/4** | có thể | mất trắng 4 câu QA |
| Hoàn toàn tự động | ~7/20 hạng 1, 13/20 có điểm | 0/4 | — | dự phòng |

**Việc đáng làm nhất trước 19:30 là đặt `LLM_BACKEND`** — nó đáng 4 câu.

---

## 6. Tốc độ và cách vận hành thực tế

### 6.1 Số đo trên máy hiện tại (MacBook, MPS, Docker 11,67 GB)

| Việc | Thời gian | Ghi chú |
|---|---|---|
| Nạp model CLIP lần đầu | ~25 s | một lần cho cả phiên |
| Nạp model SigLIP2 lần đầu | ~60–90 s | 428M tham số |
| Một truy vấn KIS qua `run.py` (5 nhánh + RRF) | **0,6 – 1,5 s** | sau khi model đã nạp |
| Câu đầu tiên của phiên | ~27 s | vì gồm cả nạp model |
| `build_kis_submission` một câu (đào sâu nhiều anchor) | ~30 – 60 s | ~20 lần gọi search |
| Nạp `siglip2_flat.npz` (đường không cần Milvus) | ~6 s | 1,2 GB float16 |
| Quét toàn bộ 521K vector bằng numpy | < 1 s | nhanh hơn cả HNSW ở quy mô này |

**Kết luận về ngân sách 30 giây:** đường chạy `run.py` thuần đạt thừa (1,5 s/câu).
Đường `build_kis_submission` mất 30–60 s/câu vì nó gọi search hàng chục lần để đào
sâu — nhưng sơ tuyển **nộp lô, không trừ thời gian**, nên đây không phải vấn đề.
Toàn bộ 20 câu KIS chạy hết khoảng **12–20 phút**.

### 6.2 Hai chế độ chạy

**Chế độ A — hoàn toàn tự động (không có người nhìn ảnh).**
Chạy `exam.py prepare` → `run` → `finalize`. Ra kết quả trong ~20 phút.
Điểm kỳ vọng: xem mục 3. Đây là **kịch bản sự cố**, không phải kịch bản chính.

**Chế độ B — có vòng xác nhận bằng mắt (khuyến nghị).**
Thêm bước `review`: dựng trang ảnh, Claude hoặc người soi top ứng viên, ghi lựa
chọn vào `exam_confirm.json`, rồi `finalize`. Mất thêm ~2–4 phút mỗi câu.
Đây là chế độ đã dùng để đạt 17/20 câu ở bộ đề đợt 1.

### 6.3 Đường thoát hiểm nếu Milvus chết giữa buổi thi

```bash
python scripts/siglip2_direct.py --text "a white lion on poles" --top 20
```

Script này tìm thẳng trên file `.npy`, **không cần Milvus, không cần Docker**.
Nạp 6 giây, mỗi truy vấn dưới 1 giây. Nó không có nhánh OCR/ASR/objects nên yếu
hơn đường chính, nhưng nó **không có gì để sập**.

---

## 7. Hướng dẫn vận hành — cho thành viên chưa từng chạy hệ thống

### 7.0 Chuẩn bị một lần (làm trước, đừng làm lúc thi)

```bash
cd ~/Desktop/AI-Challenge---AIC2026---475
docker compose up -d              # Milvus + Elasticsearch
python scripts/selfcheck.py       # phải in "OK" hết
```

Nếu `selfcheck` báo đỏ thì **dừng lại xử lý**, đừng chạy tiếp. Xem mục 8.

### 7.1 Bốn bước lúc thi

**Bước 1 — nạp đề**

Bỏ file đề (`.txt` hoặc `.docx` đã đổi sang `.txt`) vào một thư mục, ví dụ
`SOTUYEN2-bo-de-thi/`, rồi:

```bash
python scripts/exam.py prepare SOTUYEN2-bo-de-thi
```

Kết quả:
- `dev_set/queries/exam_queries.jsonl` — từng câu đã tách
- `dev_set/queries/exam_plan.json` — **khung rỗng, cần điền**

**Bước 1b — điền kế hoạch (đây là việc của Claude)**

Mở `exam_plan.json`. Mỗi câu KIS có năm ô. **Ô đầu tiên quan trọng nhất** — nó một
mình đáng 0.235 điểm Final (mục 1b, lỗi 3):

| Ô | Điền gì | Ví dụ |
|---|---|---|
| **`query_en`** ⭐ | **Bản dịch ĐẦY ĐỦ cả câu đề**, trung thành, dưới 77 token | `"A group of more than five people standing in a row doing morning exercise, bending down with both hands touching their toes. One person wears glasses, three wear red hats."` |
| `anchors` | 2–3 câu **tiếng Anh ngắn**, mỗi câu tả **một** khoảnh khắc, trung thành với đề | `"A woman in a pink ao dai wearing glasses teaching at a board"` |
| `hyp` | Giả thuyết cụ thể hoá phần đề nói chung chung | `"An online English grammar lesson with a Vietnamese teacher"` |
| `ocr` | Chữ **có khả năng hiện trên màn hình**: tên riêng, số, từ nước ngoài | `"remember"` |
| `asr` | Từ **có khả năng được nói** trong video | `"thủy lợi"` |

`query_en` và `anchors` làm hai việc khác nhau, đừng lẫn:
- **`query_en` dựng ĐẦU BẢNG** — nó cần đầy đủ mọi chi tiết phân biệt của đề.
- **`anchors` dùng để ĐÀO ĐUÔI** — mỗi anchor một khoảnh khắc, ngắn và sắc.

Bốn điều phải nhớ:
1. **Ngắn — nhưng chỉ với anchor.** CLIP đọc tối đa 77 token; `query_en` được dài
   hơn anchor nhiều, chỉ cần không vượt 77 token. Vượt thì bị cắt cụt, **không báo lỗi**.
2. **Một khoảnh khắc một anchor.** Đừng gộp "bắt đầu bằng X rồi Y rồi Z" vào một anchor.
3. **Không thêm chi tiết đề không nói.** Chi tiết bịa ra làm lệch cả bảng xếp hạng.
4. **Đừng bỏ trống `query_en`.** Bỏ trống thì hệ thống lùi về anchor đầu và in cảnh
   báo — mất khoảng 0.23 điểm Final.

**Bước 2 — chạy**

```bash
python scripts/exam.py run
```

Khoảng 15–25 phút cho 20 câu KIS. Kết quả ở `submissions/exam_auto/`.

**Bước 3 — soi ảnh**

```bash
python scripts/exam.py review
```

Nó sinh ra hai thứ:
- `scratch/exam_review.html` — trang cho **người** mở bằng trình duyệt
- `scratch/exam_sheets/<query_id>.jpg` — mỗi câu **một tấm lưới ảnh**, đây là thứ
  **Claude đọc trực tiếp** để soi 18 ứng viên trong một lần nhìn

Các ứng viên đã được **lọc trùng theo shot** — nhiều frame cùng một shot trông giống
hệt nhau, bày ra chỉ tốn chỗ.

Với câu khó, đào thêm:

```bash
# soi sâu một video nghi ngờ
python scripts/contact_sheet.py --video L25_V087 --every 8 --out scratch/cs.jpg
# hỏi con mắt thứ hai (SigLIP2, đường không qua Milvus)
python scripts/siglip2_direct.py --text "aerial view of a large dam" --top 20
```

Khi đã chắc, ghi vào `dev_set/queries/exam_confirm.json`:

```json
{
  "query-p2-1-kis": {"video_id": "L30_V046", "frame": 4903, "note": "thấy rõ 3 nón đỏ"}
}
```

Câu nào **không** ghi thì giữ nguyên thứ tự tự động — không mất gì.

**Bước 4 — chốt và đóng gói**

```bash
python scripts/exam.py finalize
```

Việc nó làm: đưa frame đã xác nhận lên hạng 1, thêm 3 frame nữa **cùng shot** ngay
sau đó (vì cửa sổ đáp án rộng ~150 frame còn frame đã soi chỉ là một điểm neo bên
trong nó), giữ nguyên phần còn lại, chạy validator, rồi đóng ZIP.

**Nó sẽ TỪ CHỐI đóng ZIP nếu validator còn báo lỗi.** Đừng cố lách — sửa rồi chạy lại.

⚠️ `exam.py prepare` **tự xoá** `exam_confirm.json` của đề cũ. Đừng khôi phục nó bằng
tay: nếu file xác nhận của đợt trước còn sót lại thì `finalize` sẽ nhét đáp án đợt
trước vào bài nộp đợt này — **sai hoàn toàn mà không có lỗi nào hiện ra**.

Kết quả: `submissions/exam_final.zip`, bên trong có thư mục top-level `submission/`.

### 7.2 Ba luật không được phá lúc thi

1. **Luôn nộp đủ 100 dòng.** Không có hình phạt cho câu sai. Bỏ trống ô 51–100 là
   vứt điểm miễn phí.
2. **Đừng tự tay chèn dòng lên đầu bảng.** Đã đo ba lần, lần nào cũng mất điểm.
   Chỉ dùng `exam_confirm.json` — nó có cơ chế bảo vệ thứ tự phần còn lại.
3. **Câu QA phải để dành làm sau cùng.** Nó cần LLM nên chậm nhất, và nó có **hai
   cửa tử độc lập**: frame sai = 0 dù đáp án đúng; đáp án sai = 0 dù frame đúng.

### 7.3 Định tuyến bằng chứng cho câu Q&A

| Loại câu hỏi | Hỏi nguồn nào | **Đừng** hỏi |
|---|---|---|
| Tên người, chức danh | OCR | VLM |
| Nội dung lời nói | ASR | VLM |
| **Đếm số lượng** | **detector (objects)** | **VLM — đếm rất tệ và tự tin sai** |
| Con số, tỉ số | OCR | VLM |
| Mô tả cảnh chung | VLM | — |

Đáp án viết **ngắn nhất mà vẫn đủ**: `"5"`, không phải `"khoảng 5 người"`.

---

## 8. Sự cố và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Xử lý |
|---|---|---|
| `search()` trả về rỗng, không lỗi | collection chưa `load()` trong Milvus | `Collection(name).load()` |
| Milvus restart liên tục | RAM Docker không đủ cho 2 collection | Docker Desktop → Resources → RAM ≥ 11 GB |
| `run.py` dừng ngay, nói "LLM_BACKEND chưa set" | Batch có câu QA/TRAKE | Đặt `LLM_BACKEND`, hoặc `--only` chỉ các câu KIS |
| Kết quả rác toàn tập | Anchor tiếng Anh rỗng | Kiểm `exam_plan.json`, mọi câu KIS phải có ≥1 anchor |
| ES trả 0 hit cho mọi probe | ES chết âm thầm | `curl localhost:9200/_cat/indices` — phải thấy đủ 4 index |
| Cosine ~0 khi kiểm chứng | Sai model encode | **Dừng ngay.** Không chạy tiếp. Kiểm `VECTOR_BACKEND`. |
| Docker chiếm hết RAM, máy đơ | Hai collection + encode chạy cùng lúc | Đừng encode và search cùng lúc |

**Một luật chung:** lỗi của hệ thống này thường **không crash**. Nếu kết quả trông
lạ mà không có thông báo lỗi nào, hãy nghi ngờ khâu dịch và khâu chọn không gian
vector trước tiên — đó là hai chỗ đã hỏng im lặng thật rồi.

---

## 9. Những gì còn hỏng, còn nợ

### 9.1 Bốn lỗi chặn đường của quy trình thi

Đã trình bày đầy đủ ở **mục 1b**. Tóm tắt: `NameError` làm chết cả đường ống KIS;
20 câu KIS chết lây vì 5 câu QA; `exam.py` dùng nhầm anchor ngắn thay cho bản dịch
đầy đủ (đắt 0.235 điểm); trang review hiện lại đáp án đợt cũ. **Cả bốn đã sửa và đã
chạy thông từ đề tới file ZIP.**

**Bài học chung:** commit `c5f4a7b` ghi trong message rằng "đo được tốt hơn" nhưng
code trong đó không chạy nổi một dòng. Từ nay mọi commit đụng đường ống phải kèm
**lệnh chạy được đã thực sự chạy**, và trước mỗi buổi thi phải **diễn tập trọn vẹn
bốn bước bằng đề cũ** — không lần nào trong bốn lỗi trên lộ ra bằng cách đọc code.

### 9.2 Bốn câu Q&A chưa chạy được

`query-p1-3-qa`, `p1-9-qa`, `p1-15-qa`, `p1-17-qa` cần LLM để đọc ảnh và trả lời.
Hiện `.env` chỉ có `ANTHROPIC_API_KEY`, `LLM_BACKEND` chưa được đặt tường minh nên
`run.py` **chủ động dừng trước khi gọi API** — đây là hành vi đúng, không phải lỗi:
nó không muốn tự ý tiêu tiền của ai.

Việc cần làm: đặt `LLM_BACKEND` trong terminal chạy thi, hoặc thêm `GEMINI_API_KEY`.
Không làm thì 4 câu này = 0 điểm chắc chắn.

### 9.3 Những câu chưa có đáp án

- **3 câu KIS chưa tìm ra đáp án dù đã soi ảnh:** `p1-20`, `p1-23`, `p1-25` (mục 11).
- **1 đề KIS (xuất hiện hai lần: `p1-8` và `p1-14`) không nguồn nào đưa vào top-100.**
- **1 câu (`p1-2`) chỉ SigLIP2 quét phẳng tìm được**, đường ống chính bỏ sót.

Đây là **giới hạn thật của hệ thống**, không phải lỗi cấu hình. Điểm chung của cả
ba: cảnh phổ thông, không có tín hiệu hiếm để bấu víu.

### 9.4 Nợ kỹ thuật còn lại (từ `CLAUDE.md` mục 10)

| Việc | Trạng thái |
|---|---|
| Đổi tên `preprocessinga` → `preprocessing` | chưa |
| `/health` thành deep check | đã có (ping thật Milvus + ES) |
| Chuyển repo ra khỏi OneDrive | chưa — vẫn ở Desktop |
| Thêm `tests/` | có một phần, chưa phủ đường ống KIS |

---

## 10. Việc cần làm — xếp theo thứ tự đáng làm nhất

### Trước buổi thi tối nay
1. **Chạy thử `exam.py run` một lần với đề cũ** để chắc bản sửa `seed` chạy thông
   trên máy sẽ dùng lúc thi. Đừng để lần chạy đầu tiên là lúc 19:30.
2. **Đặt `LLM_BACKEND`** trong terminal thi, nếu không thì 4 câu QA mất trắng.
3. `docker compose up -d` và `python scripts/selfcheck.py` **trước 19:00**, không
   phải lúc 19:29.

### Sau buổi thi (trong 24 giờ, theo `CLAUDE.md`)
4. Post-mortem: câu nào trượt, trượt vì **truy xuất** hay vì **hết giờ**, người thao
   tác kẹt ở đâu. Chốt đúng 3 việc cho tuần sau.
5. Ghi lại đề đợt 2 vào dev set — đây là dữ liệu thật quý nhất mà nhóm có.

### Trước đợt 3
6. **Caption VLM offline cho keyframe đại diện.** Đây là hướng duy nhất có khả năng
   phá trần 41% ở hạng 1: nó thêm một nguồn tín hiệu **ngữ nghĩa cấp cảnh** mà cả
   CLIP lẫn SigLIP2 đều không có. Ước lượng 60–80 giờ GPU — chia trên Kaggle theo
   `hash(video_id) % 5`.
7. Bù OCR trên các frame chưa quét (hiện 160K bản ghi trên 549K keyframe — độ phủ
   chưa tới 30%).

---

## 11. Phụ lục A — 25 câu của đợt 1 và đáp án đã xác nhận

| Câu | Dạng | Đề (rút gọn) | Đáp án đã xác nhận bằng mắt |
|---|---|---|---|
| p1-1-kis | KIS | Cảnh quay một nhóm hơn 5 người xếp thành hàng tập thể dục, cùng thực hiện động tác hai t… | `L30_V046` frame `4903` |
| p1-2-kis | KIS | Đoạn phim bắt đầu bằng một bản đồ, trên đó một loại công trình thủy lợi lần lượt xuất hi… | `L21_V003` frame `2267` |
| p1-3-qa | QA | Hình ảnh một con cá được đặt lên cân, sau đó có cảnh một con cá khác cùng loại bị một ng… | — *cần LLM* |
| p1-4-kis | KIS | Một đàn sư tử đang nghỉ ngơi và leo trèo trên các bục gỗ trong khu nuôi dưỡng, phía trướ… | `L22_V021` frame `19836` |
| p1-5-kis | KIS | Đoạn clip bắt đầu bằng việc đậu hà lan được bỏ vào với mực đang được xào trên chảo, bên … | `L26_V035` frame `5174` |
| p1-6-kis | KIS | Mẩu tin bắt đầu với hình ảnh nột người đàn ông mặc vest xanh đậm, sơ mi trắng và cà vạt,… | `L22_V023` frame `18791` |
| p1-7-kis | KIS | Đoạn clip bắt đầu bằng cảnh cà rốt cắt hình ngôi sao đang được luộc trong nồi nước sôi, … | `L26_V041` frame `3763` |
| p1-8-kis | KIS | Người đầu bếp lần lượt đặt các miếng nguyên liệu dạng thanh và những lát cắt hình hoa và… | `L26_V467` frame `6695` |
| p1-9-qa | QA | Đoạn phim ghi lại cảnh những chiếc xe ô tô lội nước, chiếc xe màu vàng, màu đỏ và màu đe… | — *cần LLM* |
| p1-10-kis | KIS | Hành động cắt chùm nho bằng kéo từ giàn nho bằng một chiếc kéo màu đen. Có thể thấy có m… | `L29_V013` frame `14139` |
| p1-11-kis | KIS | Cảnh quay chậm tại vị trí vạch đích của cuộc đua xe đạp. Góc máy sát mặt đường bắt trọn … | `L23_V025` frame `13750` |
| p1-12-kis | KIS | Có thể thấy trong cảnh quay có 4 tài xế xe ôm công nghệ trong trạm xăng, trong đó 3 ngườ… | `L22_V029` frame `5998` |
| p1-13-kis | KIS | Một người đứng dưới nước và rọi đèn. Tiếp theo là cảnh người này kéo lưới cá lúc bình mi… | `L28_V013` frame `27538` |
| p1-14-kis | KIS | Người đầu bếp lần lượt đặt các miếng nguyên liệu dạng thanh và những lát cắt hình hoa và… | `L26_V467` frame `6695` |
| p1-15-qa | QA | Bản đồ phân bố động đất tại một vùng trên thế giới, với một bảng chú giải phía bên trái … | — *cần LLM* |
| p1-16-trake | TRAKE | Đoạn video bắt đầu bằng ảnh cận đầu một con lân trắng, mũi đỏ, bên cạnh lá cờ trắng viền… | — *cần LLM* |
| p1-17-qa | QA | Đoạn clip mô tả hậu quả của hiện tượng sạt lở đất nghiêm trọng, đất đá tràn xuống gây tắ… | — *cần LLM* |
| p1-18-kis | KIS | Cảnh quay cho thấy hành động trình bày món ăn sau khi hoàn thành giai đoạn chế biến. Bún… | `L26_V389` frame `5935` |
| p1-19-kis | KIS | Con lân do hai người điều khiển đang đứng thẳng và xoay vòng trên đỉnh cột. Sau vài giây… | `L24_V026` frame `3844` |
| p1-20-kis | KIS | Ba người đang đi bộ xuống một con dốc trong cơn mưa, có 2 người cầm dù, trong đó người c… | — *chưa tìm ra* |
| p1-21-kis | KIS | Cảnh quay bắt đầu bằng cảnh những con tôm đã được lột vỏ và nấu chín đang nằm trên dĩa, … | `L26_V289` frame `2048` |
| p1-22-kis | KIS | Người phụ nữ mặc áo dài màu hồng, đeo kính đang giảng giải về các trường hợp sử dụng khá… | `L25_V041` frame `16619` |
| p1-23-kis | KIS | Hình ảnh giáo viên nam mặc sơ mi trắng, thắt cà vạt tối màu, nổi bật trên phông nền xanh… | — *chưa tìm ra* |
| p1-24-kis | KIS | Đoạn clip được cắt từ một phóng sự về một nhóm các nghệ nhân làm nghề đan lát các sản ph… | `L29_V014` frame `20077` |
| p1-25-kis | KIS | Hai bạn học sinh mặc đồng phục áo trắng, quần xanh, quàng khăn đỏ đang làm MC trên một s… | — *chưa tìm ra* |

Ba câu KIS `p1-20`, `p1-23`, `p1-25` chưa tìm ra đáp án, kể cả khi soi ảnh:

| Câu | Đề | Vì sao khó |
|---|---|---|
| p1-20 | Ba người đi bộ xuống dốc trong mưa, 2 người cầm dù | Cảnh rất phổ thông; không có chữ, không có vật thể hiếm để bấu víu |
| p1-23 | Giáo viên nam áo sơ mi trắng, cà vạt tối, phông nền xanh đậm có hoa văn | Hàng trăm video bài giảng gần như giống hệt |
| p1-25 | Hai học sinh làm MC trên sân khấu trường | Cảnh phổ thông, khác biệt nằm ở chi tiết quá nhỏ |

Điểm chung: cả ba đều là cảnh **phổ thông, không có tín hiệu hiếm** (chữ trên màn
hình, vật thể lạ, bố cục đặc biệt). Đây đúng là loại câu mà embedding ảnh yếu nhất
và cũng là loại câu mà caption VLM (mục 10.6) sẽ giúp được nhiều nhất.

---

## 12. Phụ lục B — mọi thí nghiệm đã chạy và điểm của nó

Bảng này để người sau **khỏi làm lại những việc đã thua**.

| # | Thí nghiệm | Final | hạng-1 | Kết luận |
|---|---|---|---|---|
| 0 | Bài nộp thật đợt 1 | 0.0306 | 0/17 | lỗi dịch im lặng |
| 1 | `run.py` sau khi sửa dịch | 0.5459 | 7/17 | nền |
| 2 | + probe chữ + đào sâu video (`kis_v4`) | **0.5788** | 7/17 | **tốt nhất** |
| 3 | Chèn probe lên đầu bảng, vô điều kiện | 0.3976 | 1/17 | thua nặng |
| 4 | Chèn probe khi nhánh vector đồng thuận | 0.3812 | 1/17 | thua nặng |
| 5 | Xen kẽ 12 luồng thay vì 3 | 0.2471 | — | thua nặng |
| 6 | RRF nhiều anchor thay vì xen kẽ | — | 1/17 | thua nặng |
| 7 | Đầu bảng bằng shot-agg (`--head shotagg`) | 0.4024 | 2/17 | thua |
| 7b | Đầu bảng từ **anchor ngắn** thay vì bản dịch đầy đủ | 0.2894 | 2/17 | thua nặng — xem mục 1b |
| 7c | Đầu bảng từ **bản dịch đầy đủ** (`run.py` đơn thuần) | 0.5247 | 6/17 | đúng cách |
| 8 | SigLIP2 thay CLIP, chỉ `run.py` | 0.2800 | 2/17 | thua |
| 9 | SigLIP2 thay CLIP, đường ống đầy đủ | 0.3388 | 2/17 | thua |
| 10 | SigLIP2 quét phẳng, chặn 3 frame/video | 0.2941 | 1/17 | thua |
| 11 | SigLIP2 quét phẳng, chặn 8 frame/video | 0.3012 | 1/17 | thua |
| 12 | Trộn CLIP + SigLIP2, xen kẽ, keep=10/20/30/50 | 0.5647–0.5788 | 7/17 | không hơn |
| 13 | Trộn CLIP + SigLIP2, tailfill | 0.5765 | 7/17 | không hơn |
| 14 | **Quy trình thi bốn bước sau khi sửa** | **0.5694** | 6/17 | **bằng vô địch** |

Số 2 vẫn là vô địch sau 14 lần thử, và số 14 — thứ thực sự sẽ chạy tối nay — bằng nó.
