"""H02 RED và regression controls: không cần provider hoặc DB ngoài fixture."""
import copy
import importlib
import json

import pytest

from backend.tasks import runner
from backend.slot import ShotHit
from data.config.submit_format import Answer


def hypothesis(answer='đỏ', provenance='main:llm:legacy', evidence_hash='evidence-verified-by-pipeline'):
    return dict(answer_text=answer, video_id='L21_V001', shot_id='L21_V001#s1',
                keyframe_id='L21_V001#k10', evidence_frame_idx=10, confidence=.8,
                evidence_hash=evidence_hash, provenance=provenance,
                evidence_type='image', answer_mode='visual_attribute')


def trace(answer='đỏ', **changes):
    h = hypothesis(answer)
    result = dict(query_id='qa', task_type='QA', status='success', answer_text=answer,
                  qa_hypotheses=[h], qa_trace={'hypotheses': [h]},
                  answers=[dict(video_id='L21_V001', frame_ids=[10], keyframe_id=h['keyframe_id'], answer_text=answer)],
                  search_rows=[{'shot_id': h['shot_id'], 'keyframe_id': h['keyframe_id'], 'score': .8}])
    result.update(changes)
    return result


@pytest.fixture(autouse=True)
def no_provider(monkeypatch):
    from backend.llm import adapter
    monkeypatch.setenv('LLM_BACKEND', 'api')
    monkeypatch.setenv('LLM_API_MODEL', 'claude-sonnet-5')
    monkeypatch.setenv('LLM_CACHE_ONLY', '1')
    monkeypatch.setattr(adapter, '_mot_lan', lambda *a, **kw: pytest.fail('H02 không được gọi provider'))


@pytest.mark.parametrize('answer,provenance', [('TODO','main:llm:legacy'), ('0','placeholder:no_answer:legacy'), ('đỏ','no_answer')])
def test_runner_does_not_accept_placeholder(monkeypatch, answer, provenance):
    from backend.tasks import qa, qa_portfolio
    hit=ShotHit('L21_V001#s1', .8, 'L21_V001#k10')
    h=hypothesis(answer,provenance)
    monkeypatch.setattr(qa,'qa_pipeline',lambda *a,**kw:([hit],answer,{'hypotheses':[h]}))
    monkeypatch.setattr(qa_portfolio,'allocate_qa_portfolio',lambda *a,**kw:[Answer('L21_V001',(10,),answer_text=answer)])
    result=runner.solve_query({'query_id':'qa','task_type':'QA','query_vi':'màu gì?'},total=1)
    assert result.status=='needs_review'
    assert result.answers==[]
    assert result.search_rows[0]['shot_id']==hit.shot_id
    assert result.qa_trace['hypotheses']==[h]


@pytest.mark.parametrize('answer', ['TODO','Không đủ căn cứ','Không thể xác định từ bằng chứng'])
def test_exporter_rejects_known_unsupported(answer,monkeypatch):
    from backend.export import exporter
    monkeypatch.setattr(exporter,'_check_video_and_frames',lambda sub:[])
    sub=exporter.QuerySubmission('qa','QA',(Answer('L21_V001',(10,),answer_text=answer),))
    assert any(i.rule=='answer_unsupported' for i in exporter.validate_submission(sub,expect_answers=1))


@pytest.mark.parametrize('answer',['0','Không có người trong ảnh','Không thấy mưa','Không có thông tin liên lạc'])
def test_zero_and_legitimate_negative_with_evidence_survive(answer):
    contract=importlib.import_module('backend.common.qa_contract')
    original=trace(answer)
    result=contract.reconcile_qa_trace(original)
    assert result['status']=='success'
    assert result['answers']==original['answers']


def test_old_trace_replay_retains_evidence_and_does_not_mutate_history():
    contract=importlib.import_module('backend.common.qa_contract')
    original=trace('TODO');before=copy.deepcopy(original)
    result=contract.reconcile_qa_trace(original)
    assert original==before
    assert result['status']=='needs_review' and result['answers']==[]
    assert result['review_answers']==original['answers']
    assert result['search_rows']==original['search_rows']
    assert result['qa_trace']==original['qa_trace']


