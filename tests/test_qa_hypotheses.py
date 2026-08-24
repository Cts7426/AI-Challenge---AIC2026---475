"""TDD cho Q&A candidate-specific hypotheses và portfolio evidence-first."""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from backend.slot import ShotHit
from data.config.submit_format import Answer


def _fake_inference_with_hash(qa, result, digest: str = "f" * 64):
    """Test double explicit: production không tự tổng hợp evidence digest."""
    if result is not None:
        attempt = qa._qa_attempt_ctx.get()
        assert attempt is not None
        attempt.update({
            "evidence_hash": digest,
            "evidence_type": "test",
            "evidence_stage": "text",
        })
    return result


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
            seen.append((evidence_type, needs_images))
            or _fake_inference_with_hash(qa, ("đỏ", 10, .9)),
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
        return _fake_inference_with_hash(qa, ("Hà Nội", 10, 0.9))

    monkeypatch.setattr(qa, "_try_shot", fake_try)
    monkeypatch.setattr(qa, "_keyframe_id_for_frame", lambda *a, **kw: "L21_V001#k10")
    monkeypatch.setattr(qa, "load_frame_map", lambda: {"L21_V001#k10": 10})

    _, _, trace = qa.qa_pipeline("câu hỏi", return_trace=True)

    assert seen == [("asr", False)]
    assert trace["answer_mode"] == "asr"


def test_main_tu_tin_cao_van_thu_het_video_expansion_budget(monkeypatch):
    from backend.tasks import qa

    monkeypatch.setattr(
        qa, "parse_question",
        lambda query: qa.QuestionParts("sự kiện", "câu hỏi", "asr"),
    )
    main = {"shot_id": "L21_V001#s1", "score": .9, "keyframe_id": "L21_V001#k10"}
    expanded = ShotHit("L21_V001#s2", .5, "L21_V001#k20")
    monkeypatch.setattr(qa, "search", lambda *a, **kw: [main])
    monkeypatch.setattr(qa, "_expand_within_video", lambda *a, **kw: [expanded])
    fmap = {"L21_V001#k10": 10, "L21_V001#k20": 20}
    monkeypatch.setattr(qa, "load_frame_map", lambda: fmap)
    qa._reverse_frame_map.cache_clear()

    def fake_try(hit, *args, **kwargs):
        attempt = qa._qa_attempt_ctx.get()
        assert attempt is not None
        attempt["evidence_hash"] = ("a" if hit.shot_id.endswith("s1") else "b") * 64
        return ("đỏ", 10, .99) if hit.shot_id.endswith("s1") else ("xanh", 20, .8)

    monkeypatch.setattr(qa, "_try_shot", fake_try)
    try:
        _, answer, trace = qa.qa_pipeline("câu hỏi", return_trace=True)
    finally:
        qa._reverse_frame_map.cache_clear()

    assert answer == "đỏ"
    assert [item["shot_id"] for item in trace["hypotheses"]] == [
        "L21_V001#s1", "L21_V001#s2",
    ]


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


@pytest.mark.parametrize(
    "answer",
    [
        "Không đủ căn cứ để trả lời",
        "Không có thông tin trong bằng chứng",
        "No information is available",
        "Insufficient evidence to determine this",
    ],
)
def test_sentinel_prefix_surface_bi_loai(answer):
    from backend.tasks.qa import is_valid_qa_answer

    assert is_valid_qa_answer(answer) is False


@pytest.mark.parametrize(
    "answer",
    [
        'Biển báo ghi "Không có thông tin trong bằng chứng"',
        "No Information Technology",
        "Không có thông tin liên lạc",
    ],
)
def test_sentinel_policy_khong_loai_answer_lien_quan_nhung_hop_le(answer):
    from backend.tasks.qa import is_valid_qa_answer

    assert is_valid_qa_answer(answer) is True


def test_production_khong_duoc_bia_evidence_digest_khi_attempt_thieu_hash():
    from backend.tasks.qa import _evidence_hash_for_attempt, QANoValidHypothesisError

    with pytest.raises(QANoValidHypothesisError, match="evidence_hash"):
        _evidence_hash_for_attempt(
            {}, hit=ShotHit("L21_V001#s1", .9),
        )


