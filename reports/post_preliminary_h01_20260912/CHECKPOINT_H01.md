> **Cập nhật mới nhất:** operator đã chọn model và chuyển sang phương án 0 USD API. Xem [checkpoint cache-only](live_api_sonnet5/CACHE_ONLY_CHECKPOINT.md). Phần dưới giữ số đo tại checkpoint trước; không dùng trạng thái model unset cũ làm trạng thái hiện tại.

# Checkpoint PP-H01 — chưa nhận baseline

**Quyết định: DO NOT PROMOTE.** Phần mã H01 đã triển khai và suite mới nhất đạt 922 test; acceptance gate vẫn mở vì chưa có lựa chọn model/backend của operator và chưa có baseline query run cùng cặp instrumentation on/off dưới identity hoàn chỉnh. Không bắt đầu PP-H02–H05.

Đây là công việc POST-PRELIMINARY / POST-COMPETITION. Không tuyên bố tăng accuracy. Điểm 8.6/13, 13.6/15, 11.8/17 vẫn thuộc workflow thi có người và LLM ngoài hệ thống hỗ trợ, không phải số đo autonomous baseline.

## A. Thay đổi

- **H01A:** validate `video_prior_alpha` trước dịch/DB; giữ test alpha cũ và trạng thái video prior. Dependency import trong preflight không làm đổi environment. Dotenv chỉ bổ sung secret còn thiếu; runtime/model phải được operator chọn trong process. Lời gọi LLM không được dùng model khác lựa chọn đó, kể cả khi có cache. Thiếu lựa chọn không bị nuốt thành translation fallback.
- **H01B:** collector hash source/config/function/prompt, data/frame map, CLIP weights, dependency/scorer và cache; định danh schema/count cùng nội dung ES/Milvus. Identity thiếu phải bị chặn riêng, không coi hai hash của trạng thái thiếu là đủ cho paired run. Ghi rõ encoder cần dùng và encoder đã thu weights; chưa hỗ trợ collector weights SigLIP2 thì chặn.
- **H01C:** observer trên search production ghi query thực, branch status, candidates/ranking, lỗi và timing; truyền context qua worker TRAKE. Harness gọi `solve_query`, allocator và exporter thật, lưu JSONL append/flush, query hash, mapping theo video/keyframe/event và runtime ID. Resume bảo vệ cả cache mới sinh sau mỗi query, không chỉ cache trước run.
- Không đổi fusion/reranking/localization để thêm trace. Test runtime cũ được đặt backend tường minh thay vì dựa vào default ngầm; assertion giữ nguyên. Không sửa annotation hay artifact nộp thi.

## B. Commit / experiment IDs

- Base trước H01: `8fee5fd07bfd03d945fe93d474ffe2c29a4b7106`.
- Source checkpoint hiện có: `704bb09a07e3290945a9d50e0806352d237f67c5`, branch `wip/codex-h01-20260912`. Commit được tạo trước lượt tiếp tục này để lưu trạng thái trước đổi tài khoản; gồm cả file/report có từ trước, **không gán toàn bộ diff cho H01**. Không viết lại commit hoặc push/merge.
- Mã thí nghiệm: `PP-H01-20260912`; không có run PP-B0 đã được nhận.
- [Source snapshot](source_snapshot.zip): 199 file source/config/tests, SHA-256 `670403edf7a922f01b5d416f85e1ef70c5532a88107c52ae1f6cf5a2af1bc2d0`. [Manifest từng file](source_snapshot_manifest.json) chứa commit/tree và checksum.
- [Identity bàn giao](identity_delivery/runtime_manifest.json): `362474960c25a277b0cc169f0a30b4c111f612d53a992da1e238194d516a0a68`. Đây là capture-only, không phải kết quả chạy query. `baseline_label=PP-B0` là nhãn dự kiến của lệnh capture, không xác nhận tái lập trạng thái lịch sử.

## C. Test

| Bằng chứng | Kết quả | Phạm vi |
|---|---|---|
| `h01a_red_valid.log` | 11 failed | Tái hiện hợp đồng alpha/environment/runtime trước sửa, với TEMP hợp lệ |
| `h01a_focused.log` | 122 passed, 1 warning | H01A cùng test alpha cũ và vùng liên quan |
| `final_focused.log` | 43 passed | Hợp đồng H01, identity, trace, harness và model override |
| `selfcheck_delivery.log` | **922 passed, 1 skipped, 2 warnings**, 182.17 s | Full applicable suite: `tests` và `dev_set/tests` trên source bàn giao |

Lệnh cuối: `.venv/Scripts/python.exe scripts/selfcheck.py`; interpreter Python 3.14 trong `.venv`, TEMP/TMP đặt trong workspace, Hugging Face offline. Các log RED/GREEN cho mapping, resume, OCR probe và worker trace cùng [review](review.md) được giữ lại. Không dùng interpreter thiếu dependency để báo test xanh.

## D. Preflight / selfcheck

