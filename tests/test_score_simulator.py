# tests/test_score_simulator.py — D3.5
#
# Mô phỏng sai thì tune sai, mà tune sai KHÔNG có dấu hiệu gì: bảng vẫn ra số, số vẫn
# xếp hạng được, chỉ là chọn nhầm bảng rồi mang đi thi. Nên test ở đây nhắm vào hai
# thứ: (1) điểm chấm ra đúng luật BTC, (2) đổi bảng thật sự đổi kết quả.

from __future__ import annotations

import json

import pandas as pd
import pytest

from app.score_simulator import (
    CANDIDATE_TABLES,
    Candidate,
    QueryCandidates,
    compare_tables,
    expected_final,
    format_slots,
    load_candidates,
    r_scores_of,
    simulate_query,
    winner_ranks,
)
from backend.slot.allocator import SHOTS_PATH
from data.config.submit_format import ANSWERS_PER_QUERY, Answer
from dev_set.tools.schema import GroundTruthKIS, GroundTruthQA


@pytest.fixture(scope="module")
def real_shots() -> pd.DataFrame:
    """Vài shot THẬT — mỗi video một shot, giống kết quả search đã gom theo shot."""
    df = pd.read_parquet(SHOTS_PATH, columns=["shot_id", "video_id", "start_frame", "end_frame"])
    return df.groupby("video_id", sort=True).head(1).head(31)


@pytest.fixture(scope="module")
def kis_query(real_shots) -> tuple[QueryCandidates, GroundTruthKIS]:
    """Truy vấn KIS với shot đúng ở hạng 3, đáp án là NỬA SAU của shot đó.

    Đặt cửa sổ ở nửa sau chứ không ở giữa: điểm giữa là chỗ `_spread_evenly` hay rơi
    vào nhất, đặt đáp án ngay đó là tự cho mình điểm.
    """
    dung = real_shots.iloc[2]
    cands = [Candidate(r.shot_id, 1.0 - i * 0.01)
             for i, r in enumerate(real_shots.itertuples(index=False))]
    giua = (int(dung.start_frame) + int(dung.end_frame)) // 2
    gt = GroundTruthKIS(query_id="K01", video_id=dung.video_id,
                        frame_start=giua, frame_end=int(dung.end_frame))
    return QueryCandidates("K01", "KIS", cands), gt


# ----------------------------------------------------------- chấm đúng luật BTC

def test_sai_video_ra_0(kis_query):
    """BTC mục 2.1.1: sai video là 0 điểm ngay, không cần xét frame."""
    qc, gt = kis_query
    trung_frame = Answer(video_id="KHONG_TON_TAI", frame_ids=(gt.frame_start,))
    assert r_scores_of([trung_frame], gt, "KIS") == [0.0]


def test_frame_ngoai_cua_so_ra_0(kis_query):
    """Đúng video mà lệch cửa sổ vẫn 0 — đây là ca `trúng shot, trượt đáp án`."""
    qc, gt = kis_query
    ngoai = Answer(video_id=gt.video_id, frame_ids=(gt.frame_end + 1,))
    trong = Answer(video_id=gt.video_id, frame_ids=(gt.frame_start,))
    assert r_scores_of([ngoai, trong], gt, "KIS") == [0.0, 1.0]


def test_qa_answer_sai_thi_moi_bang_deu_0():
    """Hai cửa tử độc lập (BTC mục 2.1.2): đổi cách chia slot KHÔNG cứu được answer sai.

    Đây là kết luận quan trọng nhất mà simulator phải nói đúng — nếu nó cho điểm khi
    answer sai thì người ta sẽ ngồi tune slot cho một câu mà lỗi nằm ở tầng Q&A.
    """
    gt = GroundTruthQA(query_id="Q01", video_id="L21_V001", frame_start=0, frame_end=999,
                       answer_text="màu xanh", answer_variants=["xanh", "xanh lá", "green"])
    trung = Answer(video_id="L21_V001", frame_ids=(10,), answer_text="màu xanh")
    sai = Answer(video_id="L21_V001", frame_ids=(10,), answer_text="màu đỏ")
    assert r_scores_of([trung], gt, "QA") == [1.0]
    assert r_scores_of([sai], gt, "QA") == [0.0]


# --------------------------------------------------------------- slot thắng cuộc

def test_winner_rank_chi_dung_dong_an_diem():
    """Đặc tả D3.5: "chỉ ra slot thắng cho từng ngưỡng"."""
    rs = [0.0, 0.0, 1.0] + [0.0] * 97      # dòng đúng đầu tiên ở hạng 3
    w = winner_ranks(rs)
    assert w[1] is None, "trong 1 dòng đầu không có dòng nào ăn điểm"
    assert w[5] == 3 and w[20] == 3 and w[100] == 3


def test_winner_rank_lay_dong_dau_tien_khi_hoa():
    """Hai dòng cùng điểm cao nhất → dòng HẠNG CAO HƠN mới là dòng ăn điểm."""
    rs = [0.0, 1.0, 1.0] + [0.0] * 97
    assert winner_ranks(rs)[20] == 2


