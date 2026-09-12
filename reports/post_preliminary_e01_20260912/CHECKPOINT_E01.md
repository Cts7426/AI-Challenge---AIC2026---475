# STOP POINT E01 — Evaluation foundation

**NOT READY FOR H03A.** Đã chuẩn bị source identity, registry, source-only annotation packets, schema/tooling và preregistration. Chưa có human-created/verified query/GT mới; hai manifest chỉ là draft, không có sealed held-out. H02 correctness đã được người vận hành phê duyệt; H01 performance baseline vẫn NOT PROMOTED.

## A. Post-H02 frozen source identity

HEAD tại lúc bắt đầu `7842d11c3497a6b996959bb2484d44f055a285c6`, branch `wip/codex-h01-20260912`, tree `e89fe5cab3e72b0599fd77f402911e50c5cab838`. H02 source `4fe4f2e`; H02 checkpoint `7842d11`. [CURRENT_STATUS.md](CURRENT_STATUS.md) ghi quyết định và claim được nhận, không sửa checkpoint lịch sử.

[post_h02_source_identity.json](post_h02_source_identity.json) và [post_h02_source.zip](post_h02_source.zip) đóng 213 source/config/test files trước E01. Source-list hash `f3dc0f5c1efaaf51a5dbcd4fea8b7f251c619621a5417b8f69d545b049541f84`; ZIP hash `df463e2837685d5bdd8283ae8699b1252e968a76f98224e6614447ee12ee533e`. Không có source WIP H01/H02; 3 H01 report files modified và các cache-only audit/context_handoff untracked được ghi riêng trong [starting_git_status.txt](starting_git_status.txt), không discard/stage vào source E01.

[resource_capture/runtime_manifest.json](resource_capture/runtime_manifest.json) hash canonical identity **`36441b9b8548fa348c4f15daf26117dc1b945c044729c203bc03df1f0ffb98e4`**; collector bắt đầu trước khi thêm source E01, source list không chứa file E01. Full content digest của 177.321 raw images; ES metadata 873, objects 177.321, OCR 160.393, ASR 13.415; Milvus keyframes 177.321, hai ASR collections mỗi collection 13.415. Hashed counts bằng counts; `reproducibility_gaps=[]`.

[resource_identity_summary.json](resource_identity_summary.json) chứa config/runtime/scorer/index details. Interpreter `.venv/Scripts/python.exe`, Python 3.14.0, package versions, model/preprocess/weights, public environment whitelist và cache/data hashes được lưu. Model runtime giữ api/claude-sonnet-5, cache-only; không kiểm key/credit qua API. Đây là read-only fingerprint, không phải performance baseline hay khóa DB chống ghi; phải recapture/compare khi chạy paired baseline/candidate sau này. Milvus báo dùng client timestamp cho iterator; không khẳng định atomic snapshot qua mọi service.

## B. Updated evaluation registry

[dev_set/evaluation_registry.json](../../dev_set/evaluation_registry.json): 32 entries, giữ nguyên role_for_new_cycle của cả 18 entries registry trước, thêm provenance/hash và vai trò thận trọng cho query/GT/manifest khác. Tune/generated tuning giữ train/tuning/regression; dress25/legacy holdouts giữ diagnostic consumed; batch1_holdout13 consumed regression partial verified; competition-derived chỉ diagnostic/postmortem, không independent. Hash/link registry trước được giữ; không sửa registry lịch sử. Ready independent set = null.

## C. Dataset creation protocol

[DATASET_PROTOCOL.md](DATASET_PROTOCOL.md), [sampling_plan.json](sampling_plan.json), [sampling_audit.json](sampling_audit.json). Target **24 KIS / 12 QA / 8 TRAKE**, chia trước evaluation thành mỗi split **12/6/4**. Từ 873 video, loại 147 video ID đã xuất hiện trong query/GT metadata; còn 726, chọn 44 bằng SHA256 seed/video cố định. Không dùng retrieval ranking/submission candidates/system answers/AI proposals để chọn GT. Mỗi video một slot; split đã gán trước bất cứ run nào.

Đây là **44 gói nguồn**, không phải 44 query đã tạo. Metadata exclusion chưa chứng minh independence; prior exposure/grouping vẫn cần người duyệt. Nếu cần thay video vì duplicate hoặc không xác minh được, giữ version này và lập sampling version mới trước seal, không đổi GT vì prediction.

## D. Annotation schema

[annotation_schema.json](annotation_schema.json), [dev_set/tools/e01_schema.py](../../dev_set/tools/e01_schema.py), schema `e01.annotation.v1`. Có query ID/task/split/video, source version/hash, verifier/status/date/notes, grouping và evidence refs/hash.

