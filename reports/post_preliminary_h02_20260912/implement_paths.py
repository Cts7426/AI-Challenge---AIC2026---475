"""Áp thay đổi H02 đã đăng ký; chỉ sửa các đoạn khớp chính xác."""
from pathlib import Path

def edit(path, old, new):
    p = Path(path); text = p.read_text(encoding='utf-8')
    assert old in text, (path, old[:80])
    p.write_text(text.replace(old, new), encoding='utf-8')

p = Path('backend/tasks/qa.py'); text = p.read_text(encoding='utf-8')
start = text.index('    if (best is None or not hypotheses) and candidate_shots')
end = text.index('    i, hit, answer, evidence_frame_idx, confidence = best', start)
text = text[:start] + '''    if best is None or not hypotheses:
        # Không tạo answer giả. Ứng viên và mọi lần thử vẫn sẵn cho người duyệt.
        budget = _generation_budget_ctx.get()
        trace = {
            "result_state": "needs_review", "hypotheses": [],
            "event_vi": parts.event_vi, "question_vi": parts.question_vi,
            "evidence_type": evidence_type, "answer_mode": answer_mode,
            "planner_fallback": parts.planner_fallback, "attempts": review_attempts,
            "qa_runtime": qa_runtime_config(),
            "generations_used": budget.used if budget else None,
            "generation_limit": budget.limit if budget else None,
            "generation_limit_reached": budget_exhausted,
        }
        return (candidate_shots, "", trace) if return_trace else (candidate_shots, "")

''' + text[end:]
text = text.replace('        raise RuntimeError(f"search() không trả shot nào cho sự kiện: \'{parts.event_vi}\'")', '''        trace = {"result_state": "abstain", "hypotheses": [], "attempts": [],
                 "event_vi": parts.event_vi, "question_vi": parts.question_vi}
        return ([], "", trace) if return_trace else ([], "")''')
text = text.replace('    hypotheses: list[QAHypothesis] = []\n', '    hypotheses: list[QAHypothesis] = []\n    review_attempts: list[dict[str, object]] = []\n')
text = text.replace('            _qa_attempt_ctx.reset(attempt_token)', '            review_attempts.append({"shot_id": hit.shot_id, "keyframe_id": hit.best_keyframe_id, **attempt_details})\n            _qa_attempt_ctx.reset(attempt_token)', 1)
text = text.replace('                    _qa_attempt_ctx.reset(attempt_token)', '                    review_attempts.append({"shot_id": hit.shot_id, "keyframe_id": hit.best_keyframe_id, **attempt_details})\n                    _qa_attempt_ctx.reset(attempt_token)')
text = text.replace('        return ranked_hits, answer, {', '        return ranked_hits, answer, {\n            "result_state": "supported_answer", "attempts": review_attempts,')
text = text.replace('        if not self.evidence_hash.strip():', '        if answer_rejection_reason(self.answer_text, self.provenance, self.evidence_hash):\n            raise ValueError("QAHypothesis không được chứa placeholder/refusal")\n        if not self.evidence_hash.strip():')
p.write_text(text, encoding='utf-8')

edit('backend/tasks/runner.py', '    status: Literal["success", "failed"] = "success"', '''    status: Literal["success", "needs_review", "abstain", "failed"] = "success"
    result_state: str = "supported_answer"
    review_answers: list[dict[str, Any]] = field(default_factory=list)
    review_answer_text: str | None = None
    output_contract_reason: str | None = None''')
edit('backend/tasks/runner.py', '    def compatibility_metadata(self)', '''        if self.task_type == "QA":
            from backend.common.qa_contract import reconcile_qa_trace
            checked = reconcile_qa_trace(self.to_trace_dict())
            self.status = checked["status"]
            self.result_state = checked["result_state"]
            if self.status in ("needs_review", "abstain"):
                self.answers = []
                self.answer_text = ""
                self.review_answers = checked.get("review_answers", [])
                self.review_answer_text = checked.get("review_answer_text")
                self.output_contract_reason = checked.get("output_contract_reason")
                self.retryable = False
        elif self.status == "failed":
            self.result_state = "task_failure"

    def compatibility_metadata(self)''')
