"""Entrypoint chung để production và evaluator không còn lệch cách định tuyến."""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
from dataclasses import dataclass, field
from datetime import date, datetime, time as datetime_time
from pathlib import Path
from typing import Any, Literal, Mapping

from data.config.submit_format import Answer


FailureClass = Literal[
    "retrieval_miss",
    "wrong_frame",
    "qa_reasoning",
    "missing_evidence",
    "trake_order",
    "format",
]
FAILURE_CLASSES: frozenset[str] = frozenset({
    "retrieval_miss",
    "wrong_frame",
    "qa_reasoning",
    "missing_evidence",
    "trake_order",
    "format",
})
REPO_ROOT = Path(__file__).resolve().parents[2]


def _answer_to_dict(answer: Answer) -> dict[str, Any]:
    return {
        "video_id": answer.video_id,
        "frame_ids": list(answer.frame_ids),
        "answer_text": answer.answer_text,
        "keyframe_id": answer.keyframe_id,
    }


def _json_safe(value: Any, *, path: str = "$") -> Any:
    """Chuẩn hóa trace đệ quy mà không stringify tùy tiện làm mất cấu trúc.

    Mapping giữ mapping; tuple/set/numpy container thành list; Path và thời gian
    dùng biểu diễn chuẩn. Scalar numpy/parquet đi qua `item()`/`as_py()`. JSON
    không có NaN/Infinity nên mọi float không hữu hạn được ghi `null` để
    `json.dumps(..., allow_nan=False)` luôn kiểm chứng được artefact.
    """
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, (datetime, date, datetime_time)):
        return value.isoformat()
    if isinstance(value, Mapping):
        normalized: dict[Any, Any] = {}
        for key, item in value.items():
            safe_key = _json_safe(key, path=f"{path}.<key>")
            if not isinstance(safe_key, (str, int, float, bool, type(None))):
                raise TypeError(
                    f"Trace mapping key tại {path} không phải JSON scalar: "
                    f"{type(key).__name__}"
                )
            normalized[safe_key] = _json_safe(item, path=f"{path}.{safe_key}")
        return normalized
    if isinstance(value, (list, tuple)):
        return [_json_safe(item, path=f"{path}[{index}]") for index, item in enumerate(value)]
    if isinstance(value, (set, frozenset)):
        items = [_json_safe(item, path=f"{path}[]") for item in value]
        return sorted(
            items,
            key=lambda item: json.dumps(
                item, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ),
        )

    # PyArrow/parquet scalar công khai protocol `as_py()`; gọi xong vẫn chuẩn
    # hóa đệ quy vì kết quả có thể là datetime/Decimal/numpy scalar khác.
    as_py = getattr(value, "as_py", None)
    if callable(as_py):
        converted = as_py()
        if converted is not value:
            return _json_safe(converted, path=path)

    # Numpy container dùng `tolist()` để giữ shape/list thay vì ép thành chuỗi.
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        converted = tolist()
        if converted is not value:
            return _json_safe(converted, path=path)

    # Numpy/pandas scalar dùng `item()`; không nuốt lỗi và không fallback sang
    # `str(value)` vì làm vậy che mất schema không được hỗ trợ.
    item = getattr(value, "item", None)
    if callable(item):
        converted = item()
        if converted is not value:
            return _json_safe(converted, path=path)

    raise TypeError(f"Trace value tại {path} không JSON-safe: {type(value).__name__}")


def _query_value(query: object, name: str, default: Any = None) -> Any:
    """Đọc cùng contract từ dict hoặc dataclass Query mà không import dev_set."""
    if isinstance(query, Mapping):
        return query.get(name, default)
    return getattr(query, name, default)


def _query_plan(query: object) -> dict[str, Any]:
    """Chuẩn hóa phần input ảnh hưởng lời giải thành JSON để trace/replay."""
    return {
        "query_vi": _query_value(query, "query_vi"),
        "query_en": _query_value(query, "query_en"),
        "event_descs": _query_value(query, "event_descs"),
        "n_events": _query_value(query, "n_events"),
    }


