# backend/tasks/qa.py — C3.1: Pipeline Q&A (Hỏi & Đáp)
#
# ===== Đường đi =====
#   query VI → parse_question() tách (event, question)
#            → search(event) [KIS pipeline KHÔNG SỬA] → top-K shot ứng viên
#            → route_question(question) → biết cần bằng chứng loại gì
#            → collect_evidence() mỗi shot: OCR ±shot, ASR ±3s, metadata, objects
#            → ask_llm(): text-first, self-consistency n=3, vote
#   → qa_pipeline() trả (mọi shot ứng viên, câu trả lời thắng cuộc)
#
# qa.py CHỈ lo suy luận ra MỘT answer_text tốt nhất — KHÔNG tự xếp 100 dòng nộp.
# Việc đó là của backend.slot.allocate(hits, "QA", answer_text=...), vốn đã có
# sẵn cơ chế xen kẽ + đảm bảo đủ 100 dòng (D3.1, đã test). Lớp gọi (orchestrator)
# nối hai bước lại. Tách vậy để không có 2 bản logic "xếp slot" lệch nhau.
#
# ===== "Text-first" (chốt ở Phase 2 review, đã duyệt) =====
# Ảnh vào VLM tốn token/tiền hơn nhiều lần so với text thuần. Luôn thử OCR +
# ASR + metadata trước; chỉ thêm ảnh khi (a) route bắt buộc ("visual" — câu hỏi
# về màu sắc/hình dáng thuần thị giác) hoặc (b) câu trả lời text-only có
# confidence trung bình dưới LOW_CONFIDENCE.
#
# ===== Self-consistency KHÔNG dùng temperature =====
# backend/llm/adapter.py: model API mới (Opus 5/Sonnet 5/Fable 5) BỎ QUA
# temperature. Đa dạng câu trả lời đến từ n=3 lần sinh độc lập của chính model,
# không phải từ nhiệt độ. Vote bằng backend.common.answer_match — CHUNG với
# logic chấm điểm dev_set, để "2 câu trả lời có giống nhau không" chỉ có MỘT
# định nghĩa trong toàn hệ thống (nếu không, dev_set chấm 1 kiểu, production
# vote 1 kiểu khác, benchmark nội bộ hết còn phản ánh đúng hệ thống thật).
#
# ===== "Đếm → detector, KHÔNG hỏi VLM" (BUILD_TASKS C3.1) =====
# VLM đếm người/vật bằng mắt sai rất thường xuyên khi số lượng > 4-5. Route
# "count" đi thẳng ES objects index (FasterRCNN detections), không đưa ảnh vào
# llm(). GIỚI HẠN ĐÃ BIẾT: objects là detection TỪNG FRAME, không có tracker
# xuyên frame — đếm trên 1 frame đại diện (best_keyframe_id), không phải đếm
# "đúng" theo nghĩa unique object toàn shot. Chấp nhận ở v1, xem thêm
# data/config/qa_routing.py.
#
# ===== Hai cửa tử độc lập (BUILD_TASKS C3.1 nhắc riêng) =====
# frame sai = 0 điểm. answer sai = 0 điểm (docs/contest.md: 3 điều kiện Q&A phải
# đúng CÙNG LÚC). evidence_frame_idx trả về LUÔN được kẹp về một frame_idx CÓ
# THẬT mà pipeline đã thấy (keyframe đại diện shot, hoặc 1 trong các ảnh đã gửi
# VLM) — không bao giờ tin thẳng số VLM tự bịa ra.
#
# Chạy thử (cần Docker ES+Milvus sống, ANTHROPIC_API_KEY hoặc LLM_BACKEND=local):
#   python -m backend.tasks.qa "Tên quán ăn nơi hai người phụ nữ ngồi nói chuyện là gì?"

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from backend.common.answer_match import majority_answer
from backend.indexing.es_client import connect as es_connect
from backend.indexing.frame_map import load_frame_map
from backend.indexing.load_asr import INDEX_NAME as ASR_INDEX
from backend.indexing.load_metadata import INDEX_NAME as METADATA_INDEX
from backend.indexing.load_objects import INDEX_NAME as OBJECTS_INDEX
from backend.indexing.load_ocr import INDEX_NAME as OCR_INDEX
from backend.indexing.milvus_client import COLLECTION_NAME, connect as milvus_connect
from backend.llm.adapter import llm
from backend.retrieval.search import search
from backend.slot import ShotHit, shot_bounds
from data.config.qa_routing import route_question

