# tests/test_offline_search.py — D2.1: BM25 thô, đường lui khi không có Docker
#
# Dữ liệu thật nhưng CẮT NHỎ: một truy vấn trên toàn kho tốn ~8 s, chạy chục ca là
# hết hai phút. Lát cắt vài nghìn dòng giữ nguyên tính thật (vẫn là `doc_text` của
# Công Lý, vẫn qua đúng đường code) mà chạy trong tích tắc.

from __future__ import annotations

import pytest

from app.offline_search import DOCS_PATH, tach_tu, tim


@pytest.fixture(scope="module")
def kho_nho(tmp_path_factory):
    """Lát cắt ~3 video của `docs_bm25.parquet`, ghi ra parquet tạm."""
    import pandas as pd

    if not DOCS_PATH.exists():
        pytest.skip("chưa có docs_bm25.parquet — cần Data Factory giao trước")
    df = pd.read_parquet(DOCS_PATH, columns=["kf_id", "video_id", "shot_id", "frame_idx", "doc_text"])
    video = sorted(df.video_id.unique())[:3]
    lat = df[df.video_id.isin(video)].reset_index(drop=True)
    p = tmp_path_factory.mktemp("kho") / "docs.parquet"
    lat.to_parquet(p, index=False)
    return p, lat


# ------------------------------------------------------------------ tách từ

def test_tach_tu_bo_tu_qua_ngan():
    """Từ 1 ký tự không phân biệt được tài liệu nào, mà mỗi từ là một lượt quét toàn kho."""
    assert tach_tu("ở nhà có 3 người") == ["nhà", "có", "người"]


def test_tach_tu_KHONG_bo_dau():
    """Chốt lại một đánh đổi có chủ ý, để sau này không ai tưởng là quên làm.

    Bỏ dấu cả kho tốn 40,4 s mỗi truy vấn (đo trên 371.702 tài liệu) so với 6,2 s chỉ
    viết thường. Đường thi có `VI_FOLDED_ANALYSIS` của Elasticsearch lo việc này;
    đường lui thì chấp nhận phải gõ có dấu.
    """
    assert tach_tu("Hà Nội") == ["hà", "nội"], "đang bỏ dấu — xem lại số đo trước khi đổi"


def test_tach_tu_bo_trung_giu_thu_tu():
    assert tach_tu("bóng đá bóng rổ") == ["bóng", "đá", "rổ"]


def test_tach_tu_viet_thuong():
    assert tach_tu("Hà Nội") == ["hà", "nội"]


def test_truy_van_rong_tra_rong(kho_nho):
    p, _ = kho_nho
    assert tim("", docs_path=p) == []
    assert tim("a ở", docs_path=p) == []


# ------------------------------------------------------------------ tìm kiếm

def test_tim_duoc_tu_co_that_trong_doc_text(kho_nho):
    """Lấy một từ CÓ THẬT trong kho rồi tra ngược — phải ra frame chứa nó."""
    p, lat = kho_nho
    doc = str(lat.iloc[len(lat) // 2].doc_text)
    tu = next((t for t in doc.lower().split() if len(t) >= 5 and t.isalpha()), None)
    if tu is None:
        pytest.skip("không tìm được từ đủ dài trong lát cắt này")

    kq = tim(tu, top_k=10, docs_path=p)
    assert kq, f"'{tu}' có trong doc_text mà tra không ra"
    assert all(tu in _doc_cua(lat, r.kf_id).lower() for r in kq), "trả về frame không chứa từ đó"


def test_ten_rieng_hiem_ra_dung_frame(kho_nho):
    """BUILD_TASKS B1.7: 'tra thử một tên riêng hiếm → phải ra đúng frame'.

    Đây là phép kiểm CHẤT LƯỢNG DỮ LIỆU của Công Lý, không phải kiểm code tao: nếu
    `doc_text` không gộp đủ OCR/ASR/metadata thì tra tên riêng sẽ ra rỗng.
    """
    import collections

    p, lat = kho_nho
    dem: collections.Counter = collections.Counter()
    for doc in lat.doc_text.head(500):
        dem.update({t for t in str(doc).lower().split() if len(t) >= 6 and t.isalpha()})
    hiem = [t for t, n in dem.items() if n <= 3]
    if not hiem:
        pytest.skip("lát cắt này không có từ nào đủ hiếm")

    kq = tim(hiem[0], top_k=5, docs_path=p)
    assert kq, f"từ hiếm '{hiem[0]}' tra không ra"
    assert hiem[0] in _doc_cua(lat, kq[0].kf_id).lower(), "hạng 1 không chứa từ hiếm"


def test_xep_hang_giam_dan(kho_nho):
    p, lat = kho_nho
    tu = str(lat.iloc[0].doc_text).lower().split()[0]
    kq = tim(tu, top_k=20, docs_path=p)
    if len(kq) < 2:
        pytest.skip("ít kết quả quá, không kiểm được thứ tự")
    assert [r.score for r in kq] == sorted((r.score for r in kq), reverse=True)


def test_top_k_duoc_ton_trong(kho_nho):
    p, lat = kho_nho
    tu = str(lat.iloc[0].doc_text).lower().split()[0]
    assert len(tim(tu, top_k=3, docs_path=p)) <= 3


def test_khong_co_ket_qua_thi_tra_rong_chu_khong_sap(kho_nho):
    p, _ = kho_nho
    assert tim("zzzqqqxxx khongtontaidauca", docs_path=p) == []


def test_thieu_file_thi_tra_rong(tmp_path):
    """Chưa có docs_bm25 → UI vẫn mở được, chỉ là chế độ offline không dùng được."""
    assert tim("gì đó", docs_path=tmp_path / "khong_co.parquet") == []


# ------------------------------------------------------------------- kết quả

def test_ket_qua_du_truong_de_cham_nhan(kho_nho):
    """UI cần đủ 4 thứ để chấm nhãn: frame_idx thật · video · shot · trích dẫn."""
    p, lat = kho_nho
    tu = str(lat.iloc[0].doc_text).lower().split()[0]
    kq = tim(tu, top_k=3, docs_path=p)
    if not kq:
        pytest.skip("không có kết quả")
    r = kq[0]
    assert r.video_id and r.kf_id
    assert isinstance(r.frame_idx, int) and r.frame_idx >= 0
    assert r.trich, "phải có trích dẫn — không có thì không biết vì sao nó lên hạng"


def test_trich_dan_chua_tu_khoa(kho_nho):
    p, lat = kho_nho
    doc = str(lat.iloc[len(lat) // 3].doc_text)
    tu = next((t for t in doc.lower().split() if len(t) >= 6 and t.isalpha()), None)
    if tu is None:
        pytest.skip("không tìm được từ đủ dài")
    kq = tim(tu, top_k=1, docs_path=p)
    if not kq:
        pytest.skip("không có kết quả")
    assert tu in kq[0].trich.lower(), "trích dẫn phải cắt QUANH từ khớp, không phải đầu tài liệu"


def _doc_cua(lat, kf_id: str) -> str:
    hang = lat[lat.kf_id == kf_id]
    return "" if hang.empty else str(hang.iloc[0].doc_text)
