# tests/test_offline_search.py — D2.1: BM25 thô, đường lui khi không có Docker
#
# Dữ liệu thật nhưng CẮT NHỎ: một truy vấn trên toàn kho tốn ~8 s, chạy chục ca là
# hết hai phút. Lát cắt vài nghìn dòng giữ nguyên tính thật (vẫn là `doc_text` của
# Công Lý, vẫn qua đúng đường code) mà chạy trong tích tắc.

from __future__ import annotations

import pytest

from app.offline_search import DOCS_PATH, _count_whole_word, search, tokenize


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
    assert tokenize("ở nhà có 3 người") == ["nhà", "có", "người"]


def test_tach_tu_KHONG_bo_dau():
    """Chốt lại một đánh đổi có chủ ý, để sau này không ai tưởng là quên làm.

    Bỏ dấu cả kho tốn 40,4 s mỗi truy vấn (đo trên 371.702 tài liệu) so với 6,2 s chỉ
    viết thường. Đường thi có `VI_FOLDED_ANALYSIS` của Elasticsearch lo việc này;
    đường lui thì chấp nhận phải gõ có dấu.
    """
    assert tokenize("Hà Nội") == ["hà", "nội"], "đang bỏ dấu — xem lại số đo trước khi đổi"


def test_tach_tu_bo_trung_giu_thu_tu():
    assert tokenize("bóng đá bóng rổ") == ["bóng", "đá", "rổ"]


def test_tach_tu_viet_thuong():
    assert tokenize("Hà Nội") == ["hà", "nội"]


def test_truy_van_rong_tra_rong(kho_nho):
    p, _ = kho_nho
    assert search("", docs_path=p) == []
    assert search("a ở", docs_path=p) == []


# ------------------------------------------------------------------ tìm kiếm

