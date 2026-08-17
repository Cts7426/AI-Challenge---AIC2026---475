# tests/test_qa.py — C3.1: các quyết định THUẦN LOGIC của pipeline Q&A
#
# Chỉ test phần chạy được KHÔNG cần ES/Milvus/LLM. Phần cần hạ tầng (collect_evidence,
# ask_llm, qa_pipeline đầu-cuối) đo bằng dev_set/tools/run_evaluation.py.
#
# Ba thứ ở đây đều là lỗi IM LẶNG đã đo được ngày 16/08 — không cái nào crash, cả ba
# chỉ làm điểm sai:
#   1. shot sinh ra câu trả lời không được đẩy lên hạng 1  → answer đúng + frame sai
#   2. số shot cấp slot bị buộc chung với số shot suy luận → bỏ trắng 95 slot
#   3. `_object_count` trả 0 khi nhãn không khớp           → nộp answer "0"

from __future__ import annotations

from backend.slot import ShotHit
from backend.tasks.qa import (
    MAX_SHOTS_TRIED,
    TOP_K_SHOTS,
    TOP_K_SHOTS_FOR_SLOTS,
    _dua_len_dau,
)


def _hits(n: int) -> list[ShotHit]:
    """n shot giả, điểm giảm dần như tầng search thật trả về."""
    return [ShotHit(f"s{i}", 1.0 - i * 0.01) for i in range(n)]


# ------------------------------- shot thắng phải lên hạng 1 (hai cửa tử độc lập)

def test_shot_thang_duoc_day_len_hang_1():
    """Q&A có hai cửa tử ĐỘC LẬP. Ghép answer của shot #3 với frame của shot #1 là
    tự tay phá cửa frame trong khi cửa answer đã đúng."""
    out = _dua_len_dau(_hits(5), 2)
    assert [h.shot_id for h in out][0] == "s2"


def test_day_len_dau_giu_nguyen_thu_tu_con_lai():
    """Chỉ shot thắng đổi chỗ — phần còn lại giữ đúng thứ hạng search đã xếp."""
    out = _dua_len_dau(_hits(5), 2)
    assert [h.shot_id for h in out] == ["s2", "s0", "s1", "s3", "s4"]


def test_day_len_dau_thang_duoc_ca_sorted_cua_allocator():
    """`allocate()` tự `sorted(hits, key=score, reverse=True)` — đổi chỗ trong list
    KHÔNG đủ, điểm cũng phải cao nhất, nếu không allocator xếp lại như cũ."""
    out = _dua_len_dau(_hits(5), 3)
    theo_diem = sorted(out, key=lambda h: h.score, reverse=True)
    assert theo_diem[0].shot_id == "s3"


def test_day_len_dau_khong_lam_bien_dang_thang_diem():
    """Không bịa điểm to: score_simulator và log phân tích đều đọc `score` thật.
    Chỉ cần nhỉnh hơn đỉnh cũ một khoảng không đáng kể so với thang RRF (~0.01–0.03)."""
    goc = _hits(5)
    out = _dua_len_dau(goc, 4)
    assert out[0].score - max(h.score for h in goc) < 1e-3


def test_day_len_dau_i0_khong_dung_gi():
    goc = _hits(5)
    assert _dua_len_dau(goc, 0) is goc


def test_day_len_dau_giu_nguyen_best_keyframe_id():
    """`best_keyframe_id` là mức ưu tiên ① của allocator — mất nó là mất frame có
    bằng chứng thật của shot thắng."""
    hits = [ShotHit("s0", 0.9), ShotHit("s1", 0.8, "L21_V001#k0007")]
    assert _dua_len_dau(hits, 1)[0].best_keyframe_id == "L21_V001#k0007"


# ------------------------- số shot suy luận TÁCH khỏi số shot cấp slot

def test_so_shot_cap_slot_tach_khoi_so_shot_suy_luan():
    """Suy luận tốn 3–6 lần gọi LLM mỗi shot nên phải ít. Cấp slot KHÔNG tốn gì
    nên phải nhiều. Buộc chung một hằng là bỏ trắng 95 slot miễn phí."""
    assert TOP_K_SHOTS_FOR_SLOTS > TOP_K_SHOTS
    assert TOP_K_SHOTS_FOR_SLOTS >= 100, "phải đủ shot để allocator phủ rộng"


def test_chi_MAX_SHOTS_TRIED_shot_duoc_suy_luan():
    """Nâng số shot cấp slot KHÔNG được kéo theo chi phí LLM."""
    assert MAX_SHOTS_TRIED <= TOP_K_SHOTS


def test_100_shot_phu_rong_hon_han_5_shot():
    """Con số cụ thể của lỗi: 5 shot → 22 slot nhồi vào MỘT shot median 69 frame."""
    from data.config.slot_budget import budget_per_shot

    it, nhieu = budget_per_shot(5), budget_per_shot(TOP_K_SHOTS_FOR_SLOTS)
    assert max(it) > 20, "bằng chứng: 5 shot thì 1 shot ôm hơn 20 slot"
    assert sum(1 for x in nhieu if x) > 6 * sum(1 for x in it if x)
