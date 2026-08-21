# Script test riêng — KHÔNG phải code production. Gọi thẳng qa_pipeline() THẬT
# (backend/tasks/qa.py, không sửa gì) nhưng chèn sleep giữa các lệnh llm() để
# sống sót qua giới hạn 5 request/phút của key Gemini free-tier đang dùng tạm
# để test. Ghi kết quả vào đúng scores.jsonl/answers.jsonl/candidates.jsonl
# của run dev_set/results/run_20260817_1217 để hợp nhất với các câu đã chạy.
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import backend.llm.adapter as adapter_mod

_real_llm = adapter_mod.llm
_call_count = [0]

def _paced_llm(*args, **kwargs):
    if _call_count[0] > 0:
        print(f"    [pacing] ngủ 14s trước lệnh gọi LLM #{_call_count[0]+1}...", flush=True)
        time.sleep(14)
    _call_count[0] += 1
    return _real_llm(*args, **kwargs)

adapter_mod.llm = _paced_llm
# qa.py và text_query.py đã `from backend.llm.adapter import llm` lúc import module
# (binding sớm) — phải vá lại đúng chỗ đó, vá adapter_mod.llm không đủ.
import backend.tasks.qa as qa_mod
import backend.retrieval.text_query as text_query_mod
qa_mod.llm = _paced_llm
text_query_mod.llm = _paced_llm

from backend.indexing.es_client import connect as es_connect
from backend.indexing.milvus_client import connect as milvus_connect
from backend.slot.allocator import allocate, shot_bounds
from dev_set.tools.schema import Query, GroundTruthQA
from dev_set.tools.scoring import recall_at_k, final_score

RUN_DIR = Path("dev_set/results/run_20260817_1217")

es_connect()
milvus_connect()

queries = [Query(**json.loads(l)) for l in open("dev_set/queries/tune_qa.jsonl", encoding="utf-8")]
gts = {}
for l in open("dev_set/ground_truth/tune_gt.jsonl", encoding="utf-8"):
    row = json.loads(l)
    if row["query_id"].startswith("QA"):
        row_clean = {k: v for k, v in row.items() if k != "task_type"}
        gts[row["query_id"]] = GroundTruthQA(**row_clean)

scores_f = open(RUN_DIR / "scores.jsonl", "a", encoding="utf-8")
answers_f = open(RUN_DIR / "answers.jsonl", "a", encoding="utf-8")

for q in queries:
    gt = gts[q.query_id]
    print(f"=== {q.query_id}: {q.query_vi} ===", flush=True)
    _call_count[0] = 0
    try:
        hits, answer_text = qa_mod.qa_pipeline(q.query_vi, query_en=None)
        ans = allocate(hits, "QA", answer_text=answer_text)

        r_1 = recall_at_k(ans, gt, "QA", 1)
        r_5 = recall_at_k(ans, gt, "QA", 5)
        r_20 = recall_at_k(ans, gt, "QA", 20)
        r_50 = recall_at_k(ans, gt, "QA", 50)
        r_100 = recall_at_k(ans, gt, "QA", 100)
        fin = final_score(ans, gt, "QA")

        if fin >= 1.0:
            fc = "SUCCESS"
        else:
            retrieval_success = False
            for h in hits:
                try:
                    vid, start, end = shot_bounds(h.shot_id)
                    if vid == gt.video_id and start <= gt.frame_end and gt.frame_start <= end:
                        retrieval_success = True
                        break
                except KeyError:
                    pass
            fc = "F_QA_REASONING_FAILED" if retrieval_success else "F_QA_RETRIEVAL_FAILED"

        record = {
            "query_id": q.query_id, "task_type": "QA",
            "r_at_1": r_1, "r_at_5": r_5, "r_at_20": r_20, "r_at_50": r_50, "r_at_100": r_100,
            "final": fin, "failure_class": fc,
            "ranks": {"answer_text": answer_text, "gt_answer": gt.answer_text},
        }
        scores_f.write(json.dumps(record, ensure_ascii=False) + "\n")
        scores_f.flush()
        answers_f.write(json.dumps({
            "query_id": q.query_id,
            "answers": [{"video_id": a.video_id, "frame_ids": list(a.frame_ids),
                         "answer_text": a.answer_text, "keyframe_id": a.keyframe_id} for a in ans],
        }, ensure_ascii=False) + "\n")
        answers_f.flush()
        print(f"  -> final={fin:.2f} fc={fc} he_tra_loi='{answer_text}' dung='{gt.answer_text}'", flush=True)
    except Exception as e:
        print(f"  LỖI: {e}", flush=True)
        record = {
            "query_id": q.query_id, "task_type": "QA",
            "r_at_1": 0.0, "r_at_5": 0.0, "r_at_20": 0.0, "r_at_50": 0.0, "r_at_100": 0.0,
            "final": 0.0, "failure_class": "F0_CRASH", "ranks": {},
        }
        scores_f.write(json.dumps(record, ensure_ascii=False) + "\n")
        scores_f.flush()

    print("  nghi 20s truoc cau tiep theo...", flush=True)
    time.sleep(20)

scores_f.close()
answers_f.close()
print("XONG TAT CA QA.")
