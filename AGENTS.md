# AGENTS.md — HCMAIC 2026 Multimedia Retrieval System

> Quy ước ngôn ngữ: giải thích & comment bằng TIẾNG VIỆT; mọi thứ thành code
> (tên hàm, biến, field, collection, index) bằng TIẾNG ANH.
> Thể thức thi chi tiết (dạng bài, cách chấm, chiến lược): đọc `docs/contest.md`
> KHI làm task đụng submit / kis / qa / trake — đừng dựa vào trí nhớ.

## Dự án

Hệ truy xuất khoảnh khắc video cho AI Challenge HCMC 2026 (thể thức VBS/LSC).
Dự án học tập của SV năm 2 ngành AI — người vận hành lúc thi chính là người viết
code, nên mỗi quyết định kỹ thuật phải kèm giải thích "vì sao".
Sơ tuyển 8/2026 (online, nộp lô, KHÔNG trừ thời gian): Textual KIS, Q&A, TRAKE.
KHÔNG có AVS/KISC ở sơ tuyển — code AVS đã viết thì giữ, ngừng đầu tư.

## Lệnh chạy (từ gốc repo)

```powershell
docker compose up -d                                 # Milvus :19530 + ES :9200 (Milvus cần ~90s)
python data/sample/generate_clip_features.py         # CLIP features giả lập (chạy 1 lần)
python -m backend.indexing.load_metadata             # 5 loader cùng pattern:
python -m backend.indexing.load_objects              #   --recreate nạp lại từ đầu
python -m backend.indexing.load_clip                 #   --search/--find/--similar query thử
python -m backend.indexing.load_ocr
python -m backend.indexing.load_asr
python -m backend.retrieval.search "mô tả" --en "english translation" --top-k 10
python -m uvicorn backend.api.main:app --port 8000   # API + UI: http://localhost:8000
```

- Chưa set `ANTHROPIC_API_KEY` → luôn truyền `--en` / `query_en` (bỏ bước dịch).
- Job OCR/ASR: CHỈ chạy Colab/Kaggle — hướng dẫn ở đầu `preprocessing/*_job.py`.

## Kiến trúc & thư mục

Search engine là nền, agent là lớp mỏng bọc trên — agent GỌI search làm tool,
không viết lại logic tìm kiếm.

```
backend/
├── indexing/    # Tầng 1 — es_client.py + milvus_client.py (điểm kết nối DUY NHẤT)
│                #   load_{metadata,objects,clip,ocr,asr}.py
├── retrieval/   # Tầng 2 — text_query.py (VI→llm()→EN→CLIP), search.py (fusion 5 nguồn)
├── llm/         # adapter.py — llm(prompt)->str, điểm gọi LLM DUY NHẤT
├── agent/       # Tầng 3 — KISC + track tự động (CHUNG KẾT, làm sau)
└── api/         # main.py — /health, /search, /submit + serve frontend/
frontend/        # HTML/JS thuần, không build step, điều hướng 100% bàn phím
preprocessing/   # ocr_job.py, asr_job.py — chạy Colab/Kaggle, resume được
data/config/     # thứ CHƯA chốt, đánh dấu # TODO: BTC (bảng cuối file)
data/sample/     # fixtures test local (gitignore — không push)
docs/contest.md  # thể thức thi chi tiết
```

## Quy ước định danh

- `video_id`: "L01_V001" — trùng tên file .mp4, không đuôi.
- `frame_idx`: số nguyên, CHỈ SỐ FRAME GỐC trong video, đếm từ 0.
  Đây là thứ nộp cho ban tổ chức.
- `shot_id`: "L01_V001#s0042" — video_id + số thứ tự shot, pad 4 chữ số.
- `kf_id` / `keyframe_id`: "L01_V001#k0042" — video_id + btc_kf_ordinal, pad 4 chữ số.
  ĐÂY LÀ KHÓA JOIN XUYÊN SUỐT MỌI BẢNG (Milvus ↔ Elasticsearch ↔ frame_map).
- fps luôn lưu dạng phân số (`fps_num`, `fps_den`). KHÔNG BAO GIỜ làm tròn.
  Video 29.97 fps thực chất là 30000/1001.

## Bất biến — vi phạm gây lỗi IM LẶNG (chạy được nhưng kết quả sai)

1. LLM chỉ gọi qua `llm()` trong `backend/llm/adapter.py`. Không import
   `anthropic` hay SDK nhà cung cấp ở bất kỳ file nào khác.
2. Kết nối DB: ES qua `es_client.connect()`, Milvus qua `milvus_client.connect()`.
   Không gọi `Elasticsearch()` / `MilvusClient()` trực tiếp ở chỗ khác.
3. `keyframe_id` là khóa join Milvus ↔ Elasticsearch ↔ frame_map. Mọi bảng phải có.
   KHÔNG BAO GIỜ dùng số thứ tự file keyframe của BTC (0000.jpg, 0001.jpg)
   làm khóa. Đó là số thứ tự trong thư mục, KHÔNG phải chỉ số frame.
   Nhầm hai thứ này là lỗi im lặng làm toàn bộ điểm số bằng 0.
