# BUILD_TASKS.md — Lộ trình 3 đợt sơ tuyển

> **v3 · 21/08/2026** — nguồn task hiện hành cho ba đợt cộng điểm
>
> **Cách dùng:** làm TỪNG task theo thứ tự P0 → P1, chạy thật + test thật rồi mới
> tick. Chủ sở hữu task mới là **Thạch**; không tick dựa trên code “có vẻ đã có”.
>
> Ký hiệu: `[ ]` chưa xong · `[x]` có artefact/test chứng minh · 🔒 gác cổng.

---

## Chiến dịch hiện hành — tổng điểm của 3 đợt

Baseline regression: `dev_set/results/run_20260820_2349` chạy 30/30 query, 0 lỗi,
semantic overall khoảng 0.4817. Đây là tune đã dùng để chỉnh hệ thống, không phải
ước lượng điểm thi. Artefact tái lập `run_20260821_0209` tại commit `78c96e3`
khớp hoàn toàn: semantic 0.4817, exact 0.4017, KIS 0.4957, Q&A 0.48 và
TRAKE 0.325.

Hướng đi:

- Đợt 1 dùng Batch 1: ưu tiên dữ liệu đủ, frame đúng, ZIP hợp lệ và khả năng chạy lại.
- Đợt 2: cải thiện Q&A/TRAKE/KIS miss bằng holdout độc lập và ablation.
- Đợt 3: tối ưu theo sai số tích lũy, không thêm kiến trúc mới, đóng băng sớm.
- Đợt 2–3 chưa có dữ liệu/lịch chính thức nên dùng chu kỳ
  `ingest delta → đo → cải tiến → freeze`, không hardcode ngày.

### R0 — đóng baseline

- [x] **R0.1 · P0 · Đóng baseline hiện tại**
  - Tách thay đổi Q&A đang dở thành checkpoint truy nguồn được.
  - Lưu commit, config snapshot và artefact `run_20260820_2349`.
  - Khôi phục đúng interpreter/dependency và chạy lại regression.
  - **Xong khi:** worktree release sạch; test và baseline có lệnh tái hiện.
  - **Bằng chứng 21/08:** checkpoint `78c96e3`, full suite 596 pass; replay tune
    `run_20260821_0209` chạy 30/30, 0 lỗi và khớp toàn bộ điểm tổng baseline.

### R1 — đợt 1 / Batch 1

- [ ] **R1.1 · P0 · Audit và nạp đủ Batch 1**
  - CSV BTC chỉ là manifest URL. Chạy `scripts/audit_batch_manifest.py` để theo
    dõi từng archive: URL, trạng thái, kích thước, SHA-256, giải nén và số file.
  - Tái sử dụng file đã tải hợp lệ; không giải nén/chuyển đổi bằng script có thể
    ghi lại parquet trước khi dry-run và đối chiếu số dòng.
  - **Xong khi:** mọi URL Batch 1 có trạng thái `present`, hash và asset count;
    core parquet/map/index khớp data manifest.
  - **Tiến độ 21/08:** audit 32 URL, mới có 1 archive (`Keyframes_L21.zip`),
    còn thiếu 31; xem `reports/BATCH1_DATA_AUDIT_20260821.md`.

- [ ] **R1.2 · P0 · Một resolver ảnh cho Q&A/UI/API**
  - `resolve_frame_path(video_id, frame_idx, keyframe_id, btc_ordinal)` ưu tiên
    raw BTC rồi derived, hỗ trợ archive bọc `keyframes_Lxx` và bộ đếm 0/1-based.
  - Không suy frame index từ hậu tố keyframe tự trích.
  - **Xong khi:** unit test resolver xanh; ảnh L26/L28 có trong archive không còn
    bị Q&A báo thiếu; UI và API dùng cùng resolver.
  - **Tiến độ 21/08:** code + unit test đã xanh; chưa tick vì archive L26/L28
    chưa có để kiểm acceptance trên data thật.

- [x] **R1.3 · P0 · Preflight development/release**
  - Sửa mô tả `/health` thành deep check thật.
  - `development` cho phép SKIP có lý do; `release` nâng mục bắt buộc chưa kiểm
    thành FAIL và trả exit code khác 0.
  - Kiểm dependency, ES/Milvus, parquet/meta, frame map, CLIP/meta/norm, ảnh Q&A,
    allocator, validator ZIP và cấu hình.
  - **Xong khi:** test chứng minh từng mục fail được; máy thiếu ảnh/dependency bị
    release chặn nhưng development vẫn chẩn đoán đầy đủ.

