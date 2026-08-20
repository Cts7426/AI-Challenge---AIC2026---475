# tests/test_qa_text_fallback.py — bản vá "nối ứng viên nhánh text" cho Q&A (20/08)
#
# Bối cảnh đo được: sau khi thay CLIP mock bằng features thật, Q&A tụt
# 0,360 → 0,160. QA05 hỏi "video nhắc tới bến phà nào" — bằng chứng nằm trong
# ASR, nhưng CLIP thật kéo lên các cảnh TRÔNG GIỐNG phà, đẩy video đúng từ hạng
# 3 xuống 16. Chỉ 3 shot đầu được đem đi suy luận → LLM đọc ASR của video khác
# → trả lời sai → 0 điểm cả 100 dòng.
#
# Test ở đây khoá lại BA điều, theo đúng thứ tự rủi ro:
#   1. bản vá KHÔNG chạm được vào KIS/TRAKE (rủi ro lớn nhất — KIS là 23/30 câu)
#   2. ứng viên mới thật sự được ĐEM ĐI SUY LUẬN (nếu không, bản vá vô nghĩa)
#   3. thứ tự ứng viên gốc không đổi (không xáo trộn 100 slot đang nộp)
#
# Không cần Docker: `search` bị thay bằng hàm giả.
#
# Chạy: python -m pytest tests/test_qa_text_fallback.py -q

from __future__ import annotations

import pytest

from backend.slot import ShotHit
from backend.tasks import qa as Q


def _hit(shot: str, score: float = 1.0) -> ShotHit:
    return ShotHit(shot, score, f"{shot}_kf")


def _res(*shots: str) -> list[dict]:
    return [{"shot_id": s, "score": 1.0 - i * 0.01, "keyframe_id": f"{s}_kf"}
            for i, s in enumerate(shots)]


# ------------------------------------------------- cổng chặn theo loại câu hỏi

@pytest.mark.parametrize("route", ["ocr", "asr", "metadata", "text_first"])
def test_bat_cho_cau_hoi_dua_vao_chu_va_tieng(monkeypatch, route):
    monkeypatch.setattr(Q, "search", lambda *a, **kw: _res("S_NEW"))
    them = Q._ung_vien_nhanh_text("sự kiện", None, route, 100)
    assert [h.shot_id for h in them] == ["S_NEW"]


@pytest.mark.parametrize("route", ["visual", "count"])
def test_TAT_cho_cau_hoi_thi_giac_va_dem(monkeypatch, route):
    """Màu sắc/hình dáng thì CLIP mới là nguồn đúng; đếm thì đi đường detector.
    Hai loại này cố tình đứng ngoài bản vá."""
    monkeypatch.setattr(Q, "search",
                        lambda *a, **kw: pytest.fail(f"route {route} không được search thêm"))
    assert Q._ung_vien_nhanh_text("sự kiện", None, route, 100) == []


def test_co_config_tat_thi_khong_lam_gi(monkeypatch):
    import data.config.search_weights as W

    monkeypatch.setattr(W, "QA_TEXT_FALLBACK_ENABLED", False)
    monkeypatch.setattr(Q, "search",
                        lambda *a, **kw: pytest.fail("cờ đã tắt mà vẫn gọi search"))
    assert Q._ung_vien_nhanh_text("sự kiện", None, "asr", 100) == []


# --------------------------------------------------------- hành vi nối ứng viên

def test_KHONG_khu_trung_theo_be_o_day(monkeypatch):
    """⚠️ Bản đầu khử trùng theo bể chính ngay trong hàm này và biến cả bản vá
    thành vô nghĩa: đo 20/08 thấy cả 5 shot nhánh text ĐÃ có trong bể 100 (hạng
    6, 9, 28, 75, 76) nên bị xoá sạch, hàm trả 0 shot.

    Vấn đề chưa bao giờ là "shot vắng mặt trong bể" mà là "shot đứng hạng 16
    trong khi chỉ 3 shot đầu được suy luận". Khử trùng là việc của chỗ gọi, nơi
    biết mình đang dựng danh sách SUY LUẬN hay danh sách CẤP SLOT."""
    monkeypatch.setattr(Q, "search", lambda *a, **kw: _res("S_OLD", "S_NEW"))
    them = Q._ung_vien_nhanh_text("sự kiện", None, "asr", 100)
    assert [h.shot_id for h in them] == ["S_OLD", "S_NEW"]


def test_dung_dung_1_lan_search_va_KHONG_goi_llm(monkeypatch):
    """Ràng buộc cứng: tối đa 1 lần search bổ sung, không thêm lần gọi llm() nào."""
    dem = {"search": 0}

    def _s(*a, **kw):
        dem["search"] += 1
        assert kw.get("branches") == {"vector": False}, "phải TẮT nhánh vector"
        assert kw.get("top_k") == 100, "top_k phải BẰNG lần search chính, không phải quota"
        return _res("S_NEW")

    monkeypatch.setattr(Q, "search", _s)
    monkeypatch.setattr(Q, "llm", lambda *a, **kw: pytest.fail("không được gọi llm()"))
    Q._ung_vien_nhanh_text("sự kiện", None, "asr", 100)
    assert dem["search"] == 1


def test_search_loi_thi_nuot_chu_khong_keo_sap_cau(monkeypatch):
    """Đường phụ trợ hỏng thì Q&A phải chạy tiếp như chưa có bản vá."""
    def _no(*a, **kw):
        raise RuntimeError("ES chết")

    monkeypatch.setattr(Q, "search", _no)
    assert Q._ung_vien_nhanh_text("sự kiện", None, "asr", 100) == []


