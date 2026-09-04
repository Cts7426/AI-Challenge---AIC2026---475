# Quyết định vận hành Q&A trước Round 2 — 28/08/2026

## Kết luận điều hành

Giữ `QA_INFERENCE_MODE=legacy` và chạy một batch `run.py` tuần tự, có
checkpoint/resume, bằng đúng provider/model do operator chốt thủ công. Không bật
`two_stage`, không giảm candidate budget, không tắt text fallback, không chạy hai
process song song vào cùng output/checkpoint và không tạo/nộp ZIP bán phần.

Độ trễ hiện tại cao nhưng vẫn có thể lập lịch trong vòng sơ tuyển ba giờ nếu số
câu Q&A Round 2 không lớn hơn đáng kể so với `dress25`: 5 câu RUN 3 mất tổng cộng
1.647,5 giây (27 phút 27,5 giây), median 360,6 giây/câu. Đây không phải một upper
bound. Code không có timeout cấp query nên không có cơ sở để công bố worst-case
số học ngoài observed maximum 476,2 giây.

Tuy nhiên, chưa được dùng artefact hiện hành để release trước khi xử lý một
blocker correctness riêng: RUN 3 đã đưa sentinel `Không đủ căn cứ xác định` vào
2 dòng của `DRESS_QA_01.csv`. Task này không sửa code/config; blocker phải được
sửa và kiểm chứng trong một repair task có phê duyệt riêng.

`dress25` chỉ là diagnostic evidence. Điểm 0,20/5 và mọi đúng/sai từng câu dưới
đây không được dùng làm promotion evidence.

## Phạm vi và phân loại bằng chứng

Báo cáo dùng ba nhãn:

- **Đo được:** lấy trực tiếp từ `candidates.jsonl`, `qa_evidence.jsonl`, CSV và
  timestamp cache của `run_20260827_154710_27d970c1`.
- **Thiết lập trực tiếp từ code/config:** hành vi bắt buộc của call graph, vòng
  lặp, mode, timeout, checkpoint và export.
- **Suy ra:** phép tính hoặc tái dựng từ hai nhóm trên; không được gọi là timing
  đã instrument.

Không chạy `batch1_holdout13`, không sửa provider/model/env, prompt, code, test,
config hoặc deployment. Kiểm tra test chỉ dùng mock/fixture và `dress25` artefact.

## 1. Call graph Q&A hiện hành

```text
run.py::main
  -> giai_mot_query()
    -> backend.tasks.runner.solve_query()
      -> backend.tasks.qa.qa_pipeline()
        -> qa_inference_mode()                 # đóng băng mode cho một query
        -> parse_question()
          -> QA planner llm() n=1             # cache theo full query/fingerprint
          -> rule fallback nếu planner lỗi
        -> route answer_mode -> evidence_type
        -> search(event_vi, top_k=100)         # main retrieval
        -> _ung_vien_nhanh_text()
          -> search(..., vector=False)         # optional text-fallback retrieval
        -> dựng danh sách thử:
             tối đa 5 text hits + top-5 main, dedupe theo shot_id
        -> vòng candidate tuần tự
          -> collect_evidence()
             -> OCR trong shot + ASR ±3s + metadata
             -> objects nếu count; ảnh nếu route bắt buộc
             -> capture/hash evidence
          -> _infer_legacy()
             -> ask_llm(n=3, effort=high, max_tokens=2048)
                -> llm() gọi provider tuần tự 3 lần
             -> nếu confidence trung bình <0,5 và chưa có ảnh:
                collect_evidence(needs_images=True)
                -> ask_llm(n=3) với ảnh
             -> majority vote
          -> build_qa_hypothesis()
             -> pin evidence_frame_idx vào keyframe thật qua frame_map
        -> với tối đa 3 video đã thấy:
          -> _expand_within_video()             # 1 search/video, tối đa 3 shot/video
          -> lặp collect/infer/build như trên
        -> chọn hypothesis confidence cao nhất; không early-stop theo confidence
        -> đẩy shot thắng lên hạng 1 và kiểm frame pin lần cuối
      -> allocate_qa_portfolio()
         -> canonical của mọi hypothesis
         -> tối đa 1 alternative/hypothesis
         -> tail từ candidate retrieval
         -> fail nếu không tạo đúng total=100
      -> QueryRun
    -> checkpoint append + flush + fsync sau từng query thành công
  -> chỉ export CSV/ZIP khi checkpoint đủ toàn bộ query
```

