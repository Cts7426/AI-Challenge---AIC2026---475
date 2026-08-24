"""Contract runner chung, không chạm ES/Milvus/LLM thật trong test."""

from __future__ import annotations

import importlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.slot import ShotHit
from data.config.submit_format import Answer


KIS = {
    "query_id": "q-kis",
    "task_type": "KIS",
    "query_vi": "xe máy qua ngã tư",
    "query_en": "motorcycle at an intersection",
}


def _runner():
    return importlib.import_module("backend.tasks.runner")


def _search_row() -> dict:
    return {
        "keyframe_id": "L01_V001_001",
        "video_id": "L01_V001",
        "frame_idx": 120,
        "timestamp_ms": 4000,
        "shot_id": "L01_V001#s0001",
        "score": 0.25,
        "ranks": {"vector": 1, "ocr": 4},
        "contrib": {"vector": 0.125, "ocr": 0.02},
    }


def test_query_run_giu_raw_rows_ranks_contributions_va_trace_json(monkeypatch):
    """Bắt lỗi runner chỉ giữ Answer khiến evaluator phải search lần hai."""
    runner = _runner()
    search_module = importlib.import_module("backend.retrieval.search")
    monkeypatch.setattr(search_module, "search", lambda *a, **kw: [_search_row()])
    monkeypatch.setattr(
        importlib.import_module("backend.slot"),
        "allocate",
        lambda hits, task, **kw: [
            Answer("L01_V001", (120,), keyframe_id="L01_V001_001")
        ],
    )

    result = runner.solve_query(KIS, total=1, runtime_fingerprint="snapshot-1")

    assert result.status == "success"
    assert result.failure_class is None
    assert result.runtime_fingerprint == "snapshot-1"
    assert result.search_rows == [_search_row()]
    assert result.source_ranks == [
        {"keyframe_id": "L01_V001_001", "ranks": {"vector": 1, "ocr": 4}}
    ]
    assert result.source_contributions == [
        {"keyframe_id": "L01_V001_001", "contributions": {"vector": 0.125, "ocr": 0.02}}
    ]
    assert result.qa_hypotheses == []
    trace = json.loads(json.dumps(result.to_trace_dict(), ensure_ascii=False))
    assert trace["answers"][0]["frame_ids"] == [120]
    assert trace["query_plan"]["query_en"] == KIS["query_en"]


def test_kis_multi_anchor_ghi_plan_outer_trace_va_khong_search_trung(monkeypatch):
    """Bắt lỗi runner search lại query gốc hoặc làm mất outer-RRF provenance."""
    runner = _runner()
    multi = importlib.import_module("backend.retrieval.multi_anchor")
    slot = importlib.import_module("backend.slot")
    query = {
        "query_id": "q-kis-multi",
        "task_type": "KIS",
        "query_vi": (
            "Người bước vào cửa hàng rồi nhìn bảng giá, sau đó quay sang nói chuyện "
            "với nhân viên đang đứng cạnh quầy thanh toán phía trước"
        ),
    }
    proposed = ["Người bước vào cửa hàng", "Người nhìn bảng giá"]
    search_calls: list[str] = []

    monkeypatch.setattr(
        multi, "llm", lambda *args, **kwargs: json.dumps({"anchors": proposed})
    )
    monkeypatch.setattr(multi, "translate", lambda text: f"EN {text}")
    monkeypatch.setattr(multi, "count_clip_tokens", lambda text: 11)

    def fake_search(query_vi, **kwargs):
        search_calls.append(query_vi)
        rank = len(search_calls)
        return [{
            **_search_row(),
            "timestamp_ms": 1000 * rank,
            "score": 0.99 - rank,
        }]

    monkeypatch.setattr(multi, "search", fake_search)
    monkeypatch.setattr(
        importlib.import_module("backend.retrieval.search"),
        "search",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("runner không được search lại query gốc")
        ),
    )
    monkeypatch.setattr(
        slot,
        "allocate",
        lambda hits, task, **kwargs: [
            Answer("L01_V001", (120,), keyframe_id="L01_V001_001")
        ],
    )

    result = runner.solve_query(query, total=1, runtime_fingerprint="fp-multi")

    assert search_calls == proposed
    assert result.query_plan["strategy"] == "multi"
    assert [anchor["query_vi"] for anchor in result.query_plan["anchors"]] == proposed
    assert result.search_rows[0]["temporal_order_match"] is True
    assert result.source_ranks == [{
        "keyframe_id": "L01_V001_001",
        "ranks": {"anchor_1": 1, "anchor_2": 1},
    }]
    assert result.source_contributions[0]["contributions"] == pytest.approx({
        "anchor_1": 1 / 8,
        "anchor_2": 1 / 8,
    })
    json.dumps(result.to_trace_dict(), ensure_ascii=False, allow_nan=False)


