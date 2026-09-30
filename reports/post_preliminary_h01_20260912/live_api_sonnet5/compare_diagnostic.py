"""So toàn bộ 30 query diagnostic; không bỏ semantic field khi có khác biệt."""
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def read_arm(name):
    path = ROOT / name
    manifest = json.loads((path / 'runtime_manifest.json').read_text(encoding='utf-8'))
    rows = [json.loads(line) for line in (path / 'queries.jsonl').read_text(encoding='utf-8').splitlines()]
    summary = json.loads((path / 'measurements.json').read_text(encoding='utf-8'))
    return path, manifest, rows, summary


def semantic(row):
    result = {key: copy.deepcopy(row.get(key)) for key in (
        'input', 'query_sha256', 'runtime_manifest_id', 'task_output', 'export_status',
        'export_ranking', 'frame_mapping', 'mapping_violations', 'export_violations',
        'errors', 'candidate_mapping', 'export_files')}
    # Chỉ bỏ thời gian đo; timestamp_ms của video và mọi điểm/rank vẫn giữ.
    result['task_output'].pop('timings', None)
    return result


def differences(left, right, path=''):
    if type(left) is not type(right):
        return [path]
    if isinstance(left, dict):
        return [p for key in sorted(left.keys() | right.keys())
                for p in differences(left.get(key), right.get(key), path + '/' + key)]
    if isinstance(left, list):
        if len(left) != len(right):
            return [path + '/length']
        return [p for i, (a, b) in enumerate(zip(left, right))
                for p in differences(a, b, path + '/' + str(i))]
    return [] if left == right else [path]


def main():
    on_path, on_manifest, on_rows, on_summary = read_arm('cache_only_diagnostic_on_current')
    off_path, off_manifest, off_rows, off_summary = read_arm('cache_only_diagnostic_off')
    expected = json.loads((ROOT / 'queries.json').read_text(encoding='utf-8'))
    assert [r['input'] for r in on_rows] == [r['input'] for r in off_rows] == expected
    records = []
    for on, off in zip(on_rows, off_rows):
        paths = differences(semantic(on), semantic(off))
        csv_equal = {}
        for name in (on.get('export_files') or {}).keys() | (off.get('export_files') or {}).keys():
            a, b = on_path / 'submission' / name, off_path / 'submission' / name
            csv_equal[name] = a.is_file() and b.is_file() and a.read_bytes() == b.read_bytes()
        records.append({'query_id': on['input']['query_id'], 'semantic_equal': not paths,
                        'different_paths': paths, 'csv_equal': csv_equal,
                        'export_status': on['export_status'],
                        'on_provider_calls': on['usage_delta']['calls'],
                        'off_provider_calls': off['usage_delta']['calls']})
    result = {'queries': len(records), 'identity_equal': on_manifest['identity'] == off_manifest['identity'],
              'on_identity_id': on_manifest['manifest_id'], 'off_identity_id': off_manifest['manifest_id'],
              'semantic_equal_queries': sum(r['semantic_equal'] for r in records),
              'csv_equal_files': sum(v for r in records for v in r['csv_equal'].values()),
              'on': on_summary, 'off': off_summary, 'records': records,
              'excluded_semantic_fields': ['task_output.timings'],
              'observer_ignored': ['search_calls', 'instrumentation'],
              'measurement_fields_not_semantic': ['seconds', 'usage_delta', 'cache_after', 'cache_after_id'],
              'comparison_script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'decision': 'DO NOT PROMOTE: diagnostic resource gaps and 25 queries without complete LLM cache',
              'independent_accuracy_claim': False}
    (ROOT / 'comparison.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('queries', 'identity_equal', 'semantic_equal_queries', 'csv_equal_files', 'decision')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