Những điểm quan trọng được thiết lập trực tiếp từ code:

- `legacy` không có generation budget và không dừng khi đã có câu trả lời mạnh.
  Test `test_main_tu_tin_cao_van_thu_het_video_expansion_budget` khóa hành vi
  vẫn chạy video expansion khi main hypothesis có confidence 0,99.
- `llm(n=3)` không gửi một request có ba sample; adapter dùng vòng `for` và gọi
  provider ba lần nối tiếp.
- Mỗi lỗi candidate bị bắt để thử candidate tiếp theo. Nếu cuối cùng không có
  hypothesis hợp lệ, query fail `missing_evidence`, `retryable=true`, không có
  answers bán phần.
- Frame pin fail-closed: hypothesis chỉ được tạo khi `frame_map[keyframe_id]`
  bằng đúng `evidence_frame_idx`.

## 2. Kế toán call và latency của 5 query RUN 3

### 2.1 Bảng theo query

`Text batch`/`image batch` là số lần gọi logic `ask_llm`; mỗi batch RUN 3 dùng
`n=3`. `Text gen` bao gồm 3 generation hỗ trợ không ảnh cho mỗi query: 1 planner
và 2 bản dịch cache-miss (event query và full query). Đây là cách đếm provider
generation, không phải số HTTP retry ở SDK.

| Query | Status | Total (s) | `qa_seconds` (s) | Planner | Retrieval calls | Candidate attempts (initial + expand) | Text batches | Image batches | Text gen | Image/VLM gen | Tổng provider gen thành công | Hypotheses |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `DRESS_QA_01` | success | 360,622 | 360,355 | 1 | 5 | 17 (8+9) | 17 | 15 | 54 | 45 | 99 | 3 |
| `DRESS_QA_02` | success | 210,647 | 208,726 | 1 | 5 | 18 (9+9) | 18 | 0 | 57 | 0 | 57 | 18 |
| `DRESS_QA_03` | success | 476,212 | 476,122 | 1 | 5 | 18 (9+9) | 18 | 17 | 57 | 51 | 108 | 1 |
| `DRESS_QA_04` | failed `missing_evidence` | 404,152 | không ghi do exception | 1 | 5 | 18 (9+9) | 18 | 18 | 57 | 54 | 111 | 0 |
| `DRESS_QA_05` | success | 195,900 | 194,334 | 1 | 5 | 19 (10+9) | 19 | 0 | 60 | 0 | 60 | 19 |
| **Tổng** | 4/5 success | **1.647,534** | — | **5** | **25** | **90** | **90** | **50** | **285** | **150** | **435** | **41** |

Giải thích nguồn số:

- **Đo được:** total/`qa_seconds`, 140 evidence record, 140 inference record,
  attempt origin/order, 41 hypothesis và status/failure.
- **Thiết lập từ code + trace:** mỗi query có 1 main search, 1 text-fallback
  search và 3 filtered video-expansion search; mỗi inference record `legacy`
  yêu cầu `n=3` và adapter thực hiện tuần tự.
- **Tái dựng từ cache:** mỗi query tạo đúng 3 cache entry `n=1` mới trong cửa sổ
  chạy (planner, event translation, full-query translation). Các search lặp lại
  cùng text dùng adapter cache; không phát sinh provider generation mới.

