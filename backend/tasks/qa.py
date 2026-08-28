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
import hashlib
import json
import math
import os
import threading
import unicodedata
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
from typing import Callable, Iterator

from backend.common.answer_match import majority_answer
from backend.common.frame_assets import resolve_frame_path
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
from data.config.qa_hypotheses import (
    ANSWER_MODES,
    QA_HYPOTHESIS_CACHE_SCHEMA_VERSION,
    QA_INFERENCE_PROMPT_VERSION,
    QA_PLANNER_PROMPT_VERSION,
    QA_ANSWER_MODE_RULES,
    QA_REFUSAL_EVIDENCE_WORDS,
    QA_REFUSAL_MIN_WORDS,
    QA_REFUSAL_NEGATIONS,
    QA_SENTINEL_ANSWERS,
    QA_SENTINEL_PREFIX_CONTINUATIONS,
    QA_WINNER_RANK_PENALTY,
    qa_hypothesis_cache_dir,
    qa_hypothesis_config_snapshot,
)
from data.config.qa_inference import (
    QA_CONFIRM_ADDITIONAL_N,
    QA_CONFIRM_EFFORT,
    QA_CONFIRM_MAX_TOKENS,
    QA_LEGACY_MAX_TOKENS,
    QA_SCREEN_CONFIRM_MIN_CONFIDENCE,
    QA_SCREEN_EFFORT,
    QA_SCREEN_MAX_TOKENS,
    QA_TWO_STAGE_MAX_GENERATIONS,
    qa_inference_mode,
    qa_runtime_config,
)

N_EVIDENCE_FRAMES = 8          # BUILD_TASKS C3.1: "8 frame + ASR ±3s + OCR..."
QA_ASR_WINDOW_MS = 3000        # ±3s quanh keyframe đại diện shot — KHÁC
                                # ASR_TIME_PAD_MS của search.py (2000ms, dùng để
                                # ASR "đề cử" keyframe ứng viên, việc khác hẳn)
SELF_CONSISTENCY_N = 3
LOW_CONFIDENCE = 0.5           # dưới ngưỡng này (thang [0,1] model tự báo) mới thử thêm ảnh
TOP_K_SHOTS = 5                # BUILD_TASKS C3.1: "top 5 shots" — chỉ để SUY LUẬN
# ⚠️ SỬA 20/08 — trước là 3, LỆCH với TOP_K_SHOTS=5 (BUILD_TASKS ghi rõ "top 5
# shots" nhưng code chỉ thử 3). Điều tra QA_004 (holdout đội bạn): shot đúng
# (bằng chứng ASR có sẵn câu trả lời, ask_llm() cho ra đúng 3/3 khi test cô
# lập) nằm ở HẠNG 3 trong search() — nhưng vòng lặp cũ dừng ở shot #1 (video
# sai) ngay khi nó "đủ tự tin" theo ngưỡng cũ, không bao giờ thử tới hạng 3.
# Cùng với đổi "dừng ở kết quả ĐẦU TIÊN" → "thử hết rồi chọn confidence cao
# nhất" bên dưới, đây là cặp sửa trực tiếp cho lỗi QA gần-như-hỏng-hoàn-toàn.
MAX_SHOTS_TRIED = TOP_K_SHOTS
# ⚠️ THÊM 21/08 — điều tra "dress rehearsal" (25 câu tự sinh, chạy qua đúng
# pipeline production): 2/4 câu QA trượt vì search(event_vi) đúng VIDEO nhưng
# SAI SHOT trong video đó — event_vi (mô tả THỊ GIÁC) không đủ đặc trưng để
# phân biệt hai cảnh nấu ăn giống nhau trong CÙNG video, trong khi bằng chứng
# (con số/tên riêng) lại nằm ở một shot KHÁC của đúng video đó. Xem
# `_expand_within_video` — khi vòng chính không ra câu trả lời đủ tin cậy, tìm
# THÊM shot trong TỪNG VIDEO đã xuất hiện, dùng nguyên câu hỏi ĐẦY ĐỦ (còn cả
# từ khoá cụ thể như "giá tàu lá" mà event_vi thuần thị giác không có) — nhánh
# OCR/ASR bắt được từ khoá này dù nhánh vector đã chọn nhầm shot.
VIDEO_EXPAND_SHOTS = 3   # tối đa bấy nhiêu shot MỚI thử thêm mỗi video mở rộng
MAX_VIDEOS_EXPANDED = 3  # tối đa bấy nhiêu video KHÁC NHAU được mở rộng mỗi câu

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
QA_EVIDENCE_SCHEMA_VERSION = 1
_evidence_log_lock = threading.Lock()
_qa_cache_registry_lock = threading.Lock()


class _QACacheFlight:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.users = 0


_qa_cache_flights: dict[str, _QACacheFlight] = {}


@contextmanager
def _qa_cache_single_flight(key: str) -> Iterator[None]:
    """Cùng key chỉ một provider call; entry được xóa khi waiter cuối rời đi."""
    with _qa_cache_registry_lock:
        flight = _qa_cache_flights.get(key)
        if flight is None:
            flight = _QACacheFlight()
            _qa_cache_flights[key] = flight
        flight.users += 1
    try:
        with flight.lock:
            yield
    finally:
        with _qa_cache_registry_lock:
            flight.users -= 1
            if flight.users == 0 and _qa_cache_flights.get(key) is flight:
                del _qa_cache_flights[key]


def _qa_cache_lock_count() -> int:
    """Chỉ phục vụ health test: registry không được tăng vô hạn theo số query."""
    with _qa_cache_registry_lock:
        return len(_qa_cache_flights)


@dataclass(frozen=True)
class QuestionParts:
    event_vi: str
    question_vi: str
    answer_mode: str | None = None
    planner_fallback: bool = False


