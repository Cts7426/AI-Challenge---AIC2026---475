"""Băm canonical query/GT để score promotion không thể ghép nhầm dữ liệu."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from typing import Any, Mapping, Sequence


QUERY_IDENTITY_FIELDS = (
    "query_id", "task_type", "query_vi", "query_en", "event_descs", "n_events",
)


def canonical_sha256(value: Any) -> str:
    """Băm JSON canonical; output là SHA-256 lowercase ổn định."""
    raw = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _as_mapping(value: object) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    return {
        name: getattr(value, name)
        for name in QUERY_IDENTITY_FIELDS
        if hasattr(value, name)
    }


def query_record_sha256(query: object) -> str:
    """Băm đúng các field định nghĩa nội dung đề, không băm split/path runtime."""
    record = _as_mapping(query)
    return canonical_sha256({name: record.get(name) for name in QUERY_IDENTITY_FIELDS})


def query_set_sha256(rows: Sequence[object]) -> str:
    """Băm exact tập query theo ID/task/content, không phụ thuộc thứ tự file."""
    identities = []
    for value in rows:
        record = _as_mapping(value)
        # Manifest chứa nội dung query phải băm lại nội dung thật; không tin một
        # `query_sha256` tự khai có thể che việc sửa `query_vi`.
        query_sha = (
            query_record_sha256(record)
            if "query_vi" in record
            else record.get("query_sha256")
        )
        identities.append({
            "query_id": record.get("query_id"),
            "task_type": record.get("task_type"),
            "query_sha256": query_sha,
        })
    identities.sort(key=lambda row: str(row["query_id"]))
    return canonical_sha256(identities)


def ground_truth_record_sha256(ground_truth: object) -> str:
    """Băm toàn bộ GT đã parse, gồm verification trail của nhãn."""
    record = _as_mapping(ground_truth)
    return canonical_sha256(dict(record))


def ground_truth_set_sha256(by_query_sha256: Mapping[str, str]) -> str:
    """Băm map query_id -> GT hash để buộc artefact vào đúng bộ nhãn."""
    return canonical_sha256(dict(by_query_sha256))


def is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value.lower())
    )
