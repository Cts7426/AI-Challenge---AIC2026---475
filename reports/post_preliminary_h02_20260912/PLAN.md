# PP-H02-OFFLINE-20260912 — protocol correctness trước RED

H01 infrastructure APPROVED; cache-only performance baseline NOT PROMOTED. H01 attribution đã đóng trong ledger và patch trước khi sửa production H02. Không rewrite commit trộn, không sửa GT hoặc artifact lịch sử. Không dùng paid provider; mọi test/replay đặt guard cache-only và chặn provider bằng fixture.

Thiết kế tối thiểu: một module contract thuần cho text/provenance/evidence; trạng thái `success/supported_answer`, `needs_review`, `abstain`, `failed/task_failure`. Thiếu evidence không phải crash; trả candidate/trace cho review, giữ rejected answers trong payload riêng, không xuất autonomous CSV. Dữ liệu historical thiếu provenance chỉ được needs_review, không suy rằng answer đúng hoặc sai. Chuỗi `0` và phủ định hợp lệ phải giữ khi có evidence; placeholder zero phải nhận qua provenance.

RED trước implementation: A TODO success; B provenance placeholder/no_answer; C exporter sentinel; D stale cache/checkpoint; E zero hợp lệ; F phủ định hợp lệ; G mất evidence giữ candidates; H batch không chết vì unsupported; I trace replay cũ. Những ca đã xanh ghi rõ regression controls, không tạo lỗi giả để gọi RED.

Các đường phải kiểm: runner + legacy/two_stage pipeline dùng provider giả; cache thật trong thư mục test; checkpoint resume; pure replay trace cũ; portfolio selection; exporter; batch run.py; release/rehearsal/preflight. Không gọi test fixture live-provider là live quality evaluation.

Gate trước output: 100% placeholder/refusal đăng ký không thành autonomous success/export; 0 false rejection trong zero/negative controls có evidence; review payload giữ đủ; query unsupported không chặn compute query khác; checkpoint/replay/export cùng contract. Full denominator lịch sử đóng bằng path/hash trước replay, không loại query unsupported. Không đổi mapping/ranking để tăng số đo. Full suite không regression chưa giải thích; dev/release preflight và selfcheck giữ GT gap; provider calls=0. Không accuracy claim, không H03, không report v2.
