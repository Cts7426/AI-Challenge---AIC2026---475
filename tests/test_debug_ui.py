# tests/test_debug_ui.py — D2.1: kiểm màn hình Streamlit có VẼ ĐƯỢC không
#
# `debug_ui.py` chỉ vẽ, logic nằm ở labels/evidence/offline_search và đã có test
# riêng. Nhưng "chỉ vẽ" vẫn hỏng được: đổi tên một trường trong `Evidence` là trang
# nổ giữa lúc đang chấm nhãn, mà không test nào bắt.
#
# `AppTest` của Streamlit chạy THẬT kịch bản trong tiến trình pytest và thu lại
# exception — đủ để bắt đúng loại lỗi đó mà không cần mở trình duyệt.

from __future__ import annotations

import pytest

pytest.importorskip("streamlit", reason="app/requirements.txt chưa cài")

from streamlit.testing.v1 import AppTest  # noqa: E402

from app.debug_ui import query_id_of  # noqa: E402

DUONG_DAN = "app/debug_ui.py"


def _chay() -> AppTest:
    return AppTest.from_file(DUONG_DAN, default_timeout=120).run()


# ------------------------------------------------------------------ query_id

def test_query_id_on_dinh_giua_cac_phien():
    """Nhãn của cùng một câu hỏi phải gom về một chỗ, kể cả sau khi tắt máy."""
    assert query_id_of("thủ môn cản phá") == query_id_of("thủ môn cản phá")


def test_query_id_bo_qua_khoang_trang_va_hoa_thuong():
    """Gõ thừa một dấu cách không được biến thành truy vấn khác — nhãn sẽ tách hai đống."""
    assert query_id_of("  Thủ Môn cản phá  ") == query_id_of("thủ môn cản phá")


def test_query_id_khac_nhau_cho_cau_khac_nhau():
    assert query_id_of("thủ môn") != query_id_of("hậu vệ")


# --------------------------------------------------------------- vẽ được không

def test_trang_ve_duoc_khong_loi():
    at = _chay()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert at.title[0].value == "UI debug — AIC 2026"


def test_khong_tu_chay_search_khi_chua_bam_nut():
    """Streamlit vẽ lại trang sau MỌI thao tác. Tự chạy search là bắt đợi 8 giây mỗi
    lần chạm bàn phím, kể cả lúc chỉ bấm nút chấm nhãn."""
    at = _chay()
    at.sidebar.text_area[0].set_value("thủ môn cản phá penalty").run()
    assert not at.exception
    assert any("Bấm **Tìm kiếm**" in i.value for i in at.info)


def test_hien_query_id_khi_da_go_truy_van():
    at = _chay()
    at.sidebar.text_area[0].set_value("thủ môn cản phá penalty").run()
    qid = query_id_of("thủ môn cản phá penalty")
    assert any(qid in c.value for c in at.caption), "phải hiện query_id để biết nhãn gom vào đâu"


def test_bao_khi_chua_dat_ten_nguoi_cham(monkeypatch):
    """Nhãn không có tên người chấm thì sau này không truy ra ai chấm cái gì."""
    monkeypatch.setenv("AIC_LABELER", "unknown")
    at = _chay()
    assert any("AIC_LABELER" in w.value for w in at.sidebar.warning)


def test_bao_khi_chua_co_anh_keyframe():
    """Thiếu ảnh làm UI kém vui chứ không sai số nào — nhưng phải nói cho người dùng biết."""
    at = _chay()
    assert not at.exception
    # có ảnh thì không cần báo; chưa có thì phải báo
    from data.config.debug_ui import KEYFRAMES_DIR

    if not KEYFRAMES_DIR.is_dir():
        assert any("ảnh keyframe" in i.value for i in at.sidebar.info)


def test_du_5_o_bat_tat_nhanh():
    """Bật/tắt từng nhánh là công cụ chẩn đoán chính: tắt đi để xem nguồn nào gánh điểm."""
    at = _chay()
    ten = {c.label for c in at.sidebar.checkbox}
    assert {"vector", "metadata", "objects", "ocr", "asr"} <= ten


def test_co_o_chon_che_do_live_va_offline():
    at = _chay()
    lua_chon = set(at.sidebar.radio[0].options)
    assert lua_chon == {"live", "offline"}


def test_offline_thi_KHOA_cac_o_bat_tat_nhanh():
    """Offline chỉ có một nguồn (BM25) nên mấy ô kia không đổi được gì.

    Để bật được mà không có tác dụng là lời nói dối về chính công cụ chẩn đoán: người
    dùng tắt `vector` rồi thấy kết quả y hệt, kết luận "vector không đóng góp gì" —
    trong khi thật ra nó chưa từng được gọi.
    """
    at = _chay()
    at.sidebar.radio[0].set_value("offline").run()
    assert not at.exception
    o = {c.label: c for c in at.sidebar.checkbox}
    assert all(o[n].disabled for n in ("vector", "metadata", "objects", "ocr", "asr"))
    assert o["Gom về shot"].disabled


