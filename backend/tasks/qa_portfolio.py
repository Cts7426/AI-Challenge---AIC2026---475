"""Cấp portfolio Q&A theo evidence: canonical mọi hypothesis trước, rồi mới phủ rộng."""

from __future__ import annotations

from backend.indexing.frame_map import load_frame_map
from backend.slot import ShotHit, allocate, shot_bounds
from backend.tasks.qa import QAHypothesis, is_valid_qa_answer
from data.config.qa_hypotheses import QA_HYPOTHESIS_ALTERNATIVES_PER_HYPOTHESIS
from data.config.submit_format import Answer


def _video_from_keyframe(keyframe_id: str) -> str:
    return keyframe_id.split("#", 1)[0] if "#" in keyframe_id else keyframe_id.rsplit("_", 1)[0]


def _rank_hypotheses(hypotheses: list[QAHypothesis]) -> list[QAHypothesis]:
    """Confidence thắng; input rank phá hòa để giữ provenance retrieval."""
    indexed = list(enumerate(hypotheses))
    indexed.sort(key=lambda pair: (-pair[1].confidence, pair[0], pair[1].shot_id))
    out: list[QAHypothesis] = []
    seen: set[tuple[str, int, str]] = set()
    for _, hypothesis in indexed:
        key = (
            hypothesis.video_id,
            hypothesis.evidence_frame_idx,
            " ".join(hypothesis.answer_text.casefold().split()),
        )
        if key not in seen:
            out.append(hypothesis)
            seen.add(key)
    return out


def _alternative_rows(hypothesis: QAHypothesis) -> list[Answer]:
    """Chỉ dùng keyframe thật trong đúng shot/evidence candidate."""
    video_id, start, end = shot_bounds(hypothesis.shot_id)
    if video_id != hypothesis.video_id:
        raise RuntimeError(
            f"hypothesis lệch video/shot: {hypothesis.video_id} != {video_id}"
        )
    candidates = [
        (int(frame_idx), keyframe_id)
        for keyframe_id, frame_idx in load_frame_map().items()
        if _video_from_keyframe(keyframe_id) == video_id
        and start <= int(frame_idx) <= end
        and int(frame_idx) != hypothesis.evidence_frame_idx
    ]
    candidates.sort(
        key=lambda item: (
            abs(item[0] - hypothesis.evidence_frame_idx), item[0], item[1]
        )
    )
    return [
        Answer(
            video_id=video_id,
            frame_ids=(frame_idx,),
            answer_text=hypothesis.answer_text,
            keyframe_id=keyframe_id,
        )
        for frame_idx, keyframe_id in candidates[:QA_HYPOTHESIS_ALTERNATIVES_PER_HYPOTHESIS]
    ]


def allocate_qa_portfolio(
    hypotheses: list[QAHypothesis],
    candidate_hits: list[ShotHit],
    *,
    total: int,
) -> list[Answer]:
    """Sinh đúng `total` dòng, không sentinel/duplicate và không partial success.

    Thứ tự: canonical của mọi hypothesis; một vòng alternatives evidence-specific;
    cuối cùng dùng answer mạnh nhất cho candidate retrieval chưa dùng. Canonical
    và alternatives chỉ lấy frame tuyệt đối từ frame_map, không suy hậu tố.
    """
    if total < 1:
        raise ValueError("total Q&A phải là số nguyên dương")
    ranked = _rank_hypotheses(hypotheses)
    if not ranked:
        raise RuntimeError("Q&A không có hypothesis hợp lệ để cấp portfolio")
    if len(ranked) > total:
        raise RuntimeError(
            f"total={total} nhỏ hơn {len(ranked)} canonical hypotheses; "
            "từ chối âm thầm bỏ evidence"
        )
    if any(not is_valid_qa_answer(item.answer_text) for item in ranked):
        raise RuntimeError("Q&A portfolio nhận sentinel answer")

    fmap = load_frame_map()
    rows: list[Answer] = []
    used: set[tuple[str, tuple[int, ...], str | None]] = set()

    def append(row: Answer) -> None:
        key = (row.video_id, row.frame_ids, row.answer_text)
        if key not in used and len(rows) < total:
            rows.append(row)
            used.add(key)

    # Vòng 1 bắt buộc: mỗi evidence có một canonical trước bất kỳ alternative nào.
    for hypothesis in ranked:
        if fmap.get(hypothesis.keyframe_id) != hypothesis.evidence_frame_idx:
            raise RuntimeError(
                f"canonical hypothesis không khớp frame_map: {hypothesis.keyframe_id}"
            )
        append(Answer(
            video_id=hypothesis.video_id,
            frame_ids=(hypothesis.evidence_frame_idx,),
            answer_text=hypothesis.answer_text,
            keyframe_id=hypothesis.keyframe_id,
        ))
    if len(rows) >= total:
        return rows

    # Vòng 2: round-robin đúng candidate/evidence, không để hypothesis mạnh độc chiếm.
    alternatives = [_alternative_rows(hypothesis) for hypothesis in ranked]
    depth = max((len(items) for items in alternatives), default=0)
    for index in range(depth):
        for items in alternatives:
            if index < len(items):
                append(items[index])
        if len(rows) >= total:
            return rows

    # Phần đuôi chỉ phủ candidate chưa dùng, dùng answer có support mạnh nhất.
    evidence_shots = {hypothesis.shot_id for hypothesis in ranked}
    tail_hits = [hit for hit in candidate_hits if hit.shot_id not in evidence_shots]
    if tail_hits:
        tail = allocate(
            tail_hits,
            "QA",
            answer_text=ranked[0].answer_text,
            total=total - len(rows),
        )
        for row in tail:
            append(row)
    if len(rows) != total:
        raise RuntimeError(
            f"Q&A portfolio chỉ tạo được {len(rows)}/{total}; từ chối partial success"
        )
    return rows
