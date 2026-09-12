"""Khóa toàn bộ bốn tập có sẵn; chỉ đọc lịch sử và ghi manifest H02 riêng."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
groups = [
    ('H01_CACHE_ONLY', 'reports/post_preliminary_h01_20260912/live_api_sonnet5/cache_only_diagnostic_on_current/queries.jsonl', None),
    ('TUNE_LEGACY', 'dev_set/results/run_20260820_2349/candidates.jsonl', 'dev_set/results/run_20260820_2349/answers.jsonl'),
    ('ROUND2_OPERATOR_HISTORY', 'submissions/round2/trace.jsonl', None),
    ('ROUND3_OPERATOR_HISTORY', 'submissions/round3/trace.jsonl', None),
]

def identity(path):
    data = path.read_bytes()
    return {'path': path.relative_to(ROOT).as_posix(), 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}

rows = []
for name, source, answers in groups:
    row = {'name': name, 'source': identity(ROOT/source),
           'record_count': len([line for line in (ROOT/source).read_text(encoding='utf-8-sig').splitlines() if line.strip()])}
    if answers:
        row['answers_source'] = identity(ROOT/answers)
    rows.append(row)
csvs = [identity(p) for folder in ('submissions/round2','submissions/round3') for p in sorted((ROOT/folder).rglob('*.csv'))]
manifest = {'experiment_id': 'PP-H02-OFFLINE-20260912', 'selection': 'Toàn bộ record của bốn trace, toàn bộ CSV round2/round3; không lọc theo outcome.',
            'groups': rows, 'csv_files': csvs, 'paid_provider_calls_authorized': 0}
target = OUT/'replay_input_manifest.json'
assert not target.exists(), 'Manifest đã khóa; không ghi đè'
target.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'groups':[{k:r[k] for k in ('name','record_count')} for r in rows], 'csv_files':len(csvs)},ensure_ascii=False))
