"""Chuẩn bị nguồn E01 bằng hash sampling, không import search hay đọc system outputs."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import re

import pandas as pd
from backend.common.frame_assets import resolve_frame_path
from data.config.evaluation_foundation import DATASET_VERSION, SPLIT_TARGETS, SAMPLING_SEED, FRAME_MAP_PATH
from dev_set.tools.e01_schema import Annotation
from dev_set.tools.e01_dataset import initialize, quality

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def collect_video_ids(value):
    """Chỉ lấy metadata video để loại nguồn đã dùng; không đọc/áp đáp án cũ vào GT mới."""
    result = set()
    if isinstance(value, dict):
        for k, v in value.items():
            if k in ('video_id', 'target_video', 'video') and isinstance(v, str) and re.fullmatch(r'L\d+_V\d+', v):
                result.add(v)
            elif isinstance(v, (dict, list)):
                result |= collect_video_ids(v)
    elif isinstance(value, list):
        for item in value:
            result |= collect_video_ids(item)
    return result


def main():
    old_registry_path = ROOT/'reports/post_preliminary_cycle_20260911/evaluation_registry.json'
    registry = json.loads(old_registry_path.read_text(encoding='utf-8'))
    registry.update(schema_version='e01.registry.v1', updated_at=datetime.now(timezone.utc).isoformat(),
                    previous_registry={'path':old_registry_path.relative_to(ROOT).as_posix(), 'sha256':sha(old_registry_path)},
                    ready_independent_set=None, proposed_new_set_status='source_packets_pending_human_queries_gt',
                    h02_contract_state='PROMOTED_CORRECTNESS_ONLY', h01_performance_baseline='NOT_PROMOTED')
    existing = {e['path'] for e in registry['sets']}
    for path in sorted(set((ROOT/'dev_set/ground_truth').glob('*.jsonl')) | set((ROOT/'data/queries').glob('*.jsonl')) |
                       set((ROOT/'dev_set/manifests').glob('*.json')) | set((ROOT/'dev_set/queries').glob('*.jsonl'))):
        relative = path.relative_to(ROOT).as_posix()
        if relative in existing:
            continue
        competition = any(s in path.stem for s in ('round', 'sotuyen', 'official'))
        role = 'competition_postmortem_consumed' if competition else 'diagnostic_not_independent'
        registry['sets'].append({'path':relative, 'sha256':sha(path), 'independent':False,
                                 'role_for_new_cycle':role, 'human_verified_all':False,
                                 'rationale':'Không nâng vai trò khi thiếu bằng chứng độc lập; metadata/GT file không là dataset mới.'})
    for entry in registry['sets']:
        entry['current_sha256'] = sha(ROOT/entry['path'])
        entry['allowed_e01_roles'] = (['train_tuning', 'regression'] if entry['role_for_new_cycle']=='tuning'
                                     else ['competition_postmortem', 'diagnostic'] if 'competition' in entry['role_for_new_cycle']
                                     else ['regression', 'diagnostic'])
        entry['independent'] = False
    registry['proposed_e01'] = {'dataset_version':DATASET_VERSION, 'target':SPLIT_TARGETS,
                              'status':'pending_human_creation_verification_and_leakage_review', 'independent':False}
    registry_path = ROOT/'dev_set/evaluation_registry.json'
    if registry_path.exists():
        saved = json.loads(registry_path.read_text(encoding='utf-8'))
        registry['updated_at'] = saved['updated_at']
        if registry != saved:
            raise ValueError('Registry đã đổi; không ghi đè khi resume')
    else:
        write(registry_path, registry)

    consumed = set(); sources = []
    # Chỉ metadata trong query/GT/manifest đã có; không dùng trace/submission/candidate ranking.
    for path in sorted(set((ROOT/'dev_set/ground_truth').glob('*.json*')) |
                       set((ROOT/'dev_set/queries').glob('*.jsonl')) |
                       set((ROOT/'dev_set/manifests').glob('*.json')) |
                       set((ROOT/'data/queries').glob('*.jsonl'))):
        text = path.read_text(encoding='utf-8-sig')
        values = [json.loads(line) for line in text.splitlines() if line.strip()] if path.suffix=='.jsonl' else [json.loads(text)]
        ids = collect_video_ids(values)
        consumed |= ids
        sources.append({'path':path.relative_to(ROOT).as_posix(), 'sha256':sha(path), 'video_ids':sorted(ids)})
    fm = pd.read_parquet(ROOT/FRAME_MAP_PATH)
    videos = sorted(set(fm.video_id.astype(str)) - consumed,
                    key=lambda v:hashlib.sha256(f'{SAMPLING_SEED}|{v}'.encode()).hexdigest())
    selected = videos[:44]
    if len(selected)!=44:
        raise ValueError('Thiếu source video chưa loại theo metadata')
    catalog = {'schema_version':'e01.source.v1', 'created_at':datetime.now(timezone.utc).isoformat(),
               'frame_map':{'path':FRAME_MAP_PATH,'sha256':sha(ROOT/FRAME_MAP_PATH)}, 'videos':{}}
    raw_videos = {p.stem:p.relative_to(ROOT).as_posix() for p in (ROOT/'data/raw').rglob('*.mp4')}
    cards = {}; pixel_groups = defaultdict(set)
    for video in selected:
        frames=[]; rows=fm[fm.video_id==video].sort_values('frame_idx')
        for row in rows.itertuples(index=False):
            key=str(row.kf_id); frame=int(row.frame_idx)
            path=resolve_frame_path(video_id=video, frame_idx=frame, keyframe_id=key).path
            if path is None:
                continue
            path=Path(path)
            ref={'video_id':video,'frame_idx':frame,'keyframe_id':key,
                 'path':path.relative_to(ROOT).as_posix(),'sha256':sha(path)}
            frames.append(ref); pixel_groups[ref['sha256']].add(video)
        catalog['videos'][video]={'frames':frames,'raw_video_path':raw_videos.get(video),
                                  'indexed_frame_count':len(rows), 'fps_values':sorted(set(float(v) for v in rows.fps)),
                                  'human_source_review':'pending'}
        cards[video]=frames
    catalog_path=OUT/'source_catalog.json'; write(catalog_path,catalog)
    source_hash=sha(catalog_path)
    entries=[]; offset=0
    for split,tasks in SPLIT_TARGETS.items():
        for task,count in tasks.items():
            for i in range(1,count+1):
                video=selected[offset]; offset+=1
                query_id=f"E01_{'VAL' if split=='validation' else 'HOLD'}_{task}_{i:02d}"
                entry=Annotation(query_id=query_id,task_type=task,split=split,video_id=video,
                                 source_manifest_sha256=source_hash,source_version='e01.source.v1').model_dump()
                entries.append(entry)
    plan={'dataset_version':DATASET_VERSION,'source_catalog':catalog_path.relative_to(ROOT).as_posix(),
          'source_catalog_sha256':source_hash,'sampling_seed':SAMPLING_SEED,'entries':entries}
    write(OUT/'sampling_plan.json',plan)
    write(OUT/'sampling_audit.json',{'seed':SAMPLING_SEED, 'selection':'SHA256(seed|video_id) ascending; first 44 eligible videos',
          'eligible_videos':len(videos),'corpus_videos':int(fm.video_id.nunique()),'excluded_video_ids':sorted(consumed),
          'exclusion_sources':sources,'selected_videos':selected,'split_assigned_before_evaluation':True,
          'system_outputs_read_for_sampling_or_gt':False,'query_texts_created':0,
          'limitations':['Exclusion metadata không chứng minh chưa từng thấy video; human exposure review vẫn bắt buộc.',
                         'Exact file hash chỉ phát hiện ảnh byte-identical; near-duplicate/repeated event cần người xem.',
                         'Keyframe sampling không chứng minh biên sự kiện chính xác; thiếu video dày thì pending.'],
          'exact_shared_frame_hashes':[{'sha256':h,'videos':sorted(v)} for h,v in pixel_groups.items() if len(v)>1],
          'video_distribution':dict(Counter(v.split('_')[0] for v in selected))})
    initialize(OUT/'dataset_v1',plan)
    write(OUT/'dataset_quality.json',quality(OUT/'dataset_v1'))
    write(OUT/'annotation_schema.json',Annotation.model_json_schema())
    templates=OUT/'annotation_templates'; templates.mkdir()
    sections=[]
    for entry in entries:
        qid=entry['query_id']; video=entry['video_id']
        write(templates/f'{qid}.json',entry)
        imgs=''.join(f'<figure><img loading="lazy" src="{html.escape((ROOT/f["path"]).as_uri())}"><figcaption>frame {f["frame_idx"]} · {html.escape(f["keyframe_id"])}</figcaption></figure>' for f in cards[video])
        source=catalog['videos'][video]
        video_link=(f'<a href="{html.escape((ROOT/source["raw_video_path"]).as_uri())}">Mở video nguồn</a>' if source['raw_video_path'] else 'Chưa có video nguồn local; cửa sổ/sự kiện cần ảnh dày phải để PENDING.')
        sections.append(f'<section id="{qid}"><h2>{qid} · {video}</h2><p>{entry["task_type"]} · nguồn BTC · PENDING</p><p>{video_link}</p><p><a href="annotation_templates/{qid}.json" download>Tải mẫu nhãn trống</a> · Chưa có query, answer hoặc cửa sổ GT.</p><details><summary>Xem {len(cards[video])} keyframe theo frame tuyệt đối (không phải ranking)</summary><div class="frames">{imgs}</div></details></section>')
    document='''<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>E01 · Gán nhãn từ nguồn</title><style>body{font:16px system-ui;max-width:1400px;margin:32px auto;padding:0 20px;background:#f7f8fa;color:#182230}h1{font-size:30px}section{background:white;padding:20px;margin:20px 0;border:1px solid #d5dce5;border-radius:12px}.frames{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:10px}figure{margin:0}img{width:100%}figcaption{font-size:12px}summary{cursor:pointer;padding:12px;background:#eaf0f6}a{color:#145ac0}</style><h1>E01 · Tạo query và ground truth từ nguồn BTC</h1><p>44 gói nguồn, chưa có câu hỏi/GT đã xác minh. Không hiển thị kết quả hệ thống. Người duyệt tạo query và nhãn sau khi xem nguồn. Đừng dùng submission hoặc AI answers làm đáp án. Xem ANNOTATION_GUIDE.md để ghi revision và kiểm leakage trước seal.</p>'''+''.join(sections)+'</html>'
    (OUT/'annotation_packet.html').write_text(document,encoding='utf-8')
    print(json.dumps({'packets':44,'source_frames':sum(len(v) for v in cards.values()),'human_verified':0,'source_catalog_sha256':source_hash,'provider_calls':0}))


if __name__=='__main__':
    main()