REPO_ROOT = Path(__file__).resolve().parents[2]
KEYFRAMES_PATH = REPO_ROOT / "data" / "derived" / "keyframes.parquet"
# Ảnh keyframe 1fps (B1.2) nằm dưới thư mục này — env var vì máy dev có thể
# chưa tải ảnh về / để ở ổ khác. Xác nhận bằng cách soi trực tiếp
# aic2026-keyframes.zip: đường dẫn thật là "data/derived/keyframes/<video_id>/
# f<frame_idx>.jpg", còn cột `path` của keyframes.parquet chỉ ghi phần đuôi
# "keyframes/<video_id>/f<...>.jpg" — root phải là data/derived, KHÔNG phải data/.
KEYFRAME_ROOT = Path(os.environ.get("KEYFRAME_ROOT", REPO_ROOT / "data" / "derived"))

N_EVIDENCE_FRAMES = 8          # BUILD_TASKS C3.1: "8 frame + ASR ±3s + OCR..."
QA_ASR_WINDOW_MS = 3000        # ±3s quanh keyframe đại diện shot — KHÁC
                                # ASR_TIME_PAD_MS của search.py (2000ms, dùng để
                                # ASR "đề cử" keyframe ứng viên, việc khác hẳn)
SELF_CONSISTENCY_N = 3
LOW_CONFIDENCE = 0.5           # dưới ngưỡng này (thang [0,1] model tự báo) mới thử thêm ảnh
MAX_SHOTS_TRIED = 3            # thử tối đa bấy nhiêu shot trước khi bỏ cuộc
TOP_K_SHOTS = 5                # BUILD_TASKS C3.1: "top 5 shots" — chỉ để SUY LUẬN

# Số shot lấy về để CẤP SLOT. Tách hẳn khỏi TOP_K_SHOTS vì hai việc khác nhau:
#
#   suy luận  — chỉ cần vài shot tốt nhất, mỗi shot tốn 3-6 lần gọi LLM
#   cấp slot  — càng nhiều shot càng phủ rộng, KHÔNG tốn thêm đồng nào
#
# Bản trước dùng chung TOP_K_SHOTS=5 cho cả hai → `allocate()` chỉ nhận 5 shot và
# `budget_per_shot(5)` chia [22,21,21,18,18]: 22 slot nhồi vào MỘT shot dài trung
# vị 69 frame, trong khi KIS (top_k=100) phủ 31 shot. Shot đúng nằm ngoài top-5 là
# R@20/R@50/R@100 bằng 0 với 95 slot còn lại bỏ không — mà `CLAUDE.md` §6 luật 1
# nói thẳng "bỏ trống ô 51-100 là vứt điểm miễn phí".
TOP_K_SHOTS_FOR_SLOTS = 100
OBJECT_COUNT_MIN_SCORE = 0.5   # ngưỡng score detection tính vào phép đếm


@dataclass(frozen=True)
class QuestionParts:
    event_vi: str
    question_vi: str


@dataclass(frozen=True)
class Evidence:
    shot_id: str
    video_id: str
    ocr_texts: list[str]
    asr_texts: list[str]
    metadata_text: str
    object_count: int | None
    # (frame_idx, đường dẫn ảnh) — chỉ khác rỗng khi needs_images=True VÀ tìm
    # được ít nhất 1 file ảnh thật trên đĩa cho shot này.
    frames: list[tuple[int, Path]]
    best_frame_idx: int | None   # frame của best_keyframe_id — fallback evidence_frame_idx


@dataclass(frozen=True)
class QAResult:
    answer: str
    answer_vi: str
    answer_en: str
    evidence_frame_idx: int
    confidence: float
    evidence_type: str


# ---------------------------------------------------------------- parse + route

PARSE_QUESTION_SCHEMA = {
    "type": "object",
    "properties": {
        "event_vi": {"type": "string"},
        "question_vi": {"type": "string"},
    },
    "required": ["event_vi", "question_vi"],
    "additionalProperties": False,
}


