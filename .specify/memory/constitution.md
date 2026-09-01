<!--
Sync Impact Report
- Version change: 1.0.0 -> 2.0.0
- Bump rationale: MAJOR — governance is redefined from an operational snapshot
  into a durable constitution; copied runtime values and campaign state are no
  longer constitutional mandates.
- Modified principles:
  - I. Một nền truy xuất, ranh giới rõ ràng -> III. Một năng lực, một đường chuẩn
  - II. Định danh, ánh xạ và provenance là bất biến -> II. Định danh và provenance
    đi trước sự tiện lợi
  - III. Retrieval chịu lỗi, cấu hình được và quan sát được -> IV. Retrieval đúng,
    quan sát được và suy giảm an toàn
  - IV. Bằng chứng tái lập quyết định thay đổi -> V. Bằng chứng tái lập quyết định
    promotion
  - V. Phạm vi sơ tuyển và an toàn release đi trước -> VI. Release fail-closed và
    quyền điều khiển thuộc operator; VII. Phạm vi nhỏ, đơn giản và đảo ngược được
- Added principles:
  - I. Nguồn sự thật có chủ sở hữu
  - VI. Release fail-closed và quyền điều khiển thuộc operator
  - VII. Phạm vi nhỏ, đơn giản và đảo ngược được
- Added sections:
  - Ma trận nguồn chính sách và bằng chứng invariant
  - Quy trình bằng chứng và cổng quyết định
- Removed sections:
  - Ràng buộc kỹ thuật và vận hành (replaced by source/invariant matrix)
  - Quy trình phát triển và cổng chất lượng (replaced by evidence gate matrix)
- Removed operational snapshots:
  - Campaign publication status, local workspace path, active slot budget,
    active Q&A mode, and other mutable release choices
- Follow-up TODOs: None
-->
# HCMAIC 2026 Multimedia Retrieval System Constitution

## Core Principles

### I. Nguồn sự thật có chủ sở hữu
Mỗi giá trị hoặc quyết định có thể thay đổi MUST có đúng một nguồn chuẩn chịu
trách nhiệm cho trạng thái hiện hành. Constitution này sở hữu governance và các
invariant bền vững đã ratify; nó MUST NOT sao chép trạng thái chiến dịch, lịch,
model, path, threshold, budget, weight hoặc policy vận hành thuộc nguồn khác.
Tài liệu phụ MUST tham chiếu nguồn chuẩn thay vì lặp lại giá trị có thể đổi.
`AGENTS.md` MAY restate invariant để thi hành nhưng MUST NOT âm thầm biến một
khác biệt thành governance mới; khác biệt đó MUST kích hoạt review amendment.

Thông tin chưa được xác nhận MUST được ghi rõ là chưa biết, kèm nguồn cần xác
nhận và tác động nếu giả định sai. Mâu thuẫn giữa các nguồn MUST được xử lý theo
ma trận nguồn chính sách bên dưới; code đang chạy không tự động hợp thức hóa một
vi phạm governance. Nguyên tắc này tồn tại để ngăn policy drift và để một thay
đổi chỉ cần được thực hiện, kiểm chứng và review tại đúng nơi sở hữu nó.

### II. Định danh và provenance đi trước sự tiện lợi
`keyframe_id` MUST được giữ làm khóa join Milvus, Elasticsearch và frame map.
`frame_id` dùng cho submit MUST là frame index tuyệt đối lấy từ frame map hoặc
nguồn frame tuyệt đối đã được xác minh; ordinal ảnh, tên file và hậu tố keyframe
MUST NOT được dùng để suy frame. Mọi caller cần ảnh MUST gọi
`backend.common.frame_assets.resolve_frame_path()` thay vì tự ghép path.

Manifest URL, archive đã audit, raw asset và dữ liệu dẫn xuất MUST là các lớp
tách biệt. Archive MUST có định danh, kích thước, checksum và trạng thái; dữ liệu
dẫn xuất MUST có provenance đủ truy về input, schema, model/config, code version
và job tạo ra nó. Loader MUST dùng natural key, chạy lại không sinh trùng và
MUST NOT phá dữ liệu tương thích của đợt trước. Khi provenance hoặc mapping chưa
đủ, hệ thống MUST fail closed ở cổng bị ảnh hưởng thay vì đoán. Những ràng buộc
này bảo vệ các lỗi join/frame vốn có thể chạy êm nhưng làm kết quả vô giá trị.

