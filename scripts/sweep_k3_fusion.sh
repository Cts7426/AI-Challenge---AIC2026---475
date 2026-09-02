#!/usr/bin/env bash
# R3.K3 — quét hợp nhất khi có HAI nhánh vector.
#
# Thứ tự bắt buộc (BUILD_TASKS R3.K3): quét RRF_K trước, CỐ ĐỊNH, rồi mới quét
# BRANCH_WEIGHTS. Đổi hai thứ cùng lúc thì không quy được kết quả cho cái nào —
# đúng lỗi review 28/08 đã ghi.
#
# RRF_K=7 được chọn hồi chỉ có MỘT nhánh vector. Thêm nhánh thứ hai là đổi số
# lượng phiếu bầu, nên K tối ưu gần như chắc chắn đổi theo.
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PY:-$HOME/miniforge3/bin/python}"
EN="${EN:-dev_set/ground_truth/official_r1r2.en.manual.json}"
OUT="${OUT:-dev_set/results/run_20260902_k3_fusion}"
MULT="${MULT:-15}"
mkdir -p "$OUT"

for K in 3 5 7 10 15 20 30 60; do
  echo "=================== RRF_K=${K} · dual vector · pool=$((100 * MULT)) ==========="
  VECTOR_BACKEND=clip "$PY" -m dev_set.tools.eval_official \
    --part p1 --min-confidence MEDIUM --task KIS \
    --query-en "$EN" --dual-vector --candidate-multiplier "$MULT" --rrf-k "$K" \
    --out "${OUT}/k${K}.json"
done

echo
echo "Xong. Artefact ở ${OUT}/"