- [x] **R1.4 · P0 · Khóa hedge Q&A**
  - Cùng một bể evidence sinh `semantic`, `exact`, `robust`; không chạy retrieval
    hay LLM ba lần.
  - Lệnh release truyền policy tường minh. Đợt 1 dùng `robust` nếu BTC chưa xác nhận.
  - Chỉ nộp một ZIP cuối và ghi policy/checksum.
  - **Xong khi:** unit test portfolio giữ nguyên frame/video/rank và cả ba ZIP qua validator.

- [ ] **R1.5 · P0 · Diễn tập và nộp Batch 1**
  - Full run 0 query lỗi; đúng 100 dòng/câu trừ luật riêng TRAKE; validator sạch.
  - Lưu commit, config, data manifest, log, scores, ZIP SHA-256 và receipt.
  - Khi còn dưới 24 giờ chỉ sửa crash/format/data/frame mapping và task P0.

- [ ] **R1.6 · P1 · Postmortem đợt 1**
  - Đóng băng artefact trước khi phân tích.
  - Phân loại `retrieval_miss`, `wrong_frame`, `qa_reasoning`, `missing_evidence`,
    `trake_order`, `format`; mỗi lỗi có query, bằng chứng và task nối tiếp.

### R2 — cải thiện có đo lường

- [ ] **R2.1 · P0 · Ingest delta idempotent**: so schema/model/map với Batch 1,
  chỉ thêm natural key mới; kiểm trùng, row count và norm. Format đổi thì sửa
  adapter/validator trước khi tune.
- [ ] **R2.2 · P1 · Holdout độc lập**: 12 KIS có cửa sổ hẹp không dựng từ keyframe,
  8 Q&A phủ số/đơn vị/OCR/màu/đếm và 4 TRAKE nhiều sự kiện.
- [ ] **R2.3 · P1 · Ablation retrieval**: đo riêng từng nguồn và weighted RRF theo
  loại query, một biến mỗi lần. Giữ `100 shot × 1 frame` tới khi R2.2 chứng minh khác.
- [ ] **R2.4 · P1 · Q&A evidence-first**: dùng resolver chung; ưu tiên OCR/ASR/text
  cho số/đơn vị, VLM cho thị giác; replay semantic/exact trên cùng evidence.
- [ ] **R2.5 · P1 · TRAKE precision**: tách video-rank/event-rank, tăng top-N mỗi
  event, DP ép thứ tự; chỉ trích frame dày trong candidate video đứng cao.
- [ ] **R2.6 · P0 · Release đợt 2**: regression + release preflight + ba portfolio
  Q&A + diễn tập ZIP; đóng băng tối thiểu 24 giờ nếu lịch cho phép.

### R3 — tối ưu cuối và đóng băng

- [ ] **R3.1 · P0 · Ingest delta + drift check** như R2.1; giữ collection/index cũ
  nếu schema/model tương thích.
- [ ] **R3.2 · P1 · Tối ưu theo sai số tích lũy**: ưu tiên nhóm lỗi có điểm kỳ vọng
  lớn nhất; chỉ dùng profile config theo query type, không thêm tầng/model mới.
- [ ] **R3.3 · P1 · Holdout cuối**: thêm 6 KIS, 4 Q&A, 2 TRAKE và chỉ mở một lần.
- [ ] **R3.4 · P0 · Khóa policy**: Q&A tối đa hóa `min(semantic, exact)`, hòa chọn
  semantic; KIS/TRAKE chọn theo holdout + failure count.
- [ ] **R3.5 · P0 · Final freeze**: đóng băng 48 giờ nếu lịch cho phép; hai full run
  độc lập phải cùng validator result và checksum đầu ra.
- [ ] **POST.1 · P1 · Tổng kết**: lưu điểm ba đợt, artefact, config, failure ledger
  và danh sách hạng mục chuyển sang chung kết.

### Luật promotion và thứ tự cắt

- Correctness/invariant: nhận khi test + regression qua.
- Tuning: tăng ít nhất 0.02 trên tune hoặc tốt hơn ít nhất hai query holdout;
  không giảm holdout và không tạo failure mới.
- Q&A phải replay từ evidence/answer đã lưu, không so hai lần gọi LLM ngẫu nhiên.
- Cắt trước: UI mới → neural reranker → AVS/KISC → index frame dày toàn kho →
  model local nặng → refactor không tác động điểm/độ an toàn.
- Không bao giờ cắt: data/frame map đúng, đủ 100 dòng, exporter/validator,
  release preflight, full rehearsal và receipt.

---

## Lịch sử W0–W3 (01–22/08/2026)

