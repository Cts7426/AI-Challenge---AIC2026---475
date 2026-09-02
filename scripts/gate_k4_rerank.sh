#!/usr/bin/env bash
# R3.K4 — cổng chặn cho tầng rerank top-50.
#
# 🔒 Cổng (BUILD_TASKS): R@1 mức video trên `--part p1 --min-confidence MEDIUM`
# phải ≥ 0,25. Không đạt thì TẮT tầng này — rerank sai còn tệ hơn không có, vì
# nó đẩy đáp án đúng xuống dưới.
#
# Hai lượt chạy khác nhau ĐÚNG một biến: bật/tắt rerank. Mọi thứ khác (encoder,
# pool, bảng slot, bản dịch) giữ y nguyên.
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PY:-$HOME/miniforge3/bin/python}"
EN="${EN:-dev_set/ground_truth/official_r1r2.en.manual.json}"
OUT="${OUT:-dev_set/results/run_20260902_k4_rerank}"
mkdir -p "$OUT"

chay() {
  local ten="$1"; shift
  echo "=================== rerank ${ten} ==================="
  VECTOR_BACKEND=clip "$PY" -m dev_set.tools.eval_official \
    --part p1 --min-confidence MEDIUM --task KIS \
    --query-en "$EN" --dual-vector --candidate-multiplier 15 \
    "$@" --out "${OUT}/rerank_${ten}.json"
}

chay tat
chay bat --rerank

echo
echo "Xong. Artefact ở ${OUT}/"
