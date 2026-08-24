"""Chốt batch/receipt release theo kiểu fail-closed, không tự suy evidence.

Module chỉ đọc QueryRun trace, cache và artefact đã có. Nó không gọi retrieval,
LLM hay tự ghép frame; ZIP writer chỉ được gọi sau khi mọi gate đầu vào đã sạch.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from backend.export.exporter import Issue, QuerySubmission, write_submission_zip
from backend.tasks.runner import runtime_fingerprint, runtime_manifest
from data.config.release_gate import (
    PROMOTION_SCORER_POLICY,
    RELEASE_CONFIG_SNAPSHOT_SCHEMA_VERSION,
    RELEASE_EVIDENCE_CACHE_MANIFEST_SCHEMA_VERSION,
    RELEASE_RECEIPT_SCHEMA_VERSION,
    PROMOTION_SCORER_CONTRACT,
)


@dataclass(frozen=True)
class ReleaseBatchResult:
    eligible: bool
    reasons: tuple[dict[str, Any], ...]
    runtime_fingerprint: str | None
    trace_sha256: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "eligible": self.eligible,
            "reasons": [dict(reason) for reason in self.reasons],
            "runtime_fingerprint": self.runtime_fingerprint,
            "trace_sha256": self.trace_sha256,
        }


class ReleaseBlocked(RuntimeError):
    """Batch/artefact không đủ điều kiện nộp; caller phải trả nonzero."""

    def __init__(self, message: str, *, reasons: Sequence[Mapping[str, Any]] = ()):
        super().__init__(message)
        self.reasons = tuple(dict(reason) for reason in reasons)


def _reason(code: str, message: str, **details: Any) -> dict[str, Any]:
    return {"code": code, "message": message, **details}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value.lower())
    )


def promotion_audit_is_valid(audit: Mapping[str, Any]) -> bool:
    """Xác minh cả contract và checksum, không chỉ tin cờ `eligible` tự khai."""
    audit_hash = audit.get("audit_sha256")
    input_sha256 = audit.get("input_sha256")
    expected_inputs = {
        "holdout_manifest", "regression_manifest", "holdout_scores",
        "regression_baseline", "regression_current",
    }
    input_hashes_valid = (
        isinstance(input_sha256, Mapping)
        and set(input_sha256) == expected_inputs
        and all(
            _is_sha256(value)
            for value in input_sha256.values()
        )
    )
    if (
        audit.get("eligible") is not True
        or audit.get("status") != "ELIGIBLE"
        or audit.get("scorer_contract") != PROMOTION_SCORER_CONTRACT
        or not _is_sha256(audit_hash)
        or not _is_sha256(audit.get("current_runtime_fingerprint"))
        or audit.get("scorer_policy") != PROMOTION_SCORER_POLICY
        or not _is_sha256(audit.get("scorer_source_sha256"))
        or not input_hashes_valid
    ):
        return False
    unsigned = {key: value for key, value in audit.items() if key != "audit_sha256"}
    canonical = json.dumps(
        unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return audit_hash.lower() == expected


def _current_scorer_source_sha256() -> str:
    """Băm đúng scorer source hiện tại để audit cũ không mở khóa code mới."""
    root = Path(__file__).resolve().parents[2]
    return _sha256_file(root / "dev_set" / "tools" / "scoring.py")


def release_context_reasons(
    audit: Mapping[str, Any], *, scorer_policy: str,
) -> tuple[dict[str, Any], ...]:
    """So runtime/scorer hiện chạy với contract đã promotion."""
    reasons: list[dict[str, Any]] = []
    current_runtime = runtime_fingerprint()
    if audit.get("current_runtime_fingerprint") != current_runtime:
        reasons.append(_reason(
            "promotion_runtime_mismatch",
            "runtime release khác runtime đã qua promotion",
            promoted=audit.get("current_runtime_fingerprint"), current=current_runtime,
        ))
    current_scorer_source = _current_scorer_source_sha256()
    if audit.get("scorer_source_sha256") != current_scorer_source:
        reasons.append(_reason(
            "promotion_scorer_source_mismatch",
            "scorer source hiện tại khác source đã qua promotion",
        ))
    if audit.get("scorer_policy") != scorer_policy:
        reasons.append(_reason(
            "promotion_scorer_policy_mismatch",
            "scorer policy release khác policy đã qua promotion",
            promoted=audit.get("scorer_policy"), current=scorer_policy,
        ))
    return tuple(reasons)


def _atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temp.write_bytes(_canonical_bytes(value))
        temp.replace(path)
    finally:
        if temp.exists():
            temp.unlink()


def _issue_dict(issue: Issue | Mapping[str, Any] | object) -> dict[str, Any]:
    if isinstance(issue, Issue):
        return {
            "rule": issue.rule,
            "message": issue.message,
            "query_id": issue.query_id,
            "position": issue.position,
        }
    if isinstance(issue, Mapping):
        return dict(issue)
    return {"rule": "unknown", "message": str(issue)}


def _latest_trace_by_query(traces: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    latest: dict[str, Mapping[str, Any]] = {}
    for trace in traces:
        query_id = trace.get("query_id")
        if isinstance(query_id, str) and query_id:
            latest[query_id] = trace
    return latest


def _valid_hypothesis(hypothesis: Mapping[str, Any]) -> bool:
    required_strings = (
        "answer_text", "video_id", "shot_id", "keyframe_id",
        "evidence_hash", "provenance",
    )
    if any(not isinstance(hypothesis.get(name), str)
           or not str(hypothesis[name]).strip() for name in required_strings):
        return False
    frame_idx = hypothesis.get("evidence_frame_idx")
    if isinstance(frame_idx, bool) or not isinstance(frame_idx, int) or frame_idx < 0:
        return False
    return True


def _hypothesis_has_canonical_answer(
    hypothesis: Mapping[str, Any], answers: object,
) -> bool:
    if not isinstance(answers, list):
        return False
    for answer in answers:
        if not isinstance(answer, Mapping):
            continue
        frames = answer.get("frame_ids")
        if (
            answer.get("video_id") == hypothesis.get("video_id")
            and answer.get("answer_text") == hypothesis.get("answer_text")
            and answer.get("keyframe_id") == hypothesis.get("keyframe_id")
            and isinstance(frames, list)
            and hypothesis.get("evidence_frame_idx") in frames
        ):
            return True
    return False


def _text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _qa_query_identity(
    query: Mapping[str, Any], trace: Mapping[str, Any],
) -> tuple[str, str] | None:
    """Dựng đúng hai query hash mà `qa.py` ghi vào inference cache."""
    full_query = query.get("query_vi")
    if not isinstance(full_query, str) or not full_query:
        return None
    question: object = None
    qa_trace = trace.get("qa_trace")
    if isinstance(qa_trace, Mapping):
        question = qa_trace.get("question_vi")
    query_plan = trace.get("query_plan")
    if (not isinstance(question, str) or not question) and isinstance(
        query_plan, Mapping
    ):
        question = query_plan.get("question_vi")
    if not isinstance(question, str) or not question:
        question = full_query
    return _text_sha256(question), _text_sha256(full_query)


def _parse_trace_bytes(raw: bytes) -> list[dict[str, Any]]:
    """Parse đúng byte snapshot sẽ được băm vào receipt."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ReleaseBlocked(f"trace không phải UTF-8: {error}") from error
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise ReleaseBlocked(f"trace hỏng dòng {line_no}: {error}") from error
        if not isinstance(row, dict):
            raise ReleaseBlocked(f"trace dòng {line_no} không phải object")
        rows.append(row)
    return rows


