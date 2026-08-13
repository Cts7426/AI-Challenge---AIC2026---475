# data/config/slot_budget.py — D3.1: chia 100 slot cho các shot ứng viên.
#
# Tách khỏi backend/slot/allocator.py vì hai thứ đổi với nhịp khác nhau:
#   allocator.py    → CƠ CHẾ  : rút frame, xen kẽ, bảo đảm đủ 100. Viết một lần là xong.
#   slot_budget.py  → CHIẾN THUẬT: cược bao nhiêu slot vào shot hạng mấy. Đổi nhiều lần.
#
# Vì sao một shot cần nhiều hơn 1 slot: BTC chấm `frame_id ∈ [s, e]`, một cửa sổ hẹp
# bên trong shot. Shot median 69 frame (đo trên shots.parquet, max 1795) — trúng shot
# vẫn có thể trượt cửa sổ. Ngược lại, rải đều 100 shot × 1 frame thì phủ rộng mà shot
# nào cũng chỉ một cửa. Bảng dưới là điểm cân giữa RỘNG và SÂU.
#
# TODO: BTC — độ rộng cửa sổ [s, e] chưa công bố. Rộng → nên rải ra nhiều shot hơn;
# hẹp → nên đào sâu vào ít shot. Bảng hiện tại là giả định, D4.1 là task tune nó.

from data.config.submit_format import ANSWERS_PER_QUERY

# (số shot, số slot mỗi shot), xếp theo hạng shot giảm dần.
# 3×8 + 7×5 + 10×3 + 11×1 = 100 slot, phủ 31 shot.
#   hạng 1–3   : 8 slot — tin nhất, đào sâu cho chắc trúng cửa sổ
#   hạng 4–10  : 5 slot
#   hạng 11–20 : 3 slot
#   hạng 21–31 : 1 slot — vé số, nhưng ô 51–100 bỏ trống cũng là vứt điểm miễn phí
SLOT_BUDGET: list[tuple[int, int]] = [(3, 8), (7, 5), (10, 3), (11, 1)]

# Thụt vào mỗi đầu shot khi rải frame, theo tỉ lệ độ dài shot. Frame sát biên hay
# dính chuyển cảnh (mờ, lẫn hai cảnh). Frame ĐẦU TIÊN của shot không chịu luật này —
# nó là keyframe thật, có bằng chứng.
SHOT_EDGE_INSET = 0.10

# TRAKE: số khoảnh khắc mỗi dòng khi đề bài không công bố N.
# TODO: BTC — chưa rõ đề TRAKE có cho biết N trước không.
TRAKE_DEFAULT_N = 4


def budget_per_shot(
    n_shots: int,
    table: list[tuple[int, int]] = SLOT_BUDGET,
    total: int = ANSWERS_PER_QUERY,
) -> list[int]:
    """Trải bảng ngân sách thành hạn mức từng shot theo hạng.

    Vào: số shot ứng viên thực có · bảng cược · tổng slot cần chia (lúc thi = 100).
    Ra: list dài đúng `n_shots`, phần tử i = số slot cấp cho shot hạng i.
    Bất biến: tổng luôn bằng `total`, kể cả khi n_shots lệch so với bảng.

    Ba ca lệch, xử lý ở đây chứ không để allocator lo:
      · ít shot hơn bảng → rải vòng tròn phần thiếu, ưu tiên hạng cao
      · nhiều shot hơn bảng → shot ngoài bảng nhận 0
      · `total` nhỏ hơn tổng bảng → bớt CHIỀU SÂU trước, giữ CHIỀU RỘNG
    """
    if n_shots <= 0:
        raise ValueError("Không có shot ứng viên nào để cấp phát slot")
    if total < 1:
        raise ValueError(f"total phải >= 1, nhận {total}")

    quota = [0] * n_shots
    i = 0
    for n_shot, slots in table:
        for _ in range(n_shot):
            if i >= n_shots:
                break
            quota[i] = slots
            i += 1

    # Thừa slot → bớt từng cái một ở shot đang sâu nhất, hoà thì bớt shot hạng thấp.
    # Bớt chiều sâu chứ không cắt đuôi: cắt đuôi thì total=5 ra [5,0,0,…] — cả 5 dòng
    # đầu cùng một shot, đúng cái sai mà luật xen kẽ đang tránh.
    surplus = sum(quota) - total
    while surplus > 0:
        deepest = max(range(n_shots), key=lambda x: (quota[x], x))
        quota[deepest] -= 1
        surplus -= 1

    # Thiếu slot → rải vòng tròn từ hạng cao xuống, không dồn hết vào shot 1.
    missing = total - sum(quota)
    j = 0
    while missing > 0:
        quota[j % n_shots] += 1
        missing -= 1
        j += 1

    return quota