edit('backend/tasks/runner.py', '            "failure_class": self.failure_class,', '''            "result_state": self.result_state,
            "review_answers": self.review_answers,
            "review_answer_text": self.review_answer_text,
            "output_contract_reason": self.output_contract_reason,
            "failure_class": self.failure_class,''')
edit('backend/tasks/runner.py', '            "backend/common/answer_match.py",', '            "backend/common/answer_match.py",\n            "backend/common/qa_contract.py",')
edit('backend/tasks/runner.py', '''            if not str(answer_text or "").strip():
                raise RuntimeError("qa_pipeline() không suy ra được answer_text")
''', '')
edit('backend/tasks/runner.py', '            hypothesis_rows = qa_trace.get("hypotheses")', '''            # Kiểm trước allocation để placeholder không thành câu trả lời tự động.
            probe = QueryRun(
                query_id=str(_query_value(query, "query_id", "")), task_type="QA",
                answers=[], query_plan=plan, search_rows=rows, timings=timings,
                runtime_fingerprint=fingerprint, task_metadata={"hits": rows},
                answer_text=answer_text, qa_trace=qa_trace,
                qa_hypotheses=qa_trace.get("hypotheses") or [],
            )
            if probe.status != "success":
                timings["total_seconds"] = round(time.perf_counter() - started, 6)
                return probe
            hypothesis_rows = qa_trace.get("hypotheses")''')
edit('run.py', '                ra[rec["query_id"]] = rec', '                from backend.common.qa_contract import reconcile_qa_trace\n                rec = reconcile_qa_trace(rec)\n                ra[rec["query_id"]] = rec')
edit('run.py', '            rec.get("query_hash") != _query_hash(q)', '            rec.get("status", "success") != "success"\n            or rec.get("query_hash") != _query_hash(q)')
edit('run.py', '            trace_log.ghi(query_run.to_trace_dict())', '''            trace_log.ghi(query_run.to_trace_dict())
            if query_run.status != "success":
                hong.append((qid, query_run.result_state))
                log(f"  ! {qid}: {query_run.result_state}; đã lưu ứng viên/evidence để duyệt")
                if bar:
                    bar.cap_nhat(f"! {qid}")
                continue
            answers = query_run.answers''')

edit('backend/export/exporter.py', '        if task == "QA" and not (a.answer_text or "").strip():', '''        if task == "QA":
            from backend.common.qa_contract import answer_rejection_reason
            if answer_rejection_reason(a.answer_text, a.provenance, a.evidence_hash):
                out.append(Issue("answer_unsupported", "Q&A placeholder/refusal không được xuất tự động", q, i))
        if task == "QA" and not (a.answer_text or "").strip():''')

edit('data/config/submit_format.py', '    keyframe_id: str | None = None', '''    keyframe_id: str | None = None
    # Provenance chỉ dùng kiểm hợp đồng, không ghi thêm cột vào CSV BTC.
    provenance: str | None = None
    evidence_hash: str | None = None''')
edit('backend/tasks/qa_portfolio.py', 'from __future__ import annotations', 'from __future__ import annotations\n\nfrom dataclasses import replace\nfrom backend.common.qa_contract import hypothesis_supported')
edit('backend/tasks/qa_portfolio.py', '    ranked = _rank_hypotheses(hypotheses)', '''    if any(not hypothesis_supported(h.to_dict()) for h in hypotheses):
        raise RuntimeError("Q&A portfolio nhận placeholder/refusal hoặc thiếu evidence")
    ranked = _rank_hypotheses(hypotheses)''')
edit('backend/tasks/qa_portfolio.py', '            answer_text=hypothesis.answer_text,', '            answer_text=hypothesis.answer_text,\n            provenance=hypothesis.provenance, evidence_hash=hypothesis.evidence_hash,')
edit('backend/tasks/qa_portfolio.py', '            append(row)', '            append(replace(row, provenance=ranked[0].provenance, evidence_hash=ranked[0].evidence_hash))')
