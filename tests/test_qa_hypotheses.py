"""TDD cho Q&A candidate-specific hypotheses và portfolio evidence-first."""

from __future__ import annotations

import json

import pytest

from backend.slot import ShotHit
from data.config.submit_format import Answer


def test_question_planner_nhan_answer_mode_structured(monkeypatch):
    from backend.tasks import qa

    monkeypatch.setattr(
        qa,
        "llm",
        lambda *args, **kwargs: json.dumps({
            "event_vi": "hai người đứng cạnh xe",
            "question_vi": "Có bao nhiêu người?",
            "answer_mode": "visual_count",
        }),
    )

    parts = qa.parse_question("Có bao nhiêu người đứng cạnh xe?")

    assert parts.event_vi == "hai người đứng cạnh xe"
    assert parts.question_vi == "Có bao nhiêu người?"
    assert parts.answer_mode == "visual_count"
    assert qa.PARSE_QUESTION_SCHEMA["properties"]["answer_mode"]["enum"] == [
        "visual_count", "visual_read", "ocr", "asr", "metadata", "visual_attribute",
    ]


@pytest.mark.parametrize(
    "broken",
    ["not-json", json.dumps({"event_vi": "x", "question_vi": "y", "answer_mode": "invented"})],
)
def test_question_planner_loi_fallback_rule_khong_crash(monkeypatch, broken):
    from backend.tasks import qa

    monkeypatch.setattr(qa, "llm", lambda *args, **kwargs: broken)

    parts = qa.parse_question("Có mấy người đứng cạnh xe?")

    assert parts.event_vi == "Có mấy người đứng cạnh xe?"
    assert parts.question_vi == "Có mấy người đứng cạnh xe?"
    assert parts.answer_mode == "visual_count"
    assert parts.planner_fallback is True


def test_planner_fallback_giu_nguyen_text_first_route(monkeypatch):
    from backend.tasks import qa

    monkeypatch.setattr(
        qa,
        "parse_question",
        lambda query: qa.QuestionParts(query, query, "visual_read", planner_fallback=True),
    )
    monkeypatch.setattr(qa, "route_question", lambda question: ("text_first", False))
    monkeypatch.setattr(qa, "search", lambda *a, **kw: [{
        "shot_id": "L21_V001#s1", "score": .9, "keyframe_id": "L21_V001#k10",
    }])
    seen = []
    monkeypatch.setattr(
        qa,
        "_try_shot",
        lambda hit, question, evidence_type, needs_images:
            seen.append((evidence_type, needs_images)) or ("đỏ", 10, .9),
    )
    monkeypatch.setattr(qa, "_keyframe_id_for_frame", lambda *a, **kw: "L21_V001#k10")
    monkeypatch.setattr(qa, "load_frame_map", lambda: {"L21_V001#k10": 10})

    qa.qa_pipeline("không khớp rule", return_trace=True)

    assert seen == [("text_first", False)]


def test_structured_answer_mode_dieu_khien_evidence_route(monkeypatch):
    from backend.tasks import qa

    monkeypatch.setattr(
        qa,
        "parse_question",
        lambda query: qa.QuestionParts("sự kiện", "câu hỏi chung", "asr"),
    )
    monkeypatch.setattr(
        qa,
        "route_question",
        lambda question: (_ for _ in ()).throw(
            AssertionError("structured answer_mode không được route lại bằng keyword")
        ),
    )
    monkeypatch.setattr(
        qa,
        "search",
        lambda *args, **kwargs: [{
            "shot_id": "L21_V001#s1", "score": 0.9, "keyframe_id": "L21_V001#k10",
        }],
    )
    seen = []

    def fake_try(hit, question, evidence_type, needs_images):
        seen.append((evidence_type, needs_images))
        return "Hà Nội", 10, 0.9

    monkeypatch.setattr(qa, "_try_shot", fake_try)
    monkeypatch.setattr(qa, "_keyframe_id_for_frame", lambda *a, **kw: "L21_V001#k10")
    monkeypatch.setattr(qa, "load_frame_map", lambda: {"L21_V001#k10": 10})

    _, _, trace = qa.qa_pipeline("câu hỏi", return_trace=True)

    assert seen == [("asr", False)]
    assert trace["answer_mode"] == "asr"


