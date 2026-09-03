# BUILD_TASKS.md — Lộ trình 3 đợt sơ tuyển

> **v4 · 31/08/2026** — chiến dịch đang chạy là
> **"Chiến dịch Đợt 3 — bốn làn · 31/08 → 03/09"**. Đọc mục đó trước; các mục
> W0–W3 và R0–R2 giữ làm lịch sử. Mục `Thứ tự cắt nếu trễ` có **một dòng đã bị
> đảo** cho Đợt 3 — xem ghi chú tại chỗ.
>
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

- [x] **R1.1 · P0 · Audit và nạp đủ lớp dữ liệu cần cho Batch 1**
  - CSV BTC chỉ là manifest URL. Chạy `scripts/audit_batch_manifest.py` để theo
    dõi đủ 32 archive: URL, trạng thái, kích thước, SHA-256, giải nén và số file.
  - Bộ bắt buộc đợt 1 gồm 14 archive keyframe + 4 archive lõi. 14 archive video
    vẫn được audit nhưng gắn `deferred_not_required_round1`; chỉ tải khi một task
    đã đo được thật sự cần pixel video/frame dày.
  - Tái sử dụng file đã tải hợp lệ; không giải nén/chuyển đổi bằng script có thể
    ghi lại parquet trước khi dry-run và đối chiếu số dòng.
  - **Xong khi:** bộ bắt buộc 18/18 có trạng thái `present`, SHA-256, số member
    của từng ZIP và số member đã giải nén khớp; 14 video có trạng thái deferred.
    Snapshot raw/derived nằm trong artefact; trạng thái database live được kiểm
    bằng preflight riêng, không suy từ việc file archive có mặt.
  - **Bằng chứng 21/08:** `reports/BATCH1_OPERATIONAL_MANIFEST_20260821.json`
    lưu provenance, kích thước + SHA-256 và asset count độc lập cho 18/18 gói
    bắt buộc; `round1_operational_audit_complete=true`. Raw aggregate có 177.321
    ảnh/873 video; meta artefact được chụp riêng. 14/14 video mang trạng thái
    `deferred_not_required_round1`; live ES/Milvus vẫn qua cổng release preflight.

- [x] **R1.2 · P0 · Một resolver ảnh cho Q&A/UI/API**
  - `resolve_frame_path(video_id, frame_idx, keyframe_id, btc_ordinal)` ưu tiên
    raw BTC rồi derived, hỗ trợ archive bọc `keyframes_Lxx` và bộ đếm 0/1-based.
  - Không suy frame index từ hậu tố keyframe tự trích.
  - **Xong khi:** unit test resolver xanh; ảnh L26/L28 có trong archive không còn
    bị Q&A báo thiếu; UI và API dùng cùng resolver.
  - **Bằng chứng 21/08 15:20:** archive L26/L28 đã giải nén; 25 keyframe ngẫu
    nhiên từ `frame_map` → `resolve_frame_path()` trả file tồn tại **25/25**;
    `preflight_check.py --profile release` báo *ảnh phủ đủ 873/873 video*
    (trước đó 0/873). Suite 628 passed / 1 skipped.

- [x] **R1.3 · P0 · Preflight development/release**
  - Sửa mô tả `/health` thành deep check thật.
  - `development` cho phép SKIP có lý do; `release` nâng mục bắt buộc chưa kiểm
    thành FAIL và trả exit code khác 0.
  - Kiểm dependency, ES/Milvus, parquet/meta, frame map, CLIP/meta/norm, ảnh Q&A,
    allocator, validator ZIP và cấu hình.
  - **Xong khi:** test chứng minh từng mục fail được; máy thiếu ảnh/dependency bị
    release chặn nhưng development vẫn chẩn đoán đầy đủ.
  - **Bằng chứng 21/08:** profile `release` với model đặt thủ công đạt `17`, hỏng
    `0`; hai mục bỏ qua chỉ là Streamlit tùy chọn và `/health` khi API chưa bật.
    Search 100 shot mất `5.2s`; ZIP 3 dạng × 100 dòng qua validator.

- [x] **R1.4 · P0 · Khóa hedge Q&A**
  - Cùng một bể evidence sinh `semantic`, `exact`, `robust`; không chạy retrieval
    hay LLM ba lần.
  - Lệnh release truyền policy tường minh. Đợt 1 dùng `robust` nếu BTC chưa xác nhận.
  - Chỉ nộp một ZIP cuối và ghi policy/checksum.
  - **Xong khi:** unit test portfolio giữ nguyên frame/video/rank và cả ba ZIP qua validator.

