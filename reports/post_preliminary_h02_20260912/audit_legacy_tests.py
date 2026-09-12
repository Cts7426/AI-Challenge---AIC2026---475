"""Liệt kê từng test cũ đổi trực tiếp/qua fixture; không sửa RED hay lịch sử."""
import ast
import json
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
paths=[p for p in subprocess.check_output(['git','--no-optional-locks','diff','--name-only'],cwd=ROOT,text=True).splitlines()
       if p.startswith(('tests/','dev_set/tests/')) and p.endswith('.py')]
rows=[]
for path in paths:
    old=subprocess.check_output(['git','show',f'HEAD:{path}'],cwd=ROOT,text=True,encoding='utf-8')
    new=(ROOT/path).read_text(encoding='utf-8')
    before={n.name:ast.dump(n,include_attributes=False) for n in ast.parse(old).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
    after={n.name:n for n in ast.parse(new).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
    for name,node in after.items():
        direct=name in before and ast.dump(node,include_attributes=False)!=before[name]
        shared=path=='tests/test_run.py' and name.startswith('test_') and any(a.arg=='chay' for a in node.args.args)
        renamed=name=='test_pipeline_toan_refusal_ngan_thi_needs_review_khong_nop_sentinel'
        if not name.startswith('test_') or not (direct or shared or renamed):continue
        category='B. BAD/INCOMPLETE FIXTURE'
        old_expect='Fixture success QA không có hypothesis/evidence; assertion behavior còn giữ.'
        new_expect='Fixture cung cấp evidence/provenance tường minh; giữ kiểm result/order/resume/ZIP.'
        why='Gate mới kiểm support trước success; không exempt test khỏi gate và không xóa assertion cũ.'
        if renamed:
            category='A. OLD CONTRACT INTENTIONALLY SUPERSEDED'
            old_expect='Mọi shot refusal vẫn phải tạo TODO hypotheses để nộp.'
            new_expect='Answer rỗng, needs_review, hypotheses rỗng, attempts còn.'
            why='User yêu cầu loại fake success; test chặt hơn ở trạng thái và evidence, RED gốc được giữ.'
        elif name=='test_runner_dung_hypotheses_va_fail_missing_evidence':
            category='A. OLD CONTRACT INTENTIONALLY SUPERSEDED'
            old_expect='Thiếu answer/evidence ném SolveQueryError retryable missing_evidence.'
            new_expect='needs_review, failure_class=None, retryable=False; answers rỗng và candidate còn.'
            why='Abstention không phải crash; phần test positive portfolio giữ nguyên.'
        elif name=='test_qa_va_trake_khong_mat_metadata_hien_co':
            category='A. OLD CONTRACT INTENTIONALLY SUPERSEDED'
            old_expect='Trace chỉ có answer_shot_id vẫn giữ answer_text như success.'
            new_expect='Trace y nguyên, needs_review, review_answer_text giữ đỏ; TRAKE metadata giữ nguyên.'
            why='Không còn giả sử legacy provenance thiếu là support; tăng kiểm dữ liệu review.'
        elif name=='test_apply_append_record_va_trace_day_du':
            category='C. EXISTING BEHAVIOR THAT MUST STILL BE PRESERVED'
            old_expect='Manual override có evidence vẫn success và append đủ100 dòng.'
            new_expect='Giữ mọi assertion; thêm output_origin=operator_assisted.'
            why='Không loại workflow operator được phép; chỉ phân biệt nguồn tự động.'
        elif name=='test_checkpoint_ghi_ngay_sau_moi_cau':
            old_expect='QA fixture không answer/evidence vẫn tính hoàn thành trước KeyboardInterrupt.'
            new_expect='Hai KIS success trước interrupt vẫn phải nằm bền trên đĩa; QA durability có ở tests resume QA khác.'
            why='Phép kiểm này cô lập flush/fsync; không giảm số completed query hoặc assertion mất dữ liệu.'
        elif name=='test_two_stage_cap_42_phu_text_main_image_va_expansion':
            old_expect='Payload evidence rỗng vẫn sinh x và tiêu thụ42 generation.'
            new_expect='Fixture có text evidence; giữ nguyên x,42 generation,trần42,14 vòng [1,2].'
            why='Cô lập kiểm budget khỏi missing-evidence gate; không giảm assertion ngân sách.'
        rows.append(dict(path=path,test=name,category=category,old_expectation=old_expect,new_expectation=new_expect,
                         reason=why,change='direct' if direct or renamed else 'shared chay fixture'))
(OUT/'legacy_test_change_audit.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
lines=['# Audit legacy tests H02','',f'{len(rows)} test được định danh; tính cả ảnh hưởng fixture dùng chung. RED.log giữ nguyên.','',
       '| Test | Loại | Cũ → mới và lý do |','|---|---|---|']
for row in rows:
    lines.append(f"| `{row['path']}::{row['test']}` | {row['category']} | {row['old_expectation']} → {row['new_expectation']} {row['reason']} |")
(OUT/'LEGACY_TEST_AUDIT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(f'{len(rows)} legacy test entries')
