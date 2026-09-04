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
# ===== D4.1 (19/08) — ĐÃ ĐO — xem lịch sử đầy đủ ở reports/slot_tuning.md =====
#
# 1. `score_simulator shotrank` trên 23 câu KIS dev: hạng của shot đúng có trung
#    vị 10, LỚN NHẤT 95. Bảng 73-shot cũ bỏ rơi K18 (hạng 80) và K01 (hạng 95) —
#    0 slot, trượt chắc chắn vì bảng ngân sách, không phải vì search kém.
#    Replay đo được: phủ trọn 100 → Final 0.470 → 0.487, chênh lệch nằm hết ở
#    R@100 (0.739 → 0.826, đúng 2 câu đó).
#
# 2. `sweep` trên shot THẬT (không phụ thuộc dev set, không dính nhược điểm §3
#    dưới): phủ rộng thắng ở MỌI độ rộng cửa sổ giả định kể cả w=11 — đúng con
#    số duy nhất BTC từng công bố (mục 2.1.1 tài liệu Sơ tuyển, ví dụ [500,510])
#    — 0.328 so với 0.211 của bảng 73-shot cũ.
#
# 3. Nhược điểm đã biết: cửa sổ ground truth của dev set được dựng TỪ CHÍNH
#    keyframe nên "trúng shot ⇒ trúng đáp án" ở phép đo #1 là hệ quả cách dựng
#    dev set, không hẳn là bằng chứng độc lập. Phép đo #2 (sweep) không có
#    nhược điểm này — và vẫn cho cùng kết luận.
#
# ===== SỬA 20/08 (đêm trước Đợt 1) — đổi sang phủ rộng =====
# Bảng 73-shot giữ tới giờ vì "chưa đủ bằng chứng cho trục ĐỘ SÂU" — đúng khi
# còn thời gian đo thêm. Đêm nay không còn thời gian đó, và đo trực tiếp trên
# `dev_set/queries/tune_kis.jsonl` (23 câu, `dev_set/tools/eval_kis_only.py`,
# KHÔNG tốn 1 lượt llm() nào — chạy được dù tài khoản Anthropic đã hết tiền)
# xác nhận lại ĐÚNG hệt phát hiện D4.1: K18 rơi đúng hạng 91, 0 slot, R@100=0
# dù search() đã tìm thấy. Tối đa hoá điểm KIS đêm trước ngày thi là ưu tiên
# rõ ràng hơn giữ nguyên một canh bạc "đào sâu" chưa từng được đo là có lợi.
# Chọn "đỉnh2 97sh" (đo ở score_simulator.py, reports/slot_tuning.md §6) thay
# vì phủ trọn `[(100,1)]` tuyệt đối — Final replay bằng nhau (0.487) nhưng vẫn
# giữ 2 slot cho hạng 1 làm hàng rào phòng khi cửa sổ [s,e] hoá ra hẹp hơn cả
# w=11. Phủ tới hạng 97 — đủ cứu cả K18 (hạng 91) lẫn K01 (hạng 95).
# Quyết định này thuộc quyền Công Lý (chủ bảng) — tự chốt, không cần báo ai.
# ===== SỬA 02/09 (R3.K5) — cân lại về phía SÂU vì ranking đã khá lên =====
# Bảng phủ rộng ở trên chọn ngày 20/08 với lý do ghi rõ: shot đúng hay rơi vào
# hạng 80–95, nên phủ rộng thắng đào sâu. Lý do đó HẾT ĐÚNG sau R3.K3: hai nhánh
# vector + pool 1500 đưa R@100 mức video lên 1,00 và R@1 lên 0,55 — không còn
# câu nào cần vớt ở hạng 91 nữa, nên slot dành cho cái đuôi là slot lãng phí.
#
# Đo 02/09 · 20 câu KIS p1 · cấu hình K3 (dual vector, pool 1500, RRF_K=7) ·
# `scripts/sweep_k5_slot.sh` · artefact `dev_set/results/run_20260902_k5_slot/`:
#
#   bảng                    Final video   f±5    f±15   f±40
#   1x2,2x2,94x1 (cũ)          0,8400     0,18   0,18   0,30
#   100x1 (phủ trọn)           0,8400     0,18   0,18   0,30
#   1x8,4x4,10x2,56x1          0,8300     0,25   0,26   0,30
#   1x4,4x3,12x2,60x1  ← chọn  0,8300     0,22   0,26   0,33
#   1x12,4x6,8x4,32x1          0,8300     0,19   0,27   0,29
#
# Chọn `1x4,4x3,12x2,60x1` vì nó là bảng DUY NHẤT cải thiện ở CẢ BA dung sai so
# với bảng cũ (+0,04 / +0,08 / +0,03). Độ rộng cửa sổ [s,e] của BTC vẫn chưa
# công bố, nên bảng chỉ thắng ở một dung sai là bảng đang cược vào một giả định
# chưa ai kiểm — `1x12,...` tụt ở ±40 nên loại dù ±15 cao nhất.
#
# Giá phải trả: Final mức VIDEO 0,8400 → 0,8300 (một video rớt khỏi 100 dòng).
# Chấp nhận, vì BTC chấm `frame_id ∈ [s,e]` — đúng video mà sai frame vẫn 0 điểm,
# nên cột frame mới là điểm thật, cột video chỉ là trần trên.
# Đo 03/09 · 20 câu KIS p1 · nhánh ocr_probe bật · dual vector · pool 1500:
#   bảng                    ±5     ±15    ±40
#   1x4,4x3,12x2,60x1      0,18   0,26   0,33   (bảng chọn ngày 02/09)
#   1x2,2x2,94x1           0,23   0,24   0,33   (bảng cũ)
#   50x2                   0,23   0,27   0,34   <- chọn, tốt nhất ở CẢ BA dung sai
# Mức video giống hệt nhau ở cả ba bảng (top-10 0,95), nên chọn thuần theo frame
# — BTC chấm frame_id ∈ [s,e], đúng video mà sai frame vẫn 0 điểm.
SLOT_BUDGET: list[tuple[int, int]] = [(50, 2)]

