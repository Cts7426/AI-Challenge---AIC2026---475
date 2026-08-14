# tests/test_search_filter.py — C4.4: filter_video_id thêm vào search.py
#
# Chỉ test phần THUẦN LOGIC (dựng query) không cần Docker — phần chạy thật
# (search() đầu-cuối với ES+Milvus sống) kiểm bằng CLI:
#   python -m backend.retrieval.search "..." --en "..." --filter-video-id L21_V001
#
# Trọng tâm: filter_video_id=None phải cho ra query Y HỆT trước khi có tham số
# này — đây là điều kiện "không đổi hành vi KIS pipeline hiện có" đã cam kết ở
# Phase 2 review.

from __future__ import annotations

import inspect

from backend.retrieval.search import (
    _branch_asr,
    _branch_objects,
    _branch_ocr,
    _branch_vector,
    _with_video_filter,
    search,
)


def test_with_video_filter_none_tra_nguyen_query():
    """None → query gốc KHÔNG đổi, kể cả identity object — đúng cam kết
    'không nhánh nào đổi hành vi' khi filter_video_id không được truyền."""
    q = {"match": {"labels.txt": "airplane"}}
    assert _with_video_filter(q, None) is q


def test_with_video_filter_boc_bool_filter_dung_video():
    q = {"match": {"labels.txt": "airplane"}}
    wrapped = _with_video_filter(q, "L21_V001")
    assert wrapped == {
        "bool": {
            "must": [{"match": {"labels.txt": "airplane"}}],
            "filter": [{"term": {"video_id": "L21_V001"}}],
        }
    }
    # filter (không phải must) — không được tham gia tính _score, chỉ thu hẹp tập
    assert "filter" in wrapped["bool"]


def test_with_video_filter_khong_sua_query_goc():
    """Không được sửa dict gốc tại chỗ — chỗ gọi khác có thể đang giữ tham
    chiếu tới q và không ngờ nó bị đổi ngầm."""
    q = {"match": {"labels.txt": "airplane"}}
    _with_video_filter(q, "L21_V001")
    assert q == {"match": {"labels.txt": "airplane"}}


def test_search_mac_dinh_filter_video_id_la_none():
    """Chữ ký search() phải mặc định filter_video_id=None — KIS pipeline hiện
    có gọi search() không truyền tham số này phải chạy y hệt trước khi sửa."""
    sig = inspect.signature(search)
    assert sig.parameters["filter_video_id"].default is None


def test_cac_nhanh_keyframe_deu_nhan_filter_video_id_optional():
    """4 nhánh mức-keyframe phải có filter_video_id optional, mặc định None —
    nhánh metadata (mức video) CỐ Ý không có tham số này (xem comment
    search.py: chỗ gọi tự tắt nhánh metadata qua branches={'metadata': False})."""
    for fn in (_branch_vector, _branch_objects, _branch_ocr, _branch_asr):
        sig = inspect.signature(fn)
        assert "filter_video_id" in sig.parameters, f"{fn.__name__} thiếu filter_video_id"
        assert sig.parameters["filter_video_id"].default is None
