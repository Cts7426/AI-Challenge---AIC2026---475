# backend/api/main.py — FastAPI: /health (Task 0.2) + POST /search (Task 2.3)
#
# Vì sao có /health riêng? Frontend, docker healthcheck, và chính mình khi debug
# đều cần một cách để hỏi "backend còn dùng được không?".
# ⚠️ SỬA W0.3: /health nay là DEEP CHECK — ping thật ES + Milvus + không gian
# vector + frame_map, trả HTTP 503 nếu có cái nào chết (backend/api/health.py).
# Bản cũ trả `{"status":"ok"}` vẫn xanh khi Milvus rỗng và mọi truy vấn trả rác.
# Đường rẻ (không đụng DB) vẫn còn, nhưng phải hỏi rõ: `/health?quick=1`.
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
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.export import QuerySubmission, write_submissions
from backend.indexing.frame_map import load_frame_map
from backend.retrieval.search import search as fused_search
from data.config.submit_format import Answer

REPO_ROOT = Path(__file__).resolve().parents[2]
# Thư mục ảnh keyframe BTC cấp (chưa có → mount tự tắt, URL trả 404 nhưng
# API vẫn chạy). Đổi chỗ chỉ cần set env, không sửa code (CLAUDE.md mục 7).
KEYFRAMES_DIR = Path(os.environ.get("KEYFRAMES_DIR", str(REPO_ROOT / "data" / "raw" / "btc" / "keyframes")))


_video_paths: dict[str, str] = {}

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
        
    # Xây dựng bảng tra đường dẫn video (xử lý vụ L26 bị chia thành L26a, L26b...)
    try:
        if KEYFRAMES_DIR.is_dir():
            print(f"Đang quét thư mục ảnh: {KEYFRAMES_DIR}")
            for parent_dir in KEYFRAMES_DIR.iterdir():
                if parent_dir.is_dir() and parent_dir.name.startswith("keyframes_"):
                    for video_dir in parent_dir.iterdir():
                        if video_dir.is_dir():
                            _video_paths[video_dir.name] = f"{parent_dir.name}/{video_dir.name}"
            print(f"Đã tìm thấy {len(_video_paths)} thư mục video.")
    except Exception as e:
        print(f"[cảnh báo] Không quét được thư mục ảnh: {e}")
        
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
def health(quick: bool = False):
    """DEEP CHECK (W0.3): ping thật ES + Milvus + không gian vector + frame_map.

    Vì sao không còn trả `{"status": "ok"}`: câu đó chỉ chứng minh tiến trình
    FastAPI còn sống. Nó vẫn xanh khi Milvus rỗng và mọi truy vấn trả rác —
    đúng lúc cần một cái đèn đỏ nhất. Chi tiết từng check ở backend/api/health.py.

    HTTP 503 khi có thành phần CRITICAL chết, để `curl -f` / script khởi động /
    docker healthcheck phát hiện được mà không cần đọc JSON.

    `?quick=1` giữ lại đường LIVENESS rẻ (không đụng DB) cho thứ chỉ cần biết
    tiến trình còn thở — vd frontend polling mỗi vài giây thì không nên kéo theo
    một lượt ping Milvus mỗi lần.

    Khai báo `def` (không `async def`): bên trong là I/O blocking, để FastAPI
    tự đẩy xuống threadpool — cùng lý do với /search.
    """
    if quick:
        return {"status": "ok", "mode": "liveness"}

    from backend.api.health import deep_check

    kq = deep_check()
    return JSONResponse(content=kq, status_code=503 if kq["status"] == "down" else 200)


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Mô tả khoảnh khắc (tiếng Việt)")
    top_k: int = Field(10, ge=1, le=100)
    # Bản dịch EN thủ công — bỏ qua bước llm() dịch. Dùng khi chưa set
    # ANTHROPIC_API_KEY hoặc muốn tự kiểm soát câu đưa vào CLIP.
    query_en: str | None = None
    task_type: Literal["KIS", "QA", "TRAKE"] = "KIS"


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
    # Chỉ TRAKE: vị trí sự kiện (0-based) mà hit này định vị — None ở KIS/QA.
    # Frontend gom các hit CÙNG video_id, sắp theo event_index để hiển thị đủ
    # N khoảnh khắc thay vì 1 ảnh đại diện duy nhất (SỬA 16/08).
    event_index: int | None = None
    # Chỉ TRAKE: vị trí này có bằng chứng thật hay bị nội suy (trake.py
    # ::_fill_missing) — UI cần biết để không hiển thị nội suy như đã "tìm thấy".
    is_interpolated: bool | None = None


class SearchResponse(BaseModel):
    hits: list[SearchHit]
    answer_text: str | None = None

