"""Trang review phải giữ đúng đáp án QA và thứ tự sự kiện TRAKE."""

from __future__ import annotations

from scripts.make_qa_trake_review import render_page


def test_render_page_hien_qa_va_day_du_su_kien_trake():
    """Một trang phải hiện đáp án QA và ghép đúng từng frame với từng sự kiện."""
    items = [
        {
            "query_id": "q-qa",
            "task_type": "QA",
            "video_id": "L30_V047",
            "frame_ids": [4911],
            "answer_text": "5",
            "status": "confirmed",
            "note": "đã đối chiếu",
        },
        {
            "query_id": "q-trake",
            "task_type": "TRAKE",
            "video_id": "L26_V156",
            "frame_ids": [3200, 3765],
            "event_descs": ["trộn nước xốt", "cắt đầu tôm"],
            "status": "needs_review",
            "note": "cần soi video dày",
        },
    ]
    queries = {
        "q-qa": "Bé gái sắp lên lớp mấy?",
        "q-trake": "Món tôm với nước cam.",
    }

    def context_provider(video_id: str, frame_id: int):
        return [
            {
                "url": f"/assets/{video_id}-{frame_id}.jpg",
                "mapped_frame": frame_id,
                "keyframe_id": f"{video_id}#k0001",
                "offset": 0,
            }
        ]

    page = render_page(items, queries, context_provider)

    assert "Bé gái sắp lên lớp mấy?" in page
    assert "Đáp án đề xuất: <strong>5</strong>" in page
    assert "E1 · trộn nước xốt" in page
    assert "E2 · cắt đầu tôm" in page
    assert "frame mục tiêu 3200" in page
    assert "frame mục tiêu 3765" in page
    assert "/assets/L26_V156-3765.jpg" in page


def test_render_page_tu_choi_trake_lech_so_su_kien():
    """Lệch số frame/sự kiện phải dừng, vì TRAKE chấm theo đúng vị trí."""
    items = [{
        "query_id": "q-trake",
        "task_type": "TRAKE",
        "video_id": "L26_V156",
        "frame_ids": [3200],
        "event_descs": ["E1", "E2"],
        "status": "needs_review",
    }]

    try:
        render_page(items, {"q-trake": "mô tả"}, lambda _v, _f: [])
    except ValueError as exc:
        assert "số frame khác số sự kiện" in str(exc)
    else:
        raise AssertionError("TRAKE lệch số sự kiện không bị từ chối")
