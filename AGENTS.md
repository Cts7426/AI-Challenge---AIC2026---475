# AGENTS.md — HCMAIC 2026 Multimedia Retrieval System

> Đây là nguồn hướng dẫn chuẩn cho agent làm việc trong repo. Nếu tài liệu khác
> mâu thuẫn, ưu tiên file này rồi kiểm lại `docs/contest.md` và code/config thật.
> Giải thích và comment bằng TIẾNG VIỆT; tên hàm, biến, field, collection và index
> bằng TIẾNG ANH.

## Bối cảnh hiện tại

- Hệ truy xuất khoảnh khắc video AIC HCMC 2026: Milvus + Elasticsearch + CLIP
  + OCR/ASR + KIS/Q&A/TRAKE + exporter.
- Sơ tuyển có **3 đợt cộng điểm**. Đợt 1 dùng Batch 1; dữ liệu, lịch và thay đổi
  thể lệ đợt 2–3 chưa được BTC công bố chính thức.
- Một người phát triển và vận hành: **Thạch**. Task P0/P1 chạy tuần tự.
- Sơ tuyển online, nộp lô, không trừ thời gian. Không đầu tư AVS/KISC/UI thi đấu
  trước khi qua sơ tuyển; code cũ giữ nguyên nếu không gây lỗi.
- Baseline tune được đóng theo `run_20260820_2349`: 30/30 query không lỗi,
  semantic overall khoảng 0.4817. Tune chỉ là regression set, không phải dự báo
  điểm thi.

## Lệnh vận hành từ gốc repo

```powershell
docker compose up -d
python -m backend.indexing.load_metadata
python -m backend.indexing.load_objects
python -m backend.indexing.load_clip
python -m backend.indexing.load_ocr
python -m backend.indexing.load_asr
python -m backend.retrieval.search "mô tả" --en "english translation" --top-k 10
python -m dev_set.tools.run_evaluation --split tune
python scripts/preflight_check.py --profile development
python scripts/preflight_check.py --profile release
python run.py queries.json --out submissions\round1 --zip --qa-submission-policy robust
python -m uvicorn backend.api.main:app --port 8000
```

- Release Q&A **luôn** truyền `--qa-submission-policy`; không phụ thuộc default.
- Dùng `--qa-submission-policy all --zip` để sinh ba portfolio từ cùng evidence,
  nhưng chỉ nộp một ZIP đã chọn và lưu lại policy.
- Job OCR/ASR chạy Colab/Kaggle, phải resume được; không cài model GPU nặng local.

## Kiến trúc và nguồn sự thật

Search engine là nền; task/agent gọi search, không chép lại retrieval.

```text
backend/indexing/   kết nối duy nhất tới ES/Milvus + loader idempotent
backend/retrieval/  query understanding + năm nguồn + weighted RRF
backend/tasks/      Q&A và TRAKE dùng kết quả retrieval
backend/common/     invariant dùng chung, gồm frame_assets resolver
backend/export/     format/validator/portfolio Q&A; không tự suy frame
data/config/        mọi path, model, metric, weight, policy thay đổi được
data/derived/       parquet/map/cache đã dựng; không phải archive BTC
data/raw/btc/       dữ liệu BTC sau khi tải/giải nén
dev_set/            tune/holdout, scorer và artefact regression
```

### Bốn lớp dữ liệu không được trộn

1. CSV BTC chỉ là **manifest URL**, không chứa video/keyframe.
2. Archive tải về phải có tên, kích thước và SHA-256 trong data manifest. Audit
   vẫn giữ đủ 32 URL, nhưng đợt 1 chỉ bắt buộc 14 keyframe + 4 gói lõi; 14 gói
   video mang trạng thái `deferred_not_required_round1` tới khi có task cần
   pixel video/frame dày đã được đo lường.
3. Raw asset sau giải nén là nguồn ảnh/video BTC; giải nén không được tự sửa
   parquet hay index.
4. Parquet/index là dữ liệu dẫn xuất có provenance; nạp delta idempotent, không
   recreate dữ liệu đợt cũ nếu schema/model vẫn tương thích.

### Hai lớp ảnh

- Raw BTC: ordinal, ví dụ `L21_V001/001.jpg`; ordinal **không phải frame index**.
- Derived: frame tuyệt đối, ví dụ
  `data/derived/keyframes/L21_V001/f0001234.jpg`; chỉ là cache.
