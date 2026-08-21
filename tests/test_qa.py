# tests/test_qa.py — C3.1: các quyết định THUẦN LOGIC của pipeline Q&A
#
# Chỉ test phần chạy được KHÔNG cần ES/Milvus/LLM. Phần cần hạ tầng (collect_evidence,
# ask_llm, qa_pipeline đầu-cuối) đo bằng dev_set/tools/run_evaluation.py.
#
# Ba thứ ở đây đều là lỗi IM LẶNG đã đo được ngày 16/08 — không cái nào crash, cả ba
# chỉ làm điểm sai:
#   1. shot sinh ra câu trả lời không được đẩy lên hạng 1  → answer đúng + frame sai
#   2. số shot cấp slot bị buộc chung với số shot suy luận → bỏ trắng 95 slot
#   3. `_object_count` trả 0 khi nhãn không khớp           → nộp answer "0"

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from backend.slot import ShotHit
from backend.tasks.qa import (
    MAX_SHOTS_TRIED,
    TOP_K_SHOTS,
    TOP_K_SHOTS_FOR_SLOTS,
    Evidence,
    QuestionParts,
    _dua_len_dau,
    _expand_within_video,
    _infer_two_stage,
    _keyframe_id_for_frame,
    _reverse_frame_map,
    ask_llm,
    capture_evidence,
    load_evidence_capture,
    qa_pipeline,
    qa_generation_budget,
    validate_evidence_capture,
)
from backend.tasks.qa import QAResult
from data.config.qa_inference import (
    QA_CONFIRM_ADDITIONAL_N,
    QA_LEGACY_MAX_TOKENS,
    QA_TWO_STAGE_MAX_GENERATIONS,
    qa_inference_mode,
)


def _hits(n: int) -> list[ShotHit]:
    """n shot giả, điểm giảm dần như tầng search thật trả về."""
    return [ShotHit(f"s{i}", 1.0 - i * 0.01) for i in range(n)]


@pytest.fixture
def fake_frame_pin(monkeypatch):
    """Pipeline unit test dùng frame giả nhưng vẫn phải qua invariant pin exact."""
    fmap = {}

    def resolve(video_id, frame_idx, *, preferred=None):
        keyframe_id = f"{video_id}#kTEST{frame_idx}"
        fmap[keyframe_id] = int(frame_idx)
        return keyframe_id

    monkeypatch.setattr("backend.tasks.qa._keyframe_id_for_frame", resolve)
    monkeypatch.setattr("backend.tasks.qa.load_frame_map", lambda: fmap)
    return fmap


# ------------------------------- shot thắng phải lên hạng 1 (hai cửa tử độc lập)

def test_shot_thang_duoc_day_len_hang_1():
    """Q&A có hai cửa tử ĐỘC LẬP. Ghép answer của shot #3 với frame của shot #1 là
    tự tay phá cửa frame trong khi cửa answer đã đúng."""
    out = _dua_len_dau(_hits(5), 2)
    assert [h.shot_id for h in out][0] == "s2"


def test_day_len_dau_giu_nguyen_thu_tu_con_lai():
    """Chỉ shot thắng đổi chỗ — phần còn lại giữ đúng thứ hạng search đã xếp."""
    out = _dua_len_dau(_hits(5), 2)
    assert [h.shot_id for h in out] == ["s2", "s0", "s1", "s3", "s4"]


def test_day_len_dau_thang_duoc_ca_sorted_cua_allocator():
    """`allocate()` tự `sorted(hits, key=score, reverse=True)` — đổi chỗ trong list
    KHÔNG đủ, điểm cũng phải cao nhất, nếu không allocator xếp lại như cũ."""
    out = _dua_len_dau(_hits(5), 3)
    theo_diem = sorted(out, key=lambda h: h.score, reverse=True)
    assert theo_diem[0].shot_id == "s3"


