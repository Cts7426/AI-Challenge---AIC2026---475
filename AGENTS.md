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
2. Archive tải về phải có tên, kích thước và SHA-256 trong data manifest.
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
- Giữ `SLOT_BUDGET = [(100, 1)]` tới khi cửa sổ KIS gán nhãn độc lập chứng minh
  chiều sâu tốt hơn chiều rộng.
- Một thử nghiệm = một thay đổi config/code có baseline và query-level diff. Không
  tune trên worktree trộn nhiều thay đổi chưa truy nguồn được.

## Quy trình release ba đợt

1. Ingest/audit dữ liệu mới và so schema/model/map với đợt trước.
2. Chạy test, tune regression và holdout promotion.
3. Tạo clean checkpoint; chạy `preflight --profile release`.
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
| `frame_map` | Đã có và đã audit | `data/derived/frame_map.parquet` | Mọi submit tra map; resolver/test cấm suy hậu tố |
| Submit frame | Đã chốt là frame tuyệt đối | `data/config/submit_format.py` | Format không có logic mapping |
| Fusion | weighted RRF hiện hành | `data/config/search_weights.py` | Ablation từng nguồn, snapshot config |
| Metric vector | L2 + COSINE hiện hành | `load_clip.py`, `clip_model.py` | Norm/cosine verification bắt buộc |
| Model/preprocess CLIP BTC | Chưa có xác nhận đủ mạnh | `data/config/clip_model.py` | Meta guard + encode lại ảnh mẫu trước reindex |
| Cách chấm answer Q&A | Semantic và exact còn mâu thuẫn | `data/config/qa_evaluation.py` | Sinh semantic/exact/robust từ cùng evidence |
| Dữ liệu/lịch đợt 2–3 | Chưa công bố | `docs/contest.md` | Ingest delta → đo → cải tiến → freeze |
| Internet chung kết | Chưa công bố, chưa thuộc sơ tuyển | `LLM_BACKEND` | Adapter API/Gemini/local; không sửa caller |
