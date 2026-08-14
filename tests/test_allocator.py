# tests/test_allocator.py — D3.1: cấp phát 100 slot
#
# Trọng tâm, theo đúng thứ tự quan trọng:
#   1. LUÔN đủ 100 dòng — kể cả 1 shot, kể cả shot 12 frame. Bất biến số một.
#   2. XEN KẼ theo shot, không gom — R@1+R@5 = 40% điểm
#   3. frame_id là số THẬT, nằm trong shot và trong [0, n_frames)
#   4. Output cắm thẳng vào validator của D0.2 phải sạch
#
# Dữ liệu: shots.parquet + frame_map.parquet + video_info.parquet THẬT của Data
# Factory. Không mock — allocator mà chạy được trên shot bịa thì chẳng chứng minh gì.

from __future__ import annotations

import pytest

from backend.export import QuerySubmission, n_frames_of, validate_submission
from backend.slot import ShotHit, allocate
from backend.slot.allocator import _frames_of_shot
from data.config.slot_budget import ANSWERS_PER_QUERY, SHOT_EDGE_INSET, budget_per_shot
from tests.conftest import _shots_df, hits_of, shots_of


@pytest.fixture(scope="session")
def nhieu_video() -> list[str]:
    """20 video thật — mô phỏng kết quả search trải trên nhiều video."""
    return sorted(_shots_df().video_id.unique())[:20]


# ------------------------------------------------- bất biến 1: LUÔN đủ 100 dòng

@pytest.mark.parametrize("so_shot", [1, 2, 3, 7, 31, 60])
def test_luon_du_100_dong_du_it_shot(real_videos, so_shot):
    """Bất biến số một: KHÔNG BAO GIỜ trả < 100 dòng, kể cả khi search chỉ ra 1 shot."""
    vid = real_videos[0][0]
    hits = hits_of([vid])[:so_shot]
    assert len(allocate(hits, "KIS")) == ANSWERS_PER_QUERY


def test_du_100_dong_tu_shot_NGAN_NHAT():
    """Ca biên xấu nhất: đúng 1 shot, và là shot ngắn nhất toàn bộ dataset.

    12 frame mà phải đẻ ra 100 dòng khác nhau → buộc phải nới ra ngoài biên shot.
    Đây là lúc mức ④ của máy phát frame làm việc.
    """
    df = _shots_df()
    ngan = df.nsmallest(1, "n_frames").iloc[0]
    answers = allocate([ShotHit(ngan.shot_id, 1.0)], "KIS")

    assert len(answers) == ANSWERS_PER_QUERY
    frames = [a.frame_ids[0] for a in answers]
    assert len(set(frames)) == ANSWERS_PER_QUERY, "phải là 100 frame KHÁC NHAU"
    assert all(0 <= f < n_frames_of(ngan.video_id) for f in frames)


def test_khong_co_shot_thi_bao_loi():
    with pytest.raises(ValueError, match="Không có shot ứng viên"):
        allocate([], "KIS")


@pytest.mark.parametrize("total", [0, -5])
def test_total_sai_thi_gay_to_chu_khong_tra_rong(real_videos, total):
    """`BUILD_TASKS` D3.1: KHÔNG BAO GIỜ trả < 100 dòng.

    Trước 09/08 hàm trả `[]` lặng lẽ khi total <= 0 — một biến chưa gán ở tầng trên
    sẽ thành bài nộp TRẮNG mà không ai biết.
    """
    hits = hits_of([real_videos[0][0]], 3)
    with pytest.raises(ValueError, match="total"):
        allocate(hits, "KIS", total=total)


