# tests/test_trake.py — C3.2/C4.4: TRAKE hợp nhất, dữ liệu TỔNG HỢP
#
# Không test trake_search() đầu-cuối ở đây (cần Docker ES+Milvus sống — kiểm
# bằng CLI `python -m backend.tasks.trake`, xem docstring đầu file đó). Test ở
# đây nhắm vào các hàm thuần logic — chính là chỗ dễ sai chỉ số nhất và không
# cần service nào để kiểm.

from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.tasks.trake import (
    TrakeCandidate,
    _align_events_in_video,
    _alternative_frame_sets,
    _apply_asr_context_bonus,
    _cross_event_bonus,
    _fill_missing,
    _localize_in_video,
    _significant_tokens,
    _split_events_heuristic,
    _topk_per_video,
    _repair_strictly_increasing,
    _UnitWeight,
    pad_answers,
    parse_events,
    to_answers,
    trake_search,
)

# --------------------------------------------------------------- _topk_per_video

def test_topk_giu_nhieu_ung_vien_khong_chi_1():
    hits = [
        {"video_id": "V1", "score": 0.5, "frame_idx": 10, "keyframe_id": "a"},
        {"video_id": "V1", "score": 0.8, "frame_idx": 20, "keyframe_id": "b"},
        {"video_id": "V1", "score": 0.3, "frame_idx": 30, "keyframe_id": "c"},
        {"video_id": "V2", "score": 0.3, "frame_idx": 5, "keyframe_id": "d"},
    ]
    out = _topk_per_video(hits, k=2)
    # V1 giữ 2 ứng viên điểm cao nhất (0.8, 0.5), SẮP LẠI theo frame_idx tăng dần
    assert [c["frame_idx"] for c in out["V1"]] == [10, 20]
    assert [c["frame_idx"] for c in out["V2"]] == [5]


def test_topk_bo_hit_khong_co_frame_idx():
    hits = [
        {"video_id": "V1", "score": 0.9, "frame_idx": None, "keyframe_id": "a"},
        {"video_id": "V1", "score": 0.5, "frame_idx": 10, "keyframe_id": "b"},
    ]
    out = _topk_per_video(hits, k=5)
    assert [c["frame_idx"] for c in out["V1"]] == [10]


def test_topk_rong():
    assert _topk_per_video([], k=5) == {}


# ---------------------------------------------------------- _align_events_in_video

def _c(score: float, frame_idx: int, kf: str = "kf") -> dict:
    return {"score": score, "frame_idx": frame_idx, "keyframe_id": kf}


def _trake_candidate(rank: int, n_alternatives: int = 4) -> TrakeCandidate:
    """Dựng ứng viên thuần logic; mỗi phương án có chuỗi frame biết trước."""
    base = (100 + rank * 100, 150 + rank * 100)
    alternatives = tuple(
        (base[0] + depth, base[1] + depth)
        for depth in range(1, n_alternatives + 1)
    )
    return TrakeCandidate(
        video_id=f"V{rank:03d}",
        score=float(100 - rank),
        frame_ids=base,
        keyframe_ids=(f"V{rank:03d}_K1", f"V{rank:03d}_K2"),
        n_hit_events=2,
        has_full_order=True,
        alternatives=alternatives,
    )


# --------------------------------------------------------------- to_answers

def test_to_answers_100_dong_phu_20_video_moi_video_5_phuong_an():
    """Bắt lỗi R3.T1: quay lại một dòng/video hoặc hoãn chiều sâu sau top-5."""
    candidates = [_trake_candidate(rank) for rank in range(30)]

    answers = to_answers(candidates, total=100)

    counts = {
        video_id: sum(answer.video_id == video_id for answer in answers)
        for video_id in {answer.video_id for answer in answers}
    }
    assert len(answers) == 100
    assert len(counts) == 20
    assert set(counts.values()) == {5}
    assert [answer.video_id for answer in answers[:5]] == ["V000"] * 5
    assert len({(answer.video_id, answer.frame_ids) for answer in answers}) == 100
    assert all(a < b for answer in answers for a, b in zip(answer.frame_ids, answer.frame_ids[1:]))


