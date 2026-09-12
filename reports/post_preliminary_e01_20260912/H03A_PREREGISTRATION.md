# H03a diagnosis — design only, protocol v1

Trạng thái: preregistered design, **chưa được phép implementation/run H03**. Câu hỏi: relevant video/frame bị mất ở đâu? Không giả định allocator là nguyên nhân. H03b chỉ được đề xuất sau chẩn đoán và quyết định mới của người vận hành. E01 không chạy retrieval trên 44 packet.

## Population và opening

Primary diagnosis: 12 KIS validation human-verified mới. QA/TRAKE thuộc foundation chung nhưng không trộn vào denominator KIS localization. Sealed held-out 12 KIS chỉ mở cho quyết định cuối theo protocol đã duyệt; các trường hợp QA/TRAKE khác giữ quy tắc sealing chung. Tune/dress25/holdout cũ/competition có thể dùng diagnostic hoặc regression đúng registry, không làm independent evidence. Với n nhỏ báo numerator/denominator, từng query và bất định; không suy rộng từ một số thắng nhỏ.

Trước chạy: GT/split/grouping/query hashes được seal; model runner chỉ nhận query, không annotation/video target. Metric join GT diễn ra ở evaluator đã có quyền mở đúng split. Ghi consumption trước khi chạy/xem held-out output. Cần thêm loader/gate cho schema E01 trong H03a được phép sau này; chưa có đường tương thích ngầm với evaluator cũ.

## Các stage phải quan sát — theo code hiện hành

Source freeze `7842d11` / H02 source `4fe4f2e`. Kiểm trực tiếp `backend/retrieval/search.py`, `backend/tasks/runner.py`, `backend/common/retrieval_trace.py`:

1. Query plan/translation và từng raw source hit; phân biệt keyframe/video/ASR segment. Ghi branch enabled/disabled/error/cache miss; nominated keyframes từ ASR/text_vi cần stage riêng.
2. Candidate union/mapping fill trước fusion; sau weighted RRF/core scoring.
3. `_finalize`: gom shot, loại orphan, video-diverse ordering nếu bật, rồi cắt top_k. Code hiện gộp các bước trong một hàm; cần checkpoint riêng trước/sau từng bước để quy đúng nguyên nhân.
4. `rerank_top50` **sau** grouping/truncation. Ghi frame identity trước/sau vì có thể chọn frame khác trong cùng shot; không chỉ theo index list.
5. Final video order nếu bật; result search chuyển sang ShotHit.
6. Allocation: sort/shot admission/budget/frame generation; output rows và final top-100/export. Multi-anchor route có nhiều search call và một bước merge: phải capture từng call rồi merge, không coi một call là toàn query.

Chuỗi yêu cầu raw → fusion → heuristic rerank → shot grouping → allocation được bao phủ theo vai trò, nhưng báo cáo giữ **thứ tự thực thi thật**, không sửa thuật toán để khớp hình vẽ. Video prior hiện disabled; heuristic rerank enabled; allocator hiện `[(50,2)]`, KIS candidate multiplier 15, vector_siglip2 override false và ocr_probe true. Đây là config source đang có, không đổi theo wording cũ của tài liệu.

## Instrumentation inventory và phần còn thiếu

H01 đã có `branches` raw snapshots, `fused_ranking`, `finalized_ranking`, `reranked_ranking`, `final_ranking`, task search_rows, export_ranking, mapping audit và timing coarse. Observer opt-in deep-copy dữ liệu; không quyết định ranking.

Chưa đủ để xác định mọi stage: ASR nomination/candidate union chưa có snapshot riêng; `finalized_ranking` trộn grouping/order/cut; allocation chưa ghi riêng admission/sort/frame-generation; chưa có per-stage reliable timing; multi-anchor merge cần identity rõ. H03a có thể bổ sung observer thuần đọc sau khi được phép, kèm test instrumentation on/off cùng output hash và fixed raw fixtures. **E01 không thêm hook retrieval hoặc chạy diagnosis**. Stage thiếu thì ghi `not_observed`, không nội suy hoặc đổ lỗi allocator.

## Candidate ledger

Mỗi row: run/arm/query_id/task/query_hash/GT_version, search_call_id/anchor_id, stage_name/order, source_name/granularity, rank, keyframe_id, video_id, absolute_frame_idx, shot_id, parent_candidate_ids, source_rank/score, mapping_status, stage_present, top100_present, drop_reason, generated_vs_indexed và latency_status.

Khóa frame lấy từ frame_map/catalog; không suy ordinal JPG. Parent relation cần cho shot representative/frame replacement và allocator-generated frame. Nếu không biết parent, giữ `unknown`, không khẳng định candidate bảo toàn. Raw segment/video không có frame phải ghi đúng granularity; không biến thành frame hit chỉ vì video đúng.

## Metrics đã đăng ký