# Thụt vào mỗi đầu shot khi rải frame, theo tỉ lệ độ dài shot. Frame sát biên hay
# dính chuyển cảnh (mờ, lẫn hai cảnh). Frame ĐẦU TIÊN của shot không chịu luật này —
# nó là keyframe thật, có bằng chứng.
SHOT_EDGE_INSET = 0.10

# TRAKE: số khoảnh khắc mỗi dòng khi đề bài không công bố N.
# TODO: BTC — chưa rõ đề TRAKE có cho biết N trước không.
TRAKE_DEFAULT_N = 4


# ══════════════════════ TRAKE — chiều sâu dòng nộp (21/08) ══════════════════════
#
# ⚠️ VẤN ĐỀ ĐO ĐƯỢC. `backend/tasks/trake.py::to_answers()` sinh ĐÚNG 1 dòng cho
# mỗi video ứng viên → 100 dòng nộp = 100 video KHÁC NHAU, mỗi video đúng MỘT
# phương án. Mà BTC chấm `R@k = R-Score CAO NHẤT trong k dòng đầu`
# (data/config/scoring.py). Hệ quả: khi video đúng đã nằm ở hạng 1, **99 dòng
# còn lại không thể cải thiện điểm** — điểm bị ĐÓNG BĂNG ở giá trị của đúng một
# dòng. Kiểm trực tiếp trên file nộp `dev_set/results/run_20260820_2101/`:
#
#   TR01: 100 dòng = 100 video khác nhau, video đúng xuất hiện ĐÚNG 1 lần
#         (dòng 1), trúng 2/4 sự kiện → R@1..R@100 đều 0.50, Final 0.500
#   TR02: video đúng ở dòng 5, trúng 2/3 → Final 0.533
#
# Và phương án đúng NẰM SẴN TRONG RỔ: soi rổ ứng viên trong chính video đúng,
# 2/3 vị trí bị DP chọn hụt vẫn có ứng viên đúng trong rổ (TR01 vị trí 2 có
# frame 3840 trong rổ 12 ứng viên; TR02 vị trí 3 có frame 2816 trong rổ 6).
# Tức là KHÔNG PHẢI truy hồi thiếu — chỉ là không có dòng nào để đặt cược thứ hai.
#
# ⚠️ VÌ SAO CÓ `TRAKE_BREADTH_ROWS` — bảo đảm KHÔNG HỒI QUY.
# "Sai video = 0 điểm tuyệt đối" (CLAUDE.md §5.3), nên đổi chiều rộng lấy chiều
# sâu là canh bạc. Đặt ngưỡng này = 20 thì **20 dòng đầu giữ NGUYÊN VẸN như
# trước** (mỗi dòng một video, đúng thứ tự cũ) → R@1, R@5, R@20 **không thể tệ
# đi về mặt cấu trúc**, chỉ R@50/R@100 mới có thể tốt lên. Đây là thay đổi
# không-âm theo thiết kế, không phải theo may mắn.
#
# Muốn cược mạnh hơn (đưa phương án thay thế lên sớm, ăn cả R@5/R@20) thì hạ số
# này — nhưng phải đo lại trên bộ đề TRAKE có nhiều câu hơn 2 câu hiện có.
TRAKE_BREADTH_ROWS = 20

