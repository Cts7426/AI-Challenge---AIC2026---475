# Post-mortem đợt 1 — vì sao bộ đáp án KIS gần như sai hết

> Viết 27/08/2026. Dành cho cả nhóm. Số liệu trong file này đều đo được, lệnh
> tái lập ghi ở cuối mỗi mục.

## Tóm tắt cho người vội

Bộ KIS nộp đợt 1 **không sai vì model kém, mà vì một bước dịch hỏng âm thầm**.
Tài khoản Anthropic hết credit → `search()` không dịch được câu hỏi sang tiếng
Anh → rơi về dùng nguyên tiếng Việt → CLIP (huấn luyện bằng tiếng Anh) suy biến
→ nhánh vector trả về cùng một cụm video ôn thi THPT cho **mọi** câu hỏi.

Không có crash. Không có log lỗi. Mỗi câu vẫn đủ 100 dòng. Đúng loại "lỗi im
lặng" CLAUDE.md mục 12 cảnh báo.

| Trạng thái | Final Score | Ăn điểm | Trong top-50 |
|---|---|---|---|
| Bộ đã nộp đợt 1 | **0.0392** | 2/17 | 2/17 |
| Sau khi sửa khâu dịch | 0.4894 | 11/17 | 10/17 |
| Sau khi sửa thêm định tuyến truy vấn | **0.5388** | 15/17 | 14/17 |

Đo trên 17 câu KIS vòng 1 đã xác minh bằng mắt
(`dev_set/ground_truth/round1_kis_findings.json`).

---

## 1. Nguyên nhân gốc

Chuỗi sự kiện, mỗi mắt xích đều "xử lý lỗi đúng cách" nhưng cộng lại thành thảm hoạ:

1. **Hết credit API.** Anthropic trả HTTP 400 `credit balance is too low`.
2. **Bước dịch VI→EN thất bại.** Nó nằm trong `search()`, gọi qua `llm()`.
3. **`try/except` bắt lỗi và rơi về tiếng Việt** — `query_en = query_vi`. Đoạn
   này *cố ý* được viết như vậy để một service chết không kéo sập cả truy vấn.
   Ý định đúng, nhưng hậu quả không ai lường.
4. **CLIP nhận tiếng Việt.** `clip-ViT-B-32` chỉ hiểu tiếng Anh; đưa tiếng Việt
   vào tokenizer thì vector suy biến.
5. **Nhánh vector dạt về một cụm.** Mọi câu hỏi — cắt nho, đan lát, tập thể dục
   — đều trả về nhóm video *"BÍ QUYẾT ÔN THI THPT 2024"* (slide + người nói,
   nhìn đồng nhất trong không gian vector suy biến).

### Dấu vân tay trong chính file đã nộp

- **18/20 câu KIS** có đáp án hạng 1 rơi vào cùng cụm `L25`.
- Bốn nhóm câu **không liên quan gì nhau** lại trùng y hệt dòng hạng 1. Ví dụ
  câu "nhóm người tập thể dục" và câu "nướng tôm" cùng trỏ `L25_V024:31287`.

### Đã loại trừ nguyên nhân dữ liệu

Trước khi kết luận, đã kiểm chính vector trong Milvus: encode lại 3 ảnh keyframe
gốc của BTC rồi so cosine với vector đã lưu → **1.0000**, norm **1.0**. Index
không hỏng, model không lệch không gian. Vấn đề nằm đúng ở đầu vào text.

### Chứng minh trực tiếp

Cùng một câu hỏi, chỉ khác có bản dịch hay không:

| | Kết quả hạng 1 |
|---|---|
| Không dịch (nguyên tiếng Việt) | `L25_V045` — bài giảng Địa lý ôn thi |
| Có dịch đúng | `L29_V013` — đúng cảnh cắt nho, `vector` và `asr` đồng thuận |

---

## 2. Đã sửa những gì

### 2.1 Khâu dịch — bỏ phụ thuộc credit