- [x] **R1.4a · P1 · Giảm lượt sinh và độ dài output không cần thiết**
  - Dịch query giới hạn 128 token; parse Q&A/TRAKE và query understanding có
    output cap riêng thay vì dùng mặc định 2.048 cho mọi tác vụ ngắn.
  - Script sinh biến thể query gộp 1 lượt sinh + tối đa 5 lượt tự kiểm thành một
    structured request; unit test chứng minh chỉ gọi model đúng một lần.
  - `eval_kis_only` lấy bản dịch cố định từ `tune_all.json` và fail trước DB nếu
    còn thiếu, nên phép đo KIS không thể âm thầm gọi API. Lần chạy 21/08 đạt
    `Final=0.539`, top-100 `18/23`, so với artefact cũ `0.522`, `17/23`.
  - Model release không được hardcode/auto-switch trong code: người vận hành đặt
    thủ công trước lệnh chạy, preflight chỉ in lại để kiểm bằng mắt.

- [ ] **R1.4b · P1 · Promotion Q&A hai tầng để giảm thời gian**
  - Code `two_stage` đã có sau cờ `QA_INFERENCE_MODE`: screen `n=1`, chỉ confirm
    thêm `n=2` trên đúng evidence; đổi text→image phải reset phiếu. `legacy` vẫn
    là mặc định release và rollback tức thời.
  - **Xong khi:** replay bằng model release trên evidence cố định cho tune +
    holdout, đo generation/thời gian/query; không giảm điểm, không sinh failure
    và qua luật promotion. Chưa tick vì chưa có live regression so với `legacy`.

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
  loại query, một biến mỗi lần. Giữ bảng hiện hành 97 shot/100 dòng tới khi R2.2
  chứng minh khác.
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

---

## Chiến dịch Đợt 3 — bốn làn · 31/08 → 03/09/2026

> **Chốt 31/08/2026.** Đợt 3 thi **04/09 19:30**, còn **4 ngày làm việc**
> (31/08, 01/09, 02/09, 03/09). Mọi mốc dưới đây tính theo 4 ngày, không phải 6.

### Vì sao có chiến dịch này

Điểm **hệ thống thật sự kiếm được**, tách khỏi phần tìm bằng mắt:

| Đợt | Nộp lên BTC | Hệ thống tự kiếm | Trung bình/câu |
|---|---|---|---|
| 1 · 21/08 | 8,6/13 | **6,8** | 0,523 |
| 2 · 28/08 | 13,6/15 | **4,4** | 0,293 |

Điều kiện vào chung kết là chạy bằng hệ thống của chính đội và nộp mã nguồn cho
BTC kiểm. Khoảng cách 13,6 với 4,4 sẽ bị phơi ra ở vòng đó dù có muốn hay không.
Chiến dịch này để khép khoảng cách đó.

Chẩn đoán từ `run_20260828_round2_single_anchor_final_01` (19 câu KIS):

- `R@1 = 0,0526` · `R@5 = 0,4211` · `R@100 = 0,5789`
- **8/19 câu trượt sạch 100 dòng** → tường recall
- **7/19 câu nằm hạng 2–5** → tường ranking; kéo 7 câu này lên hạng 1 là `+0,074`
  Final mà không cần model mới
- `wrong_frame` 14/19 → tường temporal
- Q&A: 196–476 s/câu, ~87 lời gọi LLM/câu, điểm ~0
- TRAKE: 100 dòng = 100 video khác nhau nên R@5..R@100 không bao giờ vượt R@1

### 🔓 Đảo một quyết định đã ghi thành văn

Mục `Thứ tự cắt nếu trễ` phía dưới ghi **"1. SigLIP re-encode (dùng CLIP B/32 của
BTC)"** đứng đầu danh sách cắt. Chiến dịch này **làm đúng thứ đó**.

Lý do đảo: dòng đó viết khi chưa có số đo. Giờ có rồi — `R@1 = 0,0526` và 8/19
câu trượt sạch. Mọi cải tiến khác chỉ xếp lại thứ hạng **bên trong** tập ứng viên
mà encoder đã bỏ sót. Đây là quyết định có ý thức của Thạch ngày 31/08, không
phải bỏ quên luật cũ.

