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

from backend.retrieval import search as S
from backend.retrieval.search import (
    _branch_asr,
    _branch_objects,
    _branch_ocr,
    _branch_ocr_probe,
    _branch_text_vi,
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
    """MỌI nhánh mức-keyframe phải có filter_video_id optional, mặc định None —
    nhánh metadata (mức VIDEO) CỐ Ý không có tham số này (xem comment
    search.py: chỗ gọi tự tắt nhánh metadata qua branches={'metadata': False}).

    ⚠️ Bản đầu của test này chỉ liệt kê 4 nhánh. Hai nhánh thêm sau (`text_vi`,
    `ocr_probe`) không được đưa vào, nên khi `_branch_ocr_probe` ra đời mà thiếu
    tham số thì test vẫn XANH: ép tìm trong một video mà nhánh đó vẫn trả về
    hàng của 59 video khác (đo được 04/09, filter L21_V007: 225 ứng viên / 60
    video). Vì vậy danh sách dưới đây phải lấy TỪ `NHANH_MUC_KEYFRAME` chứ không
    gõ tay — thêm nhánh mới là test tự bắt.
    """
    theo_ten = {
        "vector": _branch_vector,
        "objects": _branch_objects,
        "ocr": _branch_ocr,
        "ocr_probe": _branch_ocr_probe,
        # `vector_siglip2` dùng chung `_branch_vector`, chỉ khác tham số encoder.
        "vector_siglip2": _branch_vector,
    }
    thieu = set(S.NHANH_MUC_KEYFRAME) - set(theo_ten)
    assert not thieu, f"nhánh mức-keyframe mới chưa được test kiểm: {sorted(thieu)}"

    # `asr` và `text_vi` xếp hạng ở mức ĐOẠN thời gian, không nằm trong
    # NHANH_MUC_KEYFRAME, nhưng vẫn truy vấn ES theo video nên cũng phải lọc được.
    for fn in {*theo_ten.values(), _branch_asr, _branch_text_vi}:
        sig = inspect.signature(fn)
        assert "filter_video_id" in sig.parameters, f"{fn.__name__} thiếu filter_video_id"
        assert sig.parameters["filter_video_id"].default is None


def test_ocr_probe_chi_tra_hang_cua_video_duoc_loc(monkeypatch):
    """Tái lập lỗi 04/09: nhánh probe bỏ qua filter_video_id.

    Đây là lỗi IM LẶNG — không crash, chỉ trả ứng viên của video khác vào một
    đường chạy đã chốt video (TRAKE giai đoạn 2, Q&A đào sâu trong video, mấy
    script KIS). Sai video = 0 điểm tuyệt đối.
    """
    hang = [
        {"keyframe_id": f"L21_V{v:03d}#k{i}", "video_id": f"L21_V{v:03d}"}
        for v in (1, 2, 3)
        for i in range(4)
    ]
    monkeypatch.setattr(S, "_branch_ocr", lambda tok, limit, *a, **k: hang)

    ra = _branch_ocr_probe("cảnh có chữ 'subscribed' trên màn hình", None, 50,
                           filter_video_id="L21_V002")
    assert ra, "lọc xong phải còn hàng của chính video đó"
    assert {r["video_id"] for r in ra} == {"L21_V002"}

    # Không truyền filter → giữ nguyên hành vi cũ, đủ cả ba video.
    ra_khong_loc = _branch_ocr_probe("cảnh có chữ 'subscribed' trên màn hình", None, 50)
    assert len({r["video_id"] for r in ra_khong_loc}) == 3


def test_ocr_probe_do_do_hiem_tren_toan_kho_chu_khong_trong_mot_video(monkeypatch):
    """Chốt cái bẫy của bản vá: lệnh đo độ hiếm KHÔNG được mang filter.

    `_branch_ocr(tok, MAX_HITS + 1)` không phải để lấy kết quả — nó trả lời
    "token này khớp bao nhiêu dòng trong TOÀN KHO OCR". Lọc theo video thì token
    nào cũng khớp vài dòng, nên từ thường nào cũng lọt cửa hiếm và probe thành
    nhiễu — vẫn chạy, vẫn ra kết quả trông bình thường, không báo lỗi gì.
    """
    da_goi: list[str | None] = []

    def ocr_gia(tok, limit, filter_video_id=None):
        da_goi.append(filter_video_id)
        return [{"keyframe_id": "L21_V002#k1", "video_id": "L21_V002"}]

    monkeypatch.setattr(S, "_branch_ocr", ocr_gia)
    _branch_ocr_probe("cảnh có chữ 'subscribed' trên màn hình", None, 50,
                      filter_video_id="L21_V002")

    assert da_goi, "không gọi _branch_ocr lần nào — test không kiểm được gì"
    assert all(v is None for v in da_goi), (
        "phép đo độ hiếm bị truyền filter_video_id — cửa lọc token hiếm hỏng, "
        "mọi từ thường sẽ lọt vào probe"
    )