def test_pad_answers_giu_lich_chieu_sau_va_chi_bu_tren_20_video():
    """Bắt lỗi nhánh pad dựng lại từ đầu và làm 100 dòng nở quá 20 video."""
    candidates = [_trake_candidate(rank, n_alternatives=1) for rank in range(30)]
    evidence_rows = to_answers(candidates, total=100)

    with patch("backend.tasks.trake.n_frames_of", return_value=1_000_000):
        answers = pad_answers(candidates, total=100)

    assert answers[:len(evidence_rows)] == evidence_rows
    assert len(answers) == 100
    assert len({answer.video_id for answer in answers}) == 20
    assert len({(answer.video_id, answer.frame_ids) for answer in answers}) == 100
    assert all(a < b for answer in answers for a, b in zip(answer.frame_ids, answer.frame_ids[1:]))


def test_alternative_frame_sets_dao_toi_hang_12_cua_vi_tri_yeu_nhat():
    """Bắt lỗi xoay vòng nông khiến frame đúng sâu trong top-K không được nộp."""
    weak_candidates = [
        _c(score=1.0 - rank / 100, frame_idx=200 + rank * 50, kf=f"weak_{rank}")
        for rank in range(1, 21)
    ]
    other_candidates = [
        _c(score=2.0 - rank / 100, frame_idx=1_200 + rank * 50, kf=f"other_{rank}")
        for rank in range(1, 21)
    ]

    alternatives = _alternative_frame_sets(
        base=[100, 500, 2_500],
        candidates_by_position=[[_c(2.0, 100)], weak_candidates, other_candidates],
        chosen_score_at={0: 2.0, 1: 0.1, 2: 1.0},
        n_frames_video=10_000,
        n_alt=4,
    )

    rank_12_frame = weak_candidates[11]["frame_idx"]
    assert len(alternatives) == 4
    assert all(frames[0] == 100 and frames[2] == 2_500 for frames in alternatives)
    assert rank_12_frame in {frames[1] for frames in alternatives}


def test_alternative_frame_sets_lay_hang_theo_diem_retrieval_goc():
    """Bonus ASR không được làm lệch các mốc độ sâu 1/4/8/12 của top-K."""
    weak_candidates = []
    for rank in range(1, 21):
        candidate = _c(score=float(rank), frame_idx=200 + rank * 50, kf=f"weak_{rank}")
        candidate["_orig_score"] = 1.0 - rank / 100
        weak_candidates.append(candidate)

    alternatives = _alternative_frame_sets(
        base=[100, 500, 2_500],
        candidates_by_position=[[_c(2.0, 100)], weak_candidates, [_c(1.0, 2_500)]],
        chosen_score_at={0: 2.0, 1: 0.1, 2: 1.0},
        n_frames_video=10_000,
        n_alt=4,
    )

    assert weak_candidates[11]["frame_idx"] in {frames[1] for frames in alternatives}


def test_align_chon_dung_moi_vi_tri_1_ung_vien_tang_dan():
    cands = [[_c(0.9, 100, "e1")], [_c(0.3, 200, "e2")], [_c(0.3, 300, "e3")]]
    chain, score = _align_events_in_video(cands)
    assert [j for j, *_ in chain] == [0, 1, 2]
    assert [f for _, f, *_ in chain] == [100, 200, 300]
    assert score == pytest.approx(1.5)


def test_align_khong_duoc_gan_bang_chung_su_kien_sau_vao_vi_tri_truoc():
    """⚠️ Bài học đắt nhất giữ nguyên ở DP: sự kiện 3 khớp SỚM HƠN sự kiện 1
    (false positive, frame 20) — DP tuyệt đối KHÔNG được đưa nó vào vị trí 1
    (đó là việc mà cách "gộp rổ rồi tìm dãy tăng dần bất kỳ" sẽ làm sai).
    Ràng buộc vị trí (j_k < j_i) trong DP loại thẳng khả năng này: sự kiện 3
    (vị trí 2) không thể "nhảy" lên trước sự kiện 1 (vị trí 0)."""
    cands = [
        [_c(0.9, 50, "e1")],    # sự kiện 1: frame 50 (đúng)
        [_c(0.9, 150, "e2")],   # sự kiện 2: frame 150 (đúng)
        [_c(0.9, 20, "e3")],    # sự kiện 3: frame 20 (SAI thứ tự — false positive)
    ]
    chain, score = _align_events_in_video(cands)
    positions = [j for j, *_ in chain]
    # sự kiện 3 (vị trí 2) không thể nối tăng dần sau vị trí 0/1 (20 < 50 < 150)
    # → DP bỏ nó khỏi chuỗi thay vì ép nó lên vị trí 1
    assert 2 not in positions or chain[positions.index(2)][1] > chain[0][1]
    assert 0 in positions and 1 in positions
    frame_of = {j: f for j, f, *_ in chain}
    assert frame_of[0] == 50 and frame_of[1] == 150


