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
# 1×6 + 4×4 + 10×2 + 58×1 = 100 slot, phủ 73 shot.
# Phát hiện thực tế (17/08): shot đúng của các câu KIS có thể rơi vào hạng 32-100,
# bảng [3x8, 7x5...] cũ bị chặt cụt quá sớm khiến mất recall. Cần mở rộng đuôi.
#   hạng 1      : 6 slot — tin nhất
#   hạng 2–5    : 4 slot
#   hạng 6–15   : 2 slot
#   hạng 16–73  : 1 slot — bao phủ diện rộng để vớt vát các shot hạng thấp
#
# ===== D4.1 (19/08) — ĐÃ ĐO, CHƯA ĐỔI =====
# Số liệu đầy đủ ở reports/slot_tuning.md. Ghi lại ở đây để lần tune sau khỏi đo
# lại từ đầu — KHÔNG phải để biện minh cho một lần đổi bảng.
#
# 1. `score_simulator shotrank` trên 23 câu KIS dev: hạng của shot đúng có trung
#    vị 10, LỚN NHẤT 95. Bảng này phủ 73 shot nên K18 (hạng 80) và K01 (hạng 95)
#    không được cấp slot nào — trượt chắc chắn, không phải trượt vì search kém.
#    Replay nếu phủ trọn 100: Final 0.470 → 0.487, toàn bộ chênh lệch nằm ở
#    R@100 (0.739 → 0.826), đúng hai câu đó.
#
# 2. `sweep` trên shot THẬT, tại đúng phân bố hạng vừa nói: phủ rộng thắng ở mọi
#    độ rộng cửa sổ giả định (w=11: 0.328 so với 0.211).
#
# 3. NHƯNG số 1 và 2 chỉ đo được MỘT trục. Cửa sổ ground truth của dev set được
#    dựng TỪ CHÍNH keyframe (Q1–Q5 có keyframe đúng tâm cửa sổ, K01–K18 có
#    keyframe đúng bằng `frame_start`), nên "trúng shot ⇒ trúng đáp án" ở đó là
#    hệ quả của cách dựng dev set, không phải kết quả đo. Trục ĐỘ SÂU — bảng này
#    đang cược vào — dev set hiện tại không phủ nhận được, mà cũng không xác nhận
#    được.
#
# Giữ bảng 73 shot cho tới khi có dev set dựng cửa sổ ĐỘC LẬP với keyframe, hoặc
# tới khi BTC công bố độ rộng [s, e]. Đổi thì phải có số của cả hai trục, và phải
# báo Công Lý (người viết bảng này) trước.
SLOT_BUDGET: list[tuple[int, int]] = [(1, 6), (4, 4), (10, 2), (58, 1)]

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