def test_day_len_dau_khong_lam_bien_dang_thang_diem():
    """Không bịa điểm to: score_simulator và log phân tích đều đọc `score` thật.
    Chỉ cần nhỉnh hơn đỉnh cũ một khoảng không đáng kể so với thang RRF (~0.01–0.03)."""
    goc = _hits(5)
    out = _dua_len_dau(goc, 4)
    assert out[0].score - max(h.score for h in goc) < 1e-3


def test_day_len_dau_i0_khong_dung_gi():
    goc = _hits(5)
    assert _dua_len_dau(goc, 0) is goc


def test_day_len_dau_giu_nguyen_best_keyframe_id():
    """`best_keyframe_id` là mức ưu tiên ① của allocator — mất nó là mất frame có
    bằng chứng thật của shot thắng."""
    hits = [ShotHit("s0", 0.9), ShotHit("s1", 0.8, "L21_V001#k0007")]
    assert _dua_len_dau(hits, 1)[0].best_keyframe_id == "L21_V001#k0007"


def test_day_len_dau_i0_pin_dung_keyframe_cua_evidence():
    hits = [ShotHit("L21_V001#s0001", 0.9, "L21_V001#k0001")]
    out = _dua_len_dau(hits, 0, winning_keyframe_id="L21_V001#k0002")
    assert out[0].best_keyframe_id == "L21_V001#k0002"
    assert out[0].score == hits[0].score


def test_day_len_dau_promoted_pin_dung_keyframe_cua_evidence():
    hits = [
        ShotHit("L21_V001#s0001", 0.9, "L21_V001#k0001"),
        ShotHit("L21_V001#s0002", 0.8, "L21_V001#k0002"),
    ]
    out = _dua_len_dau(hits, 1, winning_keyframe_id="L21_V001#k0003")
    assert out[0].shot_id == "L21_V001#s0002"
    assert out[0].best_keyframe_id == "L21_V001#k0003"


def test_reverse_frame_map_tra_exact_va_fail_closed(monkeypatch):
    fmap = {
        "L21_V001#k0001": 10,
        "L21_V001_0000010": 10,
        "L21_V001#k0002": 20,
    }
    monkeypatch.setattr("backend.tasks.qa.load_frame_map", lambda: fmap)
    _reverse_frame_map.cache_clear()
    try:
        assert _keyframe_id_for_frame("L21_V001", 10) == "L21_V001#k0001"
        with pytest.raises(RuntimeError, match="không có keyframe"):
            _keyframe_id_for_frame("L21_V001", 11)
    finally:
        _reverse_frame_map.cache_clear()


# ------------------------- số shot suy luận TÁCH khỏi số shot cấp slot

def test_so_shot_cap_slot_tach_khoi_so_shot_suy_luan():
    """Suy luận tốn 3–6 lần gọi LLM mỗi shot nên phải ít. Cấp slot KHÔNG tốn gì
    nên phải nhiều. Buộc chung một hằng là bỏ trắng 95 slot miễn phí."""
    assert TOP_K_SHOTS_FOR_SLOTS > TOP_K_SHOTS
    assert TOP_K_SHOTS_FOR_SLOTS >= 100, "phải đủ shot để allocator phủ rộng"


def test_chi_MAX_SHOTS_TRIED_shot_duoc_suy_luan():
    """Nâng số shot cấp slot KHÔNG được kéo theo chi phí LLM."""
    assert MAX_SHOTS_TRIED <= TOP_K_SHOTS


def test_100_shot_phu_rong_hon_han_5_shot():
    """Bằng chứng cho lý do TOP_K_SHOTS_FOR_SLOTS tách khỏi TOP_K_SHOTS: chỉ 5 shot
    ứng viên thì one-fifth cả bài nộp (>=20/100 dòng) dồn vào MỘT shot — rủi ro
    cao nếu shot đó sai — trong khi 100 shot ứng viên phủ rộng hơn hẳn.

    ⚠️ SỬA 18/08: không còn pin con số "22" — đó là số của bảng SLOT_BUDGET đợt
    trước D4.1 (17/08) và cách chia round-robin cũ. San bằng shot thấp nhất
    trước (data/config/slot_budget.py::budget_per_shot) làm 5 shot chia ĐỀU
    đúng 20 mỗi shot với bảng hiện tại (100/5 chia hết) — max luôn >= 20 bởi
    nguyên lý chuồng bồ câu (pigeonhole) bất kể bảng SLOT_BUDGET đổi ra sao,
    nên dùng mốc đó thay vì hardcode số của một bảng cụ thể."""
    from data.config.slot_budget import budget_per_shot

    it, nhieu = budget_per_shot(5), budget_per_shot(TOP_K_SHOTS_FOR_SLOTS)
    assert max(it) >= 20, "bằng chứng: 5 shot thì 1 shot ôm ít nhất 1/5 cả bài nộp"
    assert sum(1 for x in nhieu if x) > 6 * sum(1 for x in it if x)