### III. Một năng lực, một đường chuẩn
Search trong `backend/retrieval/` MUST là nền chung; KIS, Q&A, TRAKE, API và batch
runner MUST gọi nó thay vì chép lại retrieval. Elasticsearch MUST chỉ được truy
cập qua `es_client.connect()`, Milvus qua `milvus_client.connect()`, và LLM chỉ
qua `llm()` trong `backend/llm/adapter.py`. Tầng export MUST chỉ validate và ghi
dữ liệu đã được cấp; nó MUST NOT tự retrieval, map hoặc suy frame.

Path, model, metric, weight và policy thay đổi được MUST có owner trong
`data/config/` hoặc nguồn runtime được chỉ định; caller MUST NOT hardcode bản sao.
Interface dùng chung MUST có contract rõ và test tại ranh giới. Một đường thực
thi thứ hai chỉ được tạo khi có use case khác biệt, owner, acceptance evidence
và kế hoạch hợp nhất hoặc loại bỏ; “nhanh hơn để viết” không phải lý do đủ.
Nguyên tắc này giảm hành vi lệch nhau và giữ mỗi lỗi có một nơi sửa chuẩn.

### IV. Retrieval đúng, quan sát được và suy giảm an toàn
Vector index và query MUST cùng L2-normalize, dùng metric được cấu hình nhất quán,
và mọi thay đổi không gian embedding MUST chứng minh parity bằng asset/model đúng.
Query expansion cho encoder có giới hạn token MUST dùng các câu ngắn encode riêng
và MUST NOT thêm màu, số lượng hoặc chi tiết không có trong query gốc.

Fusion đa nguồn MUST đọc cấu hình, giữ rank/contribution từng nguồn và MUST NOT
dùng ngưỡng similarity cứng nếu chưa có bằng chứng calibration. Mỗi nguồn search
MUST cô lập lỗi để một service hỏng không kéo sập toàn query; degradation MUST
được ghi vào trace thay vì bị che giấu. Model nặng MUST NOT nằm trên đường search
đồng bộ nếu chưa có budget latency/tài nguyên và bằng chứng promotion. Job nặng
MUST checkpoint/resume, append/flush theo lô và bỏ qua phần đã hoàn tất. Retrieval
chỉ đáng tin khi kết quả, đường lui và nguyên nhân suy giảm đều quan sát được.

### V. Bằng chứng tái lập quyết định promotion
Correctness fix và thay đổi invariant MUST có reproduction hoặc test tập trung,
sau đó chạy lớp regression phù hợp. Tuning MUST cô lập một thay đổi truy nguyên
được, có baseline, config snapshot và query-level diff. Tune MAY dùng để phát
triển; holdout MUST chỉ được mở và dùng theo policy promotion hiện hành. Ground
truth thiếu xác minh hoặc provenance MUST NOT được dùng để tuyên bố promotion.

So sánh có LLM MUST dùng cùng evidence/cache, runtime fingerprint và scorer
policy; hai lần gọi ngẫu nhiên không tạo thành A/B test. Mỗi run được dùng làm
bằng chứng MUST lưu đủ code revision, config, data manifest, command, log, score,
failure, runtime fingerprint và artefact đầu ra để replay. Không được tuyên bố
“hoàn tất”, “test xanh” hoặc “chất lượng tăng” nếu bằng chứng vừa nêu chưa tồn tại
trên đúng môi trường. Quyết định dựa trên artefact, không dựa trên trực giác hoặc
điểm đơn lẻ không tái lập.

### VI. Release fail-closed và quyền điều khiển thuộc operator
Release MUST dừng khi thiếu query/output, mapping, provenance, runtime identity,
validator, preflight hoặc artefact bắt buộc. Format và scorer MUST theo luật BTC
đã xác nhận trong nguồn chuẩn hiện hành; điểm chưa rõ MUST được ghi thành rủi ro
và xử lý bằng policy an toàn đã được operator phê duyệt. Chỉ package được chọn
tường minh, đã validate và có checksum mới đủ điều kiện nộp.

Provider/model LLM và các lựa chọn release có ảnh hưởng kết quả MUST do operator
đặt tường minh cho process chạy; preflight MUST báo lại chứ MUST NOT tự chọn, tự
gọi thử hoặc đổi provider. Một run/resume MUST giữ cùng runtime fingerprint;
khác fingerprint MUST tạo run mới hoặc dừng có giải thích. Receipt, checksum,
policy, config snapshot và log MUST được đóng băng cùng release. Fail closed bảo
vệ số lượt nộp hữu hạn và ngăn automation tự ý thay đổi quyết định của operator.

