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

import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.export import QuerySubmission, write_submissions
from backend.indexing.frame_map import load_frame_map
from backend.retrieval.search import search as fused_search
from data.config.submit_format import Answer

REPO_ROOT = Path(__file__).resolve().parents[2]
# Thư mục ảnh keyframe BTC cấp (chưa có → mount tự tắt, URL trả 404 nhưng
# API vẫn chạy). Đổi chỗ chỉ cần set env, không sửa code (CLAUDE.md mục 7).
KEYFRAMES_DIR = Path(os.environ.get("KEYFRAMES_DIR", str(REPO_ROOT / "data" / "keyframes")))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Trả giá khởi động lúc rảnh, không bắt người thao tác gánh giữa lúc thi:
    # nạp CLIP ~16s và bảng shot ~1s đều là chi phí MỘT LẦN.
    try:
        from backend.retrieval.text_query import _get_model
        _get_model()
        print("Đã preload model CLIP — search đầu tiên sẽ không bị chậm.")
    except Exception as e:
        # Thiếu torch/open_clip thì /health và các nguồn ES vẫn phải sống
        print(f"[cảnh báo] Không preload được CLIP (search vector sẽ lỗi): {e}")
    try:
        from backend.retrieval.search import _shot_map
        print(f"Đã preload bảng shot: {len(_shot_map())} keyframe.")
    except Exception as e:
        print(f"[cảnh báo] Không preload được bảng shot: {e}")
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
    frame_idx: int | None       # thứ BTC chấm (A1.0a) — None nếu chưa có trong Milvus
    timestamp_ms: int | None
    shot_id: str | None         # cùng shot = cùng cảnh, để UI/TRAKE gom
    score: float                # tổng RRF, KHÔNG so sánh được giữa hai truy vấn khác nhau
    # Thứ hạng của kết quả này ở TỪNG nhánh — bắt buộc phải lộ ra ngoài
    # (CLAUDE.md bất biến 7): câu trượt mà không có số này thì phân tích lỗi
    # thành đoán mò. Nhánh không xếp hạng kết quả này thì vắng mặt trong dict.
    ranks: dict[str, int]
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
            frame_idx=r.get("frame_idx"),
            shot_id=r.get("shot_id"),
            ranks=r.get("ranks", {}),
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
    # 3 dạng bài SƠ TUYỂN (docs/contest.md) — AVS không có ở sơ tuyển, đã bỏ
    task_type: Literal["KIS", "QA", "TRAKE"]
    # Thứ tự items CHÍNH LÀ thứ hạng nộp (phần tử đầu = hạng 1)
    items: list[SubmitItem] = Field(..., min_length=1)
    # Q&A bắt buộc; các dạng khác phải để trống
    answer_text: str | None = None
    # Không truyền → tự sinh theo mốc giờ (đường UI là đường thử tay)
    query_id: str | None = None


@app.post("/submit")
def post_submit(req: SubmitRequest) -> dict:
    """Ghi file nộp qua tầng export (D0.2) — mỗi truy vấn một file.

    Vai trò của endpoint này: DỊCH keyframe_id (UI đang cầm) → frame index thật
    (tra frame_map) rồi đưa xuống export. Tầng format không tra bảng — đó là
    thiết kế chống tái diễn bug W0.2, mapping phải xảy ra Ở ĐÂY, tầng gọi.

    Đường UI này là đường THỬ TAY (vài dòng đã đánh dấu) — nên số câu trả lời
    được phép < 100. Đường nộp thật (batch runner + slot allocator) mới ép đủ 100.
    """
    try:
        frame_map = load_frame_map()
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=f"Chưa có frame_map: {e}")

    def to_frame(kf_id: str) -> int:
        if kf_id not in frame_map:
            raise HTTPException(
                status_code=400,
                detail=f"keyframe '{kf_id}' không có trong frame_map — id lạ hoặc map chưa phủ video này.",
            )
        return frame_map[kf_id]

    if req.task_type == "TRAKE":
        # TRAKE: N khoảnh khắc của CÙNG MỘT video → 1 dòng duy nhất
        videos = {it.video_id for it in req.items}
        if len(videos) > 1:
            raise HTTPException(
                status_code=400,
                detail=f"TRAKE yêu cầu mọi khoảnh khắc cùng 1 video, đang có {sorted(videos)}.",
            )
        if len(req.items) < 2:
            raise HTTPException(status_code=400, detail="TRAKE cần ít nhất 2 khoảnh khắc.")
        # Khoảnh khắc theo thời gian trong video = frame index tăng dần
        frames = tuple(sorted(to_frame(it.keyframe_id) for it in req.items))
        answers = [Answer(video_id=req.items[0].video_id, frame_ids=frames,
                          keyframe_id=req.items[0].keyframe_id)]
    else:
        # KIS/QA: mỗi item là một ứng viên đã xếp hạng, mỗi dòng 1 frame
        answers = [
            Answer(
                video_id=it.video_id,
                frame_ids=(to_frame(it.keyframe_id),),
                answer_text=req.answer_text if req.task_type == "QA" else None,
                keyframe_id=it.keyframe_id,
            )
            for it in req.items
        ]

    query_id = req.query_id or f"ui_{datetime.now():%Y%m%d_%H%M%S}_{req.task_type.lower()}"
    sub = QuerySubmission(query_id=query_id, task_type=req.task_type, answers=tuple(answers))

    try:
        # expect_answers=len(answers): đường thử tay không ép đủ 100 —
        # các luật còn lại (video tồn tại, frame trong biên, TRAKE tăng dần,
        # QA có answer, không trùng) vẫn kiểm đầy đủ, sai là KHÔNG ghi file
        files, file_issues = write_submissions(
            [sub], REPO_ROOT / "submissions", expect_answers=len(answers)
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        # thiếu video_info.parquet — hạ tầng dữ liệu, không phải lỗi người dùng
        raise HTTPException(status_code=503, detail=str(e))

    return {
        "files": [str(p.relative_to(REPO_ROOT)) for p in files],
        "query_id": query_id,
        "n_answers": len(answers),
        "file_issues": [str(i) for i in file_issues],  # rỗng = file sạch (UTF-8, không BOM)
    }


# Frontend (Task 3.1) serve chung server với API — khỏi CORS, khỏi server thứ hai.
# Mount "/" phải nằm CUỐI FILE: Starlette so route theo thứ tự khai báo —
# đặt trước là static nuốt luôn /health, /search. html=True → "/" trả index.html.
FRONTEND_DIR = REPO_ROOT / "frontend"
if (FRONTEND_DIR / "index.html").exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