@app.post("/search", response_model=SearchResponse)
def post_search(req: SearchRequest) -> SearchResponse:
    try:
        answer_text = None
        if req.task_type == "QA":
            from backend.slot.allocator import shot_bounds
            from backend.tasks.qa import qa_pipeline

            # ⚠️ SỬA 18/08 — bug NGHIÊM TRỌNG, MỌI truy vấn QA qua /search đều
            # 500: qa_pipeline() trả list[ShotHit] (dataclass 3 trường: shot_id,
            # score, best_keyframe_id — KHÔNG có video_id/frame_idx, KHÔNG
            # subscriptable), trong khi khối dựng `hits` bên dưới (dùng chung
            # cho cả 3 dạng bài) đọc kiểu dict (`r["keyframe_id"]`, `r["video_id"]`).
            # Nhánh TRAKE thêm cùng đợt (638495d) đã tự chuyển sang dict đúng —
            # nhánh QA thì quên, nên bay TypeError chưa từng bị try/except phía
            # trên bắt (khối dựng `hits` nằm NGOÀI try/except) → FastAPI trả
            # thẳng 500 trần trụi, không phải lỗi truy vấn hay lỗi hạ tầng.
            #
            # video_id/frame_idx không có sẵn trong ShotHit — tra qua
            # shot_bounds() (allocator, API công khai) và load_frame_map()
            # (đã lru_cache, tra lại không tốn gì).
            shots, answer_text = qa_pipeline(req.query, top_k_shots=req.top_k, query_en=req.query_en)
            fm = load_frame_map()
            results = []
            for h in shots:
                vid, _s, _e = shot_bounds(h.shot_id)
                results.append({
                    "keyframe_id": h.best_keyframe_id or "",
                    "video_id": vid,
                    "frame_idx": fm.get(h.best_keyframe_id) if h.best_keyframe_id else None,
                    "timestamp_ms": 0,
                    "shot_id": h.shot_id,
                    "score": h.score,
                    "ranks": {"qa": 1},
                })
        elif req.task_type == "TRAKE":
            from backend.tasks.trake import parse_events, trake_search
            events = parse_events(req.query)
            candidates = trake_search(events, top_videos=10)

            # Trả ĐỦ N hit mỗi video (không chỉ 1 ảnh đại diện như bản cũ) —
            # frontend gom theo video_id + event_index để người thao tác thấy
            # đúng chuỗi đã định vị, không phải đoán mò. Vị trí bị nội suy
            # (không có bằng chứng thật) dùng keyframe_id GIẢ (không có trong
            # frame_map) — /submit chấp nhận nhờ SubmitItem.frame_idx tường
            # minh (xem post_submit), KHÔNG tra frame_map cho các vị trí này.
            results = []
            for c in candidates:
                for j, (frame_idx, kf) in enumerate(zip(c.frame_ids, c.keyframe_ids)):
                    results.append({
                        "keyframe_id": kf or f"{c.video_id}#interp{j}",
                        "video_id": c.video_id,
                        "frame_idx": frame_idx,
                        "timestamp_ms": 0,
                        "score": c.score,
                        "ranks": {"trake": 1},
                        "event_index": j,
                        "is_interpolated": kf is None,
                    })
        else:
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

    hits = [
        SearchHit(
            keyframe_id=r["keyframe_id"],
            video_id=r["video_id"],
            frame_idx=r.get("frame_idx"),
            shot_id=r.get("shot_id"),
            ranks=r.get("ranks", {}),
            timestamp_ms=r.get("timestamp_ms", 0),
            score=r["score"],
            event_index=r.get("event_index"),
            is_interpolated=r.get("is_interpolated"),
            thumbnail_url=(
                f"/thumbnails/{_video_paths.get(r['video_id'], f'keyframes_{r['video_id'].split('_')[0]}/{r['video_id']}')}/"
                f"{int(r['keyframe_id'].split('#k')[-1]):03d}.jpg"
                if "#k" in r['keyframe_id'] else f"/thumbnails/{r['video_id']}/{r['keyframe_id']}.jpg"
            ),
        )
        for r in results
    ]
    return SearchResponse(hits=hits, answer_text=answer_text)


class SubmitItem(BaseModel):
    keyframe_id: str
    video_id: str
    timestamp_ms: int | None = None
    # Chỉ cần cho TRAKE khi keyframe_id là vị trí NỘI SUY (trake.py::_fill_missing
    # — không có bằng chứng thật nên không có mặt trong frame_map). Frontend gửi
    # kèm frame_idx đã biết từ /search; KIS/QA/TRAKE-có-bằng-chứng-thật bỏ qua
    # trường này, vẫn tra frame_map như cũ (nguồn sự thật ưu tiên hơn client).
    frame_idx: int | None = None


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

    def to_frame(it: SubmitItem) -> int:
        if it.keyframe_id in frame_map:
            return frame_map[it.keyframe_id]
        # keyframe lạ với frame_map: chỉ TRAKE mới được phép, và CHỈ khi client
        # gửi kèm frame_idx tường minh — đây là ca vị trí bị nội suy (trake.py
        # ::_fill_missing, không có bằng chứng thật nên không thể có trong
        # frame_map). KIS/QA không có lối thoát này — chúng LUÔN phải là bằng
        # chứng thật, id lạ ở đó là lỗi, không phải nội suy hợp lệ.
        if req.task_type == "TRAKE" and it.frame_idx is not None:
            return it.frame_idx
        raise HTTPException(
            status_code=400,
            detail=f"keyframe '{it.keyframe_id}' không có trong frame_map — id lạ hoặc map chưa phủ video này.",
        )

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
        frames = tuple(sorted(to_frame(it) for it in req.items))
        answers = [Answer(video_id=req.items[0].video_id, frame_ids=frames,
                          keyframe_id=req.items[0].keyframe_id)]
    else:
        # KIS/QA: mỗi item là một ứng viên đã xếp hạng, mỗi dòng 1 frame
        answers = [
            Answer(
                video_id=it.video_id,
                frame_ids=(to_frame(it),),
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
