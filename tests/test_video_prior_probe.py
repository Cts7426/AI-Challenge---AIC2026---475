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


# --------------------------------------------------------------------------
# Công tắc: probe token hiếm có HAI đầu ra (nhánh mức keyframe + phiếu bầu mức
# video) nhưng là MỘT tính năng, nên phải tắt/bật cùng nhau.
# --------------------------------------------------------------------------

def _chan_moi_nhanh(monkeypatch) -> None:
    """Bịt mọi nhánh + mọi lần chạm Milvus/ES để test `_search_core` thuần logic.

    Chỉ để `vector` trả đúng MỘT hàng: `_search_core` thoát sớm khi không có ứng
    viên nào, mà khối tính phiếu bầu nằm SAU chỗ thoát đó.
    """
    from backend.retrieval import search as S

    mot_hang = [{"keyframe_id": "L21_V001#k1", "video_id": "L21_V001",
                 "frame_idx": 10, "timestamp_ms": 400}]
    monkeypatch.setattr(S, "_branch_vector", lambda *a, **k: list(mot_hang))
    for ten in ("_branch_metadata", "_branch_objects", "_branch_ocr",
                "_branch_ocr_probe", "_branch_asr", "_branch_text_vi"):
        monkeypatch.setattr(S, ten, lambda *a, **k: [])
    monkeypatch.setattr(S, "_fill_from_milvus", lambda candidates: None)
    monkeypatch.setattr(S, "_shot_map", lambda: {})
    monkeypatch.setattr(S, "_shot_of_frame", lambda video_id, frame_idx: None)


def test_tat_nhanh_ocr_probe_thi_phieu_bau_probe_cung_tat(monkeypatch):
    """`branches={'ocr_probe': False}` phải tắt CẢ phiếu bầu mức video của probe.

    Trước bản vá 04/09, chỉ `token_probe.ENABLED` tắt được `_probe_video_votes`;
    công tắc `BRANCHES['ocr_probe']` chỉ gác nhánh mức keyframe. Hệ quả: phép đo
    "bỏ probe ra thì rớt bao nhiêu điểm" vẫn chạy probe ở tầng phiếu bầu và trả
    về số SAI mà không có gì báo — đúng kiểu lỗi im lặng của mục 12 CLAUDE.md.
    """
    import data.config.video_prior as VP
    from backend.retrieval import search as S

    _chan_moi_nhanh(monkeypatch)
    # Phiếu bầu chỉ được tính khi alpha > 0, nên phải bật video_prior lên mới
    # chạm tới được dòng gọi probe.
    monkeypatch.setattr(VP, "ENABLED", True)
    monkeypatch.setattr(VP, "ALPHA", 0.5)

    da_goi: list[tuple] = []

    def probe_gia(query_vi, query_en):
        da_goi.append((query_vi, query_en))
        return {}

    monkeypatch.setattr(S, "_probe_video_votes", probe_gia)

    S._search_core("x", "x", top_k=5, branches={"ocr_probe": False})
    assert not da_goi, "tắt nhánh ocr_probe mà phiếu bầu probe vẫn chạy"

    S._search_core("x", "x", top_k=5, branches={"ocr_probe": True})
    assert len(da_goi) == 1, "bật nhánh ocr_probe thì phiếu bầu probe phải chạy"


def test_finalize_va_search_cung_luat_khi_alpha_bang_khong(monkeypatch):
    """alpha hiệu dụng = 0 thì KHÔNG xen kẽ — ở `_finalize` cũng như `search()`.

    Trước bản vá, `search()` kiểm `a > 0` còn `_finalize` thì không. Đặt
    `ALPHA = 0.0` (cách tắt tự nhiên nhất khi muốn giữ ENABLED) sẽ vẫn xen kẽ ở
    `_finalize` mà không ở `search()`: hai luật khác nhau cho cùng một hàm.
    """
    import data.config.video_prior as VP
    from backend.retrieval import search as S

    monkeypatch.setattr(VP, "ENABLED", True)
    monkeypatch.setattr(VP, "ALPHA", 0.0)

    da_goi: list[float] = []

    def xen_ke_gia(rows, alpha, **kwargs):
        da_goi.append(alpha)
        return rows

    monkeypatch.setattr(S, "_video_diverse_order", xen_ke_gia)

    rows = [_row("A", 0.9), _row("B", 0.8)]
    S._finalize(list(rows), {}, 10, group_by_shot=False)
    assert not da_goi, "alpha = 0 mà _finalize vẫn xen kẽ"

    # Đối chứng: alpha > 0 thì vẫn phải xen kẽ như cũ.
    monkeypatch.setattr(VP, "ALPHA", 0.6)
    S._finalize(list(rows), {}, 10, group_by_shot=False)
    assert da_goi == [0.6]