def parse_question(query_vi: str) -> QuestionParts:
    """Tách câu Q&A thành (sự kiện để search, câu hỏi cần trả lời).

    Ví dụ: "Tên quán ăn nơi hai người phụ nữ ngồi nói chuyện" →
      event_vi="hai người phụ nữ ngồi nói chuyện", question_vi="Tên quán ăn là gì?"
    Câu không tách rõ được (hiếm) → cả hai phần dùng nguyên câu gốc, pipeline
    vẫn chạy được chứ không chặn lại.
    """
    raw = llm(
        "Câu sau là một câu hỏi Q&A cho hệ tìm kiếm khoảnh khắc video. Tách thành 2 phần:\n"
        "- event_vi: mô tả SỰ KIỆN/KHOẢNH KHẮC cần tìm (đưa vào công cụ tìm kiếm hình ảnh) — "
        "giữ nguyên chi tiết thị giác gốc, KHÔNG thêm chi tiết mới không có trong câu gốc\n"
        "- question_vi: CÂU HỎI cần trả lời sau khi đã tìm thấy khoảnh khắc đó\n"
        "Câu không tách rõ ràng được thì dùng nguyên câu gốc cho cả hai phần.\n\n"
        f"Câu hỏi: {query_vi}",
        json_schema=PARSE_QUESTION_SCHEMA,
    )
    d = json.loads(raw)
    return QuestionParts(event_vi=d["event_vi"].strip() or query_vi,
                          question_vi=d["question_vi"].strip() or query_vi)


# ---------------------------------------------------------------- thu bằng chứng

@lru_cache(maxsize=1)
def _video_frames() -> dict[str, list[int]]:
    """video_id -> danh sách frame_idx thực sự tồn tại (dựa vào frame_map)"""
    fm = load_frame_map()
    out: dict[str, list[int]] = {}
    for k, v in fm.items():
        # k thường là L26_V257#k0144 hoặc L26_V257_0004809 -> 8 ký tự đầu là video_id
        vid = k[:8]
        out.setdefault(vid, []).append(v)
    for l in out.values():
        l.sort()
    return out