- Q&A, API và UI phải gọi
  `backend.common.frame_assets.resolve_frame_path()`. Không tự ghép path ở caller.
- Resolver ưu tiên raw rồi derived. Frame index chỉ nhận từ tham số hoặc
  `frame_map`; cấm cắt hậu tố keyframe tự trích để suy frame.

## Bất biến — vi phạm gây lỗi im lặng

1. LLM chỉ gọi qua `llm()` trong `backend/llm/adapter.py`; không import SDK nhà
   cung cấp ở nơi khác.
2. ES qua `es_client.connect()`, Milvus qua `milvus_client.connect()`; không tạo
   client trực tiếp ở module khác.
3. `keyframe_id` là khóa join Milvus ↔ Elasticsearch ↔ frame map. Mọi bảng/index
   liên quan phải giữ khóa này.
4. `frame_id` nộp = frame index tuyệt đối trong video tra từ `frame_map.parquet`;
   không phải ordinal ảnh BTC. Tầng format chỉ ghi số được cấp, không đoán.
5. Vector index và query đều L2-normalize; metric Milvus hiện hành là **COSINE**.
   Code đụng vector phải kiểm norm ≈ 1.0 và, khi có ảnh/model đúng của BTC, kiểm
   cosine ảnh encode lại với feature BTC.
6. CLIP tối đa 77 token: query expansion là nhiều câu ngắn encode riêng rồi hợp
   nhất; prompt cấm thêm màu, số lượng hoặc chi tiết không có trong query gốc.
7. Weighted RRF đọc từ config, log rank từng nguồn; không đặt ngưỡng cosine cứng.
   Mỗi nguồn retrieval có try/except trả rỗng để một service chết không kéo sập
   toàn query.
8. Job nặng phải checkpoint/resume, append + flush theo lô và skip phần đã xong.
9. VLM/Whisper/Paddle local nặng không nằm trong `/search`; Q&A batch có thể dùng
   LLM/VLM qua adapter và phải lưu cache/evidence để replay.
10. Mọi path/model/weight/policy nằm trong `data/config/`, không hardcode ở caller.
11. Model LLM do người vận hành đặt **thủ công bằng biến môi trường của process**
   ngay trước lệnh chạy. Preflight chỉ in lại backend/model, không tự chọn, không
   gọi thử API và không đổi provider. Một run/resume phải giữ nguyên model trong
   runtime fingerprint để số đo không trộn hai model.

## Quy trình đánh giá và nhận thay đổi

- `tune`: dùng phát triển và phân tích query-level. `holdout`: chỉ dùng promotion.
  Gói thi và receipt lưu read-only theo từng đợt.
- Mọi run/release phải lưu commit, config snapshot, data manifest, scorer policy,
  log, scores và checksum ZIP.
- Sửa correctness/invariant được nhận khi test + regression qua.
- Tuning chỉ được nhận khi tăng ít nhất 0.02 trên tune hoặc cải thiện ít nhất hai
  query holdout, không giảm holdout và không tạo failure mới.
- Q&A replay semantic/exact trên cùng answer/evidence; không so hai lần gọi LLM
  ngẫu nhiên. Khi luật chưa rõ, chọn policy tối đa hóa `min(semantic, exact)`, hòa
  thì chọn semantic cao hơn. Cấu hình vận hành đợt 1 là `robust`.
- Giữ `SLOT_BUDGET = [(1, 2), (2, 2), (94, 1)]` (97 shot/100 dòng) tới khi
  holdout KIS chứng minh chiều sâu tốt hơn chiều rộng. Replay hiện tại cho thấy
  các bảng sâu hơn đều giảm điểm và bỏ đói 0 correct candidate.
- Q&A release giữ `QA_INFERENCE_MODE=legacy` cho tới khi `two_stage` được replay
  trên evidence cố định bằng model release, qua tune + holdout và không sinh
  failure mới.
  Không promotion chỉ dựa vào số request lý thuyết giảm.
- Một thử nghiệm = một thay đổi config/code có baseline và query-level diff. Không
  tune trên worktree trộn nhiều thay đổi chưa truy nguồn được.

## Quy trình release ba đợt