def assess_release_batch(
    *,
    queries: Sequence[Mapping[str, Any]],
    traces: Sequence[Mapping[str, Any]],
    validator_issues: Sequence[Issue | Mapping[str, Any] | object],
    trace_path: Path,
    cache_manifest: Mapping[str, Any],
) -> ReleaseBatchResult:
    """Kiểm full batch trước ZIP; không nhận success bán phần hoặc cache mơ hồ."""
    reasons: list[dict[str, Any]] = []
    trace_sha256: str | None = None
    gated_traces = list(traces)
    if not trace_path.is_file():
        reasons.append(_reason("trace_missing", f"không thấy trace {trace_path}"))
    else:
        try:
            trace_bytes = trace_path.read_bytes()
            disk_traces = _parse_trace_bytes(trace_bytes)
            trace_sha256 = hashlib.sha256(trace_bytes).hexdigest()
            if disk_traces != list(traces):
                reasons.append(_reason(
                    "trace_content_mismatch",
                    "trace trong RAM khác byte snapshot sẽ ghi vào receipt",
                ))
            gated_traces = disk_traces
        except (OSError, ReleaseBlocked) as error:
            reasons.append(_reason("trace_invalid", str(error)))
            gated_traces = []

    query_ids = [str(query.get("query_id") or "") for query in queries]
    if not query_ids or any(not query_id for query_id in query_ids) \
            or len(set(query_ids)) != len(query_ids):
        reasons.append(_reason(
            "query_manifest", "query manifest phải có query_id duy nhất, không rỗng",
        ))

    latest = _latest_trace_by_query(gated_traces)
    expected, actual = set(query_ids), set(latest)
    if actual != expected:
        reasons.append(_reason(
            "trace_query_ids", "trace không khớp full batch",
            missing=sorted(expected - actual), unexpected=sorted(actual - expected),
        ))

    cache_entries = cache_manifest.get("entries") if isinstance(cache_manifest, Mapping) else None
    has_qa = any(query.get("task_type") == "QA" for query in queries)
    if has_qa and (not isinstance(cache_entries, list) or not cache_entries):
        reasons.append(_reason(
            "evidence_cache_missing", "batch có QA nhưng cache manifest rỗng/thiếu",
        ))

    fingerprints: set[str] = set()
    for query in queries:
        query_id = str(query.get("query_id") or "")
        trace = latest.get(query_id)
        if trace is None:
            continue
        if trace.get("status") != "success" or trace.get("retryable") is True:
            reasons.append(_reason(
                "query_not_success", f"{query_id} failed/retryable",
                query_id=query_id, status=trace.get("status"),
                retryable=bool(trace.get("retryable")),
            ))
        fingerprint = trace.get("runtime_fingerprint")
        if isinstance(fingerprint, str) and fingerprint.strip():
            fingerprints.add(fingerprint)
        else:
            reasons.append(_reason(
                "runtime_fingerprint_missing", f"{query_id} thiếu runtime fingerprint",
                query_id=query_id,
            ))

        if query.get("task_type") != "QA":
            continue
        query_identity = _qa_query_identity(query, trace)
        if query_identity is None:
            reasons.append(_reason(
                "qa_query_identity_missing", f"{query_id} thiếu query text để đối chiếu cache",
                query_id=query_id,
            ))
            continue
        query_sha256, full_query_sha256 = query_identity
        hypotheses = trace.get("qa_hypotheses")
        if not isinstance(hypotheses, list) or not hypotheses:
            reasons.append(_reason(
                "qa_hypotheses_missing", f"{query_id} không có hypothesis evidence",
                query_id=query_id,
            ))
            continue
        for index, hypothesis in enumerate(hypotheses):
            if not isinstance(hypothesis, Mapping) or not _valid_hypothesis(hypothesis):
                reasons.append(_reason(
                    "qa_evidence_invalid", f"{query_id} hypothesis {index} sai evidence",
                    query_id=query_id, hypothesis_index=index,
                ))
                continue
            if not _hypothesis_has_canonical_answer(hypothesis, trace.get("answers")):
                reasons.append(_reason(
                    "qa_evidence_not_pinned",
                    f"{query_id} hypothesis {index} không có canonical answer đúng frame/keyframe",
                    query_id=query_id, hypothesis_index=index,
                ))
            cache_match = (
                isinstance(cache_entries, list)
                and any(
                    isinstance(entry, Mapping)
                    and entry.get("parse_status") == "valid"
                    and entry.get("evidence_digest") == hypothesis.get("evidence_hash")
                    and entry.get("runtime_fingerprint") == fingerprint
                    and entry.get("query_sha256") == query_sha256
                    and entry.get("full_query_sha256") == full_query_sha256
                    for entry in cache_entries
                )
            )
            if not cache_match:
                reasons.append(_reason(
                    "qa_evidence_cache_mismatch",
                    f"{query_id} hypothesis {index} không có inference cache cùng evidence/runtime",
                    query_id=query_id, hypothesis_index=index,
                ))

    runtime_fingerprint: str | None = next(iter(fingerprints)) if len(fingerprints) == 1 else None
    if len(fingerprints) > 1:
        reasons.append(_reason(
            "runtime_fingerprint_mixed", "batch trộn nhiều runtime fingerprint",
            fingerprints=sorted(fingerprints),
        ))
    if validator_issues:
        reasons.append(_reason(
            "validator_failure", "validator từ chối submission trước khi ghi ZIP",
            issues=[_issue_dict(issue) for issue in validator_issues],
        ))
    return ReleaseBatchResult(
        eligible=not reasons,
        reasons=tuple(reasons),
        runtime_fingerprint=runtime_fingerprint,
        trace_sha256=trace_sha256,
    )


