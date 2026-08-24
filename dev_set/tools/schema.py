from __future__ import annotations
from dataclasses import dataclass, field
from typing import Iterable, Literal, Protocol, Union

# Sử dụng Answer từ định dạng nộp chung của toàn repo
from data.config.submit_format import Answer


@dataclass(frozen=True)
class Query:
    query_id: str
    task_type: Literal["KIS", "QA", "TRAKE"]
    query_vi: str
    split: Literal["tune", "holdout", "dress25"]
    query_en: str | None = None
    n_events: int | None = None
    event_descs: list[str] | None = None

    def __post_init__(self):
        if self.task_type not in ("KIS", "QA", "TRAKE"):
            raise ValueError(f"task_type invalid: {self.task_type}")
        if self.split not in ("tune", "holdout", "dress25", "gen10", "gen2"):
            raise ValueError(f"split invalid: {self.split}")
        if self.task_type == "TRAKE":
            if isinstance(self.n_events, bool) or not isinstance(self.n_events, int) \
                    or self.n_events < 2:
                raise ValueError("TRAKE query must have integer n_events >= 2")
            if self.event_descs is not None:
                if not isinstance(self.event_descs, list) or any(
                    not isinstance(event, str) or not event.strip()
                    for event in self.event_descs
                ):
                    raise ValueError("TRAKE event_descs must be a list of non-empty strings")
                if len(self.event_descs) != self.n_events:
                    raise ValueError(
                        "TRAKE event_descs length must equal declared n_events"
                    )


@dataclass(frozen=True)
class GroundTruthKIS:
    query_id: str
    video_id: str
    frame_start: int
    frame_end: int
    verification_status: Literal["unknown", "verified"] = field(
        default="unknown", kw_only=True,
    )
    provenance: str | None = field(default=None, kw_only=True)
    verified_by: str | None = field(default=None, kw_only=True)
    verified_at: str | None = field(default=None, kw_only=True)

    def __post_init__(self):
        if self.frame_start > self.frame_end:
            raise ValueError(
                f"[{self.query_id}] frame_start ({self.frame_start}) > frame_end ({self.frame_end})"
            )
        if self.frame_start < 0:
            raise ValueError(f"[{self.query_id}] frame_start < 0")
        _validate_verification_metadata(
            self.query_id,
            self.verification_status,
            self.provenance,
            self.verified_by,
            self.verified_at,
        )


@dataclass(frozen=True)
class GroundTruthQA(GroundTruthKIS):
    answer_text: str
    answer_variants: list[str]

    def __post_init__(self):
        super().__post_init__()
        if not self.answer_text:
            raise ValueError(f"[{self.query_id}] QA must have answer_text")
        if not self.answer_variants or len(self.answer_variants) < 3:
            raise ValueError(f"[{self.query_id}] QA must have >= 3 answer_variants")


@dataclass(frozen=True)
class GroundTruthTRAKE:
    query_id: str
    video_id: str
    frames: list[dict]  # [{"start": int, "end": int, "desc": str}]
    verification_status: Literal["unknown", "verified"] = "unknown"
    provenance: str | None = None
    verified_by: str | None = None
    verified_at: str | None = None

    def __post_init__(self):
        if not self.frames:
            raise ValueError(f"[{self.query_id}] TRAKE must have at least 1 frame window")
        
        # Kiểm tra không chồng lấn và hợp lệ
        prev_end = -1
        for i, window in enumerate(self.frames):
            start = window.get("start")
            end = window.get("end")
            if start is None or end is None:
                raise ValueError(f"[{self.query_id}] TRAKE window missing start/end")
            if start > end:
                raise ValueError(f"[{self.query_id}] TRAKE window {i} start > end")
            if start <= prev_end:
                raise ValueError(f"[{self.query_id}] TRAKE window {i} overlaps or is unordered")
            prev_end = end
        _validate_verification_metadata(
            self.query_id,
            self.verification_status,
            self.provenance,
            self.verified_by,
            self.verified_at,
        )


GroundTruth = Union[GroundTruthKIS, GroundTruthQA, GroundTruthTRAKE]


class GroundTruthWithVerification(Protocol):
    """Tối thiểu metadata cần có để gate biết nhãn có được xác minh hay chưa."""

    query_id: str
    verification_status: str
    provenance: str | None
    verified_by: str | None
    verified_at: str | None


@dataclass(frozen=True)
class PromotionReadiness:
    """Kết quả kiểm GT trước promotion, giữ query chưa xác minh để audit."""

    unverified_query_ids: tuple[str, ...]
    missing_query_ids: tuple[str, ...] = ()

    @property
    def eligible(self) -> bool:
        return not self.unverified_query_ids and not self.missing_query_ids

    @property
    def message(self) -> str:
        if self.eligible:
            return "GT verification: đủ điều kiện promotion."
        problems = []
        if self.unverified_query_ids:
            problems.append(f"nhãn chưa verified: {', '.join(self.unverified_query_ids)}")
        if self.missing_query_ids:
            problems.append(f"thiếu GT: {', '.join(self.missing_query_ids)}")
        return (
            "GT verification: không đủ điều kiện promotion; "
            + "; ".join(problems)
        )


def assess_promotion_ground_truth(
    ground_truth: Iterable[GroundTruthWithVerification],
    *,
    expected_query_ids: Iterable[str] | None = None,
) -> PromotionReadiness:
    """Đánh giá GT cho promotion, không coi file legacy là đã xác minh.

    Input là các GT đã parse; output giữ danh sách query không `verified` để
    chế độ phân tích báo rõ thiếu provenance. Invariant: chỉ nhãn `verified`
    mới được gate promotion chấp nhận.
    """
    parsed_ground_truth = tuple(ground_truth)
    unverified = tuple(
        gt.query_id for gt in parsed_ground_truth if gt.verification_status != "verified"
    )
    parsed_query_ids = {gt.query_id for gt in parsed_ground_truth}
    missing = () if expected_query_ids is None else tuple(
        query_id for query_id in expected_query_ids if query_id not in parsed_query_ids
    )
    return PromotionReadiness(
        unverified_query_ids=unverified,
        missing_query_ids=missing,
    )


def require_promotion_ground_truth(
    ground_truth: Iterable[GroundTruthWithVerification],
    *,
    expected_query_ids: Iterable[str] | None = None,
) -> None:
    """Từ chối promotion nếu còn bất kỳ GT nào chưa được xác minh."""
    readiness = assess_promotion_ground_truth(
        ground_truth,
        expected_query_ids=expected_query_ids,
    )
    if not readiness.eligible:
        raise ValueError(readiness.message)


def _validate_verification_metadata(
    query_id: str,
    verification_status: str,
    provenance: str | None,
    verified_by: str | None,
    verified_at: str | None,
) -> None:
    """Kiểm metadata GT ngay lúc parse để trạng thái `verified` có audit trail."""
    if verification_status not in ("unknown", "verified"):
        raise ValueError(f"[{query_id}] verification_status invalid: {verification_status}")
    if verification_status != "verified":
        return
    for field_name, value in {
        "provenance": provenance,
        "verified_by": verified_by,
        "verified_at": verified_at,
    }.items():
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"[{query_id}] verified GT must have {field_name}")