Luật nộp đã khóa: mỗi query đúng một CSV UTF-8 không header, tối đa/định mức vận
hành 100 dòng; tên giữ nguyên stem file TXT; video không `.mp4`; Q&A ≤100 ký tự;
TRAKE mỗi dòng đúng N frame. ZIP phải có top-level `submission/`. Mỗi gói tối đa
3 lượt, lần cuối được tính; file sai format vẫn mất một lượt. Public chỉ dùng 50%
đáp án nên không promotion theo dao động nhỏ trên Public.

1. Ingest/audit dữ liệu mới và so schema/model/map với đợt trước.
2. Chạy test, tune regression và holdout promotion; lưu evidence + runtime fingerprint.
3. Đặt backend/model thủ công, tạo clean checkpoint rồi chạy
   `preflight --profile release`; kiểm bằng mắt model được in ra đúng cấu hình định chạy.
4. Chạy full batch, validator và sinh các portfolio Q&A từ cùng checkpoint.
5. Chọn đúng một ZIP, ghi SHA-256, nộp và lưu receipt.
6. Đóng băng ít nhất 24 giờ cho đợt 2, 48 giờ cho đợt 3 nếu lịch cho phép.
7. Postmortem theo nhóm: `retrieval_miss`, `wrong_frame`, `qa_reasoning`,
   `missing_evidence`, `trake_order`, `format`.

Khi còn dưới 24 giờ: chỉ sửa crash, format, mất dữ liệu, sai mapping hoặc task P0.
Không thêm model/reranker/kiến trúc mới.

## Coding convention

- Đầu file/hàm giải thích ngắn bằng tiếng Việt vì sao chọn cách đó.
- Hàm xử lý dữ liệu có docstring input, output và invariant.
- Loader dùng natural key (`video_id`, `keyframe_id`) và chạy lại không sinh trùng.
- Text Việt trong ES dùng `VI_FOLDED_ANALYSIS` + `searchable_text()`.
- Ưu tiên code đọc được; tối ưu phải có đo lường.
- Không tick task hoàn thành nếu chưa có lệnh kiểm và artefact chứng minh.
- Làm từng task nhỏ theo `BUILD_TASKS.md`; nêu lệnh test và task kế tiếp.

## Môi trường

- Workspace duy nhất: `C:\dev\aic2026`; OneDrive chỉ là backup, không sửa.
- Windows 11, Python 3.14, 16 GB RAM, torch CPU.
- Không cài PaddleOCR/faster-whisper local. Milvus chạy Docker hoặc URL từ config.
- Nếu môi trường thiếu dependency, sửa môi trường/requirements trước; không tuyên
  bố test xanh dựa trên một interpreter khác.

## Trạng thái xác nhận và phòng vệ

| Hạng mục | Trạng thái | Nguồn/cấu hình | Cách phòng vệ |
|---|---|---|---|
| `frame_map` | Đã audit cấu trúc; pixel parity mới 84/873 video | `data/derived/frame_map.parquet`, `reports/data_audit.md` | 177.321 dòng đã kiểm schema/khóa/biên; 789 video chưa đối chiếu pixel, mọi submit vẫn tra map và cấm suy hậu tố |
| Submit frame | Đã chốt là frame tuyệt đối | `data/config/submit_format.py` | Format không có logic mapping |
| Fusion | weighted RRF hiện hành | `data/config/search_weights.py` | Ablation từng nguồn, snapshot config |
| Metric vector | L2 + COSINE hiện hành | `load_clip.py`, `clip_model.py` | Norm/cosine verification bắt buộc |
| Model/preprocess CLIP BTC | Đã kiểm chứng trên ảnh raw BTC | `data/config/clip_model.py`, `scripts/verify_clip_space.py` | 12 mẫu: cosine trung bình 0,9999, nhỏ nhất 0,9993; giữ meta guard trước reindex |
| Cách chấm answer Q&A | Semantic và exact còn mâu thuẫn | `data/config/qa_evaluation.py` | Sinh semantic/exact/robust từ cùng evidence |
| LLM release | Người vận hành chọn thủ công | `LLM_BACKEND`, `LLM_API_MODEL` | Preflight in giá trị; fingerprint cấm resume trộn model |
| Dữ liệu/lịch đợt 2–3 | Chưa công bố | `docs/contest.md` | Ingest delta → đo → cải tiến → freeze |
| Internet chung kết | Chưa công bố, chưa thuộc sơ tuyển | `LLM_BACKEND` | Giữ adapter; không tự đổi provider giữa một run |
