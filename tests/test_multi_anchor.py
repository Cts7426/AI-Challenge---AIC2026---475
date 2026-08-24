"""TDD cho KIS multi-anchor; chỉ mock biên LLM/dịch/search/tokenizer."""

from __future__ import annotations

import importlib
import json

import pytest


def _module():
    return importlib.import_module("backend.retrieval.multi_anchor")


def _row(keyframe_id: str = "kf-1", *, shot_id: str = "shot-1") -> dict:
    return {
        "keyframe_id": keyframe_id,
        "video_id": "L01_V001",
        "frame_idx": 120,
        "timestamp_ms": 4000,
        "shot_id": shot_id,
        "score": 0.5,
        "ranks": {"vector": 1},
        "contrib": {"vector": 0.125},
    }


def _multi_plan(module, anchors: list[tuple[str, str]]):
    return module.QueryPlan(
        strategy="multi",
        query_vi="query phức tạp",
        query_en=None,
        anchors=tuple(
            module.QueryAnchor(i, vi, en, 10)
            for i, (vi, en) in enumerate(anchors, 1)
        ),
        ordered=True,
    )


def _fusion_row(video: str, shot: str, keyframe: str, timestamp: int | None) -> dict:
    return {
        "keyframe_id": keyframe,
        "video_id": video,
        "frame_idx": None if timestamp is None else timestamp // 40,
        "timestamp_ms": timestamp,
        "shot_id": shot,
        "score": 99.0,
        "ranks": {"vector": 1},
        "contrib": {"vector": 0.125},
    }


def test_query_ngan_giu_query_en_va_search_dung_mot_lan(monkeypatch):
    """Bắt lỗi multi-anchor làm query đơn bị gọi LLM/dịch hoặc search lặp."""
    module = _module()
    calls: list[tuple[tuple, dict]] = []

    monkeypatch.setattr(
        module,
        "llm",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("không được gọi LLM")),
    )
    monkeypatch.setattr(
        module,
        "translate",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("không được dịch lại")),
    )

    def fake_search(*args, **kwargs):
        calls.append((args, kwargs))
        return [_row()]

    monkeypatch.setattr(module, "search", fake_search)

    plan = module.plan_query("xe máy qua ngã tư", "motorcycle at an intersection")
    rows = module.search_multi(plan, top_k=10)

    assert plan.strategy == "single"
    assert rows == [_row()]
    assert calls == [
        (("xe máy qua ngã tư",), {
            "query_en": "motorcycle at an intersection",
            "top_k": 10,
            "group_by_shot": True,
        })
    ]


def test_planner_loi_fallback_single_va_search_dung_mot_lan(monkeypatch):
    """Bắt lỗi provider chết làm query KIS phức tạp crash hoặc search lặp."""
    module = _module()
    calls = 0
    query_vi = (
        "Một người bước vào cửa hàng rồi nhìn lên bảng giá, sau đó quay sang "
        "nói chuyện với nhân viên đang đứng cạnh quầy thanh toán"
    )

    monkeypatch.setattr(
        module, "llm", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("offline"))
    )

    def fake_search(*args, **kwargs):
        nonlocal calls
        calls += 1
        return [_row()]

    monkeypatch.setattr(module, "search", fake_search)

    plan = module.plan_query(query_vi, "caller translation")
    rows = module.search_multi(plan, top_k=5)

    assert plan.strategy == "single"
    assert plan.fallback_reason == "planner_error"
    assert rows == [_row()]
    assert calls == 1


def test_plan_toi_da_ba_anchor_va_moi_ban_dich_khong_qua_60_token(monkeypatch):
    """Bắt lỗi planner nhận quá ba câu hoặc bỏ kiểm tokenizer CLIP thật."""
    module = _module()
    query_vi = (
        "Người phụ nữ đi vào siêu thị rồi chọn rau ở quầy thực phẩm, sau đó "
        "đặt món hàng lên xe đẩy và tiến về khu vực thanh toán phía trước"
    )
    proposed = [
        "Người phụ nữ đi vào siêu thị",
        "Người phụ nữ chọn rau ở quầy thực phẩm",
        "Người phụ nữ đặt món hàng lên xe đẩy",
        "Người phụ nữ tiến về khu vực thanh toán",
    ]
    translated: list[str] = []

    monkeypatch.setattr(
        module, "llm", lambda *args, **kwargs: json.dumps({"anchors": proposed})
    )

    def fake_translate(anchor_vi: str) -> str:
        translated.append(anchor_vi)
        return f"EN {anchor_vi}"

    monkeypatch.setattr(module, "translate", fake_translate)
    monkeypatch.setattr(module, "count_clip_tokens", lambda text: 12)

    plan = module.plan_query(query_vi)

    assert plan.strategy == "multi"
    assert [anchor.query_vi for anchor in plan.anchors] == proposed[:3]
    assert translated == proposed[:3]
    assert all(anchor.clip_tokens == 12 for anchor in plan.anchors)
    assert all(anchor.clip_tokens <= 60 for anchor in plan.anchors)