def test_trace_json_normalize_numpy_container_path_datetime_va_non_finite():
    """Bắt lỗi success trace vỡ sau solve vì scalar parquet/numpy không JSON-safe."""
    np = pytest.importorskip("numpy")
    runner = _runner()

    class ParquetScalar:
        def as_py(self):
            return np.int64(11)

    result = runner.QueryRun(
        query_id="q-json",
        task_type="KIS",
        answers=[Answer("L01_V001", (np.int64(7),), keyframe_id="kf")],
        query_plan={"anchors": ("a", "b")},
        search_rows=[{
            "frame_idx": np.int64(7),
            "embedding_preview": np.array([0.25, 0.5], dtype=np.float32),
            "asset": Path("derived/frame.jpg"),
            "at": datetime(2026, 8, 24, tzinfo=timezone.utc),
            "bad_scores": {np.float64("nan"), np.float64("inf")},
            "parquet": ParquetScalar(),
        }],
    )

    payload = result.to_trace_dict()
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    decoded = json.loads(encoded)

    row = decoded["search_rows"][0]
    assert row["frame_idx"] == 7
    assert row["embedding_preview"] == [0.25, 0.5]
    assert row["asset"] == "derived/frame.jpg"
    assert row["at"] == "2026-08-24T00:00:00+00:00"
    assert row["bad_scores"] == [None, None]
    assert row["parquet"] == 11
    assert decoded["answers"][0]["frame_ids"] == [7]


def test_giai_mot_query_la_wrapper_parity_voi_solve_query(monkeypatch):
    """Bắt lỗi run.py giữ một dispatch riêng và lại lệch production runner."""
    runner = _runner()
    run_module = importlib.import_module("run")
    search_module = importlib.import_module("backend.retrieval.search")
    monkeypatch.setattr(search_module, "search", lambda *a, **kw: [_search_row()])
    monkeypatch.setattr(
        importlib.import_module("backend.slot"),
        "allocate",
        lambda hits, task, **kw: [Answer("L01_V001", (120,), keyframe_id="L01_V001_001")],
    )

    direct = runner.solve_query(KIS, total=1)
    answers, metadata = run_module.giai_mot_query(KIS, total=1)

    assert answers == direct.answers
    assert metadata == direct.compatibility_metadata()


def test_evaluator_goi_runner_chung_va_khong_search_lan_hai(monkeypatch):
    """Bắt lỗi evaluator tự dispatch/search thay vì tiêu thụ QueryRun."""
    evaluator = importlib.import_module("dev_set.tools.run_evaluation")
    runner = _runner()
    search_module = importlib.import_module("backend.retrieval.search")
    calls = 0

    def fake_search(*args, **kwargs):
        nonlocal calls
        calls += 1
        return [_search_row()]

    monkeypatch.setattr(search_module, "search", fake_search)
    monkeypatch.setattr(
        importlib.import_module("backend.slot"),
        "allocate",
        lambda hits, task, **kw: [Answer("L01_V001", (120,), keyframe_id="L01_V001_001")],
    )

    query = type("QueryLike", (), KIS)()
    result = evaluator._solve_for_evaluation(
        query, total=1, query_runtime_fingerprint="eval-snapshot"
    )

    assert isinstance(result, runner.QueryRun)
    assert result.runtime_fingerprint == "eval-snapshot"
    assert result.search_rows == [_search_row()]
    assert calls == 1