KIS: acceptable windows/reference frames. QA: evidence region, acceptable forms, answerability, exact normalization và registered semantic variants policy. TRAKE: ordered events, windows/evidence per event, evidence-backed/ambiguous, temporal tolerance và justification. Pydantic còn kiểm điều kiện liên trường không biểu diễn hết trong JSON Schema. Zero/negative có thể là label hợp lệ; không tạo placeholder. Frame tuyệt đối chỉ từ map/source; không nới windows sau prediction.

## E. Annotation tooling changes

[dev_set/tools/e01_dataset.py](../../dev_set/tools/e01_dataset.py): init/record/quality/seal/consume/fork-correction, exclusive revision writes, hash chain, old/new label history, explicit human provenance, source/evidence hash check và leakage gates. Không sửa retrieval hoặc tools GT cũ. Source/task/video/split không sửa tại chỗ trong revision.

Source E01 commit riêng **`e387366`**, đúng 5 file mới; [E01_change_ledger.json](E01_change_ledger.json) và [E01_source_snapshot.zip](E01_source_snapshot.zip) giữ file/hash/bytes. Đây là tooling/protocol source, không phải H03 algorithm change. Report artifact dùng `.gitattributes` cục bộ để giữ nguyên bytes/hashes khi lưu Git.

[annotation_packet.html](annotation_packet.html) hiển thị **9.257 keyframe theo thứ tự frame**, có 44 template trống và hướng dẫn [ANNOTATION_GUIDE.md](ANNOTATION_GUIDE.md). Không hiển thị system output. 9.257 local image links đã kiểm tồn tại; không dùng external images. Tool dùng shared frame resolver; gallery cũ chỉ tái dùng ý tưởng, không tái dùng đường sửa manifest tại chỗ.

Seal không được tạo khi thiếu GT/grouping hoặc shared-frame review. Sau seal không record đè; consume chỉ một lần và phải trước held-out execution/inspection. Correction version giữ parent/hash/lý do và không khôi phục independence nếu parent đã consumed. Chưa có evaluator bridge cho E01 schema; H03a design ghi rõ gate này cần được thực hiện sau khi được phép.

## F. Human verification status

**Queries proposed: 0. Human verified: 0. Pending source packets: 44. Rejected: 0.** Không có tên/verifier/date được bịa cho dataset thật. Chưa đo agreement/disagreement vì chưa có reviewer nào. Legacy selfcheck gaps giữ holdout13 **6/13 verified**, round1 **0/25 GT**; không đổi manifest để lấy xanh.

## G. Validation manifest/hash

[validation_manifest.draft.json](validation_manifest.draft.json): 22 reserved slots, KIS/QA/TRAKE **12/6/4**, status `DRAFT_UNSEALED_PENDING_HUMAN`, eligible_for_evaluation=false, sealed_at=null. SHA-256 **`41954fa3a2c12171e4f670bd6dfc634503be89a5bf235000d7904d43e82c574b`**. Query/GT hashes null vì chưa có query/GT; annotation template hashes không được xem là verified GT hashes.

## H. Sealed held-out manifest/hash

[sealed_heldout_manifest.draft.json](sealed_heldout_manifest.draft.json): 22 reserved slots, **12/6/4**, cùng trạng thái DRAFT/UNSEALED. SHA-256 draft **`9445f9b7464bcf649c83ee06f540a3fb691bbef2c340b8d692c0a5c70c08b8c5`**. **Actual sealed manifest/hash: chưa có.** Không gọi draft hash là seal đã hoàn tất; không mở held-out hoặc chạy candidate model.

## I. Leakage/near-duplicate audit

[leakage_audit.json](leakage_audit.json): video IDs giữa split không giao. Có **86 nhóm exact shared frame hash**, tạo **23 cặp video qua split** cần human review. Chưa xác định bao nhiêu near-duplicate video/event group thật. Các nhóm human duplicate/event và prior exposure đều pending; wording chưa so được vì query còn trống. Không gọi dataset independent.

Shared image có thể là intro/stock footage hoặc sự kiện lặp; cần người xem và ghi giải thích. Nếu duplicate/event thật qua split, seal tiếp tục bị chặn và cần sampling version mới. Bộ phát hiện wording + kiểm group/video + exact-shared-frame gate đã có test; không tự tuyên bố 0 leakage chỉ vì khác video ID.

## J. Dataset quality report

[dataset_quality.json](dataset_quality.json): 44 source videos/packets, 0 query, 0 verified, 44 pending. Distribution L26=27, L25=7, L30=6, L27/L23/L29/L28 mỗi nhóm=1; task reservations 24/12/8, validation/held-out mỗi bên 22. Sự mất cân bằng theo nguồn được báo, không chỉnh mẫu theo performance.