# --------------------- query_en của CẢ CÂU không được lẫn vào search(event_vi)

def test_qa_pipeline_khong_dua_query_en_cau_goc_cho_search_khi_event_vi_khac(fake_frame_pin):
    """⚠️ SỬA 20/08 — bug phát hiện qua QA_004 (holdout): mọi chỗ gọi production
    (run.py, backend/api/main.py...) truyền `query_en` là bản dịch CẢ CÂU HỎI
    GỐC, không phải bản dịch của `event_vi` (câu `parse_question()` tách ra).
    Đưa thẳng vào `search(event_vi, query_en=...)` làm CLIP so khớp giữa một
    câu tiếng Việt và một câu tiếng Anh KHÔNG cùng nghĩa."""
    parts = QuestionParts(event_vi="ô tô văng xuống ruộng lúa", question_vi="Cách mặt đường bao xa?")
    with patch("backend.tasks.qa.parse_question", return_value=parts), \
         patch("backend.tasks.qa.route_question", return_value=("default", False)), \
         patch("backend.tasks.qa.search", return_value=[
             {"shot_id": "s0", "score": 1.0, "keyframe_id": "k0"}
         ]) as mock_search, \
         patch("backend.tasks.qa._try_shot", return_value=("30m", 5, 0.95)):
        qa_pipeline("Ô tô văng xuống ruộng lúa cách mặt đường bao xa?",
                    query_en="How far from the road did the car land?")
    assert mock_search.call_args.kwargs["query_en"] is None


def test_qa_pipeline_giu_query_en_khi_parse_question_khong_tach_duoc(fake_frame_pin):
    """`parse_question()` fallback (không tách được) trả event_vi == query_vi gốc
    — lúc đó query_en của caller CHẮC CHẮN đúng nghĩa event_vi, tái dùng được
    để đỡ một lượt dịch."""
    query_vi = "Câu hỏi khó tách"
    parts = QuestionParts(event_vi=query_vi, question_vi=query_vi)
    with patch("backend.tasks.qa.parse_question", return_value=parts), \
         patch("backend.tasks.qa.route_question", return_value=("default", False)), \
         patch("backend.tasks.qa.search", return_value=[
             {"shot_id": "s0", "score": 1.0, "keyframe_id": "k0"}
         ]) as mock_search, \
         patch("backend.tasks.qa._try_shot", return_value=("30m", 5, 0.95)):
        qa_pipeline(query_vi, query_en="Hard to split question")
    assert mock_search.call_args.kwargs["query_en"] == "Hard to split question"


# ------------------- mở rộng trong video khi vòng chính không đủ tin cậy

def test_expand_within_video_dung_filter_video_id_va_loc_shot_da_thu():
    """`_expand_within_video` phải gọi search() ép TRONG video đã cho, và loại
    bỏ shot đã thử ở vòng chính (không tốn lại 1 lượt LLM cho evidence đã biết
    không đủ tin cậy)."""
    with patch("backend.tasks.qa.search", return_value=[
        {"shot_id": "L21_V001#s0005", "score": 0.9, "keyframe_id": "k1"},
        {"shot_id": "L21_V001#s0009", "score": 0.8, "keyframe_id": "k2"},  # đã thử — bị loại
    ]) as mock_search:
        out = _expand_within_video("L21_V001", "câu hỏi đầy đủ", None, {"L21_V001#s0009"})
    assert mock_search.call_args.kwargs["filter_video_id"] == "L21_V001"
    assert [h.shot_id for h in out] == ["L21_V001#s0005"]


