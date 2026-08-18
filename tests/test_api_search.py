# tests/test_api_search.py — POST /search: nhánh QA phải trả dict như KIS/TRAKE
#
# SỬA 18/08 — bug NGHIÊM TRỌNG tìm được qua code review của Lý (commit 638495d):
# nhánh TRAKE của post_search() được chuyển sang trả list[dict] đúng chuẩn khối
# dựng `hits` dùng chung, nhánh QA thì QUÊN — vẫn gán thẳng list[ShotHit] (dataclass
# 3 trường, không subscriptable) vào `results`. Khối dựng `hits` bên dưới đọc
# `r["keyframe_id"]` kiểu dict → TypeError với MỌI truy vấn QA, và lỗi đó nằm
# NGOÀI try/except (chỉ bọc phần gọi pipeline) nên bay thẳng thành 500 trần trụi,
# không phải 400/503 có thông báo như các lỗi khác của endpoint này.
#
# Test dùng TestClient thật của FastAPI, mock thẳng qa_pipeline() (không cần
# ES/Milvus/LLM) — chỉ đo hành vi của post_search(), không đo qa_pipeline().

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

import backend.api.main as main_mod
from backend.slot import ShotHit


def _client() -> TestClient:
    return TestClient(main_mod.app, raise_server_exceptions=False)


def test_qa_search_khong_500_khi_qa_pipeline_thanh_cong(real_videos):
    """Bằng chứng trực tiếp của bug: mock qa_pipeline() trả đúng kiểu thật nó
    trả (list[ShotHit], str) — trước bản sửa, dòng này luôn ra 500."""
    vid = real_videos[0][0]
    from backend.slot.allocator import _shots

    shot_id = next(iter(_shots()))
    fake_shots = [ShotHit(shot_id, 0.9, None)]

    with patch("backend.tasks.qa.qa_pipeline", return_value=(fake_shots, "400g")):
        resp = _client().post(
            "/search",
            json={"query": "câu hỏi bất kỳ", "task_type": "QA", "query_en": "any question"},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["answer_text"] == "400g"
    assert len(body["hits"]) == 1
    assert body["hits"][0]["shot_id"] == shot_id
    # video_id KHÔNG có trong ShotHit — phải được post_search() tự tra qua
    # shot_bounds(), không phải bịa hay để trống.
    assert body["hits"][0]["video_id"]


def test_qa_search_giu_dung_thu_hang_shot(real_videos):
    """Thứ tự shot qa_pipeline() trả (đã đẩy shot thắng lên hạng 1, xem
    backend/tasks/qa.py::_dua_len_dau) phải giữ nguyên tới response — người
    thao tác chọn top-5 dựa trên thứ tự này."""
    from backend.slot.allocator import _shots

    shot_ids = list(_shots())[:3]
    fake_shots = [ShotHit(sid, 1.0 - i * 0.1, None) for i, sid in enumerate(shot_ids)]

    with patch("backend.tasks.qa.qa_pipeline", return_value=(fake_shots, "câu trả lời")):
        resp = _client().post(
            "/search", json={"query": "q", "task_type": "QA", "query_en": "q"},
        )
    assert resp.status_code == 200, resp.text
    got_shot_ids = [h["shot_id"] for h in resp.json()["hits"]]
    assert got_shot_ids == shot_ids