Phần dưới giữ để truy nguồn quyết định cũ. Trạng thái vận hành hiện tại và task
tiếp theo lấy ở R0–R3 phía trên; tên thành viên cũ không còn là owner hiện hành.

## W0 — NỢ KỸ THUẬT (01–02/08) · làm ngay cuối tuần này

Bốn việc này chặn mọi thứ phía sau. Làm trước khi sprint bắt đầu.

**W0.1 [Thạch] — Đổi tên thư mục**
> Đổi tên `preprocessinga/` thành `preprocessing/` cho khớp `CLAUDE.md` mục 9.
> Sửa mọi import trỏ tới nó. Kiểm bằng `grep -rn "preprocessinga" .` → phải rỗng.

**W0.2 [Minh Hoàng] — 🔴 Gỡ bug frame_id khỏi tầng format**
> `submit_format.py` hiện có `_answer_value()` tự suy `frame_id` bằng cách cắt hậu
> tố sau dấu `_` cuối của `keyframe_id` (`L03_V001_0007` → `0007`). Đó là **số thứ
> tự keyframe**, không phải **frame index trong video** mà BTC chấm.
>
> **Không vá bằng cách truyền `frame_map` vào.** Thay vào đó: **xoá hẳn mọi phép
> tính khỏi tầng format.** `submit_format.py` chỉ được ghi ra đúng thứ nó nhận,
> không tự suy ra gì cả.
>
> Trách nhiệm cấp `frame_idx` thật chuyển lên slot allocator (D3.1) — nơi đã có
> `frame_map`. Làm vậy thì lỗi này không thể tái diễn về mặt cấu trúc, chứ không
> phải vá một lần rồi người sau viết lại y như cũ.
>
> Nếu `Answer` thiếu `frame_idx` → raise lỗi rõ ràng, **tuyệt đối không đoán**.
> - Trách nhiệm tra `keyframe_id → frame_idx` chuyển lên slot allocator (D3.1)
>
> Lý do làm vậy thay vì vá: sau khi tầng format không còn khả năng tự tính, bug này
> **không thể tái diễn về mặt cấu trúc** — kể cả khi sau này có người viết lại module.
> Giải thích cho tôi vì sao lỗi cũ nguy hiểm (nó không crash, chỉ trả về số sai).

**W0.3 [Thạch] — /health thành deep check**
> `/health` hiện chỉ trả `{"status":"ok"}` — chứng minh FastAPI sống, không chứng minh
> nối được DB. Sửa thành ping thật vector store + Elasticsearch, trả trạng thái từng
> cái kèm latency. Trả HTTP 503 nếu có cái nào chết.

**W0.4 [Thạch] — Chuyển repo ra khỏi OneDrive**
> Repo đang ở `C:\Users\...\OneDrive\...`. Khi dataset về, OneDrive sẽ cố sync hàng
> triệu keyframe → treo máy, xung đột khóa file, hỏng Docker volume.
> Chuyển sang `C:\dev\aic2026` (hoặc trong WSL: `~/aic2026`). Cập nhật đường dẫn trong config.

**W0.5 [Công Lý] — 🔴 BẮT ĐẦU TẢI DATA NGAY**
> Không phải task cho Claude Code. Tải **20 video trước** để cả nhóm có cái chạy thử,
> rồi mới tải phần còn lại. Video rất nặng, có thể mất nhiều ngày, và nó nằm trên đường găng.

**W0.6 [Linh] — 🔴 GỬI CÂU HỎI BTC** (xem `KE_HOACH_3_TUAN` mục 7)

---

## W1 (03–09/08) — NỀN MÓNG + BASELINE NỘP ĐƯỢC

> 🎯 **Mục tiêu tuần: ngày 09/08 có file nộp hợp lệ sinh từ pipeline thật.**
> Không đặt job GPU nào lên đường găng tuần này.

### 🔒 B0.1 [Công Lý] — Audit dữ liệu & frame_map · 03→06/08 · GÁC CỔNG

**B0.1a**
> Viết `backend/indexing/build_video_info.py` sinh `derived/video_info.parquet`:
> `video_id`, `fps_num`, `fps_den`, `n_frames`, `duration_s`, `width`, `height`.
> - `n_frames` đếm **thật** bằng `ffprobe`, KHÔNG lấy từ metadata container
> - fps ở **dạng phân số** (`fps_num`/`fps_den`), KHÔNG làm tròn. Giải thích cho tôi
>   vì sao 29.97 phải là 30000/1001.

