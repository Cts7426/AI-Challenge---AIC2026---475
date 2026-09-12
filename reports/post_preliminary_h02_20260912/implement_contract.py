"""Chuyển bộ kiểm hiện hành sang module thuần, giữ nguyên luật phủ định hợp lệ."""
from pathlib import Path

qa_path = Path('backend/tasks/qa.py')
qa = qa_path.read_text(encoding='utf-8')
normalize = qa[qa.index('def _normalize_answer('):qa.index('def _dap_an_cho_trong(')]
validators = qa[qa.index('def _la_cau_tu_choi('):qa.index('def build_qa_hypothesis(')]
validators = validators.replace('if not normalized or normalized in QA_SENTINEL_ANSWERS:', 'if not normalized or normalized in QA_SENTINEL_ANSWERS or normalized in QA_PLACEHOLDER_ANSWERS:')
imports = '''"""Hợp đồng Q&A dùng chung cho inference, replay và export; không gọi service.

Supported chỉ xác nhận cấu trúc evidence/provenance, không xác nhận ground truth.
"""
from __future__ import annotations

import copy
import re
import unicodedata
from collections.abc import Mapping

from data.config.qa_hypotheses import (
    QA_ANSWER_MODE_RULES, QA_SENTINEL_ANSWERS, QA_SENTINEL_PREFIX_CONTINUATIONS,
    QA_REFUSAL_EXACT_ANSWERS, QA_REFUSAL_SUBJECT_PREFIXES, QA_REFUSAL_SHORT_ANSWERS,
    QA_REFUSAL_MIN_WORDS, QA_REFUSAL_NEGATIONS, QA_REFUSAL_EVIDENCE_WORDS,
    QA_PLACEHOLDER_ANSWERS, QA_PLACEHOLDER_PROVENANCE_TOKENS,
)

'''
Path('backend/common/qa_contract.py').write_text(imports + normalize + validators, encoding='utf-8')
qa = qa.replace(qa[qa.index('def _normalize_answer('):qa.index('def _diem_co_phat_hang(')], '')
qa = qa.replace(qa[qa.index('def _la_cau_tu_choi('):qa.index('def build_qa_hypothesis(')], '')
index = qa.index('def _diem_co_phat_hang(')
qa = qa[:index] + 'from backend.common.qa_contract import (\n    _normalize_answer, _la_cau_tu_choi, _dung_kieu_dap_an,\n    is_valid_qa_answer, answer_rejection_reason,\n)\n\n\n' + qa[index:]
qa_path.write_text(qa, encoding='utf-8')
