"""Schema nhãn E01 độc lập evaluator cũ; pending không bao giờ giả là GT verified."""
from __future__ import annotations

from typing import Literal
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, model_validator
from data.config.evaluation_foundation import SCHEMA_VERSION, QA_NORMALIZATION_POLICY, QA_SEMANTIC_POLICY


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Window(StrictModel):
    start: int = Field(ge=0)
    end: int = Field(ge=0)

    @model_validator(mode="after")
    def ordered(self):
        if self.end < self.start:
            raise ValueError("Cửa sổ frame tuyệt đối phải có start <= end")
        return self


class Evidence(StrictModel):
    video_id: str = Field(min_length=1)
    keyframe_id: str = Field(min_length=1)
    frame_idx: int = Field(ge=0)
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    support: str = Field(min_length=1)


class Verification(StrictModel):
    status: Literal["pending", "verified", "rejected"] = "pending"
    verifier: str | None = None
    verified_at: str | None = None
    source_only_attestation: bool = False
    notes: str = ""


class Grouping(StrictModel):
    duplicate_group: str | None = None
    event_group: str | None = None
    review_status: Literal["pending", "verified"] = "pending"
    verifier: str | None = None
    reviewed_at: str | None = None
    prior_exposure_checked: bool = False
    prior_exposure_found: bool | None = None
    shared_frame_reviewed: bool = False
    shared_frame_explanation: str = ""
    notes: str = ""


class Event(StrictModel):
    description: str = Field(min_length=1)
    windows: list[Window] = Field(min_length=1)
    evidence_keys: list[str] = Field(min_length=1)
    support_status: Literal["evidence_backed", "ambiguous"]
    temporal_tolerance_frames: int = Field(default=0, ge=0)
    tolerance_justification: str = ""


class Label(StrictModel):
    windows: list[Window] = Field(default_factory=list)
    acceptable_answers: list[str] = Field(default_factory=list)
    exact_policy: str = QA_NORMALIZATION_POLICY
    semantic_policy: str = QA_SEMANTIC_POLICY
    answerability: Literal["answerable", "unanswerable", "pending"] = "pending"
    unanswerable_reason: str = ""
    events: list[Event] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    notes: str = ""


class Annotation(StrictModel):
    """Input bản ghi người duyệt; output schema chặt; frame chỉ là số tuyệt đối từ map."""
    schema_version: str = SCHEMA_VERSION
    query_id: str = Field(pattern=r"^E01_(VAL|HOLD)_(KIS|QA|TRAKE)_\d{2}$")
    task_type: Literal["KIS", "QA", "TRAKE"]
    split: Literal["validation", "sealed_heldout"]
    video_id: str = Field(min_length=1)
    query_text: str = ""
    source_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_version: str = Field(min_length=1)
    verification: Verification = Field(default_factory=Verification)
    grouping: Grouping = Field(default_factory=Grouping)
    label: Label = Field(default_factory=Label)

    @model_validator(mode="after")
    def validate_verified(self):
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("Schema version không được đổi ngầm")
        expected_prefix = "VAL" if self.split == "validation" else "HOLD"
        if not self.query_id.startswith(f"E01_{expected_prefix}_{self.task_type}_"):
            raise ValueError("Query ID không khớp split/task")
        v, label = self.verification, self.label
        if any(e.video_id != self.video_id for e in label.evidence):
            raise ValueError("Evidence sai target video")
        if v.status != "verified":
            return self
        if not (v.verifier and v.verifier.strip() and v.verified_at and v.source_only_attestation):
            raise ValueError("Verified cần người duyệt, ngày và xác nhận chỉ dùng nguồn gốc")
        if datetime.fromisoformat(v.verified_at).tzinfo is None:
            raise ValueError("verified_at cần timezone")
        if not self.query_text.strip() or not label.evidence:
            raise ValueError("Verified cần query và evidence thực")
        if self.task_type in ("KIS", "QA") and not label.windows:
            raise ValueError("KIS/QA cần cửa sổ/evidence region cố định")
        if self.task_type in ("KIS", "QA") and not any(
            w.start <= e.frame_idx <= w.end for w in label.windows for e in label.evidence
        ):
            raise ValueError("Cần reference frame nằm trong cửa sổ chấp nhận")
        if self.task_type == "QA":
            if label.exact_policy != QA_NORMALIZATION_POLICY or label.semantic_policy != QA_SEMANTIC_POLICY:
                raise ValueError("QA normalization policy phải khớp version đã đăng ký")
            if label.answerability == "pending":
                raise ValueError("QA cần quyết định answerability")
            if label.answerability == "answerable" and not all(a.strip() for a in label.acceptable_answers):
                raise ValueError("Không nhận answer form rỗng")
            if label.answerability == "answerable" and not label.acceptable_answers:
                raise ValueError("QA answerable cần answer forms")
            if label.answerability == "unanswerable" and (label.acceptable_answers or not label.unanswerable_reason.strip()):
                raise ValueError("QA unanswerable cần lý do, không có answer giả")
        if self.task_type == "TRAKE":
            if len(label.events) < 2:
                raise ValueError("TRAKE cần ít nhất hai sự kiện có thứ tự")
            evidence_keys = {e.keyframe_id for e in label.evidence}
            previous = -1
            for event in label.events:
                if event.support_status != "evidence_backed":
                    raise ValueError("Sự kiện ambiguous phải pending")
                if not set(event.evidence_keys) <= evidence_keys:
                    raise ValueError("TRAKE event thiếu evidence tương ứng")
                refs = [e for e in label.evidence if e.keyframe_id in event.evidence_keys]
                if not any(w.start <= e.frame_idx <= w.end for w in event.windows for e in refs):
                    raise ValueError("Event reference phải nằm trong event window")
                if event.temporal_tolerance_frames and not event.tolerance_justification.strip():
                    raise ValueError("Temporal tolerance cần lý do từ nguồn")
                first = min(w.start for w in event.windows)
                if first < previous:
                    raise ValueError("TRAKE event windows đảo thứ tự")
                previous = first
        return self
