"""Tiên nghiệm MỨC VIDEO cho làn KIS — vá chỗ RRF đánh rơi video đúng.

===== Vì sao cần =====
RRF hiện hành xếp hạng KEYFRAME rồi gom shot. Một video mà đáp án là cảnh kéo
dài sẽ có hàng trăm keyframe cùng khớp ở mức khá, nhưng KHÔNG keyframe nào
thắng tuyệt đối. Kết quả: shot tốt nhất của nó bị hàng chục shot lẻ từ video
khác chen lên trước.

Đo được trên p1 (20 câu KIS, 02-03/09):

    câu      hạng VIDEO trong nhánh tốt nhất      hạng dòng nộp cuối cùng
    p1-19    7  (siglip2) · 8 (clip) · 18 (meta)  85
    p1-22    3  (siglip2) · 3 (meta) · 11 (asr)   38

Video đúng đã nằm sẵn top-10 ở tầng nhánh; chỉ tầng hợp nhất làm mất. Đây đúng
là điều post-mortem đợt 1 mục 2.2c đã ghi: "chọn video và định vị frame là hai
việc khác nhau, cần tín hiệu khác nhau".

===== Công thức =====
    score = (1-α)·rrf_chuẩn_hoá(keyframe) + α·vote_chuẩn_hoá(video)

    vote(v) = Σ_nhánh Σ_dòng≤CAP  w_nhánh / (RRF_K + hạng)

`vote` cộng dồn MỌI bằng chứng của một video nên thưởng video có nhiều cảnh
khớp; `rrf` giữ nguyên độ nhạy với một cảnh khớp mạnh. Chuẩn hoá về [0,1] theo
max TRONG TỪNG TRUY VẤN vì hai đại lượng khác thang — cộng thô là cộng nhầm.

===== Vì sao có CAP =====
Không chặn thì video dài (nhiều keyframe trong pool) thắng bằng số lượng chứ
không bằng độ khớp. CAP=100 nghĩa là mỗi nhánh chỉ được bỏ phiếu bằng 100 dòng
đầu. Đo được: bỏ CAP thì top-10 tụt 0,90 -> 0,80.

===== Số đo chọn tham số (p1, 20 câu, pool 1500, bản dịch đóng băng) =====
    α       0,0     0,4     0,5    0,6*    0,7     0,8     1,0
    top-10  0,90    0,90    0,90   0,90    0,90    0,85    0,75
    top-50  0,90    0,95    0,95   1,00    1,00    1,00    1,00
    top-5   0,75    0,80    0,80   0,65    0,60    0,60    0,60

α=0,6 là mép TRÁI của vùng đạt top-50=1,00 — chọn mép trái để giữ được nhiều
nhất phần đầu bảng, vì R@1+R@5 chiếm 40% điểm BTC.

⚠️ Tuning trên 20 câu. Vùng α∈[0,6; 0,7] cho cùng kết quả nên không phải một
điểm nhọn, nhưng vẫn phải xác nhận trên holdout p2 trước khi tin.

===== Nút quay đầu =====
    ENABLED = False   -> tắt hoàn toàn, search trở về hành vi trước bản vá
"""
from __future__ import annotations

ENABLED = False

# Trọng số của phiếu bầu mức video trong điểm cuối. 0 = tắt, 1 = chỉ dùng phiếu.
ALPHA = 0.5

# Mỗi nhánh chỉ được bỏ phiếu bằng CAP dòng đầu tiên của nó.
VOTE_CAP = 100

# Số dòng ĐẦU BẢNG được giữ nguyên theo điểm chất lượng, không bị xen kẽ đụng
# vào. Post-mortem đợt 1 mục 2.2a: đầu bảng đắt hơn phần đuôi rất nhiều.
GIU_DAU = 5

# Trọng số của tín hiệu "hạng xuất hiện đầu tiên" so với tín hiệu cộng dồn.
# Hai thứ đã chuẩn hoá riêng về [0,1] trước khi trộn.
BEST_MIX = 4.0
