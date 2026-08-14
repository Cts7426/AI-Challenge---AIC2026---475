# tests/test_trake.py — C3.2: TRAKE giai đoạn 1, dữ liệu TỔNG HỢP
#
# Không test trake_stage1() đầu-cuối ở đây (cần Docker ES+Milvus sống — kiểm
# bằng CLI `python -m backend.tasks.trake`, xem docstring đầu file đó). Test ở
# đây nhắm vào 2 hàm thuần logic — chính là chỗ dễ sai chỉ số nhất và không cần
# service nào để kiểm.

from __future__ import annotations

from backend.tasks.trake import _best_per_video, _is_strictly_increasing


# ---------------------------------------------------------------- _best_per_video

def test_best_per_video_lay_diem_cao_nhat():
    hits = [
        {"video_id": "V1", "score": 0.5, "frame_idx": 10},
        {"video_id": "V1", "score": 0.8, "frame_idx": 20},  # cùng video, điểm cao hơn → thắng
        {"video_id": "V2", "score": 0.3, "frame_idx": 5},
    ]
    best = _best_per_video(hits)
    assert best["V1"] == {"score": 0.8, "frame_idx": 20}
    assert best["V2"] == {"score": 0.3, "frame_idx": 5}


def test_best_per_video_rong():
    assert _best_per_video([]) == {}


# ------------------------------------------------------------ _is_strictly_increasing

def test_tang_dan_ngat_true():
    assert _is_strictly_increasing([10, 20, 30])


def test_tang_dan_ngat_false_khi_bang():
    assert not _is_strictly_increasing([10, 10, 30])


def test_tang_dan_ngat_false_khi_giam():
    assert not _is_strictly_increasing([30, 20, 10])


def test_tang_dan_ngat_1_phan_tu_luon_true():
    assert _is_strictly_increasing([10])


def test_tang_dan_ngat_rong_luon_true():
    assert _is_strictly_increasing([])


# --------------------------------------------------- kịch bản gộp điểm video (mô phỏng)

def test_video_khop_ca_N_su_kien_diem_cao_hon_video_khop_1():
    """Đúng Ý ĐỒ log-sum: video có bằng chứng cho CẢ N sự kiện phải thắng video
    chỉ khớp 1 sự kiện dù sự kiện đó khớp rất mạnh — mô phỏng công thức
    video_score = Σ best_shot_score(event_i, video) của trake_stage1()."""
    # sự kiện 1: V1 khớp mạnh (0.9), V2 không khớp
    event1 = _best_per_video([{"video_id": "V1", "score": 0.9, "frame_idx": 100}])
    # sự kiện 2: V1 khớp vừa (0.3), V2 không khớp
    event2 = _best_per_video([{"video_id": "V1", "score": 0.3, "frame_idx": 200}])
    # sự kiện 3: V1 khớp vừa (0.3), V2 không khớp
    event3 = _best_per_video([{"video_id": "V1", "score": 0.3, "frame_idx": 300}])

    per_event = [event1, event2, event3]
    v1_score = sum(e.get("V1", {}).get("score", 0.0) for e in per_event)
    assert v1_score == 0.9 + 0.3 + 0.3

    # Video V2 không khớp sự kiện nào → tổng 0, chắc chắn thua V1 dù V1 không
    # có sự kiện nào khớp "chói loá" bằng đối thủ giả định 0.95 chỉ ở 1 sự kiện
    v_single_strong = 0.95  # video giả định chỉ khớp 1/3 sự kiện nhưng rất mạnh
    assert v1_score > v_single_strong  # phủ rộng thắng chói loá đơn lẻ