def test_align_chon_ung_vien_thu_2_khi_ung_vien_1_pha_thu_tu():
    """Sự kiện 2 có 2 ứng viên: điểm cao nhất (0.9) nằm TRƯỚC sự kiện 1 (phá thứ
    tự), ứng viên thứ 2 (0.4) nằm SAU. DP phải chọn ứng viên thứ 2 để giữ được
    dãy tăng dần đủ 2 vị trí, thay vì bỏ hẳn sự kiện 2 — đây chính là "phương
    án B" mà bản top-1 cũ (EVENT_TOP_K=1) không có."""
    cands = [
        [_c(0.8, 100)],
        [_c(0.9, 50, "sai_thu_tu"), _c(0.4, 150, "dung_thu_tu")],
    ]
    chain, score = _align_events_in_video(cands)
    assert [j for j, *_ in chain] == [0, 1]
    assert chain[1][1] == 150
    assert chain[1][2] == "dung_thu_tu"
    assert score == pytest.approx(0.8 + 0.4)


def test_align_rong():
    chain, score = _align_events_in_video([[], []])
    assert chain == []
    assert score == 0.0


def test_align_bo_qua_vi_tri_thieu_bang_chung():
    cands = [[_c(0.5, 10)], [], [_c(0.5, 60)]]
    chain, score = _align_events_in_video(cands)
    assert [j for j, *_ in chain] == [0, 2]


def test_align_ep_khoang_cach_toi_thieu_giua_2_vi_tri():
    """⚠️ Đo thật (16/08): CLIP trả CÙNG 1 khung hình top-1 cho "đổ muối" lẫn
    "đổ rau" (cách nhau ~19 frame thực tế) — DP tối đa điểm sẽ ghép chúng làm
    "2 sự kiện" nếu không có ràng buộc khoảng cách. min_gap chặn combo chụm
    1 chỗ dù điểm CAO HƠN, buộc DP chọn ứng viên xa hơn (điểm thấp hơn)."""
    cands = [
        [_c(0.9, 100)],                      # sự kiện 1: điểm cao, frame 100
        [_c(0.9, 110), _c(0.3, 500)],        # sự kiện 2: ứng viên gần (110, điểm cao NHƯNG < min_gap) vs xa (500, điểm thấp)
    ]
    chain, score = _align_events_in_video(cands, min_gap=30)
    assert [j for j, *_ in chain] == [0, 1]
    assert chain[1][1] == 500  # buộc chọn ứng viên XA hơn, không phải điểm cao hơn


# ---------------------------------------------------------------- _fill_missing

def test_fill_khong_thieu_gi_tra_nguyen():
    assert _fill_missing([10, 20, 30]) == [10, 20, 30]


def test_fill_noi_suy_giua_2_vi_tri_lan_can():
    assert _fill_missing([10, None, 30]) == [10, 20, 30]


def test_fill_thieu_o_dau_dung_gia_tri_lan_can():
    out = _fill_missing([None, 20, 30])
    assert out[0] == 20 and out[1:] == [20, 30]


def test_fill_thieu_o_cuoi_dung_gia_tri_lan_can():
    out = _fill_missing([10, 20, None])
    assert out[:2] == [10, 20] and out[2] == 20


def test_fill_toan_bo_none_raise():
    with pytest.raises(RuntimeError):
        _fill_missing([None, None, None])


# ---------------------------------------------------------- _repair_strictly_increasing

def test_repair_giu_nguyen_khi_da_tang_dan():
    assert _repair_strictly_increasing([10, 30, 50, 70], 1000) == [10, 30, 50, 70]