def test_missing_evidence_is_reviewable_not_crash(monkeypatch):
    from backend.tasks import qa
    hit=ShotHit('L21_V001#s1', .8, 'L21_V001#k10')
    monkeypatch.setattr(qa,'qa_pipeline',lambda *a,**kw:([hit],'',{'hypotheses':[], 'attempts':[{'reason':'missing evidence'}]}))
    result=runner.solve_query({'query_id':'qa','task_type':'QA','query_vi':'màu gì?'},total=1)
    assert result.status=='needs_review' and result.answers==[]
    assert result.search_rows and result.qa_trace['attempts']


def test_no_candidates_abstains():
    contract=importlib.import_module('backend.common.qa_contract')
    result=contract.reconcile_qa_trace(trace('',search_rows=[],qa_hypotheses=[],qa_trace={},answers=[]))
    assert result['status']=='abstain'


def test_checkpoint_stale_refusal_not_success(tmp_path):
    import run
    record=trace('Không đủ căn cứ')
    path=tmp_path/'checkpoint.jsonl';path.write_text(json.dumps(record,ensure_ascii=False)+'\n',encoding='utf-8')
    restored=run.Checkpoint(path).doc()['qa']
    assert restored['status']!='success'
    assert restored['answers']==[]
    assert restored['review_answers']==record['answers']


@pytest.mark.parametrize('mode',['legacy','two_stage'])
def test_cached_refusal_pipeline_preserves_candidates(tmp_path,monkeypatch,mode):
    from backend.tasks import qa
    monkeypatch.setenv('QA_INFERENCE_MODE',mode)
    monkeypatch.setenv('QA_HYPOTHESIS_CACHE_DIR',str(tmp_path/'cache'))
    monkeypatch.setattr(qa,'parse_question',lambda _:qa.QuestionParts('sự kiện','màu gì?','visual_attribute'))
    monkeypatch.setattr(qa,'search',lambda *a,**kw:[dict(shot_id='L21_V001#s1',score=.8,keyframe_id='L21_V001#k10')])
    monkeypatch.setattr(qa,'_expand_within_video',lambda *a,**kw:[])
    monkeypatch.setattr(qa,'_shot_bu_vung_trong',lambda *a,**kw:[])
    monkeypatch.setattr(qa,'collect_evidence',lambda *a,**kw:qa.Evidence('L21_V001#s1','L21_V001',['bằng chứng trong fixture'],[],'',None,[],10,'evidence'))
    monkeypatch.setattr(qa,'load_frame_map',lambda:{'L21_V001#k10':10})
    cached=json.dumps(dict(answer='Không đủ căn cứ',answer_en='insufficient evidence',confidence=.99,evidence_frame_idx=10))
    monkeypatch.setattr(qa,'_qa_cache_get',lambda *a,**kw:[cached]*3)
    hits,answer,payload=qa.qa_pipeline('màu gì?',return_trace=True)
    assert hits and not answer
    assert payload['result_state']=='needs_review'
    assert payload['hypotheses']==[]
    assert payload['attempts'][0]['inference'][0]['outputs'][0]['answer']=='Không đủ căn cứ'