Raw source MP4 local: **0/44**; source frames available 9.257. Ambiguous cases chưa được human rà soát (44 pending), không coi 0 event label hiện có là 0 ambiguity thật. Frame thưa không chứng minh onset/order/window; item cần dense evidence phải chờ nguồn đủ. Hash source catalog **`992b66868a3c7f642394c63b87144840c57727717b53d6bdfb9fb693b172bdef`**. Dataset version `e01-v1`, revision 1 giữ nguyên; source-only plan còn chưa seal.

## K. Proposed H03a diagnostic protocol

[H03A_PREREGISTRATION.md](H03A_PREREGISTRATION.md): design only. Đo WHERE IS THE CORRECT CANDIDATE LOST, theo raw sources/nomination → fusion → grouping/order/truncation → rerank → final search → allocation/export. Code hiện grouping trước rerank; không đổi execution order để khớp sơ đồ giả định. Multi-anchor phải trace từng search và merge.

H01 observer có raw/fused/finalized/reranked/final/task/export snapshots; còn thiếu snapshot candidate nomination, các bước trong finalized, allocator admission/frame-generation và một số timing. Ghi rõ not_observed, chưa triển khai hook mới. Failure taxonomy A–F gồm raw absence, fusion, rerank, grouping, allocation và indexed-frame unavailability; không mặc định allocator là lỗi.

## L. Preregistered H03 metrics

Protocol K đăng ký video R@1/5/20/50/100 và frame R@1/5/20/50/100 riêng; video unique rank và row-budget hit báo tách nhau. Fixed verified windows; conditional frame distance khi video đúng; availability before fusion; survival after fusion/rerank/grouping/allocation; moved-out-of-top100 tách removal/replacement; duplicate/shot coverage; mapping violations; latency/stage timing khi có clock đáng tin. Định nghĩa numerator/denominator, failures/missing stages và lineage cho generated frames được ghi trong bảng metrics. Không đo các số này ở E01.

## M. Exact baseline requirements

Baseline/candidate cùng query/GT/split/seal, translations bytes/provenance, source base trừ một intended patch, model/encoder/weights/preprocess, index content, raw/derived/map, config, scorer, cache policy và runtime protocol. Resource đổi → baseline chạy lại; missing identity không là equality. Không có baseline end-to-end hợp lệ khi translation exact-cache miss. Fixed-translation chỉ là component diagnostic nếu translation đã tồn tại và đóng provenance; E01 query trống nên chưa có arm này. Không đổi model/provider hoặc dùng số dư API để hoàn tất.

## N. Remaining blockers và kiểm chứng

Blockers: human tạo/xác minh 44 query/GT; kiểm 23 cặp shared frames + near-duplicate/event/exposure/wording; bổ sung nguồn đủ cho trường hợp temporal chưa xác minh; version/split điều chỉnh nếu cần trước seal; seal thật/query-GT hashes; H03a loader/trace gaps và quyền thực hiện H03 còn chưa có. Không thể hoàn tất human-dependent dataset bằng suy đoán của agent.

Focused E01 **28 passed**; full suite **1009 passed, 1 skipped**, exit 0. **Selfcheck cuối exit 1**, suite bên trong vẫn 1009 passed/1 skipped; thiếu duy nhất holdout13 6/13 verified và round1 0/25 GT. Bằng chứng sau review fix: [selfcheck_final_command.json](selfcheck_final_command.json)/[selfcheck_final.log](selfcheck_final.log). Development preflight trong selfcheck 20 đạt/0 hỏng/2 skip. E01 không thay retrieval, nên không biến kết quả này thành cải thiện retrieval. [REVIEW_E01.md](REVIEW_E01.md) ghi review và giới hạn.

Tất cả lệnh qua hard guard trong [run_check.py](run_check.py), external dispatch/provider calls **0**. Lần packet đầu lỗi API resolver được lưu và sửa; không giấu log. [integrity_verification.json](integrity_verification.json): 213 existing source/config files, 69 H02 evidence files và 36 historical query/GT/manifest source files giữ hash; không sửa historical competition artifacts. WIP người dùng/H01 giữ riêng.

Lệnh kiểm công cụ:

```powershell
.venv\Scripts\python.exe reports/post_preliminary_e01_20260912/run_check.py verify_e01 -m pytest dev_set/tests/test_e01_dataset.py -q
.venv\Scripts\python.exe -m dev_set.tools.e01_dataset quality --dataset reports/post_preliminary_e01_20260912/dataset_v1
```

## O. Recommendation

**NOT READY FOR H03A.** Phần tooling/protocol/source identity đã được chuẩn bị; dữ liệu độc lập có human verification và seal vẫn là blocker. Việc tiếp theo là người vận hành tạo/duyệt nhãn từ packet, giải quyết leakage/thiếu nguồn và chốt dataset version trước seal. H02 giữ PROMOTED CORRECTNESS; H01 performance baseline vẫn NOT PROMOTED. Dừng tại E01; không triển khai H03a/H03b/H04/H05, không tạo report v2, không gọi paid APIs.