### Bộ đo dùng cho toàn chiến dịch

`dev_set/ground_truth/official_r1r2.jsonl` — **55 câu đề chính thức** Đợt 1+2,
dựng lại được bằng `dev_set/tools/build_official_gt.py`.

- **41 câu dùng được ngay** ở mức video (`video_confidence >= HIGH`)
- Tách riêng `video_confidence` và `frame_confidence`: tường recall/ranking chỉ
  cần GT mức video, mà mức video đáng tin hơn hẳn mức frame

**Chia tune / holdout — đọc kỹ, đây là chỗ dễ đốt nhầm hạn mức:**

| Bộ lọc | Tổng | KIS | Q&A | TRAKE | Dùng cho |
|---|---|---|---|---|---|
| `--part p1 --min-confidence MEDIUM` | 25 | 20 | 4 | 1 | **TUNE — chạy thoải mái** |
| `--part p1 --min-confidence HIGH` | 11 | 9 | 2 | 0 | tập con sạch, kiểm tỉnh táo |
| `--part p2 --min-confidence HIGH` | 30 | 19 | 9 | 2 | **HOLDOUT — 2 lượt cho cả chiến dịch** |

⚠️ **Mọi cổng chặn trước 03/09 chấm trên `p1 --min-confidence MEDIUM`, không phải
trên 41 câu.** 30/41 câu ở mức HIGH nằm trong holdout Đợt 2; chấm bake-off trên
đó là đốt hạn mức ngay ngày đầu.

`MEDIUM` nghĩa là tiên nghiệm ~66% nhãn đúng, tức khoảng 1/3 nhãn sai. Chấp nhận
được vì **cổng K1/K4 là so sánh TƯƠNG ĐỐI** (encoder A với B, có rerank với
không): cùng một tập nhãn nhiễu áp cho mọi nhánh thì nhiễu hạ điểm tuyệt đối
nhưng **giữ nguyên thứ tự thắng thua**. Chỉ đừng đọc con số tuyệt đối từ tập này.

⚠️ **Q&A chỉ có 4 câu ở tập tune.** Quá mỏng để tune một mình — làn Q&A phải ghép
thêm 5 câu Q&A của `dress25` (legacy, chưa xác minh, chỉ dùng so sánh tương đối)
để có 9 câu. Ghi rõ điều này khi báo cáo số Q&A.

Bộ chấm: `dev_set/tools/eval_official.py` — đo **hai tầng tách bạch**, mức video
(không phụ thuộc cửa sổ `[s,e]` chưa biết, là thước chính) và mức frame ở nhiều
dung sai `±5 / ±15 / ±40` cùng lúc. Script **chặn `--part p2`** trừ khi truyền
`--i-am-spending-a-holdout-run`, và tự ghi vào `dev_set/holdout_log.md`.
- Cửa sổ `[s,e]` của BTC vẫn chưa công bố → file chỉ lưu `frame_exact`;
  evaluator phải báo cáo điểm ở nhiều mức dung sai (±5 / ±15 / ±40)
- **Ba câu Đợt 1 đã phân xử lại bằng keyframe thật** vì bài nộp sai:
  `p1-18` → `L26_V389` (không phải `L26_V235`), `p1-17` → `L22_V008` /
  "đèo Tà Pứa" (không phải `L22_V025` / "Đèo Tằng Quái"), `p1-9` → `L21_V003`
- ⚠️ `verified_by` còn ghi "trợ lý — CẦN NGƯỜI KÝ LẠI". Chưa có tên người thật
  thì đây là **development evidence**, chưa phải promotion evidence (R3.V1)

**Đợt 2 đã dùng lại kho Đợt 1** — 54/54 video đáp án của cả hai đợt nằm trong
Batch 1, và `L24_V035` + `L25_V060` xuất hiện ở **cả hai đợt**. Nên giả định làm
việc: Đợt 3 vẫn Batch 1, hoặc Batch 1 cộng thêm L31+. Batch 2 tới 31/08 vẫn
chưa có.

---

### Làn KIS · Công Lý + Minh Hoàng — 19/30 câu

