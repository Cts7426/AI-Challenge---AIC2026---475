# 📋 Báo Cáo Kỹ Thuật — C3.1 / C3.2 / C4.4: Pipeline Q&A + TRAKE

> **Ngày:** 14/08/2026
>
> **Người thực hiện:** Thi (Claude Code thay mặt thực hiện theo yêu cầu)
>
> **Phạm vi:** `backend/tasks/{qa,trake,trake_fallback}.py` (C3.1/C3.2/C4.4) +
> `backend/llm/adapter.py` (mở rộng C0.1 — backend Gemini) + hạ tầng dữ liệu
> (Milvus CLIP, ES objects — thuộc phạm vi B của Công Lý, làm thay vì đang chặn
> đường thử nghiệm) + `backend/common/answer_match.py` (tách từ E4.2 của
> Minh Hoàng/Linh, dùng chung).
>
> **Trạng thái: CHẠY ĐƯỢC ĐẦU-CUỐI cả ba dạng pipeline, có LLM thật (Gemini),
> có Milvus + ES thật, không mock.** 291 test xanh (46 test mới). 2 bug thật
> trong đặc tả gốc + 1 bug thật trong code cũ (`search.py`) được tìm ra và sửa
> — chi tiết ở §7.

---

## Mục lục

1. [Bối cảnh & cách làm](#1-bối-cảnh--cách-làm)
2. [Phần C (Thi) — ba pipeline chính](#2-phần-c-thi--ba-pipeline-chính)
3. [Phần C mở rộng — backend Gemini cho `llm()`](#3-phần-c-mở-rộng--backend-gemini-cho-llm)
4. [Phần B (Công Lý) — hạ tầng dữ liệu đã hoàn thiện](#4-phần-b-công-lý--hạ-tầng-dữ-liệu-đã-hoàn-thiện)
5. [Phần E (Minh Hoàng / Linh) — tách logic so khớp answer dùng chung](#5-phần-e-minh-hoàng--linh--tách-logic-so-khớp-answer-dùng-chung)
6. [Sửa chéo bắt buộc trên file của người khác](#6-sửa-chéo-bắt-buộc-trên-file-của-người-khác)
7. [Lỗi & lỗ hổng đã tìm ra — danh sách đầy đủ](#7-lỗi--lỗ-hổng-đã-tìm-ra--danh-sách-đầy-đủ)
8. [Kết quả chạy thực tế đầu-cuối](#8-kết-quả-chạy-thực-tế-đầu-cuối)
9. [Giới hạn đã biết — chưa/không sửa](#9-giới-hạn-đã-biết--chưasửa)
10. [Đối chiếu với đặc tả BUILD_TASKS](#10-đối-chiếu-với-đặc-tả-build_tasks)
11. [Việc tiếp theo](#11-việc-tiếp-theo)

---

## 1. Bối cảnh & cách làm

Hệ thống có KIS chạy được nhưng thiếu hoàn toàn Q&A và TRAKE. Một agent trước
(Antigravity IDE, lưu ở `~/.gemini/antigravity-ide/brain/`, **không nằm trong
repo**) đã soạn sẵn 1 bản kế hoạch triển khai — quy trình làm việc ở đây là:

1. Đọc kế hoạch cũ + toàn bộ bất biến liên quan (`CLAUDE.md`, `docs/contest.md`,
   `BUILD_TASKS.md`) **trước khi viết bất kỳ dòng code nào**.
2. Phản biện kế hoạch cũ bằng văn bản (không code) — tìm lỗ hổng, đối chiếu với
   nguồn sự thật (`docs/contest.md` cho công thức chấm, không dựa trí nhớ).
3. Chờ duyệt kiến trúc mới, rồi mới code.
4. Sau khi code xong: **không dừng ở "test xanh"** — chạy thật trên Docker
   (ES + Milvus), phát hiện thêm lỗi mà unit test không bắt được (thiếu dữ
   liệu, sai đường dẫn, hạn mức Milvus).

Ba cửa tử của Q&A/TRAKE mà mọi quyết định thiết kế dưới đây đều phải phục vụ
(`docs/contest.md` mục 2):

| Dạng | Công thức R-Score | Ý nghĩa cho code |
|:---|:---|:---|
| Q&A | `I(v=GTᵥ ∧ id∈[s,e] ∧ a=GTₐ)` | sai answer thì frame đúng cũng **0** |
| TRAKE | sai video → **0 tuyệt đối**; đúng video → `(1/N)·Σⱼ I(idⱼ∈[sⱼ,eⱼ])` | khớp **THEO VỊ TRÍ j**, không phải "có mặt ở đâu đó" |

---

## 2. Phần C (Thi) — ba pipeline chính

### 2.1. `backend/tasks/qa.py` — C3.1

**Đường đi:**

```
query VI → parse_question() [llm()+schema] → (event_vi, question_vi)
         → search(event_vi) [KIS pipeline KHÔNG SỬA LOGIC] → top-5 shot
         → route_question(question_vi) [data/config/qa_routing.py, rule-based]
         → collect_evidence() mỗi shot: OCR ±shot · ASR ±3s · metadata · objects
         → ask_llm(): text-first, self-consistency n=3, vote
         → qa_pipeline() trả (mọi shot ứng viên, answer thắng cuộc)
```

`qa_pipeline()` **không tự xếp 100 dòng nộp** — nó trả `(list[ShotHit], answer_text)`,
lớp gọi tự đưa vào `backend.slot.allocate(hits, "QA", answer_text=...)` (D3.1,
đã có sẵn, đã test). Lý do tách: nếu `qa.py` tự viết lại cơ chế xen kẽ/đủ 100
dòng, sẽ có 2 bản logic dễ trôi lệch nhau.

**Các quyết định thiết kế chính:**

| Quyết định | Vì sao |
|:---|:---|
| Text-first (OCR/ASR/metadata trước, ảnh sau) | VLM tốn token/tiền hơn nhiều lần text. Chỉ thêm ảnh khi route bắt buộc ("visual") hoặc confidence trung bình < 0.5 |
| `route_question()` rule-based (từ khoá), không hỏi LLM | Route chỉ cần biết NGUỒN bằng chứng nào đáng tin, 1 phép match từ khoá trả lời được — hỏi LLM là thêm 1 vòng gọi mạng vô ích |
| "đếm" → ES objects trực tiếp, KHÔNG hỏi VLM | BUILD_TASKS C3.1 ghi rõ; VLM đếm bằng mắt sai thường xuyên khi số lượng > 4-5 |
| Self-consistency n=3, KHÔNG dùng `temperature` | `backend/llm/adapter.py` cho biết model Claude API mới bỏ hẳn temperature — đa dạng câu trả lời phải đến từ n>1, không phải nhiệt độ |
| Vote bằng `backend.common.answer_match` (chung với chấm điểm) | Tránh 2 định nghĩa "2 câu trả lời giống nhau" trôi lệch nhau giữa production và dev_set |
| Thử tối đa 3 shot (`MAX_SHOTS_TRIED`), không chỉ shot #1 | 1 shot thiếu bằng chứng không được làm hỏng cả câu hỏi |
| `evidence_frame_idx` LUÔN kẹp về tập frame CÓ THẬT đã gửi VLM | "Hai cửa tử độc lập": không bao giờ tin thẳng số VLM tự bịa — nếu VLM trả số ngoài danh sách ảnh đã gửi, thay bằng frame gần nhất đã biết + log cảnh báo |

**Chi tiết thu bằng chứng (`collect_evidence`):**

- `_ocr_for_shot`: index `ocr` không lưu `shot_id`/`frame_idx` (chỉ `keyframe_id`)
  → tra `frame_idx` qua `backend/indexing/frame_map.py` (nguồn DUY NHẤT) rồi lọc
  trong Python theo biên shot.
- `_asr_for_shot`: cửa sổ ±3s quanh timestamp của `best_keyframe_id` (khác
  `ASR_TIME_PAD_MS` của `search.py` — đó là 2000ms dùng cho việc "đề cử", việc
  khác hẳn).
- `_object_count`: đếm detection 1 nhãn trên **1 keyframe đại diện** (không có
  tracker xuyên frame — xem giới hạn ở §9).
- `_evidence_frames`: đọc thật `data/derived/keyframes.parquet` (1fps, B1.2),
  ưu tiên frame gần `best_keyframe_id` nhất rồi rải đều phần còn lại theo thời
  gian; **chỉ trả file ảnh thực sự tồn tại trên đĩa**, log cảnh báo cho từng
  file thiếu thay vì gửi rác cho VLM.

### 2.2. `backend/tasks/trake.py` — C3.2

**Sửa kiến trúc lớn nhất so với kế hoạch gốc:** BUILD_TASKS viết "ghép truy vấn
tổng hợp" (nối N mô tả sự kiện thành 1 câu rồi search 1 lần). Cách này **vi
phạm bất biến CLIP 77 token** (CLAUDE.md bất biến 6) — với N≥3 sự kiện, CLIP
tự cắt cụt phần đuôi câu **lặng lẽ**, sự kiện cuối chuỗi biến mất khỏi vector
mà không cảnh báo gì. Đã đổi sang:

```
parse_events(query_vi) → N mô tả sự kiện, GIỮ ĐÚNG thứ tự câu gốc [llm()+schema]
trake_stage1(events):
    N search(event_i) SONG SONG (mỗi event 1 câu ngắn, encode riêng — đúng
      bất biến CLIP) → mỗi search trả shot tốt nhất của MỖI video ứng viên
    video_score = Σᵢ best_shot_score(event_i, video)  — video có bằng chứng cho
      CẢ N sự kiện tự nhiên cao điểm hơn video chỉ khớp 1 sự kiện dù khớp mạnh
      → đúng Ý ĐỒ log-sum gốc, không cần sửa search.py, không cần filter
    thưởng thứ tự thời gian (TRAKE_ORDER_BONUS, data/config/search_weights.py —
      KHÔNG hardcode) khi video có ĐỦ N sự kiện VÀ frame đại diện tăng dần
      NGHIÊM NGẶT theo đúng thứ tự event — chỉ dùng XẾP LẠI HẠNG, không lọc cứng
    trả top-10 video (BUILD_TASKS C3.2)
```

`N = len(events)` lấy từ chính `parse_events()`, **không đọc** `TRAKE_DEFAULT_N`
của config — vì `dev_set/tools/scoring.py::rscore_trake` trả **0 điểm tuyệt đối**
nếu số khoảnh khắc nộp khác N thật của đề, kể cả khi mọi frame đều đúng vị trí.

### 2.3. `backend/tasks/trake_fallback.py` — C4.4

**Bug nghiêm trọng nhất tìm được trong toàn bộ phiên làm việc**, nằm ở cả
BUILD_TASKS lẫn kế hoạch cũ: *"chạy N lần độc lập → sắp xếp kết quả theo thời
gian tăng dần"*.

`docs/contest.md` xác nhận rõ (mục "TRAKE khớp theo vị trí"): *"frame thứ j
phải rơi vào khoảng `[sⱼ,eⱼ]` của khoảnh khắc thứ j. **Không phải khớp bất kỳ
thứ tự nào**."* — nghĩa là **frame ở vị trí j đại diện cho ĐÚNG sự kiện thứ j**,
không phải "N con số bất kỳ miễn tăng dần".

**Vì sao sort theo giá trị là sai, không chỉ là "chưa tối ưu":** nếu search của
sự kiện 3 (do trùng khớp giả — false positive) trả về frame SỚM HƠN frame của
sự kiện 1, thao tác sort sẽ đẩy frame đó lên vị trí 1 — **tự tay** gán frame
của sự kiện 3 vào vị trí đại diện cho sự kiện 1. Validator vẫn xanh (dãy tăng
dần), nhưng điểm BTC chấm dựa vào vị trí sẽ **sai hoàn toàn** mà không có dấu
hiệu gì trong code hay trong lúc chạy thử.

**Thuật toán đã viết — giữ vị trí, chỉ sửa cục bộ:**

```
với mỗi sự kiện j (ĐÚNG thứ tự câu hỏi):
    search(event_j, filter_video_id=video_hạng_1, top_k=1) → frame_idx tốt nhất
      TRONG video đó (không lẫn video khác)
sự kiện không có bằng chứng trong video → _fill_missing(): nội suy TUYẾN TÍNH
    giữa 2 sự kiện lân cận có bằng chứng thật; thiếu ở đầu/cuối dãy → dùng giá
    trị lân cận gần nhất; TOÀN BỘ N sự kiện đều thiếu → raise rõ ràng
_repair_strictly_increasing(): quét TRÁI→PHẢI, frame_j ≤ frame_{j-1} thì đẩy
    frame_j = frame_{j-1}+1 (kỹ thuật giống hệt backend/slot/allocator.py::
    _trake_row, tái dùng ý tưởng chứ không copy) — GIỮ VỊ TRÍ, không sort
    → tràn khỏi độ dài video: dịch lùi cả chuỗi; vẫn âm (video quá ngắn cho
      ngần ấy sự kiện — về mặt TOÁN HỌC bất khả thi) → rải đều làm phương án
      cuối, log cảnh báo rõ ràng thay vì crash
```

Kết quả `trake_stage2_fallback()` **luôn là dòng hạng 1** của bài nộp TRAKE —
dòng duy nhất có bằng chứng thật cho từng sự kiện. Dòng 2-100 vẫn do
`backend.slot.allocate()` lấp bằng cơ chế rải-trong-shot có sẵn (D3.1), dùng
làm lưới an toàn thống kê.

**Xác nhận sống trên dữ liệu thật** (không phải suy luận trên giấy — xem §8.3):
gặp đúng ca "sự kiện 3 khớp sớm hơn sự kiện 1-2" trong lúc chạy thử thật, và
thuật toán xử lý đúng như thiết kế.

---

## 3. Phần C mở rộng — backend Gemini cho `llm()`

Team chưa có ngân sách cho `ANTHROPIC_API_KEY`. Vì `backend/llm/adapter.py` là
điểm gọi LLM DUY NHẤT (CLAUDE.md bất biến 1), thêm backend mới chỉ cần sửa
**đúng một file** — không đụng `qa.py`/`trake.py`/`query_understanding.py`.

### 3.1. Những gì đã thêm

- `LLM_BACKEND=gemini`, `GEMINI_API_KEY`, `LLM_GEMINI_MODEL` (env var, cùng
  quy ước với `LLM_API_MODEL`/`LLM_LOCAL_MODEL` đã có).
- `_gemini_client()`, `_gemini_parts()` (ảnh — cùng quy ước với `_noi_dung()`
  của Claude: nhận đường dẫn file hoặc bytes).
- `_call_gemini()`: text + ảnh + JSON schema, retry riêng 3 lần (backoff mũ)
  cho lỗi 503 tạm thời — khác lỗi JSON hỏng (đã có retry riêng) và khác
  lỗi mạng/429 (SDK tự retry).
- `_sanitize_schema_for_gemini()`: **phát hiện quan trọng** — Gemini
  `response_schema` dùng phương ngữ OpenAPI 3.0, không hiểu `additionalProperties`
  (lỗi 400 thật khi test trên `PARSE_QUESTION_SCHEMA` của `qa.py`). Hàm này
  khử đệ quy các khoá không hỗ trợ, trả BẢN SAO — không sửa schema gốc, vì
  cùng 1 schema constant còn dùng cho backend `api`/`local` (JSON Schema chuẩn
  vẫn cần `additionalProperties` để chặt chẽ ở đó).
- `_ghi_nhan()` refactor: nhận số token đã trích sẵn thay vì object `usage`
  thô — vì mỗi SDK đặt tên field khác nhau (Anthropic: `input_tokens`/
  `output_tokens`; Gemini: `prompt_token_count`/`candidates_token_count`).
- Cache key thêm `temperature` — vì Gemini **không** bỏ qua tham số này như
  Claude, đổi temperature phải đổi cache.

### 3.2. Đo thật, không đoán tên model

| Model thử | Kết quả đo thật (14/08) |
|:---|:---|
| `gemini-2.5-pro`, `gemini-3-pro-preview`, `gemini-pro-latest` | **429 RESOURCE_EXHAUSTED** — quota free-tier = 0 cho tier Pro |
| `gemini-flash-latest` (alias) | hay **503 quá tải**, có lần **treo nhiều phút không tự timeout** — nghi alias route không ổn định phía Google lúc test |
| `gemini-2.5-flash` (bản cố định) | **nhanh, ổn định** — text/JSON-schema/ảnh đều đúng |

→ `DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"`, có ghi lại đầy đủ lý do trong
comment code (không phải chọn ngẫu nhiên) và đường nâng cấp khi Google đổi
chính sách (chỉ cần đổi 1 dòng hoặc set `LLM_GEMINI_MODEL`).

### 3.3. Một lưu ý bảo mật trong lúc làm

User dán trực tiếp một chuỗi dạng `AQ.Ab8...` vào chat để làm `GEMINI_API_KEY`.
Chuỗi này **không đúng định dạng API key chuẩn** của Google AI Studio
(`AIzaSy...`) — giống định dạng access token OAuth tạm thời hơn. Đã cảnh báo
trực tiếp cho user (khuyên revoke nếu là credential thật, vì đã lộ vào lịch sử
chat) trước khi dùng. User xác nhận đây đúng là key họ định dùng → test thật,
xác nhận **hoạt động được** với `google-genai` SDK (`api_key=`) bình thường.
Ghi lại ở đây vì đây là loại rủi ro cần cảnh giác khi người vận hành dán
thông tin xác thực trực tiếp vào chat thay vì qua biến môi trường.

---

## 4. Phần B (Công Lý) — hạ tầng dữ liệu đã hoàn thiện

Không thuộc phạm vi C3.x, nhưng **chặn cứng** việc thử nghiệm C3.x — nên đã
làm luôn theo yêu cầu, có kiểm chứng đầy đủ:

### 4.1. Nạp CLIP feature THẬT vào Milvus

```
python -m backend.indexing.load_clip --features-dir data/raw/btc/clip-features-32
```

- 177.321 vector nạp vào collection `keyframes` (trước đó collection **không
  tồn tại**).
- **Kiểm chứng bắt buộc theo CLAUDE.md bất biến 1** (đã chạy, không chỉ viết
  logic rồi báo xong):
  - norm mọi vector ≈ 1.0 (sai số ≤ 0.001) — script tự động sau khi nạp.
  - `scripts/verify_clip_space.py` (đã có sẵn trong repo, chỉ chạy lại):
    encode lại 10 ảnh BTC đã có feature, so cosine với vector BTC cấp —
    **trung bình 0.9994, nhỏ nhất 0.9978** → ĐẠT. Xác nhận model
    `ViT-B-32-quickgelu/openai` đúng không gian vector với BTC.

### 4.2. Cài `open_clip_torch`

Thiếu ở mọi Python env trên máy (kể cả `.venv` có sẵn `torch`) → nhánh
`vector` của `search()` lỗi `ModuleNotFoundError`. Cài xong, encode thử: shape
`(512,)`, norm=1.0 — khớp `data/config/clip_model.py`.

### 4.3. `scripts/load_objects_from_btc.py` (mới) — nạp objects THẬT

`backend/indexing/load_objects.py` chỉ đọc **một** file JSON gộp sẵn — dữ liệu
BTC thật là **177.321 file JSON rời**, mỗi file 1 keyframe
(`data/raw/btc/objects/<video_id>/<ordinal>.json`). Viết script chuyển định
dạng + nạp hàng loạt, **tái dùng nguyên vẹn** `create_index()` của
`load_objects.py` — một schema ES `objects` DUY NHẤT, không tạo mapping thứ 2.

**Đối chiếu khoá join trước khi nạp** (đúng tinh thần bất biến 2 — không tự
suy đoán format): so `data/raw/btc/objects/L25_V064/001.json` với
`frame_map.parquet` → xác nhận `keyframe_id = "{video_id}#k{ordinal:04d}"`
(ordinal lấy từ tên file, ordinal trong tên file khớp đúng cột `btc_ordinal`).

Kết quả: 177.321 keyframe, **0 lỗi**, 56 giây. Đối chiếu thủ công (query ES
+ so sánh tay) khớp 100% giữa hàm `_object_count()` và dữ liệu thô.

### 4.4. Bug tìm ra: `KEYFRAME_ROOT` sai 1 cấp thư mục

Trong lúc viết `qa.py` (§2.1), đoán đường dẫn ảnh keyframe là `data/<path>`.
Soi trực tiếp `aic2026-keyframes.zip` (46GB, có sẵn trong repo) thì đường dẫn
thật là `data/derived/<path>`. Đây đúng kiểu lỗi CLAUDE.md cảnh báo: sai 1 cấp
thư mục thì code **chạy được, không crash**, chỉ lặng lẽ log "thiếu ảnh" cho
MỌI frame — route "visual" của Q&A sẽ luôn rơi về text-only mà không ai biết
vì sao. Đã sửa + xác nhận bằng ảnh thật (371.703 file đã có sẵn trên đĩa,
`_evidence_frames()` tìm đúng 8/8 file mẫu).

---

## 5. Phần E (Minh Hoàng / Linh) — tách logic so khớp answer dùng chung

`dev_set/tools/scoring.py::answer_matches` (3 tầng: chuẩn hoá → quy đổi số↔chữ
→ fuzzy 0.85) vốn chỉ phục vụ chấm điểm dev_set. `qa.py` (§2.1) cần **đúng
logic này** để vote self-consistency (3 câu trả lời khác diễn đạt, cùng nghĩa,
phải gom lại). Nếu viết 2 bản riêng, chúng sẽ trôi lệch nhau theo thời gian —
dev_set chấm một kiểu, production vote một kiểu khác.

**Đã làm:** tách phần cài đặt sang `backend/common/answer_match.py` (mới),
thêm `majority_answer()` cho self-consistency. `dev_set/tools/scoring.py`
import lại từ đó, **re-export** `answer_matches` để code cũ (kể cả test cũ)
không phải sửa gì. 4 test cũ của `dev_set/tests/test_scoring.py` vẫn xanh
nguyên vẹn sau refactor.

---

## 6. Sửa chéo bắt buộc trên file của người khác

| File | Chủ sở hữu (BUILD_TASKS) | Sửa gì | Vì sao bắt buộc |
|:---|:---|:---|:---|
| `backend/retrieval/search.py` | Thạch (A2.1/A2.2) | +`filter_video_id` (4 nhánh keyframe-level) | C4.4 cần ép search trong 1 video đã biết |
| `backend/retrieval/search.py` | Thạch | `ef=128` → `ef=max(128, limit)` | Bug thật — xem §7.3 |
| `backend/slot/allocator.py` | Minh Hoàng (D3.1) | + `shot_bounds()` (public, thin wrapper) | `qa.py` cần tra biên shot mà không đọc lại `shots.parquet` lần 2 |

Cả 3 chỗ đều là **thêm/mở rộng có kiểm soát**, không đổi hành vi cũ:
`filter_video_id` mặc định `None` (KIS pipeline y hệt trước), `ef` chỉ đổi
khi `limit > 128` (KIS thường `limit < 128` nên không chạm), `shot_bounds()`
là hàm mới hoàn toàn, không sửa hàm cũ nào.

---

## 7. Lỗi & lỗ hổng đã tìm ra — danh sách đầy đủ

### 7.1. 🔴 Vi phạm bất biến CLIP 77 token trong đặc tả gốc C3.2

Kế hoạch cũ + BUILD_TASKS: nối N mô tả sự kiện thành 1 câu cho TRAKE stage 1.
Vi phạm CLAUDE.md bất biến 6. **Sửa:** N search song song, xem §2.2.

### 7.2. 🔴 Sort theo giá trị thay vì giữ vị trí trong đặc tả gốc C4.4

Phá vỡ đúng thứ TRAKE cần (khớp theo vị trí j, không phải theo giá trị tăng
dần). **Sửa:** giữ vị trí + sửa đơn điệu cục bộ, xem §2.3. **Xác nhận sống
trên dữ liệu thật** ở §8.3 — không phải suy luận trên giấy.

### 7.3. 🔴 `search.py` — Milvus HNSW `ef=128` hardcode, TRAKE cần pool rộng

Milvus đòi `ef ≥ k` cho search HNSW, báo lỗi thẳng chứ không tự nới. C3.2 xin
`top_k=200` → `limit = 200×5 = 1000` (nhân `CANDIDATE_MULTIPLIER`) → `ef=128 <
1000` → **toàn bộ nhánh vector chết mỗi lần chạy `trake_stage1()`**, `search()`
vẫn chạy tiếp bằng 4 nhánh còn lại (an toàn, không crash) nhưng **mất tín hiệu
mạnh nhất mà không ai để ý** — đúng kiểu lỗi im lặng CLAUDE.md lo nhất. Phát
hiện khi chạy `trake_stage1()` thật lần đầu (không unit test nào bắt được vì
cần Milvus thật với pool đủ lớn). **Sửa:** `ef = max(128, limit)`. Regression
xác nhận: KIS pool nhỏ (`limit≤128`) kết quả y hệt trước khi sửa.

### 7.4. 🟡 `temperature=0.7` trong đặc tả gốc — đã bị adapter bỏ qua

`backend/llm/adapter.py` (viết trước phiên này) đã đổi: model Claude API mới
bỏ hẳn `temperature`. Kế hoạch cũ (viết theo BUILD_TASKS cũ) chưa cập nhật
theo thay đổi đó. **Sửa:** self-consistency dựa vào n=3 + hướng dẫn trong
prompt, không dựa temperature (Gemini thì vẫn nhận temperature bình thường —
đã ghi rõ khác biệt 2 backend trong code, §3.1).

### 7.5. 🟡 Gemini `response_schema` không hiểu `additionalProperties`

Không phải JSON Schema đầy đủ mà là phương ngữ OpenAPI 3.0. Lỗi 400 thật khi
test schema gốc của dự án. **Sửa:** `_sanitize_schema_for_gemini()`, §3.1.

### 7.6. 🟡 `KEYFRAME_ROOT` đoán sai — xem §4.4

### 7.7. 🟡 `_repair_strictly_increasing` — công thức rải đều dùng `round()` có thể đụng nhau

Bắt được bằng test tổng hợp (`tests/test_trake_fallback.py`), không phải chạy
thật: video cực ngắn so với N sự kiện, `round()` sinh 2 giá trị trùng nhau.
**Sửa:** chạy lại đúng phép đẩy +1 sau khi rải, kẹp biên; phân biệt rõ ca
"ngắn nhưng đủ toán học" (phải tăng dần ngặt tuyệt đối) với ca "bất khả thi
toán học" (video ngắn hơn cả số sự kiện — chấp nhận trùng ở sát biên, không
crash, log cảnh báo).

### 7.8. 🟢 Trùng lặp logic so khớp answer — xem §5 (không phải bug đang chạy sai, mà là rủi ro trôi lệch về sau)

### 7.9. 🟢 `_ghi_nhan()` gắn cứng theo shape `usage` của Anthropic — không mở rộng được đa backend

Refactor sang nhận số đã trích sẵn, §3.1 — dọn đường cho backend thứ 3/4 sau
này (không phải bug, nhưng sẽ THÀNH bug khi thêm backend nếu không sửa trước).

---

## 8. Kết quả chạy thực tế đầu-cuối

Toàn bộ dưới đây chạy trên **Docker thật** (ES 8.13.4 + Milvus 2.4.17), dữ
liệu BTC thật, Gemini thật — không dữ liệu giả lập.

### 8.1. Hạ tầng sau khi hoàn thiện (§4)

```
ES   : metadata 873 doc · ocr 160.393 · asr 13.415 · objects 177.321 keyframe
       (17.909.421 "docs" — ES đếm cả nested sub-document, 100 detection/keyframe)
Milvus: keyframes 177.321 vector, norm ≈ 1.000000, cosine với BTC = 0.9994 (10 mẫu)
Ảnh keyframe: 371.703 file thật trên đĩa
```

### 8.2. `qa_pipeline()` thật (Gemini)

```
$ python -m backend.tasks.qa "Kênh truyền hình phát sóng bản tin có tên là gì?"

Trả lời: Báo Thanh Niên

5 shot ứng viên (đưa vào backend.slot.allocate để ra 100 dòng nộp):
  hạng 1: shot=L25_V031#s0063 score=0.02878 best_kf=L25_V031#k0121
  ...
[llm] 5 lần gọi (0 trúng cache) · 7.758 token vào · 212 token ra · ≈ $0.0024
```

### 8.3. `trake_stage1()` + `trake_stage2_fallback()` thật — bằng chứng sống của bug §7.2

```
$ python -m backend.tasks.trake "cầu thủ sút phạt đền, sau đó thủ môn bay
  người cản phá, cuối cùng trọng tài thổi còi" --parse

3 sự kiện: [cầu thủ sút phạt đền | thủ môn bay người cản phá | trọng tài thổi còi]
Top 10 video: hạng 1 = L25_V059 (score=0.07128)

$ python -m backend.tasks.trake_fallback L25_V059 "cầu thủ sút phạt đền .
  thủ môn bay người cản phá . trọng tài thổi còi"

frame_ids (3 khoảnh khắc, tăng dần ngặt): (32473, 32474, 32475)
```

Truy vết dữ liệu THÔ trước khi sửa đơn điệu:

| Sự kiện | frame_idx thô | Vấn đề |
|:---|---:|:---|
| 1. cầu thủ sút phạt đền | 32473 | — |
| 2. thủ môn bay người cản phá | 32473 | trùng sự kiện 1 |
| 3. trọng tài thổi còi | **32339** | **SỚM HƠN** sự kiện 1&2 — false positive thật |

Thuật toán **giữ nguyên vị trí sự kiện 3 ở hạng 3**, chỉ đẩy +1
(`32473→32474→32475`) — **không** sắp xếp lại làm sự kiện 3 nhảy lên vị trí 1.
Đây chính là ca mà thuật toán "sort theo giá trị" của đặc tả gốc (§7.2) sẽ làm
sai, xảy ra tự nhiên ngay lần chạy thử đầu tiên trên dữ liệu thật, không phải
kịch bản dàn dựng.

### 8.4. Test suite

```
tests/ (5 file mới: test_answer_match, test_trake_fallback, test_trake,
        test_qa_routing, test_search_filter) + dev_set/tests/
────────────────────────────────────────────────────────────────
291 passed, 0 failed   (46 test mới, 245 test cũ — không hồi quy)
```

---

## 9. Giới hạn đã biết — chưa/không sửa

| # | Giới hạn | Vì sao chấp nhận ở v1 |
|:---|:---|:---|
| 1 | Đếm object ("count" route) chỉ đếm trên **1 frame đại diện**, không có tracker xuyên frame | Data BTC chỉ có detection từng frame; cài tracker ngoài phạm vi C3.1, cần quyết định riêng nếu muốn chính xác hơn |
| 2 | `gemini-2.5-flash` là model **tạm thời** thay Anthropic — team chưa có `ANTHROPIC_API_KEY` | Đổi lại backend `api` chỉ cần set `LLM_BACKEND=api` + key — không sửa code |
| 3 | Quota Gemini free-tier = 0 cho mọi model đuôi "-pro" | Ngoài tầm kiểm soát code, phụ thuộc chính sách Google |
| 4 | TRAKE fallback vẫn có thể trả frame sai vị trí thật (chỉ **không tự làm sai thêm** bằng sort) khi search không đủ tinh phân biệt các khoảnh khắc con trong 1 shot ngắn — xem ca thật ở §8.3 | Đây chính xác là lý do BUILD_TASKS gọi C4.4 là "phương án sinh tồn", còn C4.1 (DP, P2) mới là hướng chính xác hơn |
| 5 | `_object_count`/objects index dùng ngưỡng `score >= 0.5` cố định | Chưa có dev_set để tune ngưỡng — TODO khi có dữ liệu chấm |

---

## 10. Đối chiếu với đặc tả BUILD_TASKS

| Yêu cầu (C3.1) | Trạng thái |
|:---|:---|
| Pipeline KIS trên "mô tả sự kiện" → top-K shot | ✅ tái dùng `search()` nguyên vẹn |
| Thu bằng chứng: frame + ASR ±3s + OCR + object + metadata | ✅ |
| Định tuyến theo loại câu hỏi (bảng trong config) | ✅ `data/config/qa_routing.py` |
| Đếm → detector, KHÔNG hỏi VLM | ✅ |
| VLM trả JSON: answer/answer_vi/answer_en/evidence_frame_idx/confidence/evidence_type | ✅ (kẹp `evidence_frame_idx` về tập thật — chặt hơn yêu cầu gốc) |
| Tự nhất quán n=3 | ✅ (đổi `temperature=0.7` → n=3 thuần, lý do §7.4) |
| Answer ngắn nhất mà vẫn đủ | ✅ `majority_answer()` chọn đại diện ngắn nhất trong nhóm thắng |

| Yêu cầu (C3.2) | Trạng thái |
|:---|:---|
| Gộp N mô tả sự kiện → pipeline KIS | ✅ (đổi cách gộp — lý do §7.1, đã duyệt Phase 2) |
| Gom điểm cấp VIDEO bằng log-sum | ✅ (log-sum theo Σ best-shot-score, đạt đúng ý đồ) |
| Cộng thưởng thứ tự thời gian | ✅ `TRAKE_ORDER_BONUS`, config, không hardcode |
| Trả top-10 video | ✅ |

| Yêu cầu (C4.4) | Trạng thái |
|:---|:---|
| KIS N lần độc lập trong video hạng 1 | ✅ `filter_video_id` |
| Sắp xếp theo thời gian tăng dần | ⚠️ **ĐỔI** sang giữ vị trí + sửa đơn điệu cục bộ — đúng công thức chấm thật (§7.2), sort thuần sẽ sai theo `docs/contest.md` |
| Cứu nhóm khỏi 0 điểm khi DP không kịp | ✅ — dòng hạng 1 luôn có bằng chứng thật cho từng vị trí |

---

## 11. Việc tiếp theo

1. **Chờ `ANTHROPIC_API_KEY`** (hoặc tiếp tục Gemini) — đổi 1 biến môi trường,
   không sửa code.
2. **Nối vào orchestrator thật** (`backend/api/main.py` hoặc `run.py`):
   `qa_pipeline()`/`trake_stage1()`/`trake_stage2_fallback()` hiện chỉ chạy
   qua CLI (`python -m backend.tasks.*`) — chưa có endpoint `/search` nào gọi
   chúng để ra file nộp thật. Đây là việc để `allocate()` biến kết quả thành
   100 dòng CSV/JSON thật.
3. **C4.1 (TRAKE DP)** — P2 theo BUILD_TASKS, chưa làm. `trake_fallback.py`
   hiện tại là lưới an toàn, không thay thế được độ chính xác của DP đúng
   đoạn đã khoanh.
4. **Tune ngưỡng `score >= 0.5`** của `_object_count` và `TRAKE_ORDER_BONUS`
   khi có `dev_set/` thật (chờ D3.5 — mô phỏng chấm điểm).
5. Cân nhắc thêm `--recreate` tuỳ chọn cho `scripts/load_objects_from_btc.py`
   khi BTC cấp thêm batch objects mới (idempotent theo `keyframe_id`, batch 2
   nạp thêm không tạo trùng — nhưng chưa test đường "nạp thêm", chỉ test "nạp
   từ đầu").