def test_bo_hit_khong_co_shot_id(monkeypatch):
    monkeypatch.setattr(Q, "search", lambda *a, **kw: [
        {"shot_id": None, "score": 1.0, "keyframe_id": "x"},
        {"shot_id": "S_NEW", "score": 0.9, "keyframe_id": "y"},
    ])
    them = Q._ung_vien_nhanh_text("sự kiện", None, "asr", 100)
    assert [h.shot_id for h in them] == ["S_NEW"]


# ------------------------------------- ứng viên mới PHẢI được đem đi suy luận

def test_ung_vien_text_duoc_thu_du_nam_ngoai_top_3(monkeypatch):
    """⚠️ Ca QA05 — lý do tồn tại của cả bản vá.

    Bản vá "nối vào cuối danh sách" theo nghĩa đen là VÔ NGHĨA: vòng suy luận
    chỉ lấy MAX_SHOTS_TRIED = 3 shot đầu, mà ứng viên nối thêm nằm ở vị trí 100+.
    Ở đây shot đúng chỉ nhánh text mới tìm ra, và nó PHẢI được thử.
    """
    goc = _res(*[f"S{i}" for i in range(50)])
    monkeypatch.setattr(Q, "search",
                        lambda *a, **kw: (_res("S_TEXT") if kw.get("branches") else goc))
    monkeypatch.setattr(Q, "parse_question",
                        lambda q: Q.QuestionParts(event_vi="sk", question_vi="ai nói gì?"))
    monkeypatch.setattr(Q, "route_question", lambda q: ("asr", False))

    da_thu = []

    def _try(hit, *a, **kw):
        da_thu.append(hit.shot_id)
        return ("bến phà Vàm Cống", 123) if hit.shot_id == "S_TEXT" else None

    monkeypatch.setattr(Q, "_try_shot", _try)
    shots, answer = Q.qa_pipeline("câu hỏi")

    assert "S_TEXT" in da_thu, "ứng viên nhánh text KHÔNG được đem đi suy luận"
    assert da_thu[0] == "S_TEXT", (
        "câu hỏi định tuyến về text thì shot nhánh text phải được thử TRƯỚC — "
        "vòng lặp dừng ở shot đầu tiên trả lời được, xếp sau là không bao giờ tới")
    assert answer == "bến phà Vàm Cống"
    assert shots[0].shot_id == "S_TEXT", "shot sinh ra answer phải được kéo lên hạng 1"


def test_thu_tu_ung_vien_goc_khong_doi(monkeypatch):
    """100 slot nộp không được xáo trộn vì một tín hiệu chưa kiểm chứng."""
    goc = _res("A", "B", "C", "D")
    monkeypatch.setattr(Q, "search",
                        lambda *a, **kw: (_res("Z") if kw.get("branches") else goc))
    monkeypatch.setattr(Q, "parse_question",
                        lambda q: Q.QuestionParts(event_vi="sk", question_vi="ai nói gì?"))
    monkeypatch.setattr(Q, "route_question", lambda q: ("asr", False))
    monkeypatch.setattr(Q, "_try_shot",
                        lambda hit, *a, **kw: ("x", 1) if hit.shot_id == "A" else None)

    shots, _ = Q.qa_pipeline("câu hỏi")
    assert [h.shot_id for h in shots] == ["A", "B", "C", "D", "Z"], \
        "ứng viên gốc phải giữ nguyên thứ tự, ứng viên text nối vào CUỐI"


def test_shot_dau_bang_du_nhanh_KHONG_duoc_cat_duong_ung_vien_text(monkeypatch):
    """⚠️ Ca đo được 20/08 (run_20260820_2225): bản vá đã đưa đúng shot vào danh
    sách mà điểm không đổi, vì shot #1 của bảng đủ nhánh trả lời trôi chảy một
    câu SAI và vòng lặp return ngay tại đó.

    Ở đây CẢ HAI shot đều trả lời được — shot nhánh text phải thắng."""
    goc = _res("S_CLIP", "S1", "S2")
    monkeypatch.setattr(Q, "search",
                        lambda *a, **kw: (_res("S_TEXT") if kw.get("branches") else goc))
    monkeypatch.setattr(Q, "parse_question",
                        lambda q: Q.QuestionParts(event_vi="sk", question_vi="ai nói gì?"))
    monkeypatch.setattr(Q, "route_question", lambda q: ("asr", False))
    monkeypatch.setattr(Q, "_try_shot", lambda hit, *a, **kw: (
        ("Phà Châu Giang", 1) if hit.shot_id == "S_CLIP" else ("bến phà Vàm Cống", 2)))

    _, answer = Q.qa_pipeline("câu hỏi")
    assert answer == "bến phà Vàm Cống"


def test_route_thi_giac_van_uu_tien_bang_du_nhanh(monkeypatch):
    """Câu hỏi về màu sắc/hình dáng thì CLIP mới đúng — không được đảo thứ tự."""
    goc = _res("S_CLIP", "S1")
    monkeypatch.setattr(Q, "search", lambda *a, **kw: goc)
    monkeypatch.setattr(Q, "parse_question",
                        lambda q: Q.QuestionParts(event_vi="sk", question_vi="áo màu gì?"))
    monkeypatch.setattr(Q, "route_question", lambda q: ("visual", True))
    da_thu = []
    monkeypatch.setattr(Q, "_try_shot",
                        lambda hit, *a, **kw: (da_thu.append(hit.shot_id), ("đỏ", 1))[1])
    Q.qa_pipeline("câu hỏi")
    assert da_thu[0] == "S_CLIP"
