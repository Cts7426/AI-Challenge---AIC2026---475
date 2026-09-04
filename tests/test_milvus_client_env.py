"""Milvus adapter không được thay đổi cấu hình process khi chỉ được import."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_KEYS = ("LLM_BACKEND", "LLM_API_MODEL", "GEMINI_API_KEY")


def test_import_search_khong_tu_nap_dotenv_qua_pymilvus(tmp_path) -> None:
    """Import production search không được làm fingerprint/model đổi giữa run."""
    (tmp_path / ".env").write_text(
        "LLM_BACKEND=api\n"
        "LLM_API_MODEL=model-khong-duoc-tu-nap\n"
        "GEMINI_API_KEY=secret-khong-duoc-tu-nap\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    for key in RUNTIME_KEYS:
        env.pop(key, None)
    env["PYTHONPATH"] = str(REPO_ROOT)
    script = (
        "import json, os; "
        "import backend.retrieval.search; "
        f"print(json.dumps({{key: os.environ.get(key) for key in {RUNTIME_KEYS!r}}}))"
    )

    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {key: None for key in RUNTIME_KEYS}
