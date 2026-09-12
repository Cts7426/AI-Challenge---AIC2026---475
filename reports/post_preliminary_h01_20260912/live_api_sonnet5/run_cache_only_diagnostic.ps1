# Replay diagnostic cục bộ; mọi cache miss phải bị chặn trước provider.
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath 'C:\dev\aic2026'
$env:LLM_BACKEND = 'api'
$env:LLM_API_MODEL = 'claude-sonnet-5'
$env:LLM_CACHE_ONLY = '1'
$env:LLM_CACHE_DIR = 'C:\dev\aic2026\reports\post_preliminary_h01_20260912\live_api_sonnet5\work_cache\llm'
$env:QA_HYPOTHESIS_CACHE_DIR = 'C:\dev\aic2026\reports\post_preliminary_h01_20260912\live_api_sonnet5\work_cache\qa'
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
@'
import json,time
from datetime import datetime,timezone
from pathlib import Path
from backend.common.resource_identity import capture_manifest,manifest_id,file_identity,cache_identity,reproducibility_gaps
from scripts.run_reproducible_baseline import execute_query,query_identity
from run import _doc_queries

root=Path.cwd();base=root/'reports/post_preliminary_h01_20260912/live_api_sonnet5'
out=base/'cache_only_diagnostic';out.mkdir(exist_ok=False)
queries=_doc_queries(base/'queries.json')
identity=capture_manifest(root,live=True,content_digests=False)
identity_id=manifest_id(identity)
manifest={'manifest_id':identity_id,'identity':identity,'captured_at':datetime.now(timezone.utc).isoformat(),
          'mode':'cache_only_diagnostic','promotion':'not_eligible_diagnostic_identity',
          'reproducibility_gaps':reproducibility_gaps(identity),
          'prior_full_resource_capture':file_identity(base/'resource_capture/runtime_manifest.json'),
          'protocol':file_identity(base/'CACHE_ONLY_PROTOCOL.md'),'orchestration':file_identity(base/'run_cache_only_diagnostic.ps1'),
          'query_file':file_identity(base/'queries.json'),'new_api_budget_usd':0}
(out/'runtime_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(out/'query_manifest.json').write_text(json.dumps({'role':'diagnostic_regression_consumed_tune',
 'queries':[{'input':q,'sha256':query_identity(q)} for q in queries],'independent_accuracy_claim':False},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
records=[];started=time.perf_counter()
with (out/'queries.jsonl').open('x',encoding='utf-8') as stream:
 for q in queries:
  record=execute_query(q,out,identity_id,instrumentation=True,qa_policy='robust')
  record['cache_after']=cache_identity(root);record['cache_after_id']=manifest_id(record['cache_after'])
  stream.write(json.dumps(record,ensure_ascii=False,allow_nan=False)+'\n');stream.flush();records.append(record)
  print(q['query_id'],record['task_output']['status'],record['export_status'],record['usage_delta'],flush=True)
  if record['usage_delta'].get('calls',0):
   raise RuntimeError('cache-only invariant: phát hiện provider call; dừng ngay')
summary={'queries':len(records),'task_success':sum(r['task_output']['status']=='success' for r in records),
 'exported':sum(r['export_status']=='written' for r in records),
 'cache_blocked_queries':[r['input']['query_id'] for r in records if r['export_status']=='blocked_cache_miss'],
 'cache_only_misses':sum(r['usage_delta'].get('cache_only_misses',0) for r in records),
 'provider_calls':sum(r['usage_delta'].get('calls',0) for r in records),
 'cache_hits':sum(r['usage_delta'].get('cache_hits',0) for r in records),
 'api_usd':sum(r['usage_delta'].get('usd',0) for r in records),
 'mapping_violations':sum(r['mapping_violations'] or 0 for r in records),
 'export_violations':sum(r['export_violations'] or 0 for r in records),
 'unknown_mapping_queries':sum(r['mapping_violations'] is None for r in records),
 'seconds':time.perf_counter()-started,'promotion':'DO NOT PROMOTE diagnostic only',
 'independent_accuracy_claim':False,'all_queries_have_cached_evidence':all(r['export_status']=='written' for r in records)}
(out/'measurements.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False),flush=True)
'@ | .\.venv\Scripts\python.exe -u -
exit $LASTEXITCODE