| Kiểm tra mới nhất | Đạt | Hỏng | Bỏ qua | Exit |
|---|---:|---:|---:|---:|
| Development | 18 | 1 | 2 | 1 |
| Release | 18 | 1 | 2 | 1 |
| Selfcheck | Suite đạt; còn 4 nhóm thiếu | | | 1 |

Preflight hỏng ở **runtime Q&A: backend/model chưa được operator đặt trong process**. Hai skip là Streamlit tùy chọn và API/UI chưa chạy. DB, encoder CLIP, norm vector mẫu, mapping và validator smoke hiện đạt. Các báo cáo [development](development_delivery_parsed.json), [release](release_delivery_parsed.json) và command/log lưu kết quả đầy đủ.

Selfcheck còn: preflight runtime; holdout13 mới 6/13 verified; round1 0/25 có GT; LLM backend chưa chọn. Không tắt check hoặc tự gán verified để làm xanh. Dataset độc lập mới 24 KIS / 12 QA / 8 TRAKE chưa được dựng/đóng; việc đó chưa phải bằng chứng accuracy cho H01.

## E. Runtime / model / index identity

- Source 110 file, config 24 file, data 28 file, function 760 hash, scorer 3 file, weights CLIP 1 file trong snapshot bàn giao. Runtime gồm interpreter/platform/dependencies và allowlist environment; không lưu secret.
- `LLM_BACKEND` và các biến model: **unset**. Không lấy `.env` hoặc model mặc định làm quyết định vận hành. Vector thực tế: CLIP, `ViT-B-32-quickgelu / openai`, 512 chiều, COSINE; `text_vi` và `vector_siglip2` tắt.
- Frame map SHA-256: `37cc71f672f0e93c78c0de4930659e2ffdb16cc3e7ff9c2dfabf9867f911ec22`; đối chiếu [identity summary](identity_summary.json) và manifest gốc.
- [Hash ảnh riêng](asset_identity.json): 177.321 file, ID `709ac08cbfb6481e689b59ea7f7c56ded47b8544955300813b9817ca916d08d5`. Thu hash mất 1637.30 s; đây là chi phí đọc dữ liệu, không phải latency query, GT verification hoặc pixel/frame parity.
- ES 8.13.4: metadata 873, objects 177.321, OCR 160.393, ASR 13.415 document; UUID và mappings đã lưu. Milvus keyframes: collection ID `468480499968244985`, 177.321 entity, HNSW/COSINE; hai collection ASR phụ cũng được ghi nhận.
- Docker đã hoạt động lại trước lượt tiếp tục này: hai container hiện healthy, mount `aic2026_es_data` và `aic2026_milvus_data`. [Inventory](docker_delivery_inventory.json), [mount/start time](docker_delivery_mounts.txt). Nhật ký lỗi socket trước đó vẫn giữ nguyên; nó không còn mô tả tình trạng hiện tại. Task này không restore, reindex hoặc xóa volume. Chưa biết đầy đủ thao tác môi trường giữa hai lượt, nên không suy rằng trạng thái live bằng lịch sử.
- [Hash nội dung DB](index_content_identity.json) thu riêng bằng scan chỉ đọc, ID `b5363462080965febf587cf7ce7de0ff252e722259bd0c432e8e38d3d528fd94`, 204.83 s. Cả 4 index ES và 3 collection Milvus có hashed_count khớp count; keyframes đủ 177.321 entity. Hash ảnh, scan DB và capture runtime có thời điểm khác nhau; không tự ghép thành bằng chứng snapshot đồng thời của một baseline đã chạy.

## F. Runnable baseline manifest

**Chưa có manifest của baseline query run đủ điều kiện nhận.** Harness có thể chạy và capture-only đã thực thi; model chưa chọn nên run thật phải dừng trước LLM/external I/O theo hợp đồng H01A.

Sau khi operator đặt backend/model, cần chụp lại đầy đủ identity trong một môi trường cố định, khóa query diagnostic và trạng thái cache cho hai nhánh on/off, rồi chạy production harness. Cú pháp từ gốc repo:

```powershell
.venv/Scripts/python.exe -m scripts.run_reproducible_baseline --out <thu-muc-moi> --queries <query-json-da-khoa> --qa-submission-policy robust --baseline-label PP-B0-RESTORED --content-digests --instrumentation on
```

Không thực thi nguyên lệnh placeholder này. Chọn nhãn `PP-B0-RESTORED` nếu không chứng minh được trạng thái DB lịch sử, ghi provenance thực tế trước run; nhãn không có nghĩa agent đã reindex. Run off phải dùng cùng input/code/config/model/resource và cache đầu vào với run on; không dùng cache ấm sau một run như cache lạnh của run kia. `--expected-resource-manifest` chặn identity ban đầu khác nhau. Chỉ nhận sau khi query failures=0, mapping/export violations=0, identity/cache integrity không đổi ngoài append cho phép và semantic output cặp bằng nhau.

## G. Số đo hiện có