Người vận hành (hoặc Claude lúc thi) viết thẳng `query_en` vào file truy vấn.
`run.py` đã nhận sẵn trường này. Chạy 20 câu KIS với bản dịch viết tay:
**0 lần gọi LLM, 20/20 câu xong trong 14 giây.**

⚠️ Kiểm token bằng code, đừng ước lượng: CLIP cắt ở 77 token **không báo lỗi**.
Cả 20 bản dịch đều dưới 77 nên không bị cắt câm.

### 2.2 Định tuyến truy vấn — nơi lãi nhiều nhất mà không đổi model

Ba bài học phải trả giá bằng 11 thí nghiệm đo đạc:

**a. Không bao giờ xáo trộn đầu bảng.** Theo bảng điểm BTC: hạng 1 → Final
1.00, hạng 5 → 0.64, hạng 62 → 0.04. Đẩy một câu từ hạng 1 xuống hạng 5 **mất
0.36** — đúng bằng lợi ích cứu một câu chết lên top-20. Ba thí nghiệm đầu đều
thua vì làm loãng top-5. Thiết kế duy nhất không bao giờ lỗ: **giữ y nguyên N
slot đầu, chỉ dùng phần đuôi để phủ thêm giả thuyết.**

**b. Không RRF các anchor mô tả khoảnh khắc khác nhau.** Đề KIS thường kể một
chuỗi ("bắt đầu bằng… sau đó… kết thúc bằng"). Mỗi anchor tả một khoảnh khắc,
nên frame đúng chỉ khớp mạnh với *một* anchor. RRF cộng dồn lại **thưởng cho
shot khớp lờ mờ với cả ba, dìm shot khớp hoàn hảo với một**. Đo được: R@1 tụt
từ 6/17 xuống 1/17. Mỗi nguồn phải giữ bảng xếp hạng riêng rồi **xen kẽ** slot.