def test_live_thi_MO_cac_o_bat_tat_nhanh():
    at = _chay()
    at.sidebar.radio[0].set_value("live").run()
    assert not at.exception
    assert not any(c.disabled for c in at.sidebar.checkbox)


# ------------------------------------------- hợp đồng với backend.retrieval.search

def test_bao_dung_goi_con_THIEU_cho_che_do_live():
    """Thiếu gói thì phải nói TÊN GÓI, không nói chung chung "không nạp được".

    `backend.retrieval.search` nạp lười (`import torch` nằm trong thân hàm) nên nó
    import trót lọt trên máy chưa cài gì. Nếu chỉ dựa vào phép import đó, UI mặc định
    chọn `live`, người dùng bấm Tìm kiếm rồi mới nhận lỗi.
    """
    import importlib.util

    from app.debug_ui import LIVE_PACKAGES

    thieu = [pip for mod, pip in LIVE_PACKAGES.items()
             if importlib.util.find_spec(mod) is None]
    at = _chay()
    at.sidebar.radio[0].set_value("live").run()
    assert not at.exception
    loi = " ".join(e.value for e in at.sidebar.error)
    if thieu:
        assert all(g in loi for g in thieu), f"thiếu {thieu} mà báo: {loi!r}"
        assert "pip install" in loi, "phải kèm lệnh cài, không bắt người dùng tự tra"
    else:
        assert "thiếu gói" not in loi


def test_ten_nhanh_KHOP_voi_search_weights():
    """Tên nhánh UI gửi đi phải trùng tên nhánh `search()` nhận.

    Đây là hợp đồng mà không ai kiểm được lúc chạy: `search()` gộp `{**BRANCHES,
    **branches}` nên một khoá gõ sai KHÔNG báo lỗi — nó chỉ nằm im, nhánh thật vẫn
    bật theo mặc định. Người dùng bỏ tick `vector`, kết quả không đổi, rồi kết luận
    sai rằng vector không đóng góp gì. Chạy được mà kết quả sai, đúng loại lỗi im
    lặng dự án đang phòng.
    """
    from data.config.search_weights import BRANCHES as SEARCH_BRANCHES

    from app.debug_ui import BRANCHES as UI_BRANCHES

    assert set(UI_BRANCHES) == set(SEARCH_BRANCHES), (
        f"UI gửi {sorted(set(UI_BRANCHES) - set(SEARCH_BRANCHES))}, search không biết khoá này"
    )


def test_truong_ket_qua_UI_doc_deu_co_trong_hop_dong_cua_search():
    """UI đọc `keyframe_id/video_id/frame_idx/shot_id/score/ranks` từ mỗi kết quả.

    Đổi tên một trường bên `search()` thì UI im lặng vẽ ra `None` — thẻ trống, không
    chấm nhãn được, không có thông báo nào. Neo vào docstring của `search()` để lần
    đổi tên tiếp theo làm test đỏ.
    """
    import inspect

    from backend.retrieval import search as mod

    tai_lieu = inspect.getdoc(mod.search) or ""
    for truong in ("keyframe_id", "video_id", "frame_idx", "shot_id", "score", "ranks"):
        assert truong in tai_lieu, f"`search()` không còn hứa trả `{truong}`"


# ------------------------------------------- định tuyến theo dạng bài (19/08)
#
# Bản trước `run_search()` luôn gọi `search(cfg["query"])` cho cả ba dạng bài —
# ném NGUYÊN câu multi-event của TRAKE vào search như một câu KIS đơn. UI khi đó
# hiện kết quả của một pipeline KHÁC HẲN đường thi, nên nhãn chấm ở đây đo nhầm
# hệ thống, mà `eval.py` (E4.2) và `score_simulator` (D3.5) lại ăn theo bộ nhãn đó.
#
# Cùng con bug đã bị bắt một lần ở `dev_set/tools/run_evaluation.py` (sửa 16/08).
# Bộ test dưới đây khoá lại để nó không quay về lần thứ ba.

def _cfg(task: str, **thay_doi) -> dict:
    from app.debug_ui import BRANCHES

    return {"query": "vận động viên chạy đà rồi giậm nhảy rồi tiếp đất",
            "query_en": "", "task": task, "top_k": 10, "mode": "live", "moment": 1,
            "n_moments_total": 4, "branches": {b: True for b in BRANCHES},
            "group_by_shot": True, "run": True, "has_key": True, **thay_doi}