**B0.1b**
> Tìm file map keyframe của BTC (mùa trước là `map-keyframes` CSV với cột `n`,
> `pts_time`, `fps`, `frame_idx`). Viết loader sinh `frame_map`: `keyframe_id → frame_idx`.
> Nếu không tìm thấy file map, báo tôi ngay — đây là blocker, đừng tự suy ra.

**B0.1c — XÁC THỰC BẰNG MẮT**
> Viết `scripts/verify_frame_map.py`: lấy 20 keyframe ngẫu nhiên, dùng `frame_map`
> trích frame tương ứng từ video gốc bằng ffmpeg, so sánh pixel với ảnh keyframe BTC.
> ```bash
> ffmpeg -i video.mp4 -vf "select=eq(n\,1234)" -vsync 0 -frames:v 1 out.png
> ```
> In ra bảng: keyframe_id · frame_idx · độ lệch pixel · ĐẠT/KHÔNG.
> **Sai lệch > 1 frame ở bất kỳ mẫu nào → in cảnh báo đỏ và exit code khác 0.**

### A1.0 [Thạch] — Nạp CLIP B/32 của BTC · 04→06/08

**A1.0a**
> Cập nhật `data/config/clip_model.py`: model `clip-ViT-B-32`, 512 chiều.
> Viết loader đọc `.npy` BTC cấp → chuẩn hóa L2 → nạp vào vector store.
> Ghi kèm `.meta.json` (model, version, ngày, commit) và assert lúc load.

**A1.0b — ⚠️ KIỂM CHỨNG KHÔNG GIAN VECTOR**
> Viết `scripts/verify_clip_space.py`: lấy 1 keyframe BTC đã có feature, tự encode lại
> bằng `clip-ViT-B-32`, tính cosine với vector BTC cấp.
> - ≈ 1.0 → ĐẠT
> - ~0 → sai model, **in cảnh báo đỏ và dừng**
> - 0.5–0.9 → nghi ngờ preprocessing/chuẩn hóa khác, báo tôi
> Chạy trên 10 mẫu, in bảng kết quả.

### ✅ C0.1 [Thi] — llm() adapter · 03→06/08
> 🔴 **Thạch đã làm thay để kịp tiến độ.**
>
> Hoàn thiện `backend/llm/adapter.py`:
> `llm(prompt, images=None, json_schema=None, n=1, temperature=0) -> str`
> - Đổi backend API ↔ local bằng biến môi trường `LLM_BACKEND`, **một dòng config**
> - Retry với backoff mũ · cache trên đĩa theo hash prompt · đếm token + chi phí tích lũy
> - Validator JSON tự động, retry khi output hỏng
> Kiểm: `grep -rn "anthropic\|openai" backend/ | grep -v backend/llm/` → **phải rỗng**.

### ✅ C1.1 [Thi] — Hiểu truy vấn v1 · 06→09/08
> 🔴 **Thạch đã làm thay để kịp tiến độ.**
>
> `backend/retrieval/query_understanding.py` nhận query tiếng Việt, trả:
> `{caption_main, captions_expanded[4], constraints_json}`
> - Prompt dịch: 1 caption EN ngắn, phong cách chú thích ảnh
> - Prompt mở rộng: 4 caption EN khác nhau, **cấm thêm chi tiết không có trong query gốc**
> - Prompt trích ràng buộc: `{scene, objects, colors, count, time, text_seen}`
> - ⚠️ Mỗi caption ≤ 60 token **kiểm bằng tokenizer trong code**, không ước lượng bằng mắt
> - Cache theo hash query

### D0.2 [Minh Hoàng] — Export + validator · 03→06/08
> `backend/export.py` với `to_submission(rows, fmt)` — format tách rời **hoàn toàn**
> khỏi pipeline, đổi format = đổi 1 tham số.
> Validator kiểm: đúng 100 dòng/query · `video_id` tồn tại · `frame_id ∈ [0, n_frames)` ·
> không dòng trùng lặp hoàn toàn · TRAKE có đúng N frame và **thứ tự tăng dần** ·
> Q&A có `answer` không rỗng · UTF-8 không BOM.
> **Gộp thêm từ W0.2** — interface mới của `build_submission()`:
> ```python
> build_submission(query_id, task_type, answers: list[Answer])
>
> @dataclass
> class Answer:
>     video_id: str
>     frame_ids: list[int]      # TRAKE có N phần tử; KIS/Q&A có 1
>     answer_text: str | None   # chỉ Q&A
>     keyframe_id: str          # giữ để debug + map lại nếu BTC đổi format
> ```
> - **Thứ hạng = thứ tự phần tử trong list.** Không truyền `rank` riêng (dễ lệch với
>   thứ tự thật). Việc file có cột `rank` hay không là quyết định của tầng format.
> - Một hàm chung cho cả 3 dạng bài, không tách 3 hàm.
>
> **Validator chia hai tầng:**
> - *Format* (đúng cột, đúng kiểu, đúng encoding) → cạnh `submit_format.py`
> - *Ngữ nghĩa* (đủ 100 dòng · `frame_id ∈ [0, n_frames)` · không trùng · TRAKE tăng
>   dần · Q&A có `answer`) → trong `export.py`, vì cần đọc `video_info.parquet`