@pytest.mark.parametrize(
    "invented_anchor",
    [
        "Hai người đứng cạnh quầy",
        "Vài người đứng cạnh quầy",
        "Người đứng cạnh quầy số 7",
        "Người mặc áo đỏ đứng cạnh quầy",
        "Người mặc áo màu bạc đứng cạnh quầy",
    ],
)
def test_reject_anchor_bia_so_luong_chu_so_hoac_mau(monkeypatch, invented_anchor):
    """Bắt lỗi anchor tự thêm constraint làm thu hẹp sai tập retrieval."""
    module = _module()
    query_vi = (
        "Người bước vào cửa hàng rồi nhìn bảng giá, sau đó quay sang nói chuyện "
        "với nhân viên đang đứng cạnh quầy thanh toán ở phía trước"
    )
    monkeypatch.setattr(
        module,
        "llm",
        lambda *args, **kwargs: json.dumps({
            "anchors": [
                "Người bước vào cửa hàng",
                invented_anchor,
                "Người nói chuyện với nhân viên cạnh quầy thanh toán",
            ]
        }),
    )
    monkeypatch.setattr(module, "translate", lambda text: f"EN {text}")
    monkeypatch.setattr(module, "count_clip_tokens", lambda text: 10)

    plan = module.plan_query(query_vi)

    assert plan.strategy == "multi"
    assert [anchor.query_vi for anchor in plan.anchors] == [
        "Người bước vào cửa hàng",
        "Người nói chuyện với nhân viên cạnh quầy thanh toán",
    ]


def test_translation_hoac_tokenizer_loi_fallback_single(monkeypatch):
    """Bắt lỗi một anchor lỗi dịch/token khiến KIS crash hoặc chạy multi bán phần."""
    module = _module()
    query_vi = (
        "Người bước vào cửa hàng rồi nhìn bảng giá, sau đó quay sang nói chuyện "
        "với nhân viên đang đứng cạnh quầy thanh toán ở phía trước"
    )
    monkeypatch.setattr(
        module,
        "llm",
        lambda *args, **kwargs: json.dumps({
            "anchors": ["Người bước vào cửa hàng", "Người nhìn bảng giá"]
        }),
    )
    monkeypatch.setattr(
        module,
        "translate",
        lambda text: (_ for _ in ()).throw(RuntimeError("translation offline")),
    )

    plan = module.plan_query(query_vi)

    assert plan.strategy == "single"
    assert plan.fallback_reason == "translation_error"


def test_anchor_qua_60_token_fallback_single(monkeypatch):
    """Bắt lỗi caption chạm trần CLIP vẫn được đưa vào vector search."""
    module = _module()
    query_vi = (
        "Người bước vào cửa hàng rồi nhìn bảng giá, sau đó quay sang nói chuyện "
        "với nhân viên đang đứng cạnh quầy thanh toán ở phía trước"
    )
    monkeypatch.setattr(
        module,
        "llm",
        lambda *args, **kwargs: json.dumps({
            "anchors": ["Người bước vào cửa hàng", "Người nhìn bảng giá"]
        }),
    )
    monkeypatch.setattr(module, "translate", lambda text: f"EN {text}")
    monkeypatch.setattr(module, "count_clip_tokens", lambda text: 61)

    plan = module.plan_query(query_vi)

    assert plan.strategy == "single"
    assert plan.fallback_reason == "token_limit"


def test_query_dai_khong_co_quan_he_thu_tu_khong_bat_temporal(monkeypatch):
    """Bắt lỗi mọi query dài đều bị ép bonus thứ tự dù chỉ là nhiều thuộc tính."""
    module = _module()
    query_vi = (
        "Khung cảnh khu chợ ngoài trời có người bán hàng bên quầy thực phẩm cùng "
        "khách mua sắm xung quanh và nhiều biển hiệu cửa hàng ở phía sau khu vực"
    )
    monkeypatch.setattr(
        module,
        "llm",
        lambda *args, **kwargs: json.dumps({
            "anchors": ["Khung cảnh khu chợ ngoài trời", "Khách mua sắm xung quanh"]
        }),
    )
    monkeypatch.setattr(module, "translate", lambda text: f"EN {text}")
    monkeypatch.setattr(module, "count_clip_tokens", lambda text: 10)

    plan = module.plan_query(query_vi)

    assert plan.strategy == "multi"
    assert plan.ordered is False