def test_batch_unsupported_qa_does_not_skip_next_query(tmp_path,monkeypatch):
    import run
    calls=[]
    def solve(q,total):
        calls.append(q['query_id'])
        obj=runner.QueryRun(q['query_id'],q['task_type'],[],{},answer_text='TODO' if q['task_type']=='QA' else None)
        if q['task_type']=='KIS':obj.answers=[Answer('L21_V001',(10,))]
        return obj.answers,obj.compatibility_metadata()
    monkeypatch.setattr(run,'giai_mot_query',solve)
    monkeypatch.setattr(run,'_preflight',lambda *a:True)
    monkeypatch.setattr(run,'_llm_runtime_errors',lambda *a:[])
    queries=[dict(query_id='qa',task_type='QA',query_vi='màu gì?'),dict(query_id='kis',task_type='KIS',query_vi='xe',query_en='car')]
    inp=tmp_path/'q.json';inp.write_text(json.dumps(queries),encoding='utf-8');out=tmp_path/'out'
    monkeypatch.setattr(run.sys,'argv',['run.py','--queries',str(inp),'--out',str(out),'--answers','1','--qa-submission-policy','robust'])
    assert run.main()==1
    assert calls==['qa','kis']
    rows=[json.loads(l) for l in (out/run.TRACE_NAME).read_text(encoding='utf-8').splitlines()]
    assert rows[0]['status'] in ('needs_review','abstain')
    assert rows[1]['status']=='success'
    assert not list(out.glob('*.csv'))


@pytest.mark.parametrize('mode',['legacy','two_stage'])
@pytest.mark.parametrize('answer',['TODO','0','Không có người trong ảnh'])
def test_mocked_live_inference_contract(tmp_path,monkeypatch,mode,answer):
    """Chạy adapter-call site thật với llm giả, không gọi provider; cache miss thật."""
    from backend.tasks import qa
    monkeypatch.setenv('QA_INFERENCE_MODE',mode)
    monkeypatch.setenv('QA_HYPOTHESIS_CACHE_DIR',str(tmp_path/'cache'))
    monkeypatch.setattr(qa,'parse_question',lambda _:qa.QuestionParts('sự kiện','gì?','visual_attribute'))
    monkeypatch.setattr(qa,'search',lambda *a,**kw:[dict(shot_id='L21_V001#s1',score=.8,keyframe_id='L21_V001#k10')])
    monkeypatch.setattr(qa,'_expand_within_video',lambda *a,**kw:[])
    monkeypatch.setattr(qa,'_shot_bu_vung_trong',lambda *a,**kw:[])
    monkeypatch.setattr(qa,'collect_evidence',lambda *a,**kw:qa.Evidence('L21_V001#s1','L21_V001',['bằng chứng trong fixture'],[],'',None,[],10,'evidence'))
    monkeypatch.setattr(qa,'load_frame_map',lambda:{'L21_V001#k10':10})
    calls=[]
    def fake_llm(*args,**kwargs):
        calls.append(kwargs)
        raw=json.dumps(dict(answer=answer,answer_en=answer,confidence=.99,evidence_frame_idx=10))
        return [raw]*kwargs.get('n',1)
    monkeypatch.setattr(qa,'llm',fake_llm)
    first=qa.qa_pipeline('gì?',return_trace=True)
    assert calls
    calls.clear()
    second=qa.qa_pipeline('gì?',return_trace=True)
    assert not calls, 'Lần hai phải replay file cache thật'
    assert first[1:]==second[1:]
    assert second[2]['result_state']==('needs_review' if answer=='TODO' else 'supported_answer')


@pytest.mark.parametrize('answer,provenance',[('TODO','main:llm'),('0','placeholder:no_answer'),('Không đủ căn cứ','main:llm')])
def test_portfolio_and_all_policies_reject_unsupported(monkeypatch,answer,provenance):
    from backend.tasks import qa,qa_portfolio
    from backend.export.qa_variants import apply_qa_submission_policy
    from backend.export import exporter
    h=qa.QAHypothesis.from_dict(hypothesis('đỏ'))
    # Giả lập object cũ đã deserialize trước khi contract mới có hiệu lực.
    object.__setattr__(h,'answer_text',answer);object.__setattr__(h,'provenance',provenance)
    with pytest.raises(RuntimeError,match='placeholder/refusal'):
        qa_portfolio.allocate_qa_portfolio([h],[],total=1)
    a=Answer('L21_V001',(10,),answer_text=answer,provenance=provenance)
    for policy in ('semantic','exact','robust'):
        with pytest.raises(ValueError,match='placeholder/refusal'):
            apply_qa_submission_policy([a],policy)
    monkeypatch.setattr(exporter,'_check_video_and_frames',lambda sub:[])
    assert any(i.rule=='answer_unsupported' for i in exporter.validate_submission(exporter.QuerySubmission('qa','QA',(a,)),expect_answers=1))