- [ ] **R3.K1 · P0 · [Công Lý] Bake-off encoder trên 5.000 keyframe**
  - Ba nhánh cùng một bộ truy vấn: `ViT-B-32-quickgelu` (nền) ·
    `google/siglip2-so400m-patch16-384` · `facebook/PE-Core-L14-336`.
  - Bỏ `PE-Core-bigG-14-448` dù MERVIN dùng: ~1,9 tỷ tham số ở 448px, encode
    177K ảnh mất 5–10 giờ GPU, không còn đường lùi nếu hỏng.
  - **Xong khi:** có bảng R@1/R@5 **mức video** của cả ba trên
    `eval_official.py --part p1 --min-confidence MEDIUM` (25 câu, 20 KIS).
    **KHÔNG chấm trên p2** — đó là holdout, chỉ có 2 lượt cho cả chiến dịch.
  - **🔒 Cổng 31/08 23:00:** encoder mới phải hơn `B/32` **≥ +0,15 R@5 mức video**.
    Không đạt → **huỷ hẳn K1–K2**, Lý và Hoàng chuyển toàn bộ sang K3–K5 trên
    encoder cũ.

- [ ] **R3.K2 · P0 · [Công Lý] Encode 177.321 keyframe, nạp `keyframes_v2`**
  - 5 tài khoản Kaggle chia theo `hash(video_id) % 5`, checkpoint + resume, tải
    kết quả về ngay sau mỗi lô.
  - **Collection MỚI `keyframes_v2`. Không đụng collection đang chạy** — đó là
    đường lùi cho tối 04/09.
  - **Xong khi:** `.meta.json` đủ trường; kiểm chứng không gian vector **kiểu mới**
    đạt — bất biến cũ ("encode lại ảnh BTC → cosine ≈ 1,0") **chết** khi đổi model
    vì khác không gian. Thay bằng: (a) encode cùng một ảnh hai lần → cosine = 1,0;
    (b) 20 cặp ảnh–caption đã biết đúng → cosine cao rõ rệt so với cặp ngẫu nhiên.

- [ ] **R3.K3 · P1 · [Minh Hoàng] Quét lại fusion trên 7 nhánh**
  - Bỏ bước dịch VI→EN khỏi đường online nếu chọn SigLIP 2 (đa ngữ, hiểu tiếng
    Việt trực tiếp) — bớt một lời gọi LLM, bớt một nguồn sai, bớt độ trễ.
  - `RRF_K = 7` được chọn cho `B/32`; encoder mạnh hơn thì K tối ưu gần như chắc
    chắn đổi. Quét `{3,5,7,10,15,20,30,60}` **trước**, cố định, rồi mới quét
    `BRANCH_WEIGHTS` của hai nhánh mới. Một biến mỗi lần.
  - Giữ **song song hai nhánh vector** (B/32 cũ + mới): cả hai đã encode sẵn, chi
    phí query gần bằng 0, và ensemble hai không gian là cách rerank rẻ nhất có.
  - **Xong khi:** có bảng quét; đo lại độ trễ và đối chiếu ngân sách 30s
    (bất biến 10 — thêm 2 nhánh là thêm 2 truy vấn, phải đo chứ không suy đoán).

- [ ] **R3.K4 · P1 · [Minh Hoàng] Tầng rerank top-50**
  - Đây là nơi 40% điểm nằm và hệ thống hiện **không có tầng nào**: RRF là bước
    xếp hạng cuối cùng.
  - Chấm lại top-50 bằng tín hiệu RRF không dùng được: điểm cosine **thật** đã
    chuẩn hoá theo phân bố của chính truy vấn đó · khớp `extract_constraints()`
    (đã có sẵn, chưa từng dùng để rerank) · đồng thuận nhánh (shot được ≥3/7
    nhánh đề cử đáng tin hơn shot chỉ một nhánh đẩy lên).
  - **🔒 Cổng 02/09:** R@1 **mức video** trên `--part p1 --min-confidence MEDIUM`
    ≥ **0,25**. Không đạt thì **tắt đi** — rerank sai còn tệ hơn không có, vì nó
    đẩy đáp án đúng xuống. **Không chạm p2 hôm nay.**

- [ ] **R3.K5 · P1 · [Công Lý] Chỉnh `SLOT_BUDGET` sâu hơn**
  - Bảng hiện tại `[(1,2),(2,2),(94,1)]` phủ rộng vì ranking kém. Ranking khá lên
    thì cân lại về phía sâu: thử `[(1,8),(4,4),(10,2),(56,1)]`.
  - **Xong khi:** đo ở cả ba giả định cửa sổ ±5 / ±15 / ±40.