def test_runtime_fingerprint_deterministic_va_khong_chua_secret(monkeypatch):
    """Bắt lỗi hash phụ thuộc thứ tự/secret hoặc bỏ sót model ảnh hưởng cache."""
    runner = _runner()
    monkeypatch.setenv("LLM_BACKEND", "local")
    monkeypatch.setenv("LLM_LOCAL_MODEL", "model-a")
    monkeypatch.setenv("GEMINI_API_KEY", "secret-one")
    first = runner.runtime_fingerprint()
    monkeypatch.setenv("GEMINI_API_KEY", "secret-two")
    assert runner.runtime_fingerprint() == first
    monkeypatch.setenv("LLM_LOCAL_MODEL", "model-b")
    assert runner.runtime_fingerprint() != first
    manifest = runner.runtime_manifest()
    assert "secret-one" not in json.dumps(manifest)
    assert "secret-two" not in json.dumps(manifest)


@pytest.mark.parametrize(
    "failure_class",
    [
        "retrieval_miss",
        "wrong_frame",
        "qa_reasoning",
        "missing_evidence",
        "trake_order",
        "format",
    ],
)
def test_failure_trace_chi_dung_sau_failure_class_cua_spec(failure_class):
    """Bắt lỗi trace quay lại nhãn F0/F_UNKNOWN không thuộc product spec."""
    runner = _runner()
    trace = runner.failure_trace(
        KIS, RuntimeError("boom"), failure_class=failure_class,
        runtime_fingerprint="fp",
    )
    assert trace.status == "failed"
    assert trace.failure_class == failure_class
    assert trace.answers == []
    assert trace.to_trace_dict()["error"] == "RuntimeError: boom"


def test_failure_trace_tu_choi_nhan_ngoai_spec():
    runner = _runner()
    with pytest.raises(ValueError, match="failure_class"):
        runner.failure_trace(KIS, RuntimeError("boom"), failure_class="F0_CRASH")


def test_qa_va_trake_khong_mat_metadata_hien_co(monkeypatch):
    """Bắt lỗi QueryRun làm mất qa_trace/n_trake khi hợp nhất interface."""
    runner = _runner()
    qa = importlib.import_module("backend.tasks.qa")
    trake = importlib.import_module("backend.tasks.trake")
    slot = importlib.import_module("backend.slot")
    hit = ShotHit("L01_V001#s0001", 0.5, "L01_V001_001")
    monkeypatch.setattr(
        qa,
        "qa_pipeline",
        lambda *a, **kw: ([hit], "đỏ", {"answer_shot_id": hit.shot_id}),
    )
    monkeypatch.setattr(
        slot,
        "allocate",
        lambda *a, **kw: [Answer("L01_V001", (120,), answer_text="đỏ")],
    )
    qa_run = runner.solve_query(
        {"query_id": "q-qa", "task_type": "QA", "query_vi": "màu gì?"}, total=1
    )
    assert qa_run.qa_trace == {"answer_shot_id": hit.shot_id}
    assert qa_run.answer_text == "đỏ"

    candidate = type(
        "Candidate",
        (),
        {
            "video_id": "L01_V001",
            "score": 0.7,
            "frame_ids": (120, 240),
            "keyframe_ids": ("a", "b"),
            "n_hit_events": 2,
            "has_full_order": True,
        },
    )()
    monkeypatch.setattr(trake, "trake_search", lambda *a, **kw: [candidate])
    monkeypatch.setattr(
        trake,
        "to_answers",
        lambda candidates, total=None: [Answer("L01_V001", (120, 240), keyframe_id="a")],
    )
    trake_run = runner.solve_query(
        {
            "query_id": "q-trake",
            "task_type": "TRAKE",
            "query_vi": "a . b",
            "event_descs": ["a", "b"],
            "n_events": 2,
        },
        total=1,
    )
    assert trake_run.n_trake == 2
    assert trake_run.task_metadata["candidates"][0]["has_full_order"] is True