@pytest.mark.parametrize('answer',['TODO','Không đủ căn cứ','0'])
def test_release_gate_rejects_unsupported_trace(answer):
    from backend.export.release_rehearsal import assess_release_batch
    from pathlib import Path
    row=trace(answer)
    if answer=='0':
        row['qa_hypotheses'][0]['provenance']='placeholder:no_answer'
    result=assess_release_batch(queries=[dict(query_id='qa',task_type='QA',query_vi='gì?')],
        traces=[row],validator_issues=[],trace_path=Path('trace.jsonl'),cache_manifest={'entries':[]})
    assert not result.eligible
    assert any(reason['code']=='query_not_success' for reason in result.reasons)


def test_harness_resume_downgrades_stale_success(tmp_path):
    from scripts import run_reproducible_baseline as harness
    query=dict(query_id='qa',task_type='QA',query_vi='gì?')
    row=dict(input=query,query_sha256=harness.query_identity(query),runtime_manifest_id='fp',
             task_output=trace('TODO'),export_status='not_exported')
    path=tmp_path/'queries.jsonl'; original=json.dumps(row,ensure_ascii=False)+'\n';path.write_text(original,encoding='utf-8')
    restored=harness.read_checkpoint(tmp_path,[query],'fp')['qa']
    assert restored['task_output']['status']=='needs_review'
    assert restored['export_status']=='blocked_output_contract'
    assert path.read_text(encoding='utf-8')==original


def test_evaluation_resume_requires_supported_trace(tmp_path):
    from dev_set.tools.run_evaluation import _resume_supported_ids
    from types import SimpleNamespace
    queries=[SimpleNamespace(query_id=q,task_type=t) for q,t in [('qa','QA'),('kis','KIS')]]
    scores=tmp_path/'scores.jsonl';candidates=tmp_path/'candidates.jsonl'
    scores.write_text('\n'.join(json.dumps(dict(query_id=q.query_id,status='success')) for q in queries),encoding='utf-8')
    candidates.write_text(json.dumps(trace('TODO')),encoding='utf-8')
    assert _resume_supported_ids(scores,candidates,queries)=={'kis'}
    candidates.write_text(json.dumps(trace('0')),encoding='utf-8')
    assert _resume_supported_ids(scores,candidates,queries)=={'qa','kis'}


def test_api_unsupported_retains_candidates(monkeypatch):
    from backend.api import main
    from backend.tasks import qa
    from backend.slot import allocator
    from fastapi.testclient import TestClient
    h=hypothesis('TODO');payload={'hypotheses':[h],'attempts':[{'evidence_hash':'evidence'}]}
    monkeypatch.setattr(qa,'qa_pipeline',lambda *a,**kw:([ShotHit(h['shot_id'],.8,h['keyframe_id'])],'TODO',payload))
    monkeypatch.setattr(allocator,'shot_bounds',lambda _:('L21_V001',0,20))
    monkeypatch.setattr(main,'load_frame_map',lambda:{h['keyframe_id']:10})
    monkeypatch.setattr(main,'_thumbnail_url',lambda _: '')
    response=TestClient(main.app).post('/search',json={'query':'gì?','task_type':'QA'})
    assert response.status_code==200
    body=response.json()
    assert body['result_state']=='needs_review' and not body['answer_text']
    assert body['hits'][0]['frame_idx']==10 and body['qa_trace']==payload