def test_repair_day_frame_trung_len_1():
    out = _repair_strictly_increasing([10, 10, 10], 1000)
    assert out == [10, 11, 12]


def test_repair_vuot_do_dai_video_dich_ca_chuoi():
    out = _repair_strictly_increasing([995, 996, 997, 998], 1000)
    assert out[-1] <= 999
    assert all(a < b for a, b in zip(out, out[1:]))


def test_repair_video_qua_ngan_khong_crash():
    out = _repair_strictly_increasing([0, 0, 0, 0, 0], 3)
    assert len(out) == 5
    assert all(0 <= f < 3 for f in out)
    assert out == sorted(out)


# --------------------------------------------------------------- _localize_in_video

def test_localize_du_ca_N_su_kien_tang_dan_duoc_bonus():
    cands = [[_c(0.9, 100, "k1")], [_c(0.3, 200, "k2")], [_c(0.3, 300, "k3")]]
    result = _localize_in_video("L21_V001", cands)
    assert isinstance(result, TrakeCandidate)
    assert result.has_full_order is True
    assert result.frame_ids == (100, 200, 300)
    assert result.keyframe_ids == ("k1", "k2", "k3")
    from data.config.search_weights import TRAKE_MIN_BLEND_LAMBDA, TRAKE_ORDER_BONUS
    # score = (Σ điểm vị trí + λ × điểm vị trí YẾU NHẤT) × bonus — sửa 20/08,
    # xem _blend_score() trong backend/tasks/trake.py + reports/trake_hardening.md
    expected = (0.9 + 0.3 + 0.3 + TRAKE_MIN_BLEND_LAMBDA * 0.3) * TRAKE_ORDER_BONUS
    assert result.score == pytest.approx(expected)


def test_localize_video_khop_ca_N_su_kien_diem_cao_hon_video_khop_1():
    """Đúng Ý ĐỒ log-sum gốc: video có bằng chứng cho CẢ N sự kiện phải thắng
    video chỉ khớp 1 sự kiện dù sự kiện đó khớp rất mạnh — kể cả khi thứ tự
    KHÔNG hoàn hảo (nhánh không-bonus vẫn phải cộng điểm theo độ phủ)."""
    # L21_V011: khớp cả 3 sự kiện, điểm vừa phải, 1 sự kiện phá thứ tự (không bonus)
    v1 = _localize_in_video(
        "L21_V011",
        [[_c(0.6, 100)], [_c(0.6, 200)], [_c(0.6, 50)]],  # sự kiện 3 SỚM hơn sự kiện 1
    )
    assert v1.has_full_order is False
    assert v1.n_hit_events == 3
    # L22_V006 giả định: chỉ khớp 1/3 sự kiện nhưng rất mạnh
    v2 = _localize_in_video("L22_V006", [[_c(0.95, 50)], [], []])
    assert v1.score > v2.score


def test_localize_thieu_bang_chung_mot_vi_tri_noi_suy():
    cands = [[_c(0.5, 100, "k1")], [], [_c(0.5, 300, "k3")]]
    result = _localize_in_video("L21_V001", cands)
    assert result.has_full_order is False
    assert result.keyframe_ids == ("k1", None, "k3")
    assert result.frame_ids[1] == 200  # nội suy tuyến tính giữa 100 và 300
    assert all(a < b for a, b in zip(result.frame_ids, result.frame_ids[1:]))


# ------------------------------------------------------ C4.4: lưới an toàn

def test_split_events_heuristic_uu_tien_dau_cham():
    assert _split_events_heuristic("A . B . C") == ["A", "B", "C"]


def test_split_events_heuristic_lien_tu_tuan_tu():
    out = _split_events_heuristic("người đàn ông bước vào sau đó ngồi xuống ghế")
    assert len(out) == 2
    assert out[0] == "người đàn ông bước vào"
    assert out[1] == "ngồi xuống ghế"


def test_split_events_heuristic_khong_dau_cham_van_ra_it_nhat_2():
    out = _split_events_heuristic("một hai ba bốn năm sáu")
    assert len(out) >= 2


def test_split_events_heuristic_khong_bao_gio_rong():
    out = _split_events_heuristic("một")
    assert len(out) >= 2


