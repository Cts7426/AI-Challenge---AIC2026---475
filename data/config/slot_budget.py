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
# Độ rộng cửa sổ [s, e] của KIS vẫn CHƯA được BTC công bố thành con số. Ví dụ duy
# nhất có số trong tài liệu vòng Sơ tuyển (mục 2.1.1) là [500, 510] — 11 frame,
# hẹp hơn shot median (69 frame) rất nhiều. Xem reports/slot_tuning.md §2.

from data.config.submit_format import ANSWERS_PER_QUERY

# (số shot, số slot mỗi shot), xếp theo hạng shot giảm dần.
#
# ===== D4.1 (19/08) — 100 shot × 1 slot, phủ TRỌN 100 hạng =====
# Đo đầy đủ ở reports/slot_tuning.md. Ba bằng chứng, xếp theo độ chắc chắn:
#
# 1. ĐO ĐƯỢC, KHÔNG PHỤ THUỘC GIẢ ĐỊNH — `score_simulator shotrank` trên 23 câu
#    KIS dev: hạng của shot đúng có trung vị 10, lớn nhất 95. Bảng cũ phủ 73 shot
#    nên K18 (hạng 80) và K01 (hạng 95) KHÔNG được cấp slot nào — trượt chắc
#    chắn, không phải trượt vì search kém. Đó là điểm tự vứt đi.
#    Replay: Final 0.470 (bảng cũ) → 0.487 (phủ 100), toàn bộ chênh lệch nằm ở
#    R@100 (0.739 → 0.826), đúng hai câu đó.
#
# 2. ĐO ĐƯỢC — `sweep` trên shot THẬT, tại đúng phân bố hạng vừa nói: phủ rộng
#    thắng ở mọi độ rộng cửa sổ giả định (w=11: 0.328 so với 0.211 của bảng cũ).
#
# 3. KHÔNG ĐO ĐƯỢC bằng dev set hiện tại — liệu ĐÀO SÂU trong shot có đáng
#    không. Cửa sổ ground truth của dev set được dựng TỪ CHÍNH keyframe (đo
#    19/08: Q1–Q5 có keyframe đúng tâm cửa sổ, K01–K18 có keyframe đúng bằng
#    `frame_start`), nên "trúng shot ⇒ trúng đáp án" ở đó là hệ quả của cách
#    dựng dev set chứ không phải kết quả đo. Không có bằng chứng thì không cược:
#    ưu tiên cái đo được (phủ rộng) hơn cái chỉ suy đoán (đào sâu).
#
# Hệ quả có lợi kèm theo: mỗi shot chỉ nhận 1 slot nên MỌI dòng nộp đều là frame
# của keyframe thật (mức ưu tiên ① trong allocator) — không dòng nào là frame
# rải suy đoán.
#
# Ít hơn 100 shot ứng viên thì `budget_per_shot()` tự rải phần dư thành chiều
# sâu (71 shot → 29 shot đầu được 2 slot). Chiều sâu quay lại đúng lúc không còn
# chiều rộng để mua, không cần bảng riêng.
#
# ⚠️ ĐẢO LẠI KHI NÀO: nếu đợt 1 cho thấy cửa sổ đáp án thật sự hẹp (~10 frame)
# VÀ shot đúng thường ở hạng ≤ 5, thì chiều sâu mới mua được thứ chiều rộng
# không mua nổi. Chạy lại `shotrank` + `replay` trên dev set có cửa sổ dựng ĐỘC
# LẬP với keyframe rồi hãy đổi — đừng đổi bằng cảm giác.
SLOT_BUDGET: list[tuple[int, int]] = [(100, 1)]

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

    # Thiếu slot → san bằng shot đang THẤP NHẤT trước (hoà thì ưu tiên hạng cao),
    # không round-robin từ index 0.
    #
    # ⚠️ SỬA 18/08 — bản cũ round-robin cố định từ j=0: `quota[j % n_shots] += 1`.
    # Khi bảng ban đầu ĐÃ lệch (vd n_shots=3 với SLOT_BUDGET hạng-1 riêng: quota
    # mồi = [6,4,4]), vòng lặp này CỘNG THÊM gần đều lên trên nền đã lệch — độ
    # lệch không được san bằng mà CHỒNG lên nhau: 86 slot thiếu chia 3 vòng tròn
    # ra [+29,+29,+28] → kết quả [35,33,32], lệch 3 thay vì 1. Đúng cái sai mà
    # cơ chế xen kẽ (docstring allocator.py) đang tránh — 3 slot thừa dồn hẳn
    # vào shot hạng 1 là quay lại lối gom cũ.
    #
    # San bằng thấp nhất trước: 4 vòng đầu kéo [6,4,4] → [6,6,6] (bù đúng độ
    # lệch mồi), rồi mới round-robin đều từ đó — [34,33,33] giống kết quả bảng
    # cũ (n_shot đều nhau), đúng ý "rải đều khi ít shot" của docstring.
    missing = total - sum(quota)
    while missing > 0:
        thap_nhat = min(range(n_shots), key=lambda x: (quota[x], x))
        quota[thap_nhat] += 1
        missing -= 1

    return quota
