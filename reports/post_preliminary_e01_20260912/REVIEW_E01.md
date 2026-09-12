# E01 code review và kiểm phạm vi

Tự review code/diff trước bàn giao theo AGENTS.md; không spawn reviewer vì turn này không có chỉ thị cho phép delegation. Không có tool slash `/code-review` khả dụng, nên kiểm trực tiếp source và invariants. Đây không phải review độc lập của người thứ hai.

| Điểm kiểm | Kết quả / bằng chứng |
|---|---|
| Retrieval/model/slot/config cũ | 213 file nguồn/config trong snapshot trước E01 giữ nguyên hash; E01 chỉ thêm config protocol/schema/tool/test/registry. |
| Gọi LLM/client | Tool dataset chỉ dùng stdlib/Pydantic/config; packet dùng resolver/frame map/source assets, không import search. Resource capture dùng H01 client tập trung read-only, hard guard external dispatch. |
| Frame identity | Packet lấy frame_idx từ frame_map, ảnh qua resolve_frame_path; record đối chiếu source catalog, map hash và từng asset hash. Không suy ordinal. |
| Human provenance | record verified/group-verified yêu cầu human-reviewed và actor/reason; CLI đóng thời điểm; không có workflow agent tự tạo GT. Test dùng fixture-human trong tmp_path. |
| Version/seal | Exclusive writes, hash chain, old/new label history, seal digest, consume once, corrections giữ parent/consumed. |
| Leakage | Video/group/event/wording cross-split chặn seal; shared-frame overlap cần human review/explanation. 23 cặp thực vẫn PENDING. |
| Claim independence trước seal | Review phát hiện quality có thể báo independent khi mới đủ nhãn nhưng shared-frame check chưa qua. Đã tách labels_ready_for_seal_checks và independence_established; independence chỉ true sau seal, false sau consume. Thêm assertion vào shared-frame test. |
| Legacy tools | Không sửa gallery/mark_verified cũ vì chúng cập nhật manifest/GT tại chỗ. E01 bổ sung tool mới; không gán nhãn sẵn từ current answers. |

Lần prepare packet đầu lỗi do coi FramePathResolution là Path; sửa dùng `.path` theo API thật. Registry đã tạo được giữ nguyên/kiểm equality khi resume; không ghi đè nguồn cũ. Giữ log lỗi `packets.log` và log thành công `packets_resume.log`. Không có provider attempt trong cả hai lần.

Giới hạn chủ đích: lời xác nhận human trên CLI là provenance do người chịu trách nhiệm khai, không phải xác thực danh tính. Seal/hash-chain là integrity guard cục bộ, không chống người có toàn quyền sửa file và mọi hash. Tool không tự gọi evaluator; H03a cần loader/consumption gate được duyệt riêng. Annotation trên ảnh thưa không xác nhận được mọi temporal boundary; GT thật còn pending.