def test_task_failure_keeps_review_payload(monkeypatch):
    from backend.tasks import qa,qa_portfolio
    hit=ShotHit('L21_V001#s1',.8,'L21_V001#k10');payload={'hypotheses':[hypothesis('0')],'attempts':[{'evidence_hash':'evidence'}]}
    monkeypatch.setattr(qa,'qa_pipeline',lambda *a,**kw:([hit],'0',payload))
    def fail(*a,**kw):raise RuntimeError('mapping failure')
    monkeypatch.setattr(qa_portfolio,'allocate_qa_portfolio',fail)
    with pytest.raises(runner.SolveQueryError) as exc:
        runner.solve_query(dict(query_id='qa',task_type='QA',query_vi='gì?'),total=1)
    result=exc.value.query_run
    assert result.result_state=='task_failure' and result.answers==[]
    assert result.qa_trace==payload and result.search_rows[0]['shot_id']==hit.shot_id


@pytest.mark.parametrize('provenance,origin',[('main:llm:legacy','autonomous'),('operator_evidence','operator_assisted'),('visual','unknown'),('', 'unknown')])
def test_origin_and_roundtrip_are_explicit(provenance,origin):
    from backend.common.qa_contract import reconcile_qa_trace, autonomous_qa_trace
    row=trace('0');row['qa_hypotheses'][0]['provenance']=provenance
    checked=reconcile_qa_trace(row)
    assert checked['output_origin']==origin
    assert checked['autonomous_eligible']==(origin=='autonomous')
    assert reconcile_qa_trace(checked)==checked
    if origin!='autonomous':assert autonomous_qa_trace(row)['status']=='needs_review'
    if origin=='operator_assisted':assert checked['status']=='success'


def test_manual_answer_provenance_overrides_autonomous_hypothesis():
    from backend.common.qa_contract import reconcile_qa_trace
    row=trace('0');row['answers'][0]['provenance']='operator_evidence'
    result=reconcile_qa_trace(row)
    assert result['output_origin']=='operator_assisted' and not result['autonomous_eligible']
    from backend.common.qa_contract import autonomous_qa_trace
    manual_review=autonomous_qa_trace(row)
    assert reconcile_qa_trace(manual_review)==manual_review
    review=reconcile_qa_trace(dict(task_type='QA',answer_text='TODO'))
    assert reconcile_qa_trace(review)==review


def test_autonomous_export_requires_supported_explicit_provenance(monkeypatch):
    from backend.export import exporter
    monkeypatch.setattr(exporter,'_check_video_and_frames',lambda sub:[])
    for provenance,valid in [('main:llm:legacy',True),('operator_evidence',False),('visual',False),('',False)]:
        row=trace('0');row['qa_hypotheses'][0]['provenance']=provenance
        sub=exporter.QuerySubmission('qa','QA',(Answer('L21_V001',(10,),answer_text='0',keyframe_id='L21_V001#k10'),),autonomous=True,output_contract=row)
        issues=exporter.validate_submission(sub,expect_answers=1)
        assert not any(i.rule=='answer_unsupported' for i in issues) if valid else any(i.rule=='answer_unsupported' for i in issues)


@pytest.mark.parametrize('mode',['legacy','two_stage'])
def test_empty_evidence_stops_before_inference(monkeypatch,mode):
    from backend.tasks import qa
    monkeypatch.setenv('QA_INFERENCE_MODE',mode)
    monkeypatch.setattr(qa,'collect_evidence',lambda *a,**kw:qa.Evidence('L21_V001#s1','L21_V001',[],[],'',None,[],10,'empty-hash'))
    monkeypatch.setattr(qa,'ask_llm',lambda *a,**kw:pytest.fail('Không được infer evidence rỗng'))
    assert qa._try_shot(ShotHit('L21_V001#s1',.8,'L21_V001#k10'),'gì?','image',True) is None


def test_all_attempt_errors_are_task_failure_with_candidates(monkeypatch):
    from backend.tasks import qa
    monkeypatch.setattr(qa,'parse_question',lambda _:qa.QuestionParts('sự kiện','gì?','visual_attribute'))
    monkeypatch.setattr(qa,'search',lambda *a,**kw:[dict(shot_id='L21_V001#s1',score=.8,keyframe_id='L21_V001#k10')])
    monkeypatch.setattr(qa,'_expand_within_video',lambda *a,**kw:[])
    monkeypatch.setattr(qa,'_shot_bu_vung_trong',lambda *a,**kw:[])
    def fail(*a,**kw):raise TypeError('fixture bug')
    monkeypatch.setattr(qa,'_try_shot',fail)
    with pytest.raises(runner.SolveQueryError) as exc:
        runner.solve_query(dict(query_id='qa',task_type='QA',query_vi='gì?'),total=1)
    result=exc.value.query_run
    assert result.result_state=='task_failure' and result.process_status=='failed'
    assert result.search_rows and result.qa_trace['attempts'][0]['error']=='TypeError: fixture bug'