Toàn bộ 140 inference record có `raw_count=parsed_count=requested_n=3`. Validation
đầy đủ, kể cả SHA-256 ảnh hiện còn trên đĩa, trả:

```text
records=280, evidence_records=140, inference_records=140
```

41/41 hypothesis có `keyframe_id -> evidence_frame_idx` khớp `frame_map` hiện
hành. Bốn CSV thành công đều có đúng 100 dòng; `DRESS_QA_04.csv` không tồn tại.

### 2.2 Cache hits/misses

| Lớp cache | RUN 3 |
|---|---|
| QA planner/hypothesis cache | 0 hit; miss lần lượt 33, 19, 36, 37, 20 record cho QA01–05 (gồm 1 planner/query) |
| Adapter cache cho 140 inference batch `n=3` | 0 hit; 140 file cache `n=3` được tạo trong đúng cửa sổ từng query |
| Adapter cache cho dịch lặp | Tái dựng từ call graph: 3 hit/query (event search thứ hai và 2/3 full-query expansion); counter runtime không được lưu vào artefact |

RUN 3 vì vậy là cold-cache cho planner và suy luận candidate. Không được dùng
latency của lần replay sau khi cache đã ấm để lập ngân sách thi cho query mới.

### 2.3 Retry, validation, early stop và fallback thực tế

- **Retries đo được:** không có log/counter retry được persist. Không thể nói
  RUN 3 đã retry bao nhiêu lần. 140 inference batch đều kết thúc với đủ output.
- **Retry được thiết lập từ code:** Anthropic client có timeout 120 giây/request
  và `max_retries=4`; adapter có tối đa 2 lần thử nếu JSON parse hỏng. Structured
  output làm JSON hỏng ít khả năng hơn nhưng không biến con số retry RUN 3 thành
  số đo.
- **Early stop:** không xảy ra và cũng không tồn tại trong `legacy` theo
  confidence. Cả 5 query chạy hết video-expansion budget.
- **Planner fallback:** không query nào dùng; cả 5 planner thành công.
- **Text fallback:** cả 5 query đi vào vì route là `asr` hoặc `ocr`.
- **Image fallback:** QA01 15, QA03 17, QA04 18 batch ảnh; QA02/QA05 không vào.
- **Missing evidence:** QA04 thử đủ 18 shot, 36 inference batch/108 generation
  rồi fail closed, không đoán answer và không tạo partial answer.

## 3. Nút thắt latency

Nút thắt chính là fan-out candidate nhân với self-consistency `n=3`, chạy hoàn
toàn tuần tự, cộng thêm image escalation và video expansion luôn chạy hết.

- 140 logical inference batch trở thành 420 provider generation nối tiếp.
- QA01/03/04 riêng image escalation tạo thêm 45/51/54 VLM generation.
- Với bốn query thành công, `qa_seconds` chiếm 99,1–100,0% total. Phần sau
  `qa_pipeline` (portfolio/serialize) nhiều nhất chỉ 1,92 giây trong artefact này.
- Lấy total chia số provider generation thành công cho từng query cho ra khoảng
  3,27–4,41 giây/generation. Đây chỉ là **derived quotient** còn chứa retrieval,
  evidence I/O và overhead; không phải timing riêng của provider.

Không có instrumentation tách thời gian cho planner, từng `search`, ES/Milvus,
evidence collection hay từng provider request. Vì task cấm thêm instrumentation,
không thể phân rã chính xác hơn mà không suy đoán.

## 4. Các mode hiện được hỗ trợ