4. Vector: L2-normalize CẢ HAI PHÍA trước khi index và query; metric Milvus =
   COSINE. Code đụng vector phải kèm phép kiểm chứng chạy được (vd norm ≈ 1.0;
   khi có features BTC: encode lại 1 ảnh, cosine với vector BTC phải ≈ 1.0).
5. `frame_id` nộp bài = frame index TRONG VIDEO (tra frame_map), KHÔNG phải số
   thứ tự file keyframe. Nhầm = 0 điểm dù đúng video.
6. CLIP giới hạn 77 token: mở rộng query = nhiều câu ngắn encode riêng rồi hợp
   nhất, không nối thành đoạn dài. Prompt mở rộng cấm LLM thêm chi tiết không có
   trong query gốc. Không đặt ngưỡng cosine cứng (thực tế chỉ ~0.2–0.3).
7. Job nặng (OCR/ASR/trích frame) phải resume được: JSONL append + flush từng lô,
   đọc file out để skip phần đã xong (Colab/Kaggle tự tắt sau ~9–12h).
8. Model nặng (VLM/whisper/paddle) chỉ chạy offline — không đặt trong đường chạy
   online của /search.
9. Mọi tham số đọc từ `data/config/`. Không hardcode đường dẫn, ngưỡng, tên model.

## Kỷ luật job dài (preprocessing)

Mọi job xử lý dữ liệu phải:
- Chia lô, ghi checkpoint sau mỗi lô
- Đọc `data/manifests/<job>.json` lúc khởi động, bỏ qua phần đã xong
- Chạy lại được sau khi bị ngắt giữa chừng mà không làm lại từ đầu
- Nhận tham số `--shard i --num-shards n` để chia việc.
  + Ingest (tải ZIP): chia theo `int(md5(zip_name).hexdigest(), 16) % num_shards`
  + Job Kaggle (ASR, OCR): chia theo `int(md5(video_id).hexdigest(), 16) % num_shards`
  + Hai kiểu shard này CỐ Ý khác nhau.
- In tiến độ và thời gian còn lại ước tính

## Coding convention

- Đầu file/hàm: comment "vì sao chọn cách này" bằng tiếng Việt, ngắn gọn.
- Loader idempotent: `_id`/PK = khóa tự nhiên (`video_id`, `keyframe_id`) —
  chạy lại không sinh bản ghi trùng; batch 2 của BTC nạp thêm không index lại.
- Text tiếng Việt trong ES: dùng `VI_FOLDED_ANALYSIS` + `searchable_text()` từ
  `es_client.py` — không tự định nghĩa analyzer mới.
- Mỗi nguồn trong search fusion bọc try/except trả rỗng — 1 service chết thì
  search chạy tiếp bằng các nguồn còn lại, không sập.
- Ưu tiên code đọc được hơn code ngắn; mỗi tối ưu phải kiểm chứng/đo được.
- Mỗi hàm xử lý dữ liệu phải có docstring ghi rõ đầu vào, đầu ra, và
  bất biến (invariant) mà nó giữ.

## Ngăn xếp

- **Online (backend/)**: Python 3.14, FastAPI, Milvus, Elasticsearch, open_clip.
  Windows 11, 16GB RAM, torch CPU.
- **Preprocessing**: Python 3.10+, pandas, pyarrow, ffmpeg.
  Chạy trên Colab/Kaggle (GPU). KHÔNG dùng Milvus/ES/Docker cho preprocessing.

## Quy trình làm việc

1. Làm TỪNG task nhỏ theo `BUILD_TASKS.md`, chạy thật + test thật rồi mới sang
   task sau. Xong task: tick checklist, nêu cách chạy/test và task tiếp theo.
2. Trước khi tin kết quả search trên data thật: xác nhận version CLIP với BTC
   (hiện là giả định — xem bảng dưới).

## Môi trường

- Folder làm việc: `C:\dev\aic2026`. Bản OneDrive chỉ là backup — KHÔNG sửa.
- Windows 11, Python 3.14, 16GB RAM. torch bản CPU:
  `pip install torch --index-url https://download.pytorch.org/whl/cpu`
- KHÔNG cài paddlepaddle / paddleocr / faster-whisper local (không có wheel
  cho Py3.14/Windows, và là job GPU). Milvus Lite không chạy trên Windows —
  đổi backend Milvus qua env `MILVUS_URL` (nhận cả đường dẫn `.db` cho Lite).

## Điều CHƯA chốt (# TODO: BTC) — config nào nắm giữ

| Thứ | File | Giả định hiện tại |
|---|---|---|
| Model CLIP + dim | `data/config/clip_model.py` | ViT-B-32-quickgelu / openai / 512 |
| Format submit | `data/config/submit_format.py` | frame_id = hậu tố keyframe_id |
| Trọng số fusion | `data/config/search_weights.py` | vec 1.0 / obj .7 / ocr .6 / asr .6 / meta .4 |
| frame_map (vị trí file) | chưa có — TÌM NGAY khi tải data | CSV map-keyframes: n, pts_time, fps, frame_idx |
| Internet ở chung kết | `backend/llm/adapter.py` (env `LLM_BACKEND`) | api; local = stub NotImplementedError |