def _evidence_frames(shot_id: str, best_keyframe_id: str | None, n: int) -> list[tuple[int, Path]]:
    """n (frame_idx, path) ảnh THẬT của shot để gửi VLM.

    Ưu tiên frame gần best_keyframe_id nhất (bằng chứng mạnh nhất — đây là nơi
    search() thực sự khớp), phần còn lại rải đều theo frame_idx thực sự CÓ TRONG frame_map
    để có cả chuỗi thời gian trong shot chứ không giả định fps đều.
    """
    from backend.slot.allocator import shot_bounds
    try:
        video_id, start, end = shot_bounds(shot_id)
    except KeyError:
        return []

    all_frames = _video_frames().get(video_id, [])
    # Unique và đã sort
    frames = sorted(list(set(f for f in all_frames if start <= f <= end)))
    
    if not frames:
        return []

    fm = load_frame_map()
    best_frame = fm.get(best_keyframe_id) if best_keyframe_id else None

    # Lấy mẫu đều trên danh sách có thật
    step = max(1, len(frames) // n)
    picked = frames[::step][:n]

    if best_frame is not None and best_frame in frames:
        if best_frame in picked:
            picked.remove(best_frame)
        else:
            picked.pop()
        picked.insert(0, best_frame)

    out: list[tuple[int, Path]] = []
    for f in picked:
        p = KEYFRAME_ROOT / video_id / f"f{f:07d}.jpg"
        if p.exists():
            out.append((f, p))
        else:
            print(f"  [cảnh báo] thiếu file ảnh {p} — bỏ frame {f} khỏi bằng chứng VLM")
    return out


def _keyframe_timestamp_ms(keyframe_id: str) -> int | None:
    rows = milvus_connect().query(
        COLLECTION_NAME, filter=f'keyframe_id == "{keyframe_id}"',
        output_fields=["timestamp_ms"],
    )
    return rows[0].get("timestamp_ms") if rows else None


OCR_PAGE_SIZE = 1000   # số dòng mỗi trang khi quét OCR của một video


def _ocr_for_shot(es, video_id: str, start_frame: int, end_frame: int) -> list[str]:
    """OCR text của mọi keyframe đã OCR nằm trong biên shot.

    Index `ocr` không lưu shot_id/frame_idx (chỉ keyframe_id) — tra frame_idx
    qua frame_map.py (nguồn DUY NHẤT, bất biến 5) rồi lọc trong Python, không
    lọc được thẳng bằng ES query.

    ⚠️ SỬA 16/08 — phải QUÉT HẾT, không cắt ở 500 dòng đầu.

    Bản trước gọi `es.search(..., size=500)` một lần, không `sort`. Video có hơn
    500 keyframe đã OCR (≈ hơn 8 phút ở 1 fps) thì phần dư bị bỏ — và vì không
    sort, thứ tự do Lucene quyết định, nên keyframe của shot đang xét có thể nằm
    ngoài 500 dòng đầu một cách hoàn toàn ngẫu nhiên. Kết quả: `ocr_texts = []`
    cho một shot THẬT SỰ CÓ CHỮ, không exception, không cảnh báo.

    Đây là ca khó lần nhất trong Q&A: `route_question` chọn đúng đường "ocr" cho
    câu hỏi về tên/biển số/tỉ số, rồi đưa xuống bằng chứng rỗng, rồi LLM đoán bừa.

    Dùng `search_after` thay vì `from`/`size`: `from` sâu bị ES chặn ở
    `max_result_window` = 10.000.

    Sắp theo `keyframe_id` (kiểu `keyword`, xem mapping ở
    `backend/indexing/load_ocr.py`) chứ KHÔNG theo `_doc`: `search_after` cần một
    khoá sắp xếp DUY NHẤT và ổn định. `_doc` chỉ ổn định trong một shard và có
    thể đổi khi segment merge giữa chừng — lúc đó trang sau nhảy cóc hoặc lặp,
    và mình lại mất OCR y như bug đang sửa, chỉ khó tái hiện hơn.
    """
    if not es.indices.exists(index=OCR_INDEX):
        return []

    fm = load_frame_map()
    out: list[str] = []
    search_after = None
    while True:
        body = {
            "index": OCR_INDEX,
            "query": {"term": {"video_id": video_id}},
            "size": OCR_PAGE_SIZE,
            "sort": [{"keyframe_id": "asc"}],
        }
        if search_after is not None:
            body["search_after"] = search_after
        hits = es.search(**body)["hits"]["hits"]
        if not hits:
            break
        for h in hits:
            fidx = fm.get(h["_source"]["keyframe_id"])
            if fidx is not None and start_frame <= fidx <= end_frame:
                out.append(h["_source"]["text"])
        if len(hits) < OCR_PAGE_SIZE:
            break
        search_after = hits[-1]["sort"]
    return out


def _asr_for_shot(es, video_id: str, center_ms: int | None) -> list[str]:
    """ASR text trong cửa sổ ±QA_ASR_WINDOW_MS quanh keyframe đại diện shot."""
    if center_ms is None or not es.indices.exists(index=ASR_INDEX):
        return []
    hits = es.search(
        index=ASR_INDEX,
        query={"bool": {"filter": [
            {"term": {"video_id": video_id}},
            {"range": {"start_ms": {"lte": center_ms + QA_ASR_WINDOW_MS}}},
            {"range": {"end_ms": {"gte": center_ms - QA_ASR_WINDOW_MS}}},
        ]}},
        size=20,
    )["hits"]["hits"]
    return [h["_source"]["text"] for h in hits]


def _metadata_for_video(es, video_id: str) -> str:
    try:
        doc = es.get(index=METADATA_INDEX, id=video_id)["_source"]
    except Exception:
        return ""
    parts = [doc.get("title", ""), doc.get("description", "")]
    return " — ".join(p for p in parts if p)


def _object_count(es, keyframe_id: str, label_en: str) -> int | None:
    """Đếm detection nhãn label_en trên MỘT keyframe (không tracker — xem
    giới hạn đã biết ở data/config/qa_routing.py).

    Trả None = KHÔNG ĐẾM ĐƯỢC (chỗ gọi phải lùi về hỏi LLM), khác hẳn 0 = đếm
    được và đúng là không có gì.

    ⚠️ SỬA 16/08 — hai lỗi chồng nhau ở bản trước:

    1. So nhãn bằng `==` chính xác, trong khi `label_en` là danh từ tiếng Anh do
       LLM sinh TỰ DO (`query_understanding.extract_constraints`), không ràng buộc
       vào 600 lớp OpenImages. "people" ≠ "Person", "cars" ≠ "Car" → đếm ra 0.
       Giờ đi qua `resolve_object_labels()` để gộp các nhãn đồng nghĩa.

    2. Không phân biệt "đếm được 0" với "không khớp nhãn nào". Cả hai đều ra 0,
       mà 0 khác None nên `_try_shot` nộp thẳng answer "0" — câu "có bao nhiêu
       người" trả lời "0" và KHÔNG BAO GIỜ hỏi LLM, vì `CLAUDE.md` §5.2 quy định
       "đếm → detector, KHÔNG hỏi VLM" nên đường này được tin tuyệt đối.
       Giờ: keyframe không có detection nào mang nhãn cần đếm → trả None.
    """
    try:
        doc = es.get(index=OBJECTS_INDEX, id=keyframe_id)["_source"]
    except Exception:
        return None

    from data.config.qa_routing import resolve_object_labels

    muc_tieu = {n.lower() for n in resolve_object_labels(label_en)}
    if not muc_tieu:
        return None

    dets = doc.get("detections", [])
    # Có nhãn cần đếm xuất hiện trong ảnh không (BẤT KỂ điểm tin cậy)? Dùng để
    # phân biệt "detector không thấy gì" với "chỉ thấy mờ, dưới ngưỡng".
    co_nhan = any(d.get("label", "").lower() in muc_tieu for d in dets)
    if not co_nhan:
        # Không có detection nào mang nhãn này → detector KHÔNG BIẾT, không phải
        # "có 0 cái". Lùi về LLM thay vì nộp "0".
        return None

    return sum(
        1 for d in dets
        if d.get("label", "").lower() in muc_tieu
        and d.get("score", 0) >= OBJECT_COUNT_MIN_SCORE
    )


def collect_evidence(
    hit: ShotHit, question_vi: str, evidence_type: str, needs_images: bool
) -> Evidence:
    """Gom OCR + ASR + metadata (+ objects nếu đếm, + ảnh nếu cần thị giác)
    của MỘT shot ứng viên."""
    video_id, start, end = shot_bounds(hit.shot_id)
    es = es_connect()
    best_frame = load_frame_map().get(hit.best_keyframe_id) if hit.best_keyframe_id else None
    center_ms = _keyframe_timestamp_ms(hit.best_keyframe_id) if hit.best_keyframe_id else None

    ocr_texts = _ocr_for_shot(es, video_id, start, end)
    asr_texts = _asr_for_shot(es, video_id, center_ms)
    metadata_text = _metadata_for_video(es, video_id)

    object_count = None
    if evidence_type == "count" and hit.best_keyframe_id:
        try:
            from backend.retrieval.query_understanding import extract_constraints
            objs = extract_constraints(question_vi).get("objects") or []
            if objs:
                object_count = _object_count(es, hit.best_keyframe_id, objs[0])
        except Exception as e:
            print(f"  [cảnh báo] trích đối tượng để đếm lỗi, chuyển sang hỏi LLM: {e}")

    frames: list[tuple[int, Path]] = []
    if needs_images:
        frames = _evidence_frames(hit.shot_id, hit.best_keyframe_id, N_EVIDENCE_FRAMES)

    return Evidence(hit.shot_id, video_id, ocr_texts, asr_texts, metadata_text,
                     object_count, frames, best_frame)


# --------------------------------------------------------------------- suy luận

QA_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "answer_vi": {"type": "string"},
        "answer_en": {"type": "string"},
        "evidence_frame_idx": {"type": "integer"},
        "confidence": {"type": "number"},
    },
    "required": ["answer", "answer_vi", "answer_en", "evidence_frame_idx", "confidence"],
    "additionalProperties": False,
}


