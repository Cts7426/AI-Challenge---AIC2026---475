# AI-First Engineering: AI-Challenge AIC2026

Dự án này được thiết kế theo tư duy **AI-First**. Mọi luật lệ, quy định, và quy trình làm việc đều được "cắm" tại đây để AI (như Claude/Gemini) đọc và hiểu trước khi code.

## 1. Cấu trúc Kiến trúc Hệ thống (`skill/architecture/`)
Cửu Âm Chân Kinh lưu trữ thiết kế của toàn bộ các tầng trong dự án:
- `01-data-pipeline.md`: Luồng dữ liệu, DB Milvus & Elasticsearch.
- `02-retrieval-engine.md`: Động cơ Search, Fusion RRF.
- `03-llm-integration.md`: Adapter kết nối AI (Claude, Gemini, Local).
- `04-evaluation-loop.md`: Cơ chế chấm điểm và bảo vệ Ground truth.

## 2. Các Luật Lệ Viết Code (`skill/rules/`)
- `python-style.md`: Coding convention và cách viết Python.
- `invariants.md`: 9 quy tắc **BẤT BIẾN** - vi phạm là hệ thống hỏng im lặng.
- `api-conventions.md`: Quy chuẩn xây dựng FastAPI.
- `testing-eval.md`: Cách chạy script đánh giá và mô phỏng điểm số.

## 3. Quy trình Quản trị Task (`skill/bmad/`)
- `INDEX.md`: Quy trình quản lý Task (Breakdown -> Make -> Assess -> Deploy).
- `epics/`: Chứa các mục tiêu lớn (VD: Nợ kỹ thuật W0).
- `stories/`: Chứa các file giao việc nhỏ (Given-When-Then).

---
## Hạ tầng Code Tóm Tắt
- `backend/`: API và Logic xử lý (FastAPI).
- `app/`: Các công cụ UI nội bộ (Streamlit).
- `frontend/`: UI thuần tham gia thi đấu.
- `preprocessing/`: Scripts tiền xử lý (Kaggle/Colab).
- `data/`: Cấu hình và dữ liệu mẫu.
- `dev_set/`: Dữ liệu Ground truth và công cụ chấm điểm.
