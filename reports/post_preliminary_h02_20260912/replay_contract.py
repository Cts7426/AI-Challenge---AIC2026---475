"""Replay cấu trúc trên toàn bộ manifest đã khóa; không inference, không sửa lịch sử."""
from pathlib import Path
import collections
import copy
import csv
import hashlib
import io
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.common.qa_contract import reconcile_qa_trace, answer_rejection_reason, autonomous_qa_trace
from backend.indexing.frame_map import load_frame_map

REPORT = Path(__file__).resolve().parent
OUT = REPORT/'replay_final'
OUT.mkdir(exist_ok=True)
manifest_path = REPORT/'replay_input_manifest.json'
manifest = json.loads(manifest_path.read_text(encoding='utf-8'))

def read_locked(identity):
    data = (ROOT/identity['path']).read_bytes()
    assert len(data)==identity['size'] and hashlib.sha256(data).hexdigest()==identity['sha256'], identity['path']
    return data.decode('utf-8-sig')

def json_rows(identity):
    return [json.loads(line) for line in read_locked(identity).splitlines() if line.strip()]

fmap = load_frame_map()
def mapping_errors(answers):
    return sum(bool(a.get('keyframe_id')) and
               (a['keyframe_id'] not in fmap or fmap[a['keyframe_id']] not in a.get('frame_ids',[]))
               for a in answers)

changes, full_outputs, group_reports = [], [], []
for group in manifest['groups']:
    raw_rows = json_rows(group['source'])
    extra = {r['query_id']:r for r in json_rows(group['answers_source'])} if group.get('answers_source') else {}
    transitions = collections.Counter()
    origin_transitions = collections.Counter()
    modes = collections.Counter()
    task_counts = collections.Counter()
    stats = collections.Counter()
    for index, raw in enumerate(raw_rows,1):
        before = copy.deepcopy(raw.get('task_output',raw))
        if extra:
            before['answers'] = extra.get(before['query_id'],{}).get('answers',[])
        # Schema legacy chưa có status; báo rõ đó là success ngầm, không đánh giá accuracy.
        old_status = before.get('status','legacy_implicit_success')
        after = reconcile_qa_trace(before)
        new_status = after.get('status',old_status)
        autonomous = autonomous_qa_trace(before)
        origin = after.get('output_origin', 'unknown')
        origin_transitions[f'{origin} -> {autonomous.get("output_origin", "unknown")}'] += 1
        qa_trace = before.get('qa_trace') or {}
        hypotheses = before.get('qa_hypotheses') or qa_trace.get('hypotheses') or []
        provenances = [h.get('provenance',h.get('source')) for h in hypotheses if isinstance(h,dict)]
        known_modes = {str(p).split(':')[-1] for p in provenances} & {'legacy','two_stage'}
        mode = next(iter(known_modes)) if len(known_modes)==1 else 'unknown'
        modes[mode] += 1
        task_counts[before['task_type']] += 1
        transitions[f'{old_status} -> {new_status}'] += 1
        stats['records'] += 1
        stats['qa_records'] += before.get('task_type')=='QA'
        original_answers=before.get('answers') or []
        output_answers=after.get('answers') or []
        if new_status in ('needs_review','abstain'):
            assert after.get('review_answers',[])==original_answers
            for field in ('qa_trace','qa_hypotheses','search_rows','candidates','task_metadata'):
                assert after.get(field)==before.get(field), (group['name'],index,field)
            stats['review_payloads_preserved'] += 1
        else:
            assert original_answers==output_answers
        stats['new_mapping_violations'] += max(0,mapping_errors(output_answers)-mapping_errors(original_answers))
        stats['input_mapping_violations'] += mapping_errors(original_answers)
        if before.get('task_type')=='QA':
            stats['input_unsupported_answer_rows'] += sum(bool(answer_rejection_reason(a.get('answer_text'),a.get('provenance'),a.get('evidence_hash'))) for a in original_answers)
            stats['unsupported_autonomous_answer_rows'] += sum(bool(answer_rejection_reason(a.get('answer_text'),a.get('provenance'),a.get('evidence_hash'))) for a in output_answers)
            stats['input_qa_answer_rows'] += len(original_answers)
            stats['output_qa_answer_rows'] += len(output_answers)
        changes.append({'group':group['name'],'record':index,'query_id':before['query_id'],'task_type':before['task_type'],
                        'old_status':old_status,'new_status':new_status,'result_state':after.get('result_state'),
                        'input_answers':len(original_answers),'output_answers':len(output_answers),
                        'review_answers':len(after.get('review_answers') or []),
                        'historical_export_status':raw.get('export_status'),
                        'source_artifact':group['source']['path'], 'qa_mode':mode,
                        'old_answer':before.get('answer_text'), 'old_provenances':provenances,
                        'old_answers':original_answers,
                        'new_origin':origin, 'autonomous_eligible':after.get('autonomous_eligible',False),
                        'autonomous_policy_status':autonomous.get('status',old_status),
                        'candidate_evidence_preserved':True,
                        'reason':after.get('output_contract_reason') or ('task_failure_preserved' if new_status=='failed' else 'unchanged_contract'),
                        'old_origin':origin})
        full_outputs.append({'group':group['name'],'record':index,'task_output':after})
    group_reports.append({'name':group['name'],'distinct_query_ids':len({r.get('task_output',r)['query_id'] for r in raw_rows}),
                          'transitions':dict(transitions),'counts':dict(stats),
                          'task_counts':dict(task_counts),'mode_record_counts':dict(modes),
                          'origin_transitions':dict(origin_transitions)})
    qa_changes=[r for r in changes if r['group']==group['name'] and r['task_type']=='QA']
    group_reports[-1]['qa_mode_record_counts']=dict(collections.Counter(r['qa_mode'] for r in qa_changes))
    group_reports[-1]['qa_origin_counts']=dict(collections.Counter(r['new_origin'] for r in qa_changes))
    group_reports[-1]['qa_autonomous_policy_transitions']=dict(collections.Counter(
        f"{r['old_status']} -> {r['autonomous_policy_status']}" for r in qa_changes))

