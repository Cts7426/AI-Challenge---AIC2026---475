"""Ghi quyết định xác minh tay của một câu trong manifest đã đóng băng.

Vì sao cần một lệnh riêng thay vì sửa JSONL bằng tay: `verification_status`,
`provenance`, `verified_by`, `verified_at` phải khớp Y HỆT giữa GT record
(`dev_set/ground_truth/*.jsonl`) và entry tương ứng trong manifest — khớp cả
`ground_truth_sha256` được băm lại từ chính record đó
(`dev_set/tools/run_evaluation.py::_load_frozen_inputs`). Sửa tay một trong
hai chỗ mà quên chỗ kia sẽ làm evaluator crash ngay khi nạp frozen set (bug
thật đã gặp — xem test `test_batch1_holdout13_manifest_loads_against_production_ground_truth`).

Script CHỈ ghi lại quyết định người dùng đã tự xem — không tự đoán đúng/sai,
không tự đổi frame_start/frame_end/answer_text.

Chạy:
    python -m dev_set.tools.mark_verified --manifest batch1_holdout13 \
        --query-id KIS_001 --status verified --by "Cong Ly"

    python -m dev_set.tools.mark_verified --manifest batch1_holdout13 \
        --query-id KIS_002 --status unknown --by "Cong Ly" \
        --note "video đúng nhưng cửa sổ frame lệch ~40 frame, để lại unknown"
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from dev_set.tools.promotion_provenance import ground_truth_record_sha256
from dev_set.tools.schema import GroundTruthKIS, GroundTruthQA, GroundTruthTRAKE

REPO = Path(__file__).resolve().parents[2]
MANIFEST_DIR = REPO / "dev_set/manifests"
GT_DIR = REPO / "dev_set/ground_truth"

_GT_CLASS = {"KIS": GroundTruthKIS, "QA": GroundTruthQA, "TRAKE": GroundTruthTRAKE}

# manifest_id -> GT jsonl mặc định, giống default trong _load_frozen_inputs().
_DEFAULT_GT_PATH = {
    "batch1_holdout13": GT_DIR / "holdout_gt.jsonl",
}


def _load_jsonl(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", required=True, help="tên manifest, vd: batch1_holdout13")
    parser.add_argument("--ground-truth", type=Path, default=None, help="override GT path (bắt buộc cho manifest ngoài holdout)")
    parser.add_argument("--query-id", required=True)
    # schema.py chỉ định nghĩa Literal["unknown", "verified"] cho verification_status
    # (xem GroundTruthKIS/QA/TRAKE) — không có "rejected". Câu bị bác GT vẫn ghi
    # "unknown" kèm --note giải thích lý do, đúng cách dùng đã mô tả ở docstring trên.
    parser.add_argument("--status", required=True, choices=["verified", "unknown"])
    parser.add_argument("--by", required=True, help="tên người xác nhận")
    parser.add_argument("--note", default=None, help="ghi chú ngắn, gộp vào provenance")
    args = parser.parse_args()

    manifest_path = MANIFEST_DIR / f"{args.manifest}.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries_by_id = {e["query_id"]: e for e in manifest["entries"]}
    if args.query_id not in entries_by_id:
        parser.error(f"{args.query_id} không có trong {manifest_path}")
    entry = entries_by_id[args.query_id]

    gt_path = args.ground_truth or _DEFAULT_GT_PATH.get(args.manifest)
    if gt_path is None:
        parser.error(f"manifest '{args.manifest}' không có GT mặc định, cần --ground-truth")

    gt_rows = _load_jsonl(gt_path)
    gt_by_id = {row["query_id"]: row for row in gt_rows}
    if args.query_id not in gt_by_id:
        parser.error(f"{args.query_id} không có trong {gt_path}")
    row = gt_by_id[args.query_id]

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    provenance = f"human-review://{args.manifest}/{args.by}"
    if args.note:
        provenance += f" — {args.note}"

    row["verification_status"] = args.status
    row["provenance"] = provenance
    row["verified_by"] = args.by
    row["verified_at"] = now

    task_type = row["task_type"]
    parsed = _GT_CLASS[task_type](**{k: v for k, v in row.items() if k != "task_type"})
    gt_hash = ground_truth_record_sha256(parsed)

    entry["verification_status"] = args.status
    entry["provenance"] = provenance
    entry["verified_by"] = args.by
    entry["verified_at"] = now
    entry["ground_truth_sha256"] = gt_hash

    _write_jsonl(gt_path, gt_rows)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(f"Đã ghi {args.query_id} -> {args.status} (by={args.by}, at={now}) trong {gt_path.name} + {manifest_path.name}")


if __name__ == "__main__":
    main()
