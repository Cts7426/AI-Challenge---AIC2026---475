# tests/test_llm_adapter.py — C0.1: retry của backend Gemini trong llm()
#
# SỬA 18/08: `_call_gemini()` trước đây chỉ retry `ServerError` (5xx). 429
# RESOURCE_EXHAUSTED (rate limit free-tier — 5 request/phút, xem
# `DEFAULT_GEMINI_MODEL` trong backend/llm/adapter.py) ném `ClientError` (4xx),
# bay thẳng ra ngoài không retry giây nào — đây là nguyên nhân chính khiến Q&A
# (nhiều lệnh gọi llm() nhất/câu) luôn crash trên key free-tier, chưa một lần
# chạy hết một dev_set eval (xem dev_set/results/run_*/scores.jsonl — 0 dòng
# QA trong MỌI run cho tới bản sửa này).
#
# Test ở đây mock thẳng `client.models.generate_content` — không gọi mạng thật,
# không cần GEMINI_API_KEY.

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

try:
    from google.genai.errors import ClientError, ServerError
except ModuleNotFoundError:
    pytest.skip("google-genai chưa được cài", allow_module_level=True)

import backend.llm.adapter as adapter


def _make_response(text: str = "ok"):
    resp = MagicMock()
    resp.text = text
    resp.usage_metadata = MagicMock(
        prompt_token_count=10, candidates_token_count=5, cached_content_token_count=0
    )
    return resp


def _client_error(code: int) -> ClientError:
    return ClientError(code, {"message": f"lỗi {code}", "status": "ERR"}, None)


@pytest.fixture(autouse=True)
def _khong_that_su_ngu(monkeypatch):
    """Test đo HÀNH VI retry (bao nhiêu lần, có đợi không), không đo THỜI GIAN
    thật — vá time.sleep để suite chạy tức thì, chỉ ghi lại đã gọi bao lâu."""
    slept = []
    monkeypatch.setattr(adapter.time, "sleep", lambda s: slept.append(s))
    yield slept


@pytest.fixture
def _fake_client():
    client = MagicMock()
    with patch.object(adapter, "_gemini_client", return_value=client):
        yield client


def test_429_retry_roi_thanh_cong(_fake_client, _khong_that_su_ngu):
    """429 hai lần rồi thành công lần 3 — phải retry, KHÔNG raise, và phải đợi
    theo bậc RATE_LIMIT_BACKOFF (đợi dài vì hạn mức free-tier reset THEO PHÚT,
    không phải theo giây như 503)."""
    _fake_client.models.generate_content.side_effect = [
        _client_error(429), _client_error(429), _make_response("xong"),
    ]
    out = adapter._call_gemini("prompt", None, None, "gemini-2.5-flash", 100, None)
    assert out == "xong"
    assert _khong_that_su_ngu == [15, 30]  # 2 bậc đầu của RATE_LIMIT_BACKOFF


def test_429_lien_tuc_het_luot_retry_thi_raise_ro_rang(_fake_client, _khong_that_su_ngu):
    """429 liên tục vượt quá số lần retry cho phép → RuntimeError CÓ Ý NGHĨA
    (không phải ClientError thô khó hiểu), để chỗ gọi (qa.py) biết đây là hết
    hạn mức chứ không phải lỗi logic."""
    _fake_client.models.generate_content.side_effect = _client_error(429)
    with pytest.raises(RuntimeError, match="429"):
        adapter._call_gemini("prompt", None, None, "gemini-2.5-flash", 100, None)


def test_loi_4xx_khac_429_khong_retry(_fake_client, _khong_that_su_ngu):
    """400 (vd schema hỏng) là lỗi THẬT — retry không sửa được gì, phải bay ra
    NGAY, không đốt thời gian chờ vô ích trong ngân sách 30s của đường online."""
    _fake_client.models.generate_content.side_effect = _client_error(400)
    with pytest.raises(ClientError):
        adapter._call_gemini("prompt", None, None, "gemini-2.5-flash", 100, None)
    assert _khong_that_su_ngu == []  # không sleep giây nào


def test_503_van_retry_nhu_cu(_fake_client, _khong_that_su_ngu):
    """Hành vi cũ (retry ServerError) không được vỡ khi thêm nhánh 429."""
    server_err = ServerError(503, {"message": "quá tải", "status": "UNAVAILABLE"}, None)
    _fake_client.models.generate_content.side_effect = [server_err, _make_response("xong")]
    out = adapter._call_gemini("prompt", None, None, "gemini-2.5-flash", 100, None)
    assert out == "xong"
    assert _khong_that_su_ngu == [1]  # bậc đầu của backoff 503 (2**0)
