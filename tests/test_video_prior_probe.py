"""Khoá các bất biến của tiên nghiệm mức video + probe token hiếm (03/09).

Ba thứ ở đây đều là lỗi IM LẶNG nếu hỏng: không crash, chỉ trả bảng nộp sai
thứ tự hoặc mất video. Vì vậy phải có test, không dựa vào việc đọc lại code.
"""
from __future__ import annotations

import pytest

from backend.retrieval.search import _ung_vien_probe, _video_diverse_order


def _row(video_id: str, score: float, vote: float = 0.0, kf: str = "") -> dict:
    return {"video_id": video_id, "score": score, "video_vote": vote,
            "keyframe_id": kf or f"{video_id}#k1"}


def test_xen_ke_khong_them_bot_dong():
    """Bất biến: chỉ ĐỔI THỨ TỰ. Mất một dòng là mất một slot nộp, không báo lỗi."""
    rows = [_row("A", 0.9), _row("A", 0.8), _row("B", 0.7), _row("C", 0.6)]
    ra = _video_diverse_order(rows, alpha=0.5)
    assert len(ra) == len(rows)
    assert sorted(id(r) for r in ra) == sorted(id(r) for r in rows)


def test_xen_ke_moi_video_duoc_luot_truoc_khi_dao_sau():
    """Video B/C phải có mặt trước khi A được dòng thứ hai — sai video là 0 điểm."""
    rows = [_row("A", 0.9), _row("A", 0.85), _row("A", 0.8), _row("B", 0.7), _row("C", 0.6)]
    ra = _video_diverse_order(rows, alpha=0.0)
    assert [r["video_id"] for r in ra[:3]] == ["A", "B", "C"]


def test_giu_dau_bang_khong_bi_xao():
    """Post-mortem đợt 1 mục 2.2a: đầu bảng đắt hơn đuôi, không được xáo."""
    rows = [_row("A", 0.9), _row("A", 0.85), _row("B", 0.7), _row("C", 0.6)]
    ra = _video_diverse_order(rows, alpha=1.0, giu_dau=2)
    assert [r["score"] for r in ra[:2]] == [0.9, 0.85]


def test_ghi_diem_bat_buoc_khi_la_lan_xep_cuoi():
    """`allocate()` và rerank TỰ SẮP LẠI theo `score`.

    Đổi thứ tự list mà không ghi lại `score` thì thứ tự mới bị vứt ở bước sau và
    bật/tắt cho ra kết quả GIỐNG HỆT — lỗi im lặng đã xảy ra một lần với tầng
    rerank (báo cáo K1–K5 §5).
    """
    rows = [_row("A", 0.1), _row("B", 0.9)]
    ra = _video_diverse_order(rows, alpha=0.0, ghi_diem=True)
    diem = [r["score"] for r in ra]
    assert diem == sorted(diem, reverse=True)
    assert all("score_truoc_xen_ke" in r for r in ra)


def test_alpha_ngoai_khoang_bi_tu_choi():
    with pytest.raises(ValueError):
        from backend.retrieval.search import _search_core
        _search_core("x", "y", video_prior_alpha=1.5)


def test_ung_vien_probe_uu_tien_cum_trong_ngoac():
    """Đề hay đặt chữ-trên-màn-hình trong nháy; đó là token đáng probe nhất."""
    ra = _ung_vien_probe("cô giáo giảng động từ 'remember' trên bảng", None)
    assert ra[0] == "remember"


def test_ung_vien_probe_bo_token_qua_ngan():
    """Token ngắn khớp lung tung, probe chúng chỉ tốn truy vấn ES."""
    ra = _ung_vien_probe("xe đi qua ngã tư", None)
    assert all(len(t) >= 4 for t in ra)
