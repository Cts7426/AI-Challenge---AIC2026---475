#!/usr/bin/env bash
# A/B cấu hình Đợt 2 (cũ) vs Đợt 3 (mới) — phân xử "tune đúng" hay "học thuộc p1".
#
# ===== Câu hỏi cần trả lời =====
# Chiến dịch Đợt 3 tune toàn bộ trên 20 câu p1 và đạt Final mức video 0,80.
# Trên holdout p2 (19 câu, chưa từng mở) cùng cấu hình đó chỉ được 0,6421.
# Hai cách giải thích, chưa phân biệt được:
#     (a) cấu hình Đợt 3 overfit lên 20 câu p1
#     (b) p2 vốn khó hơn p1, cấu hình nào cũng tụt
# Cách duy nhất phân biệt: chạy cấu hình CŨ trên CHÍNH p2. Nếu cũ >= mới thì (a),
# phải lùi trước Đợt 3. Nếu cũ < mới thì (b), giữ nguyên và yên tâm.
#
# ===== Ba arm =====
#   dot2   cấu hình Đợt 2 nguyên bản: MỘT nhánh vector, pool 500, không probe,
#          không rerank, bảng slot phủ rộng 1x2,2x2,94x1
#   dot3   cấu hình đang chạy: HAI nhánh vector, pool 1500, probe, rerank,
#          bảng slot 50x2
#   dot3_slotcu  giống dot3 nhưng trả bảng slot về bản cũ — tách riêng đóng góp
#          của BẢNG SLOT khỏi đóng góp của RETRIEVAL. Bảng slot là thứ dễ overfit
#          nhất vì nó được chọn thuần theo cột frame của p1.
#
# ⚠️ Chỉ ba arm, chọn TRƯỚC khi nhìn kết quả. Đây là phép CHỌN GIỮA HAI CẤU HÌNH
# ĐÃ ĐÓNG BĂNG, không phải quét tham số. Quét trên holdout là biến holdout thành
# tune set và mất luôn thứ duy nhất còn ước lượng được năng lực thật.
#
# Chạy:  bash scripts/ab_dot2_vs_dot3.sh p1     # miễn phí, tập đã tune
#        bash scripts/ab_dot2_vs_dot3.sh p2     # TIÊU LƯỢT HOLDOUT
set -euo pipefail

PART="${1:-p1}"
PY="${PY:-.venv/bin/python}"
EN="dev_set/ground_truth/official_r1r2.en.json"
OUT="dev_set/results/run_20260903_ab_${PART}"
SLOT_CU="1x2,2x2,94x1"

mkdir -p "$OUT"
HOLDOUT=()   # rỗng khi chạy p1; xem ghi chú bash 3.2 ở dưới
if [ "$PART" = "p2" ]; then
  HOLDOUT=(--i-am-spending-a-holdout-run)
  echo "⚠️  ĐANG TIÊU LƯỢT HOLDOUT — xem dev_set/holdout_log.md"
fi

chung=(--part "$PART" --task KIS --min-confidence MEDIUM --query-en "$EN")

echo "=== arm dot2 — cấu hình Đợt 2 nguyên bản ==="
VECTOR_BACKEND=clip "$PY" -u -m dev_set.tools.eval_official "${chung[@]}" \
  --candidate-multiplier 5 --no-ocr-probe --no-rerank --slot-budget "$SLOT_CU" \
  ${HOLDOUT[@]+"${HOLDOUT[@]}"} --out "$OUT/dot2.json"

echo "=== arm dot3 — cấu hình đang chạy ==="
VECTOR_BACKEND=clip "$PY" -u -m dev_set.tools.eval_official "${chung[@]}" \
  --dual-vector --candidate-multiplier 15 \
  ${HOLDOUT[@]+"${HOLDOUT[@]}"} --out "$OUT/dot3.json"

echo "=== arm dot3_slotcu — retrieval mới, bảng slot cũ ==="
VECTOR_BACKEND=clip "$PY" -u -m dev_set.tools.eval_official "${chung[@]}" \
  --dual-vector --candidate-multiplier 15 --slot-budget "$SLOT_CU" \
  ${HOLDOUT[@]+"${HOLDOUT[@]}"} --out "$OUT/dot3_slotcu.json"

echo
echo "Xong → $OUT"
