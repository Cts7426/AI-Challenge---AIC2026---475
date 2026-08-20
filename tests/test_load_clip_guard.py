# tests/test_load_clip_guard.py — chốt chặn vector giả của load_clip (20/08)
#
# Bối cảnh: 19/08 vector ngẫu nhiên lọt vào Milvus và ở đó 24 giờ. Mọi phép kiểm
# đang có đều PASS — norm = 1, dim = 512, meta khớp config, search trả top-k với
# điểm 0,2–0,3 trông y hệt kết quả đúng. Chỉ có điểm dev set (KIS Final 0,047 vs
# 0,496) mới lộ ra. Test này khoá lại phép kiểm duy nhất bắt được nó.
#
# Không cần Docker, không cần file thật: dựng .npy tổng hợp trong tmp_path theo
# ĐÚNG hai công thức đã đo được ngoài đời.
#
# Chạy: python -m pytest tests/test_load_clip_guard.py -q

from __future__ import annotations

import numpy as np
import pytest

from backend.indexing.load_clip import assert_not_mock
from data.config.clip_model import CLIP_EMBEDDING_DIM

DIM = CLIP_EMBEDDING_DIM


def _ghi(thu_muc, ten: str, arr: np.ndarray) -> None:
    arr = arr / np.linalg.norm(arr, axis=1, keepdims=True)
    np.save(thu_muc / ten, arr.astype(np.float32))


def _mock(thu_muc, n_video: int = 45, n_kf: int = 6) -> list[str]:
    """Đúng công thức của data/sample/generate_clip_features.py:
    mỗi video một `base` ngẫu nhiên, keyframe = 0.85*base + 0.15*nhiễu."""
    rng = np.random.default_rng(0)
    ten_file = []
    for i in range(n_video):
        base = rng.standard_normal(DIM)
        rows = 0.85 * base + 0.15 * rng.standard_normal((n_kf, DIM))
        ten = f"L21_V{i:03d}.npy"
        _ghi(thu_muc, ten, rows)
        ten_file.append(ten)
    return ten_file


def _that(thu_muc, n_video: int = 45, n_kf: int = 6) -> list[str]:
    """Mô phỏng hiệu ứng nón của CLIP thật: mọi ảnh chia chung một hướng trội.

    ⚠️ Ba thành phần phải CÙNG THANG. Bản đầu viết `0.75*non_da_chuan_hoa +
    0.25*randn(512)` — nhiễu có norm ≈ √512 ≈ 22,6 nên nuốt sạch hướng chung
    (norm 1), kết quả ra vector ngẫu nhiên thuần và test tự báo "thật" là mock.
    Dùng Gaussian chưa chuẩn hoá cho cả ba thì tỉ lệ hệ số mới đúng là tỉ lệ
    phương sai: cosine khác video ≈ 1/(1 + 0,816² + 0,5²) ≈ 0,52 — sát số đo
    thật trên features BTC (0,56).
    """
    rng = np.random.default_rng(1)
    non = rng.standard_normal(DIM)                       # hướng chung của cả kho
    ten_file = []
    for i in range(n_video):
        canh = non + 0.816 * rng.standard_normal(DIM)    # bối cảnh riêng mỗi video
        rows = canh + 0.5 * rng.standard_normal((n_kf, DIM))
        ten = f"L21_V{i:03d}.npy"
        _ghi(thu_muc, ten, rows)
        ten_file.append(ten)
    return ten_file


def test_tu_choi_vector_ngau_nhien(tmp_path):
    """Ca 19/08: vector Gaussian ngẫu nhiên PHẢI bị chặn trước khi nạp."""
    files = _mock(tmp_path)
    with pytest.raises(ValueError, match="VECTOR NGẪU NHIÊN"):
        assert_not_mock(tmp_path, files)


def test_thong_bao_noi_ro_phai_lam_gi(tmp_path):
    """Thông báo phải chỉ được đường ra, không chỉ nói 'sai'."""
    files = _mock(tmp_path)
    with pytest.raises(ValueError) as e:
        assert_not_mock(tmp_path, files)
    msg = str(e.value)
    assert "clip-features-32-aic25-b1.zip" in msg, "phải chỉ ra file features thật"
    assert "VÔ NGHĨA" in msg, "phải nói rõ hậu quả, không chỉ báo lỗi kỹ thuật"


def test_cho_qua_embedding_that(tmp_path):
    """CLIP thật có hiệu ứng nón → cosine khác video cao → phải được nạp."""
    files = _that(tmp_path)
    assert assert_not_mock(tmp_path, files) > 0.3


def test_khoang_cach_giua_hai_ca_du_rong(tmp_path_factory):
    """Không được có vùng xám: hai ca phải cách xa ngưỡng, không sát nút.

    Số đo ngoài đời 20/08: mock +0,0003 · thật +0,6890 · ngưỡng 0,15.
    """
    from backend.indexing.load_clip import MOCK_COSINE_MAX

    d_that = tmp_path_factory.mktemp("that")
    that = assert_not_mock(d_that, _that(d_that))
    assert that > MOCK_COSINE_MAX * 2, f"ca thật chỉ {that:.4f}, quá sát ngưỡng"

    d_mock = tmp_path_factory.mktemp("mock")
    files = _mock(d_mock)
    with pytest.raises(ValueError) as e:
        assert_not_mock(d_mock, files)
    con_so = float(str(e.value).split("khác nhau:")[1].split("(")[0])
    assert abs(con_so) < MOCK_COSINE_MAX / 2, f"ca mock ra {con_so:.4f}, quá sát ngưỡng"


def test_qua_it_file_thi_bo_qua_chot(tmp_path):
    """1 video thì không có cặp KHÁC video để so — trả NaN, KHÔNG chặn nhầm."""
    _mock(tmp_path, n_video=1)
    kq = assert_not_mock(tmp_path, ["L21_V000.npy"])
    assert kq != kq, "phải trả NaN khi không đủ dữ liệu để phán quyết"


def test_file_thieu_khong_lam_sap(tmp_path):
    """Tên file có trong danh sách mà không có trên đĩa → bỏ qua, không nổ."""
    files = _that(tmp_path, n_video=10)
    assert assert_not_mock(tmp_path, files + ["KHONG_TON_TAI.npy"]) > 0.3