csv_reports=[]
for identity in manifest['csv_files']:
    rows=list(csv.reader(io.StringIO(read_locked(identity))))
    is_qa='qa' in Path(identity['path']).stem.casefold()
    blocked=[i for i,row in enumerate(rows,1) if is_qa and (len(row)<3 or answer_rejection_reason(row[2]))]
    csv_reports.append({'path':identity['path'],'rows':len(rows),'qa':is_qa,'unsupported_rows':blocked,
                        'hypothetical_text_gate':'blocked' if blocked else 'no_known_text_refusal',
                        'provenance_available':False})

totals={key:sum(g['counts'].get(key,0) for g in group_reports) for key in set().union(*(g['counts'] for g in group_reports))}
assert totals.get('unsupported_autonomous_answer_rows',0)==0
assert totals.get('new_mapping_violations',0)==0
summary={'experiment_id':manifest['experiment_id'],'input_manifest_sha256':hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
         'source_runs':len(group_reports),'unique_query_ids':len({r['query_id'] for r in changes}),
         'unique_task_query_pairs':len({(r['task_type'],r['query_id']) for r in changes}),
         'task_record_counts':dict(collections.Counter(r['task_type'] for r in changes)),
         'task_unique_query_counts':{task:len({r['query_id'] for r in changes if r['task_type']==task}) for task in {r['task_type'] for r in changes}},
         'needs_review_unique_query_ids':len({r['query_id'] for r in changes if r['new_status']=='needs_review'}),
         'qa_origin_record_counts':dict(collections.Counter(r['new_origin'] for r in changes if r['task_type']=='QA')),
         'groups':group_reports,'counts':totals,'csv_files':len(csv_reports),
         'csv_known_unsupported_rows':sum(len(r['unsupported_rows']) for r in csv_reports),
         'csv_files_blocked_by_text_gate':sum(bool(r['unsupported_rows']) for r in csv_reports),
         'replay_crashes':0,'paid_provider_calls':0,'historical_files_modified':0,
         'limitations':['Không chấm accuracy hoặc tự xác nhận GT.',
                        'Tên group ROUND*_OPERATOR_HISTORY chỉ xác định nguồn, không được dùng để suy provenance của record.',
                        'H01 task status còn success không có nghĩa exportable: cache-miss export gate vẫn độc lập và không đổi.',
                        'Trace legacy thiếu evidence/provenance phải duyệt, không có nghĩa answer sai.',
                        'CSV không có provenance; số 0 không thể phân loại placeholder chỉ từ CSV.',
                        'Mapping dùng reference keyframe có sẵn; không suy frame hoặc chạy lại retrieval.',
                        'Số đo tính mọi record, gồm cả lần chạy lại; distinct query IDs báo riêng từng nhóm.']}
assert summary['counts']['records']==129 and summary['csv_files']==66
# Kiểm lại bytes sau khi replay, tránh tuyên bố immutable chỉ từ phép kiểm đầu.
for group in manifest['groups']:
    read_locked(group['source'])
    if group.get('answers_source'):read_locked(group['answers_source'])
for identity in manifest['csv_files']:read_locked(identity)
for filename,payload in [('replay_summary.json',summary),('replay_query_changes.json',changes),('historical_csv_audit.json',csv_reports)]:
    (OUT/filename).write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'reconciled_traces.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in full_outputs),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False,indent=2))
