# scripts/manual_qa_override.py — thêm Q&A đã được operator xác minh vào checkpoint.
#
# Helper này chỉ dùng khi pipeline không suy ra answer nhưng operator có ảnh bằng
# chứng và frame-map canonical. Mặc định là dry-run; --apply mới append record.
# Không sửa dòng checkpoint cũ và không tự suy frame từ tên ảnh/keyframe.

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import run as run_module  # noqa: E402
from backend.export import QuerySubmission, validate_submission  # noqa: E402
from backend.export.exporter import n_frames_of  # noqa: E402
from backend.export.qa_variants import apply_qa_submission_policy  # noqa: E402
from backend.indexing.frame_map import load_frame_map  # noqa: E402
from backend.tasks.runner import QueryRun  # noqa: E402
from data.config.submit_format import (  # noqa: E402
    ANSWER_MAX_CHARS,
    ANSWERS_PER_QUERY,
    Answer,
)


class ManualOverrideError(ValueError):
    """Dữ liệu operator không đủ an toàn để ghi checkpoint."""


def _sha256(path: Path) -> str:
    """Băm evidence để provenance không phụ thuộc đường dẫn tạm."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mapped_keyframes(video_id: str, start: int, end: int) -> dict[int, str]:
    """Frame tuyệt đối → keyframe canonical, chỉ từ frame_map đã audit."""
    by_frame: dict[int, str] = {}
    for keyframe_id, frame_idx in load_frame_map().items():
        frame_idx = int(frame_idx)
        if not keyframe_id.startswith(f"{video_id}#") or not start <= frame_idx <= end:
            continue
        current = by_frame.get(frame_idx)
        if current is None or keyframe_id < current:
            by_frame[frame_idx] = keyframe_id
    return by_frame


def build_override(
    *,
    queries_path: Path,
    out_dir: Path,
    query_id: str,
    answer_text: str,
    video_id: str,
    frame_id: int,
    keyframe_id: str,
    frame_start: int,
    frame_end: int,
    evidence_path: Path,
) -> tuple[dict, dict, dict]:
    """Dựng record checkpoint + trace nhưng chưa ghi.

    Input là fact/operator evidence tường minh. Output gồm checkpoint record,
    trace record và summary. Invariant: đúng 100 frame khác nhau, frame hạng 1
    khớp keyframe trong frame_map, mọi frame nằm trong video thật.
    """
    if not evidence_path.is_file():
        raise ManualOverrideError(f"không thấy evidence: {evidence_path}")
    if not answer_text or answer_text != answer_text.strip():
        raise ManualOverrideError("answer phải khác rỗng và không có khoảng trắng đầu/cuối")
    if len(answer_text) > ANSWER_MAX_CHARS:
        raise ManualOverrideError(
            f"answer dài {len(answer_text)} ký tự, tối đa {ANSWER_MAX_CHARS}"
        )
    if frame_end < frame_start:
        raise ManualOverrideError("frame-end phải >= frame-start")
    frames = list(range(frame_start, frame_end + 1))
    if len(frames) != ANSWERS_PER_QUERY:
        raise ManualOverrideError(
            f"khoảng frame có {len(frames)} dòng, phải đúng {ANSWERS_PER_QUERY}"
        )
    if frame_id not in frames:
        raise ManualOverrideError("frame-id hạng 1 phải nằm trong khoảng frame")

    try:
        n_frames = n_frames_of(video_id)
    except KeyError as exc:
        raise ManualOverrideError(f"video_id không tồn tại: {video_id}") from exc
    if frame_start < 0 or frame_end >= n_frames:
        raise ManualOverrideError(
            f"khoảng [{frame_start}, {frame_end}] nằm ngoài [0, {n_frames})"
        )

    frame_map = load_frame_map()
    mapped_primary = frame_map.get(keyframe_id)
    if mapped_primary is None:
        raise ManualOverrideError(f"keyframe_id không có trong frame_map: {keyframe_id}")
    mapped_primary = int(mapped_primary)
    if mapped_primary != frame_id:
        raise ManualOverrideError(
            f"frame-id={frame_id} lệch frame_map={mapped_primary} cho {keyframe_id}"
        )
    if not keyframe_id.startswith(f"{video_id}#"):
        raise ManualOverrideError(
            f"keyframe_id={keyframe_id} không thuộc video_id={video_id}"
        )

    queries = run_module._doc_queries(queries_path)
    query = next((item for item in queries if item["query_id"] == query_id), None)
    if query is None:
        raise ManualOverrideError(f"query-id không tồn tại trong file đề: {query_id}")
    if query["task_type"] != "QA":
        raise ManualOverrideError(f"{query_id} không phải task QA")

    checkpoint = run_module.Checkpoint(out_dir / run_module.CHECKPOINT_NAME)
    existing = checkpoint.doc()
    if query_id in existing:
        raise ManualOverrideError(f"checkpoint đã có {query_id}; không append trùng")
    fingerprints = {
        str(record.get("runtime_fingerprint") or "")
        for record in existing.values()
        if str(record.get("runtime_fingerprint") or "")
    }
    if len(fingerprints) != 1:
        raise ManualOverrideError(
            f"checkpoint phải có đúng một runtime fingerprint, đang có {len(fingerprints)}"
        )
    runtime_fingerprint = next(iter(fingerprints))

    # Hạng 1 là frame operator xác minh; phần còn lại đi theo khoảng cách tới nó.
    ranked_frames = sorted(frames, key=lambda value: (abs(value - frame_id), value))
    mapped = _mapped_keyframes(video_id, frame_start, frame_end)
    answers = [
        Answer(
            video_id=video_id,
            frame_ids=(value,),
            answer_text=answer_text,
            keyframe_id=mapped.get(value),
        )
        for value in ranked_frames
    ]
    if answers[0].keyframe_id != keyframe_id:
        raise ManualOverrideError(
            f"keyframe canonical của frame hạng 1 là {answers[0].keyframe_id}, không phải {keyframe_id}"
        )

    base_submission = QuerySubmission(query_id, "QA", tuple(answers))
    issues = validate_submission(base_submission)
    robust_answers = apply_qa_submission_policy(answers, "robust")
    issues += validate_submission(QuerySubmission(query_id, "QA", tuple(robust_answers)))
    if issues:
        raise ManualOverrideError(
            "validator từ chối override: "
            + " · ".join(f"{issue.slug}: {issue.message}" for issue in issues[:10])
        )

    evidence_hash = _sha256(evidence_path)
    qa_trace = {
        "event_vi": query["query_vi"],
        "question_vi": query["query_vi"],
        "evidence_type": "manual_image",
        "answer_mode": "manual_verified",
        "planner_fallback": False,
        "hypotheses": [
            {
                "answer_text": answer_text,
                "video_id": video_id,
                "evidence_frame_idx": frame_id,
                "keyframe_id": keyframe_id,
                "source": "operator_evidence",
            }
        ],
        "answer_shot_id": None,
        "evidence_frame_idx": frame_id,
        "submitted_keyframe_id": keyframe_id,
        "submitted_frame_idx": frame_id,
        "confidence": "operator_verified",
        "qa_runtime": {
            "manual_override": True,
            "evidence_path": str(evidence_path.resolve()),
            "evidence_sha256": evidence_hash,
            "verified_frame_interval": [frame_start, frame_end],
        },
        "generations_used": 0,
        "generation_limit": 0,
        "generation_limit_reached": False,
    }
    at = datetime.now().isoformat(timespec="seconds")
    n_real = sum(answer.keyframe_id is not None for answer in answers)
    record = {
        "query_id": query_id,
        "task_type": "QA",
        "query_hash": run_module._query_hash(query),
        "runtime_fingerprint": runtime_fingerprint,
        "n_answers": len(answers),
        "n_real": n_real,
        "seconds": 0.0,
        "at": at,
        "answer_text": answer_text,
        "qa_trace": qa_trace,
        "n_trake": None,
        "answers": [run_module._answer_to_dict(answer) for answer in answers],
    }
    trace = QueryRun(
        query_id=query_id,
        task_type="QA",
        answers=answers,
        query_plan={
            "query_vi": query["query_vi"],
            "query_en": query.get("query_en"),
            "event_descs": query.get("event_descs"),
            "n_events": query.get("n_events"),
        },
        qa_hypotheses=list(qa_trace["hypotheses"]),
        timings={"total_seconds": 0.0},
        runtime_fingerprint=runtime_fingerprint,
        task_metadata={"manual_override": True, "evidence_sha256": evidence_hash},
        answer_text=answer_text,
        qa_trace=qa_trace,
    ).to_trace_dict()
    summary = {
        "query_id": query_id,
        "answer_text": answer_text,
        "video_id": video_id,
        "first_frame": ranked_frames[0],
        "frame_interval": [frame_start, frame_end],
        "n_answers": len(answers),
        "n_real": n_real,
        "query_hash": record["query_hash"],
        "runtime_fingerprint": runtime_fingerprint,
        "evidence_sha256": evidence_hash,
    }
    return record, trace, summary


def _append(path: Path, record: dict) -> None:
    """Append + flush + fsync qua đúng writer checkpoint của run.py."""
    writer = run_module.Checkpoint(path)
    writer.mo()
    try:
        writer.ghi(record)
    finally:
        writer.dong()


def main() -> int:
    parser = argparse.ArgumentParser(description="Thêm Q&A operator-verified vào checkpoint")
    parser.add_argument("--queries", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--query-id", required=True)
    parser.add_argument("--answer", required=True)
    parser.add_argument("--video-id", required=True)
    parser.add_argument("--frame-id", type=int, required=True)
    parser.add_argument("--keyframe-id", required=True)
    parser.add_argument("--frame-start", type=int, required=True)
    parser.add_argument("--frame-end", type=int, required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--apply", action="store_true", help="backup rồi append; mặc định dry-run")
    args = parser.parse_args()

    out_dir = Path(args.out)
    try:
        record, trace, summary = build_override(
            queries_path=Path(args.queries),
            out_dir=out_dir,
            query_id=args.query_id,
            answer_text=args.answer,
            video_id=args.video_id,
            frame_id=args.frame_id,
            keyframe_id=args.keyframe_id,
            frame_start=args.frame_start,
            frame_end=args.frame_end,
            evidence_path=Path(args.evidence),
        )
        if args.apply:
            checkpoint_path = out_dir / run_module.CHECKPOINT_NAME
            trace_path = out_dir / run_module.TRACE_NAME
            checkpoint_backup = out_dir / f"checkpoint.before-{args.query_id}.jsonl"
            trace_backup = out_dir / f"trace.before-{args.query_id}.jsonl"
            if checkpoint_backup.exists() or trace_backup.exists():
                raise ManualOverrideError("backup manual override đã tồn tại; dừng để tránh ghi lặp")
            shutil.copy2(checkpoint_path, checkpoint_backup)
            if trace_path.exists():
                shutil.copy2(trace_path, trace_backup)
            # Trace trước, checkpoint sau: nếu bước cuối lỗi thì exporter vẫn dừng vì thiếu query.
            _append(trace_path, trace)
            _append(checkpoint_path, record)
            summary["mode"] = "applied"
            summary["checkpoint_backup"] = str(checkpoint_backup)
            summary["trace_backup"] = str(trace_backup) if trace_backup.exists() else None
        else:
            summary["mode"] = "dry-run"
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    except (ManualOverrideError, OSError, ValueError) as exc:
        print(f"[manual QA] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