### D3.1 [Minh Hoàng] — Slot allocator v1 · 06→09/08
> `backend/slot/allocator.py` — nhận top-K shot + `query_type`, trả **đúng 100 dòng đã xếp hạng**.
>
> KIS (bảng khởi điểm, để trong config): 3 shot×8 frame + 7×5 + 10×3 + 11×1 = 100
>
> **Thứ tự nộp:**
> - ⚠️ **XEN KẼ theo shot, KHÔNG gom theo shot.** Slot 1 = frame tốt nhất shot 1,
>   slot 2 = shot 2, slot 3 = shot 3, slot 4 = frame thứ hai shot 1...
>   Lý do: R@1+R@5 = 40% điểm; 8 slot đầu cùng một shot mà shot đó sai là mất trắng.
>
> **Chọn frame trong mỗi shot:**
> - ⚠️ **`frame_idx` không cần là keyframe đã index** — chỉ cần số nguyên trong
>   `[0, n_frames)` thuộc shot đó. Độ sâu là miễn phí.
> - **Frame ĐẦU TIÊN của mỗi shot = keyframe có điểm cao nhất** (frame mình thực sự
>   có bằng chứng), KHÔNG phải điểm giữa tính toán ra.
> - Các frame tiếp theo: rải đều phần còn lại của shot, **thụt vào 10% mỗi đầu** để
>   tránh frame chuyển cảnh (mờ, lẫn hai cảnh). Ép về `int`, khử trùng lặp.
> - ⚠️ **Slot allocator chịu trách nhiệm cấp `frame_idx` THẬT.** Tra qua `frame_map`
>   của B0.1, hoặc tính từ `start_frame`/`end_frame` của shot. Tầng format không tra
>   bảng, không suy luận — nó chỉ ghi ra con số nhận được.
>
> **Bất biến:**
> - ⚠️ **KHÔNG BAO GIỜ trả < 100 dòng**, kể cả khi chỉ tìm được 3 shot. Bù bằng cách
>   rải thêm frame trong các shot đã có.
> - Unit test cả ba dạng bài, gồm case biên: shot chỉ được 1 slot, shot ngắn hơn số
>   slot được cấp, và trường hợp chỉ có 3 shot ứng viên.

### A2.1 + A2.2 [Thạch] — Search + RRF · 06→09/08
> `backend/retrieval/search.py`:
> - Nhánh vector: search trên CLIP features
> - Nhánh text: BM25 trên metadata (title, description, keywords)
> - Hợp nhất bằng **RRF**: `score(d) = Σ_nhánh 1/(60 + rank_nhánh(d))`, k trong config
> - Bật/tắt từng nhánh bằng config
> - ⚠️ **LOG THỨ HẠNG TỪNG NHÁNH** cho mỗi kết quả. Bắt buộc — không có thì tuần sau
>   phân tích lỗi thành đoán mò.
> - Gom về shot, lấy điểm max mỗi shot
> - **Đừng đặt ngưỡng điểm cứng** — cosine CLIP thực tế chỉ quanh 0.2–0.3

### B1.1 [Công Lý] — Shot segmentation · 06→09/08
> TransNetV2 → `derived/shots.parquet` (`shot_id`, `video_id`, `start_frame`,
> `end_frame`, `rep_kf_id`). Shot > 60s cắt cưỡng bức thành đoạn 30s.
> Nếu TransNetV2 chậm/khó cài: PySceneDetect chế độ content, threshold 27.

### ✅ A6.2-early [Thạch] — Orchestrator tối giản · 08→09/08
> `run_minimal.py`: nhận file query → chạy search → slot allocator → export → file nộp.
> Chỉ CLIP + BM25 + slot, **không rerank, không VLM**.
> Đây là thứ chứng minh G2 và cũng là kịch bản dự phòng cho ngày nộp.

> ### 🚩 G1 — 06/08: `frame_map` xanh chưa? Ba người xác thực độc lập chưa?
> ### 🚩 G2 — 09/08: CÓ FILE NỘP HỢP LỆ CHƯA?
> **G2 không đạt → cắt sạch P2, cả nhóm dồn vào ghép ống.**