@pytest.mark.parametrize("n", [0, 1])
def test_trake_duoi_2_khoanh_khac_bi_tu_choi(real_videos, n):
    """Allocator không được đẻ ra thứ validator của chính mình từ chối.

    `_check_shape` bên export.py bắt TRAKE phải có ít nhất 2 frame.
    n=0 là ca đặc biệt: `n_trake or MAC_DINH` sẽ nuốt số 0 mất, nên phải dùng `is None`.
    """
    hits = hits_of([real_videos[0][0]], 3)
    with pytest.raises(ValueError, match="ít nhất 2 khoảnh khắc"):
        allocate(hits, "TRAKE", n_trake=n)


def test_score_nan_bi_chan_o_cua_vao(real_videos):
    """score = NaN → gãy to, KHÔNG được lặng lẽ xếp hạng bừa.

    NaN so sánh với mọi số đều False nên `sorted()` mất tính bắc cầu: thứ hạng
    shot thành tuỳ ý mà bài nộp vẫn đủ 100 dòng và validator vẫn xanh. Rủi ro
    có thật từ khi A2.2 dùng RRF — `1/(K + rank)` sinh NaN nếu rank hỏng.
    """
    hits = hits_of([real_videos[0][0]], 3)
    hong = [ShotHit(hits[1].shot_id, float("nan"))] + hits
    with pytest.raises(ValueError, match="NaN"):
        allocate(hong, "KIS")


def test_score_binh_thuong_khong_bi_bao_nham(real_videos):
    """Đối chứng: score âm hoặc 0 là hợp lệ, chỉ NaN mới bị chặn."""
    hits = [ShotHit(h.shot_id, d) for h, d in zip(hits_of([real_videos[0][0]], 3), (0.0, -1.5, 2.0))]
    assert len(allocate(hits, "KIS")) == ANSWERS_PER_QUERY


def test_shot_id_la_bao_loi_ro_rang():
    """shot_id không có trong shots.parquet → nói thẳng là hai bên lệch bản dữ liệu."""
    with pytest.raises(KeyError, match="shots.parquet"):
        allocate([ShotHit("L99_V999#s0000", 1.0)], "KIS")


def test_shot_id_la_o_HANG_CHOT_van_bao_loi(real_videos):
    """shot_id lạ phải nổ kể cả khi nó nằm ở hạng thấp, không bao giờ được rút tới.

    Máy phát frame dựng lười (khỏi tra `frame_map` thừa), nhưng phần tra BIÊN SHOT thì
    không được lười theo: bắt lúc có lúc không còn tệ hơn không bắt — lỗi "search và
    Data Factory dùng hai bản shot khác nhau" phải lộ ngay lúc gọi.
    """
    hits = hits_of([real_videos[0][0]], 40) + [ShotHit("L99_V999#s0000", -1.0)]
    with pytest.raises(KeyError, match="shots.parquet"):
        allocate(hits, "KIS")


# ------------------------------------------------- bất biến 2: XEN KẼ theo shot

def test_5_slot_dau_thuoc_5_shot_khac_nhau(real_videos):
    """R@1+R@5 = 40% điểm. Gom 5 slot đầu vào 1 shot mà shot sai là mất trắng."""
    vid = real_videos[0][0]
    answers = allocate(hits_of([vid])[:31], "KIS")

    bien = {(r.start_frame, r.end_frame) for r in shots_of(vid, 31)}
    def shot_cua(f: int):
        return next((b for b in bien if b[0] <= f <= b[1]), None)

    nam_dau = [shot_cua(a.frame_ids[0]) for a in answers[:5]]
    assert len(set(nam_dau)) == 5, f"5 slot đầu chỉ thuộc {len(set(nam_dau))} shot"


def test_slot_1_la_shot_diem_cao_nhat(real_videos):
    """Hạng 1 được 1.00 điểm, hạng 2 chỉ 0.80 → slot 1 phải là shot tin nhất."""
    vid = real_videos[0][0]
    ds = shots_of(vid, 5)
    # cố tình đảo: shot cuối điểm cao nhất
    hits = [ShotHit(r.shot_id, 0.1 * i) for i, r in enumerate(ds)]
    tot_nhat = ds[-1]

    dau = allocate(hits, "KIS")[0]
    assert tot_nhat.start_frame <= dau.frame_ids[0] <= tot_nhat.end_frame


