"""Snapshot đúng file H02; giữ index/HEAD và mọi WIP ngoài phạm vi."""
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
BASE='235414784b5ee80b9552fd7fe7ce898db1cbf35b'
def git(*args):
    return subprocess.check_output(['git','--no-optional-locks',*args],cwd=ROOT)
def sha(data):return hashlib.sha256(data).hexdigest()

changed=git('diff','--name-only',BASE).decode().splitlines()
scoped=sorted(p for p in changed if p.startswith(('backend/','data/config/','dev_set/tools/','dev_set/tests/','tests/','scripts/')) or p in ('run.py','run_minimal.py'))
scoped=sorted(set(scoped)|{'backend/common/qa_contract.py','tests/test_h02_contract.py'})
rows=[]
for name in scoped:
    path=ROOT/name
    old=subprocess.run(['git','show',f'{BASE}:{name}'],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
    rows.append(dict(path=name,category='test' if name.startswith(('tests/','dev_set/tests/')) else 'production_or_tooling',
                     base_sha256=sha(old.stdout) if old.returncode==0 else None,
                     sha256=sha(path.read_bytes()),bytes=path.stat().st_size))
patch=git('diff','--binary',BASE,'--',*scoped)
for row in rows:
    if row['base_sha256'] is None and row['path'] not in changed:
        patch+=subprocess.run(['git','diff','--no-index','--binary','--','/dev/null',row['path']],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL).stdout
(OUT/'H02_exact_changes.patch').write_bytes(patch)
snapshot=OUT/'H02_source_snapshot.zip'
with zipfile.ZipFile(snapshot,'w',compression=zipfile.ZIP_DEFLATED) as archive:
    for row in rows:archive.write(ROOT/row['path'],row['path'])
tools=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p.read_bytes()),bytes=p.stat().st_size)
       for p in sorted(OUT.rglob('*.py')) if '__pycache__' not in p.parts]
ledger=dict(experiment_id='PP-H02-OFFLINE-20260912',base_commit=BASE,base_tree=git('rev-parse',f'{BASE}^{{tree}}').decode().strip(),
            branch=git('branch','--show-current').decode().strip(),source_files=rows,report_tools=tools,
            source_file_count=len(rows),snapshot_sha256=sha(snapshot.read_bytes()),patch_sha256=sha(patch),
            unrelated_modified_paths=[p for p in changed if p not in scoped],history_rewritten=False)
(OUT/'H02_change_ledger.json').write_text(json.dumps(ledger,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'H02_SOURCE_LEDGER.md').write_text('# H02 source/change ledger\n\n'+
    f"Base `{BASE}`, tree `{ledger['base_tree']}`. {len(rows)} file source/test/tooling; H01 là ledger riêng15file.\n\n"+
    '| File | SHA-256 hiện tại |\n|---|---|\n'+''.join(f"| `{r['path']}` | `{r['sha256']}` |\n" for r in rows)+
    '\nPatch bao gồm cả file mới; snapshot ZIP chỉ có source, không key/data/cache. Report tooling có hash trong JSON. Không gán toàn bộ mixed commit cho H02.\n',encoding='utf-8')
print(json.dumps({'source_file_count':len(rows),'report_tool_count':len(tools),'snapshot_sha256':ledger['snapshot_sha256']}))
