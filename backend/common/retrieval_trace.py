"""Observer tùy chọn: trace giữ bản sao dữ liệu, không tham gia quyết định ranking."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from functools import wraps
import inspect
import time

_calls = ContextVar("retrieval_calls", default=None)
_active = ContextVar("retrieval_call", default=None)


@contextmanager
def capture_retrieval():
    """Output list các search thật trong context; reset kể cả task ném lỗi."""
    calls = []
    token = _calls.set(calls)
    try:
        yield calls
    finally:
        _calls.reset(token)


def current_call():
    return _active.get()


@contextmanager
def bind_call(call):
    """Truyền observer sang worker; không chia sẻ context giữa hai query."""
    token = _active.set(call)
    try:
        yield
    finally:
        _active.reset(token)


def record(stage: str, value) -> None:
    """Snapshot khi observer bật; sửa dữ liệu về sau không được viết lại lịch sử."""
    call = current_call()
    if call is not None:
        call[stage] = deepcopy(value)


def record_error(stage: str, error: Exception) -> None:
    call = current_call()
    if call is not None:
        call["errors"].append({"stage": stage, "type": type(error).__name__, "message": str(error)})


def traced_search(fn):
    """Bọc search thật; không bắt lỗi thay caller và không thay output."""
    signature = inspect.signature(fn)
    @wraps(fn)
    def wrapped(*args, **kwargs):
        calls = _calls.get()
        if calls is None:
            return fn(*args, **kwargs)
        bound = signature.bind(*args, **kwargs)
        bound.apply_defaults()
        call = {"input": deepcopy(dict(bound.arguments)), "branches": {}, "errors": [],
                "status": "running", "fused_ranking": [], "reranked_ranking": [], "final_ranking": []}
        calls.append(call)
        start = time.perf_counter()
        with bind_call(call):
            try:
                result = fn(*args, **kwargs)
                record("final_ranking", result)
                call["status"] = "success"
                return result
            except Exception as error:
                call["status"] = "failed"
                call["error"] = {"type": type(error).__name__, "message": str(error)}
                raise
            finally:
                call["seconds"] = time.perf_counter() - start
    return wrapped