def build_evidence_cache_manifest(cache_dir: Path) -> dict[str, Any]:
    """Băm từng cache JSON; không chép output/model secret vào receipt."""
    entries: list[dict[str, Any]] = []
    if cache_dir.is_dir():
        for path in sorted(cache_dir.glob("*.json"), key=lambda item: item.name):
            record: Mapping[str, Any] = {}
            try:
                parsed = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(parsed, Mapping):
                    record = parsed
            except (OSError, json.JSONDecodeError):
                # File hỏng vẫn vào manifest với parse_status để gate/review thấy,
                # không im lặng bỏ nó khỏi provenance.
                pass
            identity = record.get("identity") if isinstance(record.get("identity"), Mapping) else {}
            entries.append({
                "path": path.relative_to(cache_dir).as_posix(),
                "sha256": _sha256_file(path),
                "parse_status": "valid" if identity else "invalid",
                "query_sha256": identity.get("query_sha256"),
                "full_query_sha256": identity.get("full_query_sha256"),
                "evidence_digest": identity.get("evidence_digest"),
                "runtime_fingerprint": identity.get("runtime_fingerprint"),
            })
    return {
        "schema_version": RELEASE_EVIDENCE_CACHE_MANIFEST_SCHEMA_VERSION,
        "cache_dir": cache_dir.as_posix(),
        "entries": entries,
    }