| Số đo | Giá trị | Giới hạn |
|---|---:|---|
| Live baseline queries qua harness | **0** | Chưa gọi LLM, không có điểm baseline |
| Fixture production KIS | 1 query, 100 dòng | Retrieval cố định trong test, không phải accuracy baseline |
| Fixture mapping / export violations | 0 / 0 | 1 dòng có keyframe tham chiếu; 99 frame allocator rải được ghi thiếu tham chiếu |
| Instrumentation on/off trong fixture | Answers và export bằng nhau | Chưa thay cho kiểm chứng live KIS/QA/TRAKE |
| Preflight latency smoke | 7.4 s development; 7.2 s release | 100 shot, query smoke có EN; không phải baseline hoặc đo tác động H01 |

Không báo 99 frame không có keyframe reference là bằng chứng đúng. Preflight validator ba dạng bài đạt chỉ là smoke test, không phải 3 loại query đã chạy trong accepted baseline.

## H. Mẫu instrumentation

[instrumentation_fixture.json](instrumentation_fixture.json) chứa input `xe máy` / `motorcycle`, query hash, runtime marker **`fixture-identity`**, source ranks/contributions, search calls, raw/fused/reranked/final ranking, task output, export order, mapping và timing. Marker này cố ý là fixture, không phải live resource ID.

Nhánh tắt, nhánh lỗi và nhánh không có hit có trạng thái riêng; trace được copy để ranking tiếp theo không ghi đè lịch sử. Worker TRAKE giữ context; candidate mapping kiểm đúng video và từng vị trí event. Các kiểm tra này chưa phải bằng chứng localization tốt hơn.

## I. Gaps còn lại

1. Operator chưa chọn backend/model. Không thể tự chọn provider/model hoặc xác nhận credit thay người vận hành.
2. Chưa có cặp baseline on/off dưới identity hoàn chỉnh, cùng cache đầu vào. Capture runtime chưa hash ảnh/DB inline; hai component digest có file riêng, không xóa gap trong manifest để làm đạt giả.
3. Scan Milvus ghi cảnh báo không lấy được server `mvccTs`, dùng client timestamp. Có digest toàn nội dung không đồng nghĩa snapshot nguyên tử khi đang có writer; trước paired run cần giữ tài nguyên không đổi và kiểm before/after. Chưa có bằng chứng point-in-time lịch sử.
4. SigLIP2 weights chưa có collector; nhánh hiện tắt, khi bật phải hoàn thiện identity trước run. Không tự bật model/nhánh mới.
5. GT cũ chưa đủ human verification; dataset validation/sealed mới chưa có query/GT manifest đóng và kiểm leakage. Không đổi tên tập đã tiêu thụ thành held-out độc lập.
6. Có lệch giữa AGENTS.md cũ và code cấu hình đã tồn tại trước H01: `SLOT_BUDGET=[(50,2)]` ở cả base `8fee5fd` và source bàn giao. H01 ghi nhận nguyên trạng theo hợp đồng không đổi valid output; không hồi cấu hình hoặc tự promotion một chiến thuật allocation khác. QA release vẫn dùng policy robust và lựa chọn inference mode đã khóa trong config/runtime.

## J. Thay đổi semantic

Các thay đổi correctness có chủ đích: alpha sai luôn lỗi trước I/O; import không điền lựa chọn model từ dotenv; thiếu runtime tường minh hoặc gọi model khác lựa chọn phải lỗi trước cache/provider thay vì dùng default/fallback. Runtime manifest dùng marker unset thay default giả. Không có assertion rằng những trường hợp invalid này giữ output cũ.

Trường hợp hợp lệ trong fixture giữ answers và thứ tự export khi bật/tắt trace. Không phát hiện đổi thuật toán ranking qua review; **chưa chứng minh semantic equivalence cho live QA/TRAKE hoặc toàn bộ query regression**. H01 không có claim cải thiện điểm hoặc tốc độ.

## K. Khuyến nghị

**DO NOT PROMOTE H01 BASELINE.** Giữ mã, test và evidence đã hoàn thành; tiếp tục riêng gate H01 khi có model operator chọn. Các lỗi còn lại được công khai, không làm xanh hình thức. Không mở PP-H02.

## L. Đề xuất PP-H02

Chưa thể đưa đề xuất chính xác dựa trên “now-runnable baseline”, vì baseline đó chưa tồn tại. Đề cương tạm thời vẫn là contract Q&A dựa trên evidence: phân biệt supported answer, unsupported/refusal/placeholder và đo chất lượng/coverage trên cùng evidence đã khóa. Đây **không phải đăng ký ngưỡng sau kết quả hay yêu cầu phê duyệt triển khai**.

Sau khi H01 được nhận, dùng query-level lỗi thực tế để viết đúng phạm vi H02 và preregister quality/regression/latency gates trước bất kỳ thử nghiệm H02 nào. Không áp dụng quy tắc chung “+0.02 OR >=2 queries”.