def test_outer_rrf_dung_literal_gom_shot_va_tie_break_deterministic(monkeypatch):
    """Bắt lỗi dùng inner score/nhầm k hoặc sort tie phụ thuộc thứ tự dict."""
    module = _module()
    plan = _multi_plan(module, [("sự kiện a", "event a"), ("sự kiện b", "event b")])
    responses = {
        "sự kiện a": [
            _fusion_row("L02_V001", "shot-z", "kf-z-best", 100),
            _fusion_row("L01_V001", "shot-a", "kf-a-second", 200),
        ],
        "sự kiện b": [
            _fusion_row("L01_V001", "shot-a", "kf-a-best", 300),
            _fusion_row("L02_V001", "shot-z", "kf-z-second", 400),
        ],
    }

    def fake_search(query_vi, **kwargs):
        assert kwargs == {"query_en": f"event {query_vi[-1]}", "top_k": 100,
                          "group_by_shot": True}
        return responses[query_vi]

    monkeypatch.setattr(module, "search", fake_search)

    rows = module.search_multi(plan, top_k=10)

    literal = 1 / (7 + 1) + 1 / (7 + 2)
    assert [row["video_id"] for row in rows] == ["L01_V001", "L02_V001"]
    assert rows[0]["score"] == pytest.approx(literal * 1.25)
    assert rows[1]["score"] == pytest.approx(literal * 1.25)
    assert rows[0]["keyframe_id"] == "kf-a-best"
    assert rows[0]["anchor_ranks"] == {"anchor_1": 2, "anchor_2": 1}
    assert rows[0]["anchor_contributions"] == pytest.approx({
        "anchor_1": 1 / 9,
        "anchor_2": 1 / 8,
    })


def test_gom_shot_giu_representative_co_frame_metadata_day_du_nhat(monkeypatch):
    """Bắt lỗi occurrence rank cao nhưng thiếu frame làm hỏng row fused."""
    module = _module()
    plan = _multi_plan(module, [("a", "a en"), ("b", "b en")])
    incomplete = _fusion_row("L01_V001", "target", "kf-missing", None)
    complete = _fusion_row("L01_V001", "target", "kf-complete", 240)
    monkeypatch.setattr(
        module,
        "search",
        lambda query_vi, **kwargs: (
            [incomplete]
            if query_vi == "a"
            else [_fusion_row("L09_V001", "other", "kf-other", 100), complete]
        ),
    )

    rows = module.search_multi(plan, top_k=10)
    target = next(row for row in rows if row["shot_id"] == "target")

    assert target["keyframe_id"] == "kf-complete"
    assert target["frame_idx"] == 6
    assert target["timestamp_ms"] == 240


def test_temporal_bonus_chi_ap_dung_video_du_anchor_va_timestamp_tang(monkeypatch):
    """Bắt lỗi temporal hard-filter hoặc bonus khi thiếu/đảo timestamp."""
    module = _module()
    plan = _multi_plan(module, [("a", "a en"), ("b", "b en")])
    responses = {
        "a": [
            _fusion_row("L01_V001", "ordered-a", "o-a", 100),
            _fusion_row("L02_V001", "reversed-a", "r-a", 300),
            _fusion_row("L03_V001", "missing-a", "m-a", None),
            _fusion_row("L04_V001", "incomplete-a", "i-a", 100),
        ],
        "b": [
            _fusion_row("L01_V001", "ordered-b", "o-b", 200),
            _fusion_row("L02_V001", "reversed-b", "r-b", 100),
            _fusion_row("L03_V001", "missing-b", "m-b", 200),
        ],
    }
    monkeypatch.setattr(module, "search", lambda query_vi, **kwargs: responses[query_vi])

    rows = module.search_multi(plan, top_k=20)

    by_video: dict[str, list[dict]] = {}
    for row in rows:
        by_video.setdefault(row["video_id"], []).append(row)
    assert set(by_video) == {"L01_V001", "L02_V001", "L03_V001", "L04_V001"}
    assert all(row["temporal_order_match"] is True for row in by_video["L01_V001"])
    assert all(row["temporal_order_match"] is False for row in by_video["L02_V001"])
    assert all(row["temporal_order_match"] is False for row in by_video["L03_V001"])
    assert all(row["temporal_order_match"] is False for row in by_video["L04_V001"])
    assert by_video["L04_V001"][0]["score"] == pytest.approx(1 / 11)