---

## W2 (10–16/08) — BA DẠNG BÀI + TÍN HIỆU

> 🎯 **Mục tiêu: cả KIS, Q&A, TRAKE đều có điểm đo được.**

### B1.2 [Công Lý] — Trích keyframe · 10→12/08
> **1 fps** (không phải 2), tối thiểu 2/shot, tối đa 20/shot. JPEG q90, cạnh dài 448px.
> `derived/keyframes.parquet`: `kf_id`, `video_id`, `shot_id`, `frame_idx`, `path`, `row_id`.
> - `frame_idx` khớp **tuyệt đối** video gốc — test lại 20 mẫu
> - Job **resume được** sau khi phiên Kaggle ngắt
> - Nhắc tôi: mật độ này chỉ để tìm đúng shot; độ sâu slot lấy từ frame_idx phát ra.

### B1.3 [Công Lý + Linh vận hành] — ASR · 10→14/08
> `preprocessing/asr_job.py`:
> - **Tách audio khỏi video TRƯỚC** khi upload Kaggle (nhẹ hơn cả chục lần)
> - PhoWhisper hoặc faster-whisper
> - `derived/asr.parquet`: `video_id`, `seg_id`, `start_s`, `end_s`,
>   **`start_frame`, `end_frame`** (quy đổi sẵn), `text_vi`
> - Video không có tiếng → đánh dấu, không coi là lỗi
> - Checkpoint mỗi lô, ghi `manifest.json`, chia việc bằng `hash(video_id) % 5`

### B1.4 [Công Lý + Linh vận hành] — OCR · 12→16/08
> PaddleOCR trên `rep_kf` + keyframe có text-region.
> - **Lọc trước bằng text-detector nhẹ** → giảm ~80% khối lượng
> - `text_clean` qua `llm()` sửa dấu tiếng Việt, **GIỮ NGUYÊN `text_raw`**
>   (LLM đôi khi "sửa" sai và làm hỏng tên riêng)
> - Kiểm 30 mẫu chữ chạy dưới màn hình, đọc đúng ≥ 80%

### B1.7 [Công Lý] — docs_bm25 · 14→16/08
> Gộp một hàng mỗi keyframe: `doc_text` = metadata title + description + ASR
> (segment phủ frame này **±3s**) + OCR `text_clean` + object labels.
> - ⚠️ ASR gán theo cửa sổ ±3s, **KHÔNG gán cả video**
> - Metadata là mỏ vàng: với bản tin, `description` thường liệt kê sẵn toàn bộ tin
>   trong chương trình
> - Tra thử một tên riêng hiếm → phải ra đúng frame

### ✅ C3.1 [Thi] — Pipeline Q&A · 10→14/08
> `backend/tasks/qa.py`:
> - Chạy pipeline KIS trên phần "mô tả sự kiện" → top-K shot
> - Thu bằng chứng mỗi shot: 8 frame + ASR ±3s + OCR + object + metadata
> - **Định tuyến theo loại câu hỏi** (bảng trong config):
>   tên/chức danh → OCR · địa điểm → OCR+metadata · lời nói → ASR ·
>   **đếm → detector, KHÔNG hỏi VLM** · màu → thị giác · số/tỉ số → OCR
> - VLM trả JSON: `answer`, `answer_vi`, `answer_en`, `evidence_frame_idx`,
>   `confidence`, `evidence_type`
> - `evidence_frame_idx` là frame **chứa bằng chứng**, không phải `rep_kf`
> - Tự nhất quán n=3, temperature 0.7, lấy đa số
> - Answer **ngắn nhất mà vẫn đủ**: `"5"` không phải `"khoảng 5 người"`
> - Nhắc tôi hai cửa tử độc lập: frame sai = 0, answer sai = 0.

### ✅ C3.2 [Thi] — TRAKE giai đoạn 1 · 12→16/08
> `backend/tasks/trake.py` — chắc video:
> - Ghép **toàn bộ N mô tả sự kiện** thành truy vấn tổng hợp → pipeline KIS
> - **Gom điểm ở cấp VIDEO bằng log-sum**, không cấp shot
> - Cộng thưởng nếu N sự kiện xuất hiện trong cùng video **đúng thứ tự thời gian**
> - Trả top-10 video xếp hạng
> - Nhắc tôi: sai video = 0 tuyệt đối, nên giai đoạn 1 quan trọng hơn giai đoạn 2.