| Mode/path | Implemented | Enabled/release | Tests | Replay/diagnostic evidence | Kết luận |
|---|---|---|---|---|---|
| `legacy` | Có; `n=3` mỗi cohort, max_tokens 2048 | Default là `legacy`; deployment/runbook yêu cầu set tường minh | Unit/integration hiện hành | RUN 3 `dress25`; baseline/retrieval artefact cũ. Chỉ diagnostic, không promotion | Mode release duy nhất hiện đủ điều kiện vận hành |
| `two_stage` | Có; screen `n=1`, confirm `n=2`, cap 42 generation | Không được bật trong release hiện hành | Unit test screen/confirm, evidence cohort, cap, mode resolution | Không tìm thấy live replay/promotion artefact; config snapshots hiện có đều `<unset>` và trace RUN 3 resolve `legacy` | Không dùng Round 2 |
| Pre-hypothesis/deprecated lower-cost path | Không còn là production path được hỗ trợ | Không | Chỉ compatibility branch trong runner | Không có evidence release hiện hành | Không hồi sinh |
| Batch async/concurrent | Không được implement trong `run.py`; main loop tuần tự | Không có runbook cho nhiều worker | Cache single-flight chỉ test trùng key trong một process, không chứng minh batch concurrency | Không có | Không dùng |

Tổng bộ test liên quan đã chạy bằng interpreter của repo:

```text
163 passed in 5.21s
```

Bộ này gồm Q&A modes, planner/hypothesis cache, evidence pinning, sentinel hiện
được liệt kê, text fallback, portfolio, checkpoint, full-export và release gate.
Nó chứng minh correctness theo các case đã viết; nó không thay thế replay chất
lượng/latency của `two_stage`.

## 5. Ràng buộc submission/runbook ảnh hưởng vận hành

- Sơ tuyển online, nộp theo lô và không trừ thời gian. Nội bộ có thể hoàn tất
  query theo thời gian trước deadline; đây không phải phép cho chạy concurrent.
- Runbook yêu cầu chạy một lần cho toàn bộ đề ngay khi mở đề, bằng `legacy`, rồi
  dùng checkpoint để resume. Một query hỏng không chặn query sau.
- `--only` được hỗ trợ để retry query hỏng sau full pass; nó vẫn đọc checkpoint
  của toàn bộ input.
- `run.py` không ghi CSV/ZIP nếu checkpoint còn thiếu bất kỳ query nào. Test khóa
  cả trường hợp một query hỏng và trường hợp `--only` chỉ có subset.
- Mỗi file phải đúng 100 dòng; ZIP phải có top-level `submission/`; Q&A <=100 ký
  tự; không có answer bán phần/sentinel; validator và checksum phải qua trước
  upload.
- Runtime fingerprint làm checkpoint hết hạn khi model/mode/config đổi. Không
  đổi provider, model hoặc inference mode giữa run/resume.
- Timeout chỉ tồn tại ở từng provider request. Không có timeout cấp query hay
  numeric worst-case đã được release cam kết.

**Deferred execution:** chỉ có bằng chứng hỗ trợ kiểu “để query hỏng chạy lại sau
bằng `--only` trong cùng checkpoint”. Không có bằng chứng hỗ trợ bỏ Q&A khỏi full
batch rồi nộp ZIP thiếu, và không có hỗ trợ chạy Q&A bất đồng bộ/song song.

## 6. Ma trận quyết định A–D