def test_qa_pipeline_mo_rong_trong_video_cuu_duoc_cau_tra_loi(fake_frame_pin):
    """⚠️ SỬA 21/08 — phát hiện qua "dress rehearsal" (25 câu tự sinh chạy qua
    đúng pipeline production, đêm 20/08): search(event_vi) đúng VIDEO nhưng SAI
    SHOT (event_vi thuần thị giác không phân biệt được hai cảnh giống nhau
    trong cùng video). Vòng chính CHỈ có 1 shot của video đúng, `_try_shot` trả
    None (không đủ tin cậy) — mở rộng trong đúng video đó phải tìm ra shot khác
    chứa bằng chứng thật và cứu được câu trả lời."""
    parts = QuestionParts(event_vi="cận cảnh rau", question_vi="Giá tàu lá là bao nhiêu?")
    main_shot = {"shot_id": "L28_V016#s0058", "score": 0.13, "keyframe_id": "k1"}
    extra_shot = {"shot_id": "L28_V016#s0099", "score": 0.05, "keyframe_id": "k2"}

    def fake_search(query, query_en=None, top_k=100, group_by_shot=True, filter_video_id=None):
        if filter_video_id == "L28_V016":
            return [extra_shot]
        return [main_shot]

    def fake_try_shot(hit, question_vi, evidence_type, needs_images):
        if hit.shot_id == "L28_V016#s0099":
            return "300 và 350", 9500, 0.95
        return None  # shot chính không đủ tin cậy

    with patch("backend.tasks.qa.parse_question", return_value=parts), \
         patch("backend.tasks.qa.route_question", return_value=("default", False)), \
         patch("backend.tasks.qa.search", side_effect=fake_search), \
         patch("backend.tasks.qa._try_shot", side_effect=fake_try_shot):
        hits, answer = qa_pipeline("Cận cảnh rau. Giá tàu lá là bao nhiêu?",
                                    query_en="How much are the leaves?")

    assert answer == "300 và 350"
    assert hits[0].shot_id == "L28_V016#s0099"


# --------------------------------------------------- effort của bước suy luận

def test_ask_llm_dung_effort_high():
    """SỬA 18/08 — adapter.py (DEFAULT_EFFORT) ghi rõ ý đồ thiết kế: "Task nào
    cần nghĩ kỹ (Q&A suy luận) thì tự truyền effort='high'". ask_llm() CHÍNH LÀ
    bước đó nhưng trước bản sửa không hề truyền — luôn chạy effort THẤP NHẤT
    (mặc định của llm(), dành cho dịch/mở rộng câu ngắn) trên backend "api"
    (Claude — backend dùng lúc thi thật). Không crash (effort="low" vẫn hợp
    lệ) nên không lộ qua test hạ tầng nào khác — lỗi CHẤT LƯỢNG câu trả lời im
    lặng, chỉ mock trực tiếp mới bắt được mà không cần ES/Milvus/LLM thật."""
    ev = Evidence(
        shot_id="s0", video_id="V1", ocr_texts=[], asr_texts=[],
        metadata_text="", object_count=None, frames=[], best_frame_idx=10,
    )
    fake = '{"answer": "5", "answer_vi": "5", "answer_en": "5", ' \
           '"evidence_frame_idx": 10, "confidence": 0.9}'
    with patch("backend.tasks.qa.llm", return_value=fake) as m:
        ask_llm("câu hỏi bất kỳ", ev)
    assert m.call_args.kwargs.get("effort") == "high"
    assert m.call_args.kwargs.get("max_tokens") == 2048
    assert QA_LEGACY_MAX_TOKENS == 2048


def _qa_result(answer: str, confidence: float, frame: int = 10) -> QAResult:
    return QAResult(answer, answer, answer, frame, confidence, "")


