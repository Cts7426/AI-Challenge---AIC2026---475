# tests/test_health.py — W0.3: test deep check của /health
#
# Bộ test này KHÔNG cần docker: mỗi check được thay bằng hàm giả để dựng đúng
# các tình huống cần kiểm — DB chết, DB treo, index rỗng, chỉ có cảnh báo.
#
# Vì sao phải test bằng tình huống giả: cái đáng sợ nhất của một health check là
# nó BÁO XANH khi hệ thống hỏng. Chạy nó trên máy đang khoẻ chỉ chứng minh
# được nửa còn lại. Ca "Milvus rỗng" và ca "service treo" chỉ dựng được bằng giả lập.
#
# Chạy: python -m pytest tests/test_health.py -q

from __future__ import annotations

import time

import pytest

from backend.api import health as H


def _fake(status, detail="x", extra=None, sleep=0.0):
    def fn():
        if sleep:
            time.sleep(sleep)
        return status, detail, extra or {}
    return fn


def _dat_checks(monkeypatch, checks):
    """Thay bảng CHECKS bằng bộ giả: (tên, critical, hàm)."""
    monkeypatch.setattr(H, "CHECKS", tuple(checks))
    # Không nạp module thật trong test — chỉ tốn thời gian, không kiểm được gì
    monkeypatch.setattr(H, "_warm_imports", lambda: 0.0)


# ------------------------------------------------------------- trạng thái chung

def test_tat_ca_xanh_thi_ok(monkeypatch):
    _dat_checks(monkeypatch, [("a", True, _fake(H.OK)), ("b", False, _fake(H.OK))])
    assert H.deep_check()["status"] == "ok"


def test_critical_chet_thi_down(monkeypatch):
    _dat_checks(monkeypatch, [("a", True, _fake(H.DOWN)), ("b", False, _fake(H.OK))])
    assert H.deep_check()["status"] == "down"


def test_khong_critical_chet_chi_la_degraded(monkeypatch):
    """Index ocr chưa nạp KHÔNG được làm sập cả API — search chạy tiếp bằng nguồn khác."""
    _dat_checks(monkeypatch, [("a", True, _fake(H.OK)), ("b", False, _fake(H.DOWN))])
    assert H.deep_check()["status"] == "degraded"


def test_canh_bao_thi_degraded(monkeypatch):
    _dat_checks(monkeypatch, [("a", True, _fake(H.OK)), ("b", False, _fake(H.WARN))])
    assert H.deep_check()["status"] == "degraded"


# ------------------------------------------------------- không bao giờ ném lỗi

def test_check_no_loi_thanh_down_chu_khong_ném_ra_ngoai(monkeypatch):
    """/health mà trả 500 thì vô dụng — lỗi kết nối là THÔNG TIN, không phải sự cố."""
    def no():
        raise ConnectionError("Milvus chết")

    _dat_checks(monkeypatch, [("milvus", True, no)])
    kq = H.deep_check()
    assert kq["status"] == "down"
    assert "ConnectionError" in kq["checks"][0]["detail"]
    assert "Milvus chết" in kq["checks"][0]["detail"]


def test_service_treo_bi_cat_theo_timeout(monkeypatch):
    """DB TREO nguy hiểm hơn DB chết: không có trần thì /health treo theo."""
    _dat_checks(monkeypatch, [("treo", True, _fake(H.OK, sleep=5))])
    t0 = time.perf_counter()
    kq = H.deep_check(timeout_s=0.2)
    giay = time.perf_counter() - t0

    assert kq["status"] == "down"
    assert "treo" in kq["checks"][0]["detail"]
    assert giay < 2.0, "deep_check phải trả về ngay khi hết timeout, không đợi check treo"


def test_check_chay_song_song(monkeypatch):
    """3 check mỗi cái 0.3s phải xong trong ~0.3s, không phải 0.9s."""
    _dat_checks(monkeypatch, [(f"c{i}", False, _fake(H.OK, sleep=0.3)) for i in range(3)])
    t0 = time.perf_counter()
    H.deep_check()
    assert time.perf_counter() - t0 < 0.7


# ------------------------------------------------------------- hình dạng output

def test_output_co_du_thong_tin_de_chan_doan(monkeypatch):
    _dat_checks(monkeypatch, [("es", True, _fake(H.OK, "ES 8.13.4", {"doc_counts": {"ocr": 5}}))])
    kq = H.deep_check()
    c = kq["checks"][0]
    assert c["name"] == "es" and c["critical"] is True
    assert c["detail"] == "ES 8.13.4" and c["doc_counts"] == {"ocr": 5}
    assert isinstance(c["latency_ms"], float) and c["latency_ms"] >= 0
    assert "latency_ms" in kq and "import_ms" in kq


def test_format_report_khong_no_voi_moi_trang_thai(monkeypatch):
    _dat_checks(monkeypatch, [("a", True, _fake(H.DOWN)), ("b", False, _fake(H.WARN)),
                              ("c", False, _fake(H.OK, ""))])
    txt = H.format_report(H.deep_check())
    assert "DOWN" in txt and "WARN" in txt and "OK" in txt


# --------------------------------------------- luật riêng của từng check thật