def test_parse_events_fallback_khi_llm_loi():
    """C4.4: llm() lỗi (mạng/API) KHÔNG được làm parse_events() raise — quan
    sát thật ở run.py::main(): raise ở đây → câu TRAKE mất trắng khỏi bài nộp
    (0 tuyệt đối), thay vì có cơ hội ăn điểm từng phần nhờ đoán heuristic."""
    with patch("backend.tasks.trake.llm", side_effect=RuntimeError("giả lập mất mạng")):
        events = parse_events(
            "người đàn ông đội mũ bước vào . sau đó ngồi xuống ghế . cuối cùng đứng dậy"
        )
    assert len(events) >= 2


def test_parse_events_duong_binh_thuong_khong_doi():
    """LLM chạy tốt → parse_events() vẫn dùng thẳng kết quả LLM, KHÔNG rơi
    xuống heuristic (đường bình thường không đổi hành vi)."""
    with patch("backend.tasks.trake.llm") as mock_llm:
        mock_llm.return_value = '{"events_vi": ["sự kiện A", "sự kiện B"]}'
        events = parse_events("câu hỏi bất kỳ")
    assert events == ["sự kiện A", "sự kiện B"]


def test_trake_search_fallback_khi_tat_ca_su_kien_rong():
    """C4.4: toàn bộ N search riêng lẻ rỗng (mô phỏng ES/Milvus chết cho mọi
    sự kiện) → trake_search() phải thử tìm kiếm cứu cánh (câu ghép), KHÔNG
    trả [] ngay khi vẫn còn chỗ để tìm."""
    events = ["sự kiện A", "sự kiện B"]

    def fake_search(query_vi, top_k=10, group_by_shot=None, **kw):
        if query_vi in events:
            return []
        return [
            {"video_id": "V1", "score": 0.5, "frame_idx": 100, "keyframe_id": "k1"},
            {"video_id": "V1", "score": 0.4, "frame_idx": 300, "keyframe_id": "k2"},
        ]

    with patch("backend.tasks.trake.search", side_effect=fake_search), \
         patch("backend.tasks.trake.n_frames_of", return_value=10_000_000):
        result = trake_search(events)
    assert result != []
    assert result[0].video_id == "V1"


def test_trake_search_duong_binh_thuong_khong_dung_fallback():
    """Có ≥1 sự kiện search ra kết quả bình thường → KHÔNG kích hoạt nhánh
    cứu cánh (chỉ gọi search() đúng N lần, không có lần ghép câu thứ N+1)."""
    events = ["sự kiện A", "sự kiện B"]
    calls: list[str] = []

    def fake_search(query_vi, top_k=10, group_by_shot=None, **kw):
        calls.append(query_vi)
        return [{"video_id": "V1", "score": 0.5, "frame_idx": 100, "keyframe_id": "k1"}]

    with patch("backend.tasks.trake.search", side_effect=fake_search), \
         patch("backend.tasks.trake.n_frames_of", return_value=10_000_000):
        result = trake_search(events)
    assert result != []
    assert sorted(calls) == sorted(events)  # đúng N lần, không có lần cứu cánh


# ------------------------------------- 20/08: bonus cộng hưởng nội dung ASR

def test_significant_tokens_bo_dau_ha_thuong_loc_hu_tu():
    toks = _significant_tokens("Xe máy va chạm với xe ba gác trên đường")
    assert "xe" not in toks  # 2 ký tự, dưới ngưỡng 3
    assert "may" in toks
    assert "cham" in toks  # "chạm" bỏ dấu
    assert "voi" not in toks  # hư từ


