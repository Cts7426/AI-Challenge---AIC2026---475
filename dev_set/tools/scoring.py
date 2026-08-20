from __future__ import annotations
from backend.common.answer_match import answer_matches, exact_answer_matches
from data.config.qa_evaluation import DEFAULT_QA_MATCH_POLICY, QA_MATCH_POLICIES
from dev_set.tools.schema import GroundTruthKIS, GroundTruthQA, GroundTruthTRAKE, Answer

# answer_matches re-export ở đây để code cũ import từ dev_set.tools.scoring vẫn
# chạy — cài đặt thật nằm ở backend/common/answer_match.py, DÙNG CHUNG với
# majority voting của backend/tasks/qa.py (một nguồn sự thật cho "thế nào là
# 2 câu trả lời giống nhau", xem docstring file đó).
__all__ = ["rscore_kis", "rscore_qa", "rscore_trake", "recall_at_k", "final_score",
           "ndcg_at_k", "answer_matches", "exact_answer_matches"]

K_THRESHOLDS = (1, 5, 20, 50, 100)

def rscore_kis(video_id: str, frame_idx: int, gt: GroundTruthKIS) -> float:
    if video_id != gt.video_id:
        return 0.0
    return 1.0 if gt.frame_start <= frame_idx <= gt.frame_end else 0.0

def rscore_qa(
    video_id: str,
    frame_idx: int,
    answer: str,
    gt: GroundTruthQA,
    qa_match_policy: str = DEFAULT_QA_MATCH_POLICY,
) -> float:
    """Chấm một dòng Q&A theo chính sách ngữ nghĩa hoặc chuỗi tuyệt đối.

    Input: video/frame/answer dự đoán, GT và `qa_match_policy`. Output: 0 hoặc 1.
    Invariant: video và frame phải đúng trước khi so answer; policy `exact` chỉ
    so canonical GT, còn `semantic` mới sử dụng variants do người gán nhãn cấp.
    """
    if video_id != gt.video_id:
        return 0.0
    if not (gt.frame_start <= frame_idx <= gt.frame_end):
        return 0.0

    if qa_match_policy not in QA_MATCH_POLICIES:
        raise ValueError(
            f"qa_match_policy phải là một trong {QA_MATCH_POLICIES}, nhận {qa_match_policy!r}"
        )
    if qa_match_policy == "exact":
        match = exact_answer_matches(answer, gt.answer_text)
    else:
        match, _ = answer_matches(answer, gt.answer_text, gt.answer_variants)
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
def recall_at_k(
    rows: list[Answer],
    gt,
    task_type: str,
    k: int,
    qa_match_policy: str = DEFAULT_QA_MATCH_POLICY,
) -> float:
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
            hit = rscore_qa(
                r.video_id, r.frame_ids[0], r.answer_text or "", gt, qa_match_policy
            )
        elif task_type == "TRAKE":
            hit = rscore_trake(r.video_id, r.frame_ids, gt)
        best = max(best, hit)
    return best

def final_score(
    rows: list[Answer],
    gt,
    task_type: str,
    qa_match_policy: str = DEFAULT_QA_MATCH_POLICY,
) -> float:
    """Tính Final Score theo một chính sách Q&A, các task khác không đổi."""
    sum_score = 0.0
    for k in K_THRESHOLDS:
        sum_score += recall_at_k(rows, gt, task_type, k, qa_match_policy)
    return sum_score / 5.0



# ===================================================== nDCG (A2.4, 19/08)
# Vì sao cần thêm một chỉ số nữa khi đã có Final Score:
#
#   Final Score = trung bình 5 giá trị R@k, mà mỗi R@k chỉ lấy R-Score CAO NHẤT
#   trong k câu đầu. Nghĩa là nó CHỈ nhìn câu đúng ĐẦU TIÊN — đẩy câu đúng thứ
#   hai từ hạng 80 lên hạng 30 không làm Final đổi một chút nào.
#
#   Rerank (A2.4) lại chính là việc SẮP XẾP LẠI cả danh sách. Đo nó bằng Final
#   Score là đo bằng thước không có vạch: rerank tốt lên mà điểm đứng yên, rồi
#   kết luận "không tăng → tắt" vì thước, chứ không vì model.
#
# nDCG nhìn TOÀN BỘ k vị trí, mỗi vị trí chiết khấu theo log — đúng thứ cần để
# trả lời câu hỏi của A2.4. Nó KHÔNG thay Final Score (Final Score mới là điểm
# BTC chấm), chỉ là thước phụ để quyết định bật/tắt rerank.

import math


def _relevance(
    row: Answer,
    gt,
    task_type: str,
    qa_match_policy: str = DEFAULT_QA_MATCH_POLICY,
) -> float:
    """Độ liên quan của MỘT dòng nộp, thang [0, 1]. Dùng lại đúng rscore_* đang chấm.

    KIS/QA nhị phân (0 hoặc 1); TRAKE ra điểm lẻ theo tỉ lệ khoảnh khắc khớp —
    nDCG nhận cả hai, không cần nhánh riêng.
    """
    if not row.frame_ids:
        raise ValueError(f"Answer rỗng frame_ids cho video {row.video_id} — lỗi allocator")
    if task_type == "KIS":
        return rscore_kis(row.video_id, row.frame_ids[0], gt)
    if task_type == "QA":
        return rscore_qa(
            row.video_id, row.frame_ids[0], row.answer_text or "", gt, qa_match_policy
        )
    if task_type == "TRAKE":
        return rscore_trake(row.video_id, row.frame_ids, gt)
    raise ValueError(f"task_type không hợp lệ: {task_type}")


def _dcg(rels: list[float]) -> float:
    """DCG = Σ rel_i / log2(i + 1), i đếm từ 1."""
    return sum(r / math.log2(i + 1) for i, r in enumerate(rels, start=1))


def ndcg_at_k(
    rows: list[Answer], gt, task_type: str, k: int = 20,
    ideal_rels: list[float] | None = None,
    qa_match_policy: str = DEFAULT_QA_MATCH_POLICY,
) -> float:
    """nDCG@k của một bài nộp. Trả 0.0 khi không có dòng nào liên quan.

    ⚠️ `ideal_rels` — tham số quyết định con số có SO SÁNH ĐƯỢC hay không.
    Mặc định (None) mẫu số IDCG tính từ chính `rows`, tức "sắp xếp lại tốt nhất
    có thể của đúng danh sách này". Đúng khi đo MỘT bài nộp đơn lẻ.
    NHƯNG khi A/B hai cách xếp hạng (rerank bật vs tắt), hai bên có thể giữ lại
    hai tập ứng viên khác nhau → hai mẫu số khác nhau → hai con số nDCG không
    còn so với nhau được, mà vẫn trông như so được. Lúc đó PHẢI truyền cùng một
    `ideal_rels` (thường lấy từ bể ứng viên chung trước khi cắt) cho cả hai bên.
    """
    if k < 1:
        raise ValueError(f"k phải >= 1, nhận {k}")

    rels = [_relevance(r, gt, task_type, qa_match_policy) for r in rows[:k]]
    if ideal_rels is None:
        ideal_rels = [_relevance(r, gt, task_type, qa_match_policy) for r in rows]

    idcg = _dcg(sorted(ideal_rels, reverse=True)[:k])
    if idcg <= 0:
        return 0.0  # không có gì liên quan trong bể → mọi cách xếp đều như nhau
    return _dcg(rels) / idcg