def test_qahypothesis_constructor_tu_choi_hash_rong_va_sentinel():
    from backend.tasks.qa import QAHypothesis

    with pytest.raises(ValueError, match="evidence_hash"):
        QAHypothesis("đỏ", "L21_V001", "L21_V001#s1", "kf", 10, .9,
                     "", "main:llm", "visual", "visual_attribute")
    with pytest.raises(ValueError, match="sentinel"):
        QAHypothesis("không đủ căn cứ", "L21_V001", "L21_V001#s1", "kf", 10, .9,
                     "a" * 64, "main:llm", "visual", "visual_attribute")


def test_hypothesis_pin_exact_frame_keyframe_hash_va_provenance(monkeypatch):
    from backend.tasks import qa

    fmap = {"L21_V001#k0002": 20}
    monkeypatch.setattr(qa, "load_frame_map", lambda: fmap)
    qa._reverse_frame_map.cache_clear()
    try:
        hypothesis = qa.build_qa_hypothesis(
            ShotHit("L21_V001#s0001", 0.8, "L21_V001#k0001"),
            answer_text="đỏ",
            evidence_frame_idx=20,
            confidence=0.9,
            evidence_hash="a" * 64,
            provenance="main:llm:legacy",
            answer_mode="visual_attribute",
            evidence_type="visual",
        )
    finally:
        qa._reverse_frame_map.cache_clear()

    assert hypothesis is not None
    assert hypothesis.video_id == "L21_V001"
    assert hypothesis.shot_id == "L21_V001#s0001"
    assert hypothesis.keyframe_id == "L21_V001#k0002"
    assert hypothesis.evidence_frame_idx == 20
    assert hypothesis.evidence_hash == "a" * 64
    assert hypothesis.provenance == "main:llm:legacy"


@pytest.mark.parametrize(
    "answer",
    [
        " không đủ căn cứ ", "KHÔNG   CÓ THÔNG TIN", "insufficient evidence",
        "No information", "Không đủ căn cứ.", "No information...",
    ],
)
def test_sentinel_answer_bi_loai_fail_closed(answer):
    from backend.tasks.qa import is_valid_qa_answer

    assert is_valid_qa_answer(answer) is False


def test_production_khong_duoc_bia_evidence_digest_khi_attempt_thieu_hash():
    from backend.tasks.qa import _evidence_hash_for_attempt, QANoValidHypothesisError

    with pytest.raises(QANoValidHypothesisError, match="evidence_hash"):
        _evidence_hash_for_attempt(
            {}, question_vi="gì?", hit=ShotHit("L21_V001#s1", .9),
            answer="đỏ", frame=10, allow_legacy_test_double=False,
        )