@dataclass
class QueryRun:
    """Kết quả một query cùng provenance đủ để scorer không search lại.

    `answers` chỉ có ở trạng thái success. `failure_class` chỉ có ở trạng thái
    failed và luôn thuộc sáu nhãn product spec; caller vẫn được quyền ném lại
    exception để retry, nhưng có thể ghi `to_trace_dict()` trước khi làm vậy.
    """

    query_id: str
    task_type: str
    answers: list[Answer]
    query_plan: dict[str, Any]
    search_rows: list[dict[str, Any]] = field(default_factory=list)
    source_ranks: list[dict[str, Any]] = field(default_factory=list)
    source_contributions: list[dict[str, Any]] = field(default_factory=list)
    qa_hypotheses: list[dict[str, Any]] = field(default_factory=list)
    timings: dict[str, float] = field(default_factory=dict, compare=False)
    failure_class: FailureClass | None = None
    status: Literal["success", "failed"] = "success"
    runtime_fingerprint: str = ""
    task_metadata: dict[str, Any] = field(default_factory=dict)
    answer_text: str | None = None
    qa_trace: dict[str, Any] | None = None
    n_trake: int | None = None
    error: str | None = None
    retryable: bool = False

    def __post_init__(self) -> None:
        if self.failure_class is not None and self.failure_class not in FAILURE_CLASSES:
            raise ValueError(f"failure_class không thuộc product spec: {self.failure_class}")
        if self.status == "success" and self.failure_class is not None:
            raise ValueError("QueryRun success không được mang failure_class")
        if self.status == "failed" and self.failure_class is None:
            raise ValueError("QueryRun failed phải có failure_class")
        if self.status == "failed" and self.answers:
            raise ValueError("QueryRun failed không được chứa partial/fake answers")

    def compatibility_metadata(self) -> dict[str, Any]:
        """Giữ tuple contract cũ của run.py trong lúc caller chuyển dần."""
        return {
            "answer_text": self.answer_text,
            "qa_trace": self.qa_trace,
            "n_trake": self.n_trake,
            "query_run": self,
        }

    def to_trace_dict(self) -> dict[str, Any]:
        """Đổi sang JSON-safe record; không chứa secret hay object backend."""
        trace = {
            "query_id": self.query_id,
            "task_type": self.task_type,
            "status": self.status,
            "failure_class": self.failure_class,
            "error": self.error,
            "retryable": self.retryable,
            "runtime_fingerprint": self.runtime_fingerprint,
            "query_plan": self.query_plan,
            "source_ranks": self.source_ranks,
            "source_contributions": self.source_contributions,
            "search_rows": self.search_rows,
            "qa_hypotheses": self.qa_hypotheses,
            "timings": self.timings,
            "task_metadata": self.task_metadata,
            "answer_text": self.answer_text,
            "qa_trace": self.qa_trace,
            "n_trake": self.n_trake,
            "answers": [_answer_to_dict(answer) for answer in self.answers],
        }
        return _json_safe(trace)


class SolveQueryError(RuntimeError):
    """Lỗi retryable kèm trace đầy đủ, nhưng không giả làm query thành công."""

    def __init__(self, message: str, query_run: QueryRun):
        super().__init__(message)
        self.query_run = query_run


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _source_hash(path: Path) -> str:
    try:
        return _sha256_bytes(path.read_bytes())
    except OSError:
        return "missing"


