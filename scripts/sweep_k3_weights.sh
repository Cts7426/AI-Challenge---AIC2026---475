#!/usr/bin/env bash
# R3.K3 bước 2 — quét BRANCH_WEIGHTS của nhánh vector THỨ HAI.
#
# Chạy SAU khi đã quét và cố định RRF_K (bước 1 → RRF_K=7, xem
# scripts/sweep_k3_fusion.sh). Đổi hai thứ cùng lúc thì không quy được kết quả
# cho cái nào — luật "một biến mỗi lần" của BUILD_TASKS.
#
# Chỉ quét trọng số của nhánh PHỤ, giữ nhánh chính ở 1,0: RRF chỉ quan tâm TỈ LỆ
# giữa các trọng số, nên quét cả hai chiều là quét lại cùng một không gian hai lần.
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PY:-$HOME/miniforge3/bin/python}"
EN="${EN:-dev_set/ground_truth/official_r1r2.en.manual.json}"
OUT="${OUT:-dev_set/results/run_20260902_k3_weights}"
mkdir -p "$OUT"

for W in 0.4 0.6 0.8 1.0 1.2 1.5; do
  echo "=================== vector_siglip2 = ${W} ==================="
  VECTOR_BACKEND=clip "$PY" -m dev_set.tools.eval_official \
    --part p1 --min-confidence MEDIUM --task KIS \
    --query-en "$EN" --dual-vector --candidate-multiplier 15 --rrf-k 7 \
    --branch-weights "vector_siglip2=${W}" \
    --out "${OUT}/w${W}.json"
done

echo
echo "Xong. Artefact ở ${OUT}/"