def test_format_slots_bao_nguong_NHO_NHAT(kis_query):
    """Dòng thắng nhiều ngưỡng thì phải báo ngưỡng nhỏ nhất — báo R@100 là vô nghĩa."""
    qc, gt = kis_query
    res = simulate_query(qc, gt, CANDIDATE_TABLES["hiện tại 3×8"], "t")
    if res.final > 0:
        assert "thắng R@100" not in format_slots(res, top=100) or res.winner_rank[50] is None


# ------------------------------------------------------- đổi bảng phải đổi kết quả

def test_luon_du_100_dong_moi_bang(kis_query):
    """Bất biến số một của D3.1 phải sống sót qua mọi bảng đem thử."""
    qc, gt = kis_query
    for ten, bang in CANDIDATE_TABLES.items():
        res = simulate_query(qc, gt, bang, ten)
        assert len(res.answers) == ANSWERS_PER_QUERY, f"bảng «{ten}» ra {len(res.answers)} dòng"
        assert len(res.r_scores) == ANSWERS_PER_QUERY


def test_doi_bang_thi_bo_dong_thuc_su_khac(kis_query):
    """Nếu hai bảng cho ra 100 dòng y hệt thì cả task D4.1 là công cốc — phải nổ ở đây."""
    qc, gt = kis_query
    sau = simulate_query(qc, gt, CANDIDATE_TABLES["sâu    2×20"], "sâu")
    rong = simulate_query(qc, gt, CANDIDATE_TABLES["rất rộng 1×"], "rộng")
    khac = [(a.video_id, a.frame_ids) for a in sau.answers] != \
           [(a.video_id, a.frame_ids) for a in rong.answers]
    assert khac, "đào sâu và rải rộng cho ra cùng một bài nộp — allocator không đọc bảng"


def test_bang_sau_dat_nhieu_slot_hon_vao_shot_hang_dau(kis_query):
    """Kiểm rằng "sâu" đúng là sâu: đếm số dòng thuộc video của shot hạng 1."""
    qc, gt = kis_query
    dau = qc.candidates[0].shot_id
    from backend.slot.allocator import shot_bounds
    vid = shot_bounds(dau)[0]

    def dem(bang):
        return sum(1 for a in simulate_query(qc, gt, bang).answers if a.video_id == vid)

    assert dem(CANDIDATE_TABLES["sâu    2×20"]) > dem(CANDIDATE_TABLES["rất rộng 1×"])


def test_compare_tables_bo_qua_truy_van_thieu_dap_an(kis_query):
    """Thiếu ground truth thì BỎ QUA, không tính 0 — tính 0 là dìm điểm theo số nhãn thiếu."""
    qc, gt = kis_query
    lac = QueryCandidates("KHONG_CO_GT", "KIS", qc.candidates)
    cmp = compare_tables([qc, lac], {gt.query_id: gt}, {"t": CANDIDATE_TABLES["hiện tại 3×8"]})
    assert cmp["t"]["n"] == 1


# --------------------------------------------------------------- chế độ sweep

def test_cua_so_rong_hon_thi_diem_khong_the_giam(kis_query):
    """Cửa sổ đáp án rộng ra thì dễ trúng hơn — điểm kỳ vọng phải tăng đơn điệu.

    Đây là phép kiểm tính đúng đắn của `expected_final`: một lỗi lệch chỉ số hay lỗi
    quét thiếu vị trí gần như chắc chắn phá vỡ tính đơn điệu này.
    """
    qc, gt = kis_query
    res = simulate_query(qc, gt, CANDIDATE_TABLES["hiện tại 3×8"])
    from backend.slot.allocator import shot_bounds
    vid, a, b = shot_bounds(qc.candidates[2].shot_id)

    diem = [expected_final(res.answers, vid, (a, b), w) for w in (1, 5, 20, 100)]
    assert diem == sorted(diem), f"cửa sổ rộng hơn mà điểm giảm: {diem}"


def test_cua_so_phu_ca_shot_thi_gan_diem_toi_da(kis_query):
    """Cửa sổ rộng bằng cả shot → mọi frame trong shot đều đúng → điểm phải cao."""
    qc, gt = kis_query
    res = simulate_query(qc, gt, CANDIDATE_TABLES["sâu    2×20"])
    from backend.slot.allocator import shot_bounds
    vid, a, b = shot_bounds(qc.candidates[0].shot_id)
    assert expected_final(res.answers, vid, (a, b), b - a + 1) > 0.5


def test_video_khong_co_dong_nao_ra_0(kis_query):
    """Shot đúng không được cấp slot nào → 0, không được ném lỗi."""
    qc, gt = kis_query
    res = simulate_query(qc, gt, CANDIDATE_TABLES["hiện tại 3×8"])
    assert expected_final(res.answers, "KHONG_TON_TAI", (0, 100), 10) == 0.0


# ------------------------------------------------------------------- đọc file

def test_dong_hong_bi_bo_qua_chu_khong_keo_sap_ca_file(tmp_path, capsys):
    """Một dòng hỏng không đáng làm mất cả lần chạy đo — nhưng không được im lặng."""
    p = tmp_path / "candidates.jsonl"
    tot = json.dumps({"query_id": "K01", "task_type": "KIS",
                      "candidates": [{"shot_id": "s1", "score": 0.5}]})
    p.write_text(tot + "\n{khong-phai-json}\n" + tot + "\n", encoding="utf-8")

    qcs = load_candidates(p)
    assert len(qcs) == 2
    assert "bỏ qua dòng hỏng" in capsys.readouterr().out