def test_two_stage_ca_ro_rang_dung_dung_ba_generation():
    """Một winner rõ: screen n=1 + confirm n=2, không tăng so với legacy n=3."""
    ev = Evidence("s0", "V1", [], [], "", None, [], 10)
    calls = []

    def fake_ask(question, evidence, **kw):
        calls.append((id(evidence), kw["n"], kw["effort"], kw["max_tokens"]))
        return [_qa_result("5", 0.95)] * kw["n"]

    with patch("backend.tasks.qa.ask_llm", side_effect=fake_ask):
        got = _infer_two_stage("bao nhiêu?", ShotHit("s0", 1.0), ev, "default")
    assert got and got[:2] == ("5", 10) and got[2] == pytest.approx(0.95)
    assert [c[1] for c in calls] == [1, 2]
    assert calls[0][0] == calls[1][0], "screen/confirm phải dùng đúng cùng Evidence"
    assert calls[0][2:] == calls[1][2:], "screen/confirm phải cùng effort/max_tokens"


def test_two_stage_doi_evidence_thi_reset_phieu_text():
    """Phiếu text yếu không được trộn với ba phiếu ảnh của cohort mới."""
    text_ev = Evidence("s0", "V1", [], [], "", None, [], 10)
    image_ev = Evidence("s0", "V1", [], [], "", None, [(11, None)], 11)
    seen = []

    def fake_ask(question, evidence, **kw):
        seen.append((bool(evidence.frames), kw["n"]))
        if not evidence.frames:
            return [_qa_result("sai", 0.2, 10)]
        return [_qa_result("đúng", 0.9, 11)] * kw["n"]

    with patch("backend.tasks.qa.ask_llm", side_effect=fake_ask), \
         patch("backend.tasks.qa.collect_evidence", return_value=image_ev):
        got = _infer_two_stage("gì?", ShotHit("s0", 1.0), text_ev, "visual")
    assert got and got[0] == "đúng" and got[1] == 11
    assert got[2] == pytest.approx(0.9), "phiếu text cũ không được làm giảm vote ảnh"
    assert seen == [(False, 1), (True, 1), (True, 2)]


def test_two_stage_bat_dong_screen_confirm_van_vote_dung_mot_cohort():
    """Screen A + confirm B,B phải cho B với 2/3; không reset khi evidence không đổi."""
    ev = Evidence("s0", "V1", [], [], "", None, [], 10)
    calls = []

    def fake_ask(question, evidence, **kw):
        calls.append((id(evidence), kw["effort"], kw["max_tokens"], kw["n"]))
        if kw["n"] == 1:
            return [_qa_result("A", 0.9)]
        return [_qa_result("B", 0.9), _qa_result("B", 0.9)]

    with patch("backend.tasks.qa.ask_llm", side_effect=fake_ask):
        got = _infer_two_stage("gì?", ShotHit("s0", 1.0), ev, "default")
    assert got == ("B", 10, pytest.approx(0.6))
    assert calls[0][:3] == calls[1][:3]


def test_two_stage_thieu_mot_confirm_thi_khong_chot():
    ev = Evidence("s0", "V1", [], [], "", None, [], 10)
    with patch(
        "backend.tasks.qa.ask_llm",
        side_effect=[[_qa_result("A", 0.9)], [_qa_result("A", 0.9)]],
    ):
        assert _infer_two_stage("gì?", ShotHit("s0", 1.0), ev, "default") is None


def test_two_stage_shot_yeu_khong_goi_confirm():
    """Shot yếu không có ảnh chỉ tốn 1 generation thay vì legacy 3."""
    ev = Evidence("s0", "V1", [], [], "", None, [], 10)
    with patch("backend.tasks.qa.ask_llm", return_value=[_qa_result("đoán", 0.1)]) as ask, \
         patch("backend.tasks.qa.collect_evidence", return_value=ev):
        assert _infer_two_stage("gì?", ShotHit("s0", 1.0), ev, "default") is None
    assert ask.call_count == 1
    assert ask.call_args.kwargs["n"] == 1