### VII. Phạm vi nhỏ, đơn giản và đảo ngược được
Công việc MUST bám ưu tiên, deadline và phạm vi chiến dịch trong nguồn kế hoạch
hiện hành. Với một operator, task P0/P1 MUST được xếp tuần tự trừ khi kế hoạch đã
chứng minh các nhánh độc lập và đủ năng lực vận hành. Mỗi thử nghiệm MUST là thay
đổi nhỏ nhất có thể đo; độ phức tạp mới MUST có giả thuyết, chi phí, tiêu chí bỏ
và bằng chứng tốt hơn giải pháp đơn giản hiện có.

Thay đổi MUST ưu tiên config-gated, idempotent và có rollback/migration rõ ràng.
Code cũ MAY được giữ nếu không vi phạm invariant, không cản đường chuẩn và chi phí
loại bỏ lớn hơn rủi ro duy trì. Khi sát deadline, phạm vi sửa MUST thu hẹp theo
runbook/`AGENTS.md`; constitution này không đóng cứng một mốc giờ hoặc danh sách
feature cho mọi đợt. Mục tiêu là tối đa hóa kết quả vận hành với ít trạng thái,
ít đường chạy và ít quyết định không thể đảo ngược nhất.

## Ma trận nguồn chính sách và bằng chứng invariant

| Miền quyết định | Nguồn chuẩn | Quy tắc bắt buộc |
|---|---|---|
| Hướng dẫn agent, bối cảnh và ưu tiên hiện hành | `AGENTS.md` | Có ưu tiên thi hành cao nhất; lệch invariant bền vững MUST kích hoạt review amendment |
| Governance và invariant bền vững đã ratify | Constitution này | Sở hữu cách quản trị policy, bằng chứng, promotion, release và amendment |
| Luật BTC, format và scorer | `docs/contest.md` cùng nguồn BTC đã lưu | Chỉ thông tin đã xác nhận được dùng làm luật; thay đổi MUST có ngày/provenance |
| Kiến trúc và contract đã triển khai | `ARCHITECTURE.md`, code và tests | Docs MUST khớp code; lệch nhau là defect cần phân xử, không phải quyền chọn tùy ý |
| Knob runtime và policy thay đổi được | `data/config/` và biến môi trường được chỉ định | Giá trị MUST đọc tại runtime và lưu snapshot; tài liệu khác chỉ tham chiếu |
| Thứ tự task, deadline và trạng thái chiến dịch | `BUILD_TASKS.md` cùng plan hiện hành | Không đưa snapshot chiến dịch vào constitution; task chỉ hoàn tất khi có evidence |
| Một run/release cụ thể | Runbook và artefact versioned của run | Là bản ghi bất biến của command, fingerprint, input, output, checksum và receipt |

Các invariant dưới đây MUST có bằng chứng tương ứng trước khi thay đổi được nhận:

| Invariant | Bằng chứng tối thiểu |
|---|---|
| Join và frame tuyệt đối | Schema/key audit, biên frame và pixel parity trên mẫu phù hợp |
| Không gian vector | Norm gần 1, metric/index-query đồng nhất và encode parity với feature chuẩn |
| Loader/data delta | Manifest/checksum, row-count diff, idempotency và compatibility/migration record |
| Ranh giới client/adapter | Contract test hoặc search tĩnh chứng minh không có đường gọi trực tiếp ngoài owner |
| Retrieval chịu lỗi | Test lỗi từng nguồn, trace degradation và rank/contribution từng nguồn |
| Runtime có LLM | Evidence/cache cố định, provider/model/config fingerprint và replay command |
| Submission/release | Full-query completeness, validator, preflight, config snapshot, checksum và receipt |

Nếu nguồn chuẩn và bằng chứng mâu thuẫn, reviewer MUST phân loại đó là lỗi tài
liệu, lỗi implementation, dữ liệu stale hoặc thay đổi policy chưa ratify. Reviewer
MUST NOT chọn âm thầm nguồn thuận tiện nhất.

## Quy trình bằng chứng và cổng quyết định

Mọi thay đổi MUST được phân loại trước khi thực hiện và đi qua cổng tương ứng:

