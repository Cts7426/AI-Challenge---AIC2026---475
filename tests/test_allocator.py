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
