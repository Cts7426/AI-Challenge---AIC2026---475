"""Digest scorer phải đổi khi bất kỳ dependency định nghĩa điểm nào đổi."""

from __future__ import annotations

from pathlib import Path


def test_scorer_contract_digest_bao_phu_answer_match_va_policy(tmp_path):
    from dev_set.tools.scorer_contract import scorer_contract_sha256

    paths = (
        "dev_set/tools/scoring.py",
        "backend/common/answer_match.py",
        "data/config/qa_evaluation.py",
    )
    for relative in paths:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {relative}\n", encoding="utf-8")

    original = scorer_contract_sha256(root=tmp_path)
    dependency = tmp_path / "backend/common/answer_match.py"
    dependency.write_text("# semantic behavior changed\n", encoding="utf-8")

    assert scorer_contract_sha256(root=tmp_path) != original