def test_wrapper_try_shot_khong_duoc_tu_dong_bat_synthetic_digest(monkeypatch):
    from backend.tasks import qa

    monkeypatch.setattr(
        qa, "parse_question", lambda query: qa.QuestionParts("sự kiện", "câu hỏi", "asr")
    )
    monkeypatch.setattr(qa, "search", lambda *a, **kw: [{
        "shot_id": "L21_V001#s1", "score": .9, "keyframe_id": "L21_V001#k10",
    }])
    monkeypatch.setattr(qa, "_try_shot", lambda *a, **kw: ("đỏ", 10, .9))

    with pytest.raises(qa.QANoValidHypothesisError, match="evidence_hash"):
        qa.qa_pipeline("câu hỏi", return_trace=True)


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
    monkeypatch.setattr(
        qa, "_try_shot", lambda *a, **kw: _fake_inference_with_hash(qa, ("đỏ", 10, .9))
    )
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


def test_inference_cache_single_flight_cung_key_chi_goi_llm_mot_lan(tmp_path, monkeypatch):
    from backend.tasks import qa

    monkeypatch.setenv("QA_HYPOTHESIS_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("LLM_BACKEND", "local")
    monkeypatch.setenv("LLM_LOCAL_MODEL", "qa-model")
    ev = qa.Evidence("L21_V001#s1", "L21_V001", ["42"], [], "", None, [], 10, "e" * 64)
    raw = json.dumps({
        "answer": "42", "answer_vi": "42", "answer_en": "42",
        "evidence_frame_idx": 10, "confidence": .9,
    })
    calls = 0
    calls_lock = threading.Lock()
    gate = threading.Barrier(2)

    def fake_llm(*args, **kwargs):
        nonlocal calls
        with calls_lock:
            calls += 1
        time.sleep(.05)
        return raw

    monkeypatch.setattr(qa, "llm", fake_llm)

    def invoke():
        gate.wait()
        return qa.ask_llm("Kết quả là gì?", ev, n=1, runtime_fingerprint="fp")

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(invoke) for _ in range(2)]
        outputs = [future.result(timeout=5) for future in futures]

    assert outputs[0] == outputs[1]
    assert calls == 1
    assert qa._qa_cache_lock_count() == 0


def test_planner_cache_single_flight_cung_key_chi_goi_llm_mot_lan(tmp_path, monkeypatch):
    from backend.tasks import qa

    monkeypatch.setenv("QA_HYPOTHESIS_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("LLM_BACKEND", "local")
    monkeypatch.setenv("LLM_LOCAL_MODEL", "qa-model")
    raw = json.dumps({
        "event_vi": "sự kiện", "question_vi": "màu gì?",
        "answer_mode": "visual_attribute",
    })
    calls = 0
    calls_lock = threading.Lock()
    gate = threading.Barrier(2)

    def fake_llm(*args, **kwargs):
        nonlocal calls
        with calls_lock:
            calls += 1
        time.sleep(.05)
        return raw

    monkeypatch.setattr(qa, "llm", fake_llm)

    def invoke():
        token = qa._qa_runtime_fingerprint_ctx.set("fp")
        try:
            gate.wait()
            return qa.parse_question("màu gì?")
        finally:
            qa._qa_runtime_fingerprint_ctx.reset(token)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(invoke) for _ in range(2)]
        outputs = [future.result(timeout=5) for future in futures]

    assert outputs[0] == outputs[1]
    assert calls == 1
    assert qa._qa_cache_lock_count() == 0


