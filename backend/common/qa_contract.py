"""Hợp đồng Q&A dùng chung cho inference, replay và export; không gọi service.

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
    QA_OPERATOR_PROVENANCE_TOKENS, QA_AUTONOMOUS_PROVENANCE_TOKENS,
)

def _normalize_answer(answer_text: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(answer_text))
    normalized = " ".join(normalized.casefold().split())
    while normalized and unicodedata.category(normalized[0]).startswith("P"):
        normalized = normalized[1:].lstrip()
    while normalized and unicodedata.category(normalized[-1]).startswith("P"):
        normalized = normalized[:-1].rstrip()
    return normalized


def _la_cau_tu_choi(normalized: str) -> bool:
    """Dò câu từ chối bằng BA luật, xếp từ chặt tới rộng.

    Vì sao không chỉ liệt kê chuỗi: danh sách là ĐÓNG còn LLM đẻ biến thể vô
    hạn. Đo 28/08 trên đề đợt 1, danh sách 6 chuỗi chỉ bắt 1/5 câu từ chối thật.
    Vì sao không chỉ dò hình dạng: lưới rộng LOẠI NHẦM đáp án thật ("Không thấy
    mưa", "Không có người trong ảnh") — mà loại nhầm đắt hơn bỏ sót.

    Hợp nhất 03/09 từ hai bản làm độc lập (Minh Hoàng ở `integrate/dot3`,
    Thạch ở `codex/qa-last-3h`). Bản hợp nhất phải qua trọn 22 ca của
    `tests/test_qa_hypotheses.py`: 15 chuỗi phải chặn, 7 chuỗi phải giữ.

      ① ĐÍCH DANH  hai surface quan sát được thật, luật hình dạng không với tới.
      ② NGẮN       "không biết" / "we don't know" — bóc chủ ngữ rồi khớp trọn vẹn.
      ③ HÌNH DẠNG  phủ định ĐỨNG ĐẦU + từ nói về việc xác định/bằng chứng.

    Luật ③ đòi phủ định đứng ĐẦU chứ không phải nằm đâu đó, vì đó là thứ duy
    nhất phân biệt được câu từ chối với đáp án có chứa chữ phủ định:
        'Biển báo ghi "Không có thông tin trong bằng chứng"'  -> GIỮ (đáp án thật)
        "Không thể xác định từ bằng chứng"                    -> CHẶN
    """
    if normalized in QA_REFUSAL_EXACT_ANSWERS:          # ①
        return True

    tokens = normalized.split()
    # Bóc chủ ngữ: "tôi không biết" và "không biết" là cùng một câu từ chối.
    if tokens and tokens[0] in QA_REFUSAL_SUBJECT_PREFIXES:
        tokens = tokens[1:]
    con_lai = " ".join(tokens)

    if con_lai in QA_REFUSAL_SHORT_ANSWERS:             # ②
        return True

    if len(tokens) < QA_REFUSAL_MIN_WORDS:              # ③
        return False
    if tokens[0] not in QA_REFUSAL_NEGATIONS:
        return False
    # Từ bằng chứng có thể gồm hai tiếng ("xác định") nên dò trên cả chuỗi.
    return any(w in con_lai for w in QA_REFUSAL_EVIDENCE_WORDS)


def _dung_kieu_dap_an(normalized: str, answer_mode: str | None) -> bool:
    """Đáp án phải đúng DẠNG câu hỏi đòi (câu đếm phải có chữ số, v.v.).

    Đo 28/08: p1-17 hỏi tên con đèo, hạng 1 là "Chồn Hương" còn "Đèo Bạch Mã"
    nằm hạng 2 — hai bên hoà confidence 0.62 mà không có gì phá hoà theo kiểu.
    """
    rule = QA_ANSWER_MODE_RULES.get(answer_mode or "")
    if not rule:
        return True
    if rule.get("digit") and not any(c.isdigit() for c in normalized):
        return False
    max_words = rule.get("max_words")
    if isinstance(max_words, int) and len(normalized.split()) > max_words:
        return False
    return True


def is_valid_qa_answer(answer_text: str | None, answer_mode: str | None = None) -> bool:
    """Từ chối answer rỗng/sentinel trước khi nó trở thành hypothesis/CSV.

    `answer_mode` không bắt buộc để mọi caller cũ gọi được như trước; truyền vào
    thì thêm cổng kiểm kiểu.
    """
    if answer_text is None:
        return False
    normalized = _normalize_answer(answer_text)
    if not normalized or normalized in QA_SENTINEL_ANSWERS or normalized in QA_PLACEHOLDER_ANSWERS:
        return False
    for prefix in QA_SENTINEL_ANSWERS:
        marker = prefix + " "
        if not normalized.startswith(marker):
            continue
        suffix = normalized[len(marker):]
        first_token = suffix.split(" ", 1)[0]
        first_token = _normalize_answer(first_token)
        if first_token in QA_SENTINEL_PREFIX_CONTINUATIONS:
            return False
    if _la_cau_tu_choi(normalized):
        return False
    return _dung_kieu_dap_an(normalized, answer_mode)


def answer_rejection_reason(answer_text, provenance=None, evidence_hash=None) -> str | None:
    """Input text và dấu vết tùy chọn; output lý do chặn, không suy GT từ nội dung."""
    tokens = set(re.split(r"[:/\s.-]+", str(provenance or "").casefold()))
    if tokens & QA_PLACEHOLDER_PROVENANCE_TOKENS or str(evidence_hash or "").casefold().startswith("placeholder-"):
        return "placeholder_provenance"
    if not isinstance(answer_text, str) or not is_valid_qa_answer(answer_text):
        return "unsupported_answer"
    return None


def hypothesis_supported(hypothesis) -> bool:
    """Kiểm hypothesis lưu trên đĩa mà không import inference/DB hoặc tự tạo evidence."""
    if not isinstance(hypothesis, Mapping):
        return False
    required = ("answer_text", "video_id", "shot_id", "keyframe_id", "evidence_hash", "provenance")
    if hypothesis.get("provenance") == "operator_evidence":
        # Bằng chứng operator có frame canonical nhưng không nhất thiết có shot.
        required = tuple(k for k in required if k != "shot_id")
    if any(not isinstance(hypothesis.get(k), str) or not hypothesis[k].strip() for k in required):
        return False
    frame = hypothesis.get("evidence_frame_idx")
    return (
        isinstance(frame, int) and not isinstance(frame, bool) and frame >= 0
        and answer_rejection_reason(hypothesis["answer_text"], hypothesis["provenance"], hypothesis["evidence_hash"]) is None
        and is_valid_qa_answer(hypothesis["answer_text"], hypothesis.get("answer_mode"))
    )


def provenance_origin(values) -> str:
    """Chỉ gán nguồn khi có marker tường minh; thiếu hoặc mơ hồ giữ unknown."""
    origins = []
    for value in values:
        tokens = set(re.split(r"[:/\s.-]+", str(value or "").casefold()))
        if tokens & QA_OPERATOR_PROVENANCE_TOKENS:
            origins.append("operator_assisted")
        elif tokens & QA_AUTONOMOUS_PROVENANCE_TOKENS:
            origins.append("autonomous")
        else:
            origins.append("unknown")
    if "operator_assisted" in origins:
        return "operator_assisted"
    return "autonomous" if origins and all(o == "autonomous" for o in origins) else "unknown"


def reconcile_qa_trace(record: Mapping) -> dict:
    """Input trace/checkpoint; output bản sao áp contract mới, giữ nguyên payload duyệt.

    Không sửa lịch sử, không khôi phục success từ trạng thái đã bị chặn. Evidence
    hỗ trợ answer của portfolio; kiểm frame-map vẫn thuộc allocator/release gate.
    """
    result = copy.deepcopy(dict(record))
    if str(result.get("task_type", "")).upper() != "QA":
        return result
    extra = result.get("phu") or {}
    extra = extra if isinstance(extra, Mapping) else {}
    qa_trace = result.get("qa_trace") or extra.get("qa_trace") or {}
    qa_trace = qa_trace if isinstance(qa_trace, Mapping) else {}
    hypotheses = result.get("qa_hypotheses") or qa_trace.get("hypotheses") or []
    if result.get("qa_hypotheses") and qa_trace.get("hypotheses"):
        top, nested = result["qa_hypotheses"], qa_trace["hypotheses"]
        hypotheses = top + nested if isinstance(top, list) and isinstance(nested, list) else [None]
    answers = result.get("answers") or []
    if not isinstance(answers, list):
        result["review_answers"] = copy.deepcopy(answers)
        answers = []
    provenance_rows = hypotheses if isinstance(hypotheses, list) else []
    provenances = [h.get("provenance", h.get("source")) for h in provenance_rows if isinstance(h, Mapping)]
    provenances.extend(a["provenance"] for a in answers if isinstance(a, Mapping) and a.get("provenance"))
    review_answers = result.get("review_answers") or []
    if isinstance(review_answers, list):
        provenances.extend(a["provenance"] for a in review_answers if isinstance(a, Mapping) and a.get("provenance"))
    if result.get("provenance"):
        provenances.append(result["provenance"])
    task_metadata = result.get("task_metadata") or {}
    if isinstance(task_metadata, Mapping) and task_metadata.get("manual_override") is True:
        provenances.append("manual_override")
    qa_runtime = qa_trace.get("qa_runtime") or {}
    if isinstance(qa_runtime, Mapping) and qa_runtime.get("manual_override") is True:
        provenances.append("manual_override")
    result["output_origin"] = provenance_origin(provenances)
    result["autonomous_eligible"] = False
    result["process_status"] = "failed" if result.get("status") == "failed" else "completed"
    if result.get("status") == "failed":
        result["result_state"] = "task_failure"
        if answers:
            result["review_answers"] = answers
            result["answers"] = []
        return result
    answer_text = result.get("answer_text", extra.get("answer_text"))
    proposed = [a.get("answer_text") for a in answers if isinstance(a, Mapping)]
    if answer_text:
        proposed.append(answer_text)
    valid_hypotheses = isinstance(hypotheses, list) and bool(hypotheses) and all(hypothesis_supported(h) for h in hypotheses)
    supported_texts = {_normalize_answer(h["answer_text"]) for h in hypotheses} if valid_hypotheses else set()
    supported = (
        result.get("status", "success") == "success"
        and qa_trace.get("result_state", "supported_answer") == "supported_answer"
        and valid_hypotheses and bool(proposed)
        and len([a for a in answers if isinstance(a, Mapping)]) == len(answers)
        and all(answer_rejection_reason(a.get("answer_text"), a.get("provenance"), a.get("evidence_hash")) is None for a in answers)
        and all(answer_rejection_reason(text) is None and _normalize_answer(text) in supported_texts for text in proposed)
    )
    if supported:
        result.update(status="success", result_state="supported_answer", output_contract_version=1)
        result["autonomous_eligible"] = result["output_origin"] == "autonomous"
        return result
    has_review = bool(answers or proposed or hypotheses or result.get("search_rows") or result.get("candidates") or result.get("review_answers") or result.get("review_answer_text") or qa_trace.get("attempts") or qa_trace.get("candidates"))
    status = "needs_review" if has_review else "abstain"
    if answers:
        result["review_answers"] = answers
    if answer_text:
        if not result.get("review_answer_text"):
            result["review_answer_text"] = answer_text
    rejection_reasons = [answer_rejection_reason(h.get("answer_text"), h.get("provenance"), h.get("evidence_hash"))
                         for h in provenance_rows if isinstance(h, Mapping)]
    rejection_reasons += [answer_rejection_reason(text) for text in proposed]
    reason = next((r for r in rejection_reasons if r), "unsupported_or_missing_evidence")
    if result.get("status") in ("needs_review", "abstain") and result.get("output_contract_reason"):
        reason = result["output_contract_reason"]
    result.update(status=status, result_state=status, answers=[], answer_text="",
                  failure_class=None, retryable=False, output_contract_version=1,
                  output_contract_reason=reason)
    return result


def autonomous_qa_trace(record: Mapping) -> dict:
    """Áp policy tự động; giữ nguồn assisted/unknown và payload để người duyệt."""
    result = reconcile_qa_trace(record)
    if result.get("task_type") == "QA" and result.get("status") == "success" and not result["autonomous_eligible"]:
        result["status"] = "needs_review"
        result = reconcile_qa_trace(result)
        result["output_contract_reason"] = "non_autonomous_provenance"
    return result