def runtime_manifest() -> dict[str, Any]:
    """Snapshot deterministic của env/config ảnh hưởng query, không đọc secret.

    Model chỉ lấy từ biến của backend đang chọn. Tất cả file `data/config/*.py`
    được hash theo đường dẫn tương đối đã sort để thay đổi knob cache-relevant
    luôn làm fingerprint đổi mà không đưa nội dung/credential vào trace.
    """
    backend = str(os.environ.get("LLM_BACKEND") or "api").strip()
    model_env = {
        "api": "LLM_API_MODEL",
        "gemini": "LLM_GEMINI_MODEL",
        "local": "LLM_LOCAL_MODEL",
    }.get(backend)
    model = str(os.environ.get(model_env) or "<unset>") if model_env else "<invalid>"
    config_hashes = {
        path.relative_to(REPO_ROOT).as_posix(): _source_hash(path)
        for path in sorted((REPO_ROOT / "data" / "config").glob("*.py"))
    }
    critical_hashes = {
        path: _source_hash(REPO_ROOT / path)
        for path in (
            "backend/retrieval/multi_anchor.py",
            "backend/retrieval/search.py",
            "backend/common/answer_match.py",
            "backend/slot/allocator.py",
            "backend/tasks/qa.py",
            "backend/tasks/qa_portfolio.py",
            "backend/tasks/trake.py",
            "backend/tasks/runner.py",
        )
    }
    return {
        "schema_version": 1,
        "llm": {"backend": backend, "model": model},
        "qa_inference_mode": str(os.environ.get("QA_INFERENCE_MODE") or "<unset>"),
        "config_sha256": config_hashes,
        "critical_sources_sha256": critical_hashes,
    }


