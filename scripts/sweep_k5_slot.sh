#!/usr/bin/env bash
# R3.K5 — cân lại SLOT_BUDGET trên cấu hình ranking MỚI.
#
# Bảng hiện hành [(1,2),(2,2),(94,1)] chọn ngày 20/08 vì lúc đó ranking kém: shot
# đúng hay rơi vào hạng 80–95, nên phủ rộng thắng đào sâu. Cấu hình K3 (hai nhánh
# vector + pool 1500) đưa R@1 mức video lên 0,55 và R@100 lên 1,00 — giả định
# "ranking kém" không còn đúng, nên phải đo lại chứ không suy diễn.
#
# Chạy ở CẢ BA dung sai ±5/±15/±40: độ rộng cửa sổ [s,e] của BTC vẫn chưa được
# công bố. Bảng nào chỉ thắng ở ±40 là đang mua điểm bằng rải rộng, không phải
# định vị đúng hơn — không chọn.
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PY:-$HOME/miniforge3/bin/python}"
EN="${EN:-dev_set/ground_truth/official_r1r2.en.manual.json}"
OUT="${OUT:-dev_set/results/run_20260902_k5_slot}"
mkdir -p "$OUT"

# ten            bảng (mỗi ô: số_shot x số_slot, tổng phải bằng 100)
chay() {
  local ten="$1" bang="$2"
  echo "=================== ${ten}  ${bang} ==================="
  VECTOR_BACKEND=clip "$PY" -m dev_set.tools.eval_official \
    --part p1 --min-confidence MEDIUM --task KIS \
    --query-en "$EN" --dual-vector --candidate-multiplier 15 \
    --slot-budget "$bang" --tolerances 5,15,40 \
    --out "${OUT}/${ten}.json"
}

chay rong_hien_hanh  "1x2,2x2,94x1"          # bảng đang chạy — nền so sánh
chay sau_buildtasks  "1x8,4x4,10x2,56x1"     # bảng BUILD_TASKS đề nghị
chay sau_vua         "1x4,4x3,12x2,60x1"     # trung dung giữa hai bảng trên
chay sau_manh        "1x12,4x6,8x4,32x1"     # cược mạnh vào hạng đầu
chay phu_tron        "100x1"                 # rải tuyệt đối — trần của "phủ rộng"

echo
echo "Xong. Artefact ở ${OUT}/"
