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
TOP_K_SHOTS = 5                # BUILD_TASKS C3.1: "top 5 shots"
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
def _keyframes_by_shot() -> dict[str, list[tuple[int, str]]]:
    """shot_id → [(frame_idx, path), ...] keyframe THẬT (có file ảnh trích sẵn)
    của shot, đọc từ keyframes.parquet (B1.2). Cache 1 lần/tiến trình — 371k
    dòng, đọc lại mỗi lần gọi collect_evidence là quá chậm.
    """
    import pandas as pd

    if not KEYFRAMES_PATH.exists():
        return {}
    df = pd.read_parquet(KEYFRAMES_PATH, columns=["shot_id", "frame_idx", "path"])
    out: dict[str, list[tuple[int, str]]] = {}
    for shot_id, frame_idx, path in df.itertuples(index=False):
        out.setdefault(shot_id, []).append((int(frame_idx), path))
    for v in out.values():
        v.sort()
    return out


def _evidence_frames(shot_id: str, best_keyframe_id: str | None, n: int) -> list[tuple[int, Path]]:
    """n (frame_idx, path) ảnh THẬT của shot để gửi VLM.

    Ưu tiên frame gần best_keyframe_id nhất (bằng chứng mạnh nhất — đây là nơi
    search() thực sự khớp), phần còn lại rải đều theo frame_idx để có cả chuỗi
    thời gian trong shot chứ không phải n bản gần như giống hệt nhau.

    Chỉ trả file THỰC SỰ TỒN TẠI trên đĩa: keyframes.parquet có thể ghi đường
    dẫn cho ảnh chưa tải về máy này (dữ liệu tải theo lô) — lỗi ở đây phải LỘ
    RA bằng list rỗng/ngắn hơn n, không phải giả vờ có ảnh rồi gửi rác cho VLM.
    """
    rows = _keyframes_by_shot().get(shot_id, [])
    if not rows:
        return []
    fm = load_frame_map()
    best_frame = fm.get(best_keyframe_id) if best_keyframe_id else None

    order = list(range(len(rows)))
    if best_frame is not None:
        order.sort(key=lambda i: abs(rows[i][0] - best_frame))
        closest = order[0]
        step = max(1, len(rows) // n)
        spread = [i for i in range(0, len(rows), step) if i != closest]
        order = [closest] + spread
    else:
        step = max(1, len(rows) // n)
        order = list(range(0, len(rows), step))

    out: list[tuple[int, Path]] = []
    for i in order:
        if len(out) >= n:
            break
        frame_idx, rel_path = rows[i]
        p = KEYFRAME_ROOT / rel_path
        if p.exists():
            out.append((frame_idx, p))
        else:
            print(f"  [cảnh báo] thiếu file ảnh {p} — bỏ frame {frame_idx} khỏi bằng chứng VLM")
    return out


def _keyframe_timestamp_ms(keyframe_id: str) -> int | None:
    rows = milvus_connect().query(
        COLLECTION_NAME, filter=f'keyframe_id == "{keyframe_id}"',
        output_fields=["timestamp_ms"],
    )
    return rows[0].get("timestamp_ms") if rows else None


def _ocr_for_shot(es, video_id: str, start_frame: int, end_frame: int) -> list[str]:
    """OCR text của mọi keyframe đã OCR nằm trong biên shot.

    Index `ocr` không lưu shot_id/frame_idx (chỉ keyframe_id) — tra frame_idx
    qua frame_map.py (nguồn DUY NHẤT, bất biến 5) rồi lọc trong Python, không
    lọc được thẳng bằng ES query.
    """
    if not es.indices.exists(index=OCR_INDEX):
        return []
    hits = es.search(
        index=OCR_INDEX, query={"term": {"video_id": video_id}}, size=500,
    )["hits"]["hits"]
    fm = load_frame_map()
    out = []
    for h in hits:
        fidx = fm.get(h["_source"]["keyframe_id"])
        if fidx is not None and start_frame <= fidx <= end_frame:
            out.append(h["_source"]["text"])
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
    giới hạn đã biết ở data/config/qa_routing.py)."""
    try:
        doc = es.get(index=OBJECTS_INDEX, id=keyframe_id)["_source"]
    except Exception:
        return None
    dets = doc.get("detections", [])
    return sum(
        1 for d in dets
        if d.get("label", "").lower() == label_en.lower() and d.get("score", 0) >= OBJECT_COUNT_MIN_SCORE
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
    raw = llm(prompt, images=images, json_schema=QA_RESULT_SCHEMA, n=SELF_CONSISTENCY_N)
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


def _try_shot(hit: ShotHit, question_vi: str, evidence_type: str, needs_images: bool) -> str | None:
    """Thử suy luận trên MỘT shot. Trả None nếu bằng chứng không đủ để chốt câu
    trả lời (chỗ gọi thử shot kế tiếp)."""
    ev = collect_evidence(hit, question_vi, evidence_type, needs_images)

    if evidence_type == "count":
        if ev.object_count is not None:
            return str(ev.object_count)  # detector, KHÔNG hỏi VLM (BUILD_TASKS C3.1)
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
    return answer


# ------------------------------------------------------------------------- API chính

def qa_pipeline(query_vi: str, top_k_shots: int = TOP_K_SHOTS, query_en: str | None = None) -> tuple[list[ShotHit], str]:
    """query VI → (mọi shot ứng viên đã xếp hạng, câu trả lời thắng cuộc).

    Chỗ gọi tự đưa 2 giá trị này vào backend.slot.allocate(hits, "QA",
    answer_text=...) để ra đủ 100 dòng nộp — xem docstring đầu file.
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

    for hit in candidate_shots[:MAX_SHOTS_TRIED]:
        try:
            answer = _try_shot(hit, parts.question_vi, evidence_type, needs_images)
        except Exception as e:
            print(f"  [cảnh báo] shot {hit.shot_id} lỗi khi suy luận Q&A, thử shot kế tiếp: {e}")
            continue
        if answer is not None:
            return candidate_shots, answer

    raise RuntimeError(
        f"Thử {min(MAX_SHOTS_TRIED, len(candidate_shots))} shot đều không suy luận được câu "
        "trả lời đủ tin cậy — kiểm tra bằng chứng (OCR/ASR/metadata) của các shot này có rỗng không."
    )


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
