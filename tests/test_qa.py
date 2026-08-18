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

from unittest.mock import patch

from backend.slot import ShotHit
from backend.tasks.qa import (
    MAX_SHOTS_TRIED,
    TOP_K_SHOTS,
    TOP_K_SHOTS_FOR_SLOTS,
    Evidence,
    _dua_len_dau,
    ask_llm,
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
    """Bằng chứng cho lý do TOP_K_SHOTS_FOR_SLOTS tách khỏi TOP_K_SHOTS: chỉ 5 shot
    ứng viên thì one-fifth cả bài nộp (>=20/100 dòng) dồn vào MỘT shot — rủi ro
    cao nếu shot đó sai — trong khi 100 shot ứng viên phủ rộng hơn hẳn.

    ⚠️ SỬA 18/08: không còn pin con số "22" — đó là số của bảng SLOT_BUDGET đợt
    trước D4.1 (17/08) và cách chia round-robin cũ. San bằng shot thấp nhất
    trước (data/config/slot_budget.py::budget_per_shot) làm 5 shot chia ĐỀU
    đúng 20 mỗi shot với bảng hiện tại (100/5 chia hết) — max luôn >= 20 bởi
    nguyên lý chuồng bồ câu (pigeonhole) bất kể bảng SLOT_BUDGET đổi ra sao,
    nên dùng mốc đó thay vì hardcode số của một bảng cụ thể."""
    from data.config.slot_budget import budget_per_shot

    it, nhieu = budget_per_shot(5), budget_per_shot(TOP_K_SHOTS_FOR_SLOTS)
    assert max(it) >= 20, "bằng chứng: 5 shot thì 1 shot ôm ít nhất 1/5 cả bài nộp"
    assert sum(1 for x in nhieu if x) > 6 * sum(1 for x in it if x)


# --------------------------------------------------- effort của bước suy luận

def test_ask_llm_dung_effort_high():
    """SỬA 18/08 — adapter.py (DEFAULT_EFFORT) ghi rõ ý đồ thiết kế: "Task nào
    cần nghĩ kỹ (Q&A suy luận) thì tự truyền effort='high'". ask_llm() CHÍNH LÀ
    bước đó nhưng trước bản sửa không hề truyền — luôn chạy effort THẤP NHẤT
    (mặc định của llm(), dành cho dịch/mở rộng câu ngắn) trên backend "api"
    (Claude — backend dùng lúc thi thật). Không crash (effort="low" vẫn hợp
    lệ) nên không lộ qua test hạ tầng nào khác — lỗi CHẤT LƯỢNG câu trả lời im
    lặng, chỉ mock trực tiếp mới bắt được mà không cần ES/Milvus/LLM thật."""
    ev = Evidence(
        shot_id="s0", video_id="V1", ocr_texts=[], asr_texts=[],
        metadata_text="", object_count=None, frames=[], best_frame_idx=10,
    )
    fake = '{"answer": "5", "answer_vi": "5", "answer_en": "5", ' \
           '"evidence_frame_idx": 10, "confidence": 0.9}'
    with patch("backend.tasks.qa.llm", return_value=fake) as m:
        ask_llm("câu hỏi bất kỳ", ev)
    assert m.call_args.kwargs.get("effort") == "high"
