"""Kiểm bộ chuyển bộ đề BTC (.txt mỗi câu) → JSONL cho run.py.

Lỗi ở tầng này là lỗi IM LẶNG: file vẫn ghi ra, run.py vẫn chạy, chỉ có nội
dung truy vấn gửi cho LLM/CLIP là bẩn. Nên phải test bằng đúng định dạng BTC
phát ở Đợt 3 (`E1: ...` có dấu hai chấm).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "txt_to_run_queries",
    Path(__file__).resolve().parents[1] / "scripts" / "txt_to_run_queries.py",
)
mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mod)


def _write(tmp_path: Path, name: str, body: str) -> Path:
    (tmp_path / name).write_text(body, encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize(
    "sep",
    [":", ".", ")", "", " -"],
    ids=["colon", "dot", "paren", "space-only", "dash"],
)
def test_event_separator_khong_lot_vao_mo_ta(tmp_path: Path, sep: str) -> None:
    """`E1: mô tả` → mô tả sạch, KHÔNG còn dấu ngăn cách ở đầu."""
    body = (
        "Con lân màu đỏ đang biểu diễn trên các cột trụ.\n"
        f"E1{sep} Con lân treo hai chân trước vào hai trụ gần cuối.\n"
        f"E2{sep} Khoảnh khắc đầu tiên con lân ngậm một thanh trụ.\n"
    )
    d = _write(tmp_path, "query-p2-34-trake.txt", body)

    (q,) = mod._load_query_dir(d)

    assert q["query_id"] == "query-p2-34-trake"
    assert q["task_type"] == "TRAKE"
    assert q["event_descs"] == [
        "Con lân treo hai chân trước vào hai trụ gần cuối.",
        "Khoảnh khắc đầu tiên con lân ngậm một thanh trụ.",
    ]
    # query_vi gộp lại cũng không được dính dấu ngăn cách lạc
    assert " . : " not in q["query_vi"]
    assert q["query_vi"].startswith("Con lân màu đỏ")


def test_su_kien_nhieu_cau_giu_nguyen_dau_cham_giua_cau(tmp_path: Path) -> None:
    """E3 của câu 21 có 2 câu — chỉ bỏ dấu SAU SỐ, không đụng dấu trong câu."""
    d = _write(
        tmp_path,
        "query-p2-21-trake.txt",
        "Một món ăn làm từ tôm.\n"
        "E1: Khoảnh khắc bắt đầu trộn nước xốt.\n"
        "E3: Người đầu bếp cho tôm ra dĩa. Hãy chọn khoảnh khắc con tôm chạm dĩa.\n",
    )

    (q,) = mod._load_query_dir(d)

    assert q["event_descs"][1] == (
        "Người đầu bếp cho tôm ra dĩa. Hãy chọn khoảnh khắc con tôm chạm dĩa."
    )


def test_dong_khong_phai_su_kien_giu_nguyen(tmp_path: Path) -> None:
    """Đợt 2 BTC dùng `Cảnh 1:` — không khớp `E\d+`, phải giữ NGUYÊN VĂN."""
    d = _write(
        tmp_path,
        "query-p2-8-trake.txt",
        "4 cảnh nối tiếp nhau.\n"
        "Cảnh 1: Hai người dán niêm phong thùng carton.\n"
        "Cảnh 2: Các thùng được xếp ngay ngắn.\n",
    )

    (q,) = mod._load_query_dir(d)

    assert q["event_descs"] == [
        "Cảnh 1: Hai người dán niêm phong thùng carton.",
        "Cảnh 2: Các thùng được xếp ngay ngắn.",
    ]


def test_query_id_dung_y_nguyen_ten_file_btc(tmp_path: Path) -> None:
    """query_id sai = nộp sai tên file = BTC không ghép được điểm."""
    d = _write(tmp_path, "query-p2-14-qa.txt", "Bé gái sắp lên lớp mấy?\n")

    (q,) = mod._load_query_dir(d)

    assert q["query_id"] == "query-p2-14-qa"
    assert q["task_type"] == "QA"
    assert "event_descs" not in q


def test_kis_nhieu_dong_gop_thanh_mot_query(tmp_path: Path) -> None:
    d = _write(tmp_path, "query-p2-1-kis.txt", "Dòng một.\n\nDòng hai.\n")

    (q,) = mod._load_query_dir(d)

    assert q["query_vi"] == "Dòng một. Dòng hai."
