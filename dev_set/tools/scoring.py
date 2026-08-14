from __future__ import annotations
from backend.common.answer_match import answer_matches
from dev_set.tools.schema import GroundTruthKIS, GroundTruthQA, GroundTruthTRAKE, Answer

# answer_matches re-export ở đây để code cũ import từ dev_set.tools.scoring vẫn
# chạy — cài đặt thật nằm ở backend/common/answer_match.py, DÙNG CHUNG với
# majority voting của backend/tasks/qa.py (một nguồn sự thật cho "thế nào là
# 2 câu trả lời giống nhau", xem docstring file đó).
__all__ = ["rscore_kis", "rscore_qa", "rscore_trake", "recall_at_k", "final_score", "answer_matches"]

K_THRESHOLDS = (1, 5, 20, 50, 100)

def rscore_kis(video_id: str, frame_idx: int, gt: GroundTruthKIS) -> float:
    if video_id != gt.video_id:
        return 0.0
    return 1.0 if gt.frame_start <= frame_idx <= gt.frame_end else 0.0

def rscore_qa(video_id: str, frame_idx: int, answer: str, gt: GroundTruthQA) -> float:
    if video_id != gt.video_id:
        return 0.0
    if not (gt.frame_start <= frame_idx <= gt.frame_end):
        return 0.0
    
    # Kế hoạch gốc: answer đúng mà frame sai = 0; nhưng đây frame đã đúng
    match, tier = answer_matches(answer, gt.answer_text, gt.answer_variants)
    return 1.0 if match else 0.0

def rscore_trake(video_id: str, frames: tuple[int, ...], gt: GroundTruthTRAKE) -> float:
    if video_id != gt.video_id:
        return 0.0
    
    n = len(gt.frames)
    if len(frames) != n:
        return 0.0
        
    hits = 0
    for j, f in enumerate(frames):
        if gt.frames[j]["start"] <= f <= gt.frames[j]["end"]:
            hits += 1
            
    return hits / n

# Bảng điểm theo hạng câu đúng đầu tiên — docs/contest.md, mục "Cách chấm".
# KHÔNG phải nhị phân (có/không trong top-k): hạng càng xa 1 điểm càng thấp.
RANK_BANDS = ((1, 1.00), (5, 0.80), (20, 0.60), (50, 0.40), (100, 0.20))

def _score_for_rank(rank: int) -> float:
    """rank = vị trí 1-based trong danh sách đã nộp."""
    for upper, val in RANK_BANDS:
        if rank <= upper:
            return val
    return 0.0

def recall_at_k(rows: list[Answer], gt, task_type: str, k: int) -> float:
    """R@k = điểm theo hạng của câu đúng SỚM NHẤT trong k câu đầu (docs/contest.md).

    KHÔNG phải "có trúng trong top-k hay không": trúng ở hạng 5 chỉ được 0.80,
    không phải 1.0 — nhầm chỗ này thổi phồng Final Score so với BTC thật.
    """
    best = 0.0
    for rank, r in enumerate(rows[:k], start=1):
        if task_type in ("KIS", "QA", "TRAKE") and not r.frame_ids:
            raise ValueError(f"Answer rỗng frame_ids cho video {r.video_id} — lỗi allocator")
        hit = 0.0
        if task_type == "KIS":
            hit = rscore_kis(r.video_id, r.frame_ids[0], gt)
        elif task_type == "QA":
            hit = rscore_qa(r.video_id, r.frame_ids[0], r.answer_text or "", gt)
        elif task_type == "TRAKE":
            hit = rscore_trake(r.video_id, r.frame_ids, gt)
        if hit > 0:
            # TODO: BTC/team xác nhận — nhân hạng-band với tỉ lệ khớp TRAKE là
            # cách đọc HỢP LÝ NHẤT của docs/contest.md, nhưng doc không viết
            # thẳng ra công thức kết hợp này. Với KIS/QA hit là nhị phân nên
            # phép nhân không đổi gì (an toàn), TRAKE là chỗ cần chốt lại.
            best = max(best, _score_for_rank(rank) * hit)
    return best

def final_score(rows: list[Answer], gt, task_type: str) -> float:
    """Tính Final Score = (R@1 + R@5 + R@20 + R@50 + R@100) / 5"""
    sum_score = 0.0
    for k in K_THRESHOLDS:
        sum_score += recall_at_k(rows, gt, task_type, k)
    return sum_score / 5.0