### ✅ C4.4 [Thi] — Fallback TRAKE · 14→16/08 · **LÀM SỚM, ĐỪNG ĐỢI THẤT BẠI**
> `backend/tasks/trake_fallback.py`: chạy pipeline KIS **N lần độc lập** cho N mô tả
> trong video hạng 1, sắp xếp kết quả theo thứ tự thời gian tăng dần, nộp.
> Đây là thứ cứu nhóm khỏi 0 điểm ở 1/3 số câu nếu DP không kịp.
>
> ⚠️ **20/08 — file riêng đã bị xoá lúc gộp DP (16/08, commit `638495d`),
> phát hiện lại khi kiểm tra toàn diện TRAKE.** Kiến trúc mới (1 DP hợp nhất,
> không còn stage1/stage2 tách rời) khiến bản fallback CŨ (dùng
> `filter_video_id` trong video hạng 1 đã chốt) không còn khớp. Viết lại lưới
> an toàn GỌN TRONG `backend/tasks/trake.py` thay vì file riêng:
> `parse_events()` rơi về tách heuristic không cần LLM khi LLM lỗi,
> `trake_search()` thử search cứu cánh khi mọi sự kiện đều rỗng. Chi tiết +
> đo thật: `reports/trake_hardening.md`.

### D2.1 [Minh Hoàng] — UI debug · 10→13/08 · **Streamlit, KHÔNG React**
> - Nhập query → thấy kết quả **từng tầng cạnh nhau** (sau RRF / sau rerank)
> - Click một frame → thấy ngay caption, OCR, ASR, object của frame đó
> - **Hiển thị thứ hạng từng nhánh** cho mỗi kết quả
> - Nút "đúng/sai" ghi thẳng vào `dev_set/labels.jsonl`

### D3.5 [Minh Hoàng] — Mô phỏng chấm điểm · 14→16/08
> `app/score_simulator.py`:
> - Với mỗi query dev: hiện 100 slot đã nộp, đánh dấu slot nào đúng
> - Chỉ ra slot thắng cho từng ngưỡng R@1/R@5/R@20/R@50/R@100
> - **Thử lại phân bổ khác NGAY LẬP TỨC** mà không chạy lại pipeline — chỉ sắp xếp
>   lại danh sách ứng viên đã có
> - Trả lời được: "đổi từ 3 shot×8 frame sang 5 shot×5 frame thì điểm đổi thế nào"
> Đây là công cụ có tỉ lệ điểm/giờ cao nhất cả dự án.

### E4.2 [Minh Hoàng code, Linh đặc tả] — eval.py · 10→13/08
> Một lệnh ra đúng `Final Score` theo công thức thể lệ, tách theo dạng bài.
> **Xuất riêng R@1, R@5, R@20, R@50, R@100** — để biết đang yếu ở recall hay ở ranking.
> Hai bệnh này cần hai thuốc khác nhau.

> ### 🚩 G3 — 16/08: ba dạng bài đều có điểm chưa?
> ★ 20:00 phiên phân tích lỗi — xem 10 câu sai tệ nhất, chốt **3 việc** cho W3

---

## W3 (17–22/08) — TỐI ƯU + NỘP

> 🎯 **Mục tiêu: nộp an toàn. Không thêm tính năng.**

### A2.4 [Thạch] — Rerank text · 17→19/08 · *chỉ nếu G3 xanh*
> BGE-reranker-v2-m3 trên `doc_text`, 300 shot → 100.
> **Đo mức tăng nDCG@20 trên dev set.** Không tăng → tắt, đừng để mặc định.

### D4.1 [Minh Hoàng] — Chỉnh slot theo dữ liệu · 17→19/08
> Dùng `score_simulator`: shot đúng thường xếp hạng bao nhiêu trên dev set?
> - Hay ở hạng 1 (precision cao) → dịch phân bổ về phía **SÂU**
> - Thứ hạng phân tán → dịch về phía **RỘNG**
> Ghi bảng thử vào `reports/slot_tuning.md`. Đây là điểm miễn phí, không cần model mạnh hơn.

