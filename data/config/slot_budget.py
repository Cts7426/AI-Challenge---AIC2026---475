# data/config/slot_budget.py — D3.1: Chia 100 slot cho các shot
#
# Tách khỏi backend/slot/allocator.py vì hai thứ này đổi với nhịp khác nhau:
#   allocator.py  → CƠ CHẾ  : rút frame, xen kẽ, bảo đảm đủ 100. Viết một lần là xong.
#   slot_budget.py      → CHIẾN THUẬT: cược bao nhiêu slot vào shot hạng mấy. Sẽ đổi nhiều lần.
#
# Vì sao một shot cần NHIỀU hơn 1 slot?
# → Chấm frame_id ∈ [s, e].
#   Shot median 69 frame (đo trên shots.parquet, max 1795).
#
# Vì sao không rải đều 100 shot × 1 frame?
# → Ngược lại: phủ rộng nhưng shot nào cũng chỉ 1 cửa, trúng shot mà trượt cửa sổ.
#   Bảng dưới là điểm cân giữa RỘNG (phủ nhiều shot) và SÂU (chắc trúng cửa sổ).
#
# TODO: BTC — độ rộng cửa sổ [s, e] chưa công bố.
#   Cửa sổ RỘNG  → nên rải ra nhiều shot hơn, giảm slot mỗi shot.
#   Cửa sổ HẸP   → nên đào sâu hơn vào ít shot.
#   Đây là giả định, không phải con số đã chốt.

# Mỗi cặp (số shot, số slot mỗi shot), xếp theo hạng shot giảm dần.
# 3×8 + 7×5 + 10×3 + 11×1 = 100 slot, phủ 31 shot.
#
#   hạng 1–3   : 8 slot — tin nhất, đào sâu cho chắc trúng cửa sổ
#   hạng 4–10  : 5 slot
#   hạng 11–20 : 3 slot
#   hạng 21–31 : 1 slot — vé số, nhưng ô 51–100 bỏ trống cũng là vứt điểm miễn phí
SLOT_BUDGET: list[tuple[int, int]] = [(3, 8), (7, 5), (10, 3), (11, 1)]

# ANSWERS_PER_QUERY (= 100) là LUẬT CỦA BTC nên nó sống ở submit_format.py chứ không
# phải ở đây. Import lại để chỗ dùng khỏi phải nhớ nó nằm file nào — nhưng chỉ có MỘT
# nơi khai báo. Hai bản sao của cùng con số là cách chắc nhất để chúng lệch nhau về sau.
from data.config.submit_format import ANSWERS_PER_QUERY  # noqa: E402

# Thụt vào mỗi đầu shot khi rải frame, tính theo tỉ lệ độ dài shot.
# Vì sao: frame sát biên shot hay dính chuyển cảnh — mờ, hoặc lẫn hai cảnh.
# Frame ĐẦU TIÊN của shot không chịu luật này (nó là keyframe thật, có bằng chứng).
SHOT_EDGE_INSET = 0.10

# TRAKE: số khoảnh khắc mỗi dòng khi đề bài không công bố N.
# TODO: BTC — chưa rõ đề TRAKE có cho biết N trước không.
TRAKE_DEFAULT_N = 4


def budget_per_shot(n_shots: int, table: list[tuple[int, int]] = SLOT_BUDGET) -> list[int]:
    """Trải bảng ngân sách thành hạn mức từng shot theo hạng.

    INPUT: số shot ứng viên thực có.
    OUTPUT: list dài đúng n_shots, phần tử i = số slot cấp cho shot hạng i.
    Bất biến: tổng = ANSWERS_PER_QUERY, kể cả khi n_shots ít hơn hoặc nhiều hơn bảng.

    Hai ca lệch so với bảng, đều xử lý ở đây chứ không để allocator lo:
      - Ít shot hơn bảng (search chỉ ra 3 shot) → chia đều phần thiếu cho các shot
        đang có, ưu tiên shot hạng cao. KHÔNG BAO GIỜ trả tổng < 100.
      - Nhiều shot hơn bảng → các shot ngoài bảng nhận 0, coi như không dùng.
    """
    if n_shots <= 0:
        raise ValueError("Không có shot ứng viên nào để cấp phát slot")

    han_muc = [0] * n_shots
    i = 0
    for so_shot, slot_moi_shot in table:
        for _ in range(so_shot):
            if i >= n_shots:
                break
            han_muc[i] = slot_moi_shot
            i += 1

    # Thiếu slot (ít shot hơn bảng) → rải vòng tròn từ shot hạng cao xuống.
    # Rải vòng tròn chứ không dồn hết vào shot 1: dồn hết là quay lại đúng cái
    # sai "8 slot đầu cùng một shot" mà luật xen kẽ đang tránh.
    thieu = ANSWERS_PER_QUERY - sum(han_muc)
    j = 0
    while thieu > 0:
        han_muc[j % n_shots] += 1
        thieu -= 1
        j += 1

    return han_muc
