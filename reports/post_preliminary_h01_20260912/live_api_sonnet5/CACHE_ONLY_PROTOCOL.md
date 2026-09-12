# Đổi protocol theo yêu cầu bảo toàn số dư — trước query replay

Operator cho biết chỉ còn $5.52 và yêu cầu cách khác; chưa cho phép egress/API mới. Phương án mới là **0 USD API**, `LLM_CACHE_ONLY=1`, giữ `LLM_BACKEND=api` và `LLM_API_MODEL=claude-sonnet-5` đã chọn. Không chuyển provider/model, không sinh đáp án bằng model khác. Protocol tạo cache qua API trước đó chưa thực thi và không còn là kế hoạch được phép chạy.

Chỉ copy 913 JSON cache có metadata model khớp Sonnet 5 vào cache làm việc riêng; giữ nguyên cache lịch sử. Seed có checksum từng file và nguồn. Các key của adapter vẫn gồm prompt/model/images/parameters, không gán lại model hoặc sửa cache cho trúng key.

Thêm guard trong adapter trước mọi dispatch: cache thiếu/tắt hoặc bị validator loại thì `CacheOnlyMissError`; trả cache hợp lệ nguyên trạng. Ghi counter cache misses để harness bắt cả lỗi đã bị caller nuốt thành fallback. Nếu query có bất kỳ cache miss nào, không xuất CSV và không nhận nó thành baseline thành công. Policy cache-only phải vào fingerprint/identity để không resume trộn hai chế độ. Đây là correctness của đường replay ngân sách 0, không phải thay đổi inference/ranking khi có đủ cache.

Chạy diagnostic trước trên **nguyên 30 query đã khóa** để biết coverage cache. Dùng runner/search/exporter thật, DB thật; không đổi query/GT sau khi xem kết quả. Diagnostic chụp source/config/runtime/cache mới và tham chiếu full resource capture đã có; do không rehash pixel/DB inline, ghi rõ identity chưa đủ để nhận baseline. Nếu thiếu cache, báo đúng số query/miss và giữ DO NOT PROMOTE; không tự chạy API bù hoặc loại query khó khỏi mẫu số.

Chỉ khi diagnostic đủ cache 30/30 mới chạy cặp on/off với full before/after resource digests và cùng seed. Gate semantic/mapping/export giữ nguyên protocol gốc, thêm provider calls=0 và cache-only misses=0. Không gọi chi phí capture/test/Docker cục bộ là phí API. Không tuyên bố H01 hoàn tất chỉ vì replay được một phần.

Bảng giá source hiện cũ nhưng không ảnh hưởng phí API bằng 0 của chế độ này; không sửa bảng giá trong thí nghiệm replay để trộn thay đổi. Nếu sau này operator cho phép API, giá phải được tính theo `COST_ESTIMATE.md` và ngân sách phải khóa trước run.
