# PP-H01 — kế hoạch triển khai sau sơ tuyển

> Thực hiện tuần tự trong workspace duy nhất theo phê duyệt STOP POINT 1; dùng quy trình writing-plans, executing-plans và test-driven-development. Không triển khai H02–H05.

**Goal:** Khóa hợp đồng runtime, định danh tài nguyên và đo đúng đường production để xét một baseline có thể tái lập.

**Architecture:** H01A sửa validation trước I/O và tách secret khỏi lựa chọn model. H01B chụp manifest bất biến ngoài đường query. H01C thêm bộ thu trace tùy chọn, không dùng trace để quyết định ranking, rồi chạy harness qua `solve_query` và exporter thật.

**Tech Stack:** Python 3.14 trong `.venv`, pytest, Milvus, Elasticsearch, CLIP CPU.

**Spec:** `approval.txt` (nguyên văn phê duyệt); audit gốc được giữ nguyên ở `../post_preliminary_cycle_20260911/STOP_POINT_1.md`.

## Ràng buộc và protocol thay thế

- H01 là hạ tầng đo, không phải cải thiện accuracy. Các điểm thi cũ chỉ thuộc quy trình thi có người hỗ trợ.
- Sửa correctness đăng ký trước: alpha sai luôn ValueError trước dịch/DB; import không điền environment; thiếu backend/model tường minh phải báo lỗi trước gọi LLM.
- Với đầu vào hợp lệ và cùng resource/model/cache: answers, thứ tự và điểm retrieval phải bằng nhau khi bật/tắt instrumentation. Sai khác ngoài ba sửa correctness trên phải điều tra.
- **Thay thế** quy tắc chung “+0.02 OR >=2 queries” ở đề xuất cũ: mỗi H02–H05 phải có ngưỡng quality/regression/latency riêng, đóng trước khi xem kết quả. Chưa đăng ký ngưỡng cụ thể hoặc chạy thử các họ này.
- H03 phải bảo toàn video recall, kiểm moved-out-top100 và mapping=0; H04 bảo toàn recall/order và mẫu số; H05 bảo toàn chất lượng/coverage, không tăng unsupported/refusal. Đây là yêu cầu thiết kế, chưa phải giấy phép triển khai.
- Dataset mới dự kiến validation 12/6/4 và sealed 12/6/4 KIS/QA/TRAKE. Chỉ đóng manifest khi có query/split/GT hashes, trạng thái người kiểm, evidence, timestamp/version và kiểm leakage. Hiện chưa có dataset mới; không chạy hay tuyên bố độc lập trên dữ liệu chưa đóng. Mọi sửa annotation sau quan sát phải thành phiên bản mới kèm lý do.
- Giữ registry vai trò dữ liệu cũ. Không thay lịch sử submission hoặc nhãn verified.
- Mọi thay đổi index phải có nhật ký trước/sau. Nếu không chứng minh cùng trạng thái cũ, baseline mang nhãn PP-B0-RESTORED; candidate sau dùng cùng resource identity.

## H01A — hợp đồng đầu vào/environment

Files: `scripts/preflight_check.py`, `backend/llm/adapter.py`, `backend/retrieval/search.py`, `tests/test_h01_contracts.py`.

- [ ] Thêm test alpha (-.1, 1.5, NaN, infinity, text) chặn trước translation/retrieval; giữ nguyên test cũ.
- [ ] Test preflight trong process mới với `.env` giả không được đổi env; test secret loader không nạp model; test llm thiếu lựa chọn không đọc cache/gọi provider.
- [ ] Chạy RED bằng `.venv/Scripts/python -m pytest tests/test_h01_contracts.py -q` và lưu log.
- [ ] Sửa tối thiểu: validate alpha đầu `_search_core`; import preflight giữ nguyên environment; `_nap_dotenv` chỉ nạp secret; `llm` và preflight dùng lựa chọn tường minh.
- [ ] Chạy focused gồm test mới, alpha cũ, preflight, milvus env, llm adapter, runner/run; lưu GREEN trước full suite.

## H01B — identity

Files: `backend/common/resource_identity.py`, `data/config/experiment.py`, `tests/test_resource_identity.py`.

Interface: `capture_manifest(root: Path, live: bool) -> dict`, `manifest_id(manifest: dict) -> str`.

- [ ] Test đổi source/config/data/cache làm đổi hash, lỗi resource ghi trạng thái unavailable và không được coi paired-equivalent; không thu secret.
- [ ] Manifest gồm source bytes/commit, mọi config và function/prompt source, model/vector backend, data/map hashes, model metadata/weights có sẵn, dependencies, scorer, cache trước/sau; live ES UUID/mapping/count và Milvus ID/schema/entity count qua client tập trung.
- [ ] Chụp Docker trước khi start, chỉ dùng volume hiện có; ghi thao tác restore nếu cần. Không tự bật encoder/nhánh khác.
- [ ] Xét paired identity: manifest ID chính xác, resource payload tương đương, không dùng timestamp thay content identity; ghi gaps nếu chỉ có schema/count chưa có snapshot nội dung DB.

## H01C — harness production

Files: `backend/common/retrieval_trace.py`, `backend/retrieval/search.py`, `scripts/run_reproducible_baseline.py`, `tests/test_retrieval_trace.py`, `tests/test_baseline_harness.py`.

Interface: context manager `capture_retrieval()` thu search calls; mỗi call chứa query thật, branches/status/raw candidates, fused/reranked/final ranking, errors/timing. Harness gọi `backend.tasks.runner.solve_query`, exporter thật, xuất JSONL append+flush và manifest.

- [ ] Test cùng fixture deterministic bật/tắt trace có output giống hệt; disabled/failed/zero_hits/success khác nhau; lỗi task vẫn lưu trace.
- [ ] Trace đặt ở ranh giới hiện có, snapshot copy để không bị mutation ranking sau đó; không sửa thuật toán fusion/rerank/allocation.
- [ ] Harness chặn thiếu model và input/manifest không hợp lệ trước external I/O; output dir mới không ghi đè baseline.
- [ ] Freeze tập query diagnostic trước chạy, không đọc sealed. Chạy cặp bật/tắt dưới model operator chọn; mapping/export violations phải 0 để nhận.
- [ ] Chạy full suite, dev/release preflight, `scripts/selfcheck.py`; lưu stdout/stderr, command, exit và phân loại mọi failure.
- [ ] Tự code-review diff và tái kiểm sau sửa; lưu source snapshot/commit và báo checkpoint A–L, PROMOTE hoặc DO NOT PROMOTE. Dừng trước H02.
