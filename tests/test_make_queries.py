"""Đường nhập gói đề chính thức: giữ nguyên tên file và metadata TRAKE."""

from __future__ import annotations

import json

from scripts import make_queries as M


def _official_txt_package(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    for name in (
        "query-1-kis.txt", "query-2-kis.txt",
        "query-3-qa.txt", "query-4-trake.txt",
    ):
        (tmp_path / name).write_text(f"nội dung {name}", encoding="utf-8")
    return tmp_path


def test_doc_thu_muc_giu_nguyen_ten_file_va_task(tmp_path):
    rows = M.doc_goi_de(_official_txt_package(tmp_path), None)
    assert [row["query_id"] for row in rows] == [
        "query-1-kis", "query-2-kis", "query-3-qa", "query-4-trake",
    ]
    assert [row["task_type"] for row in rows] == ["KIS", "KIS", "QA", "TRAKE"]
    assert any("query-4-trake" in error and "n_events" in error for error in M.kiem(rows))


def test_doc_mot_txt_khong_hut_nham_file_cung_thu_muc(tmp_path):
    package = _official_txt_package(tmp_path)
    rows = M.doc_goi_de(package / "query-3-qa.txt", None)
    assert [row["query_id"] for row in rows] == ["query-3-qa"]


def test_cli_n_events_ghi_jsonl_dung_schema(tmp_path, monkeypatch):
    package = _official_txt_package(tmp_path / "de")
    out = tmp_path / "queries.jsonl"
    monkeypatch.setattr(M.sys, "argv", [
        "make_queries.py", str(package), "--out", str(out),
        "--n-events", "query-4-trake=4",
    ])
    assert M.main() == 0
    rows = [json.loads(line) for line in out.read_text("utf-8").splitlines()]
    assert rows[-1] == {
        "query_id": "query-4-trake",
        "task_type": "TRAKE",
        "query_vi": "nội dung query-4-trake.txt",
        "n_events": 4,
    }


def test_json_event_descs_tuong_minh_tu_derive_n_events_va_preview(tmp_path, capsys):
    source = tmp_path / "de.json"
    source.write_text(json.dumps([{
        "query_id": "query-4-trake", "task_type": "TRAKE", "query_vi": "a rồi b",
        "event_descs": ["a", "b"],
    }], ensure_ascii=False), encoding="utf-8")
    [row] = M.doc_goi_de(source, None)
    assert row["n_events"] == 2 and M.kiem([row]) == []
    M.in_bang([row])
    preview = capsys.readouterr().out
    assert "events" in preview and "query-4-trake" in preview


def test_hau_to_chinh_thuc_khong_khop_task_thi_loi():
    rows = [{
        "query_id": "query-4-trake", "task_type": "QA", "query_vi": "x",
    }]
    assert any("hậu tố tên file là TRAKE" in error for error in M.kiem(rows))