| Metric | Định nghĩa cố định / denominator |
|---|---|
| video R@1/5/20/50/100 | Tỷ lệ query có target video trong k **unique videos**, lấy thứ tự xuất hiện đầu ở stage. Báo thêm video-hit theo top-k candidate rows để không che row budget. All eligible queries trong denominator; failures tính miss. |
| frame R@1/5/20/50/100 | Có row trong top-k candidate/frame rows với đúng video và absolute frame thuộc union GT windows đã seal; không tự nới tolerance. Với raw đa nhánh báo từng branch và union availability, không bịa global raw rank. |
| Conditional localization error | Trong query có đúng video ở stage/top-k: min distance từ predicted frame cùng video tới GT-window union; 0 nếu nằm trong window. Báo median/mean/p90 bằng frame, số query điều kiện, và riêng số đúng video nhưng không có frame hợp lệ. Không gán 0 cho missing. Khi đổi sang giây phải dùng fps metadata đã khóa. |
| Candidate availability before fusion | Hai boolean riêng video_present/frame_window_present trong union raw+nominated keyframes; tỷ lệ theo tất cả query và breakdown branch. Phân biệt index-wide relevant-frame availability từ map với raw pool availability. |
| Survival after fusion | Relevant frame/video có trước và còn sau; báo numerator/conditional denominator, rank change và top100 change. Candidate identity và relevant-hit survival là hai bảng riêng. |
| Survival after rerank | Như trên, theo thứ tự code; ghi frame replacement trong cùng shot, không coi đổi keyframe thành mất video. |
| Survival after shot grouping | Trước/sau gom; orphan removal, representative replacement, top-k truncation và video ordering phải tách lý do. |
| Survival after allocation | Shot admitted + generated/exported frame có còn hit window; ghi budget, số shot được cấp slot, candidate lineage. |
| moved-out-of-top100 | Relevant hit có rank<=100 trước, sau rank>100 trong danh sách còn tồn tại. Loại khỏi pool, đổi representative và failed/missing stage báo riêng, không gộp là moved-out. |
| Duplicate/shot coverage | Số rows, unique keyframes, unique (video,frame), unique shots/videos; duplicate row fraction; relevant-shot coverage. Shot không map được báo missing riêng. |
| Mapping violations | Count và denominator mọi reference đối chiếu map: missing keyframe, wrong video, wrong absolute frame, orphan/unknown shot. Generated frames kiểm bounds và provenance; không tự bắt chúng phải có indexed keyframe. |
| Latency / stage timing | Wall-clock monotonic per stage khi đo được; median/p95, warmup/cold-cache riêng, thread overlap không cộng branch times thành query time. Thiếu clock/snapshot ghi unavailable. Instrumentation overhead đo paired on/off trên diagnostic, không claim latency gain E01. |

Unit query là query_id trong version; retry là execution record riêng, không tăng số query. Report count failed/blocked/unsupported, giữ denominator và lỗi service/translation. Primary fixed-window metric; sensitivity rộng hơn nếu preregister riêng phải gắn nhãn sensitivity, không sửa GT.

## Failure taxonomy và hành động sau diagnosis

- A: target video/frame không có trong raw pool. Phân biệt video absent với video present nhưng raw frame miss.
- B: có raw union, mất tại fusion/core candidate filtering.
- C: mất hoặc thay frame tại rerank.
- D: mất ở grouping/orphan removal/representative/cut.
- E: có trước allocation, bị shot admission/budget/frame selection loại khỏi final output.
- F: target video có trong index nhưng không có indexed frame đủ gần fixed GT windows; không đổ lỗi ranking nếu asset pool không thể hit.

F đo độc lập bằng indexed candidate inventory, không chỉnh GT theo inventory. Vì frame có thể được tạo lại/recovered ở stage sau, báo mọi transition và first irreversible loss; không cưỡng ép pipeline monotonic. Query có nhiều khả năng/thiếu trace gắn unresolved và lý do, không tự chọn dominant stage. Dominant = tần suất first irreversible loss trong toàn bộ validation failures có đủ trace; báo raw counts, ties/uncertainty. H03b intervention phải theo bằng chứng đó và được duyệt mới.

## LLM/cost controls

Không có paid provider authorization. Bất cứ exact translation/LLM cache miss cần thiết nào chặn phần autonomous end-to-end; không dùng output fallback để gọi baseline hoàn chỉnh. Không đổi model/provider hoặc gọi AI để tạo GT.

FIXED-TRANSLATION arm chỉ được chuẩn bị nếu đã có translations đóng băng với query hash, exact text bytes, source/cache provenance, model/prompt khi biết, và human/operator/autonomous attribution rõ ràng. Arm đó là DIAGNOSTIC / COMPONENT-LEVEL. Query E01 còn trống nên hiện **không có arm translation mới**, không tự tạo bản dịch rồi gọi là frozen historical translation.

## Baseline requirements trước mọi H03b promotion

Baseline và candidate phải cùng dataset_version/seal/query/GT hashes, split và consumption policy; translation bytes/hashes; source base trừ đúng intended patch; selected model/provider/encoders/weights/preprocess; ES/Milvus content/schema/index identity; frame_map/raw assets/derived data; config weights/pools/slots/rerank; scorer code+policy; cache read/write/exact-hit policy và initial cache manifest; runtime executable/Python/dependency lock/threading/warmup/instrumentation protocol.

Source/index/model/data đổi thì baseline chạy lại trên resource mới. Cùng missing identity không được coi là paired equality. Dùng H01 `require_reproducible`/`validate_resume_identity` làm gate, kèm E01 source patch/version và scorer metric-spec hash. Resource capture E01 là reference fingerprint, không phải performance baseline.

Một H03b arm = một thay đổi có baseline query-level paired diff. Validation chọn giữa variants đã preregister; held-out mở một lần để quyết định cuối, không đọc failure rồi sửa và vẫn gọi independent. Không có quyền H03b từ tài liệu này. Stop E01: NOT READY FOR H03A cho tới khi human GT/leakage/source support và quyền chạy được hoàn tất.