| Phương án | Support hiện tại | Tác động latency dự kiến | Rủi ro runtime worst-case | Rủi ro evidence | Rủi ro contract | Rủi ro change | Test/replay hiện có | Reversible | Khuyến nghị Round 2 |
|---|---|---|---|---|---|---|---|---|---|
| **A. Giữ current Q&A** | `legacy` là release path chính thức | Không giảm; median quan sát 360,6s, max 476,2s | Trung bình-cao vì không có query timeout; vẫn schedulable theo batch nếu số QA tương tự | Thấp cho pin/hash, nhưng hiện có blocker sentinel cụ thể | Thấp sau khi đủ checkpoint/validator; không được xuất partial ZIP | Thấp nhất | 163 test pass + RUN 3 diagnostic | Cao: resume cùng fingerprint | **Chọn, có điều kiện sửa sentinel riêng trước release** |
| **B. Existing lower-cost/two-stage** | Implemented nhưng release cấm tới khi replay tune+holdout trên evidence cố định | Có thể giảm candidate yếu theo lý thuyết; chưa đo live | Không biết | Cohort/pinning có unit test, chưa có replay release | Cao vì trái runbook/product spec | Trung bình-cao ngay sát thi | Unit only; không có live replay/promotion | Có về env nhưng checkpoint sẽ hết hạn | **Bác bỏ** |
| **C. Giảm candidate/hypothesis budget** | `MAX_SHOTS_TRIED`, `VIDEO_EXPAND_SHOTS`, `MAX_VIDEOS_EXPANDED` là constant trong production code, không phải supported config knob; generation cap chỉ thuộc `two_stage` | Có thể giảm tuyến tính nhưng chưa đo exact effect | Có thể giảm runtime nhưng tăng missing evidence/recall | Trung bình-cao | Trung bình nếu làm mất query/100-row evidence | Cao vì cần code/config change và measurement mới | Không có A/B 5-query cho budget mới | Có thể revert code nhưng không an toàn trước thi | **Bác bỏ** |
| **D. Tắt optional path** | Text fallback có cờ config và test disabled state; image/video expansion không có cờ vận hành tương đương | Tắt text fallback giảm tối đa 5 candidate ban đầu, nhưng effect thật chưa cô lập | Có thể giảm thời gian nhưng đẩy đúng video ra ngoài inference set | Cao: RUN 3 có winner/hypothesis từ text fallback | Có thể tăng `missing_evidence` | Trung bình | Test correctness, không có live disabled replay | Có | **Bác bỏ** |

## 7. Rủi ro và các lựa chọn bị loại

### Blocker sentinel quan sát trực tiếp

`is_valid_qa_answer()` chặn exact sentinel và một tập continuation giới hạn.
Chuỗi `Không đủ căn cứ xác định` không khớp continuation hiện có, nên RUN 3 đã:

1. tạo một `QAHypothesis` cho chuỗi này;
2. đưa nó vào portfolio canonical/alternative;
3. ghi vào dòng 3 và 6 của `DRESS_QA_01.csv`.

Đây là lỗi correctness/output integrity, không phải tuning. Validator format
không thể biết câu này là sentinel. Không được giải quyết bằng cách đoán answer,
xoá dòng thủ công hoặc nộp dưới 100 dòng.

### Các lựa chọn bị loại khác

- Không dùng điểm diagnostic 0,20 để biện minh giảm budget hoặc đổi algorithm.
- Không bật `two_stage`: release constraint yêu cầu replay tune + holdout trên
  evidence cố định; artefact đó chưa tồn tại.
- Không chạy `batch1_holdout13`; task này không chạy và không dùng nó.
- Không đổi model/provider/parameters để chữa latency.
- Không tắt evidence validation/pinning; validation hiện qua 280/280 record và
  41/41 hypothesis pin đúng.
- Không chạy Q&A async/concurrent: không có implementation/runbook, checkpoint
  append và output dir được thiết kế cho một process tuần tự.
- Không chấp nhận missing-evidence bằng guessed/sentinel answer. QA04 phải tiếp
  tục fail và được retry như một query hỏng.
- Không phát hành partial ZIP. Nếu sát hard stop mà checkpoint Round 2 chưa đủ,
  chỉ candidate snapshot cũ đã validator mới là đường lui; không ghép subset.

## 8. Quyết định vận hành Round 2

### Quyết định

Chọn phương án A: giữ `legacy` và toàn bộ candidate/evidence/portfolio path hiện
hành, không tối ưu cost trong task này. Lý do: latency cao nhưng vòng sơ tuyển
không trừ thời gian, full batch có checkpoint và observed 5-query total vẫn nằm
trong ngân sách ba giờ; mọi lựa chọn giảm cost hiện không đáp ứng đồng thời
support, replay và release constraints.