def test_planner_cache_end_to_end_cung_fingerprint_khong_goi_lai_llm(tmp_path, monkeypatch):
    from backend.tasks import qa

    monkeypatch.setenv("QA_HYPOTHESIS_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("LLM_BACKEND", "local")
    monkeypatch.setenv("LLM_LOCAL_MODEL", "qa-model")
    planner_raw = json.dumps({
        "event_vi": "sự kiện", "question_vi": "màu gì?",
        "answer_mode": "visual_attribute",
    })
    planner_calls = []
    monkeypatch.setattr(qa, "llm", lambda *a, **kw: planner_calls.append(1) or planner_raw)
    monkeypatch.setattr(qa, "search", lambda *a, **kw: [{
        "shot_id": "L21_V001#s1", "score": .9, "keyframe_id": "L21_V001#k10",
    }])
    monkeypatch.setattr(qa, "_try_shot", lambda *a, **kw: ("đỏ", 10, .9))
    monkeypatch.setattr(qa, "_keyframe_id_for_frame", lambda *a, **kw: "L21_V001#k10")
    monkeypatch.setattr(qa, "load_frame_map", lambda: {"L21_V001#k10": 10})

    first = qa.qa_pipeline("màu gì?", return_trace=True, runtime_fingerprint="same-fp")
    second = qa.qa_pipeline("màu gì?", return_trace=True, runtime_fingerprint="same-fp")

    assert first == second
    assert planner_calls == [1]


def test_portfolio_canonical_moi_hypothesis_di_truoc_alternative(monkeypatch):
    from backend.tasks.qa import QAHypothesis
    from backend.tasks import qa_portfolio

    hypotheses = [
        QAHypothesis("đỏ", "L21_V001", "L21_V001#s1", "L21_V001#k10", 10,
                     0.9, "a" * 64, "main:llm", "visual", "visual_attribute"),
        QAHypothesis("xanh", "L21_V002", "L21_V002#s1", "L21_V002#k20", 20,
                     0.8, "b" * 64, "main:llm", "visual", "visual_attribute"),
    ]
    fmap = {
        "L21_V001#k10": 10, "L21_V001#k11": 11,
        "L21_V002#k20": 20, "L21_V002#k21": 21,
        "L21_V003#k30": 30,
    }
    bounds = {
        "L21_V001#s1": ("L21_V001", 0, 19),
        "L21_V002#s1": ("L21_V002", 20, 29),
        "L21_V003#s1": ("L21_V003", 30, 39),
    }
    monkeypatch.setattr(qa_portfolio, "load_frame_map", lambda: fmap)
    monkeypatch.setattr(qa_portfolio, "shot_bounds", lambda shot_id: bounds[shot_id])

    def fake_allocate(hits, task_type, *, answer_text, total):
        assert [h.shot_id for h in hits] == ["L21_V003#s1"]
        return [Answer("L21_V003", (30,), answer_text=answer_text, keyframe_id="L21_V003#k30")]

    monkeypatch.setattr(qa_portfolio, "allocate", fake_allocate)
    rows = qa_portfolio.allocate_qa_portfolio(
        hypotheses,
        [ShotHit("L21_V001#s1", .9, "L21_V001#k10"),
         ShotHit("L21_V002#s1", .8, "L21_V002#k20"),
         ShotHit("L21_V003#s1", .7, "L21_V003#k30")],
        total=5,
    )

    assert [(row.video_id, row.frame_ids[0], row.answer_text) for row in rows] == [
        ("L21_V001", 10, "đỏ"),
        ("L21_V002", 20, "xanh"),
        ("L21_V001", 11, "đỏ"),
        ("L21_V002", 21, "xanh"),
        ("L21_V003", 30, "đỏ"),
    ]
    assert len({(r.video_id, r.frame_ids, r.answer_text) for r in rows}) == 5


def test_portfolio_fail_neu_total_nho_hon_so_hypothesis(monkeypatch):
    from backend.tasks.qa import QAHypothesis
    from backend.tasks import qa_portfolio

    hypotheses = [
        QAHypothesis(str(i), f"L21_V00{i}", f"L21_V00{i}#s1", f"L21_V00{i}#k1", i,
                     .9 - i / 10, str(i) * 64, "main:llm", "visual", "visual_attribute")
        for i in (1, 2)
    ]
    monkeypatch.setattr(
        qa_portfolio,
        "load_frame_map",
        lambda: {item.keyframe_id: item.evidence_frame_idx for item in hypotheses},
    )
    with pytest.raises(RuntimeError, match="canonical"):
        qa_portfolio.allocate_qa_portfolio(hypotheses, [], total=1)


def test_qa_cache_identity_hit_va_fingerprint_miss(tmp_path, monkeypatch):
    from backend.tasks import qa

    monkeypatch.setenv("QA_HYPOTHESIS_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("LLM_BACKEND", "local")
    monkeypatch.setenv("LLM_LOCAL_MODEL", "qa-model")
    monkeypatch.delenv("LLM_NO_CACHE", raising=False)
    ev = qa.Evidence("L21_V001#s1", "L21_V001", ["42"], [], "", None, [], 10, "e" * 64)
    raw = json.dumps({
        "answer": "42", "answer_vi": "42", "answer_en": "42",
        "evidence_frame_idx": 10, "confidence": 0.9,
    })
    calls = []
    monkeypatch.setattr(qa, "llm", lambda *args, **kwargs: calls.append(args[0]) or raw)

    first = qa.ask_llm("Kết quả là gì?", ev, n=1, runtime_fingerprint="fp-a")
    second = qa.ask_llm("Kết quả là gì?", ev, n=1, runtime_fingerprint="fp-a")
    third = qa.ask_llm("Kết quả là gì?", ev, n=1, runtime_fingerprint="fp-b")

    assert first == second == third
    assert len(calls) == 2, "cùng identity phải hit; đổi fingerprint phải miss"
    files = list(tmp_path.glob("*.json"))
    assert len(files) == 2
    record = json.loads(files[0].read_text(encoding="utf-8"))
    assert set(record["identity"]) >= {
        "query_sha256", "llm", "prompt_version", "config_snapshot",
        "evidence_digest", "runtime_fingerprint",
    }


def test_image_fallback_khong_duoc_ghi_de_digest_khi_ket_qua_van_tu_text(monkeypatch):
    from backend.tasks import qa

    hit = ShotHit("L21_V001#s1", .9, "L21_V001#k10")
    text_ev = qa.Evidence(hit.shot_id, "L21_V001", [], [], "", None, [], 10, "t" * 64)
    image_ev = qa.Evidence(hit.shot_id, "L21_V001", [], [], "", None, [(11, None)], 11,
                           "i" * 64)
    low = qa.QAResult("đỏ", "đỏ", "red", 10, .1, "visual")
    attempt = {"origin": "main", "evidence_hash": text_ev.evidence_hash}
    token = qa._qa_attempt_ctx.set(attempt)

    def fake_collect(*args, **kwargs):
        attempt["evidence_hash"] = image_ev.evidence_hash
        return image_ev

    monkeypatch.setattr(qa, "collect_evidence", fake_collect)
    monkeypatch.setattr(qa, "ask_llm", lambda *a, **kw: [low] if not kw else [])
    try:
        result = qa._infer_legacy("màu gì?", hit, text_ev, "visual")
    finally:
        qa._qa_attempt_ctx.reset(token)

    assert result is not None and result[0] == "đỏ"
    assert attempt["evidence_hash"] == text_ev.evidence_hash


def test_runner_dung_hypotheses_va_fail_missing_evidence(monkeypatch):
    from backend.tasks import qa, runner

    hit = ShotHit("L21_V001#s1", 0.8, "L21_V001#k10")
    hypothesis = qa.QAHypothesis(
        "đỏ", "L21_V001", hit.shot_id, hit.best_keyframe_id, 10,
        0.9, "a" * 64, "main:llm", "visual", "visual_attribute",
    )
    trace = {"hypotheses": [hypothesis.to_dict()], "answer_mode": "visual_attribute"}
    monkeypatch.setattr(qa, "qa_pipeline", lambda *a, **kw: ([hit], "đỏ", trace))
    portfolio = [Answer("L21_V001", (10,), answer_text="đỏ", keyframe_id=hit.best_keyframe_id)]
    import backend.tasks.qa_portfolio as portfolio_module
    monkeypatch.setattr(portfolio_module, "allocate_qa_portfolio", lambda *a, **kw: portfolio)

    result = runner.solve_query(
        {"query_id": "q", "task_type": "QA", "query_vi": "màu gì?"},
        total=1,
        runtime_fingerprint="fp",
    )

    assert result.answers == portfolio
    assert result.qa_hypotheses == [hypothesis.to_dict()]
    assert result.query_plan["answer_mode"] == "visual_attribute"

    monkeypatch.setattr(qa, "qa_pipeline", lambda *a, **kw: ([hit], "", {"hypotheses": []}))
    with pytest.raises(runner.SolveQueryError) as exc:
        runner.solve_query(
            {"query_id": "empty", "task_type": "QA", "query_vi": "gì?"},
            total=1,
            runtime_fingerprint="fp",
        )
    assert exc.value.query_run.failure_class == "missing_evidence"
    assert exc.value.query_run.retryable is True
    assert exc.value.query_run.answers == []
