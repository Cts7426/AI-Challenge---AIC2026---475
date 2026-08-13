# data/config/scoring.py — E4.2: công thức chấm điểm của BTC, chép nguyên văn.
#
# Nguồn: "Thông tin vòng Sơ tuyển AIC2026", mục 2. Đây là hằng số của cuộc thi,
# KHÔNG phải tham số tune — để riêng khỏi `search_weights.py`/`slot_budget.py` là
# để không ai vô tình chỉnh nó khi đang tune thứ khác.
#
# Hai tầng, đừng trộn:
#   Tầng 1 — mỗi câu trả lời một R-Score ∈ [0,1], KHÔNG dính thứ hạng.
#   Tầng 2 — R@k = max R-Score trong k câu đầu; Final = trung bình 5 giá trị R@k.
#
# ⚠️ Bảng "hạng 1 → 1.00, hạng 2–5 → 0.80…" hay thấy trong tài liệu rút gọn là KẾT
# QUẢ SUY RA của hai tầng này khi R-Score nhị phân (KIS/Q&A). Nó SAI với TRAKE vì
# TRAKE có điểm lẻ. Luôn chạy công thức, không tra bảng.

from __future__ import annotations

# Các mốc xếp hạng BTC chấm.
K_MOC: tuple[int, ...] = (1, 5, 20, 50, 100)

# Số câu trả lời tối đa mỗi truy vấn. Trùng với ANSWERS_PER_QUERY của tầng export —
# giữ ở đây để `eval.py` không phải import ngược lên tầng nộp bài.
SO_CAU_TOI_DA = 100

# Dạng bài có `answer`. Q&A có HAI cửa tử độc lập: frame sai = 0, answer sai = 0.
DANG_CO_ANSWER = ("QA",)


def r_at_k(r_scores: list[float], k: int) -> float:
    """`R@k` = R-Score cao nhất trong k câu đầu.

    Nộp ít hơn k câu thì chỉ xét số câu đang có — không coi phần thiếu là 0 rồi
    kéo max xuống, vì max của tập nhỏ hơn vẫn là max hợp lệ.
    """
    if not r_scores:
        return 0.0
    return max(r_scores[:k], default=0.0)


def final_score(r_scores: list[float]) -> float:
    """Trung bình cộng của R@1, R@5, R@20, R@50, R@100.

    Ví dụ của BTC: câu 1 được 0.5, câu 3 được 0.8, câu 15 được 0.6
    → R@1 = 0.5 · R@5 = R@20 = R@50 = R@100 = 0.8
    → Final = (0.5 + 0.8×4) / 5 = 0.74
    """
    return sum(r_at_k(r_scores, k) for k in K_MOC) / len(K_MOC)