@dataclass(frozen=True)
class QAHypothesis:
    """Một answer gắn chặt với candidate và evidence đã thực sự sinh ra nó."""

    answer_text: str
    video_id: str
    shot_id: str
    keyframe_id: str
    evidence_frame_idx: int
    confidence: float
    evidence_hash: str
    provenance: str
    evidence_type: str
    answer_mode: str

    def __post_init__(self) -> None:
        if not self.evidence_hash.strip():
            raise ValueError("QAHypothesis phải có evidence_hash")
        if not is_valid_qa_answer(self.answer_text, self.answer_mode):
            raise ValueError("QAHypothesis không được chứa answer rỗng/sentinel")
        if self.answer_mode not in ANSWER_MODES:
            raise ValueError(f"answer_mode không hợp lệ: {self.answer_mode!r}")

    def to_dict(self) -> dict[str, object]:
        return {
            "answer_text": self.answer_text,
            "video_id": self.video_id,
            "shot_id": self.shot_id,
            "keyframe_id": self.keyframe_id,
            "evidence_frame_idx": self.evidence_frame_idx,
            "confidence": self.confidence,
            "evidence_hash": self.evidence_hash,
            "provenance": self.provenance,
            "evidence_type": self.evidence_type,
            "answer_mode": self.answer_mode,
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "QAHypothesis":
        return cls(
            answer_text=str(value["answer_text"]),
            video_id=str(value["video_id"]),
            shot_id=str(value["shot_id"]),
            keyframe_id=str(value["keyframe_id"]),
            evidence_frame_idx=int(value["evidence_frame_idx"]),
            confidence=float(value["confidence"]),
            evidence_hash=str(value["evidence_hash"]),
            provenance=str(value["provenance"]),
            evidence_type=str(value["evidence_type"]),
            answer_mode=str(value["answer_mode"]),
        )


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
    # Chỉ có giá trị khi QA_EVIDENCE_LOG_PATH bật và capture đã ghi bền thành công.
    evidence_hash: str = ""


@dataclass(frozen=True)
class QAResult:
    answer: str
    answer_vi: str
    answer_en: str
    evidence_frame_idx: int
    confidence: float
    evidence_type: str


class QAGenerationBudgetExceeded(RuntimeError):
    """Two-stage đã chạm trần generation của đúng một query."""


class QAEvidenceCaptureError(RuntimeError):
    """Capture đã bật nhưng ảnh/digest/record không thể ghi đủ để replay."""


class QANoValidHypothesisError(RuntimeError):
    """Không candidate nào tạo được answer có evidence hợp lệ; caller nên retry."""


@dataclass
class QAGenerationBudget:
    """Bộ đếm logic n của screen/confirm; legacy không tạo bộ đếm này."""

    limit: int
    used: int = 0

    def reserve(self, n: int, stage: str) -> None:
        if n < 1:
            raise ValueError("n generation phải dương")
        if self.used + n > self.limit:
            raise QAGenerationBudgetExceeded(
                f"Q&A two-stage đã dùng {self.used}/{self.limit} generation; "
                f"không đủ chỗ cho {stage} n={n}"
            )
        self.used += n


_generation_budget_ctx: ContextVar[QAGenerationBudget | None] = ContextVar(
    "qa_generation_budget", default=None,
)
_qa_mode_ctx: ContextVar[str | None] = ContextVar("qa_inference_mode", default=None)
_qa_attempt_ctx: ContextVar[dict[str, object] | None] = ContextVar(
    "qa_attempt", default=None,
)
_qa_runtime_fingerprint_ctx: ContextVar[str] = ContextVar(
    "qa_runtime_fingerprint", default="<unset>",
)
_qa_full_query_hash_ctx: ContextVar[str] = ContextVar(
    "qa_full_query_sha256", default="",
)


def _current_qa_mode() -> str:
    """Đóng băng mode trong một query, nhưng resolve runtime cho caller trực tiếp."""
    return _qa_mode_ctx.get() or qa_inference_mode()


@contextmanager
def qa_generation_budget(
    limit: int = QA_TWO_STAGE_MAX_GENERATIONS,
) -> Iterator[QAGenerationBudget]:
    """Context test/runner dùng để áp trần generation cho đúng một query."""
    budget = QAGenerationBudget(limit=limit)
    token = _generation_budget_ctx.set(budget)
    try:
        yield budget
    finally:
        _generation_budget_ctx.reset(token)


# ---------------------------------------------------------------- parse + route

PARSE_QUESTION_SCHEMA = {
    "type": "object",
    "properties": {
        "event_vi": {"type": "string"},
        "question_vi": {"type": "string"},
        "answer_mode": {"type": "string", "enum": list(ANSWER_MODES)},
    },
    "required": ["event_vi", "question_vi", "answer_mode"],
    "additionalProperties": False,
}


def _build_planner_prompt(query_vi: str) -> str:
    return (
        f"Prompt version: {QA_PLANNER_PROMPT_VERSION}\n"
        "Câu sau là một câu hỏi Q&A cho hệ tìm kiếm khoảnh khắc video. "
        "Tách thành 3 phần:\n"
        "- event_vi: mô tả SỰ KIỆN/KHOẢNH KHẮC cần tìm (đưa vào công cụ "
        "tìm kiếm hình ảnh) — giữ nguyên chi tiết thị giác gốc, KHÔNG "
        "thêm chi tiết mới không có trong câu gốc\n"
        "- question_vi: CÂU HỎI cần trả lời sau khi đã tìm thấy khoảnh khắc đó\n"
        "- answer_mode: đúng một trong visual_count, visual_read, ocr, asr, "
        "metadata, visual_attribute\n"
        "Câu không tách rõ ràng được thì dùng nguyên câu gốc cho cả hai phần.\n\n"
        f"Câu hỏi: {query_vi}"
    )


def parse_question(query_vi: str) -> QuestionParts:
    """Tách câu Q&A thành (sự kiện để search, câu hỏi cần trả lời).

    Ví dụ: "Tên quán ăn nơi hai người phụ nữ ngồi nói chuyện" →
      event_vi="hai người phụ nữ ngồi nói chuyện", question_vi="Tên quán ăn là gì?"
    Câu không tách rõ được (hiếm) → cả hai phần dùng nguyên câu gốc, pipeline
    vẫn chạy được chứ không chặn lại.
    """
    try:
        fingerprint = _qa_runtime_fingerprint_ctx.get()
        planner_identity = _planner_cache_identity(query_vi, fingerprint)
        planner_key = _qa_cache_key(planner_identity)
        if fingerprint != "<unset>":
            raw = _qa_cached_outputs(
                planner_key,
                planner_identity,
                lambda: [llm(
                _build_planner_prompt(query_vi),
                json_schema=PARSE_QUESTION_SCHEMA,
                max_tokens=384,
                )],
            )[0]
        else:
            raw = llm(
                _build_planner_prompt(query_vi),
                json_schema=PARSE_QUESTION_SCHEMA,
                max_tokens=384,
            )
        d = json.loads(raw)
        event_vi = str(d["event_vi"]).strip()
        question_vi = str(d["question_vi"]).strip()
        answer_mode = str(d["answer_mode"]).strip()
        if answer_mode not in ANSWER_MODES:
            raise ValueError(f"answer_mode không hợp lệ: {answer_mode!r}")
        return QuestionParts(
            event_vi=event_vi or query_vi,
            question_vi=question_vi or query_vi,
            answer_mode=answer_mode,
        )
    except QAEvidenceCaptureError:
        raise
    except Exception as error:
        # Planner là nhánh hỗ trợ. Lỗi mạng/JSON/schema phải quay về đúng route
        # rule-based hiện hành, không làm mất cả query.
        evidence_type, _ = route_question(query_vi)
        answer_mode = _answer_mode_for_evidence_type(evidence_type)
        print(f"  [cảnh báo] Q&A planner lỗi, dùng rule fallback: {error}")
        return QuestionParts(query_vi, query_vi, answer_mode, planner_fallback=True)


def _answer_mode_for_evidence_type(evidence_type: str) -> str:
    """Map route legacy sang enum planner mà không thay hành vi evidence hiện có."""
    return {
        "count": "visual_count",
        "ocr": "ocr",
        "asr": "asr",
        "metadata": "metadata",
        "visual": "visual_attribute",
        "text_first": "visual_read",
    }.get(evidence_type, "visual_read")


def _route_for_answer_mode(answer_mode: str) -> tuple[str, bool]:
    """Structured mode quyết định route; rule legacy chỉ dùng khi planner fallback."""
    routes = {
        "visual_count": ("count", False),
        "visual_read": ("visual", True),
        "ocr": ("ocr", False),
        "asr": ("asr", False),
        "metadata": ("metadata", False),
        "visual_attribute": ("visual", True),
    }
    try:
        return routes[answer_mode]
    except KeyError:
        raise ValueError(f"answer_mode không hợp lệ: {answer_mode!r}") from None


def _normalize_answer(answer_text: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(answer_text))
    normalized = " ".join(normalized.casefold().split())
    while normalized and unicodedata.category(normalized[0]).startswith("P"):
        normalized = normalized[1:].lstrip()
    while normalized and unicodedata.category(normalized[-1]).startswith("P"):
        normalized = normalized[:-1].rstrip()
    return normalized


def _dap_an_cho_trong(answer_mode: str | None) -> str:
    """Đáp án chỗ trống, đủ hợp lệ để nộp nhưng nhìn là biết phải điền tay.

    Phải qua được chính `is_valid_qa_answer` (câu đếm đòi chữ số) nếu không
    `build_qa_hypothesis` sẽ trả None và ta lại rơi vào cảnh không nộp gì.

    Không dùng "?" — `_normalize_answer` bỏ dấu câu nên nó thành chuỗi rỗng và
    bị chính bộ lọc loại. "TODO" sống qua chuẩn hoá và đập vào mắt lúc soi.
    """
    rule = QA_ANSWER_MODE_RULES.get(answer_mode or "")
    return "0" if rule and rule.get("digit") else "TODO"


def _diem_co_phat_hang(confidence: float, rank_index: int) -> float:
    """Confidence trừ phạt theo ĐỘ SÂU của shot trong bảng retrieval.

    Vì sao cần: Q&A có hai cửa tử độc lập — sai video là 0 tuyệt đối dù answer
    đúng. Đo 28/08: winner của p1-3 là shot hạng 104, p1-15 là hạng 105, chọn
    thuần theo confidence tự khai. Mà confidence lại bị ĐẢO NGƯỢC: câu từ chối
    "không thấy cân" được 0.60 (khẳng định không thấy gì là quan sát dễ) trong
    khi đọc số mờ thật thì model chỉ dám 0.30. Kết quả là câu từ chối ở đáy
    bảng luôn thắng câu trả lời thật ở đầu bảng.

    Phạt log10 để đầu bảng gần như không bị đụng: hạng 1 -> 0 · hạng 10 -> -0,15
    · hạng 100 -> -0,30. Shot sâu vẫn thắng được, nhưng phải hơn hẳn.
    """
    return confidence - QA_WINNER_RANK_PENALTY * math.log10(1 + max(0, rank_index))


def _la_cau_tu_choi(normalized: str) -> bool:
    """Dò HÌNH DẠNG câu từ chối: phủ định + từ nói về việc thiếu bằng chứng.

    Vì sao không liệt kê chuỗi: danh sách là ĐÓNG còn LLM đẻ biến thể vô hạn.
    Đo 28/08 trên đề đợt 1, danh sách 6 chuỗi chỉ bắt 1/5 câu từ chối thật.

    Chỉ dò khi >= QA_REFUSAL_MIN_WORDS từ — "Không" (câu có/không) và "0"
    (câu đếm) là đáp án THẬT, không được loại.
    """
    tokens = normalized.split()
    if len(tokens) < QA_REFUSAL_MIN_WORDS:
        return False
    if not any(t in QA_REFUSAL_NEGATIONS for t in tokens):
        return False
    # Từ bằng chứng có thể gồm hai tiếng ("xác định") nên dò trên cả chuỗi.
    return any(w in normalized for w in QA_REFUSAL_EVIDENCE_WORDS)


def _dung_kieu_dap_an(normalized: str, answer_mode: str | None) -> bool:
    """Đáp án phải đúng DẠNG câu hỏi đòi (câu đếm phải có chữ số, v.v.).

    Đo 28/08: p1-17 hỏi tên con đèo, hạng 1 là "Chồn Hương" còn "Đèo Bạch Mã"
    nằm hạng 2 — hai bên hoà confidence 0.62 mà không có gì phá hoà theo kiểu.
    """
    rule = QA_ANSWER_MODE_RULES.get(answer_mode or "")
    if not rule:
        return True
    if rule.get("digit") and not any(c.isdigit() for c in normalized):
        return False
    max_words = rule.get("max_words")
    if isinstance(max_words, int) and len(normalized.split()) > max_words:
        return False
    return True


def is_valid_qa_answer(answer_text: str | None, answer_mode: str | None = None) -> bool:
    """Từ chối answer rỗng/sentinel trước khi nó trở thành hypothesis/CSV.

    `answer_mode` không bắt buộc để mọi caller cũ gọi được như trước; truyền vào
    thì thêm cổng kiểm kiểu.
    """
    if answer_text is None:
        return False
    normalized = _normalize_answer(answer_text)
    if not normalized or normalized in QA_SENTINEL_ANSWERS:
        return False
    for prefix in QA_SENTINEL_ANSWERS:
        marker = prefix + " "
        if not normalized.startswith(marker):
            continue
        suffix = normalized[len(marker):]
        first_token = suffix.split(" ", 1)[0]
        first_token = _normalize_answer(first_token)
        if first_token in QA_SENTINEL_PREFIX_CONTINUATIONS:
            return False
    if _la_cau_tu_choi(normalized):
        return False
    return _dung_kieu_dap_an(normalized, answer_mode)


def build_qa_hypothesis(
    hit: ShotHit,
    *,
    answer_text: str,
    evidence_frame_idx: int,
    confidence: float,
    evidence_hash: str,
    provenance: str,
    answer_mode: str,
    evidence_type: str,
) -> QAHypothesis | None:
    """Pin answer vào keyframe/frame_map thật; sentinel không được tạo object."""
    if not is_valid_qa_answer(answer_text, answer_mode):
        return None
    if not evidence_hash.strip():
        raise QANoValidHypothesisError("Q&A hypothesis thiếu evidence_hash")
    if answer_mode not in ANSWER_MODES:
        raise ValueError(f"answer_mode không hợp lệ: {answer_mode!r}")
    video_id = hit.shot_id.split("#", 1)[0]
    keyframe_id = _keyframe_id_for_frame(
        video_id,
        int(evidence_frame_idx),
        preferred=hit.best_keyframe_id,
    )
    mapped_frame = load_frame_map().get(keyframe_id)
    if mapped_frame != int(evidence_frame_idx):
        raise QANoValidHypothesisError(
            f"hypothesis pin sai frame: {keyframe_id!r}->{mapped_frame}, "
            f"evidence={evidence_frame_idx}"
        )
    return QAHypothesis(
        answer_text=str(answer_text).strip(),
        video_id=video_id,
        shot_id=hit.shot_id,
        keyframe_id=keyframe_id,
        evidence_frame_idx=int(evidence_frame_idx),
        confidence=float(confidence),
        evidence_hash=evidence_hash,
        provenance=provenance,
        evidence_type=evidence_type,
        answer_mode=answer_mode,
    )


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
        resolution = resolve_frame_path(video_id, frame_idx=f)
        if resolution.path is not None:
            out.append((f, resolution.path))
            if resolution.warning:
                print(f"  [cảnh báo] {resolution.warning}")
        else:
            print(
                f"  [cảnh báo] không tìm được ảnh {video_id}/frame {f}: "
                f"{resolution.reason} — bỏ khỏi bằng chứng VLM"
            )
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

    ev = Evidence(hit.shot_id, video_id, ocr_texts, asr_texts, metadata_text,
                  object_count, frames, best_frame)
    evidence_hash = capture_evidence(hit, question_vi, evidence_type, needs_images, ev)
    return replace(ev, evidence_hash=evidence_hash)


def _sha256_file(path: Path) -> str:
    """Hash streaming; lỗi đọc ảnh là lỗi capture, không được ghi digest rỗng."""
    digest = hashlib.sha256()
    try:
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                digest.update(chunk)
    except (OSError, AttributeError) as e:
        raise QAEvidenceCaptureError(f"không đọc được ảnh evidence {path}: {e}") from e
    return digest.hexdigest()


def _stable_evidence_payload(record: dict[str, object]) -> dict[str, object]:
    """Phần hash không chứa run/query/score/path tuyệt đối hay metadata attempt."""
    frames = record.get("frames") or []
    return {
        "schema_version": QA_EVIDENCE_SCHEMA_VERSION,
        "question_vi": record.get("question_vi", ""),
        "shot_id": record.get("shot_id", ""),
        "video_id": record.get("video_id", ""),
        "best_keyframe_id": record.get("best_keyframe_id"),
        "evidence_type": record.get("evidence_type", ""),
        "needs_images": bool(record.get("needs_images", False)),
        "ocr_texts": record.get("ocr_texts") or [],
        "asr_texts": record.get("asr_texts") or [],
        "metadata_text": record.get("metadata_text", ""),
        "object_count": record.get("object_count"),
        "best_frame_idx": record.get("best_frame_idx"),
        "frames": [
            {"frame_idx": row.get("frame_idx"), "sha256": row.get("sha256", "")}
            for row in frames
        ],
    }


def _hash_json(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _append_capture_record(record: dict[str, object]) -> None:
    """Append + flush + fsync; capture bật mà ghi lỗi thì fail closed."""
    raw_path = os.environ.get("QA_EVIDENCE_LOG_PATH", "").strip()
    if not raw_path:
        return
    path = Path(raw_path)
    try:
        with _evidence_log_lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
    except OSError as e:
        raise QAEvidenceCaptureError(
            f"không ghi bền được QA evidence capture {path}: {e}"
        ) from e


def capture_evidence(hit: ShotHit, question_vi: str, evidence_type: str,
                     needs_images: bool, ev: Evidence) -> str:
    """Tính hash evidence ổn định và ghi record nếu capture được bật.

    Hash luôn tồn tại để hypothesis/cache không mất provenance ở development.
    Promotion runner bật `QA_EVIDENCE_LOG_PATH`; khi đó thiếu ảnh/digest/ghi file
    vẫn ném lỗi thay vì tạo artefact trông hợp lệ nhưng không replay được.
    """
    frame_rows = [
        {"frame_idx": int(frame_idx), "path": str(path), "sha256": _sha256_file(path)}
        for frame_idx, path in ev.frames
    ]
    attempt = _qa_attempt_ctx.get() or {"origin": "direct", "order": 0}
    record: dict[str, object] = {
        "schema_version": QA_EVIDENCE_SCHEMA_VERSION,
        "record_type": "evidence",
        "run_id": os.environ.get("LLM_RUN_ID", ""),
        "query_id": os.environ.get("LLM_QUERY_ID", ""),
        "attempt": {
            "origin": str(attempt.get("origin", "direct")),
            "order": int(attempt.get("order", 0)),
            "stage": "image" if ev.frames else "text",
            "mode": _current_qa_mode(),
        },
        "question_vi": question_vi,
        "shot_id": ev.shot_id,
        "video_id": ev.video_id,
        "shot_score": float(hit.score),
        "best_keyframe_id": hit.best_keyframe_id,
        "evidence_type": evidence_type,
        "needs_images": bool(needs_images),
        "ocr_texts": list(ev.ocr_texts),
        "asr_texts": list(ev.asr_texts),
        "metadata_text": ev.metadata_text,
        "object_count": ev.object_count,
        "best_frame_idx": ev.best_frame_idx,
        "frames": frame_rows,
    }
    evidence_hash = _hash_json(_stable_evidence_payload(record))
    record["evidence_hash"] = evidence_hash
    _append_capture_record(record)
    if isinstance(attempt, dict):
        # Context thuộc riêng query hiện tại; pipeline đọc lại sau `_try_shot`
        # để gắn hypothesis đúng evidence cuối (text hoặc image escalation).
        attempt["evidence_hash"] = evidence_hash
        attempt["evidence_type"] = evidence_type
        attempt["evidence_stage"] = "image" if ev.frames else "text"
    return evidence_hash


def _capture_inference_output(
    ev: Evidence,
    *,
    usage_tag: str,
    effort: str,
    max_tokens: int,
    requested_n: int,
    raw_count: int,
    results: list[QAResult],
) -> None:
    """Ghi knobs + mọi output đã parse để frozen evidence có thể replay vote."""
    if not os.environ.get("QA_EVIDENCE_LOG_PATH", "").strip():
        return
    if not ev.evidence_hash:
        raise QAEvidenceCaptureError("capture đang bật nhưng Evidence thiếu evidence_hash")
    attempt = _qa_attempt_ctx.get() or {"origin": "direct", "order": 0}
    outputs = [
        {
            "answer": r.answer,
            "answer_vi": r.answer_vi,
            "answer_en": r.answer_en,
            "evidence_frame_idx": r.evidence_frame_idx,
            "confidence": r.confidence,
        }
        for r in results
    ]
    record: dict[str, object] = {
        "schema_version": QA_EVIDENCE_SCHEMA_VERSION,
        "record_type": "inference",
        "run_id": os.environ.get("LLM_RUN_ID", ""),
        "query_id": os.environ.get("LLM_QUERY_ID", ""),
        "attempt": {
            "origin": str(attempt.get("origin", "direct")),
            "order": int(attempt.get("order", 0)),
        },
        "mode": _current_qa_mode(),
        "stage": usage_tag,
        "evidence_hash": ev.evidence_hash,
        "effort": effort,
        "max_tokens": int(max_tokens),
        "requested_n": int(requested_n),
        "raw_count": int(raw_count),
        "parsed_count": len(results),
        "outputs": outputs,
    }
    record["output_hash"] = _hash_json({
        "schema_version": QA_EVIDENCE_SCHEMA_VERSION,
        "mode": record["mode"],
        "stage": usage_tag,
        "evidence_hash": ev.evidence_hash,
        "effort": effort,
        "max_tokens": int(max_tokens),
        "requested_n": int(requested_n),
        "outputs": outputs,
    })
    _append_capture_record(record)


def load_evidence_capture(path: str | Path, *, validate_images: bool = True) -> list[dict]:
    """Nạp và kiểm toàn bộ capture; hỏng một record/digest/link là từ chối."""
    capture_path = Path(path)
    if not capture_path.is_file():
        raise RuntimeError(f"thiếu QA evidence capture: {capture_path}")
    records: list[dict] = []
    evidence_hashes: set[str] = set()
    for line_no, line in enumerate(capture_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"capture JSON hỏng ở dòng {line_no}: {e}") from e
        if record.get("schema_version") != QA_EVIDENCE_SCHEMA_VERSION:
            raise RuntimeError(f"capture dòng {line_no} sai schema_version")
        record_type = record.get("record_type")
        if record_type == "evidence":
            expected_hash = _hash_json(_stable_evidence_payload(record))
            if not record.get("evidence_hash") or record["evidence_hash"] != expected_hash:
                raise RuntimeError(f"capture dòng {line_no} sai evidence_hash")
            if record.get("needs_images") and not (record.get("frames") or []):
                raise RuntimeError(f"capture dòng {line_no} yêu cầu ảnh nhưng không có frame")
            for frame in record.get("frames") or []:
                if not frame.get("sha256"):
                    raise RuntimeError(f"capture dòng {line_no} thiếu SHA-256 ảnh")
                if validate_images and _sha256_file(Path(frame["path"])) != frame["sha256"]:
                    raise RuntimeError(f"capture dòng {line_no} ảnh đã đổi digest: {frame['path']}")
            evidence_hashes.add(record["evidence_hash"])
        elif record_type == "inference":
            expected_output_hash = _hash_json({
                "schema_version": QA_EVIDENCE_SCHEMA_VERSION,
                "mode": record.get("mode"),
                "stage": record.get("stage"),
                "evidence_hash": record.get("evidence_hash"),
                "effort": record.get("effort"),
                "max_tokens": record.get("max_tokens"),
                "requested_n": record.get("requested_n"),
                "outputs": record.get("outputs") or [],
            })
            if not record.get("output_hash") or record["output_hash"] != expected_output_hash:
                raise RuntimeError(f"capture dòng {line_no} sai output_hash")
            attempt = record.get("attempt") or {}
            if "origin" not in attempt or "order" not in attempt:
                raise RuntimeError(f"capture dòng {line_no} thiếu origin/order")
        else:
            raise RuntimeError(f"capture dòng {line_no} có record_type lạ {record_type!r}")
        records.append(record)
    if not records:
        raise RuntimeError(f"QA evidence capture rỗng: {capture_path}")
    for line_no, record in enumerate(records, 1):
        if record.get("record_type") == "inference" and record.get("evidence_hash") not in evidence_hashes:
            raise RuntimeError(f"capture record {line_no} tham chiếu evidence_hash chưa tồn tại")
    return records


def validate_evidence_capture(
    path: str | Path,
    *,
    expected_query_ids: set[str] | None = None,
    validate_images: bool = True,
) -> dict[str, int]:
    """Promotion gate: mỗi QA thành công phải có evidence và output đã ghi bền."""
    records = load_evidence_capture(path, validate_images=validate_images)
    evidence_qids = {
        str(r.get("query_id", "")) for r in records if r.get("record_type") == "evidence"
    }
    output_qids = {
        str(r.get("query_id", "")) for r in records if r.get("record_type") == "inference"
    }
    expected = expected_query_ids or set()
    missing_evidence = expected - evidence_qids
    missing_outputs = expected - output_qids
    if missing_evidence or missing_outputs:
        raise RuntimeError(
            "QA capture chưa đủ cho promotion: "
            f"thiếu evidence={sorted(missing_evidence)}, thiếu output={sorted(missing_outputs)}"
        )
    return {
        "records": len(records),
        "evidence_records": sum(r.get("record_type") == "evidence" for r in records),
        "inference_records": sum(r.get("record_type") == "inference" for r in records),
    }


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
        f"Prompt version: {QA_INFERENCE_PROMPT_VERSION}",
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


def _llm_identity() -> dict[str, str]:
    """Chỉ lấy backend/model công khai; không đưa API key vào cache/trace."""
    backend = str(os.environ.get("LLM_BACKEND") or "<unset>").strip()
    model_env = {
        "api": "LLM_API_MODEL",
        "gemini": "LLM_GEMINI_MODEL",
        "local": "LLM_LOCAL_MODEL",
    }.get(backend)
    model = str(os.environ.get(model_env) or "<unset>") if model_env else "<invalid>"
    return {"backend": backend, "model": model}


def _planner_cache_identity(query_vi: str, runtime_fingerprint: str) -> dict[str, object]:
    """Planner không có evidence; các chiều còn lại vẫn khóa cache đầy đủ."""
    return {
        "cache_kind": "question_planner",
        "query_sha256": hashlib.sha256(query_vi.encode("utf-8")).hexdigest(),
        "llm": _llm_identity(),
        "prompt_version": QA_PLANNER_PROMPT_VERSION,
        "config_snapshot": {
            "qa_inference": qa_runtime_config(),
            "qa_hypotheses": qa_hypothesis_config_snapshot(),
        },
        "runtime_fingerprint": runtime_fingerprint,
    }


def _qa_cache_identity(
    question_vi: str,
    ev: Evidence,
    *,
    n: int,
    effort: str,
    max_tokens: int,
    usage_tag: str,
    runtime_fingerprint: str,
    full_query_sha256: str,
) -> dict[str, object]:
    """Identity đủ query/model/prompt/config/evidence để replay không trộn run."""
    return {
        "query_sha256": hashlib.sha256(question_vi.encode("utf-8")).hexdigest(),
        "full_query_sha256": full_query_sha256,
        "llm": _llm_identity(),
        "prompt_version": QA_INFERENCE_PROMPT_VERSION,
        "config_snapshot": {
            "qa_inference": qa_runtime_config(),
            "qa_hypotheses": qa_hypothesis_config_snapshot(),
            "n": int(n),
            "effort": effort,
            "max_tokens": int(max_tokens),
            "usage_tag": usage_tag,
        },
        "evidence_digest": ev.evidence_hash,
        "runtime_fingerprint": runtime_fingerprint,
    }


def _qa_cache_key(identity: dict[str, object]) -> str:
    canonical = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _qa_cache_get(key: str, identity: dict[str, object]) -> list[str] | None:
    if os.environ.get("LLM_NO_CACHE"):
        return None
    path = qa_hypothesis_cache_dir() / f"{key}.json"
    if not path.is_file():
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise QAEvidenceCaptureError(f"QA hypothesis cache hỏng {path}: {error}") from error
    if (
        record.get("schema_version") != QA_HYPOTHESIS_CACHE_SCHEMA_VERSION
        or record.get("identity") != identity
        or not isinstance(record.get("outputs"), list)
        or not all(isinstance(item, str) for item in record["outputs"])
    ):
        raise QAEvidenceCaptureError(
            f"QA hypothesis cache fingerprint/schema mismatch: {path}"
        )
    return list(record["outputs"])


def _qa_cache_put(key: str, identity: dict[str, object], outputs: list[str]) -> None:
    if os.environ.get("LLM_NO_CACHE"):
        return
    directory = qa_hypothesis_cache_dir()
    path = directory / f"{key}.json"
    temp_path = directory / f".{key}.{os.getpid()}.{threading.get_ident()}.tmp"
    record = {
        "schema_version": QA_HYPOTHESIS_CACHE_SCHEMA_VERSION,
        "identity": identity,
        "outputs": outputs,
    }
    if identity.get("provenance"):
        record["provenance"] = identity["provenance"]
    try:
        directory.mkdir(parents=True, exist_ok=True)
        temp_path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        temp_path.replace(path)
    except OSError as error:
        raise QAEvidenceCaptureError(f"không ghi được QA hypothesis cache {path}: {error}") from error


def _qa_cached_outputs(
    key: str,
    identity: dict[str, object],
    producer: Callable[[], list[str]],
) -> list[str]:
    """Double-check cache dưới per-key lock để cùng key chỉ gọi provider một lần."""
    if os.environ.get("LLM_NO_CACHE"):
        return producer()
    with _qa_cache_single_flight(key):
        cached = _qa_cache_get(key, identity)
        if cached is not None:
            return cached
        outputs = producer()
        if not outputs or not all(isinstance(item, str) for item in outputs):
            raise QAEvidenceCaptureError("QA cache producer trả output sai contract")
        _qa_cache_put(key, identity, outputs)
        return outputs


def ask_llm(
    question_vi: str,
    ev: Evidence,
    *,
    n: int = SELF_CONSISTENCY_N,
    effort: str = "high",
    max_tokens: int = QA_LEGACY_MAX_TOKENS,
    usage_tag: str = "qa.legacy",
    runtime_fingerprint: str | None = None,
) -> list[QAResult]:
    """Gọi llm() `n` lần, trả list QAResult đã
    kẹp evidence_frame_idx về tập frame CÓ THẬT (không tin thẳng số VLM tự bịa —
    xem "hai cửa tử độc lập" ở đầu file)."""
    images = [str(p) for _, p in ev.frames] or None
    prompt = _build_prompt(question_vi, ev)
    budget = _generation_budget_ctx.get()
    if (
        budget is not None
        and _current_qa_mode() == "two_stage"
        and (usage_tag.startswith("qa.screen.") or usage_tag.startswith("qa.confirm."))
    ):
        # Giữ chỗ TRƯỚC request mạng. Nếu không đủ cho cả n, không gọi một phần.
        budget.reserve(n, usage_tag)
    # ⚠️ SỬA 18/08 — adapter.py (DEFAULT_EFFORT) ghi rõ: "Task nào cần nghĩ kỹ
    # (Q&A suy luận) thì tự truyền effort='high'". Đây CHÍNH LÀ bước suy luận
    # đó — mọi lệnh gọi trong qa.py trước bản sửa này đều để mặc định "low"
    # (dịch/mở rộng câu ngắn), tức bước quan trọng nhất của Q&A đang chạy ở
    # effort THẤP NHẤT trên backend "api" (Claude — backend thi thật, xem
    # CLAUDE.md mục 11 "Chưa chốt: internet lúc thi"). Không crash, không lộ ở
    # backend "gemini" (effort không ảnh hưởng gì bên đó) — lỗi im lặng thuần
    # chất lượng câu trả lời, chỉ lộ ra khi đổi ANTHROPIC_API_KEY lúc thi.
    fingerprint = runtime_fingerprint or _qa_runtime_fingerprint_ctx.get()
    full_query_sha256 = (
        _qa_full_query_hash_ctx.get()
        or hashlib.sha256(question_vi.encode("utf-8")).hexdigest()
    )
    identity = _qa_cache_identity(
        question_vi,
        ev,
        n=n,
        effort=effort,
        max_tokens=max_tokens,
        usage_tag=usage_tag,
        runtime_fingerprint=fingerprint,
        full_query_sha256=full_query_sha256,
    )
    key = _qa_cache_key(identity)
    def produce() -> list[str]:
        raw = llm(
            prompt, images=images, json_schema=QA_RESULT_SCHEMA, n=n,
            effort=effort, max_tokens=max_tokens,
        )
        return list(raw) if isinstance(raw, list) else [raw]

    raw_list = (
        _qa_cached_outputs(key, identity, produce)
        if ev.evidence_hash else produce()
    )

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
    _capture_inference_output(
        ev,
        usage_tag=usage_tag,
        effort=effort,
        max_tokens=max_tokens,
        requested_n=n,
        raw_count=len(raw_list),
        results=results,
    )
    return results


def _vote_results(results: list[QAResult]) -> tuple[str, int | None, float] | None:
    """Vote + chấm confidence cho đúng MỘT bộ evidence; không trộn text với ảnh."""
    if not results:
        return None
    answer, votes = majority_answer([r.answer for r in results])
    if len(results) > 1 and votes < 2:
        return None
    frame = next((r.evidence_frame_idx for r in results if r.answer == answer), None)
    if frame is None:
        frame = results[0].evidence_frame_idx
    winner_confs = [r.confidence for r in results if r.answer == answer]
    confidence = (sum(winner_confs) / len(winner_confs)) * (votes / len(results))
    return answer, frame, confidence


_ATTEMPT_EVIDENCE_KEYS = ("evidence_hash", "evidence_type", "evidence_stage")


def _attempt_evidence_snapshot() -> dict[str, object]:
    attempt = _qa_attempt_ctx.get()
    if attempt is None:
        return {}
    return {key: attempt[key] for key in _ATTEMPT_EVIDENCE_KEYS if key in attempt}


def _restore_attempt_evidence(snapshot: dict[str, object]) -> None:
    attempt = _qa_attempt_ctx.get()
    if attempt is None:
        return
    for key in _ATTEMPT_EVIDENCE_KEYS:
        if key in snapshot:
            attempt[key] = snapshot[key]
        else:
            attempt.pop(key, None)


def _infer_legacy(question_vi: str, hit: ShotHit, ev: Evidence,
                  evidence_type: str) -> tuple[str, int | None, float] | None:
    """Đường rollback n=3 cũ, giữ nguyên hành vi để so A/B và cứu release."""
    results = ask_llm(question_vi, ev)
    if not results:
        return None
    avg_conf = sum(r.confidence for r in results) / len(results)
    if avg_conf < LOW_CONFIDENCE and not ev.frames:
        text_evidence = _attempt_evidence_snapshot()
        ev_img = collect_evidence(hit, question_vi, evidence_type, needs_images=True)
        if ev_img.frames:
            with_images = ask_llm(
                question_vi, ev_img, usage_tag="qa.legacy.image",
            )
            if with_images:
                results = with_images
            else:
                # Không có output ảnh thì vote vẫn dựa trên cohort text ban đầu;
                # provenance phải quay lại digest text, không gắn nhầm ảnh vừa thử.
                _restore_attempt_evidence(text_evidence)
        else:
            _restore_attempt_evidence(text_evidence)
    return _vote_results(results)


def _infer_two_stage(question_vi: str, hit: ShotHit, ev: Evidence,
                     evidence_type: str) -> tuple[str, int | None, float] | None:
    """Sàng lọc n=1 rồi xác nhận thêm n=2 trên CHÍNH bộ evidence đã sàng lọc.

    Nếu text yếu và chuyển sang ảnh, phiếu text bị bỏ hoàn toàn: hai prompt có
    evidence khác nhau không được coi là ba phiếu self-consistency cùng cohort.
    """
    stage = "image" if ev.frames else "text"
    screen = ask_llm(
        question_vi, ev, n=1, effort=QA_SCREEN_EFFORT,
        max_tokens=QA_SCREEN_MAX_TOKENS, usage_tag=f"qa.screen.{stage}",
    )
    if len(screen) != 1:
        return None

    if screen[0].confidence < LOW_CONFIDENCE and not ev.frames:
        text_evidence = _attempt_evidence_snapshot()
        ev_img = collect_evidence(hit, question_vi, evidence_type, needs_images=True)
        if ev_img.frames:
            # Evidence đổi → reset cohort bằng một screen ảnh mới, không giữ phiếu text.
            ev = ev_img
            stage = "image"
            screen = ask_llm(
                question_vi, ev, n=1, effort=QA_SCREEN_EFFORT,
                max_tokens=QA_SCREEN_MAX_TOKENS, usage_tag="qa.screen.image",
            )
            if len(screen) != 1:
                _restore_attempt_evidence(text_evidence)
                return None
        else:
            _restore_attempt_evidence(text_evidence)

    if screen[0].confidence < QA_SCREEN_CONFIRM_MIN_CONFIDENCE:
        return None

    confirm = ask_llm(
        question_vi, ev, n=QA_CONFIRM_ADDITIONAL_N,
        effort=QA_CONFIRM_EFFORT, max_tokens=QA_CONFIRM_MAX_TOKENS,
        usage_tag=f"qa.confirm.{stage}",
    )
    if len(confirm) != QA_CONFIRM_ADDITIONAL_N:
        return None
    return _vote_results(screen + confirm)


def _try_shot(
    hit: ShotHit, question_vi: str, evidence_type: str, needs_images: bool
) -> tuple[str, int | None, float] | None:
    """Thử suy luận trên MỘT shot. Trả `(answer, evidence_frame_idx, confidence)`,
    hoặc None nếu bằng chứng không đủ để chốt (chỗ gọi thử shot kế tiếp).

    `confidence` ∈ [0,1] dùng để SO SÁNH GIỮA CÁC SHOT — chỗ gọi (`qa_pipeline`)
    thử hết `MAX_SHOTS_TRIED` shot rồi chọn confidence cao nhất, KHÔNG dừng ở
    shot đầu tiên "đủ tự tin". Xem ⚠️ SỬA 20/08 ở `qa_pipeline`.

    ⚠️ SỬA 16/08 — bản trước chỉ trả `str`, nên `evidence_frame_idx` mà `ask_llm()`
    đã cất công kẹp về tập frame CÓ THẬT (xem "hai cửa tử độc lập" đầu file) bị
    VỨT ĐI ngay tại đây. `reports/C31_C32_C44_TECHNICAL_REPORT.md` §93 khẳng định
    cơ chế kẹp đó bảo vệ cửa frame của Q&A — thực tế nó chưa từng rời khỏi hàm này,
    và frame nộp hoàn toàn do thứ hạng shot của allocator quyết định.
    """
    ev = collect_evidence(hit, question_vi, evidence_type, needs_images)
    attempt = _qa_attempt_ctx.get()
    if isinstance(attempt, dict) and ev.evidence_hash:
        attempt.update({
            "evidence_hash": ev.evidence_hash,
            "evidence_type": evidence_type,
            "evidence_stage": "image" if ev.frames else "text",
        })

    if evidence_type == "count":
        # `object_count == 0` KHÔNG còn tới được đây: `_object_count()` trả None khi
        # detector không thấy nhãn nào, thay vì 0. Giữ điều kiện `> 0` làm chốt chặn
        # thứ hai — nộp "0" cho câu "có bao nhiêu…" gần như luôn là dấu hiệu nhãn
        # không khớp, không phải sự thật.
        if ev.object_count is not None and ev.object_count > 0:
            # detector, KHÔNG hỏi VLM (BUILD_TASKS C3.1). Bằng chứng nằm ở đúng
            # keyframe vừa đếm — coi như tin cậy tuyệt đối, không có gì để so
            # self-consistency (detector không "phiếu bầu" nhiều lần).
            if ev.best_frame_idx is None:
                raise RuntimeError("detector có answer nhưng keyframe không tra được frame tuyệt đối")
            provenance = (
                f"{attempt.get('origin', 'direct') if isinstance(attempt, dict) else 'direct'}:"
                f"detector:{_current_qa_mode()}"
            )
            identity = _qa_cache_identity(
                question_vi,
                ev,
                n=0,
                effort="detector",
                max_tokens=0,
                usage_tag="qa.detector.count",
                runtime_fingerprint=_qa_runtime_fingerprint_ctx.get(),
                full_query_sha256=(
                    _qa_full_query_hash_ctx.get()
                    or hashlib.sha256(question_vi.encode("utf-8")).hexdigest()
                ),
            )
            identity.update({"cache_kind": "detector", "provenance": provenance})
            key = _qa_cache_key(identity)

            def produce_detector() -> list[str]:
                return [json.dumps({
                    "answer": str(ev.object_count),
                    "answer_vi": str(ev.object_count),
                    "answer_en": str(ev.object_count),
                    "evidence_frame_idx": ev.best_frame_idx,
                    "confidence": 1.0,
                }, ensure_ascii=False, sort_keys=True)]

            [raw_detector] = _qa_cached_outputs(key, identity, produce_detector)
            parsed_detector = json.loads(raw_detector)
            direct = QAResult(
                str(parsed_detector["answer"]),
                str(parsed_detector.get("answer_vi", parsed_detector["answer"])),
                str(parsed_detector.get("answer_en", parsed_detector["answer"])),
                int(parsed_detector["evidence_frame_idx"]),
                float(parsed_detector["confidence"]),
                "count",
            )
            _capture_inference_output(
                ev,
                usage_tag="qa.detector.count",
                effort="detector",
                max_tokens=0,
                requested_n=0,
                raw_count=1,
                results=[direct],
            )
            return direct.answer, direct.evidence_frame_idx, direct.confidence
        print(f"  [cảnh báo] shot {hit.shot_id}: không đếm được bằng detector, hỏi LLM (kém tin cậy hơn)")

    mode = _current_qa_mode()
    if mode == "legacy":
        return _infer_legacy(question_vi, hit, ev, evidence_type)
    if mode == "two_stage":
        return _infer_two_stage(question_vi, hit, ev, evidence_type)
    raise ValueError(
        f"QA_INFERENCE_MODE={mode!r} không hợp lệ; dùng legacy|two_stage"
    )


def _evidence_hash_for_attempt(
    attempt_details: dict[str, object],
    *,
    hit: ShotHit,
) -> str:
    """Production luôn fail closed; test double phải tự gắn digest vào context."""
    evidence_hash = str(attempt_details.get("evidence_hash") or "").strip()
    if evidence_hash:
        return evidence_hash
    raise QANoValidHypothesisError(
        f"shot {hit.shot_id} sinh answer nhưng thiếu evidence_hash"
    )


# ------------------------------------------------------------------------- API chính

def _ung_vien_nhanh_text(
    event_vi: str,
    query_en: str | None,
    evidence_type: str,
    top_k: int,
) -> list[ShotHit]:
    """Vài shot mà riêng nhánh TEXT xếp cao nhất. Tốn đúng 1 lần search, KHÔNG gọi llm().

    Chỉ chạy cho câu hỏi mà bằng chứng nằm trong chữ/tiếng — xem
    QA_TEXT_FALLBACK_ROUTES trong data/config/search_weights.py để biết số đo và lý do.

    ⚠️ `top_k` truyền vào phải BẰNG top_k của lần search chính, rồi mới cắt lấy
    QA_TEXT_FALLBACK_QUOTA shot đầu. KHÔNG được gọi thẳng search(top_k=5).
    Đo thật 20/08 trên QA05:

        search(top_k=5)       → L28_V001#s0126, L28_V002#s0054, L28_V007#s0016/17/18
        search(top_k=100)[:5] → L28_V001#s0126, L28_V002#s0054, L28_V014#s0133, ...
                                                                ^^^^^^^^ video ĐÚNG

    Vì bể ứng viên nội bộ của search() tỉ lệ với top_k (`pool = top_k *
    CANDIDATE_MULTIPLIER`), top_k nhỏ không cho ra TIỀN TỐ của bảng lớn mà cho ra
    một bảng KHÁC — nghèo hơn. Bản đầu của bản vá này gọi top_k=5 và làm video
    đúng biến mất hoàn toàn, trong khi ở bảng đủ rộng nó đứng hạng 3.

    KHÔNG khử trùng với bể ứng viên chính ở đây — đó là việc của chỗ gọi, vì hai
    mục đích (suy luận / cấp slot) cần hai luật khử trùng khác nhau.

    Lỗi bị nuốt: đây là đường phụ trợ, hỏng thì Q&A chạy tiếp như chưa có nó.
    """
    from data.config.search_weights import (
        QA_TEXT_FALLBACK_ENABLED,
        QA_TEXT_FALLBACK_QUOTA,
        QA_TEXT_FALLBACK_ROUTES,
    )

    if not QA_TEXT_FALLBACK_ENABLED or evidence_type not in QA_TEXT_FALLBACK_ROUTES:
        return []

    try:
        res = search(event_vi, query_en=query_en, top_k=top_k,
                     group_by_shot=True, branches={"vector": False})
    except Exception as e:
        print(f"  [cảnh báo] search nhánh text lỗi, bỏ qua ứng viên bổ sung: {e}")
        return []

    them = [
        ShotHit(r["shot_id"], r["score"], r["keyframe_id"])
        for r in res if r.get("shot_id")
    ][:QA_TEXT_FALLBACK_QUOTA]
    if them:
        print(f"  [{evidence_type}] nhánh text đề cử {len(them)} shot: "
              + ", ".join(h.shot_id for h in them))
    return them


def _qa_pipeline_impl(
    query_vi: str,
    top_k_shots: int = TOP_K_SHOTS_FOR_SLOTS,
    query_en: str | None = None,
    return_trace: bool = False,
) -> tuple[list[ShotHit], str] | tuple[list[ShotHit], str, dict[str, object]]:
    """query VI → ứng viên, đáp án và tùy chọn provenance Q&A.

    Chỗ gọi tự đưa 2 giá trị này vào backend.slot.allocate(hits, "QA",
    answer_text=...) để ra đủ 100 dòng nộp — xem docstring đầu file.

    Input: query, số shot, bản dịch EN và cờ trace. Output mặc định giữ nguyên
    `(hits, answer)` để mọi caller cũ tương thích; `return_trace=True` thêm dict
    chứa route, shot và frame đã sinh answer. Invariant: trace chỉ mô tả evidence
    đã dùng, không đổi thứ hạng/score hay frame mà allocator sẽ nộp.

    ⚠️ SỬA 16/08 — hai thay đổi về SỐ SHOT và THỨ TỰ SHOT:

    · `top_k_shots` mặc định thành TOP_K_SHOTS_FOR_SLOTS (100), không còn là
      TOP_K_SHOTS (5). Chỉ MAX_SHOTS_TRIED shot đầu được đem đi suy luận nên chi
      phí LLM không đổi, nhưng allocator có đủ shot để phủ rộng.

    · Shot suy ra được câu trả lời được ĐẨY LÊN HẠNG 1. Bản trước trả nguyên thứ
      tự search, nên khi shot #3 mới cho ra answer thì slot hạng 1 vẫn rơi vào
      shot #1 — chính cái shot pipeline vừa kết luận là không đủ bằng chứng.
      Q&A có hai cửa tử ĐỘC LẬP (frame và answer): ghép answer của shot #3 với
      frame của shot #1 là tự tay phá cửa thứ nhất trong khi cửa thứ hai đã đúng.

    ⚠️ SỬA 20/08 — "dừng ở shot ĐẦU TIÊN đủ tự tin" → "thử hết MAX_SHOTS_TRIED
    shot rồi chọn confidence CAO NHẤT". Điều tra câu QA_004 (holdout đội bạn,
    "cách mặt đường bao xa"): search() xếp video đúng ở HẠNG 3, nhưng shot hạng
    1 (video sai) đã đủ tự tin để `_try_shot` chốt ngay ở ngưỡng cũ → pipeline
    KHÔNG BAO GIỜ chạm tới bằng chứng đúng ở hạng 3 (ASR có sẵn câu trả lời,
    test cô lập cho 3/3 đúng). Với retrieval còn nhiễu (chỉ 6/26 câu QA holdout
    có video đúng lọt top-3), "câu trả lời hợp lý đầu tiên" gần như chắc chắn
    SAI VIDEO — thử hết rồi lấy tốt nhất mới cho các shot xếp sau cơ hội. Cả
    video expansion budget cũng được thử deterministic; confidence tự khai của
    LLM không được phép chặn candidate-specific hypotheses khác.
    """
    parts = parse_question(query_vi)
    if parts.answer_mode is None or parts.planner_fallback:
        evidence_type, needs_images = route_question(parts.question_vi)
        answer_mode = parts.answer_mode or _answer_mode_for_evidence_type(evidence_type)
    else:
        answer_mode = parts.answer_mode
        evidence_type, needs_images = _route_for_answer_mode(answer_mode)

    # ⚠️ SỬA 20/08 — KHÔNG chuyển thẳng `query_en` (mọi chỗ gọi production —
    # run.py, run_minimal.py, backend/api/main.py — đều truyền vào đây là bản
    # dịch của CẢ CÂU HỎI GỐC `query_vi`, ví dụ "How far did the car fly from
    # the road after the crash?") sang `search(parts.event_vi, ...)`.
    # `parts.event_vi` là một CÂU TIẾNG VIỆT KHÁC — chỉ phần mô tả sự kiện
    # thị giác do `parse_question()` tách ra (vd "chiếc ô tô văng xuống ruộng
    # lúa"), KHÔNG có phần câu hỏi. Đưa bản dịch của câu hỏi vào
    # `encode_text()` (nhánh CLIP) và nhánh objects (`match: labels.txt`) làm
    # CLIP so khớp lệch — phát hiện khi điều tra QA_004 (holdout đội bạn):
    # video đúng tụt hạng, cùng lúc với lỗi "dừng ở shot đầu tiên" đã sửa ở
    # trên. Chỉ tái dùng `query_en` của caller khi `parse_question()` KHÔNG
    # tách được (rơi về nguyên câu gốc, `event_vi == query_vi` — lúc đó hai
    # bản dịch chắc chắn khớp nhau); còn lại để `search()` tự dịch
    # `event_vi` mới — thêm đúng một lượt gọi llm(), không đáng kể so với
    # hàng chục lượt `ask_llm()` suy luận QA đã tốn ngay sau đó.
    event_query_en = query_en if parts.event_vi == query_vi else None
    hits = search(parts.event_vi, query_en=event_query_en, top_k=top_k_shots, group_by_shot=True)
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

    # Ứng viên nhánh text phục vụ HAI mục đích khác nhau, và phải xử lý khác nhau:
    #
    #   · CẤP SLOT (100 dòng nộp) — nối vào CUỐI, giữ nguyên thứ tự ứng viên gốc.
    #     Chen lên đầu là đổi thứ hạng frame của cả bài nộp bằng một tín hiệu chưa
    #     được kiểm chứng.
    #   · SUY LUẬN (sinh answer) — phải được THỬ, nếu không bản vá vô nghĩa:
    #     vòng dưới chỉ lấy MAX_SHOTS_TRIED shot đầu, mà ứng viên vừa nối
    #     nằm ở vị trí 100+. Đây chính là chỗ QA05 cần: video đúng đứng hạng 16
    #     theo bảng đủ nhánh (ngoài tầm suy luận) nhưng hạng 3 theo nhánh text.
    #
    # Shot nào thắng thì `_dua_len_dau` kéo nó lên hạng 1 — nên frame nộp vẫn
    # khớp với shot đã sinh ra câu trả lời (cửa tử thứ nhất của Q&A).
    # ⚠️ HAI luật khử trùng khác nhau, đây là chỗ bản đầu làm sai và biến cả bản
    # vá thành vô nghĩa (đo 20/08: cả 5 shot nhánh text đều ĐÃ có trong bể 100 —
    # hạng 6, 9, 28, 75, 76 — nên khử trùng theo bể xoá sạch, hàm trả 0 shot).
    #
    # Vấn đề chưa bao giờ là "shot vắng mặt trong bể", mà là "shot đứng hạng 16
    # trong khi chỉ 3 shot đầu được đem đi suy luận". Nên:
    #   · SUY LUẬN — khử trùng trong CHÍNH danh sách thử (đừng thử 2 lần cùng
    #     một shot), KHÔNG khử theo bể. Shot hạng 16 mà nhánh text tin thì vẫn
    #     phải được thử.
    #   · CẤP SLOT — khử theo bể, chỉ nối shot THẬT SỰ mới vào cuối. Bể 100 dòng
    #     không được có hai dòng cùng nội dung.
    ung_vien_text = _ung_vien_nhanh_text(
        parts.event_vi, query_en, evidence_type, top_k_shots
    )

    # ⚠️ THỨ TỰ THỬ mới là thứ quyết định, không phải danh sách có ai.
    #
    # Đo 20/08 (run_20260820_2225): ứng viên nhánh text ĐÃ vào danh sách — log
    # ghi rõ "nhánh text đề cử ... L28_V014#s0133" — mà điểm QA không nhúc nhích.
    # Lý do bản đầu: vòng dưới DỪNG ở shot ĐẦU TIÊN trả lời được, nối thêm vào
    # SAU người thắng thì có nối bao nhiêu cũng vô nghĩa.
    #
    # Nên với câu hỏi mà `route_question` đã kết luận bằng chứng nằm trong
    # CHỮ/TIẾNG, shot do nhánh text xếp hạng được thử TRƯỚC — đó chính là ý
    # nghĩa của định tuyến ("lời nói → ASR"), áp dụng cho cả việc CHỌN SHOT để
    # đọc bằng chứng, không chỉ chọn LOẠI bằng chứng.
    #
    # ⚠️ SỬA 21/08 (Công Lý, "dress rehearsal" 25 câu) — thứ tự ưu tiên KHÔNG
    # thay thế nguyên tắc "thử hết rồi chọn confidence cao nhất" (xem docstring
    # trên): dừng ở kết quả ĐẦU TIÊN "đủ tự tin" vẫn là đúng lỗi QA_004 đã sửa —
    # chỉ khác chỗ danh sách để thử giờ có thêm ứng viên nhánh text đứng trước.
    # Chỉ đổi thứ tự SUY LUẬN. Thứ tự 100 dòng nộp bên dưới vẫn nguyên vẹn.
    thu_de_suy_luan: list[ShotHit] = []
    for h in ung_vien_text + candidate_shots[:MAX_SHOTS_TRIED]:
        if h.shot_id not in {x.shot_id for x in thu_de_suy_luan}:
            thu_de_suy_luan.append(h)

    co_roi = {h.shot_id for h in candidate_shots}
    candidate_shots += [h for h in ung_vien_text if h.shot_id not in co_roi]

    best: tuple[int, ShotHit, str, int | None, float] | None = None  # (i, hit, answer, frame, confidence)
    tried_shot_ids: set[str] = set()
    text_shot_ids = {h.shot_id for h in ung_vien_text}
    attempt_order = 0
    budget_exhausted = False
    hypotheses: list[QAHypothesis] = []
    hypothesis_keys: set[tuple[str, int, str]] = set()
    for hit in thu_de_suy_luan:
        tried_shot_ids.add(hit.shot_id)
        attempt_order += 1
        attempt_token = _qa_attempt_ctx.set({
            "origin": "text_fallback" if hit.shot_id in text_shot_ids else "main",
            "order": attempt_order,
        })
        attempt_details: dict[str, object] = {}
        try:
            ket_qua = _try_shot(hit, parts.question_vi, evidence_type, needs_images)
        except QAGenerationBudgetExceeded as e:
            print(f"  [giới hạn] {e}")
            budget_exhausted = True
            break
        except QAEvidenceCaptureError:
            raise
        except Exception as e:
            print(f"  [cảnh báo] shot {hit.shot_id} lỗi khi suy luận Q&A, thử shot kế tiếp: {e}")
            continue
        finally:
            attempt_details = dict(_qa_attempt_ctx.get() or {})
            _qa_attempt_ctx.reset(attempt_token)
        if ket_qua is None:
            continue
        answer, frame, confidence = ket_qua
        if not is_valid_qa_answer(answer, answer_mode):
            print(f"  [cảnh báo] shot {hit.shot_id}: loại sentinel answer {answer!r}")
            continue
        if frame is None:
            print(f"  [cảnh báo] shot {hit.shot_id}: answer thiếu evidence frame")
            continue
        evidence_hash = _evidence_hash_for_attempt(
            attempt_details,
            hit=hit,
        )
        provenance = (
            f"{attempt_details.get('origin', 'legacy_caller')}:"
            f"{'detector' if evidence_type == 'count' else 'llm'}:{_current_qa_mode()}"
        )
        hypothesis = build_qa_hypothesis(
            hit,
            answer_text=answer,
            evidence_frame_idx=int(frame),
            confidence=confidence,
            evidence_hash=evidence_hash,
            provenance=provenance,
            answer_mode=answer_mode,
            evidence_type=evidence_type,
        )
        if hypothesis is not None:
            hypothesis_key = (
                hypothesis.video_id,
                hypothesis.evidence_frame_idx,
                _normalize_answer(hypothesis.answer_text),
            )
            if hypothesis_key not in hypothesis_keys:
                hypotheses.append(hypothesis)
                hypothesis_keys.add(hypothesis_key)
        print(f"  ({hit.shot_id}): answer={answer!r} confidence={confidence:.2f}")
        # Tra theo shot_id, KHÔNG dùng list.index(hit): shot đề cử bởi nhánh
        # text mang `score` của bảng text nên khác object với bản nằm trong
        # bể chính — `.index()` sẽ ném ValueError đúng lúc vừa có câu trả lời.
        i = next(j for j, h in enumerate(candidate_shots) if h.shot_id == hit.shot_id)
        # Vòng chính KHÔNG phạt theo hạng: shot do nhánh text đề cử được nối vào
        # cuối `candidate_shots` nên chỉ số của nó lớn, nhưng đó là ứng viên
        # được CHỌN CÓ CHỦ ĐÍCH chứ không phải kết quả mò sâu — phạt nó là cắt
        # đúng đường ứng viên text.
        if best is None or confidence > best[4]:
            best = (i, hit, answer, frame, confidence)

    # ⚠️ THÊM 21/08 — vòng chính (kể cả ứng viên nhánh text) chưa đủ tin cậy: có
    # thể ĐÚNG VIDEO nhưng SAI SHOT (event_vi thuần thị giác không phân biệt
    # được hai cảnh giống nhau trong cùng video — xem VIDEO_EXPAND_SHOTS). Mở
    # rộng tìm thêm shot trong từng video đã thấy, dùng nguyên câu hỏi ĐẦY ĐỦ
    # (query_vi, còn từ khoá cụ thể mà event_vi thuần thị giác không có).
    # `candidate_shots` được NỐI THÊM (không thay list gốc) để `_dua_len_dau`
    # cuối hàm vẫn dùng index bình thường.
    if not budget_exhausted:
        seen_videos: list[str] = []
        for hit in thu_de_suy_luan:
            vid = hit.shot_id.split("#")[0]
            if vid not in seen_videos:
                seen_videos.append(vid)

        for vid in seen_videos[:MAX_VIDEOS_EXPANDED]:
            try:
                extra_hits = _expand_within_video(vid, query_vi, query_en, tried_shot_ids)
            except Exception as e:
                print(f"  [cảnh báo] mở rộng video {vid} lỗi: {e}")
                continue
            for hit in extra_hits:
                candidate_shots.append(hit)
                i = len(candidate_shots) - 1
                tried_shot_ids.add(hit.shot_id)
                attempt_order += 1
                attempt_token = _qa_attempt_ctx.set({
                    "origin": "video_expand",
                    "order": attempt_order,
                })
                attempt_details = {}
                try:
                    ket_qua = _try_shot(hit, parts.question_vi, evidence_type, needs_images)
                except QAGenerationBudgetExceeded as e:
                    print(f"  [giới hạn] {e}")
                    budget_exhausted = True
                    break
                except QAEvidenceCaptureError:
                    raise
                except Exception as e:
                    print(f"  [cảnh báo] shot {hit.shot_id} lỗi khi suy luận Q&A: {e}")
                    continue
                finally:
                    attempt_details = dict(_qa_attempt_ctx.get() or {})
                    _qa_attempt_ctx.reset(attempt_token)
                if ket_qua is None:
                    continue
                answer, frame, confidence = ket_qua
                if not is_valid_qa_answer(answer, answer_mode) or frame is None:
                    print(f"  [cảnh báo] shot {hit.shot_id}: answer sentinel/thiếu frame bị loại")
                    continue
                evidence_hash = _evidence_hash_for_attempt(
                    attempt_details,
                    hit=hit,
                )
                hypothesis = build_qa_hypothesis(
                    hit,
                    answer_text=answer,
                    evidence_frame_idx=int(frame),
                    confidence=confidence,
                    evidence_hash=evidence_hash,
                    provenance=f"video_expand:{'detector' if evidence_type == 'count' else 'llm'}:{_current_qa_mode()}",
                    answer_mode=answer_mode,
                    evidence_type=evidence_type,
                )
                if hypothesis is not None:
                    hypothesis_key = (
                        hypothesis.video_id,
                        hypothesis.evidence_frame_idx,
                        _normalize_answer(hypothesis.answer_text),
                    )
                    if hypothesis_key not in hypothesis_keys:
                        hypotheses.append(hypothesis)
                        hypothesis_keys.add(hypothesis_key)
                print(f"  [mở rộng {vid}] ({hit.shot_id}): answer={answer!r} confidence={confidence:.2f}")
                # Chỉ shot ĐÀO THÊM mới chịu phạt độ sâu, và phạt một chiều:
                # nó phải vượt confidence thô của đương kim sau khi trả phí độ
                # sâu. Đây đúng là chỗ sinh ra hai winner hạng 104/105 hôm 28/08.
                if best is None or _diem_co_phat_hang(confidence, i) > best[4]:
                    best = (i, hit, answer, frame, confidence)
            if budget_exhausted:
                break

    if (best is None or not hypotheses) and candidate_shots and not budget_exhausted:
        # THÀ ĐOÁN CÒN HƠN BỎ TRỐNG. Không có hình phạt cho câu sai, mà bỏ trống
        # thì `finalize` chặn cả gói ZIP (đo 28/08: p1-15 và p1-3 làm hỏng toàn
        # bộ submission). Q&A có hai cửa tử độc lập nên answer sai vẫn là 0 —
        # nhưng video+frame đúng thì người thao tác sửa answer bằng tay được,
        # còn không nộp gì thì không sửa được. Đáp án chỗ trống này CỐ Ý vô
        # nghĩa để người soi thấy ngay là phải điền, không tưởng là máy trả lời.
        hit = candidate_shots[0]
        frame = load_frame_map().get(hit.best_keyframe_id)
        if frame is not None:
            answer = _dap_an_cho_trong(answer_mode)
            hypothesis = build_qa_hypothesis(
                hit,
                answer_text=answer,
                evidence_frame_idx=int(frame),
                confidence=0.0,
                evidence_hash=_evidence_hash_for_attempt({}, hit=hit),
                provenance=f"placeholder:no_answer:{_current_qa_mode()}",
                answer_mode=answer_mode,
                evidence_type=evidence_type,
            )
            if hypothesis is not None:
                hypotheses.append(hypothesis)
                best = (0, hit, answer, int(frame), 0.0)
                print(f"  [CHỖ TRỐNG] không shot nào trả lời được — nộp shot đầu bảng "
                      f"({hit.shot_id}) với answer={answer!r}, NGƯỜI PHẢI ĐIỀN TAY")

    if best is None or not hypotheses:
        suffix = (
            f" Đã chạm trần {QA_TWO_STAGE_MAX_GENERATIONS} generation two-stage."
            if budget_exhausted else ""
        )
        raise QANoValidHypothesisError(
            f"Thử {len(tried_shot_ids)} shot (kể cả ứng viên nhánh text và mở rộng trong video) đều "
            "không suy luận được câu trả lời đủ tin cậy — kiểm tra bằng chứng (OCR/ASR/metadata) "
            f"của các shot này có rỗng không.{suffix}"
        )

    i, hit, answer, evidence_frame_idx, confidence = best
    if evidence_frame_idx is None:
        raise RuntimeError("Q&A winner thiếu evidence_frame_idx; từ chối ghép answer với frame đoán")
    video_id = hit.shot_id.split("#", 1)[0]
    winning_keyframe_id = _keyframe_id_for_frame(
        video_id, int(evidence_frame_idx), preferred=hit.best_keyframe_id,
    )
    if i > 0:
        print(f"  shot thắng là hạng {i + 1} ({hit.shot_id}, confidence={confidence:.2f}) — đẩy lên "
              "hạng 1 để frame nộp khớp với shot đã sinh ra câu trả lời")
    ranked_hits = _dua_len_dau(
        candidate_shots, i, winning_keyframe_id=winning_keyframe_id,
    )
    submitted_frame = load_frame_map().get(ranked_hits[0].best_keyframe_id)
    if submitted_frame != int(evidence_frame_idx):
        raise RuntimeError(
            "không pin được frame nộp Q&A vào evidence winner: "
            f"keyframe={ranked_hits[0].best_keyframe_id!r} -> {submitted_frame}, "
            f"evidence={evidence_frame_idx}"
        )
    if return_trace:
        runtime = qa_runtime_config()
        budget = _generation_budget_ctx.get()
        return ranked_hits, answer, {
            "event_vi": parts.event_vi,
            "question_vi": parts.question_vi,
            "evidence_type": evidence_type,
            "answer_mode": answer_mode,
            "planner_fallback": parts.planner_fallback,
            "hypotheses": [hypothesis.to_dict() for hypothesis in hypotheses],
            "answer_shot_id": hit.shot_id,
            "evidence_frame_idx": evidence_frame_idx,
            "submitted_keyframe_id": winning_keyframe_id,
            "submitted_frame_idx": submitted_frame,
            "confidence": confidence,
            "qa_runtime": runtime,
            "generations_used": budget.used if budget is not None else None,
            "generation_limit": budget.limit if budget is not None else None,
            "generation_limit_reached": budget_exhausted,
        }
    return ranked_hits, answer


def qa_pipeline(
    query_vi: str,
    top_k_shots: int = TOP_K_SHOTS_FOR_SLOTS,
    query_en: str | None = None,
    return_trace: bool = False,
    runtime_fingerprint: str | None = None,
) -> tuple[list[ShotHit], str] | tuple[list[ShotHit], str, dict[str, object]]:
    """Đóng băng mode và tạo generation budget riêng cho từng query Q&A."""
    mode = qa_inference_mode()
    mode_token = _qa_mode_ctx.set(mode)
    fingerprint_token = _qa_runtime_fingerprint_ctx.set(
        runtime_fingerprint or "<unset>"
    )
    full_query_token = _qa_full_query_hash_ctx.set(
        hashlib.sha256(query_vi.encode("utf-8")).hexdigest()
    )
    budget_token = None
    if mode == "two_stage":
        budget_token = _generation_budget_ctx.set(
            QAGenerationBudget(limit=QA_TWO_STAGE_MAX_GENERATIONS)
        )
    try:
        return _qa_pipeline_impl(query_vi, top_k_shots, query_en, return_trace)
    finally:
        if budget_token is not None:
            _generation_budget_ctx.reset(budget_token)
        _qa_full_query_hash_ctx.reset(full_query_token)
        _qa_runtime_fingerprint_ctx.reset(fingerprint_token)
        _qa_mode_ctx.reset(mode_token)


def _expand_within_video(
    video_id: str, query_vi: str, query_en: str | None, tried_shot_ids: set[str]
) -> list[ShotHit]:
    """Tìm THÊM shot ứng viên trong MỘT video cụ thể, dùng nguyên câu hỏi đầy đủ
    (còn từ khoá cụ thể, khác `event_vi` thuần thị giác) — xem VIDEO_EXPAND_SHOTS.

    Lọc bỏ shot đã thử ở vòng chính (`tried_shot_ids`) — không tốn lại 1 lượt LLM
    cho evidence đã biết là không đủ tin cậy.
    """
    hits = search(query_vi, query_en=query_en, top_k=VIDEO_EXPAND_SHOTS + len(tried_shot_ids),
                  group_by_shot=True, filter_video_id=video_id)
    out = []
    for r in hits:
        if r["shot_id"] is None or r["shot_id"] in tried_shot_ids:
            continue
        out.append(ShotHit(r["shot_id"], r["score"], r["keyframe_id"]))
        if len(out) >= VIDEO_EXPAND_SHOTS:
            break
    return out


@lru_cache(maxsize=1)
def _reverse_frame_map() -> dict[tuple[str, int], tuple[str, ...]]:
    """Reverse map frame tuyệt đối → keyframe_id; ưu tiên ID BTC dạng `#k`."""
    grouped: dict[tuple[str, int], set[str]] = {}
    for keyframe_id, frame_idx in load_frame_map().items():
        if "#" in keyframe_id:
            video_id = keyframe_id.split("#", 1)[0]
        elif "_" in keyframe_id:
            video_id = keyframe_id.rsplit("_", 1)[0]
        else:
            continue
        grouped.setdefault((video_id, int(frame_idx)), set()).add(keyframe_id)
    return {
        key: tuple(sorted(ids, key=lambda value: ("#k" not in value, value)))
        for key, ids in grouped.items()
    }


def _keyframe_id_for_frame(
    video_id: str,
    frame_idx: int,
    *,
    preferred: str | None = None,
) -> str:
    """Tra keyframe có frame tuyệt đối đúng bằng evidence; không suy tên/hậu tố."""
    fmap = load_frame_map()
    if preferred and fmap.get(preferred) == frame_idx:
        preferred_video = (
            preferred.split("#", 1)[0]
            if "#" in preferred else preferred.rsplit("_", 1)[0]
        )
        if preferred_video == video_id:
            return preferred
    candidates = _reverse_frame_map().get((video_id, int(frame_idx)), ())
    if not candidates:
        raise RuntimeError(
            f"frame evidence {video_id}:{frame_idx} không có keyframe tương ứng trong frame_map"
        )
    return candidates[0]


def _dua_len_dau(
    shots: list[ShotHit],
    i: int,
    *,
    winning_keyframe_id: str | None = None,
) -> list[ShotHit]:
    """Đưa phần tử thứ i lên đầu, GIỮ NGUYÊN thứ tự tương đối của phần còn lại.

    Không sửa `score`: allocator tự `sorted(hits, key=score, reverse=True)` nên
    đổi chỗ trong list là chưa đủ — nhưng bịa điểm cho shot thắng thì làm hỏng
    mọi thứ đọc `score` về sau (score_simulator, log phân tích). Thay vào đó gán
    lại điểm shot thắng = điểm cao nhất + một khoảng nhỏ, và ghi rõ trong log.
    """
    thang = shots[i]
    pinned = winning_keyframe_id or thang.best_keyframe_id
    if i == 0:
        if pinned == thang.best_keyframe_id:
            return shots
        return [ShotHit(thang.shot_id, thang.score, pinned)] + shots[1:]
    con_lai = shots[:i] + shots[i + 1:]
    diem_cao_nhat = max(s.score for s in shots)
    # +1e-6: đủ để thắng sorted() mà không làm biến dạng thang điểm RRF (~0.01-0.03)
    return [ShotHit(thang.shot_id, diem_cao_nhat + 1e-6, pinned)] + con_lai


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