### Làn Q&A · Thạch — 9/30 câu

- [ ] **🔒 R3.Q1 · P0 · [Thạch] Sửa H1 — sentinel lọt qua validator**
  - Review 28/08 kết luận `NOT READY — P0/P1 BLOCKER REMAINS` chỉ vì mục này.
  - `"Không đủ căn cứ xác định"` được `is_valid_qa_answer()` nhận là đáp án hợp lệ,
    đi qua validator, vào CSV, vào ZIP; vì không thành `missing_evidence` nên
    `--only`/resume **không tự chạy lại**. Quan sát thật ở
    `dev_set/results/run_20260827_154710_27d970c1/DRESS_QA_01.csv` dòng 3 và 6.
  - Chặn ở **cả hai chỗ**: `is_valid_qa_answer()` và constructor `QAHypothesis`.
  - **Xong khi:** có test dùng **đúng chuỗi đã quan sát**; verdict `NOT READY` gỡ được.

- [ ] **R3.Q2 · P0 · [Thạch] Cổng bằng chứng trước khi gọi LLM**
  - Shot không có OCR, không có ASR trong ±3s, không có metadata thì **không gọi
    LLM**. Đây là chỗ phần lớn trong ~87 lời gọi/câu đang bị đốt.
  - **Xong khi:** số lời gọi mỗi câu xuống ≤ 25.

- [ ] **R3.Q3 · P0 · [Thạch] Dừng sớm khi đã đủ tin**
  - `legacy` hiện không có ngân sách sinh và không dừng khi đã có câu trả lời mạnh.
    Test `test_main_tu_tin_cao_van_thu_het_video_expansion_budget` đang **khoá đúng
    hành vi ngược lại** — sửa cả test.
  - **🔒 Cổng 02/09:** ≤ **60 s/câu**. Không đạt → tối 04/09 **để Q&A làm sau cùng**
    và chấp nhận bỏ nếu hết giờ (9 câu × 6 phút = 54 phút, không được ăn hết buổi thi).

- [ ] **R3.Q4 · P1 · [Thạch] Định tuyến bằng chứng đúng `CLAUDE.md` 5.2**
  - tên/chức danh → OCR · lời nói → ASR · **đếm → detector, TUYỆT ĐỐI không hỏi
    VLM** · số/tỉ số → OCR.
  - **Xong khi:** Q&A ≥ **0,40** trên 9 câu tune — 4 câu Q&A của `p1` cộng 5 câu
    Q&A của `dress25`. ⚠️ Tập mỏng và `dress25` chưa xác minh; chỉ đọc **chênh
    lệch trước/sau**, không đọc con số tuyệt đối. 9 câu Q&A của `p2` là holdout,
    để dành cho quyết định cuối 03/09.

### Làn TRAKE · Thạch — 2/30 câu

- [ ] **R3.T1 · P1 · [Thạch] `to_answers()` phát nhiều phương án mỗi video**
  - Lỗi đã ghi sẵn trong `data/config/slot_budget.py`: 1 dòng/video → 100 dòng =
    100 video, nên khi video đúng đã ở hạng 1 thì 99 dòng còn lại **không thể**
    cải thiện điểm. TR01 đo được R@1..R@100 đều 0,50.
  - 100 dòng nên phủ ~10–20 video × 5–10 phương án chuỗi frame, rút từ top-`K`
    ứng viên mỗi sự kiện của DP.
  - **Xong khi:** R@5..R@100 không còn bằng R@1.

- [ ] **R3.T2 · P1 · [Thạch] Đo lại TRAKE** trên 3 câu TRAKE trong `official_r1r2`,
  có số trước/sau.

### Làn Text · Thạch + Công Lý + Minh Hoàng

