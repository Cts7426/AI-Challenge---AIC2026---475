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

# ⚠️ SỬA 14/08 (code review phát hiện): bản trước nhân hit với "bảng rút gọn"
# tra theo hạng (_score_for_rank) — SAI. docs/contest.md ghi rất rõ:
#     R@k   = max{ R-Score(r₁ … r_k) }          k ∈ {1, 5, 20, 50, 100}
#     Final = trung bình 5 giá trị R@k
# "Bảng rút gọn" (hạng 1→1.00, 2-5→0.80, 6-20→0.60...) chỉ là HỆ QUẢ khi
# R-Score nhị phân — KHÔNG được dùng làm công thức tính (docs/contest.md nói
# thẳng: "Suy ra từ công thức trên, không phải một luật riêng").
#
# Đo thật với ví dụ CÓ ĐÁP SỐ của BTC (câu 1=0.5, câu 3=0.8, câu 15=0.6 →
# Final=0.74, docs/contest.md dòng 60-62): bản cũ ra 0.612. Với KIS đúng ở
# hạng 3 (đáng lẽ Final=0.80): bản cũ ra 0.640. Bug không chỉ ảnh hưởng TRAKE
# (điểm lẻ) như comment cũ tưởng — KIS/QA nhị phân CŨNG sai, vì bản cũ áp
# _score_for_rank(rank) một lần rồi COI NHƯ ĐÓ LÀ Final, thay vì tính max
# R-Score riêng cho từng ngưỡng k rồi mới lấy trung bình 5 giá trị.
def recall_at_k(rows: list[Answer], gt, task_type: str, k: int) -> float:
    """R@k = R-Score CAO NHẤT trong k câu đầu (docs/contest.md, công thức gốc).

    KHÔNG tra bảng rút gọn ở đây — bảng đó chỉ đúng khi áp dụng cho TOÀN BỘ
    Final Score (5 giá trị R@k gộp lại), không phải cho từng R@k riêng lẻ.
    """
    best = 0.0
    for r in rows[:k]:
        if task_type in ("KIS", "QA", "TRAKE") and not r.frame_ids:
            raise ValueError(f"Answer rỗng frame_ids cho video {r.video_id} — lỗi allocator")
        hit = 0.0
        if task_type == "KIS":
            hit = rscore_kis(r.video_id, r.frame_ids[0], gt)
        elif task_type == "QA":
            hit = rscore_qa(r.video_id, r.frame_ids[0], r.answer_text or "", gt)
        elif task_type == "TRAKE":
            hit = rscore_trake(r.video_id, r.frame_ids, gt)
        best = max(best, hit)
    return best

def final_score(rows: list[Answer], gt, task_type: str) -> float:
    """Tính Final Score = (R@1 + R@5 + R@20 + R@50 + R@100) / 5"""
    sum_score = 0.0
    for k in K_THRESHOLDS:
        sum_score += recall_at_k(rows, gt, task_type, k)
    return sum_score / 5.0