def test_cross_event_bonus_dem_dung_tu_khoa_su_kien_khac():
    """token_weight=_UnitWeight() (mọi từ trọng số 1.0) — tương đương đếm thô,
    để kiểm đúng LOGIC chọn từ (own_position bị loại khỏi other_tokens),
    không lẫn với việc trọng số IDF làm giảm bonus (test riêng bên dưới)."""
    with patch("backend.tasks.trake._asr_text_at",
               return_value="va chạm mạnh làm người đàn ông ngã xuống đường"):
        events_tokens = [
            _significant_tokens("thanh niên điều khiển xe máy"),   # vị trí 0
            _significant_tokens("va chạm mạnh với xe ba gác"),     # vị trí 1 (đang tính bonus CHO vị trí này)
            _significant_tokens("người đàn ông ngã xuống đường"),  # vị trí 2
        ]
        bonus = _cross_event_bonus("V1", 100, own_position=1, events_tokens=events_tokens,
                                    token_weight=_UnitWeight())
    # ASR text trùng từ khoá vị trí 2 ("người","đàn","ông","ngã","xuống","đường")
    # nhưng KHÔNG tính từ khoá của chính vị trí 1 ("va","chạm"... dù cũng xuất
    # hiện trong text — own_position bị loại khỏi other_tokens một cách chủ ý)
    assert bonus > 0


def test_cross_event_bonus_khong_co_asr_tra_0():
    with patch("backend.tasks.trake._asr_text_at", return_value=""):
        bonus = _cross_event_bonus("V1", 100, own_position=0, events_tokens=[{"a"}, {"b"}],
                                    token_weight=_UnitWeight())
    assert bonus == 0


def test_cross_event_bonus_tu_hiem_dong_gop_nhieu_hon_tu_chung_chung():
    """⚠️ Kịch bản Y HỆT bug thật khi chưa có trọng số IDF (đo 20/08): đếm thô
    làm R@1 toàn bộ 8 câu TRAKE dev-set về 0.000 vì từ vựng chung chung (vd
    "cắt", "nước") lặp ở HẦU HẾT ứng viên nấu ăn, nhiễu ngang từ khoá THẬT SỰ
    đặc trưng. Trọng số thấp cho từ chung chung, cao cho từ hiếm → bonus phải
    PHẢN ÁNH ĐÚNG mức đặc trưng, không đếm ngang hàng."""
    token_weight = {"chung": 0.02, "hiem": 1.0}  # "chung" xuất hiện 50 ứng viên, "hiem" chỉ 1
    with patch("backend.tasks.trake._asr_text_at", return_value="tu chung tu hiem"):
        bonus_chung = _cross_event_bonus("V1", 100, own_position=0,
                                          events_tokens=[set(), {"chung"}], token_weight=token_weight)
        bonus_hiem = _cross_event_bonus("V1", 100, own_position=0,
                                         events_tokens=[set(), {"hiem"}], token_weight=token_weight)
    assert bonus_hiem > bonus_chung


def test_build_token_weight_tu_xuat_hien_nhieu_ung_vien_trong_so_thap():
    """Từ "chung" xuất hiện trong ASR của 3 ứng viên (2 video khác nhau) →
    trọng số 1/3. Từ "hiem" chỉ 1 ứng viên → trọng số 1.0 (tối đa)."""
    from backend.tasks.trake import _build_token_weight

    def fake_asr(vid, frame_idx):
        return {("V1", 100): "chung", ("V1", 200): "chung hiem", ("V2", 300): "chung"}.get((vid, frame_idx), "")

    topk_per_event_video = [
        {"V1": [{"frame_idx": 100, "score": 0.1}, {"frame_idx": 200, "score": 0.1}]},
        {"V2": [{"frame_idx": 300, "score": 0.1}]},
    ]
    with patch("backend.tasks.trake._asr_text_at", side_effect=fake_asr):
        weights = _build_token_weight(topk_per_event_video)
    assert weights["chung"] == pytest.approx(1 / 3)
    assert weights["hiem"] == pytest.approx(1.0)


def test_apply_asr_context_bonus_tat_khi_weight_0():
    """TRAKE_ASR_CONTEXT_BONUS_WEIGHT=0 — bonus không được đụng vào candidates
    (kể cả khi có events) — hành vi CŨ y hệt, không đổi gì. Patch tường minh
    về 0, KHÔNG dựa vào giá trị mặc định của config (mặc định thật là 0.5,
    xem data/config/search_weights.py — test này chỉ kiểm NHÁNH TẮT của hàm)."""
    cands = [[{"score": 0.5, "frame_idx": 100, "keyframe_id": "k1"}]]
    with patch("backend.tasks.trake.TRAKE_ASR_CONTEXT_BONUS_WEIGHT", 0.0):
        out = _apply_asr_context_bonus("V1", cands, events=["sự kiện A"])
    assert out is cands  # trả nguyên object, không copy/sửa gì


