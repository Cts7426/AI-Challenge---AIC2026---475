"""Một lệnh trả lời đúng một câu: HIỆN GIỜ CÒN THIẾU GÌ ĐỂ COI LÀ XONG?

Vì sao cần: "xong sạch sẽ" phải là thứ MÁY đọc được, không phải cảm giác. Repo
này đã có sẵn ba thước đo thật (test suite, preflight, promotion gate) nhưng
nằm rải ba chỗ, phải nhớ mới chạy. Script gom cả ba, in một bảng, và exit != 0
khi còn việc — nên vòng lặp tự động biết khi nào được dừng.

Script CHỈ ĐỌC: không sửa file, không gọi LLM, không đụng index. Chạy lại bao
nhiêu lần cũng ra cùng kết quả trên cùng trạng thái repo.

Chạy:
    .venv/bin/python3.14 scripts/selfcheck.py
    .venv/bin/python3.14 scripts/selfcheck.py --skip-preflight   # nhanh, khỏi cần Docker
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PY = sys.executable


@dataclass
class Check:
    """Một phép kiểm: `ok` quyết định exit code, `detail` để người đọc hiểu."""

    name: str
    ok: bool
    detail: str


def _run(cmd: list[str], timeout: int = 600) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd, cwd=REPO, capture_output=True, text=True, timeout=timeout,
        )
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, f"quá {timeout}s không xong"
    except Exception as error:  # noqa: BLE001 — selfcheck không được tự crash
        return 1, f"{type(error).__name__}: {error}"


def check_tests() -> Check:
    code, out = _run([PY, "-m", "pytest", "tests", "dev_set/tests", "-q"])
    summary = ""
    for line in out.splitlines():
        if "passed" in line or "failed" in line or "error" in line.lower():
            summary = line.strip()
    return Check("Test suite", code == 0, summary or "không đọc được kết quả")


def check_preflight() -> Check:
    code, out = _run([PY, "scripts/preflight_check.py", "--profile", "development"])
    summary = ""
    for line in out.splitlines():
        if line.startswith("ĐẠT ") and "HỎNG" in line:
            summary = line.strip()
    return Check("Preflight (development)", code == 0, summary or "không đọc được kết quả")


def check_ground_truth() -> Check:
    """GT verified là điều kiện CẦN của promotion gate — kiểm riêng cho rõ."""
    manifest_path = REPO / "dev_set/manifests/batch1_holdout13.json"
    if not manifest_path.exists():
        return Check("Ground truth (holdout13)", False, "thiếu manifest")

    entries = json.loads(manifest_path.read_text(encoding="utf-8"))["entries"]
    verified = [e["query_id"] for e in entries if e.get("verification_status") == "verified"]
    pending = [e["query_id"] for e in entries if e.get("verification_status") != "verified"]

    if not pending:
        return Check("Ground truth (holdout13)", True, f"{len(verified)}/{len(entries)} verified")
    return Check(
        "Ground truth (holdout13)",
        False,
        f"{len(verified)}/{len(entries)} verified — còn: {', '.join(pending)}",
    )


def check_regression_gt() -> Check:
    """25 câu vòng 1: manifest đã đóng băng nhưng GT có thể chưa tồn tại."""
    manifest_path = REPO / "dev_set/manifests/batch1_round1_queries.json"
    if not manifest_path.exists():
        return Check("Ground truth (round1 25 câu)", False, "thiếu manifest")

    queries = json.loads(manifest_path.read_text(encoding="utf-8"))["queries"]
    has_gt = any(q.get("ground_truth_sha256") for q in queries)
    if not has_gt:
        return Check(
            "Ground truth (round1 25 câu)",
            False,
            f"0/{len(queries)} có GT — chưa điều tra đáp án đúng câu nào",
        )
    verified = sum(1 for q in queries if q.get("verification_status") == "verified")
    return Check(
        "Ground truth (round1 25 câu)",
        verified == len(queries),
        f"{verified}/{len(queries)} verified",
    )


def check_llm_backend() -> Check:
    """Bước dịch VI→EN đi qua llm(); backend chết thì KIS hỏng âm thầm, không crash."""
    import os

    backend = os.environ.get("LLM_BACKEND", "api")
    if backend == "api" and not os.environ.get("ANTHROPIC_API_KEY"):
        detail = "LLM_BACKEND=api nhưng thiếu ANTHROPIC_API_KEY"
        return Check("LLM backend", False, detail)
    if backend == "gemini" and not os.environ.get("GEMINI_API_KEY"):
        return Check("LLM backend", False, "LLM_BACKEND=gemini nhưng thiếu GEMINI_API_KEY")
    # Có key không đồng nghĩa còn credit — chỉ khẳng định được cấu hình có mặt.
    return Check("LLM backend", True, f"LLM_BACKEND={backend} (cấu hình có mặt; credit KHÔNG kiểm ở đây)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--skip-preflight", action="store_true", help="bỏ qua preflight (khỏi cần Docker)")
    args = parser.parse_args()

    checks = [check_tests()]
    if not args.skip_preflight:
        checks.append(check_preflight())
    checks += [
        check_ground_truth(),
        check_regression_gt(),
        check_llm_backend(),
    ]

    width = max(len(c.name) for c in checks)
    print()
    print("=" * 72)
    print("SELFCHECK — còn thiếu gì để coi là xong")
    print("=" * 72)
    for check in checks:
        mark = "ĐẠT".ljust(5) if check.ok else "THIẾU"
        print(f"  {mark}  {check.name.ljust(width)}  {check.detail}")
    print("=" * 72)

    failed = [c for c in checks if not c.ok]
    if not failed:
        print("Không còn mục nào thiếu.")
        return 0
    print(f"Còn {len(failed)} mục chưa xong:")
    for check in failed:
        print(f"  - {check.name}: {check.detail}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