> Đây là phần MERVIN (đội *chmod*, **79/88 vòng sơ tuyển AIC HCMC 2025**) có mà
> nhóm chưa có. Lý do độc lập với MERVIN: hệ thống hiện **không có tìm kiếm ngữ
> nghĩa tiếng Việt ở bất kỳ đâu** — 5 nhánh là CLIP (tiếng Anh, qua bản dịch) cộng
> bốn nhánh BM25 khớp từ khoá. Đó là lỗ hổng **năng lực**, không phải chất lượng.
>
> **Mọi job trong làn này phải idempotent theo `video_id`, checkpoint, resume,
> nạp delta** (đúng yêu cầu R3.1). Đó là thứ biến làn này từ "artefact dùng một
> lần" thành "pipeline chạy lại được trong 4–6 giờ" nếu Đợt 3 có batch mới.
>
> **Chạy như script offline sinh parquet, KHÔNG nằm trong vòng lặp `run.py`** —
> để việc đổi provider không lây vào runtime fingerprint của lượt chạy.

- [ ] **🔒 R3.X1 · P1 · [Thạch] Làm sạch 13.415 đoạn ASR bằng `gemini-3.6-flash`**
  - `LLM_BACKEND=gemini` — một dòng config, không sửa code (`CLAUDE.md` mục 3).
    Key **trả phí**, nên không vướng tường 5 request/phút của free-tier.
  - Gom 5 đoạn/lô → 2.683 lời gọi. Ghi ra **cột mới `text_vi_clean`**, không ghi
    đè `text_vi`.
  - **Smoke 100 bản ghi trước khi phóng 2.683.** Cache hiện có 755 entry toàn bộ
    `claude-sonnet-5` — đường Gemini gần như chưa chạy thật ở quy mô nào, và
    review 28/08 liệt "Provider integration test gap" vào backlog. Bài học
    `maxItems` là lỗi tương thích provider chỉ lộ ra ở lần gọi thật.
  - **Bắt đầu SÁNG 31/08** — đường găng dài nhất của làn này; X2/X3/X4 đều đứng sau.
  - **Xong khi:** 13.415/13.415 đoạn có bản sạch, resume được.

- [ ] **R3.X2 · P1 · [Công Lý] Encode nhánh vector tiếng Việt — HAI nhánh**
  - `dangvantuan/vietnamese-embedding` (PhoBERT, 768 chiều, 512 token) —
    **bắt buộc `pyvi.ViTokenizer.tokenize()` trước khi encode.** Bỏ bước này thì
    model vẫn chạy, vector vẫn `norm = 1`, chỉ chất lượng tụt không cảnh báo.
  - `BAAI/bge-m3` — huấn luyện thẳng cho **retrieval**, đa ngữ, context 8192, không
    cần tách từ. Chạy nhánh này vì bảng của MERVIN đo **STS** (đối xứng) chứ không
    đo retrieval (bất đối xứng, truy vấn → tài liệu); dangvantuan đứng đầu STS là
    dấu hiệu, không phải bằng chứng.
  - Chọn bằng đo trên 41 câu GT. **14.198 vector, ~15 phút GPU** nên chạy hai nhánh
    vẫn dưới nửa giờ.
  - ⚠️ Máy hiện không có CUDA (`torch 2.13.0+cpu`) nhưng X2 nhỏ: CPU khoảng 10–20
    phút với dangvantuan, 30–60 phút với bge-m3. **X2 không tranh GPU với K2.**
  - **Xong khi:** hai collection, `.meta.json` đủ, có bảng so sánh.

- [ ] **R3.X3 · P2 · [Công Lý] Tóm tắt cấp video** từ ASR sạch, 783 video,
  `gemini-3.6-flash`, index riêng.
  - ⚠️ **Chốt trần độ dài tóm tắt ≤ 400 token trong prompt.** Transcript trung bình
    2.130 token/video — gấp 4 lần cửa sổ 512 của dangvantuan; không chặn thì nhánh
    này bị cắt cụt âm thầm lúc encode. Ràng buộc biến mất nếu chọn `bge-m3`.
  - Bằng chứng yếu nhất trong bốn mục X: MERVIN dùng nhánh này cho **người lọc**
    trên UI, chưa có bằng chứng nó giúp pipeline chạy tự động.

- [ ] **R3.X4 · P1 · [Minh Hoàng] Nối nhánh 6 và 7 vào `BRANCHES`**
  - **Mặc định `False`** cho tới khi R3.K3 đo xong. Hoàng nối đúng hai nhánh mà
    ngay sau đó chính anh quét ở K3 — cùng một file, không có bàn giao ở giữa.
  - ⚠️ **90/873 video không có ASR.** Hai nhánh mới sẽ mù với những video đó.

