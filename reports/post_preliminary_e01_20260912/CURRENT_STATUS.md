# Nguồn sự thật sau quyết định H02 và E01

Theo [authorization.txt](authorization.txt), CHECKPOINT_H02 được người vận hành **APPROVED — PROMOTE H02 CORRECTNESS**. Source `4fe4f2e`; report/checkpoint `7842d11`.

Claim được nhận: QA post-preliminary phân biệt supported autonomous answers với review-required/unsupported/refusal/placeholder ở các đường live/replay/export đã được test, đồng thời giữ candidate/evidence có thể duyệt. Không suy ra accuracy/recall/điểm thi/latency/retrieval tốt hơn. Live path coverage là test/mocks và replay, không phải live-provider benchmark mới.

Bằng chứng H02 được nhận: 981 passed/1 skipped, development/release preflight passed; replay khóa 129 records / 80 unique query IDs / 66 CSV; giữ review evidence 14 records; false rejection 0 trong fixture audit; provider calls 0; historical competition artifacts nguyên vẹn.

H01 infrastructure APPROVED; performance baseline NOT PROMOTED. Selfcheck exit 1 là evaluation/GT gap: holdout13 6/13 verified, round1 0/25 GT. Không sửa GT vì mục tiêu test xanh.

E01 chỉ được làm evaluation foundation. H03/H04/H05 implementation chưa được phép. Dataset E01 mới đang PENDING, chưa independent/sealed; xem CHECKPOINT_E01.md. Không có quyền gọi paid provider, đổi provider/model hay dùng số dư còn lại.
