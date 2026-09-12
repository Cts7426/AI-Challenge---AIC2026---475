# PP-H01 — hạ tầng đo sau sơ tuyển

Chỉ PP-H01 được triển khai. H02–H05 chưa được phép bắt đầu. Không cập nhật report v1 hoặc artifact nộp thi.

- [Checkpoint H01 A–L](CHECKPOINT_H01.md): **DO NOT PROMOTE**, chưa mở H02.
- `identity_delivery/runtime_manifest.json`: snapshot source/runtime và schema/count DB của lượt bàn giao; capture-only, chưa phải baseline.
- `index_content_identity.json`: hash nội dung DB đọc riêng, không rebuild/reindex.
- `source_snapshot.zip`, `source_snapshot_manifest.json`, `delivery_checksums.json`: mã nguồn và bằng chứng bàn giao.
- [Phê duyệt gốc](approval.txt), [kế hoạch và protocol thay thế](PLAN.md).
- [Review và các lỗi đã xử lý](review.md).
- [Nhật ký thử khôi phục Docker trước đó](docker_attempts.json). Lượt bàn giao đã kết nối lại được DB: xem `docker_delivery_inventory.json` và `docker_delivery_mounts.txt`. Không biết đầy đủ thao tác khôi phục ngoài task, không tự suy rằng live state khớp lịch sử.
- `instrumentation_fixture.json`: dữ liệu test, dùng runner/allocator/exporter thật với nguồn retrieval cố định; **không phải live accuracy baseline**.
- `identity_offline_initial/runtime_manifest.json`: snapshot đầu triển khai, trước các sửa review; **không dùng làm identity cuối hoặc baseline được nhận**.
- `asset_identity.json`: hash nội dung ảnh, không phải xác nhận ground truth hay pixel/frame parity.

## Lệnh harness sau khi đủ môi trường

Từ gốc repo, dùng `.venv/Scripts/python.exe -m scripts.run_reproducible_baseline`.
Operator phải đặt `LLM_BACKEND` và biến model tương ứng trong process trước lệnh run. Agent không chọn giá trị thay operator. Chế độ `--capture-only` có thể ghi identity thiếu; lệnh run chặn identity thiếu.

```powershell
.venv/Scripts/python.exe -m scripts.run_reproducible_baseline --help
```

Lệnh run yêu cầu `--out <thư mục mới> --queries <JSON queries> --qa-submission-policy robust --baseline-label PP-B0-RESTORED --content-digests`. Nhãn RESTORED chỉ dùng sau khi đã ghi nhận quá trình khôi phục và không chứng minh được live DB cũ. Không so score lịch sử như cùng environment.

`--instrumentation on|off` chỉ điều khiển observer. `--expected-resource-manifest <runtime_manifest.json>` kiểm **toàn bộ identity ban đầu**, gồm cache, cho cặp H01 cùng code/config. Candidate của một họ giả thuyết mới phải có protocol xác định phần code/config được đổi trước khi chạy.

`--resume` giữ manifest và fingerprint ban đầu, kiểm input/CSV và snapshot cache sau mỗi query trước khi skip. Cache mới được append; sửa/xóa evidence đã ghi sẽ chặn. Checkpoint JSON bị hỏng được giữ nguyên và báo lỗi, không tự sửa lịch sử. Không dùng resume để đổi model, policy hoặc trạng thái instrumentation.

Harness ghi JSONL append + flush mỗi query; lưu query thật, mọi nhánh và trạng thái, ranking trước/sau rerank, task output, thứ tự export, mapping, timing và runtime ID. TRAKE giữ context qua worker. Các frame rải/nội suy thiếu keyframe được ghi `no_keyframe_reference`, không tự gọi là evidence đã xác minh.

Ngưỡng promotion chung cũ đã bị phê duyệt mới thay thế. Chưa có dataset human-verified độc lập mới, chưa có accuracy claim từ H01 và chưa đề nghị mở H02.