def _build_prompt(question_vi: str, ev: Evidence) -> str:
    parts = [
        "Bạn đang suy luận để trả lời câu hỏi về MỘT khoảnh khắc trong video. "
        "CHỈ dùng bằng chứng dưới đây, KHÔNG suy đoán ngoài bằng chứng — "
        "không đủ căn cứ thì trả confidence THẤP thay vì bịa câu trả lời.",
        f"\nCâu hỏi: {question_vi}",
    ]
    if ev.metadata_text:
        parts.append(f"\nMetadata video: {ev.metadata_text}")
    if ev.ocr_texts:
        parts.append("\nChữ đọc được trên hình (OCR):\n- " + "\n- ".join(ev.ocr_texts))
    if ev.asr_texts:
        parts.append("\nLời thoại quanh khoảnh khắc (ASR, ±3s):\n- " + "\n- ".join(ev.asr_texts))
    if ev.frames:
        nhan = ", ".join(f"frame_idx={fi}" for fi, _ in ev.frames)
        parts.append(
            f"\nĐính kèm {len(ev.frames)} ảnh khung hình, ĐÚNG THỨ TỰ tương ứng với: {nhan}. "
            "evidence_frame_idx PHẢI là một trong các số này."
        )
    parts.append(
        "\nTrả lời NGẮN NHẤT có thể mà vẫn đủ nghĩa (vd: '5' không phải 'khoảng 5 người'). "
        "answer = câu trả lời (VI hoặc EN đều được), answer_vi/answer_en = bản dịch hai chiều, "
        f"evidence_frame_idx = frame chứa bằng chứng rõ nhất "
        f"(không có ảnh đính kèm thì dùng {ev.best_frame_idx}), confidence trong [0,1]."
    )
    return "\n".join(parts)


