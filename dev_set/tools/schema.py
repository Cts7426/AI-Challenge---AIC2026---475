from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal, Union

# Sử dụng Answer từ định dạng nộp chung của toàn repo
from data.config.submit_format import Answer


@dataclass(frozen=True)
class Query:
    query_id: str
    task_type: Literal["KIS", "QA", "TRAKE"]
    query_vi: str
    split: Literal["tune", "holdout"]
    query_en: str | None = None
    n_events: int | None = None
    event_descs: list[str] | None = None

    def __post_init__(self):
        if self.task_type not in ("KIS", "QA", "TRAKE"):
            raise ValueError(f"task_type invalid: {self.task_type}")
        if self.split not in ("tune", "holdout"):
            raise ValueError(f"split invalid: {self.split}")
        if self.task_type == "TRAKE":
            if not self.n_events or self.n_events <= 0:
                raise ValueError("TRAKE query must have n_events > 0")


@dataclass(frozen=True)
class GroundTruthKIS:
    query_id: str
    video_id: str
    frame_start: int
    frame_end: int

    def __post_init__(self):
        if self.frame_start > self.frame_end:
            raise ValueError(
                f"[{self.query_id}] frame_start ({self.frame_start}) > frame_end ({self.frame_end})"
            )
        if self.frame_start < 0:
            raise ValueError(f"[{self.query_id}] frame_start < 0")


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


GroundTruth = Union[GroundTruthKIS, GroundTruthQA, GroundTruthTRAKE]