def test_apply_asr_context_bonus_tat_khi_khong_co_events():
    cands = [[{"score": 0.5, "frame_idx": 100, "keyframe_id": "k1"}]]
    out = _apply_asr_context_bonus("V1", cands, events=None)
    assert out is cands


def test_apply_asr_context_bonus_cong_diem_khi_co_cong_huong():
    """Với weight > 0 và có cộng hưởng ASR: score được CỘNG THÊM, KHÔNG mutate
    dict gốc (an toàn — dict gốc có thể còn dùng ở video/lần gọi khác)."""
    cands = [
        [{"score": 0.5, "frame_idx": 100, "keyframe_id": "k1"}],
        [{"score": 0.5, "frame_idx": 200, "keyframe_id": "k2"}],
    ]
    with patch("backend.tasks.trake.TRAKE_ASR_CONTEXT_BONUS_WEIGHT", 0.1), \
         patch("backend.tasks.trake._asr_text_at", return_value="mô tả sự kiện B ở đây"):
        out = _apply_asr_context_bonus("V1", cands, events=["sự kiện A", "sự kiện B"])
    assert out[0][0]["score"] > 0.5          # vị trí 0: bonus vì text nhắc "sự kiện B"
    assert cands[0][0]["score"] == 0.5        # dict GỐC không bị mutate


def test_localize_in_video_uu_tien_ung_vien_cong_huong_asr_hon_diem_cao():
    """⚠️ Kịch bản Y HỆT bug thật (reports/trake_hardening.md §6): 1 sự kiện
    diễn đạt chung chung có 2 ứng viên hợp lệ cùng thứ tự trong CÙNG video —
    ứng viên ĐÚNG (điểm thấp hơn nhưng văn bản ASR nhắc tới sự kiện khác) và
    ứng viên SAI (điểm cao hơn nhưng thuộc 1 đoạn không liên quan). Với bonus
    cộng hưởng ASR đủ mạnh, DP phải chọn ứng viên ĐÚNG thay vì điểm cao hơn."""
    cands = [
        [{"score": 0.9, "frame_idx": 100, "keyframe_id": "e1"}],
        [
            {"score": 0.02, "frame_idx": 300, "keyframe_id": "dung"},   # ĐÚNG — điểm thấp
            {"score": 0.05, "frame_idx": 900, "keyframe_id": "sai"},    # SAI — điểm cao hơn
        ],
    ]

    def fake_asr_text(vid, frame_idx):
        if frame_idx == 300:
            return "mô tả liên quan tới sự kiện đầu tiên"  # cộng hưởng với event 0
        if frame_idx == 900:
            return "một đoạn hoàn toàn không liên quan"
        return ""

    with patch("backend.tasks.trake.TRAKE_ASR_CONTEXT_BONUS_WEIGHT", 0.1), \
         patch("backend.tasks.trake._asr_text_at", side_effect=fake_asr_text), \
         patch("backend.tasks.trake.n_frames_of", return_value=10_000_000):
        result = _localize_in_video("V1", cands, events=["sự kiện đầu tiên", "sự kiện chung chung"])

    assert result.keyframe_ids[1] == "dung"


def test_localize_in_video_khong_events_giu_hanh_vi_cu():
    """Không truyền events (tương thích ngược, vd test cũ/chỗ gọi khác) →
    _apply_asr_context_bonus() không đụng gì, DP chọn thuần theo điểm gốc —
    xác nhận KHÔNG có ai bị buộc phải truyền events."""
    cands = [
        [{"score": 0.9, "frame_idx": 100, "keyframe_id": "e1"}],
        [
            {"score": 0.02, "frame_idx": 300, "keyframe_id": "thap_diem"},
            {"score": 0.05, "frame_idx": 900, "keyframe_id": "cao_diem"},
        ],
    ]
    with patch("backend.tasks.trake.n_frames_of", return_value=10_000_000):
        result = _localize_in_video("V1", cands)  # KHÔNG truyền events
    assert result.keyframe_ids[1] == "cao_diem"  # thuần theo điểm, đúng hành vi cũ