def ask_llm(question_vi: str, ev: Evidence) -> list[QAResult]:
    """Gọi llm() self-consistency n=SELF_CONSISTENCY_N, trả list QAResult đã
    kẹp evidence_frame_idx về tập frame CÓ THẬT (không tin thẳng số VLM tự bịa —
    xem "hai cửa tử độc lập" ở đầu file)."""
    images = [str(p) for _, p in ev.frames] or None
    prompt = _build_prompt(question_vi, ev)
    # ⚠️ SỬA 18/08 — adapter.py (DEFAULT_EFFORT) ghi rõ: "Task nào cần nghĩ kỹ
    # (Q&A suy luận) thì tự truyền effort='high'". Đây CHÍNH LÀ bước suy luận
    # đó — mọi lệnh gọi trong qa.py trước bản sửa này đều để mặc định "low"
    # (dịch/mở rộng câu ngắn), tức bước quan trọng nhất của Q&A đang chạy ở
    # effort THẤP NHẤT trên backend "api" (Claude — backend thi thật, xem
    # CLAUDE.md mục 11 "Chưa chốt: internet lúc thi"). Không crash, không lộ ở
    # backend "gemini" (effort không ảnh hưởng gì bên đó) — lỗi im lặng thuần
    # chất lượng câu trả lời, chỉ lộ ra khi đổi ANTHROPIC_API_KEY lúc thi.
    raw = llm(prompt, images=images, json_schema=QA_RESULT_SCHEMA, n=SELF_CONSISTENCY_N,
              effort="high")
    raw_list = raw if isinstance(raw, list) else [raw]

    valid_frames = {fi for fi, _ in ev.frames} or ({ev.best_frame_idx} if ev.best_frame_idx is not None else set())
    fallback_frame = ev.best_frame_idx if ev.best_frame_idx is not None else (
        ev.frames[0][0] if ev.frames else None
    )

    results: list[QAResult] = []
    for r in raw_list:
        try:
            d = json.loads(r)
        except json.JSONDecodeError:
            continue  # llm() đã tự retry JSON hỏng ở tầng dưới; hiếm khi tới đây
        fi = int(d["evidence_frame_idx"])
        if valid_frames and fi not in valid_frames:
            print(f"  [cảnh báo] VLM trả evidence_frame_idx={fi} không nằm trong bằng chứng đã "
                  f"gửi ({sorted(valid_frames)}) — thay bằng {fallback_frame}")
            fi = fallback_frame
        if fi is None:
            continue
        results.append(QAResult(
            answer=d["answer"], answer_vi=d.get("answer_vi", d["answer"]),
            answer_en=d.get("answer_en", d["answer"]), evidence_frame_idx=fi,
            confidence=float(d["confidence"]), evidence_type="",
        ))
    return results


