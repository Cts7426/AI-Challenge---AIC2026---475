# data/config/scoring.py — công thức chấm điểm của BTC (nguồn: tài liệu vòng Sơ tuyển
# AIC2026, mục 2). Hằng số của cuộc thi, KHÔNG phải tham số tune — để riêng khỏi
# search_weights.py / slot_budget.py để không ai chỉnh nhầm khi đang tune thứ khác.

from __future__ import annotations

K_THRESHOLDS: tuple[int, ...] = (1, 5, 20, 50, 100)
MAX_ANSWERS = 100                        # BTC chỉ chấm 100 câu đầu mỗi truy vấn
TASKS_WITH_ANSWER = ("QA",)              # dạng bài có thêm cửa tử `answer`


def r_at_k(r_scores: list[float], k: int) -> float:
    """R-Score cao nhất trong k câu trả lời đầu tiên.

    Nộp ít hơn k câu thì chỉ xét số câu đang có — max của tập nhỏ hơn vẫn là max
    hợp lệ, không được coi phần thiếu là 0 rồi kéo kết quả xuống.
    """
    return max(r_scores[:k], default=0.0)


def final_score(r_scores: list[float]) -> float:
    """Trung bình cộng của R@1, R@5, R@20, R@50, R@100.

    Ví dụ BTC: câu 1 được 0.5, câu 3 được 0.8, câu 15 được 0.6
    → R@1 = 0.5; R@5 = R@20 = R@50 = R@100 = 0.8 → Final = 0.74.

    ⚠️ Bảng rút gọn "hạng 1 → 1.00, hạng 2–5 → 0.80…" là HỆ QUẢ của hàm này khi
    R-Score nhị phân. Nó không đúng cho TRAKE (điểm lẻ) — luôn gọi hàm, đừng tra bảng.
    """
    return sum(r_at_k(r_scores, k) for k in K_THRESHOLDS) / len(K_THRESHOLDS)