| Loại thay đổi | Bằng chứng bắt buộc trước khi nhận |
|---|---|
| Governance/tài liệu chuẩn | Template resolution, source cross-check, impact report, version/date và diff review |
| Correctness/invariant | Reproduction hoặc failing test, fix, focused test và regression liên quan |
| Data/schema/loader | Provenance, dry-run/count diff, idempotency, compatibility và migration/rollback |
| Vector/model/preprocess | Baseline, norm/metric guard, parity trên asset chuẩn, meta/schema và kế hoạch reindex |
| Retrieval/tuning | Một biến đổi truy nguyên được, baseline, query-level diff, tune và holdout theo policy hiện hành |
| LLM/Q&A | Evidence/cache cố định, fingerprint đồng nhất, replay semantic/exact và failure diff |
| Release | Test/promotion gate, clean checkpoint, release preflight, validator, checksum và receipt plan |

Quy trình tối thiểu gồm sáu bước:

1. **Xác định authority:** nêu nguồn chuẩn, acceptance criteria, invariant và dữ
   liệu/điều kiện chưa biết.
2. **Đóng baseline:** lưu trạng thái có thể tái lập trước thay đổi, gồm config và
   failure hiện hành; không trộn nhiều thử nghiệm chưa truy nguồn được.
3. **Thực hiện tối thiểu:** chỉ sửa phạm vi cần thiết; giữ interface và đường lui
   trừ khi migration đã được duyệt.
4. **Kiểm chứng đúng rủi ro:** chạy test/cổng trong bảng trên bằng đúng interpreter,
   data và service profile; dependency thiếu là lỗi môi trường cần sửa, không phải
   lý do hạ cổng.
5. **Quyết định tường minh:** accept, reject hoặc defer dựa trên policy promotion
   hiện hành; ghi query-level/failure diff và lý do.
6. **Đóng artefact:** cập nhật owner source, lưu reproduction command và chỉ đánh
   dấu task hoàn tất khi evidence tồn tại. Release tiếp tục qua Principle VI.

Postmortem MUST phân loại lỗi bằng taxonomy hiện hành trong `AGENTS.md` hoặc
artefact release. Taxonomy MAY thay đổi ở nguồn sở hữu mà không cần amend
constitution, miễn vẫn cho phép truy nguyên nguyên nhân và tạo task khắc phục.

## Governance

Constitution này ràng buộc spec, plan, task, review và release nhưng không thay
thế nguồn vận hành. `AGENTS.md` có ưu tiên thi hành cao nhất. Nếu `AGENTS.md`
khác một invariant đã ratify, agent MUST tuân thủ `AGENTS.md` cho tác vụ hiện tại,
ghi nhận conflict và kích hoạt review amendment trước khi coi khác biệt là policy
bền vững. Luật BTC đã xác nhận điều khiển format/scoring; code/config mô tả hành
vi thực tế nhưng MUST được sửa nếu vi phạm nguồn cấp cao hơn. Khi xung đột chưa
phân xử, phần việc bị ảnh hưởng MUST dừng; phần độc lập MAY tiếp tục nếu không
làm khó rollback.

Amendment MUST có: lý do; principle/section bị tác động; thay đổi trong ma trận
nguồn; compatibility và migration/rollback; Sync Impact Report; version đề xuất;
và phê duyệt của operator/maintainer được ủy quyền. Thay đổi giá trị runtime,
model, budget, lịch, trạng thái dữ liệu hoặc policy một đợt MUST được thực hiện ở
nguồn sở hữu và MUST NOT tự động làm phát sinh amendment.

Version tuân thủ semantic versioning:

- **MAJOR** khi bỏ, định nghĩa lại hoặc thay đổi quyền sở hữu/precedence theo cách
  không tương thích với governance trước.
- **MINOR** khi thêm principle, cổng hoặc nghĩa vụ kiểm chứng mới mà không phá
  nghĩa vụ hiện có.
- **PATCH** khi làm rõ, sửa lỗi hoặc cải thiện diễn đạt mà không đổi nghĩa vụ.

Compliance MUST được kiểm ở bốn thời điểm: khi duyệt spec/plan, trước khi nhận
thay đổi, trước release và trong postmortem. Constitution MUST được audit khi BTC
đổi luật, kiến trúc/data contract đổi lớn, hoặc postmortem phát hiện lỗ hổng mang
tính hệ thống. Ngoại lệ MUST có phạm vi, owner, lý do, kiểm soát bù, ngày hết hạn
hoặc trigger kết thúc; ngoại lệ hết hạn MUST bị gỡ hoặc ratify thành amendment.
Deadline không miễn các invariant về định danh, provenance, mapping, runtime
identity, format hoặc bằng chứng release.

**Version**: 2.0.0 | **Ratified**: 2026-09-01 | **Last Amended**: 2026-09-01
