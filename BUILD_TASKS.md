# BUILD_TASKS.md — Lộ trình task

> Dán nội dung lộ trình đầy đủ vào đây. Mỗi lần làm việc, copy 1 task đưa cho Claude Code.

- [x] Task 1: Dựng khung thư mục + docker-compose (Milvus + Elasticsearch standalone)
- [x] Task 0.2: FastAPI tối thiểu với GET /health
- [x] Task 1.1: llm() adapter (backend/llm/adapter.py)
- [x] Task 1.2: nạp Metadata vào Elasticsearch (backend/indexing/load_metadata.py)
- [x] Task 1.3: nạp Objects vào Elasticsearch (backend/indexing/load_objects.py)
- [x] Task 1.4: nạp CLIP features vào Milvus (backend/indexing/load_clip.py)
- [x] Task 2.1: text → CLIP query (backend/retrieval/text_query.py) — version CLIP tạm: ViT-B-32-quickgelu/openai, CHỜ BTC xác nhận
- [x] Task 2.2: search + fusion (backend/retrieval/search.py) — trọng số trong data/config/search_weights.py, CHƯA tune trên data thật
- [x] Task 2.3: endpoint POST /search (backend/api/main.py) — ~0.3s/request; thumbnail_url theo quy ước /thumbnails/<video>/<kf>.jpg, TODO BTC cấu trúc Keyframes thật
- [x] Task 3.1: frontend search + lưới thumbnail + lightbox (frontend/) — serve chung FastAPI tại /, điều hướng 100% bàn phím, placeholder SVG khi chưa có ảnh BTC
- [x] Task 3.2: chọn KIS/AVS + submit (POST /submit → submissions/*.json) — cấu trúc file nộp GIẢ ĐỊNH trong data/config/submit_format.py, TODO BTC
- [x] Task 4.1: OCR (preprocessing/ocr_job.py chạy Colab/Kaggle + backend/indexing/load_ocr.py) — nguồn ocr trong fusion tự bật khi index tồn tại; PaddleOCR CHƯA chạy trên ảnh thật (chờ BTC cấp keyframes)
- [x] Task 4.2: ASR (preprocessing/asr_job.py chạy Colab/Kaggle + backend/indexing/load_asr.py) — fusion join theo thời gian + đề cử keyframe từ đoạn khớp; faster-whisper CHƯA chạy trên video thật (job nặng, chạy cloud)