Quyết định có một gate bắt buộc: sửa riêng sentinel surface đã quan sát và chạy
lại test + diagnostic evidence trước khi dùng cho release. Không có workaround
operator an toàn ở tầng CSV.

### Chỉ dẫn operator

1. Chỉ bắt đầu candidate release sau khi repair sentinel riêng được duyệt và
   verification pass. Không sửa CSV bằng tay.
2. Trong đúng terminal chạy Round 2, operator đặt thủ công backend/model đã chốt;
   giữ nguyên suốt run/resume. Sau đó đặt:

   ```powershell
   $env:QA_INFERENCE_MODE = "legacy"
   ```

3. Chạy release preflight và nhìn bằng mắt backend/model/mode được in ra:

   ```powershell
   .venv\Scripts\python.exe scripts\preflight_check.py --profile release
   ```

4. Chạy đúng một process cho toàn bộ đề, không tách Q&A thành worker async và
   không dùng `--fresh`:

   ```powershell
   .venv\Scripts\python.exe run.py --queries data\queries\round2.jsonl --out submissions\round2 --zip --qa-submission-policy robust
   ```

5. Để full pass chạy hết. Query Q&A hỏng không vào checkpoint nhưng query sau
   vẫn chạy. Sau full pass, retry đúng các ID hỏng bằng cùng terminal, mode,
   model, query file và output directory:

   ```powershell
   .venv\Scripts\python.exe run.py --queries data\queries\round2.jsonl --out submissions\round2 --zip --qa-submission-policy robust --only <qa-id-hong-1>,<qa-id-hong-2>
   ```

6. Không đổi `legacy` sang `two_stage`, không giảm budget, không tắt text fallback
   và không chạy process thứ hai vào `submissions\round2`.
7. Chỉ khi command exit 0 và checkpoint đủ toàn bộ query mới kiểm ZIP, checksum,
   snapshot và upload theo runbook. Nếu còn thiếu query, `run.py` phải tiếp tục
   từ chối tạo ZIP.
8. Lập lịch với median diagnostic khoảng 6,0 phút/Q&A và average khoảng 5,5
   phút/Q&A; cộng buffer cho retry. Không dùng 7,9 phút observed max như một
   worst-case guarantee.

---

**Recommended Round-2 Q&A mode:** `legacy`, full-batch tuần tự, checkpoint/resume; không async, không `two_stage`.

**Expected typical runtime/query:** khoảng 360,6 giây (median quan sát của 5 query RUN 3; average 329,5 giây).

**Expected worst-case runtime/query:** không có numeric bound được hỗ trợ vì không có query-level timeout; observed maximum là 476,2 giây/query, không phải projected worst-case.

**Fallback behaviour:** candidate/provider/search lỗi được thử tiếp theo code; nếu cuối cùng không có hypothesis thì fail `missing_evidence`, không checkpoint answer, chạy tiếp query khác, rồi retry riêng bằng `--only` với cùng runtime fingerprint. Không đoán, không sentinel, không partial ZIP.

**Exact operator instructions:** set thủ công provider/model đã chốt; set `QA_INFERENCE_MODE=legacy`; chạy release preflight; chạy một `run.py` full-batch với `--zip --qa-submission-policy robust`; retry query hỏng bằng `--only` trong cùng output/checkpoint; chỉ validate/checksum/upload khi command exit 0 và đủ mọi CSV 100 dòng.

**Code/config repair required before contest: YES**

**If YES, exact blocker requiring a separate repair task:** `is_valid_qa_answer()` hiện cho chuỗi sentinel `Không đủ căn cứ xác định` đi qua; RUN 3 đã ghi chuỗi này vào dòng 3 và 6 của `DRESS_QA_01.csv`. Repair task phải chặn surface này trước khi tạo `QAHypothesis`/portfolio, thêm regression test đúng chuỗi quan sát, giữ fail-closed `missing_evidence`, rồi chạy lại bộ test Q&A/export và diagnostic `dress25` mà không dùng nó làm promotion evidence.
