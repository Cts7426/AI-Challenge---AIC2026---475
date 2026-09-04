"""Regression test cho readiness gate trước giờ thi."""

from __future__ import annotations

import pytest

from backend.indexing import milvus_client
from scripts import warmup


class _MilvusChiCoClip:
    """Giả lập service còn collection chính nhưng mất collection phụ."""

    def has_collection(self, collection_name: str) -> bool:
        return collection_name == milvus_client.COLLECTION_NAME

    def get_collection_stats(self, collection_name: str) -> dict[str, int]:
        assert collection_name == milvus_client.COLLECTION_NAME
        return {"row_count": 177_321}


def test_kiem_milvus_bao_hong_khi_thieu_collection_siglip2(monkeypatch) -> None:
    """Warmup phải chặn release nếu nhánh vector phụ không có index để search."""
    monkeypatch.setattr(milvus_client, "connect", lambda: _MilvusChiCoClip())

    with pytest.raises(RuntimeError, match="keyframes_siglip2"):
        warmup._kiem_milvus()


# --------------------------- nhánh chết lặng trong lượt search (sự cố 04/09)
#
# `_kiem_milvus()` ở trên bắt được ca "collection biến mất". Nhưng nhánh còn
# chết theo kiểu khác mà kiểm kê tồn tại KHÔNG thấy: collection có mà chưa nạp
# vào RAM, lệch số chiều, client ES không tương thích. Những ca đó chỉ lộ ra khi
# CHẠY THẬT một truy vấn — và `_an_toan()` trong search.py nuốt hết, chỉ in một
# dòng cảnh báo rồi trả về đủ 100 dòng. Đây là phần warmup từng báo xanh sai.

def _cho_moi_buoc_dat(monkeypatch, co_canh_bao: bool) -> None:
    """Cho mọi bước warmup ĐẠT; chỉ điều khiển việc search có in cảnh báo không."""
    import numpy as np

    from backend.indexing import es_client
    from backend.retrieval import search as search_mod
    from backend.retrieval import siglip2_query, text_query

    monkeypatch.setattr(warmup, "_kiem_milvus", lambda: "keyframes: 177,321 vector")

    class _ESSong:
        def ping(self) -> bool:
            return True

    monkeypatch.setattr(es_client, "connect", lambda: _ESSong())

    vec = np.array([1.0, 0.0])
    monkeypatch.setattr(text_query, "encode_text", lambda q: vec)
    monkeypatch.setattr(siglip2_query, "encode_text", lambda q: vec)

    def _search_gia(*args, **kwargs):
        if co_canh_bao:
            # Nguyên văn định dạng của `_an_toan()` trong search.py.
            print("  [cảnh báo] nhánh vector_siglip2 lỗi, bỏ qua: collection not found")
        return [{"shot_id": f"s{i}", "score": 1.0} for i in range(100)]

    monkeypatch.setattr(search_mod, "search", _search_gia)


def test_warmup_do_khi_search_in_canh_bao(monkeypatch, capsys) -> None:
    """Nhánh chết lặng nhưng vẫn đủ 100 dòng → warmup PHẢI đỏ, không được xanh."""
    _cho_moi_buoc_dat(monkeypatch, co_canh_bao=True)

    assert warmup.main() == 1
    out = capsys.readouterr().out
    assert "CHƯA SẴN SÀNG" in out
    assert "vector_siglip2" in out, "phải nói rõ nhánh nào chết, không chỉ báo đỏ chung chung"


def test_warmup_xanh_khi_khong_co_canh_bao(monkeypatch, capsys) -> None:
    """Đối trọng: không có cảnh báo nào thì warmup vẫn xanh như cũ."""
    _cho_moi_buoc_dat(monkeypatch, co_canh_bao=False)

    assert warmup.main() == 0
    assert "SẴN SÀNG" in capsys.readouterr().out


def test_tien_to_canh_bao_van_khop_voi_search_py() -> None:
    """Ghim hợp đồng: warmup dò log của search.py bằng chuỗi, nên chuỗi phải khớp.

    Đổi câu chữ cảnh báo trong search.py mà quên chỗ này thì warmup lại xanh sai
    một lần nữa — mà không có test nào đỏ để báo. Test này là cái báo đó.
    """
    from pathlib import Path

    nguon = (Path(warmup.REPO_ROOT) / "backend/retrieval/search.py").read_text(encoding="utf-8")
    assert warmup.CANH_BAO in nguon, (
        f"search.py không còn in {warmup.CANH_BAO!r} — warmup đang dò một chuỗi không tồn tại"
    )