def test_khong_gom_theo_shot(real_videos):
    """Slot 1 và 2 không bao giờ cùng một shot khi có từ 2 shot trở lên."""
    vid = real_videos[0][0]
    a = allocate(hits_of([vid])[:2], "KIS")
    ds = shots_of(vid, 2)
    assert ds[0].start_frame <= a[0].frame_ids[0] <= ds[0].end_frame
    assert ds[1].start_frame <= a[1].frame_ids[0] <= ds[1].end_frame


# --------------------------------------------- bất biến 3: frame_id là số THẬT

def test_khong_dong_nao_trung(nhieu_video):
    answers = allocate(hits_of(nhieu_video, 3), "KIS")
    khoa = [(a.video_id, a.frame_ids) for a in answers]
    assert len(set(khoa)) == len(khoa)


def test_moi_frame_nam_trong_video(nhieu_video):
    for a in allocate(hits_of(nhieu_video, 3), "KIS"):
        for f in a.frame_ids:
            assert 0 <= f < n_frames_of(a.video_id), f"{a.video_id} frame {f} tràn"


def test_frame_dau_moi_shot_la_keyframe_that(real_videos):
    """Frame đầu của mỗi shot phải là frame_map[best_keyframe_id], không phải số tính ra.

    Đây là điểm phân biệt "frame mình có bằng chứng" với "điểm giữa shot đoán ra".
    """
    from tests.conftest import _frame_map

    vid = real_videos[0][0]
    fm = _frame_map()
    fm = fm[fm.video_id == vid]

    hits, mong_doi = [], []
    for r in shots_of(vid, 5):
        trong = fm[(fm.frame_idx >= r.start_frame) & (fm.frame_idx <= r.end_frame)]
        if trong.empty:
            continue
        hits.append(ShotHit(r.shot_id, 1.0 - len(hits) * 0.01, trong.kf_id.iloc[0]))
        mong_doi.append(int(trong.frame_idx.iloc[0]))

    assert len(hits) >= 3, "cần ít nhất 3 shot có keyframe để test"
    answers = allocate(hits, "KIS")
    assert [a.frame_ids[0] for a in answers[: len(hits)]] == mong_doi


def test_keyframe_la_khong_lam_sap(real_videos):
    """best_keyframe_id không có trong frame_map → mất mức ①, KHÔNG được crash."""
    vid = real_videos[0][0]
    hits = [ShotHit(r.shot_id, 1.0, "L99_V999#k9999") for r in shots_of(vid, 5)]
    assert len(allocate(hits, "KIS")) == ANSWERS_PER_QUERY


def test_thut_10_phan_tram_hai_dau(real_videos):
    """Shot dài, ít slot → frame rải ra không được rơi vào 10% hai mép (frame chuyển cảnh).

    Cho hẳn một keyframe THẬT sát mép shot để chứng minh hai điều một lúc:
    mức ① được miễn luật thụt (nó là bằng chứng), còn mọi frame sau thì không.
    """
    from tests.conftest import _frame_map

    df = _shots_df()
    vid = real_videos[0][0]
    dai = df[(df.video_id == vid) & (df.n_frames > 200)]
    if dai.empty:
        pytest.skip(f"{vid} không có shot nào đủ dài để kiểm luật thụt biên")
    r = dai.iloc[0]

    span = r.end_frame - r.start_frame + 1
    inset = int(span * SHOT_EDGE_INSET)

    # keyframe thật nằm trong vùng 10% đầu shot — nếu không có thì bỏ phần kiểm mức ①
    fm = _frame_map()
    mep = fm[(fm.video_id == vid)
             & (fm.frame_idx >= r.start_frame)
             & (fm.frame_idx < r.start_frame + inset)]
    kf = mep.kf_id.iloc[0] if not mep.empty else None
    kf_frame = int(mep.frame_idx.iloc[0]) if not mep.empty else None

    # shot này đứng đầu; các shot khác chỉ để hút bớt slot, KHÔNG lặp lại shot này
    khac = [h for h in hits_of([vid], 40) if h.shot_id != r.shot_id]
    answers = allocate([ShotHit(r.shot_id, 1.0, kf)] + khac, "KIS")

    trong_shot = [
        a.frame_ids[0] for a in answers
        if r.start_frame <= a.frame_ids[0] <= r.end_frame
    ]
    if kf_frame is not None:
        assert trong_shot[0] == kf_frame, "mức ① phải là keyframe thật, dù nó sát mép"
        trong_shot = trong_shot[1:]

    assert trong_shot, "shot đầu bảng phải được cấp nhiều hơn 1 slot"
    assert all(r.start_frame + inset <= f <= r.end_frame - inset for f in trong_shot), (
        f"có frame rơi vào 10% mép shot [{r.start_frame}, {r.end_frame}]"
    )


