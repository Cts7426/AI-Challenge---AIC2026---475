# tests/test_evidence.py — D2.1: tra bằng chứng của một keyframe
#
# Trọng tâm là CẦU NỐI HAI HỆ TÊN (xem đầu app/evidence.py). Nối sai thì panel bằng
# chứng trống trơn mà không crash, không cảnh báo — người chấm nhãn tưởng frame đó
# không có OCR/ASR gì, rồi chấm sai. Đúng loại lỗi im lặng cả dự án đang phòng.
#
# Dữ liệu thật, không mock: lấy thẳng từ data/derived/ như test của D0.2 và D3.1.

from __future__ import annotations

import pytest

from app.evidence import bang_chung, keyframe_cung_shot, tach_id


@pytest.fixture(scope="module")
def cap_id():
    """Một cặp (id kiểu BTC, id kiểu tự trích) CÓ THẬT, cùng trỏ một chỗ."""
    import pandas as pd

    from app.evidence import DERIVED

    p = DERIVED / "clip_kf_map.parquet"
    if not p.exists():
        pytest.skip("chưa có clip_kf_map.parquet — cần Data Factory giao trước")
    df = pd.read_parquet(p, columns=["kf_id", "clip_kf_id", "video_id"])
    df = df[df.clip_kf_id.notna()]
    if df.empty:
        pytest.skip("clip_kf_map.parquet không có dòng nào nối được hai hệ tên")
    r = df.iloc[len(df) // 2]
    return str(r.clip_kf_id), str(r.kf_id), str(r.video_id)


# ------------------------------------------------------------ dịch giữa hai hệ

def test_dich_duoc_ca_hai_chieu(cap_id):
    """Đưa vào hệ nào cũng phải ra được cả hai dạng — đây là cả lý do file này tồn tại.

    Chiều tự-trích → BTC là 1-1 nên so bằng được. Chiều ngược lại là NHIỀU-VỀ-MỘT
    (75.124/166.661 keyframe BTC ứng với >1 keyframe tự trích, nhiều nhất 6), nên chỉ
    đòi hỏi: dịch xuôi rồi dịch ngược phải quay về đúng chỗ cũ.
    """
    btc, own, video = cap_id
    assert tach_id(own) == (video, btc, own)

    v2, btc2, own2 = tach_id(btc)
    assert (v2, btc2) == (video, btc)
    assert own2 is not None and tach_id(own2)[1] == btc, "dịch xuôi-ngược phải khép kín"


def test_chieu_nhieu_ve_mot_chon_keyframe_GAN_NHAT(cap_id):
    """BTC → tự trích phải lấy cái `frame_drift` NHỎ NHẤT, không phải cái gặp sau cùng.

    Lấy bừa thì bằng chứng hiển thị lệch tới 22 frame so với ảnh đang nhìn — gần một
    giây, đủ để đọc nhầm nội dung frame mà không có dấu hiệu gì.
    """
    import pandas as pd

    from app.evidence import DERIVED

    btc, _, video = cap_id
    df = pd.read_parquet(DERIVED / "clip_kf_map.parquet",
                         columns=["kf_id", "clip_kf_id", "frame_drift"],
                         filters=[("video_id", "==", video)])
    ung_vien = df[df.clip_kf_id == btc]
    if len(ung_vien) < 2:
        pytest.skip("keyframe BTC này chỉ có 1 ứng viên, không kiểm được phép chọn")
    gan_nhat = str(ung_vien.loc[ung_vien.frame_drift.idxmin()].kf_id)
    assert tach_id(btc)[2] == gan_nhat


def test_khong_bia_id_bang_cach_ghep_chuoi(cap_id):
    """Dạng còn lại phải TRA từ clip_kf_map, không được suy ra bằng phép thay chuỗi.

    `L21_V001#k0004` → `L21_V001_0000375`: hậu tố 0000375 là frame_idx, không có
    quan hệ số học nào với 0004. Ghép chuỗi là đúng kiểu suy diễn mà W0.2 đã cấm.
    """
    btc, own, _ = cap_id
    assert own != btc.replace("#k", "_"), "cặp test này quá dễ, không chứng minh được gì"


def test_id_la_khong_lam_sap():
    video, btc, own = tach_id("khong_theo_he_nao")
    assert btc is None and own is None


@pytest.mark.parametrize("xau", ["", None, 123])
def test_dau_vao_khong_phai_chuoi_tra_rong(xau):
    """Ô rỗng của parquet ra `NAType`, UI có thể dán vào `None` — không được nổ regex."""
    assert tach_id(xau) == ("", None, None)


# --------------------------------------------------------------- gom bằng chứng

def test_bang_chung_co_du_thong_tin_nhan_dang(cap_id):
    btc, own, video = cap_id
    bc = bang_chung(btc)
    assert bc.video_id == video
    assert bc.kf_id_btc == btc
    # nhiều-về-một: chỉ đòi hỏi dịch được và khép kín, không đòi đúng dòng đã bốc
    assert bc.kf_id_tu_trich and tach_id(bc.kf_id_tu_trich)[1] == btc
    assert bc.frame_idx is not None and bc.frame_idx >= 0
    assert bc.n_frames_video and bc.frame_idx < bc.n_frames_video


def test_frame_idx_lay_tu_frame_map_khong_phai_hau_to_id(cap_id):
    """`frame_idx` phải là con số BTC chấm, tra từ frame_map.

    Hậu tố của id tự trích cũng là một frame_idx, nhưng của keyframe TỰ CẮT — lệch
    với keyframe BTC trung vị 11 frame (đo trên clip_kf_map.frame_drift). Lấy nhầm
    là sai lệch nửa giây ở mọi dòng.
    """
    import pandas as pd

    from app.evidence import DERIVED

    btc, _, video = cap_id
    fm = pd.read_parquet(DERIVED / "frame_map.parquet", columns=["kf_id", "frame_idx"],
                         filters=[("video_id", "==", video)])
    mong_doi = int(fm[fm.kf_id == btc].iloc[0].frame_idx)
    assert bang_chung(btc).frame_idx == mong_doi


def test_doc_text_khong_trong_khi_co_cau_noi(cap_id):
    """`doc_text` nằm ở bảng dùng hệ TỰ TRÍCH — nối thẳng id BTC vào là rỗng trắng."""
    btc, _, _ = cap_id
    bc = bang_chung(btc)
    assert bc.doc_text, "cầu nối clip_kf_map hỏng → panel 'vì sao lên hạng' sẽ trống"
    assert bc.shot_id, "shot_id cũng lấy từ bảng hệ tự trích"


def test_shot_bien_bao_frame_cua_no(cap_id):
    """Biên shot phải thật sự chứa frame đang xem — nếu không thì đang nối nhầm shot."""
    btc, _, _ = cap_id
    bc = bang_chung(btc)
    if bc.shot_bien is None:
        pytest.skip("shot này không có trong shots.parquet")
    s, e = bc.shot_bien
    assert s <= bc.frame_idx <= e, f"frame {bc.frame_idx} nằm ngoài shot [{s}, {e}]"


def test_timestamp_khop_voi_frame_idx(cap_id):
    """timestamp = frame_idx / fps. Sai chỗ này thì cửa sổ ASR ±3s cũng sai theo."""
    btc, _, _ = cap_id
    bc = bang_chung(btc)
    if bc.timestamp_s is None:
        pytest.skip("video_info thiếu fps")
    assert 0 <= bc.timestamp_s <= 24 * 3600
    assert abs(bc.timestamp_s * 25 - bc.frame_idx) < bc.frame_idx * 0.5 + 100


def test_keyframe_la_tra_ve_rong_chu_khong_raise():
    """Keyframe không có trong kho → panel trống kèm cảnh báo, KHÔNG được sập UI."""
    bc = bang_chung("L99_V999#k0001")
    assert bc.ocr == [] and bc.asr == [] and bc.doc_text is None
    assert bc.canh_bao, "thiếu dữ liệu thì phải BÁO, không im lặng"


def test_cach_bao_khi_khong_tra_duoc_frame_idx():
    bc = bang_chung("L99_V999#k0001")
    assert any("frame_idx" in c for c in bc.canh_bao)


def test_doi_ten_cot_thi_bao_DUNG_nguyen_nhan(cap_id, monkeypatch):
    """Data Factory đổi tên cột → UI phải nói "đổi lược đồ", không đoán thành "thiếu dữ liệu".

    Đã đổi tên cột một lần ngày 07/08 (`n_frames` → `nb_frames_decoded`,
    `frame_idx_corrected` → `frame_idx`), sẽ còn đổi nữa. Nếu chỉ in ra console thì vô
    dụng: người dùng UI đang nhìn trình duyệt, không nhìn terminal — họ sẽ đọc panel
    trống thành "frame này không có dữ liệu" rồi chấm nhãn dựa trên kết luận sai.
    """
    import app.evidence as ev

    btc, _, _ = cap_id
    goc = ev._doc
    monkeypatch.setattr(
        ev, "_doc",
        lambda ten, cot, v=None: goc(ten, cot + (["cot_bia_ra"] if ten == "docs_bm25" else []), v),
    )
    ev.xoa_cache()
    ev._LOI_LUOC_DO.clear()
    try:
        bc = bang_chung(btc)
        assert any("docs_bm25" in c and "thiếu cột" in c for c in bc.canh_bao), bc.canh_bao
        # phải nêu tên cột đang có, để người sửa biết đổi thành gì
        assert any("doc_text" in c for c in bc.canh_bao)
        # và phải đứng ĐẦU: các cảnh báo sau đều là hệ quả ăn theo
        assert "docs_bm25" in bc.canh_bao[0]
    finally:
        ev.xoa_cache()
        ev._LOI_LUOC_DO.clear()


# ------------------------------------------------------------------------- ASR

def test_asr_phan_biet_truc_tiep_va_gan_do(cap_id):
    """Đoạn nói CHỨA frame khác hẳn đoạn chỉ dính vì cửa sổ ±3s.

    Không phân biệt thì người chấm tưởng câu nói đó phát ra ngay tại frame đang xem.
    """
    _, _, video = cap_id
    import pandas as pd

    from app.evidence import DERIVED

    p = DERIVED / "asr.parquet"
    if not p.exists():
        pytest.skip("chưa có asr.parquet")
    seg = pd.read_parquet(p, columns=["start_frame", "end_frame"],
                          filters=[("video_id", "==", video)])
    if seg.empty:
        pytest.skip(f"{video} không có đoạn ASR nào")

    r = seg.iloc[len(seg) // 2]
    giua = int((r.start_frame + r.end_frame) // 2)
    fm_kf = _kf_gan_frame(video, giua)
    if fm_kf is None:
        pytest.skip("không tìm được keyframe gần đoạn ASR này")

    bc = bang_chung(fm_kf)
    assert bc.asr, "frame nằm giữa một đoạn nói mà không lấy được đoạn nào"
    assert any(a["truc_tiep"] for a in bc.asr)


def _kf_gan_frame(video_id: str, frame_idx: int) -> str | None:
    """keyframe BTC gần một frame nhất — tiện ích riêng của test."""
    import pandas as pd

    from app.evidence import DERIVED

    fm = pd.read_parquet(DERIVED / "frame_map.parquet", columns=["kf_id", "frame_idx"],
                         filters=[("video_id", "==", video_id)])
    if fm.empty:
        return None
    return str(fm.iloc[(fm.frame_idx - frame_idx).abs().argmin()].kf_id)


# ------------------------------------------------------------------ dải shot

def test_keyframe_cung_shot_tang_dan_va_chua_chinh_no(cap_id):
    btc, _, video = cap_id
    bc = bang_chung(btc)
    if not bc.shot_id:
        pytest.skip("keyframe này không tra được shot")
    dai = keyframe_cung_shot(video, bc.shot_id)
    assert dai, "shot nào cũng phải có ít nhất chính keyframe này"
    assert [d["frame_idx"] for d in dai] == sorted(d["frame_idx"] for d in dai)
    assert bc.kf_id_tu_trich in [d["kf_id"] for d in dai]
