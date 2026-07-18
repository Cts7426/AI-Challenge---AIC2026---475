# backend/api/main.py — FastAPI: /health (Task 0.2) + POST /search (Task 2.3)
#
# Vì sao có /health riêng? Frontend, docker healthcheck, và chính mình khi debug
# đều cần một cách rẻ nhất để hỏi "backend còn sống không?" mà không đụng
# tới Milvus/Elasticsearch.
#
# Vì sao preload CLIP lúc khởi động (lifespan)?
# → Model load mất vài giây. Không preload thì NGƯỜI DÙNG ĐẦU TIÊN gánh độ trễ
#   đó ngay giữa lúc thi. Trả giá lúc khởi động server (lúc rảnh) tốt hơn
#   trả giá lúc bấm search (lúc tính giờ).
#
# Vì sao endpoint /search khai báo bằng `def` thường (không `async def`)?
# → search() bên trong là code blocking (chờ Milvus/ES/encode). Khai báo `def`
#   để FastAPI tự chạy nó trong threadpool — không nghẽn event loop, nhiều
#   request search chạy song song được.
#
# Chạy server (từ thư mục gốc repo):
#     python -m uvicorn backend.api.main:app --port 8000
# Test:
#     curl http://localhost:8000/health
#     curl -X POST http://localhost:8000/search -H "Content-Type: application/json" \
#          -d '{"query": "máy bay ở sân bay", "query_en": "an airplane at the airport", "top_k": 5}'
# Docs tự sinh: http://localhost:8000/docs

import json
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.retrieval.search import search as fused_search
from data.config.submit_format import build_submission

REPO_ROOT = Path(__file__).resolve().parents[2]
# Thư mục ảnh keyframe BTC cấp (chưa có → mount tự tắt, URL trả 404 nhưng
# API vẫn chạy). Đổi chỗ chỉ cần set env, không sửa code (CLAUDE.md mục 7).
KEYFRAMES_DIR = Path(os.environ.get("KEYFRAMES_DIR", str(REPO_ROOT / "data" / "keyframes")))


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        from backend.retrieval.text_query import _get_model
        _get_model()
        print("Đã preload model CLIP — search đầu tiên sẽ không bị chậm.")
    except Exception as e:
        # Thiếu torch/open_clip thì /health và các nguồn ES vẫn phải sống
        print(f"[cảnh báo] Không preload được CLIP (search vector sẽ lỗi): {e}")
    yield


app = FastAPI(
    title="HCMAIC 2026 Retrieval API",
    description="Search engine truy xuất khoảnh khắc video — AI Challenge HCMC 2026",
    lifespan=lifespan,
)

if KEYFRAMES_DIR.is_dir():
    # Ảnh keyframe phục vụ thẳng qua /thumbnails/<video_id>/<keyframe_id>.jpg
    app.mount("/thumbnails", StaticFiles(directory=KEYFRAMES_DIR), name="thumbnails")


@app.get("/health")
def health():
    return {"status": "ok"}


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Mô tả khoảnh khắc (tiếng Việt)")
    top_k: int = Field(10, ge=1, le=100)
    # Bản dịch EN thủ công — bỏ qua bước llm() dịch. Dùng khi chưa set
    # ANTHROPIC_API_KEY hoặc muốn tự kiểm soát câu đưa vào CLIP.
    query_en: str | None = None


class SearchHit(BaseModel):
    keyframe_id: str
    video_id: str
    timestamp_ms: int | None  # None nếu keyframe chưa có trong Milvus
    score: float
    thumbnail_url: str


@app.post("/search", response_model=list[SearchHit])
def post_search(req: SearchRequest) -> list[SearchHit]:
    try:
        results = fused_search(req.query, query_en=req.query_en, top_k=req.top_k)
    except RuntimeError as e:
        # Thiếu API key khi cần dịch — lỗi phía cấu hình người dùng → 400 kèm cách khắc phục
        raise HTTPException(
            status_code=400,
            detail=f"{e} — hoặc gửi kèm 'query_en' để khỏi cần dịch qua LLM.",
        )
    except Exception as e:
        # Milvus/ES chết cả → 503 để frontend phân biệt "hệ thống sập" với "query sai"
        raise HTTPException(status_code=503, detail=f"Search thất bại: {e}")

    return [
        SearchHit(
            keyframe_id=r["keyframe_id"],
            video_id=r["video_id"],
            timestamp_ms=r["timestamp_ms"],
            score=r["score"],
            # Quy ước đường dẫn ảnh: <video_id>/<keyframe_id>.jpg trong KEYFRAMES_DIR.
            # TODO: BTC — chỉnh khi biết cấu trúc thư mục Keyframes thật
            thumbnail_url=f"/thumbnails/{r['video_id']}/{r['keyframe_id']}.jpg",
        )
        for r in results
    ]


class SubmitItem(BaseModel):
    keyframe_id: str
    video_id: str
    timestamp_ms: int | None = None


class SubmitRequest(BaseModel):
    task_type: Literal["KIS", "AVS"]
    items: list[SubmitItem] = Field(..., min_length=1)


@app.post("/submit")
def post_submit(req: SubmitRequest) -> dict:
    """Task 3.2: ghi file submit JSON (format tạm — TODO BTC trong submit_format.py).

    Ràng buộc theo thể thức: KIS nộp ĐÚNG 1 khoảnh khắc; AVS nộp >=1.
    Kiểm ở server chứ không chỉ ở UI — phòng lỗi UI gửi nhầm lúc thi.
    """
    if req.task_type == "KIS" and len(req.items) != 1:
        raise HTTPException(400, detail=f"KIS phải nộp đúng 1 keyframe (đang gửi {len(req.items)}).")

    submission = build_submission(req.task_type, [it.model_dump() for it in req.items])

    out_dir = REPO_ROOT / "submissions"
    out_dir.mkdir(exist_ok=True)
    # Tên file có mốc giờ — không bao giờ ghi đè bài nộp trước (còn truy lại được)
    fname = f"submit_{datetime.now():%Y%m%d_%H%M%S}_{req.task_type}.json"
    path = out_dir / fname
    path.write_text(json.dumps(submission, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"file": f"submissions/{fname}", "submission": submission}


# Frontend (Task 3.1) serve chung server với API — khỏi CORS, khỏi server thứ hai.
# Mount "/" phải nằm CUỐI FILE: Starlette so route theo thứ tự khai báo —
# đặt trước là static nuốt luôn /health, /search. html=True → "/" trả index.html.
FRONTEND_DIR = REPO_ROOT / "frontend"
if (FRONTEND_DIR / "index.html").exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