# ------------------------------------------------------------- ba dạng bài

def test_kis_moi_dong_dung_1_frame(nhieu_video):
    assert all(len(a.frame_ids) == 1 for a in allocate(hits_of(nhieu_video, 3), "KIS"))


def test_qa_dong_dau_answer_vao_moi_dong(nhieu_video):
    answers = allocate(hits_of(nhieu_video, 3), "QA", answer_text="5")
    assert all(a.answer_text == "5" for a in answers)
    assert all(len(a.frame_ids) == 1 for a in answers)


def test_qa_thieu_answer_bi_tu_choi(nhieu_video):
    """Tầng slot không bịa câu trả lời — thiếu thì gãy to, không nộp dòng rỗng."""
    with pytest.raises(ValueError, match="answer_text"):
        allocate(hits_of(nhieu_video, 3), "QA")


@pytest.mark.parametrize("n", [3, 4, 5])
def test_trake_dung_N_va_tang_dan_ngat(nhieu_video, n):
    answers = allocate(hits_of(nhieu_video, 3), "TRAKE", n_trake=n)
    assert len(answers) == ANSWERS_PER_QUERY
    for a in answers:
        assert len(a.frame_ids) == n
        assert list(a.frame_ids) == sorted(set(a.frame_ids)), f"{a.frame_ids} không tăng dần ngặt"


def test_trake_video_it_shot_hon_N(real_videos):
    """Video chỉ có 2 shot mà đề đòi 4 khoảnh khắc → lấy sâu hơn trong shot đang có."""
    vids = [v for v, _ in real_videos[:2]]
    answers = allocate(hits_of(vids, 2), "TRAKE", n_trake=4)
    assert len(answers) == ANSWERS_PER_QUERY
    assert all(list(a.frame_ids) == sorted(set(a.frame_ids)) for a in answers)


