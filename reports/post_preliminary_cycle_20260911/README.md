# Hồ sơ duyệt Phase 1–3

**POST-PRELIMINARY / POST-COMPETITION INTERNAL EVALUATION.** Chưa triển khai production; dừng ở STOP POINT 1 theo yêu cầu người dùng. Selfcheck vẫn exit 1, không coi hệ thống đã hoàn tất.

- Đọc [STOP_POINT_1.md](STOP_POINT_1.md): baseline, taxonomy, 5 ưu tiên/giả thuyết, protocol, rủi ro và thứ tự triển khai.
- [baseline_manifest.json](baseline_manifest.json): mục lục identity/runtime/index/prompt/checks; trỏ đến snapshot source và dữ liệu có checksum.
- [evaluation_registry.json](evaluation_registry.json): phân loại tập đã dùng; chưa có held-out độc lập sẵn sàng.
- [integrity_review.json](integrity_review.json): source production, lịch sử và dữ liệu không đổi bytes; ZIP đọc được.
- [recomputed_diagnostics.json](recomputed_diagnostics.json): thống kê tính lại từ ZIP, không gọi retrieval hay LLM.
- `checks/`: log/exit code của Python mặc định, `.venv`, full suite qua selfcheck, preflight development/release và test lỗi cô lập.

Tái tính thống kê từ snapshot tại gốc repo:

```powershell
python reports/post_preliminary_cycle_20260911/analyze_evidence.py
```

Lệnh kiểm hệ thống đã chạy và đang có gate chưa đạt:

```powershell
python scripts/selfcheck.py
.venv\Scripts\python.exe scripts/selfcheck.py
.venv\Scripts\python.exe scripts/preflight_check.py --profile development --json
.venv\Scripts\python.exe scripts/preflight_check.py --profile release --json
```

Command metadata ghi interpreter, exit code và override chẩn đoán thực tế. Không lấy kết quả `.venv` để nói Python mặc định có dependency. Không chạy lại `capture_baseline.py` vào thư mục đã có: script cố ý từ chối ghi đè snapshot.

Để phục hồi, dùng commit `8fee5fd07bfd03d945fe93d474ffe2c29a4b7106` cùng source ZIP và dirty diff trong **thư mục kiểm chứng riêng**; kiểm SHA-256 trước khi dùng. Snapshot không chứa secret và chưa có backup live ES/Milvus/model weights; vì vậy chưa đủ dựng một full run tương đương chỉ bằng giải nén. Không giải nén ZIP đè artefact lịch sử để thử tái lập.

Tự review đã đối chiếu attribution, denominator, prompt call path, runtime config, integrity và links. Harness không có lệnh slash `/code-review`; không giả vờ đã gọi một công cụ không có. Review trực tiếp trong lượt audit không thay thế regression gate của Phase 4.