def test_two_stage_cap_42_phu_text_main_image_va_expansion(monkeypatch, fake_frame_pin):
    """Mọi origin dùng chung một budget; lượt thứ 43 bị chặn trước khi gọi llm()."""
    monkeypatch.setenv("QA_INFERENCE_MODE", "two_stage")
    monkeypatch.delenv("QA_EVIDENCE_LOG_PATH", raising=False)
    monkeypatch.setattr(
        "backend.tasks.qa.parse_question",
        lambda q: QuestionParts("sự kiện", "câu hỏi"),
    )
    monkeypatch.setattr("backend.tasks.qa.route_question", lambda q: ("default", False))

    main = [
        {"shot_id": f"M{i}#s0001", "score": 1.0 - i / 100, "keyframe_id": f"M{i}#k0001"}
        for i in range(5)
    ]
    text_hits = [ShotHit(f"T{i}#s0001", 0.5, f"T{i}#k0001") for i in range(5)]
    monkeypatch.setattr("backend.tasks.qa.search", lambda *a, **kw: main)
    monkeypatch.setattr("backend.tasks.qa._ung_vien_nhanh_text", lambda *a, **kw: text_hits)
    monkeypatch.setattr(
        "backend.tasks.qa._expand_within_video",
        lambda video_id, *a, **kw: [
            ShotHit(f"{video_id}#s00{j + 2:02d}", 0.1, f"{video_id}#k00{j + 2:02d}")
            for j in range(3)
        ],
    )
    monkeypatch.setattr(
        "backend.tasks.qa.collect_evidence",
        lambda hit, *a, **kw: Evidence(hit.shot_id, hit.shot_id.split("#")[0], [], [], "", None, [], 10),
    )
    raw = json.dumps({
        "answer": "x", "answer_vi": "x", "answer_en": "x",
        "evidence_frame_idx": 10, "confidence": 0.6,
    })
    llm_calls = []

    def fake_llm(*args, **kwargs):
        llm_calls.append(kwargs["n"])
        return raw if kwargs["n"] == 1 else [raw] * kwargs["n"]

    monkeypatch.setattr("backend.tasks.qa.llm", fake_llm)
    _, answer, trace = qa_pipeline("câu hỏi", return_trace=True)
    assert answer == "x"
    assert trace["generations_used"] == 42
    assert trace["generation_limit"] == QA_TWO_STAGE_MAX_GENERATIONS == 42
    assert trace["generation_limit_reached"] is True
    assert sum(llm_calls) == 42
    assert llm_calls == [1, QA_CONFIRM_ADDITIONAL_N] * 14


def test_generation_budget_khong_dung_vao_legacy(monkeypatch):
    monkeypatch.setenv("QA_INFERENCE_MODE", "legacy")
    monkeypatch.delenv("QA_EVIDENCE_LOG_PATH", raising=False)
    ev = Evidence("s0", "V1", [], [], "", None, [], 10)
    raw = json.dumps({
        "answer": "x", "answer_vi": "x", "answer_en": "x",
        "evidence_frame_idx": 10, "confidence": 0.9,
    })
    with patch("backend.tasks.qa.llm", return_value=[raw, raw, raw]) as model:
        with qa_generation_budget(limit=1) as budget:
            assert len(ask_llm("gì?", ev, n=3)) == 3
    assert model.call_count == 1
    assert budget.used == 0


def test_qa_mode_resolve_luc_goi_khong_bi_dong_bang_luc_import(monkeypatch):
    monkeypatch.setenv("QA_INFERENCE_MODE", "legacy")
    assert qa_inference_mode() == "legacy"
    monkeypatch.setenv("QA_INFERENCE_MODE", "two_stage")
    assert qa_inference_mode() == "two_stage"
    monkeypatch.setenv("QA_INFERENCE_MODE", "typo")
    with pytest.raises(ValueError, match="không hợp lệ"):
        qa_inference_mode()