def test_trake_it_shot_thi_khoanh_khac_KHONG_dinh_nhau(real_videos):
    """Video ít shot hơn N → N khoảnh khắc vẫn phải CÁCH XA nhau.

    Đây là test kiểm CHẤT LƯỢNG, không phải kiểm hợp lệ — và đó là lý do bộ test cũ
    bỏ lọt. Bản trước dựng N máy phát trên cùng một biên shot; chúng xả ra dãy giống
    hệt nhau nên `_mot_dong_trake` phải đẩy +1 để tách, ra `(34, 35, 36, 37)`.
    Bốn khoảnh khắc cách nhau 0,16 giây ở 25fps thì giỏi lắm trúng 1/4 cửa sổ đáp án,
    mà `test_trake_dung_N_va_tang_dan_ngat` vẫn XANH vì dãy đó tăng dần ngặt thật.
    """
    vid = real_videos[0][0]
    mot_shot = shots_of(vid, 1)[0]
    span = mot_shot.end_frame - mot_shot.start_frame + 1
    answers = allocate([ShotHit(mot_shot.shot_id, 1.0)], "TRAKE", n_trake=4, total=10)

    # Chia shot làm 4 đoạn thì hai khoảnh khắc kề nhau phải cách ~span/4.
    # Lấy ngưỡng span/8 cho rộng tay: đủ chặt để bắt ca dính nhau (cách 1 frame).
    toi_thieu = max(2, span // 8)
    for a in answers:
        cach = [y - x for x, y in zip(a.frame_ids, a.frame_ids[1:])]
        assert min(cach) >= toi_thieu, (
            f"{a.frame_ids} có hai khoảnh khắc cách nhau {min(cach)} frame, "
            f"cần ít nhất {toi_thieu} (shot dài {span})"
        )


def test_moi_shot_khong_co_keyframe_van_rai_du_diem(real_videos):
    """Shot KHÔNG có best_keyframe_id vẫn phải được rải đủ `quota` điểm cách đều.

    Bản trước luôn trừ 1 cho mức ① kể cả khi mức ① không phát gì, nên slot cuối rơi
    xuống mức ③ và nhả ra frame dính sát điểm rải đầu (đo được: 415 rồi 416).
    """
    vid = real_videos[0][0]
    r = next(s for s in shots_of(vid) if s.n_frames > 100)
    span = r.end_frame - r.start_frame + 1
    quota = 8

    gen = _frames_of_shot(int(r.start_frame), int(r.end_frame), quota, None, 10**9)
    lay = sorted(next(gen) for _ in range(quota))
    cach = [y - x for x, y in zip(lay, lay[1:])]
    # 8 điểm rải đều trên vùng đã thụt 10% hai đầu → mỗi khoảng ≈ span*0.8/7
    assert min(cach) >= span // 16, f"{lay} có hai frame dính nhau (cách {min(cach)})"


def test_keyframe_id_chi_gan_cho_dong_lay_dung_keyframe(real_videos, monkeypatch):
    """`keyframe_id` phải theo dòng lấy ĐÚNG frame của keyframe, các dòng khác để None.

    Gán bừa cho mọi dòng của shot là nói dối: frame rải sâu không đến từ keyframe nào.
    D2.1 và D3.5 dựa vào field này để truy ngược dòng nộp về bằng chứng.
    """
    import backend.slot.allocator as al

    vid = real_videos[0][0]
    r = shots_of(vid, 1)[0]
    moc = int(r.start_frame) + 5
    monkeypatch.setattr(al, "_frame_of_keyframe", lambda kf: moc)

    answers = allocate([ShotHit(r.shot_id, 1.0, "kf_gia")], "KIS", total=4)
    assert answers[0].frame_ids == (moc,) and answers[0].keyframe_id == "kf_gia"
    assert all(a.keyframe_id is None for a in answers[1:])


def test_khong_tra_frame_map_cho_shot_khong_dung_toi(real_videos, monkeypatch):
    """Shot hạng thấp (hạn mức 0) KHÔNG được tra frame_map — dựng máy phát phải LƯỜI.

    Search trả 200 shot mà bảng chỉ phủ 31: tra cả 200 là 169 lượt đọc vô ích, và mở
    rộng bề mặt lỗi sang những shot không hề được dùng.
    """
    import backend.slot.allocator as al

    dem = {"n": 0}

    def dem_tra(kf):
        dem["n"] += 1
        return None

    monkeypatch.setattr(al, "_frame_of_keyframe", dem_tra)
    hits = [ShotHit(h.shot_id, h.score, f"kf{i}") for i, h in enumerate(hits_of([real_videos[0][0]]))]
    if len(hits) < 40:
        pytest.skip("video này không đủ shot để kiểm")
    allocate(hits, "KIS")
    assert dem["n"] <= 31, f"tra frame_map {dem['n']} lần cho {len(hits)} shot — phải lười"


def test_task_khong_phai_QA_ma_co_answer_text_thi_bao_loi(nhieu_video):
    """Nuốt lặng tham số truyền nhầm là đúng loại lỗi im lặng file này đang phòng."""
    for task in ("KIS", "TRAKE"):
        with pytest.raises(ValueError, match="answer_text"):
            allocate(hits_of(nhieu_video, 3), task, answer_text="5")


def test_bang_ngan_sach_total_nho_thi_bot_chieu_sau_khong_cat_shot():
    """total nhỏ → phải giữ CHIỀU RỘNG. [5,0,0,...] là dồn cả 5 dòng vào 1 shot."""
    assert budget_per_shot(31, total=5) == [1] * 5 + [0] * 26
    for n in range(1, 40):
        for t in (1, 5, 20, 100, 150):
            assert sum(budget_per_shot(n, total=t)) == t, f"n={n} total={t}"


def test_trake_phu_nhieu_video_o_dau_danh_sach(nhieu_video):
    """Sai video là 0 tuyệt đối → 5 dòng đầu nên là 5 video khác nhau."""
    answers = allocate(hits_of(nhieu_video, 3), "TRAKE", n_trake=4)
    assert len({a.video_id for a in answers[:5]}) == 5


# --------------------------------------- chốt cuối: nối thẳng vào validator D0.2

@pytest.mark.parametrize("task,kw", [
    ("KIS", {}),
    ("QA", {"answer_text": "5"}),
    ("TRAKE", {"n_trake": 4}),
])
def test_output_qua_duoc_validator(nhieu_video, task, kw):
    """Thứ allocator đẻ ra phải nộp được ngay, không cần ai sửa tay ở giữa."""
    answers = allocate(hits_of(nhieu_video, 3), task, **kw)
    sub = QuerySubmission(f"q_{task}", task, tuple(answers))
    expected_n = kw.get("n_trake")
    assert validate_submission(sub, expected_n=expected_n) == []


def test_output_qua_validator_ca_khi_chi_co_1_shot(real_videos):
    """Ca biên nghèo nhất cũng phải ra bài nộp hợp lệ."""
    hits = hits_of([real_videos[0][0]])[:1]
    sub = QuerySubmission("q1", "KIS", tuple(allocate(hits, "KIS")))
    assert validate_submission(sub) == []


# ------------------------------------------------------------ bảng ngân sách

def test_bang_ngan_sach_luon_cong_du_100():
    for n in range(1, 60):
        assert sum(budget_per_shot(n)) == ANSWERS_PER_QUERY, f"{n} shot mà không đủ 100"


def test_bang_ngan_sach_uu_tien_shot_hang_cao():
    han = budget_per_shot(31)
    assert han[0] >= han[10] >= han[30]


def test_bang_ngan_sach_it_shot_thi_rai_deu_khong_don_het():
    """3 shot → 100 slot. Dồn hết vào shot 1 là quay lại đúng cái sai xen kẽ đang tránh."""
    han = budget_per_shot(3)
    assert sum(han) == ANSWERS_PER_QUERY
    assert max(han) - min(han) <= 1, f"chia không đều: {han}"


def test_khong_co_shot_thi_bang_ngan_sach_bao_loi():
    with pytest.raises(ValueError):
        budget_per_shot(0)


# ============================== nới hạn mức khi có shot cạn frame giữa chừng
# Đường này chạm tới khi một video ứng viên quá ngắn: shot của nó cấp hết frame rồi
# chết, phần thiếu phải do các shot còn lại gánh. Câu hỏi là gánh thế nào.

def _gia_lap_5_shot(monkeypatch, n_frames_video_ngan: int = 5):
    """1 shot ở video RẤT NGẮN (chết sớm) + 4 shot ở video dài, mỗi shot một video.

    Mỗi shot một video riêng để đếm được dòng nào đến từ shot nào — `Answer` chỉ mang
    `video_id`, không mang `shot_id`.
    """
    import backend.slot.allocator as al

    bounds = {
        "s0": ("VNGAN", 0, n_frames_video_ngan - 1),
        "s1": ("VB", 0, 4000),
        "s2": ("VC", 0, 4000),
        "s3": ("VD", 0, 4000),
        "s4": ("VE", 0, 4000),
    }
    do_dai = {"VNGAN": n_frames_video_ngan, "VB": 5000, "VC": 5000, "VD": 5000, "VE": 5000}
    monkeypatch.setattr(al, "_shots", lambda: bounds)
    monkeypatch.setattr(al, "n_frames_of", lambda v: do_dai[v])
    return [ShotHit(s, 1.0 - i * 0.01) for i, s in enumerate(bounds)]


def test_shot_can_frame_giua_chung_van_du_100_dong(monkeypatch):
    hits = _gia_lap_5_shot(monkeypatch)
    answers = allocate(hits, "KIS")
    assert len(answers) == ANSWERS_PER_QUERY
    assert len({(a.video_id, a.frame_ids) for a in answers}) == ANSWERS_PER_QUERY


def test_phan_thieu_duoc_NOI_DEU_khong_don_vao_shot_dau(monkeypatch):
    """Phần shot chết để lại phải rải cho MỌI shot còn sống, không dồn vào top.

    Bản cũ so hạn mức với một bộ đếm vòng rồi nới cả hai mỗi vòng → hiệu số đứng im,
    chỉ shot có hạn mức lớn nhất còn được rút. Mô phỏng 200 vòng với bảng thật cho ra
    shot 1–3 rút 200 lượt còn shot 4–31 đứng nguyên. Đặc tả D3.1 nói ngược lại: "bù
    bằng cách rải thêm frame trong các shot đã có".
    """
    hits = _gia_lap_5_shot(monkeypatch, n_frames_video_ngan=5)
    answers = allocate(hits, "KIS")

    dem = {v: 0 for v in ("VNGAN", "VB", "VC", "VD", "VE")}
    for a in answers:
        dem[a.video_id] += 1

    assert dem["VNGAN"] == 5, "video 5 frame chỉ cấp được 5 dòng rồi phải chết hẳn"

    goc = budget_per_shot(5, total=ANSWERS_PER_QUERY)
    thieu = goc[0] - 5
    assert thieu > 0, "kịch bản phải thật sự thiếu slot thì test mới có nghĩa"

    them = [dem[v] - q for v, q in zip(("VB", "VC", "VD", "VE"), goc[1:])]
    assert all(t > 0 for t in them), f"shot hạng thấp cũng phải được gánh thêm, đang là {them}"
    assert max(them) - min(them) <= 1, f"chênh lệch phải ≤ 1 dòng, đang là {them}"


def test_moi_shot_deu_cạn_thi_bao_loi_ro_rang(monkeypatch):
    """Cạn thật thì phải gãy to, không được lặng lẽ trả thiếu 100 dòng."""
    import backend.slot.allocator as al

    monkeypatch.setattr(al, "_shots", lambda: {"s0": ("VTI", 0, 9)})
    monkeypatch.setattr(al, "n_frames_of", lambda v: 10)
    with pytest.raises(RuntimeError, match="Cạn frame"):
        allocate([ShotHit("s0", 1.0)], "KIS")


def test_trake_shot_can_giua_chung_van_du_100_dong(monkeypatch):
    """Nhánh TRAKE có cùng vòng lặp nên phải khoá cùng một bất biến."""
    hits = _gia_lap_5_shot(monkeypatch, n_frames_video_ngan=40)
    answers = allocate(hits, "TRAKE", n_trake=4)
    assert len(answers) == ANSWERS_PER_QUERY
    assert all(len(a.frame_ids) == 4 for a in answers)
    assert len({(a.video_id, a.frame_ids) for a in answers}) == ANSWERS_PER_QUERY
