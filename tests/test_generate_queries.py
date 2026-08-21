"""Script sinh biến thể phải dùng một request có schema, không nhân chi phí theo số câu."""

import json
from unittest.mock import patch

from dev_set.tools.generate_queries import generate_variants


def test_generate_variants_mot_request_va_loai_chi_tiet_bia():
    payload = {
        "variants": [
            {"text": "người đàn ông đi bộ", "adds_detail": False},
            {"text": "người đàn ông áo đỏ đi bộ", "adds_detail": True},
            {"text": "một người đàn ông đang bước đi", "adds_detail": False},
        ]
    }
    with patch(
        "dev_set.tools.generate_queries.llm", return_value=json.dumps(payload)
    ) as mock_llm:
        out = generate_variants("người đàn ông đi bộ")

    assert out == ["người đàn ông đi bộ", "một người đàn ông đang bước đi"]
    assert mock_llm.call_count == 1
    assert mock_llm.call_args.kwargs["max_tokens"] == 512
    assert mock_llm.call_args.kwargs["json_schema"]["required"] == ["variants"]
