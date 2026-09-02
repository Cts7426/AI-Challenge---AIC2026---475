# data/config/rerank.py — R3.K4: tầng xếp lại top-50
#
# VÌ SAO CÓ TẦNG NÀY: hiện RRF là bước xếp hạng CUỐI CÙNG. Mà 40% điểm nằm ở
# R@1 + R@5 (chấm: hạng 1 = 1,00 · hạng 2–5 = 0,80), nên thứ tự của 5 dòng đầu
# đáng giá hơn mọi thứ khác. Chẩn đoán Đợt 2: 7/19 câu nằm hạng 2–5 — kéo được
# 7 câu đó lên hạng 1 là +0,074 Final mà không cần model mới.
#
# ⚠️ MẶC ĐỊNH TẮT. Cổng R3.K4 (BUILD_TASKS): R@1 mức video trên
# `--part p1 --min-confidence MEDIUM` phải ≥ 0,25. Không đạt thì để nguyên tắt —
# rerank sai còn TỆ HƠN không có, vì nó đẩy đáp án đúng xuống dưới.

# ===== BẬT 02/09 sau khi đo (R3.K4) =====
# `scripts/gate_k4_rerank.sh` · 20 câu KIS p1 · cấu hình K3 · artefact
# `dev_set/results/run_20260902_k4_rerank/`:
#
#              R@1    Final video   f±5    f±15   f±40   độ trễ
#   tắt       0,550     0,8300      0,22   0,26   0,33   0,79 s
#   bật       0,550     0,8300      0,22   0,27   0,37   0,79 s
#
# ⚠️ ĐỌC ĐÚNG: cổng BUILD_TASKS ghi "R@1 mức video ≥ 0,25". Đạt (0,550), nhưng
# con số đó GIỐNG HỆT khi tắt — nó là công của R3.K3 (hai nhánh vector + pool
# sâu), không phải của tầng này. Cổng như đang viết KHÔNG phân biệt được có
# rerank hay không.
# Bằng chứng thật để bật nằm ở mức frame: cải thiện ở ±15 và ±40, không tụt ở
# dung sai nào, độ trễ không đổi. Mức lợi KHIÊM TỐN — nếu buổi thi có bất kỳ
# dấu hiệu lạ nào thì đây là thứ nên tắt đầu tiên (đổi một dòng, không sửa code).
ENABLED = True

# Chỉ xếp lại N dòng đầu. Dòng 51+ giữ nguyên thứ tự RRF.
# Vì sao 50 chứ không phải 100: dưới hạng 50 điểm chỉ còn 0,20, xáo trộn ở đó
# gần như không đổi Final; mà càng nhiều dòng bị xếp lại thì càng nhiều cơ hội
# đẩy nhầm một đáp án đúng ra khỏi top-5.
TOP_N = 50

# ───────────────────────── Trọng số ba tín hiệu ─────────────────────────
# Điểm mới = RRF chuẩn hoá + Σ (trọng số × tín hiệu chuẩn hoá).
# Mọi tín hiệu đều được chuẩn hoá TRONG PHẠM VI MỘT TRUY VẤN rồi mới cộng —
# cosine tuyệt đối vô nghĩa giữa các truy vấn (bất biến 5: cosine CLIP thực tế
# chỉ quanh 0,2–0,3, ngưỡng cứng lọc sạch kết quả đúng).

# Đồng thuận nhánh: một shot được NHIỀU nhánh độc lập đề cử đáng tin hơn shot
# chỉ một nhánh đẩy lên. RRF đã thưởng chuyện này một phần, nhưng theo kiểu cộng
# dồn nghịch đảo hạng — một nhánh xếp hạng 1 vẫn có thể át bốn nhánh xếp hạng 40.
W_CONSENSUS = 0.30

# Cosine thật, chuẩn hoá z-score trong truy vấn: phân biệt "hạng 1 bỏ xa phần
# còn lại" với "hạng 1 chỉ nhỉnh hơn hạng 2 một chút" — thông tin mà thứ hạng
# vứt đi hoàn toàn.
W_COSINE = 0.25

# Hai nhánh vector (encoder khác nhau, không gian khác nhau) CÙNG đề cử một
# keyframe là bằng chứng mạnh hơn hẳn một nhánh đề cử. Đo 02/09: hai encoder bù
# nhau chứ không thay nhau, nên chỗ chúng ĐỒNG Ý đáng được thưởng riêng.
# Bằng 0 khi chỉ chạy một nhánh vector — tín hiệu không tồn tại thì không thưởng.
W_VECTOR_AGREE = 0.20