def test_tim_duoc_tu_co_that_trong_doc_text(kho_nho):
    """Lấy một từ CÓ THẬT trong kho rồi tra ngược — phải ra frame chứa nó."""
    p, lat = kho_nho
    doc = str(lat.iloc[len(lat) // 2].doc_text)
    tu = next((t for t in doc.lower().split() if len(t) >= 5 and t.isalpha()), None)
    if tu is None:
        pytest.skip("không tìm được từ đủ dài trong lát cắt này")

    kq = search(tu, top_k=10, docs_path=p)
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

    kq = search(hiem[0], top_k=5, docs_path=p)
    assert kq, f"từ hiếm '{hiem[0]}' tra không ra"
    assert hiem[0] in _doc_cua(lat, kq[0].kf_id).lower(), "hạng 1 không chứa từ hiếm"


def test_xep_hang_giam_dan(kho_nho):
    p, lat = kho_nho
    tu = str(lat.iloc[0].doc_text).lower().split()[0]
    kq = search(tu, top_k=20, docs_path=p)
    if len(kq) < 2:
        pytest.skip("ít kết quả quá, không kiểm được thứ tự")
    assert [r.score for r in kq] == sorted((r.score for r in kq), reverse=True)


def test_top_k_duoc_ton_trong(kho_nho):
    p, lat = kho_nho
    tu = str(lat.iloc[0].doc_text).lower().split()[0]
    assert len(search(tu, top_k=3, docs_path=p)) <= 3


def test_khong_co_ket_qua_thi_tra_rong_chu_khong_sap(kho_nho):
    p, _ = kho_nho
    assert search("zzzqqqxxx khongtontaidauca", docs_path=p) == []


def test_thieu_file_thi_tra_rong(tmp_path):
    """Chưa có docs_bm25 → UI vẫn mở được, chỉ là chế độ offline không dùng được."""
    assert search("gì đó", docs_path=tmp_path / "khong_co.parquet") == []


# ------------------------------------------------------------------- kết quả

def test_ket_qua_du_truong_de_cham_nhan(kho_nho):
    """UI cần đủ 4 thứ để chấm nhãn: frame_idx thật · video · shot · trích dẫn."""
    p, lat = kho_nho
    tu = str(lat.iloc[0].doc_text).lower().split()[0]
    kq = search(tu, top_k=3, docs_path=p)
    if not kq:
        pytest.skip("không có kết quả")
    r = kq[0]
    assert r.video_id and r.kf_id
    assert isinstance(r.frame_idx, int) and r.frame_idx >= 0
    assert r.snippet, "phải có trích dẫn — không có thì không biết vì sao nó lên hạng"


def test_trich_dan_chua_tu_khoa(kho_nho):
    p, lat = kho_nho
    doc = str(lat.iloc[len(lat) // 3].doc_text)
    tu = next((t for t in doc.lower().split() if len(t) >= 6 and t.isalpha()), None)
    if tu is None:
        pytest.skip("không tìm được từ đủ dài")
    kq = search(tu, top_k=1, docs_path=p)
    if not kq:
        pytest.skip("không có kết quả")
    assert tu in kq[0].snippet.lower(), "trích dẫn phải cắt QUANH từ khớp, không phải đầu tài liệu"


# ------------------------------------------------- đếm từ, không đếm chuỗi con

def test_dem_theo_TU_khong_theo_chuoi_con(kho_nho):
    """Từ khoá chỉ được tính khi đứng RIÊNG, không phải khi nằm trong từ khác.

    Tiếng Việt đơn âm nên đây không phải ca hiếm: đo trên L21_V001, 'ba' khớp 1.078
    lần theo chuỗi con nhưng chỉ 24 lần như một từ — thổi phồng 45 lần. Hậu quả thật
    đã thấy: gõ 'ba' ra hạng 1 là một tài liệu chứa '#baothanhnien', không hề có chữ
    'ba' nào. Rác lên đầu mà không có dấu hiệu gì.
    """
    import pandas as pd

    p, lat = kho_nho
    moi = lat.copy()
    # hai tài liệu bịa: một cái chứa ĐÚNG từ, một cái chỉ chứa nó như chuỗi con
    moi.loc[len(moi)] = ["ZZ_V000_0000001", "ZZ_V000", "ZZ_V000#s1", 1, "con voi qua duong"]
    moi.loc[len(moi)] = ["ZZ_V000_0000002", "ZZ_V000", "ZZ_V000#s1", 2,
                         "concon concert conconcon"]
    q = p.parent / "docs_dem.parquet"
    pd.DataFrame(moi).to_parquet(q, index=False)

    kq = search("con", top_k=5, docs_path=q)
    thang = [r.kf_id for r in kq]
    assert "ZZ_V000_0000001" in thang, "tài liệu chứa đúng từ 'con' phải lọt top"
    assert "ZZ_V000_0000002" not in thang, (
        "'concon/concert' KHÔNG chứa từ 'con' — đang đếm chuỗi con, xem _count_whole_word()"
    )


def test_ranh_gioi_tu_hieu_NGUYEN_AM_CO_DAU():
    """Nguyên âm có dấu phải được tính là CHỮ CÁI khi xác định ranh giới từ.

    Đây là lỗi đã thật sự xảy ra, phát hiện khi tra "tù nhân" ra toàn "nạn nhân".
    `\\b` của RE2 chỉ coi [A-Za-z0-9_] là chữ cái, nên với từ khoá 'tù':
      · 'tù nhân'  → sau 'ù' là dấu cách, RE2 coi cả hai đều không-phải-chữ nên
                     KHÔNG thấy ranh giới → không khớp (SAI, phải khớp)
      · 'ông tùng' → sau 'ù' là 'n', RE2 thấy ranh giới → khớp (SAI, không được khớp)
    Sai ngược hoàn toàn. Bản sửa dùng `\\p{L}` (lớp chữ cái Unicode).

    Kiểm thẳng `_count_whole_word` chứ không qua `search()`: đi qua BM25 thì một tf sai có
    thể bị IDF che, test xanh mà lỗi vẫn còn.
    """
    import pandas as pd

    van = pd.Series(["tù nhân bỏ trốn", "nạn nhân là ông tùng", "không liên quan", "tù tù"])
    assert _count_whole_word(van, "tù").tolist() == [1.0, 0.0, 0.0, 2.0]


def test_ranh_gioi_tu_khop_voi_module_re_chuan():
    """Đối chiếu với `re` của Python — thước đo độc lập, không cùng công cụ regex."""
    import re as _re

    import pandas as pd

    mau = ["tù,tù", "xtù tù", "tù.tù.tù", "1tù tù2", "tù-tù", "tùtù", ""]
    van = pd.Series(mau)
    mong_doi = [float(len(_re.findall(r"\btù\b", s))) for s in mau]
    assert _count_whole_word(van, "tù").tolist() == mong_doi


def test_tra_duoc_cum_tu_co_that_trong_kho(kho_nho):
    """Tài liệu chứa CẢ HAI từ phải xếp trên tài liệu chỉ chứa một từ phổ biến.

    Ca thật đã trượt: "tù nhân" trả về toàn "nạn nhân là ông tùng" — tài liệu có
    đúng chữ "tù nhân" không lọt top vì tf của 'tù' bị tính bằng 0.
    """
    import pandas as pd

    p, lat = kho_nho
    moi = lat.copy()
    moi.loc[len(moi)] = ["ZZ_V002_0000001", "ZZ_V002", "ZZ_V002#s1", 1,
                         "bạo loạn của tù nhân trong trại giam"]
    moi.loc[len(moi)] = ["ZZ_V002_0000002", "ZZ_V002", "ZZ_V002#s1", 2,
                         "nạn nhân là ông tùng 53 tuổi"]
    q = p.parent / "docs_cum.parquet"
    pd.DataFrame(moi).to_parquet(q, index=False)

    thang = [r.kf_id for r in search("tù nhân", top_k=5, docs_path=q)]
    assert thang and thang[0] == "ZZ_V002_0000001", (
        f"tài liệu chứa đúng 'tù nhân' phải đứng đầu, đang là {thang[:3]}"
    )


def _doc_cua(lat, kf_id: str) -> str:
    hang = lat[lat.kf_id == kf_id]
    return "" if hang.empty else str(hang.iloc[0].doc_text)


# ===================== nhánh chưa từng chạy (đo bằng trace) — phủ nốt cho kín

def test_snippet_khi_khong_tu_nao_khop():
    from app.offline_search import _snippet
    assert _snippet("xin chào thế giới", ["khongcotu"]) == "xin chào thế giới"


def test_o_rong_parquet_KHONG_thanh_chuoi_nan():
    """`str(NaN)` ra chuỗi 'nan' rồi trôi thẳng vào file nhãn, không ai nhận ra."""
    from app.offline_search import _str_or_none
    assert _str_or_none(float("nan")) is None
    assert _str_or_none(None) is None
    assert _str_or_none("L21_V001#s0001") == "L21_V001#s0001"


def test_kho_rong_tra_ve_rong(tmp_path):
    """docs_bm25 rỗng → trả [] chứ không chia cho 0 ở avg_len."""
    import pandas as pd
    p = tmp_path / "docs_bm25.parquet"
    pd.DataFrame({"kf_id": [], "video_id": [], "shot_id": [], "frame_idx": [],
                  "doc_text": []}).astype(
        {"kf_id": "object", "video_id": "object", "shot_id": "object",
         "frame_idx": "int64", "doc_text": "object"}).to_parquet(p)
    assert search("thủ môn", docs_path=p) == []


def test_doc_text_toan_rong_tra_ve_rong(tmp_path):
    """avg_len == 0 → phép chia `lengths / avg_len` sẽ ra inf/NaN nếu không chặn."""
    import pandas as pd
    p = tmp_path / "docs_bm25.parquet"
    pd.DataFrame({"kf_id": ["a"], "video_id": ["V"], "shot_id": ["s"],
                  "frame_idx": [1], "doc_text": [""]}).to_parquet(p)
    assert search("thủ môn", docs_path=p) == []


def test_file_khong_ton_tai_tra_ve_rong(tmp_path):
    assert search("thủ môn", docs_path=tmp_path / "khong_co.parquet") == []