@pytest.fixture
def khong_goi_search(monkeypatch):
    """Thay `search()` bằng bẫy: gọi tới là test đỏ. Trả về list ghi lại lời gọi."""
    import app.debug_ui as ui

    da_goi = []

    def bay(*args, **kwargs):
        da_goi.append(args)
        return []

    monkeypatch.setattr(ui, "_load_search", lambda: (bay, []))
    return da_goi


def test_TRAKE_goi_parse_events_chu_khong_nem_ca_cau_vao_search(monkeypatch, khong_goi_search):
    """TRAKE phải đi qua `parse_events` → `trake_search`, đúng như `post_search`."""
    import backend.tasks.trake as trake

    from app.debug_ui import run_search

    monkeypatch.setattr(trake, "parse_events", lambda q: ["chạy đà", "giậm nhảy", "tiếp đất"])
    monkeypatch.setattr(trake, "trake_search", lambda events, **kw: [
        trake.TrakeCandidate(video_id="L21_V001", score=0.9, frame_ids=(10, 20, 30),
                             keyframe_ids=("L21_V001#k0001", None, "L21_V001#k0003"),
                             n_hit_events=2, has_full_order=True)
    ])
    rows = run_search(_cfg("TRAKE"))

    assert khong_goi_search == [], "TRAKE không được gọi thẳng search() với nguyên câu"
    assert rows and rows[0]["video_id"] == "L21_V001"


def test_TRAKE_chi_hien_khoanh_khac_dang_soan(monkeypatch, khong_goi_search):
    """Nhãn TRAKE chấm theo VỊ TRÍ — trộn cả N vị trí là mời người chấm gắn nhầm."""
    import backend.tasks.trake as trake

    from app.debug_ui import run_search

    monkeypatch.setattr(trake, "parse_events", lambda q: ["a", "b", "c"])
    monkeypatch.setattr(trake, "trake_search", lambda events, **kw: [
        trake.TrakeCandidate(video_id="L21_V001", score=0.9, frame_ids=(10, 20, 30),
                             keyframe_ids=("k1", "k2", "k3"),
                             n_hit_events=3, has_full_order=True)
    ])
    rows = run_search(_cfg("TRAKE", moment=2))

    assert len(rows) == 1
    assert rows[0]["event_index"] == 1, "moment=2 phải ra event_index=1 (đếm từ 0)"
    assert rows[0]["frame_idx"] == 20


def test_TRAKE_danh_dau_frame_noi_suy(monkeypatch, khong_goi_search):
    """`keyframe_ids[j] is None` = vị trí nội suy — UI phải biết để không hiện như đã tìm thấy."""
    import backend.tasks.trake as trake

    from app.debug_ui import run_search

    monkeypatch.setattr(trake, "parse_events", lambda q: ["a", "b"])
    monkeypatch.setattr(trake, "trake_search", lambda events, **kw: [
        trake.TrakeCandidate(video_id="L21_V001", score=0.5, frame_ids=(10, 20),
                             keyframe_ids=(None, "k2"), n_hit_events=1, has_full_order=False)
    ])
    rows = run_search(_cfg("TRAKE", moment=1))
    assert rows[0]["is_interpolated"] is True


def test_QA_goi_qa_pipeline_chu_khong_search_nguyen_van_cau_hoi(monkeypatch, khong_goi_search):
    """Q&A search trên phần MÔ TẢ SỰ KIỆN đã tách, không phải nguyên văn câu hỏi."""
    import backend.tasks.qa as qa
    from backend.slot import ShotHit

    from app.debug_ui import run_search

    monkeypatch.setattr(qa, "qa_pipeline",
                        lambda q, top_k_shots=100, query_en=None:
                        ([ShotHit("L21_V001#s0006", 0.4, "L21_V001#k0007")], "5"))
    rows = run_search(_cfg("QA"))

    assert khong_goi_search == [], "Q&A không được gọi thẳng search() với nguyên câu hỏi"
    assert rows[0]["answer_text"] == "5", "câu trả lời phải đi kèm thẻ để chấm cửa thứ hai"
    assert rows[0]["shot_id"] == "L21_V001#s0006"
    assert rows[0]["video_id"], "phải tra được video_id qua shot_bounds()"


def test_KIS_van_goi_search_nhu_cu(monkeypatch, khong_goi_search):
    """Đừng sửa quá tay: KIS vẫn phải đi thẳng qua `search()` với đủ tham số nhánh."""
    from app.debug_ui import run_search

    run_search(_cfg("KIS"))
    assert len(khong_goi_search) == 1, "KIS phải gọi search() đúng một lần"


def test_QA_TRAKE_bao_loi_ro_khi_thieu_khoa_LLM(khong_goi_search):
    """Không có khoá thì hai dạng này không chạy được — nói trước, đừng ném stack trace."""
    from app.debug_ui import run_search

    assert run_search(_cfg("QA", has_key=False)) == []
    assert run_search(_cfg("TRAKE", has_key=False)) == []
