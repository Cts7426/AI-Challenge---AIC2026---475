# H01 — checkpoint phương án không gọi API mới

**0 USD API; DO NOT PROMOTE H01 BASELINE.** Operator đã chọn `api / claude-sonnet-5`, sau đó yêu cầu cách khác vì số dư $5.52. Chuyển sang `LLM_CACHE_ONLY=1`, giữ model, không xin dùng hết số dư hoặc tự chuyển provider. H02–H05 chưa bắt đầu.

## A. Thay đổi

Adapter trả cache hợp lệ nguyên trạng; cache thiếu/tắt/hỏng bị chặn trước mọi provider dispatch. Counter cache misses cho phép harness phát hiện cả caller đã nuốt lỗi rồi fallback. Query có cache miss không được xuất CSV hoặc nhận là baseline có đủ evidence. Policy mới nằm trong runtime fingerprint và resource identity. Không đổi ranking, allocator hoặc inference mode legacy.

## B. Source / experiment

Source hiện có commit bàn giao `235414784b5ee80b9552fd7fe7ce898db1cbf35b`; commit này được tạo ngoài lượt tiếp tục và chứa cả thay đổi/report ngoài phạm vi cache-only. Không gán toàn bộ diff của nó cho thí nghiệm. Các snapshot và manifest cũ giữ nguyên; source mới có `source_cache_only_snapshot.zip` và manifest riêng.

Thí nghiệm `PP-H01-CACHE-ONLY-20260912`. Runtime ID từng lượt nằm trong `cache_only_diagnostic*/runtime_manifest.json`. Lượt on đầu ghi commit cũ; lần đối chiếu cuối dùng `cache_only_diagnostic_on_current` và `cache_only_diagnostic_off`, không tự bỏ field git để coi hai ID khác nhau là bằng nhau.

## C–D. Test / preflight / selfcheck

- RED: 4 lỗi hợp đồng cache-only và 1 lỗi harness vẫn export khi caller nuốt cache miss; lưu `cache_only_red.log`, `cache_only_harness_red.log`.
- Focused: 44 passed trong `cache_only_green.log`.
- Full suite mới nhất: **928 passed, 1 skipped, 2 warnings**, 111.85 s, chạy qua `.venv/Scripts/python.exe scripts/selfcheck.py`.
- Development preflight: **19 đạt / 0 hỏng / 2 bỏ qua** trên mã cache-only mới. Release trước bổ sung guard: 19/0/2. Không gọi LLM để preflight.
- Selfcheck vẫn exit 1 do holdout13 mới 6/13 verified và round1 0/25 có GT; không tắt hoặc tự sửa trạng thái kiểm người.

## E–F. Identity / baseline

Đã thu full pixel và DB content digest ở capture-only với model operator chọn: `resource_capture/runtime_manifest.json`, ID `61533e29a6b17a767df7cfe293bdca15bd28c8538fa41a6c6ab6004f61c8373a`. Capture này có trước sửa cache-only, **không dùng làm source identity của code mới**.

Diagnostic mới hash source/config/runtime/cache và đọc schema/count DB; tham chiếu capture trước. Nó ghi rõ thiếu full content digest inline nên không đủ nhận baseline, kể cả hai ID diagnostic bằng nhau. Không restore/reindex/xóa volume.

913 file cache lịch sử có metadata Sonnet 5 được copy sang cache làm việc riêng, có checksum trong `cache_seed_manifest.json`. Metadata model đúng không có nghĩa đúng prompt/ảnh/parameters của query hiện tại; adapter vẫn kiểm key đầy đủ.

## G–H. Kết quả query-level

Tập nguyên 30 query đã khóa: 23 KIS (5 có EN sẵn), 5 QA, 2 TRAKE. Không đổi mẫu số sau khi nhìn output; không đọc sealed và không chấm accuracy độc lập.

Lượt diagnostic đầu: **5/30 query xuất CSV**, 25 query bị chặn vì thiếu cache, **132 cache misses**, **0 cache hits**, **0 provider calls**, **0 USD API**. Năm câu xuất được không cần gọi LLM; không gọi đây là replay thành công 913 cache. Mapping/export violations=0 chỉ trên 5 câu có kiểm tra; 25 câu còn lại có mapping status unknown, không tính là đạt.

`task_success=30` phản ánh pipeline cũ có fallback khi LLM lỗi. Harness đã chặn 25 output thiếu cache bằng `blocked_cache_miss`; không dùng task_success để tuyên bố 30/30 đạt. Đây cũng là bằng chứng thực tế rằng lỗi phụ thuộc LLM có thể bị che ở tầng task.

Mẫu đầy đủ nằm trong `cache_only_diagnostic/queries.jsonl`; các lỗi, thứ tự candidate/export, frame mapping và runtime ID vẫn được giữ. Bảng đối chiếu on/off cuối nằm trong `comparison.json`: **30/30 semantic bằng nhau, 5/5 CSV giống từng byte**, hai identity cùng `d1648b0e14002d03370c6a5ea2d2494f4a64098a50d200480575df1c4b96f0d4`. Mỗi lượt ghi 0 provider calls / 0 USD và 132 cache misses. Chỉ bỏ `task_output.timings` khi so task semantic; giữ nguyên timestamp video, điểm/rank, errors và mọi đáp án. Phần observer bật/tắt và counters không phải nội dung đáp án. Kết quả khớp ở output fallback không chứng minh đáp án đúng.

## I–J. Gaps và thay đổi semantic

Thiếu đúng cache cho 25 query nên chưa có baseline đủ KIS/QA/TRAKE. Không dùng output fallback làm đáp án đúng, không sinh thay bằng model khác. LLM credit/model availability chưa kiểm thành công qua API; model chỉ xác nhận cấu hình.

Cache hit hợp lệ giữ nguyên nội dung; cache miss khi policy=1 đổi hành vi có chủ đích thành chặn dispatch/export. Chế độ thường vẫn giữ hành vi cũ. Không tuyên bố tăng accuracy hoặc giảm latency inference.

Full before/after digest cho cặp diagnostic chưa có; timestamp fallback khi scan Milvus và provenance lịch sử vẫn là giới hạn như checkpoint trước. Dataset human-verified độc lập chưa hoàn tất.

Review bổ sung: reviewer độc lập trước đó không chạy được do model ở capacity; không ghi phần bổ sung đã được reviewer xác nhận. Tự rà soát diff và các test guard/harness/fingerprint đã chạy, gồm bảo vệ trước cache miss và caller fallback. Không thay SDK/không có đường provider mới ngoài adapter.

## K–L. Quyết định và bước tiếp

**DO NOT PROMOTE.** Cách miễn phí đã được triển khai và đo trên dữ liệu thật, nhưng không đủ evidence để nhận baseline toàn bộ. Giữ số dư, không gọi API thêm. Không mở H02 hoặc đăng ký ngưỡng H02 dựa trên output fallback.

Bước còn thiếu của H01 là cung cấp đúng phản hồi/evidence cache cho các request hiện chưa có, hoặc operator sau này cho phép một run có ngân sách cụ thể. Không coi yêu cầu “continue” là cho phép tiêu credit sau khi đã chọn đường 0 USD.

Lịch sử chặn API: automatic approval review đã từ chối gửi query nội bộ tới Anthropic vì chưa có phép egress cụ thể. Sau câu hỏi chi phí, operator chọn phương án khác; task tiếp tục hoàn toàn cục bộ, không thử đường vòng. Không cần phê duyệt API để dùng các artifact diagnostic này.