def runtime_fingerprint() -> str:
    """Hash canonical của `runtime_manifest()` để khóa cache/resume."""
    raw = json.dumps(
        runtime_manifest(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return _sha256_bytes(raw.encode("utf-8"))


def failure_trace(
    query: object,
    error: BaseException,
    *,
    failure_class: FailureClass,
    runtime_fingerprint: str | None = None,
    timings: Mapping[str, float] | None = None,
    retryable: bool = False,
) -> QueryRun:
    """Tạo trace lỗi JSON-safe, tuyệt đối không checkpoint answers bán phần."""
    if failure_class not in FAILURE_CLASSES:
        raise ValueError(f"failure_class không thuộc product spec: {failure_class}")
    return QueryRun(
        query_id=str(_query_value(query, "query_id", "")),
        task_type=str(_query_value(query, "task_type", "")),
        answers=[],
        query_plan=_query_plan(query),
        timings=dict(timings or {}),
        failure_class=failure_class,
        status="failed",
        runtime_fingerprint=runtime_fingerprint or globals()["runtime_fingerprint"](),
        error=f"{type(error).__name__}: {error}",
        retryable=retryable,
    )


def _trace_rows(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ranks = [
        {"keyframe_id": row.get("keyframe_id"), "ranks": dict(row.get("ranks") or {})}
        for row in rows
        if row.get("ranks")
    ]
    contributions = [
        {
            "keyframe_id": row.get("keyframe_id"),
            "contributions": dict(row.get("contrib") or {}),
        }
        for row in rows
        if row.get("contrib")
    ]
    return ranks, contributions


def _default_failure_class(task_type: str) -> FailureClass:
    if task_type == "QA":
        return "missing_evidence"
    if task_type == "TRAKE":
        return "trake_order"
    return "retrieval_miss"


def solve_query(
    query: object,
    total: int = 100,
    *,
    runtime_fingerprint: str | None = None,
) -> QueryRun:
    """Giải KIS/Q&A/TRAKE qua đúng pipeline production và trả trace thống nhất.

    Input là mapping hoặc object có field kiểu `dev_set.tools.schema.Query`;
    backend không import dev_set. Output thành công luôn là `QueryRun` đủ raw
    rows/ranks cho evaluator. Lỗi được ném lại bằng `SolveQueryError` để caller
    retry, kèm failure trace không chứa answers bán phần.
    """
    started = time.perf_counter()
    task_type = str(_query_value(query, "task_type", ""))
    fingerprint = runtime_fingerprint or globals()["runtime_fingerprint"]()
    plan = _query_plan(query)
    timings: dict[str, float] = {}

    try:
        if task_type not in ("KIS", "QA", "TRAKE"):
            raise ValueError(f"task_type không hợp lệ: {task_type!r}")
        if isinstance(total, bool) or not isinstance(total, int) or total <= 0:
            raise ValueError("total phải là số nguyên dương")

        if task_type == "TRAKE":
            from backend.tasks.trake import pad_answers, parse_events, to_answers, trake_search

            events = _query_value(query, "event_descs") or parse_events(
                str(_query_value(query, "query_vi", ""))
            )
            expected_n = _query_value(query, "n_events")
            if isinstance(expected_n, bool) or not isinstance(expected_n, int) or expected_n < 2:
                raise ValueError("TRAKE thiếu n_events hợp lệ")
            if not isinstance(events, list) or len(events) != expected_n:
                actual_n = len(events) if isinstance(events, list) else "không phải list"
                raise ValueError(
                    f"TRAKE khai báo n_events={expected_n} nhưng tách được {actual_n} sự kiện"
                )
            plan["events"] = list(events)
            stage_started = time.perf_counter()
            candidates = trake_search(events, top_videos=total)
            timings["retrieval_seconds"] = round(time.perf_counter() - stage_started, 6)
            if not candidates:
                raise RuntimeError("trake_search() không tìm được video ứng viên nào")
            answers = to_answers(candidates)
            if len(answers) < total:
                answers = pad_answers(candidates, total)
            rows = [
                {
                    "video_id": candidate.video_id,
                    "score": float(candidate.score),
                    "frame_ids": list(candidate.frame_ids),
                    "keyframe_ids": list(candidate.keyframe_ids),
                    "n_hit_events": candidate.n_hit_events,
                    "has_full_order": candidate.has_full_order,
                }
                for candidate in candidates
            ]
            timings["total_seconds"] = round(time.perf_counter() - started, 6)
            return QueryRun(
                query_id=str(_query_value(query, "query_id", "")),
                task_type=task_type,
                answers=answers[:total],
                query_plan=plan,
                search_rows=rows,
                timings=timings,
                runtime_fingerprint=fingerprint,
                task_metadata={"events": list(events), "candidates": rows},
                n_trake=expected_n,
            )

        from backend.slot import ShotHit, allocate

        if task_type == "QA":
            from backend.tasks.qa import QAHypothesis, qa_pipeline
            from backend.tasks.qa_portfolio import allocate_qa_portfolio

            stage_started = time.perf_counter()
            hits, answer_text, qa_trace = qa_pipeline(
                str(_query_value(query, "query_vi", "")),
                query_en=_query_value(query, "query_en"),
                return_trace=True,
                runtime_fingerprint=fingerprint,
                # Anchor Q&A do Claude điền ở bước 1b (exam_plan.json) — caption
                # tiếng Anh ngắn tả CẢNH, bỏ phần hỏi. Không có thì pipeline vẫn
                # chạy như cũ bằng `event_vi`.
                anchors=_query_value(query, "anchors") or None,
            )
            timings["qa_seconds"] = round(time.perf_counter() - stage_started, 6)
            if not str(answer_text or "").strip():
                raise RuntimeError("qa_pipeline() không suy ra được answer_text")
            rows = [
                {
                    "shot_id": hit.shot_id,
                    "score": float(hit.score),
                    "keyframe_id": hit.best_keyframe_id,
                }
                for hit in hits
            ]
            plan.update({
                key: qa_trace.get(key)
                for key in (
                    "event_vi", "question_vi", "evidence_type", "answer_mode",
                    "planner_fallback",
                )
                if key in qa_trace
            })
            hypothesis_rows = qa_trace.get("hypotheses")
            if hypothesis_rows is not None:
                if not isinstance(hypothesis_rows, list) or not hypothesis_rows:
                    raise RuntimeError("qa_pipeline() không có hypothesis evidence hợp lệ")
                hypotheses = [
                    QAHypothesis.from_dict(dict(item))
                    for item in hypothesis_rows
                    if isinstance(item, Mapping)
                ]
                if len(hypotheses) != len(hypothesis_rows):
                    raise RuntimeError("qa_trace.hypotheses có record sai schema")
                answers = allocate_qa_portfolio(hypotheses, hits, total=total)
                serialized_hypotheses = [item.to_dict() for item in hypotheses]
            else:
                # Contract trace cũ chỉ được giữ cho caller/test chuyển tiếp;
                # pipeline production mới luôn có khóa `hypotheses` fail-closed.
                answers = allocate(hits, "QA", answer_text=answer_text, total=total)
                serialized_hypotheses = []
            timings["total_seconds"] = round(time.perf_counter() - started, 6)
            return QueryRun(
                query_id=str(_query_value(query, "query_id", "")),
                task_type=task_type,
                answers=answers,
                query_plan=plan,
                search_rows=rows,
                timings=timings,
                runtime_fingerprint=fingerprint,
                task_metadata={"hits": rows},
                answer_text=answer_text,
                qa_trace=qa_trace,
                qa_hypotheses=serialized_hypotheses,
            )

        from backend.retrieval.multi_anchor import plan_query, search_multi

        stage_started = time.perf_counter()
        query_vi = str(_query_value(query, "query_vi", ""))
        query_en = _query_value(query, "query_en")
        kis_plan = plan_query(query_vi, query_en=query_en)
        plan = kis_plan.to_dict()
        if kis_plan.strategy == "single":
            # Giữ nguyên đường hiện hành cho query ngắn/fallback: đúng một lần
            # gọi search và giữ bản dịch EN caller đã cung cấp.
            from backend.retrieval.search import search

            # R3.K3 — làn KIS chạy HAI nhánh vector và pool sâu riêng. Truyền
            # tường minh tại đây chứ không đổi mặc định của search(): Q&A và
            # TRAKE cũng gọi search(), đổi mặc định là đội chi phí hai làn khác
            # mà không ai yêu cầu (Q&A đang 196–476 s/câu).
            from data.config.search_weights import KIS_CANDIDATE_MULTIPLIER

            rows = search(
                query_vi,
                query_en=query_en,
                top_k=total,
                group_by_shot=True,
                branches={"vector_siglip2": True},
                candidate_multiplier=KIS_CANDIDATE_MULTIPLIER,
            )
        else:
            rows = search_multi(kis_plan, top_k=total)
        timings["retrieval_seconds"] = round(time.perf_counter() - stage_started, 6)
        hits = [
            ShotHit(row["shot_id"], row["score"], row["keyframe_id"])
            for row in rows
            if row.get("shot_id")
        ]
        if not hits:
            raise RuntimeError("search() không trả shot nào có shot_id")
        ranks, contributions = _trace_rows(rows)
        answers = allocate(hits, task_type, total=total)
        timings["total_seconds"] = round(time.perf_counter() - started, 6)
        return QueryRun(
            query_id=str(_query_value(query, "query_id", "")),
            task_type=task_type,
            answers=answers,
            query_plan=plan,
            search_rows=[dict(row) for row in rows],
            source_ranks=ranks,
            source_contributions=contributions,
            timings=timings,
            runtime_fingerprint=fingerprint,
            task_metadata={"hits": [dict(row) for row in rows]},
        )
    except SolveQueryError:
        raise
    except Exception as error:
        timings["total_seconds"] = round(time.perf_counter() - started, 6)
        failure_class: FailureClass
        if isinstance(error, ValueError):
            failure_class = "format"
        else:
            failure_class = _default_failure_class(task_type)
        trace = failure_trace(
            query,
            error,
            failure_class=failure_class,
            runtime_fingerprint=fingerprint,
            timings=timings,
            retryable=task_type == "QA" and not isinstance(error, ValueError),
        )
        raise SolveQueryError(str(error), trace) from error