def test_minimal_does_not_reuse_supplied_answer(tmp_path,monkeypatch):
    import run_minimal
    from backend.tasks import runner
    result=runner.QueryRun('qa','QA',[],{},answer_text='TODO',search_rows=[{'shot_id':'candidate'}])
    monkeypatch.setattr(runner,'solve_query',lambda *a,**kw:result)
    actual=run_minimal._solve_qa(dict(query_id='qa',task_type='QA',query_vi='gì?',answer='manual-looking'),1,tmp_path)
    assert actual.status=='needs_review' and actual.answers==[]
    saved=json.loads((tmp_path/'trace.jsonl').read_text(encoding='utf-8'))
    assert saved['search_rows']==result.search_rows and saved['review_answer_text']=='TODO'


@pytest.mark.parametrize('profile',['development','release'])
def test_preflight_exercises_shared_contract(profile):
    from scripts import preflight_check as preflight
    check=next(c for c in preflight.CHECKLIST if c.fn==preflight.check_qa_output_contract)
    assert preflight.run_check(check,False,profile).status==preflight.PASS


def test_contract_import_does_not_load_heavy_stack():
    import subprocess,sys
    code="import sys; import backend.common.qa_contract; assert not any(n in sys.modules for n in ('backend.tasks.qa','backend.retrieval.search','backend.llm.adapter','torch','elasticsearch','pymilvus'))"
    result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True)
    assert result.returncode==0,result.stderr


def test_api_task_failure_retains_review_payload(monkeypatch):
    from backend.api import main
    from backend.tasks import qa
    from fastapi.testclient import TestClient
    payload={'candidates':[{'keyframe_id':'kf'}],'attempts':[{'evidence_hash':'evidence'}]}
    def fail(*a,**kw):
        error=RuntimeError('mapping failure');error.qa_review=payload;raise error
    monkeypatch.setattr(qa,'qa_pipeline',fail)
    response=TestClient(main.app).post('/search',json={'query':'gì?','task_type':'QA'})
    assert response.status_code==503
    detail=response.json()['detail']
    assert detail['result_state']=='task_failure' and detail['qa_trace']==payload


def test_autonomous_export_cannot_substitute_different_answer(monkeypatch):
    from backend.export import exporter
    monkeypatch.setattr(exporter,'_check_video_and_frames',lambda sub:[])
    sub=exporter.QuerySubmission('qa','QA',(Answer('L21_V001',(10,),answer_text='xanh'),),autonomous=True,output_contract=trace('đỏ'))
    assert any(i.rule=='answer_unsupported' for i in exporter.validate_submission(sub,expect_answers=1))


@pytest.mark.parametrize('changes',[{'video_id':'L21_V002'}, {'frame_ids':(20,)}, {'keyframe_id':'different'},
                                   {'provenance':'operator_evidence'}, {'evidence_hash':'different'}])
def test_autonomous_export_binds_full_evidence_row(monkeypatch,changes):
    from backend.export import exporter
    monkeypatch.setattr(exporter,'_check_video_and_frames',lambda sub:[])
    values=dict(video_id='L21_V001',frame_ids=(10,),answer_text='0',keyframe_id='L21_V001#k10')
    values.update(changes)
    sub=exporter.QuerySubmission('qa','QA',(Answer(**values),),autonomous=True,output_contract=trace('0'))
    assert any(i.rule=='answer_unsupported' for i in exporter.validate_submission(sub,expect_answers=1))