def write_evidence_cache_manifest(cache_dir: Path, output_path: Path) -> dict[str, Any]:
    manifest = build_evidence_cache_manifest(cache_dir)
    _atomic_write_json(output_path, manifest)
    return manifest


def capture_config_snapshot() -> dict[str, Any]:
    """Lưu đầy đủ text config (không phải env/.env), sort để hash ổn định."""
    root = Path(__file__).resolve().parents[2]
    return {
        "schema_version": RELEASE_CONFIG_SNAPSHOT_SCHEMA_VERSION,
        "files": {
            path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
            for path in sorted((root / "data" / "config").glob("*.py"))
        },
        "runtime_manifest": runtime_manifest(),
    }


def load_trace_jsonl(path: Path) -> list[dict[str, Any]]:
    """Đọc trace append-only; dòng cuối của cùng query là trạng thái hiện hành."""
    if not path.is_file():
        return []
    try:
        return _parse_trace_bytes(path.read_bytes())
    except OSError as error:
        raise ReleaseBlocked(f"không đọc được trace: {error}") from error


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _path_receipt(path: Path) -> str:
    return path.resolve().as_posix()


def create_release_package(
    *,
    queries: Sequence[Mapping[str, Any]],
    traces: Sequence[Mapping[str, Any]],
    submissions: list[QuerySubmission],
    out_dir: Path,
    trace_path: Path,
    evidence_cache_manifest_path: Path,
    evidence_cache_manifest: Mapping[str, Any],
    validator_issues: Sequence[Issue | Mapping[str, Any] | object],
    promotion_audit: Mapping[str, Any],
    query_manifest_path: Path,
    gt_manifest_path: Path | None,
    scorer_policy: str,
    submission_policy: str,
    reproduction_command: str,
    write_zip: Callable[..., tuple[Path, list[Issue]]] = write_submission_zip,
    zip_name: str = "submission.zip",
    expect_answers: int = 100,
    expected_n: dict[str, int] | None = None,
) -> Path:
    """Ghi ZIP rồi receipt atomic; mọi failure trước writer không để ZIP partial."""
    if not promotion_audit_is_valid(promotion_audit):
        reasons = (_reason(
            "promotion_not_eligible", "promotion audit chưa ELIGIBLE/đủ contract/hash",
            status=promotion_audit.get("status"),
        ),)
        raise ReleaseBlocked("promotion gate chưa đạt", reasons=reasons)
    context_reasons = release_context_reasons(
        promotion_audit, scorer_policy=scorer_policy,
    )
    if context_reasons:
        raise ReleaseBlocked(
            "runtime/scorer release khác promotion audit", reasons=context_reasons,
        )
    if not evidence_cache_manifest_path.is_file():
        raise ReleaseBlocked(
            "evidence cache manifest chưa được ghi",
            reasons=(_reason("evidence_cache_manifest_missing", str(evidence_cache_manifest_path)),),
        )
    try:
        stored_cache_manifest = json.loads(
            evidence_cache_manifest_path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as error:
        raise ReleaseBlocked(f"evidence cache manifest hỏng: {error}") from error
    if stored_cache_manifest != evidence_cache_manifest:
        raise ReleaseBlocked(
            "cache manifest trên đĩa khác object đã gate",
            reasons=(_reason("cache_manifest_mismatch", "cache manifest không đồng nhất"),),
        )

    expected_task_of = {
        str(query.get("query_id") or ""): str(query.get("task_type") or "")
        for query in queries
    }
    submission_ids = [submission.query_id for submission in submissions]
    submission_task_of = {submission.query_id: submission.task_type for submission in submissions}
    if (
        len(submission_ids) != len(set(submission_ids))
        or set(submission_ids) != set(expected_task_of)
        or any(submission_task_of.get(query_id) != task_type
               for query_id, task_type in expected_task_of.items())
    ):
        raise ReleaseBlocked(
            "submission không khớp toàn bộ query manifest",
            reasons=(_reason(
                "submission_query_ids", "submission thiếu/thừa/trùng hoặc sai task_type",
                missing=sorted(set(expected_task_of) - set(submission_ids)),
                unexpected=sorted(set(submission_ids) - set(expected_task_of)),
            ),),
        )

    batch = assess_release_batch(
        queries=queries,
        traces=traces,
        validator_issues=validator_issues,
        trace_path=trace_path,
        cache_manifest=evidence_cache_manifest,
    )
    if not batch.eligible:
        raise ReleaseBlocked("release batch chưa đủ điều kiện", reasons=batch.reasons)
    if batch.runtime_fingerprint != promotion_audit.get("current_runtime_fingerprint"):
        raise ReleaseBlocked(
            "runtime batch khác promotion audit",
            reasons=(_reason(
                "batch_runtime_mismatch",
                "fingerprint trong trace khác fingerprint đã promotion",
                promoted=promotion_audit.get("current_runtime_fingerprint"),
                batch=batch.runtime_fingerprint,
            ),),
        )
    if not query_manifest_path.is_file():
        raise ReleaseBlocked(
            "query manifest không tồn tại",
            reasons=(_reason("query_manifest_missing", str(query_manifest_path)),),
        )
    if gt_manifest_path is not None and not gt_manifest_path.is_file():
        raise ReleaseBlocked(
            "GT manifest không tồn tại",
            reasons=(_reason("gt_manifest_missing", str(gt_manifest_path)),),
        )
    upper_command = reproduction_command.upper()
    if "API_KEY=" in upper_command or "SECRET=" in upper_command or "TOKEN=" in upper_command:
        raise ReleaseBlocked("reproduction command có vẻ chứa secret")

    commit = _git_commit()
    if not commit or commit == "unknown":
        raise ReleaseBlocked(
            "không xác định được commit; từ chối tạo release receipt",
            reasons=(_reason("commit_unknown", "git commit không xác định"),),
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    config_snapshot_path = out_dir / "release_config_snapshot.json"
    _atomic_write_json(config_snapshot_path, capture_config_snapshot())

    zip_path, post_write_issues = write_zip(
        submissions,
        out_dir,
        zip_name=zip_name,
        expect_answers=expect_answers,
        expected_n=expected_n,
    )
    if post_write_issues:
        raise ReleaseBlocked(
            "ZIP vừa ghi không qua validator; không tạo receipt",
            reasons=(_reason(
                "zip_validator_failure", "ZIP không sử dụng được",
                issues=[_issue_dict(issue) for issue in post_write_issues],
            ),),
        )

    if batch.trace_sha256 is None or _sha256_file(trace_path) != batch.trace_sha256:
        raise ReleaseBlocked(
            "trace thay đổi sau khi gate; không tạo receipt",
            reasons=(_reason(
                "trace_changed_after_gate",
                "trace trên đĩa không còn là snapshot đã được gate",
            ),),
        )

    gt_manifest = (
        {"status": "not_applicable"}
        if gt_manifest_path is None
        else {
            "status": "provided",
            "path": _path_receipt(gt_manifest_path),
            "sha256": _sha256_file(gt_manifest_path),
        }
    )
    receipt = {
        "schema_version": RELEASE_RECEIPT_SCHEMA_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "commit": commit,
        "runtime_fingerprint": promotion_audit["current_runtime_fingerprint"],
        "config_snapshot": {
            "path": _path_receipt(config_snapshot_path),
            "sha256": _sha256_file(config_snapshot_path),
        },
        "trace": {
            "path": _path_receipt(trace_path),
            "sha256": batch.trace_sha256,
        },
        "evidence_cache_manifest": {
            "path": _path_receipt(evidence_cache_manifest_path),
            "sha256": _sha256_file(evidence_cache_manifest_path),
        },
        "scorer_policy": promotion_audit["scorer_policy"],
        "scorer_contract": PROMOTION_SCORER_CONTRACT,
        "scorer_source_sha256": promotion_audit["scorer_source_sha256"],
        "submission_policy": submission_policy,
        "promotion_audit": {
            "status": promotion_audit.get("status"),
            "audit_sha256": promotion_audit.get("audit_sha256"),
        },
        "query_manifest": {
            "path": _path_receipt(query_manifest_path),
            "sha256": _sha256_file(query_manifest_path),
        },
        "gt_manifest": gt_manifest,
        "zip": {"path": _path_receipt(zip_path), "sha256": _sha256_file(zip_path)},
        "validator": {"status": "valid", "issues": []},
        "reproduction_command": reproduction_command,
    }
    receipt_path = zip_path.with_suffix(".receipt.json")
    _atomic_write_json(receipt_path, receipt)
    return receipt_path