def test_milvus_collection_rong_bi_tinh_la_chet(monkeypatch):
    """Ca lỗi im lặng kinh điển: mọi thứ 'lên' bình thường, chỉ là 0 vector."""
    class _Client:
        def has_collection(self, ten):
            return True

        def get_collection_stats(self, ten):
            return {"row_count": 0}

    import backend.indexing.milvus_client as mc

    monkeypatch.setattr(mc, "connect", lambda: _Client())
    status, detail, extra = H._check_milvus()
    assert status == H.DOWN and "RỖNG" in detail and extra["row_count"] == 0


def test_milvus_co_vector_thi_ok(monkeypatch):
    class _Client:
        def has_collection(self, ten):
            return True

        def get_collection_stats(self, ten):
            return {"row_count": 371_702}

    import backend.indexing.milvus_client as mc

    monkeypatch.setattr(mc, "connect", lambda: _Client())
    status, detail, extra = H._check_milvus()
    assert status == H.OK and extra["row_count"] == 371_702


def test_milvus_chua_co_collection(monkeypatch):
    class _Client:
        def has_collection(self, ten):
            return False

    import backend.indexing.milvus_client as mc

    monkeypatch.setattr(mc, "connect", lambda: _Client())
    status, detail, _ = H._check_milvus()
    assert status == H.DOWN and "load_clip" in detail


def test_frame_map_rong_la_critical_down(monkeypatch):
    """Thiếu frame_map = nộp sai frame = 0 điểm dù tìm đúng video (bất biến 5)."""
    import backend.indexing.frame_map as fm

    monkeypatch.setattr(fm, "load_frame_map", lambda: {})
    status, detail, _ = H._check_frame_map()
    assert status == H.DOWN and "bất biến 5" in detail


def test_vector_space_lech_model_thi_no(monkeypatch):
    """Index nạp bằng model A, query bằng model B → Milvus vẫn trả top-k trông rất bình thường."""
    import backend.indexing.load_clip as lc

    def _no(strict=True):
        raise RuntimeError("INDEX VÀ CONFIG KHÔNG CÙNG KHÔNG GIAN VECTOR")

    monkeypatch.setattr(lc, "assert_index_meta", _no)
    c = H._do("vector_space", True, H._check_vector_space)
    assert c.status == H.DOWN and "KHÔNG CÙNG KHÔNG GIAN VECTOR" in c.detail


def test_clip_model_khong_tu_nap(monkeypatch):
    """Health check KHÔNG được tự nạp CLIP: ~16s + vài trăm MB cho một cú curl."""
    import backend.retrieval.text_query as tq

    monkeypatch.setattr(tq, "_model", None)
    monkeypatch.setattr(tq, "_get_model", lambda: pytest.fail("health check đã nạp model!"))
    status, detail, _ = H._check_clip_model()
    assert status == H.WARN and "chưa preload" in detail


def test_clip_model_khong_chuan_hoa_l2_la_down(monkeypatch):
    """|v| != 1 → metric COSINE của Milvus không còn là cosine (bất biến 1)."""
    import numpy as np

    import backend.retrieval.text_query as tq
    from data.config.clip_model import CLIP_EMBEDDING_DIM

    monkeypatch.setattr(tq, "_model", object())
    monkeypatch.setattr(tq, "encode_text",
                        lambda t: np.full(CLIP_EMBEDDING_DIM, 0.5, dtype=np.float32))
    status, detail, _ = H._check_clip_model()
    assert status == H.DOWN and "chuẩn hoá L2" in detail


def test_clip_model_dung_chuan_thi_ok(monkeypatch):
    import numpy as np

    import backend.retrieval.text_query as tq
    from data.config.clip_model import CLIP_EMBEDDING_DIM

    v = np.zeros(CLIP_EMBEDDING_DIM, dtype=np.float32)
    v[0] = 1.0
    monkeypatch.setattr(tq, "_model", object())
    monkeypatch.setattr(tq, "encode_text", lambda t: v)
    status, _, _ = H._check_clip_model()
    assert status == H.OK


# ------------------------------------------------------------------ endpoint

@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from backend.api.main import app

    # Không dùng `with TestClient(app)`: nó chạy lifespan → nạp CLIP thật (~16s).
    return TestClient(app)


def test_endpoint_quick_khong_dung_toi_db(client, monkeypatch):
    monkeypatch.setattr(H, "deep_check",
                        lambda *a, **kw: pytest.fail("?quick=1 không được đụng DB"))
    r = client.get("/health?quick=1")
    assert r.status_code == 200 and r.json() == {"status": "ok", "mode": "liveness"}


def test_endpoint_tra_503_khi_critical_chet(client, monkeypatch):
    import backend.api.health as mod

    monkeypatch.setattr(mod, "deep_check", lambda *a, **kw: {
        "status": "down", "latency_ms": 1.0, "import_ms": 0.0,
        "checks": [{"name": "milvus", "status": "down", "latency_ms": 1.0,
                    "critical": True}],
    })
    r = client.get("/health")
    assert r.status_code == 503
    assert r.json()["status"] == "down"


def test_endpoint_tra_200_khi_chi_degraded(client, monkeypatch):
    """Thiếu index phụ KHÔNG được làm script khởi động tưởng backend chết."""
    import backend.api.health as mod

    monkeypatch.setattr(mod, "deep_check", lambda *a, **kw: {
        "status": "degraded", "latency_ms": 1.0, "import_ms": 0.0, "checks": [],
    })
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "degraded"
