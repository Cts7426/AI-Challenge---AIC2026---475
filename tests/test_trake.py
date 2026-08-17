# tests/test_trake.py — C3.2/C4.4: TRAKE hợp nhất, dữ liệu TỔNG HỢP
#
# Không test trake_search() đầu-cuối ở đây (cần Docker ES+Milvus sống — kiểm
# bằng CLI `python -m backend.tasks.trake`, xem docstring đầu file đó). Test ở
# đây nhắm vào các hàm thuần logic — chính là chỗ dễ sai chỉ số nhất và không
# cần service nào để kiểm.

from __future__ import annotations

import pytest

from backend.tasks.trake import (
    TrakeCandidate,
    _align_events_in_video,
    _fill_missing,
    _localize_in_video,
    _repair_strictly_increasing,
    _topk_per_video,
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
    from data.config.search_weights import TRAKE_ORDER_BONUS
    assert result.score == pytest.approx((0.9 + 0.3 + 0.3) * TRAKE_ORDER_BONUS)


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
