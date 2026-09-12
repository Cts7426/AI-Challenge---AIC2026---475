"""Chạy kiểm tuần tự dưới hard guard; lưu lệnh/exit/elapsed và audit riêng từng lần."""
from pathlib import Path
import json
import os
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
name,*args=sys.argv[1:]
assert name and '/' not in name and '\\' not in name
env=dict(os.environ)
env.update(H02_OFFLINE_GUARD='1',LLM_CACHE_ONLY='1',LLM_BACKEND='api',LLM_API_MODEL='claude-sonnet-5',
           HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',
           H02_DISPATCH_AUDIT=str(OUT/f'{name}_dispatch.jsonl'),
           PYTHONPATH=os.pathsep.join((str(OUT/'offline_guard'),str(ROOT))),
           TEMP=str(ROOT/'reports/post_preliminary_h01_20260912/runtime_tmp'),
           TMP=str(ROOT/'reports/post_preliminary_h01_20260912/runtime_tmp'))
command=[str(ROOT/'.venv/Scripts/python.exe'),*args]
started=time.time()
with (OUT/f'{name}.log').open('w',encoding='utf-8') as log:
    result=subprocess.run(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
audit=OUT/f'{name}_dispatch.jsonl'
blocked=len(audit.read_text(encoding='utf-8').splitlines()) if audit.exists() else 0
record=dict(command=command,exit_code=result.returncode,seconds=round(time.time()-started,3),
            hard_guard=True,external_dispatch_attempts=blocked,external_provider_calls_completed=0,
            model_selection='api/claude-sonnet-5',cache_only=True)
(OUT/f'{name}_command.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(record,ensure_ascii=False))
raise SystemExit(result.returncode if result.returncode else (1 if blocked else 0))
