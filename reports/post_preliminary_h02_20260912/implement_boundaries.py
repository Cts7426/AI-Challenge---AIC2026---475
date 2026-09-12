"""Giữ provenance qua các ranh giới serialize, policy và release."""
from pathlib import Path

def edit(path, old, new):
    p = Path(path); text = p.read_text(encoding='utf-8')
    assert old in text, (path, old[:80])
    p.write_text(text.replace(old, new), encoding='utf-8')

edit('tests/test_h02_contract.py', "i.code=='answer_unsupported'", "i.rule=='answer_unsupported'")
edit('backend/export/qa_variants.py', '    if not answers or policy == "semantic":', '''    from backend.common.qa_contract import answer_rejection_reason
    if any(answer_rejection_reason(a.answer_text, a.provenance, a.evidence_hash) for a in answers):
        raise ValueError("Q&A policy không nhận placeholder/refusal")
    if not answers or policy == "semantic":''')
p=Path('backend/export/release_rehearsal.py');text=p.read_text(encoding='utf-8')
start=text.index('    required_strings =',text.index('def _valid_hypothesis('));end=text.index('\n\ndef _hypothesis_has_canonical_answer',start)
text=text[:start]+'''    from backend.common.qa_contract import hypothesis_supported
    return hypothesis_supported(hypothesis)

'''+text[end:]
text=text.replace('        if trace.get("status") != "success" or trace.get("retryable") is True:', '''        from backend.common.qa_contract import reconcile_qa_trace
        checked = reconcile_qa_trace({**trace, "task_type": query.get("task_type")})
        if checked.get("status") != "success" or trace.get("retryable") is True:''')
p.write_text(text,encoding='utf-8')
edit('scripts/run_reproducible_baseline.py','            records[query_id] = row', '''            from backend.common.qa_contract import reconcile_qa_trace
            if "task_output" in row:
                row["task_output"] = reconcile_qa_trace({**row["task_output"], "task_type": row["input"].get("task_type")})
                if row["task_output"].get("status") in ("needs_review", "abstain"):
                    row["export_status"] = "blocked_output_contract"
            records[query_id] = row''')
edit('run.py','"answer_text": a.answer_text, "keyframe_id": a.keyframe_id}', '"answer_text": a.answer_text, "keyframe_id": a.keyframe_id,\n            "provenance": a.provenance, "evidence_hash": a.evidence_hash}')
edit('run.py','answer_text=d.get("answer_text"), keyframe_id=d.get("keyframe_id"))', 'answer_text=d.get("answer_text"), keyframe_id=d.get("keyframe_id"),\n                  provenance=d.get("provenance"), evidence_hash=d.get("evidence_hash"))')
edit('backend/tasks/runner.py','        "keyframe_id": answer.keyframe_id,', '        "keyframe_id": answer.keyframe_id,\n        "provenance": answer.provenance, "evidence_hash": answer.evidence_hash,')
edit('dev_set/tools/run_evaluation.py','        "keyframe_id": a.keyframe_id,', '        "keyframe_id": a.keyframe_id,\n        "provenance": a.provenance, "evidence_hash": a.evidence_hash,')
edit('dev_set/tools/run_evaluation.py','        keyframe_id=d.get("keyframe_id"),', '        keyframe_id=d.get("keyframe_id"),\n        provenance=d.get("provenance"), evidence_hash=d.get("evidence_hash"),')
edit('dev_set/tools/run_evaluation.py','                    "status": "success",', '                    "status": query_run.status,\n                    "result_state": query_run.result_state,')
edit('backend/api/main.py', '    answer_text: str | None = None\n', '    answer_text: str | None = None\n    result_state: str | None = None\n    qa_trace: dict | None = None\n')
edit('backend/api/main.py', '        answer_text = None\n', '        answer_text = None\n        result_state = None\n        qa_trace = None\n')
edit('backend/api/main.py','            shots, answer_text = qa_pipeline(req.query, top_k_shots=req.top_k, query_en=req.query_en)', '''            shots, answer_text, qa_trace = qa_pipeline(req.query, top_k_shots=req.top_k, query_en=req.query_en, return_trace=True)
            from backend.common.qa_contract import reconcile_qa_trace
            checked = reconcile_qa_trace({"task_type": "QA", "qa_trace": qa_trace,
                                          "answer_text": answer_text,
                                          "search_rows": [{"shot_id": h.shot_id} for h in shots]})
            answer_text, result_state = checked["answer_text"], checked["result_state"]''')
edit('backend/api/main.py','    return SearchResponse(hits=hits, answer_text=answer_text)', '    return SearchResponse(hits=hits, answer_text=answer_text, result_state=result_state, qa_trace=qa_trace)')