def _try_shot(
    hit: ShotHit, question_vi: str, evidence_type: str, needs_images: bool
) -> tuple[str, int | None] | None:
    """Thử suy luận trên MỘT shot. Trả `(answer, evidence_frame_idx)`, hoặc None
    nếu bằng chứng không đủ để chốt (chỗ gọi thử shot kế tiếp).

    ⚠️ SỬA 16/08 — bản trước chỉ trả `str`, nên `evidence_frame_idx` mà `ask_llm()`
    đã cất công kẹp về tập frame CÓ THẬT (xem "hai cửa tử độc lập" đầu file) bị
    VỨT ĐI ngay tại đây. `reports/C31_C32_C44_TECHNICAL_REPORT.md` §93 khẳng định
    cơ chế kẹp đó bảo vệ cửa frame của Q&A — thực tế nó chưa từng rời khỏi hàm này,
    và frame nộp hoàn toàn do thứ hạng shot của allocator quyết định.
    """
    ev = collect_evidence(hit, question_vi, evidence_type, needs_images)

    if evidence_type == "count":
        # `object_count == 0` KHÔNG còn tới được đây: `_object_count()` trả None khi
        # detector không thấy nhãn nào, thay vì 0. Giữ điều kiện `> 0` làm chốt chặn
        # thứ hai — nộp "0" cho câu "có bao nhiêu…" gần như luôn là dấu hiệu nhãn
        # không khớp, không phải sự thật.
        if ev.object_count is not None and ev.object_count > 0:
            # detector, KHÔNG hỏi VLM (BUILD_TASKS C3.1). Bằng chứng nằm ở đúng
            # keyframe vừa đếm.
            return str(ev.object_count), ev.best_frame_idx
        print(f"  [cảnh báo] shot {hit.shot_id}: không đếm được bằng detector, hỏi LLM (kém tin cậy hơn)")

    results = ask_llm(question_vi, ev)
    if not results:
        return None

    avg_conf = sum(r.confidence for r in results) / len(results)
    if avg_conf < LOW_CONFIDENCE and not ev.frames:
        # Text-only không đủ tự tin → thử lại CÓ ảnh (chiến thuật Text-first đã duyệt)
        ev_img = collect_evidence(hit, question_vi, evidence_type, needs_images=True)
        if ev_img.frames:
            with_images = ask_llm(question_vi, ev_img)
            if with_images:
                results = with_images

    answer, votes = majority_answer([r.answer for r in results])
    if votes == 1 and len(results) > 1:
        return None  # self-consistency không đồng thuận — không đủ tin để chốt ở shot này

    # frame của ĐÚNG lượt sinh đã thắng phiếu, không phải lượt đầu tiên trong list
    frame = next((r.evidence_frame_idx for r in results if r.answer == answer), None)
    if frame is None:
        frame = results[0].evidence_frame_idx
    return answer, frame


# ------------------------------------------------------------------------- API chính

