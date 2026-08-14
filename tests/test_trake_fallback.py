# tests/test_trake_fallback.py — C4.4: fallback TRAKE, dữ liệu TỔNG HỢP có đáp
# án biết trước (BUILD_TASKS bắt buộc cho mọi thuật toán dễ sai chỉ số kiểu này).
#
# Trọng tâm — đúng 2 lỗi đã tìm ra và sửa ở Phase 2 review:
#   1. GIỮ VỊ TRÍ event, không sort theo giá trị (docs/contest.md: TRAKE khớp
#      THEO VỊ TRÍ — frame thứ j phải ứng với sự kiện thứ j)
#   2. Tăng dần NGẶT sau khi sửa, kể cả khi 2 event trả trùng frame hoặc tràn
#      khỏi độ dài video

from __future__ import annotations

from backend.tasks.trake_fallback import _fill_missing, _repair_strictly_increasing


# --------------------------------------------------------- _repair_strictly_increasing

def test_giu_nguyen_khi_da_tang_dan():
    """Chuỗi đã đúng thứ tự thì không được đổi — sửa nhầm cái đang đúng là mất điểm."""
    assert _repair_strictly_increasing([10, 30, 50, 70], 1000) == [10, 30, 50, 70]


def test_day_frame_trung_len_1():
    """2 event trả cùng frame_idx (hai máy tìm chung 1 shot) → tách bằng +1."""
    out = _repair_strictly_increasing([10, 10, 10], 1000)
    assert out == [10, 11, 12]
    assert all(a < b for a, b in zip(out, out[1:]))


def test_khong_sap_xep_lai_theo_gia_tri():
    """⚠️ Bài học đắt nhất của review: event-3 khớp SỚM HƠN event-1 (false
    positive) — thuật toán ĐÚNG là giữ event-3 ở vị trí 3 (chỉ đẩy +1 nếu cần),
    KHÔNG được đưa frame nhỏ lên vị trí 1. Đây chính là bug đã tìm thấy ở
    plan gốc (sort theo giá trị) và là lý do trake_fallback.py viết lại thuật
    toán này."""
    # event 1 = frame 50 (đúng), event 2 = frame 60 (đúng), event 3 = frame 20 (SAI, false positive)
    out = _repair_strictly_increasing([50, 60, 20], 1000)
    # Sort sẽ cho [20, 50, 60] — SAI vì đẩy "bằng chứng của event 3" vào vị trí 1.
    # Thuật toán giữ vị trí sẽ đẩy phần tử thứ 3 lên > 60, GIỮ event 1/2 nguyên vẹn.
    assert out[0] == 50 and out[1] == 60
    assert out[2] > out[1]
    assert out != sorted(out) or out == [50, 60, 61]  # (tăng dần NGẶT nhưng KHÔNG phải do sort)


def test_vuot_do_dai_video_dich_ca_chuoi():
    """4 event dồn về cuối video ngắn → toàn chuỗi dịch xuống, vẫn tăng dần ngặt,
    vẫn nằm trong [0, n_frames)."""
    out = _repair_strictly_increasing([995, 996, 997, 998], 1000)
    assert out[-1] <= 999
    assert all(a < b for a, b in zip(out, out[1:]))
    assert all(0 <= f < 1000 for f in out)


def test_video_ngan_vua_du_van_tang_dan_ngat():
    """Video ngắn nhưng VẪN ĐỦ TOÁN HỌC để có N số nguyên phân biệt tăng dần
    (n_frames_video >= số sự kiện) — phải rải đều CHÍNH XÁC, không đụng nhau."""
    out = _repair_strictly_increasing([0, 0, 0, 0, 0], 5)
    assert len(out) == 5
    assert all(a < b for a, b in zip(out, out[1:]))
    assert all(0 <= f < 5 for f in out)


def test_video_qua_ngan_khong_the_ve_toan_hoc_khong_crash():
    """Ca bất khả thi về mặt toán học: video chỉ có 3 frame cho 5 sự kiện —
    không đủ số nguyên phân biệt để tăng dần ngặt cả 5. Không crash, không trả
    số âm/vượt biên; chấp nhận vài phần tử trùng ở sát biên cuối (trường hợp
    này thực tế không xảy ra: N sự kiện TRAKE luôn rất nhỏ so với độ dài video)."""
    out = _repair_strictly_increasing([0, 0, 0, 0, 0], 3)
    assert len(out) == 5
    assert all(0 <= f < 3 for f in out)
    assert out == sorted(out)  # vẫn KHÔNG GIẢM, dù không thể tăng dần NGẶT hết


# --------------------------------------------------------------------- _fill_missing

def test_fill_khong_thieu_gi_tra_nguyen():
    assert _fill_missing([10, 20, 30]) == [10, 20, 30]


def test_fill_noi_suy_giua_2_event_lan_can():
    """Event giữa không có bằng chứng → nội suy tuyến tính, không phải giá trị bịa."""
    out = _fill_missing([10, None, 30])
    assert out == [10, 20, 30]


def test_fill_thieu_o_dau_dung_gia_tri_lan_can():
    out = _fill_missing([None, 20, 30])
    assert out[0] == 20
    assert out[1:] == [20, 30]


def test_fill_thieu_o_cuoi_dung_gia_tri_lan_can():
    out = _fill_missing([10, 20, None])
    assert out[:2] == [10, 20]
    assert out[2] == 20


def test_fill_nhieu_lo_lien_tiep():
    out = _fill_missing([10, None, None, 40])
    assert out[0] == 10 and out[-1] == 40
    assert out[1] < out[2]  # nội suy vẫn phải đơn điệu giữa 2 mốc biết


def test_fill_toan_bo_none_raise():
    import pytest
    with pytest.raises(RuntimeError):
        _fill_missing([None, None, None])


# ---------------------------------------------------------- kết hợp cả 2 bước (thực tế)

def test_pipeline_day_du_event_thieu_giua_video_ngan():
    """Mô phỏng luồng thật của trake_stage2_fallback: fill rồi mới repair."""
    raw = [100, None, 100, 500]  # event 2 thiếu, event 3 trùng event 1
    filled = _fill_missing(raw)
    assert None not in filled
    out = _repair_strictly_increasing(filled, n_frames_video=10_000)
    assert all(a < b for a, b in zip(out, out[1:]))
