# tests/test_ndcg.py — A2.4: test nDCG@k (dev_set/tools/scoring.py)
#
# nDCG là thước dùng để QUYẾT ĐỊNH bật hay tắt rerank. Thước sai thì quyết định
# sai, mà nDCG sai rất khó nhận ra bằng mắt: nó vẫn trả một số trong [0, 1],
# vẫn tăng giảm hợp lý, chỉ là tăng giảm theo thứ khác. Nên mỗi tính chất được
# kiểm bằng một ca có ĐÁP SỐ TỰ TÍNH ĐƯỢC.
#
# Chạy: python -m pytest tests/test_ndcg.py -q

from __future__ import annotations

import math

import pytest

from data.config.submit_format import Answer
from dev_set.tools.schema import GroundTruthKIS
from dev_set.tools.scoring import ndcg_at_k

GT = GroundTruthKIS(query_id="q", video_id="L21_V001", frame_start=100, frame_end=200)


def _rows(*dung: bool) -> list[Answer]:
    """Dựng list Answer: True = nằm trong [100, 200] (đúng), False = sai video."""
    ra = []
    for i, d in enumerate(dung):
        if d:
            ra.append(Answer(video_id="L21_V001", frame_ids=(150,), keyframe_id=f"kf{i}"))
        else:
            ra.append(Answer(video_id="L99_V999", frame_ids=(1,), keyframe_id=f"kf{i}"))
    return ra


# --------------------------------------------------------------- tính chất cơ bản

def test_xep_hoan_hao_bang_1():
    """Mọi dòng đúng đều ở trên cùng → nDCG = 1."""
    assert ndcg_at_k(_rows(True, True, False, False), GT, "KIS", k=4) == pytest.approx(1.0)


def test_khong_co_dong_nao_dung_bang_0():
    assert ndcg_at_k(_rows(False, False, False), GT, "KIS", k=3) == 0.0


def test_dung_o_hang_1_hon_dung_o_hang_2():
    """Tính chất sống còn: đẩy câu đúng lên hạng cao phải làm điểm TĂNG."""
    tren = ndcg_at_k(_rows(True, False, False), GT, "KIS", k=3)
    duoi = ndcg_at_k(_rows(False, True, False), GT, "KIS", k=3)
    assert tren > duoi
    assert tren == pytest.approx(1.0)
    assert duoi == pytest.approx(1 / math.log2(3))   # DCG=1/log2(3), IDCG=1


def test_gia_tri_dung_voi_hai_dong_dung():
    """Đúng ở hạng 2 và 3, IDCG là hạng 1 và 2 → tự tính ra được con số."""
    got = ndcg_at_k(_rows(False, True, True), GT, "KIS", k=3)
    dcg = 1 / math.log2(3) + 1 / math.log2(4)
    idcg = 1 / math.log2(2) + 1 / math.log2(3)
    assert got == pytest.approx(dcg / idcg)


def test_cat_dung_k():
    """Dòng đúng nằm ngoài k không được tính vào tử số."""
    rows = _rows(False, False, False, True)
    assert ndcg_at_k(rows, GT, "KIS", k=3) == 0.0
    assert ndcg_at_k(rows, GT, "KIS", k=4) > 0.0


def test_k_khong_hop_le():
    with pytest.raises(ValueError, match="k phải"):
        ndcg_at_k(_rows(True), GT, "KIS", k=0)


# ------------------------------------------------- mẫu số chung khi A/B hai cách xếp

def test_ideal_rels_lam_hai_ben_so_duoc_voi_nhau():
    """⚠️ Cái bẫy của A/B: hai bên giữ hai tập ứng viên khác nhau → hai mẫu số
    khác nhau → hai số nDCG trông như so được mà thật ra không.

    Bên A giữ 2 dòng đúng, bên B chỉ giữ 1 (rerank cắt mất 1). Nếu để mỗi bên tự
    tính IDCG, bên B được chuẩn hoá theo chính sự nghèo nàn của nó và ăn điểm cao.
    """
    a = _rows(True, True, False)        # 2 đúng, cả hai ở trên
    b = _rows(True, False, False)       # rerank đánh rơi 1 dòng đúng

    tu_tinh_a = ndcg_at_k(a, GT, "KIS", k=3)
    tu_tinh_b = ndcg_at_k(b, GT, "KIS", k=3)
    assert tu_tinh_a == pytest.approx(tu_tinh_b) == pytest.approx(1.0), \
        "mỗi bên tự chuẩn hoá → mất một dòng đúng mà điểm vẫn 1.0"

    chung = [1.0, 1.0, 0.0]             # bể ứng viên chung có 2 dòng đúng
    assert ndcg_at_k(a, GT, "KIS", k=3, ideal_rels=chung) > \
           ndcg_at_k(b, GT, "KIS", k=3, ideal_rels=chung), \
        "cùng mẫu số thì bên đánh rơi dòng đúng PHẢI thấp điểm hơn"


# ------------------------------------------------------------------ TRAKE điểm lẻ

def test_trake_diem_le_duoc_nhan_dung():
    """TRAKE cho điểm theo tỉ lệ khoảnh khắc khớp — nDCG phải dùng được điểm lẻ đó."""
    from dev_set.tools.schema import GroundTruthTRAKE

    gt = GroundTruthTRAKE(query_id="t", video_id="V",
                          frames=[{"start": 10, "end": 20}, {"start": 30, "end": 40}])
    dung_het = Answer(video_id="V", frame_ids=(15, 35))     # 2/2 → rel 1.0
    dung_nua = Answer(video_id="V", frame_ids=(15, 99))     # 1/2 → rel 0.5

    tot = ndcg_at_k([dung_het, dung_nua], gt, "TRAKE", k=2)
    xau = ndcg_at_k([dung_nua, dung_het], gt, "TRAKE", k=2)
    assert tot > xau, "dòng khớp nhiều khoảnh khắc hơn phải được xếp trên"