### Làn vận hành · Quang Linh

- [ ] **🔒 R3.V1 · P0 · [Linh] Ký tên vào ground truth**
  - Ba phán quyết p1-18 / p1-17 / p1-9 đang ghi `verified_by = "trợ lý — CẦN NGƯỜI
    KÝ LẠI"`. Promotion gate không mở khi thiếu tên người thật.
  - **Xong khi:** `verified_by` + `verified_how` có tên Linh ở ≥ 41 bản ghi.

- [ ] **R3.V2 · P1 · [Linh] Hỏi BTC về mẫu số chấm điểm**
  - **25 file nộp nhưng điểm /13; 30 file nhưng điểm /15.** Tỉ lệ ≈ 2 ở cả hai đợt.
    Nếu BTC chỉ chấm một nửa thì tiên nghiệm 66%/91% trong `official_r1r2` đang áp
    cho một tập con không xác định được, và phép tính mục tiêu cũng đổi theo.
  - **Xong khi:** có câu trả lời, hoặc ghi nhận đã hỏi và không có hồi đáp.

- [ ] **R3.V3 · P1 · [Linh] Diễn tập 10 câu bấm giờ 6 phút/câu** trên UI của nhóm,
  ghi lại chỗ người thao tác kẹt.

### Ba file hai làn cùng chạm — luật tránh đụng

| File | Luật |
|---|---|
| `data/config/search_weights.py` | KIS sở hữu phần trên; **TRAKE sở hữu từ `# --- TRAKE (C3.2)` xuống**. Không ai format lại nửa của người kia |
| `data/config/slot_budget.py` | KIS sở hữu `SLOT_BUDGET` + `SHOT_EDGE_INSET`; **TRAKE sở hữu từ `# ═══ TRAKE — chiều sâu dòng nộp` xuống** |
| `backend/slot/allocator.py` | KIS sở hữu `allocate()`, `_frames_of_shot()`; **TRAKE sở hữu `_allocate_trake()`, `_trake_row()`, `_draw_fresh_row()`** |
| `backend/retrieval/search.py` | **KIS sở hữu độc quyền.** Q&A gọi `search()` nhưng không đổi chữ ký — đổi một dòng ở đây là đổi ngầm 19 câu KIS |

Hai luật vận hành đi kèm:

1. **Thạch giữ quyền phủ quyết schema nhưng không tự sửa.** `CLAUDE.md` mục 13 cho
   Thạch quyền phủ quyết schema; anh đang ở làn Q&A nên schema `keyframes_v2` và
   mọi thay đổi `search()` do Công Lý/Hoàng viết, **Thạch duyệt**. Không sửa tay
   để tránh hai người cùng đụng một file.
2. **Đo riêng trước, đo chung một lần.** Làn Q&A đo trên encoder **hiện tại** (đóng
   băng); làn KIS đo ở mức video. Chỉ 03/09 mới chạy một lượt chung. Trộn sớm là
   lặp lại đúng vấn đề review đã ghi: cùng fingerprint, kết quả khác nhau, không
   quy được cho ai.

### Lịch bốn ngày

| | KIS · Lý + Hoàng | Q&A + TRAKE · Thạch | Text | Vận hành · Linh |
|---|---|---|---|---|
| **31/08 T2** | K1 bake-off 3 nhánh → **chốt encoder tối nay** | Q1 sửa H1 → Q2 cổng bằng chứng | **X1 khởi động sáng nay** (Thạch) | V1 ký GT · V2 hỏi BTC |
| **01/09 T3** | K2 encode 177K → nạp `keyframes_v2` | Q3 dừng sớm, đo latency | X1 xong → X2 (Lý) → X3 (Lý) | V1 xong |
| **02/09 T4** | K3 quét fusion 7 nhánh → K4 rerank | Q4 định tuyến → T1 TRAKE nhiều dòng | X4 nối nhánh (Hoàng) → bàn giao K3 | V3 diễn tập |
| **03/09 T5** | **12:00 FREEZE** · K5 slot · đo lượt cuối | freeze · T2 đo | — | rehearsal ZIP + receipt |
| **04/09 T6** | — | **19:30 THI** | — | — |

**🔒 Quyết định cuối · 03/09 20:00.** Cấu hình mới phải thắng cấu hình cũ trên
holdout Đợt 2. Bằng nhau hoặc thua → **nộp bằng cấu hình cũ**: nó đã rehearsal,
đã có ZIP hợp lệ, và 4,4 điểm chắc chắn hơn một con số chưa ai kiểm.

