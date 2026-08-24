"""Băm toàn bộ code/policy định nghĩa điểm để artefact không ghép nhầm scorer."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


SCORER_CONTRACT_PATHS = (
    "dev_set/tools/scoring.py",
    "backend/common/answer_match.py",
    "data/config/qa_evaluation.py",
)


def scorer_contract_sha256(*, root: Path | None = None) -> str:
    """Hash canonical path -> file digest của mọi dependency ảnh hưởng scoring."""
    repository = root or Path(__file__).resolve().parents[2]
    sources = {
        relative: hashlib.sha256((repository / relative).read_bytes()).hexdigest()
        for relative in SCORER_CONTRACT_PATHS
    }
    canonical = json.dumps(
        sources, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