# Số phương án thay thế DỰNG SẴN cho mỗi video. Đây là DỮ LIỆU, không phải
# chiến thuật — dựng thừa không tốn gì (tính thuần tuý trên rổ ứng viên đã tải,
# không thêm một lần gọi Milvus/ES nào), còn dùng bao nhiêu là việc của
# `TRAKE_ALT_BUDGET` bên dưới.
#
# 8 = cao hơn hẳn mức bảng dưới dùng tới (3), chừa chỗ nếu ai đó nâng bảng mà
# không phải sửa chỗ sinh. Dựng thừa gần như miễn phí.
TRAKE_ALT_GENERATED = 8

# Dùng BAO NHIÊU phương án thay thế cho video hạng nào — cùng dạng bảng với
# SLOT_BUDGET: (số video, số phương án mỗi video), xếp theo hạng video giảm dần.
#
# ===== ĐÃ ĐO (21/08, TR01 + TR02, đường chạy thật) =====
#   bảng                       TR01     TR02      TB
#   không chiều sâu (cũ)       0.750    0.267    0.508
#   [(1,12),(4,3),(95,1)]      0.750    0.333    0.542
#   [(5,3),(95,1)]   ← chọn    0.750    0.400    0.575
#   [(100,2)]                  0.750    0.267    0.508
#   [(100,1)]                  0.750    0.267    0.508
#   [(1,6),(9,2),(90,1)]       0.750    0.267    0.508
#
# Vì sao KHÔNG dồn cho hạng 1 (bảng [(1,12),...] trông hợp lý mà lại kém hơn):
# 12 phương án của video hạng 1 chiếm hết dòng 21–43, đẩy phương án của video
# hạng 5 — chính là video ĐÚNG của TR02 — từ dòng 47 xuống 67, tức rơi khỏi
# R@50. Đào sâu một video là lấy chỗ của mọi video khác; dồn quá tay thì tự bắn
# vào chân.
#
# Vì sao [(100,2)] và [(1,6),(9,2),...] không ăn gì: phương án cứu TR02 là
# phương án THỨ BA của video hạng 5. Bảng nào cấp <3 cho video hạng 5 đều trượt.
#
# ⚠️ TRUNG THỰC VỀ CỠ MẪU: đây là 2 câu. Bảng B thắng vì đúng 1 câu (TR02) cải
# thiện, và mức 3-phương-án vừa đủ chạm phương án cứu nó. Đừng đọc con số này
# như "đã tối ưu" — đọc như "chiều sâu có tác dụng thật, và mức vừa phải tốt hơn
# mức dồn". Đo lại khi bộ đề TRAKE có nhiều hơn 2 câu.
#
# ⚠️ TR01 KHÔNG cải thiện ở BẤT KỲ bảng nào: ứng viên đúng của vị trí 2 nằm ở
# hạng 11/12 trong rổ của chính vị trí đó, ngoài tầm mọi ngân sách hợp lý. Đó là
# lỗi XẾP HẠNG trong rổ (CLIP), không phải lỗi cấp dòng — chiều sâu không sửa được.
#
# ⚠️ ĐÁNH ĐỔI ĐÃ BIẾT: mỗi dòng phương án chiếm chỗ một dòng gốc. Sau dòng 20,
# xen kẽ 1-1 nên dòng gốc của video hạng r rơi vào khoảng dòng 20+2(r-20) — video
# hạng 36–50 bị đẩy từ R@50 xuống chỉ còn R@100. Chấp nhận vì hai ca đo được đều
# có video đúng ở hạng 1 và 5, và vì video SAI thì dòng gốc của nó vốn 0 điểm.
TRAKE_ALT_BUDGET: list[tuple[int, int]] = [(5, 3), (95, 1)]

# Bước dịch frame khi phải ĐỆM dòng (chỉ dùng khi số video ứng viên < 100 và đã
# hết phương án thay thế).
#
# ⚠️ Bản cũ dịch +1, +2, +3 frame. Đo được: hai ca trượt của TR01/TR02 đều là
# chọn nhầm ĐÚNG MỘT SHOT liền kề (`s0060` thay vì `s0059`; `s0036` thay vì
# `s0035`) — lệch khoảng 45 frame. Dịch 1 frame thì vẫn nằm nguyên trong shot
# sai, tức 90 dòng đệm gần như vô giá trị. Shot có trung vị 69 frame
# (shots.parquet) nên bước 60 là "sang shot kề" mà không nhảy quá xa.
TRAKE_PAD_SHIFT_FRAMES = 60


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
