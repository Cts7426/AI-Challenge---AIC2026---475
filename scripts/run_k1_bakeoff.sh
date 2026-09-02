#!/usr/bin/env bash
# Chạy các arm của bake-off encoder R3.K1.
#
# Vì sao là script chứ không phải lệnh gõ tay: ba arm phải khác nhau ĐÚNG một
# biến (VECTOR_BACKEND). Gõ tay ba lần là ba cơ hội để lệch một cờ mà không ai
# nhận ra, rồi báo cáo một chênh lệch không phải do encoder.
set -euo pipefail

cd "$(dirname "$0")/.."

PY="${PY:-$HOME/miniforge3/bin/python}"
EN="${EN:-dev_set/ground_truth/official_r1r2.en.manual.json}"
OUT="${OUT:-dev_set/results/run_20260902_k1_bakeoff}"
mkdir -p "$OUT"

chay() {   # $1 = ten arm · $2 = VECTOR_BACKEND · $3.. = cờ nguồn query_en
  local ten="$1" backend="$2"; shift 2
  echo "=================== ARM ${ten} · VECTOR_BACKEND=${backend} ==================="
  VECTOR_BACKEND="$backend" "$PY" -m dev_set.tools.eval_official \
    --part p1 --min-confidence MEDIUM --task KIS \
    "$@" --out "${OUT}/arm_${ten}.json"
}

chay a_clip_en    clip    --query-en "$EN"
chay b_siglip2_en siglip2 --query-en "$EN"
chay c_siglip2_vi siglip2 --query-en-vi

echo
echo "Xong. Artefact ở ${OUT}/"

# --- Đợt đo thứ hai: pool sâu hơn (CANDIDATE_MULTIPLIER=15) -------------------
# Đo 02/09 cho thấy pool 500/nhánh cắt cụt phiếu bầu RRF: câu p1-23 nhảy từ
# "không tìm thấy" lên hạng 1 khi nới pool. Chạy lại đúng hai arm với một biến
# duy nhất đổi thêm, để tách phần thắng của độ sâu khỏi phần thắng của encoder.
if [ "${SAU:-0}" = "1" ]; then
  chay a_clip_en_m15    clip    --query-en "$EN" --candidate-multiplier 15
  chay b_siglip2_en_m15 siglip2 --query-en "$EN" --candidate-multiplier 15
fi