def test_inference_cache_tach_hai_full_query_cung_planned_question(tmp_path, monkeypatch):
    from backend.tasks import qa

    monkeypatch.setenv("QA_HYPOTHESIS_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("LLM_BACKEND", "local")
    monkeypatch.setenv("LLM_LOCAL_MODEL", "qa-model")
    ev = qa.Evidence("L21_V001#s1", "L21_V001", ["42"], [], "", None, [], 10, "e" * 64)
    raw = json.dumps({
        "answer": "42", "answer_vi": "42", "answer_en": "42",
        "evidence_frame_idx": 10, "confidence": .9,
    })
    calls = []
    monkeypatch.setattr(qa, "llm", lambda *a, **kw: calls.append(1) or raw)

    token_a = qa._qa_full_query_hash_ctx.set("a" * 64)
    try:
        qa.ask_llm("Kết quả là gì?", ev, n=1, runtime_fingerprint="fp")
    finally:
        qa._qa_full_query_hash_ctx.reset(token_a)
    token_b = qa._qa_full_query_hash_ctx.set("b" * 64)
    try:
        qa.ask_llm("Kết quả là gì?", ev, n=1, runtime_fingerprint="fp")
    finally:
        qa._qa_full_query_hash_ctx.reset(token_b)

    assert calls == [1, 1]
    identities = [json.loads(path.read_text(encoding="utf-8"))["identity"]
                  for path in tmp_path.glob("*.json")]
    assert {item["full_query_sha256"] for item in identities} == {"a" * 64, "b" * 64}


def test_qa_pipeline_set_reset_full_query_hash_context(monkeypatch):
    from backend.tasks import qa

    seen = []

    def fake_impl(query_vi, *args, **kwargs):
        seen.append(qa._qa_full_query_hash_ctx.get())
        return [], "x"

    monkeypatch.setattr(qa, "_qa_pipeline_impl", fake_impl)
    qa.qa_pipeline("truy vấn đầy đủ A")

    assert seen == [qa.hashlib.sha256("truy vấn đầy đủ A".encode("utf-8")).hexdigest()]
    assert qa._qa_full_query_hash_ctx.get() == ""


def test_image_fallback_khong_duoc_ghi_de_digest_khi_ket_qua_van_tu_text(monkeypatch):
    from backend.tasks import qa

    hit = ShotHit("L21_V001#s1", .9, "L21_V001#k10")
    text_ev = qa.Evidence(hit.shot_id, "L21_V001", [], [], "", None, [], 10, "t" * 64)
    image_ev = qa.Evidence(hit.shot_id, "L21_V001", [], [], "", None, [(11, None)], 11,
                           "i" * 64)
    low = qa.QAResult("đỏ", "đỏ", "red", 10, .1, "visual")
    attempt = {
        "origin": "main", "evidence_hash": text_ev.evidence_hash,
        "evidence_type": "ocr", "evidence_stage": "text",
    }
    token = qa._qa_attempt_ctx.set(attempt)

    def fake_collect(*args, **kwargs):
        attempt["evidence_hash"] = image_ev.evidence_hash
        attempt["evidence_type"] = "visual"
        attempt["evidence_stage"] = "image"
        return image_ev

    monkeypatch.setattr(qa, "collect_evidence", fake_collect)
    monkeypatch.setattr(qa, "ask_llm", lambda *a, **kw: [low] if not kw else [])
    try:
        result = qa._infer_legacy("màu gì?", hit, text_ev, "visual")
    finally:
        qa._qa_attempt_ctx.reset(token)

    assert result is not None and result[0] == "đỏ"
    assert attempt["evidence_hash"] == text_ev.evidence_hash
    assert attempt["evidence_type"] == "ocr"
    assert attempt["evidence_stage"] == "text"


@pytest.mark.parametrize("mode", ["legacy", "two_stage"])
def test_image_fallback_frames_rong_khoi_phuc_provenance_text(mode, monkeypatch):
    from backend.tasks import qa

    hit = ShotHit("L21_V001#s1", .9, "L21_V001#k10")
    text_ev = qa.Evidence(hit.shot_id, "L21_V001", [], [], "", None, [], 10, "t" * 64)
    empty_image_ev = qa.Evidence(hit.shot_id, "L21_V001", [], [], "", None, [], 10,
                                 "i" * 64)
    low = qa.QAResult("đỏ", "đỏ", "red", 10, .1, "ocr")
    attempt = {
        "origin": "main", "evidence_hash": text_ev.evidence_hash,
        "evidence_type": "ocr", "evidence_stage": "text",
    }
    token = qa._qa_attempt_ctx.set(attempt)

    def fake_collect(*args, **kwargs):
        attempt.update({
            "evidence_hash": empty_image_ev.evidence_hash,
            "evidence_type": "visual",
            "evidence_stage": "image",
        })
        return empty_image_ev

    monkeypatch.setattr(qa, "collect_evidence", fake_collect)
    monkeypatch.setattr(qa, "ask_llm", lambda *a, **kw: [low])
    try:
        if mode == "legacy":
            qa._infer_legacy("màu gì?", hit, text_ev, "ocr")
        else:
            qa._infer_two_stage("màu gì?", hit, text_ev, "ocr")
    finally:
        qa._qa_attempt_ctx.reset(token)

    assert attempt["evidence_hash"] == text_ev.evidence_hash
    assert attempt["evidence_type"] == "ocr"
    assert attempt["evidence_stage"] == "text"


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


def test_runtime_fingerprint_phu_code_qa_portfolio(monkeypatch):
    from backend.tasks import runner

    manifest = runner.runtime_manifest()
    portfolio_path = "backend/tasks/qa_portfolio.py"
    assert portfolio_path in manifest["critical_sources_sha256"]

    before = runner.runtime_fingerprint()
    original_source_hash = runner._source_hash

    def changed_hash(path):
        if path.as_posix().endswith(portfolio_path):
            return "0" * 64
        return original_source_hash(path)

    monkeypatch.setattr(runner, "_source_hash", changed_hash)
    assert runner.runtime_fingerprint() != before


def test_visual_count_persist_cache_identity_de_release_replay(monkeypatch, tmp_path):
    """Detector không gọi provider nhưng vẫn phải có cache record cùng evidence/runtime."""
    from backend.tasks import qa

    cache_dir = tmp_path / "cache"
    monkeypatch.setenv("QA_HYPOTHESIS_CACHE_DIR", str(cache_dir))
    monkeypatch.delenv("LLM_NO_CACHE", raising=False)
    monkeypatch.setattr(
        qa, "parse_question",
        lambda _: qa.QuestionParts("sự kiện", "Có bao nhiêu người?", "visual_count"),
    )
    monkeypatch.setattr(qa, "search", lambda *a, **kw: [{
        "shot_id": "L21_V001#s1", "score": .9, "keyframe_id": "L21_V001#k10",
    }])
    monkeypatch.setattr(qa, "_expand_within_video", lambda *a, **kw: [])
    evidence_digest = "d" * 64
    monkeypatch.setattr(qa, "collect_evidence", lambda *a, **kw: qa.Evidence(
        "L21_V001#s1", "L21_V001", [], [], "", 3, [], 10, evidence_digest,
    ))
    monkeypatch.setattr(qa, "load_frame_map", lambda: {"L21_V001#k10": 10})
    qa._reverse_frame_map.cache_clear()
    try:
        _, answer, trace = qa.qa_pipeline(
            "Có bao nhiêu người trong sự kiện?", return_trace=True,
            runtime_fingerprint="r" * 64,
        )
    finally:
        qa._reverse_frame_map.cache_clear()

    assert answer == "3"
    records = [json.loads(path.read_text(encoding="utf-8")) for path in cache_dir.glob("*.json")]
    detector = next(record for record in records if record["identity"].get("cache_kind") == "detector")
    identity = detector["identity"]
    assert identity["evidence_digest"] == evidence_digest
    assert identity["runtime_fingerprint"] == "r" * 64
    assert identity["query_sha256"] == qa.hashlib.sha256(
        "Có bao nhiêu người?".encode("utf-8")
    ).hexdigest()
    assert identity["full_query_sha256"] == qa.hashlib.sha256(
        "Có bao nhiêu người trong sự kiện?".encode("utf-8")
    ).hexdigest()
    assert detector["provenance"] == trace["hypotheses"][0]["provenance"]