Holdout Đợt 2 chỉ được mở **hai lần** trong cả chiến dịch: 31/08 (K1) và 03/09
(quyết định cuối). Vi phạm là lặp lại đúng lỗi đã làm hỏng `batch1_holdout13`.

### Ngân sách API

| Hạng mục | Token | Model |
|---|---|---|
| R3.X1 làm sạch ASR | 7.970.637 | `gemini-3.6-flash` · ~$11,7 |
| R3.X3 tóm tắt 783 video | 3.991.684 | `gemini-3.6-flash` · ~$1,0 |
| R3.K1 bake-off + mọi lượt `eval_official.py` | **~6.700/lượt** | `claude-sonnet-5` · **~$0,03/lượt** |
| **Tổng** | **~12.000.000** | **≈ $12,7** |

R3.X2 tốn **0 token API** — chạy embedding local.

Con số 6.700 gồm **6.062 token vào đo thật** bằng `client.messages.count_tokens()`
trên đúng 25 câu tune (242 token/câu), cộng ~625 token ra ước lượng.

Vì sao làn KIS gần như miễn phí token: `search()` chỉ có **một** chỗ gọi `llm()` —
`text_query.translate_to_english()`, prompt 3 dòng, `max_tokens=128`, không JSON
schema. Nó **không** đi qua chuỗi `understand()` 3 lời gọi trong
`query_understanding.py`.

Cả ba nhánh bake-off dùng **chung một cache entry**: khoá cache băm prompt +
model + backend, **không có encoder trong đó**, nên lời gọi dịch không biết ảnh sẽ
được encode bằng gì. Trả tiền đúng một lần cho lượt đầu, ba nhánh sau đó miễn phí.

⚠️ **`search()` hiện LUÔN dịch khi `query_en=None`, không phân biệt encoder.**
Việc `siglip2` đa ngữ bỏ được bước dịch là **kết quả của R3.K3**, chưa đúng ở mã
hiện tại. Trước K3, nhánh SigLIP rẻ vì trúng cache, không phải vì bỏ dịch.

Encode ảnh thì **luôn 0 token** — chạy GPU local, không có LLM nào tham gia.

**Đổi provider cho một job:** biến môi trường của shell **thắng** `.env`
(`_nap_dotenv()` chỉ điền biến còn THIẾU). Nên chạy X1/X3 bằng Gemini là:

```powershell
$env:LLM_BACKEND='gemini'   # LLM_GEMINI_MODEL mặc định gemini-3.6-flash
```

Đặt trong đúng process chạy job đó, **không sửa `.env`** — `.env` phải giữ nguyên
`api`/`claude-sonnet-5` cho đường thi.

⚠️ **Không đổi provider cho đường thi.** `LLM_API_MODEL` nằm trong runtime
fingerprint; đổi backend là vô hiệu toàn bộ checkpoint, cache và mọi artefact đã
đo. Tối 04/09 giữ nguyên `api` + `claude-sonnet-5` như runbook đã khoá.

---

## Luật promotion và thứ tự cắt

> Áp cho mọi chiến dịch, không riêng Đợt 3.

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

> ⚠️ **Mục 1 đã bị ĐẢO cho Đợt 3 (31/08/2026).** Xem
> "Chiến dịch Đợt 3 — bốn làn". Đổi encoder giờ là **ưu tiên cao nhất**, không
> còn là thứ cắt đầu tiên. Lý do: dòng dưới viết khi chưa có số đo; đo được
> `R@1 = 0,0526` và 8/19 câu KIS trượt sạch 100 dòng thì mọi cải tiến khác chỉ
> xếp lại thứ hạng bên trong tập ứng viên mà encoder đã bỏ sót.
>
> Thứ tự cắt còn hiệu lực cho Đợt 3 nằm ở cuối mục chiến dịch: X3 tóm tắt →
> X2 nhánh thứ hai (`bge-m3`) → K5 slot → K4 rerank. **Không cắt** K1–K2 sau khi
> đã qua cổng 31/08.

Cắt từ trên xuống:
1. ~~SigLIP re-encode (dùng CLIP B/32 của BTC)~~ — **đảo, xem trên**
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