### C4.1 [Thi] — TRAKE DP · 17→20/08 · **P2, cắt được**
> `backend/tasks/trake_dp.py`:
> - Giải nén frame dày **chỉ trong đoạn đã khoanh**, không cả video
> - Ma trận `S[N][T]` = độ khớp sự kiện j với frame t
> - **Chuẩn hóa softmax theo cột:** `S[j][t] ← log(exp(S[j][t]/τ) / Σ_j' exp(S[j'][t]/τ))`
>   → trả lời đúng câu hỏi *"frame t khớp sự kiện nào nhất"* thay vì *"frame t giống
>   mô tả j bao nhiêu"*. Các mô tả trong cùng chuỗi rất giống nhau nên cosine tuyệt đối
>   gần như không phân biệt được. Vài dòng code, khác biệt lớn.
> - DP ép thứ tự tăng dần: `DP[j][t] = S[j][t] + max_{t'<t} DP[j-1][t']`
> - ⚠️ **BẮT BUỘC unit test bằng dữ liệu tổng hợp** — tạo chuỗi giả có đáp án biết
>   trước, kiểm DP tìm ra đúng. Thuật toán này rất dễ sai chỉ số mà chạy vẫn ra kết
>   quả trông hợp lý.
> - K-best: sinh K đường đi khác nhau, **giữ nguyên sự kiện điểm cao chắc chắn, chỉ
>   dịch chuyển sự kiện có điểm gần nhau**. Đảo cái đang đúng thì mất điểm chứ không được gì.
>
> **Không đạt R-Score 0.3 ở 20/08 → chuyển hẳn sang C4.4 fallback.**

### ✅ A6.0 [Thạch] — Orchestrator đầy đủ · 17→19/08
> `run.py`: nhận file query → ra file nộp. Progress bar. Log rõ query nào lỗi và lỗi gì.
> Chạy tiếp được khi một query hỏng. Checkpoint từng query.

### B2.3 [Công Lý] — Kiểm toàn vẹn cuối · 19→20/08
> - Assert số hàng khớp giữa `keyframes.parquet` ↔ ma trận embedding ↔ `docs_bm25`
> - Không `kf_id` nào có trong index mà thiếu trong parquet và ngược lại
> - **Kiểm lại `frame_map` trên 20 mẫu MỚI** (không phải 20 mẫu đã dùng ở B0.1)

### D6.1 [Minh Hoàng] — Preflight check · 19→20/08
> `scripts/preflight_check.py` — một lệnh tự kiểm toàn bộ checklist, in ĐẠT/KHÔNG ĐẠT,
> exit code khác 0 nếu có mục fail. Tick tay lúc 2 giờ sáng ngày nộp là công thức bỏ sót.

### E6.1 [Linh] — Diễn tập nộp · 19→20/08 · **TRƯỚC HẠN ÍT NHẤT 2 NGÀY**
> Chạy đầu-cuối 50 query giả → export → validator → preflight →
> **nộp thử lên hệ thống BTC nếu có kênh thử**.
> Phát hiện sai format ngày 20/08 thì còn sửa được. Ngày 22/08 thì không.

**20/08 — ĐÓNG BĂNG.** Sau mốc này chỉ sửa lỗi, không thêm tính năng.
**21/08 — Chạy thi & nộp.** · **22–25/08 — Đệm.**

---

## Thứ tự cắt nếu trễ

Cắt từ trên xuống:
1. SigLIP re-encode (dùng CLIP B/32 của BTC)
2. Caption VLM
3. TRAKE DP (chuyển sang fallback C4.4)
4. Rerank text
5. OCR (giữ ASR + metadata)
6. UI debug (chạy bằng script)

**Không bao giờ bỏ:** `frame_map` đúng · slot allocator đủ 100 dòng · export + validator ·
orchestrator · diễn tập nộp.

---

## Đã hoãn sang chung kết — KHÔNG ĐỤNG

Agent layer (KISC + track tự động) · AVS · Long-CLIP · InternVideo2 · LoRA fine-tune ·
modality gap correction · αQE · DBA · rerank so sánh cặp · calibration xác suất ·
slot submodular greedy · caption-space retrieval · face clustering · color index ·
audio events · dedup video · phân cấp scene · prompt ensembling · PRF · UI thi đấu

Toàn bộ tầng 1–2 tái dùng nguyên vẹn cho chung kết. Không có công sức nào bị phí.

### Z1.1 [Hậu Sơ Loại] — Chuẩn hoá boundary Search - Submit
> ⚠️ **TỪNG GÂY LỖI ÂM THẦM**: Lệch type giữa dict và ShotHit khiến `getattr(h, "shot_id", "unknown")` trên dict 
> lặng lẽ trả về `"unknown"` mà không báo lỗi, biến toàn bộ ứng viên thành shot_id lạ ở tầng nộp bài.
> Cần chuẩn hóa chung một type duy nhất (`ShotHit` hoặc class/dict cụ thể) ở ranh giới giữa tầng search 
> và tầng nộp bài (allocator, pipeline QA, run_minimal). Loại bỏ mọi chắp vá `isinstance(h, ShotHit)` 
> hay dùng thử `.get()` ở từng điểm tiêu thụ.
