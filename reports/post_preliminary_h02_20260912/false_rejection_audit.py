"""Controls có nhãn fixture tường minh; không suy GT từ đáp án thi lịch sử."""
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from backend.common.qa_contract import reconcile_qa_trace, autonomous_qa_trace
from data.config.qa_hypotheses import QA_SENTINEL_ANSWERS, QA_REFUSAL_SHORT_ANSWERS, QA_REFUSAL_EXACT_ANSWERS

OUT=Path(__file__).resolve().parent
def record(answer,provenance='main:llm:legacy',mode='visual_attribute',evidence=True):
    h=dict(answer_text=answer,provenance=provenance,evidence_hash='fixture-evidence',
           video_id='L21_V001',shot_id='L21_V001#s1',keyframe_id='L21_V001#k10',
           evidence_frame_idx=10,confidence=.8,answer_mode=mode)
    return dict(task_type='QA',query_id='fixture',status='success',answer_text=answer,
                answers=[dict(video_id=h['video_id'],frame_ids=[10],keyframe_id=h['keyframe_id'],answer_text=answer)],
                qa_hypotheses=[h] if evidence else [],search_rows=[dict(shot_id=h['shot_id'])])

valid=['0','Không','Không có người trong ảnh','Không thấy mưa','Không có thông tin liên lạc',
       'No Information Technology','Biển báo ghi Không có thông tin trong bằng chứng','đỏ']
results=[]
for answer in valid:
    mode='visual_count' if answer=='0' else 'asr'
    checked=autonomous_qa_trace(record(answer,mode=mode))
    results.append(dict(case=answer,expected='success',actual=checked['status'],kind='valid_autonomous_fixture'))
manual=reconcile_qa_trace(record('0','operator_evidence',mode='visual_count'))
results.append(dict(case='operator zero explicit',expected='success',actual=manual['status'],kind='valid_assisted_fixture',origin=manual['output_origin']))
invalid=sorted(set(QA_SENTINEL_ANSWERS)|set(QA_REFUSAL_SHORT_ANSWERS)|set(QA_REFUSAL_EXACT_ANSWERS)|{'TODO','Không thể xác định từ bằng chứng'})
for answer in invalid:
    checked=autonomous_qa_trace(record(answer))
    results.append(dict(case=answer,expected='needs_review',actual=checked['status'],kind='registered_unsupported'))
for label,row in [('placeholder_zero',record('0','placeholder:no_answer:legacy')),
                  ('no_evidence',record('đỏ',evidence=False)),
                  ('unknown_origin',record('đỏ','visual'))]:
    checked=autonomous_qa_trace(row)
    results.append(dict(case=label,expected='needs_review',actual=checked['status'],kind='registered_unsupported'))
false_rejections=sum(r['actual']!=r['expected'] for r in results if r['kind'].startswith('valid'))
false_accepts=sum(r['actual']!=r['expected'] for r in results if r['kind']=='registered_unsupported')
assert false_rejections==false_accepts==0
payload=dict(valid_fixtures=len(valid)+1,unsupported_fixtures=len(invalid)+3,false_rejections=false_rejections,
             false_accepts=false_accepts,ground_truth_verified_by_agent=False,rows=results)
(OUT/'false_rejection_audit.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in payload.items() if k!='rows'},ensure_ascii=False))