def test_evidence_hash_on_dinh_qua_run_id_query_id_va_absolute_path(tmp_path, monkeypatch):
    monkeypatch.setenv("QA_INFERENCE_MODE", "legacy")
    img_a = tmp_path / "root-a" / "frame.jpg"
    img_b = tmp_path / "root-b" / "frame.jpg"
    img_a.parent.mkdir()
    img_b.parent.mkdir()
    img_a.write_bytes(b"same-image-bytes")
    img_b.write_bytes(b"same-image-bytes")
    hit = ShotHit("L21_V001#s0001", 0.9, "L21_V001#k0001")

    log_a = tmp_path / "a.jsonl"
    monkeypatch.setenv("QA_EVIDENCE_LOG_PATH", str(log_a))
    monkeypatch.setenv("LLM_RUN_ID", "run-a")
    monkeypatch.setenv("LLM_QUERY_ID", "query-a")
    ev_a = Evidence("L21_V001#s0001", "L21_V001", [], [], "meta", None, [(10, img_a)], 10)
    hash_a = capture_evidence(hit, "màu gì?", "visual", True, ev_a)

    log_b = tmp_path / "b.jsonl"
    monkeypatch.setenv("QA_EVIDENCE_LOG_PATH", str(log_b))
    monkeypatch.setenv("LLM_RUN_ID", "run-b")
    monkeypatch.setenv("LLM_QUERY_ID", "query-b")
    ev_b = Evidence("L21_V001#s0001", "L21_V001", [], [], "meta", None, [(10, img_b)], 10)
    hash_b = capture_evidence(hit, "màu gì?", "visual", True, ev_b)

    assert hash_a == hash_b
    assert load_evidence_capture(log_a)[0]["schema_version"] == 1
    record_b = load_evidence_capture(log_b)[0]
    assert record_b["run_id"] == "run-b" and record_b["query_id"] == "query-b"
    assert record_b["frames"][0]["path"] != str(img_a)

    captured_b = Evidence(
        "L21_V001#s0001", "L21_V001", [], [], "meta", None,
        [(10, img_b)], 10, hash_b,
    )
    raw = json.dumps({
        "answer": "đỏ", "answer_vi": "đỏ", "answer_en": "red",
        "evidence_frame_idx": 10, "confidence": 0.9,
    })
    with patch("backend.tasks.qa.llm", return_value=raw):
        ask_llm("màu gì?", captured_b, n=1, usage_tag="qa.legacy.image")
    stats = validate_evidence_capture(log_b, expected_query_ids={"query-b"})
    records = load_evidence_capture(log_b)
    output = next(r for r in records if r["record_type"] == "inference")
    assert stats == {"records": 2, "evidence_records": 1, "inference_records": 1}
    assert output["stage"] == "qa.legacy.image"
    assert output["outputs"][0]["answer"] == "đỏ"

    tampered = tmp_path / "tampered.jsonl"
    tampered_records = [dict(r) for r in records]
    tampered_records[-1] = json.loads(json.dumps(tampered_records[-1], ensure_ascii=False))
    tampered_records[-1]["outputs"][0]["answer"] = "xanh"
    tampered.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in tampered_records) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="output_hash"):
        load_evidence_capture(tampered)


def test_capture_fail_closed_khi_thieu_digest_hoac_khong_ghi_duoc(tmp_path, monkeypatch):
    monkeypatch.setenv("QA_INFERENCE_MODE", "legacy")
    hit = ShotHit("L21_V001#s0001", 0.9, "L21_V001#k0001")
    missing = tmp_path / "missing.jpg"
    ev_missing = Evidence("L21_V001#s0001", "L21_V001", [], [], "", None, [(10, missing)], 10)
    monkeypatch.setenv("QA_EVIDENCE_LOG_PATH", str(tmp_path / "capture.jsonl"))
    with pytest.raises(RuntimeError, match="không đọc được ảnh evidence"):
        capture_evidence(hit, "gì?", "visual", True, ev_missing)

    ev_text = Evidence("L21_V001#s0001", "L21_V001", [], [], "", None, [], 10)
    monkeypatch.setenv("QA_EVIDENCE_LOG_PATH", str(tmp_path))
    with pytest.raises(RuntimeError, match="không ghi bền"):
        capture_evidence(hit, "gì?", "default", False, ev_text)
