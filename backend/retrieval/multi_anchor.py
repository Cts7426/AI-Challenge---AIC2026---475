"""Lập kế hoạch KIS nhiều anchor nhưng tái sử dụng nguyên vẹn search hiện có."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass
from typing import Literal

from backend.llm.adapter import llm
from backend.retrieval.query_understanding import count_clip_tokens, translate
from backend.retrieval.search import search
from data.config.multi_anchor import (
    COLOR_MARKER,
    COMPLEX_MARKERS,
    COMPLEX_MARKER_MIN,
    COUNT_CLASSIFIERS,
    ENABLED,
    MAX_ANCHORS,
    MAX_CLIP_TOKENS,
    ORDER_MARKER_PAIRS,
    ORDER_MARKERS,
    PER_ANCHOR_POOL,
    RRF_K,
    SHORT_QUERY_MAX_WORDS,
    TEMPORAL_BONUS,
    QUANTIFIER_TERMS,
)


@dataclass(frozen=True)
class QueryAnchor:
    """Một mô tả sự kiện được encode riêng; ordinal giữ thứ tự query gốc."""

    ordinal: int
    query_vi: str
    query_en: str | None
    clip_tokens: int | None = None


@dataclass(frozen=True)
class QueryPlan:
    """Kế hoạch immutable để trace/replay không bị caller sửa ngầm."""

    strategy: Literal["single", "multi"]
    query_vi: str
    query_en: str | None
    anchors: tuple[QueryAnchor, ...]
    ordered: bool = False
    fallback_reason: str | None = None

    def to_dict(self) -> dict:
        """Trả cấu trúc chỉ gồm scalar/list/dict, ghi thẳng được vào QueryRun."""
        return asdict(self)


ANCHOR_SCHEMA = {
    "type": "object",
    "properties": {
        "anchors": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": MAX_ANCHORS,
        }
    },
    "required": ["anchors"],
    "additionalProperties": False,
}


def _single_plan(query_vi: str, query_en: str | None, reason: str | None = None) -> QueryPlan:
    return QueryPlan(
        strategy="single",
        query_vi=query_vi,
        query_en=query_en,
        anchors=(QueryAnchor(1, query_vi, query_en),),
        fallback_reason=reason,
    )


def _needs_multiple(query_vi: str) -> bool:
    marker_count = sum(_marker_occurrences(query_vi, marker) for marker in COMPLEX_MARKERS)
    return len(query_vi.split()) > SHORT_QUERY_MAX_WORDS or marker_count >= COMPLEX_MARKER_MIN


def _is_ordered(query_vi: str) -> bool:
    """Chỉ bật khi có transition rõ hoặc đủ cặp boundary của nhiều sự kiện."""
    if any(_marker_occurrences(query_vi, marker) for marker in ORDER_MARKERS):
        return True
    return any(
        _marker_occurrences(query_vi, first) and _marker_occurrences(query_vi, last)
        for first, last in ORDER_MARKER_PAIRS
    )


def _content_tokens(text: str) -> tuple[str, ...]:
    """Token Unicode deterministic; bỏ punctuation nhưng giữ chữ số và dấu Việt."""
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return tuple(re.findall(r"\w+", normalized, flags=re.UNICODE))


def _marker_occurrences(text: str, marker: str) -> int:
    """Đếm marker theo token phrase nên dấu phẩy/chấm không làm mất match."""
    if marker in {";", "→"}:
        return text.count(marker)
    tokens = _content_tokens(text)
    marker_tokens = _content_tokens(marker)
    width = len(marker_tokens)
    if width == 0:
        return 0
    return sum(
        tokens[index:index + width] == marker_tokens
        for index in range(len(tokens) - width + 1)
    )


def _contains_token_sequence(tokens: tuple[str, ...], phrase: tuple[str, ...]) -> bool:
    """Kiểm phrase local liên tiếp, không phụ thuộc punctuation/case."""
    width = len(phrase)
    return width > 0 and any(
        tokens[index:index + width] == phrase
        for index in range(len(tokens) - width + 1)
    )


def _preserves_quantifier_context(
    anchor_tokens: tuple[str, ...], original_tokens: tuple[str, ...]
) -> bool:
    """Không cho tái gắn số lượng/thời lượng sang head noun khác."""
    quantifiers = sorted(
        (_content_tokens(term) for term in QUANTIFIER_TERMS),
        key=len,
        reverse=True,
    )
    classifiers = set(COUNT_CLASSIFIERS)
    for index, token in enumerate(anchor_tokens):
        matched = next(
            (
                phrase for phrase in quantifiers
                if anchor_tokens[index:index + len(phrase)] == phrase
            ),
            None,
        )
        if matched is None and not token.isdigit():
            continue
        width = len(matched) if matched is not None else 1
        end = index + width
        context_end = end
        if end < len(anchor_tokens):
            context_end += 1
            if anchor_tokens[end] in classifiers and context_end < len(anchor_tokens):
                context_end += 1
        context = anchor_tokens[index:context_end]
        if not _contains_token_sequence(original_tokens, context):
            return False
    return True


def _preserves_color_context(
    anchor_tokens: tuple[str, ...], original_tokens: tuple[str, ...]
) -> bool:
    """Giữ màu cạnh đúng head noun mà không dùng danh sách tên màu đóng."""
    marker = COLOR_MARKER.casefold()
    declared_colors = {
        tokens[index + 1]
        for tokens in (original_tokens, anchor_tokens)
        for index, token in enumerate(tokens[:-1])
        if token == marker
    }
    for index, token in enumerate(anchor_tokens):
        if token not in declared_colors:
            continue
        if len(anchor_tokens) == 1:
            context = (token,)
        elif index == 0:
            context = anchor_tokens[:2]
        elif anchor_tokens[index - 1] == marker and index >= 2:
            context = anchor_tokens[index - 2:index + 1]
        else:
            context = anchor_tokens[index - 1:index + 1]
        if not _contains_token_sequence(original_tokens, context):
            return False
    return True


def _is_faithful(anchor_vi: str, original_vi: str) -> bool:
    """Fail closed: anchor chỉ được sắp xếp/tái dùng token có trong query gốc.

    So theo tập token để việc tách anchor được lặp lại chủ thể và đổi trật tự từ
    nhỏ, nhưng mọi màu/count/modifier mới (kể cả ngoài vocabulary biết trước)
    đều làm plan invalid.
    """
    anchor_sequence = _content_tokens(anchor_vi)
    original_sequence = _content_tokens(original_vi)
    anchor_tokens = set(anchor_sequence)
    original_tokens = set(original_sequence)
    return (
        bool(anchor_tokens)
        and anchor_tokens <= original_tokens
        and _preserves_quantifier_context(anchor_sequence, original_sequence)
        and _preserves_color_context(anchor_sequence, original_sequence)
    )


def _validated_anchors(payload: object, query_vi: str) -> list[str] | None:
    """Fail closed toàn plan nếu schema, uniqueness hay fidelity sai."""
    if (
        not isinstance(payload, dict)
        or set(payload) != {"anchors"}
        or not isinstance(payload.get("anchors"), list)
    ):
        return None
    raw_anchors = payload["anchors"]
    if len(raw_anchors) > MAX_ANCHORS:
        return None
    validated: list[str] = []
    seen: set[str] = set()
    for raw_anchor in raw_anchors:
        if not isinstance(raw_anchor, str):
            return None
        anchor = " ".join(raw_anchor.split())
        canonical = anchor.casefold()
        if not anchor or canonical in seen or not _is_faithful(anchor, query_vi):
            return None
        seen.add(canonical)
        validated.append(anchor)
    return validated


def plan_query(query_vi: str, query_en: str | None = None) -> QueryPlan:
    """Tách query phức tạp; mọi lỗi planner phải quay lại đúng single path cũ."""
    if not ENABLED or not _needs_multiple(query_vi):
        return _single_plan(query_vi, query_en)
    try:
        raw = llm(
            "Split the Vietnamese video-moment description into at most "
            f"{MAX_ANCHORS} short Vietnamese event anchors in original order. "
            "Use only details explicitly present in the original: never add colors, "
            "numbers, counts, objects, places, times or actions. Return JSON only.\n\n"
            f"Vietnamese description: {query_vi}",
            json_schema=ANCHOR_SCHEMA,
            max_tokens=384,
        )
        anchors_vi = _validated_anchors(json.loads(raw), query_vi)
    except Exception:
        return _single_plan(query_vi, query_en, "planner_error")

    if anchors_vi is None or len(anchors_vi) < 2:
        return _single_plan(query_vi, query_en, "invalid_anchors")

    anchors: list[QueryAnchor] = []
    try:
        for ordinal, anchor_vi in enumerate(anchors_vi, 1):
            translated = translate(anchor_vi)
            if not isinstance(translated, str) or not translated.strip():
                return _single_plan(query_vi, query_en, "translation_error")
            anchor_en = translated.strip()
            tokens = count_clip_tokens(anchor_en)
            if tokens > MAX_CLIP_TOKENS:
                return _single_plan(query_vi, query_en, "token_limit")
            anchors.append(QueryAnchor(ordinal, anchor_vi, anchor_en, tokens))
    except Exception:
        return _single_plan(query_vi, query_en, "translation_error")

    return QueryPlan(
        strategy="multi",
        query_vi=query_vi,
        query_en=query_en,
        anchors=tuple(anchors),
        ordered=_is_ordered(query_vi),
    )


def search_multi(plan: QueryPlan, top_k: int = 100) -> list[dict]:
    """Search từng anchor rồi outer-RRF theo shot, không chép logic nhánh search."""
    if plan.strategy == "single":
        return search(
            plan.query_vi,
            query_en=plan.query_en,
            top_k=top_k,
            group_by_shot=True,
        )

    occurrences: dict[str, list[tuple[QueryAnchor, int, dict]]] = {}
    best_video_timestamps: dict[str, dict[int, int | None]] = {}
    for anchor in plan.anchors:
        rows = search(
            anchor.query_vi,
            query_en=anchor.query_en,
            top_k=PER_ANCHOR_POOL,
            group_by_shot=True,
        )
        seen_videos: set[str] = set()
        for rank, row in enumerate(rows, 1):
            video_id = str(row.get("video_id") or "")
            if video_id and video_id not in seen_videos:
                best_video_timestamps.setdefault(video_id, {})[anchor.ordinal] = row.get(
                    "timestamp_ms"
                )
                seen_videos.add(video_id)
            shot_id = row.get("shot_id")
            keyframe_id = row.get("keyframe_id")
            # clip_kf_map vắng vẫn không được làm mất ứng viên: keyframe là khóa
            # deterministic tạm thời, còn khi có map thì luôn gom đúng shot_id.
            group_key = (
                f"shot:{shot_id}" if shot_id is not None else f"keyframe:{keyframe_id}"
            )
            occurrences.setdefault(group_key, []).append((anchor, rank, dict(row)))

    expected_ordinals = {anchor.ordinal for anchor in plan.anchors}
    ordered_videos: set[str] = set()
    if plan.ordered:
        for video_id, timestamps_by_anchor in best_video_timestamps.items():
            if set(timestamps_by_anchor) != expected_ordinals:
                continue
            timestamps = [timestamps_by_anchor[ordinal] for ordinal in sorted(expected_ordinals)]
            if all(timestamp is not None for timestamp in timestamps) and all(
                left <= right for left, right in zip(timestamps, timestamps[1:])
            ):
                ordered_videos.add(video_id)

    query_anchors = [asdict(anchor) for anchor in plan.anchors]
    fused: list[dict] = []
    for group_rows in occurrences.values():
        # Representative ưu tiên metadata keyframe/frame đầy đủ nhất để allocator
        # không nhận row fused bị khuyết; sau đó mới xét rank và keyframe_id.
        def representative_key(item: tuple[QueryAnchor, int, dict]) -> tuple:
            _, rank, row = item
            completeness = sum(
                row.get(field) is not None
                for field in ("keyframe_id", "frame_idx", "timestamp_ms", "shot_id")
            )
            return (-completeness, rank, str(row.get("keyframe_id") or ""))

        _, _, representative = min(group_rows, key=representative_key)
        anchor_ranks: dict[str, int] = {}
        for anchor, rank, _ in group_rows:
            name = f"anchor_{anchor.ordinal}"
            anchor_ranks[name] = min(rank, anchor_ranks.get(name, rank))
        anchor_contributions = {
            name: 1.0 / (RRF_K + rank) for name, rank in anchor_ranks.items()
        }
        temporal_match = str(representative.get("video_id") or "") in ordered_videos
        score = sum(anchor_contributions.values())
        if temporal_match:
            score *= TEMPORAL_BONUS

        fused_row = dict(representative)
        fused_row.update({
            "score": score,
            "anchor_ranks": anchor_ranks,
            "anchor_contributions": anchor_contributions,
            "temporal_order_match": temporal_match,
            "query_anchors": query_anchors,
            # Alias tương thích QueryRun/source trace hiện hành; đây là rank và
            # contribution của OUTER fusion, không phải nhánh retrieval bên trong.
            "ranks": dict(anchor_ranks),
            "contrib": dict(anchor_contributions),
        })
        fused.append(fused_row)

    fused.sort(key=lambda row: (
        -float(row["score"]),
        str(row.get("video_id") or ""),
        str(row.get("shot_id") or ""),
        row.get("timestamp_ms") if row.get("timestamp_ms") is not None else float("inf"),
        str(row.get("keyframe_id") or ""),
    ))
    return fused[:top_k]
