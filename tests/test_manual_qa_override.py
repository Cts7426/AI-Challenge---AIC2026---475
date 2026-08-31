"""Kiểm helper cứu Q&A thủ công vẫn giữ checkpoint và frame-map invariant."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
SCRIPT = REPO_ROOT / "scripts" / "manual_qa_override.py"


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Tạo query/checkpoint tối thiểu; dữ liệu frame thật vẫn đọc từ repo."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    queries = tmp_path / "queries.jsonl"
    queries.write_text(
        json.dumps(
            {
                "query_id": "query-p2-19-qa",
                "task_type": "QA",
                "query_vi": "Quán trọ nằm trên đường nào?",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    checkpoint = out_dir / "checkpoint.jsonl"
    checkpoint.write_text(
        json.dumps(
            {
                "query_id": "query-p2-1-kis",
                "task_type": "KIS",
                "runtime_fingerprint": "fingerprint-test",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    evidence = REPO_ROOT / "data" / "raw" / "btc" / "keyframes" / "L30_V043" / "029.jpg"
    return queries, out_dir, evidence


def _run(tmp_path: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    queries, out_dir, evidence = _fixture(tmp_path)
    return subprocess.run(
        [
            str(PYTHON),
            str(SCRIPT),
            "--queries",
            str(queries),
            "--out",
            str(out_dir),
            "--query-id",
            "query-p2-19-qa",
            "--answer",
            "Lý Thường Kiệt",
            "--video-id",
            "L30_V043",
            "--frame-id",
            "1818",
            "--keyframe-id",
            "L30_V043#k0029",
            "--frame-start",
            "1743",
            "--frame-end",
            "1842",
            "--evidence",
            str(evidence),
            *extra,
        ],
        cwd=REPO_ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


def test_dry_run_khong_sua_checkpoint_va_bao_dung_100_frame(tmp_path: Path):
    """Bắt lỗi helper ghi dữ liệu dù operator chưa truyền --apply."""
    _, out_dir, _ = _fixture(tmp_path)
    before = (out_dir / "checkpoint.jsonl").read_bytes()

    result = _run(tmp_path / "actual")

    assert result.returncode == 0, result.stderr + result.stdout
    summary = json.loads(result.stdout)
    assert summary["mode"] == "dry-run"
    assert summary["n_answers"] == 100
    assert summary["first_frame"] == 1818
    actual_checkpoint = tmp_path / "actual" / "out" / "checkpoint.jsonl"
    assert actual_checkpoint.read_bytes() == before


def test_apply_append_record_va_trace_day_du(tmp_path: Path):
    """Bắt lỗi record thiếu dòng, trùng frame hoặc mất provenance thủ công."""
    result = _run(tmp_path, "--apply")

    assert result.returncode == 0, result.stderr + result.stdout
    out_dir = tmp_path / "out"
    records = [json.loads(line) for line in (out_dir / "checkpoint.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()]
    record = records[-1]
    assert record["query_id"] == "query-p2-19-qa"
    assert record["answer_text"] == "Lý Thường Kiệt"
    assert len(record["answers"]) == 100
    assert record["answers"][0] == {
        "video_id": "L30_V043",
        "frame_ids": [1818],
        "answer_text": "Lý Thường Kiệt",
        "keyframe_id": "L30_V043#k0029",
    }
    assert len({item["frame_ids"][0] for item in record["answers"]}) == 100
    assert record["qa_trace"]["qa_runtime"]["manual_override"] is True
    traces = [json.loads(line) for line in (out_dir / "trace.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()]
    assert traces[-1]["status"] == "success"
    assert traces[-1]["query_id"] == "query-p2-19-qa"


def test_tu_choi_keyframe_va_frame_id_lech_nhau(tmp_path: Path):
    """Bắt đúng lỗi 3740 bị ghép với evidence canonical ở frame 1818."""
    queries, out_dir, evidence = _fixture(tmp_path)
    result = subprocess.run(
        [
            str(PYTHON), str(SCRIPT),
            "--queries", str(queries), "--out", str(out_dir),
            "--query-id", "query-p2-19-qa", "--answer", "Lý Thường Kiệt",
            "--video-id", "L30_V043", "--frame-id", "3740",
            "--keyframe-id", "L30_V043#k0029",
            "--frame-start", "3690", "--frame-end", "3789",
            "--evidence", str(evidence),
        ],
        cwd=REPO_ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "frame_map=1818" in result.stderr
    assert not (out_dir / "trace.jsonl").exists()