**c. Chọn video và định vị frame là hai việc khác nhau, cần tín hiệu khác
nhau.** Ví dụ p1-8: anchor *giả thuyết* ("steamed fish garnished with vegetable
strips") tìm đúng **video** ở hạng 2; anchor *trung thành với đề* tìm đúng
**frame** ở hạng 5 trong video đó. Không cái nào một mình đủ. Khi đào một video,
phải đào bằng **mọi** anchor.

### 2.3 Hai kỹ thuật mới, hiệu quả rõ rệt

**Dùng thẳng frame mà OCR/ASR trỏ tới.** Trước đây probe chỉ dùng để *đề cử
video*, rồi lại nhờ CLIP tìm frame bên trong — trong khi hit OCR vốn đã gắn với
đúng `keyframe_id`. Cứu được p1-12 (OCR bắt chữ `mazut` trên ticker giá dầu) và
p1-22 (OCR bắt chữ `remember` trên bảng).

**Liệt kê giả thuyết cho phần đề nói chung chung.** "Công trình thủy lợi" →
*hydroelectric dam releasing water*; "đĩa đang được hấp trong nồi" → *steamed
fish garnished with vegetable strips*. Đây **không phải** thêm chi tiết vào đề
(vi phạm bất biến #6) mà là phủ không gian khả năng — và vì mỗi giả thuyết có
luồng slot riêng, **giả thuyết sai chỉ tốn slot, không phá thứ hạng**. Cứu được
p1-2 và p1-21.

### 2.4 Các lỗi khác tìm được trên đường

- **Cổng release holdout chưa từng chạy được lần nào.**
  `dev_set/manifests/batch1_holdout13.json` thiếu `ground_truth_sha256` nên
  `_load_frozen_inputs()` ném `ValueError` ngay câu đầu. Test tích hợp không bắt
  được vì nó *tự sinh GT giả trong thư mục tạm*, chưa từng đọc file thật. Đã vá
  và khoá bằng test đọc thẳng file thật.
- **VLM reranker nằm trong đường chạy online** — vi phạm CLAUDE.md. Đã tách
  `search()` thành `_search_core` + `_finalize` + `search()`; hàm công khai
  **không còn tham số `rerank`**, nên production không thể chạm tới VLM. Chặn
  bằng cấu trúc code chứ không bằng quy ước.
- **Regex `\d+` cắt điểm `"0.85"` thành `0`** trong reranker — ảnh đúng bị chấm
  0 điểm âm thầm. Đã sửa nhận số thập phân.
- **`vlm_scene_graph_job_mlx.py` hardcode token ảnh của Llama** nhưng vẫn quảng
  cáo hỗ trợ Qwen2-VL → caption bịa, không báo lỗi. Đã chặn cứng bằng `ap.error`.

---

## 3. Đang chạy: đổi encoder sang SigLIP2

### Vì sao phải đổi

Sau khi vắt kiệt phần định tuyến, **vẫn còn 3 câu không cách nào cứu được**
(p1-2, p1-8, p1-14). Video đúng nằm hạng 12 trong bảng bỏ phiếu giữa 873 video,
vì CLIP B/32 không phân biệt nổi "đĩa hấp trong nồi có nguyên liệu thái thanh"
với 36 chương trình nấu ăn khác trông na ná. Đây là **giới hạn thật của model**,
không phải chỗ chỉnh tham số được.

### Bằng chứng chọn model

A/B công bằng trên cùng hồ 44 video (16 video chứa đáp án + 28 video nhiễu
**cùng thể loại**), cùng anchor, cùng tập keyframe:

| | Final | Top-5 | Mất hẳn |
|---|---|---|---|
| CLIP ViT-B/32 | 0.5976 | 10/17 | 1 |
| **SigLIP2 ViT-L/16** | **0.7153** | **15/17** | **0** |

Quan trọng nhất — nó giải đúng những câu CLIP bó tay:

| Câu | CLIP | SigLIP2 |
|---|---|---|
| p1-8 / p1-14 (đĩa hấp) | 13 | **4** |
| p1-12 (giá dầu mazut) | mất hẳn | **5** |
| p1-22 (bảng `remember`) | 30 | **4** |

⚠️ **Sai lệch cần biết:** CLIP phải chọn giữa 12.779 vector còn SigLIP2 chỉ
9.530 — tức CLIP chịu nhiều nhiễu hơn 34%. Mức chênh thật có thể nhỏ hơn 0.118.
Và đây là hồ 44 video, không phải 873 — con số đo là **mức cải thiện tương
đối**, không phải điểm dự kiến.

### Model đang encode

`ViT-SO400M-16-SigLIP2-256` (428M tham số, 1152 chiều) — bản mạnh nhất còn chạy
được trong thời gian thực tế trên máy hiện tại:

| Model | Ước tính encode 549K ảnh |
|---|---|
| ViT-L-16-SigLIP2-256 | ~30 giờ (đo thật) |
| **ViT-SO400M-16-SigLIP2-256** | **~12,6 giờ với fp16** |
| ViT-SO400M-16-SigLIP2-384 | ~90 giờ |
| ViT-gopt-16-SigLIP2-384 | ~300 giờ |

### Những gì đã đo để job này chạy được

Job đầu tiên **treo hẳn**, không phải chạy chậm — CPU-time chỉ nhích 1,35s
trong 90 giây, RAM 11,7/13,3 GB, máy vào swap. Loại trừ từng nguyên nhân:

| Nghi ngờ | Đo được | Kết luận |
|---|---|---|
| Đọc đĩa chậm | 190–212 ảnh/s (8–16 luồng) | Không phải |
| Docker chiếm RAM | Tắt ES+Milvus (4 GB) → không đổi | Không phải |
| Throttle nhiệt | `pmset -g therm`: không cảnh báo | Không phải |
| Nạp cả video vào RAM | 1.618 ảnh ≈ 1,3 GB tensor cùng lúc | **Đúng** |
| ViT-L quá nặng cho MPS fp32 | 5,0 ảnh/s bền vững | **Đúng** |

Ba bản vá: nạp theo khối + đệm kép, `gc.collect()` trước khi nạp model, và
**fp16** — nhanh gấp **2,81 lần**, đã kiểm cosine với fp32 là **0,9995** và
top-10 xếp hạng không đổi.

Hai thứ đáng nhớ cho lần sau:
- **48 luồng đọc làm tốc độ sập từ 190 xuống 6 ảnh/s.** Quá nhiều luồng còn tệ
  hơn ít luồng.
- **Benchmark ngắn nói dối.** Đo 600 ảnh còn trong cache ra 13,6 ảnh/s, chạy
  thật nhiều giờ chỉ còn 5,0. Hệ số ~2,7 lần.

### Cách bật/tắt

Encoder mới nằm ở **collection riêng**, không ghi đè `keyframes`. Đổi encoder là
đổi cả không gian vector; ghi đè mà kém hơn thì không còn đường lùi, và lỗi loại
này **không crash**.

```bash
VECTOR_BACKEND=siglip2 python -m backend.retrieval.search "..." --en "..."
VECTOR_BACKEND=clip     # mặc định, giữ nguyên hành vi cũ
```

---

## 4. Còn hỏng — cần người, agent không tự giải được

1. **Q&A đứng im hoàn toàn.** Hết credit Anthropic. Q&A bắt buộc cần LLM đọc
   ảnh nên **không có đường vòng như KIS**. Nạp thêm credit, hoặc đặt
   `LLM_BACKEND=gemini` (adapter đã hỗ trợ sẵn, key lấy miễn phí tại
   aistudio.google.com/apikey).
2. **GT holdout mới 6/13 verified.** Bảy câu bị đánh dấu sai hẳn nên cổng
   promotion đang `BLOCKED` — đúng thiết kế fail-closed, không phải bug. GT
   round1 (17 câu) đã điều tra xong nhưng vẫn mang trạng thái `unknown`: theo
   AGENTS.md chỉ **người** mới được nâng lên `verified`.
3. **Ba câu KIS còn treo:** p1-20 (áo mưa in hình gấu), p1-23 (đã chốt được
   series Địa lý, chưa đúng slide sơ đồ 3 tầng), p1-25 (2 học sinh MC).
4. **`query-p1-8-kis` và `query-p1-14-kis` có đề giống hệt nhau từng chữ.**
   Nếu BTC không cố ý ra trùng thì file đề bị lỗi — nên hỏi lại.

---

## 5. Công cụ mới, cách dùng

| Lệnh | Làm gì |
|---|---|
| `python scripts/selfcheck.py` | Một lệnh trả lời "còn thiếu gì để coi là xong", exit 1 khi còn việc |
| `python -m dev_set.tools.gt_verification_gallery --manifest <tên>` | Trang HTML soi keyframe để xác minh GT bằng mắt |
| `python -m dev_set.tools.mark_verified --query-id ... --status verified --by ...` | Ghi quyết định xác minh, đồng bộ GT + manifest + hash |
| `python scripts/make_kis_answer_sheet.py --embed` | Trang đối chiếu đề bài ↔ ảnh đáp án |
| `python scripts/encode_siglip2.py` | Encode SigLIP2, checkpoint/resume được |
| `python -m backend.indexing.load_siglip2` | Nạp vector SigLIP2 vào collection riêng |

Ngoài ra `.claude/settings.json` có hook tự chạy pytest sau mỗi lần sửa `.py` —
test đỏ thì chặn lại. Bấm `/hooks` một lần để kích hoạt.

---

## 6. Ba bài học đắt nhất

1. **Fallback im lặng nguy hiểm hơn crash.** `try/except` rơi về tiếng Việt là
   quyết định đúng về mặt sẵn sàng, nhưng vì không ai theo dõi *tỉ lệ dùng
   fallback*, nó âm thầm phá cả bộ đáp án. Nên đếm và cảnh báo mỗi lần rơi vào
   nhánh dự phòng, chứ không chỉ log một dòng.
2. **Test dùng dữ liệu giả không chứng minh được gì về dữ liệu thật.** Cổng
   release "đã xong" suốt nhiều ngày nhưng chưa từng chạy nổi một lần.
3. **Đo trước khi tin.** Ba giả thuyết cải tiến đầu tiên của tôi đều nghe rất
   hợp lý và đều làm điểm **tệ đi**. Chỉ có đo mới phân biệt được.