def qa_pipeline(
    query_vi: str,
    top_k_shots: int = TOP_K_SHOTS_FOR_SLOTS,
    query_en: str | None = None,
) -> tuple[list[ShotHit], str]:
    """query VI → (mọi shot ứng viên đã xếp hạng, câu trả lời thắng cuộc).

    Chỗ gọi tự đưa 2 giá trị này vào backend.slot.allocate(hits, "QA",
    answer_text=...) để ra đủ 100 dòng nộp — xem docstring đầu file.

    ⚠️ SỬA 16/08 — hai thay đổi về SỐ SHOT và THỨ TỰ SHOT:

    · `top_k_shots` mặc định thành TOP_K_SHOTS_FOR_SLOTS (100), không còn là
      TOP_K_SHOTS (5). Chỉ MAX_SHOTS_TRIED shot đầu được đem đi suy luận nên chi
      phí LLM không đổi, nhưng allocator có đủ shot để phủ rộng.

    · Shot suy ra được câu trả lời được ĐẨY LÊN HẠNG 1. Bản trước trả nguyên thứ
      tự search, nên khi shot #3 mới cho ra answer thì slot hạng 1 vẫn rơi vào
      shot #1 — chính cái shot pipeline vừa kết luận là không đủ bằng chứng.
      Q&A có hai cửa tử ĐỘC LẬP (frame và answer): ghép answer của shot #3 với
      frame của shot #1 là tự tay phá cửa thứ nhất trong khi cửa thứ hai đã đúng.
    """
    parts = parse_question(query_vi)
    evidence_type, needs_images = route_question(parts.question_vi)

    hits = search(parts.event_vi, query_en=query_en, top_k=top_k_shots, group_by_shot=True)
    if not hits:
        raise RuntimeError(f"search() không trả shot nào cho sự kiện: '{parts.event_vi}'")

    candidate_shots = [
        ShotHit(r["shot_id"], r["score"], r["keyframe_id"])
        for r in hits if r["shot_id"] is not None
    ]
    if not candidate_shots:
        raise RuntimeError(
            "search() có kết quả nhưng không shot nào có shot_id — kiểm tra clip_kf_map.parquet"
        )

    for i, hit in enumerate(candidate_shots[:MAX_SHOTS_TRIED]):
        try:
            ket_qua = _try_shot(hit, parts.question_vi, evidence_type, needs_images)
        except Exception as e:
            print(f"  [cảnh báo] shot {hit.shot_id} lỗi khi suy luận Q&A, thử shot kế tiếp: {e}")
            continue
        if ket_qua is None:
            continue
        answer, _frame = ket_qua
        if i > 0:
            print(f"  shot thắng là hạng {i + 1} ({hit.shot_id}) — đẩy lên hạng 1 để "
                  "frame nộp khớp với shot đã sinh ra câu trả lời")
        return _dua_len_dau(candidate_shots, i), answer

    raise RuntimeError(
        f"Thử {min(MAX_SHOTS_TRIED, len(candidate_shots))} shot đều không suy luận được câu "
        "trả lời đủ tin cậy — kiểm tra bằng chứng (OCR/ASR/metadata) của các shot này có rỗng không."
    )


def _dua_len_dau(shots: list[ShotHit], i: int) -> list[ShotHit]:
    """Đưa phần tử thứ i lên đầu, GIỮ NGUYÊN thứ tự tương đối của phần còn lại.

    Không sửa `score`: allocator tự `sorted(hits, key=score, reverse=True)` nên
    đổi chỗ trong list là chưa đủ — nhưng bịa điểm cho shot thắng thì làm hỏng
    mọi thứ đọc `score` về sau (score_simulator, log phân tích). Thay vào đó gán
    lại điểm shot thắng = điểm cao nhất + một khoảng nhỏ, và ghi rõ trong log.
    """
    if i == 0:
        return shots
    thang = shots[i]
    con_lai = shots[:i] + shots[i + 1:]
    diem_cao_nhat = max(s.score for s in shots)
    # +1e-6: đủ để thắng sorted() mà không làm biến dạng thang điểm RRF (~0.01-0.03)
    return [ShotHit(thang.shot_id, diem_cao_nhat + 1e-6, thang.best_keyframe_id)] + con_lai


def main() -> None:
    ap = argparse.ArgumentParser(description="Pipeline Q&A (C3.1)")
    ap.add_argument("query", help="câu hỏi tiếng Việt")
    ap.add_argument("--top-k-shots", type=int, default=TOP_K_SHOTS)
    args = ap.parse_args()

    hits, answer = qa_pipeline(args.query, top_k_shots=args.top_k_shots)
    print(f'\nCâu hỏi: "{args.query}"')
    print(f"Trả lời: {answer}")
    print(f"\n{len(hits)} shot ứng viên (đưa vào backend.slot.allocate để ra 100 dòng nộp):")
    for i, h in enumerate(hits[:5], 1):
        print(f"  hạng {i}: shot={h.shot_id} score={h.score:.5f} best_kf={h.best_keyframe_id}")

    from backend.llm.adapter import print_usage
    print()
    print_usage()


if __name__ == "__main__":
    main()
