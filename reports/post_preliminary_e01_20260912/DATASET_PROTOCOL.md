# E01 — dataset creation protocol v1

Trạng thái: chuẩn bị nguồn, chưa có GT độc lập. Target 24 KIS / 12 QA / 8 TRAKE. Hai split dự kiến validation và sealed_heldout đều 12/6/4. Tên `sealed_heldout` là đích sử dụng; chưa có seal không được gọi là held-out sẵn sàng.

## Sampling trước evaluation

Nguồn là 873 video trong frame_map BTC hiện có. Chỉ lấy video ID từ metadata của query/GT/manifest cũ để loại 147 video đã biết; không dùng thứ hạng, submission candidates hay answer cũ để chọn GT. Còn 726 video, sắp theo SHA256(`PP-E01-20260912-source-only-v1|video_id`), lấy 44 video đầu; lần lượt gán slot 12/6/4 validation rồi 12/6/4 held-out. Seed, danh sách loại, hash nguồn và thứ tự được ghi trong `sampling_audit.json`/`sampling_plan.json` trước mọi evaluation. 44 source packets khác 44 query: query_text và GT ban đầu đều trống.

Không lọc nguồn theo việc model làm tốt/xấu. Chưa chạy bất cứ query mới nào; chưa đọc candidate-system output cho item mới. Human chỉ xem ảnh/video BTC trong packet, tự tạo query và nhãn. Metadata exclusion không chứng minh người chưa từng thấy video; người duyệt phải khai báo prior exposure. Set cũ giữ vai trò đã tiêu thụ trong registry mới; không đổi tên thành independent.

## Grouping và leakage

Mỗi source video chỉ có một slot, nên video ID hiện không giao giữa split. Exact byte hash các keyframe được so giữa 44 video: 86 nhóm hash xuất hiện ở nhiều video, cần kiểm tra nguyên nhân (footage lặp, intro chung, frame ít thông tin...). Không tự gọi các nhóm này là 86 video duplicate hay kết luận toàn bộ video độc lập. Phải xem các cặp được liệt kê trong `leakage_audit.json`.

Người duyệt gán duplicate_group và event_group dựa trên footage/sự kiện, bao gồm các nguồn đã tiêu thụ. Các video/sự kiện trùng hoặc gần trùng không được nằm ở hai split. Wording được so bằng NFC/casefold/space normalization và token Jaccard >=0.8 (ít nhất 4 token), hoặc wording chuẩn hóa trùng hoàn toàn; chỉ là bộ phát hiện hỗ trợ, human vẫn kiểm diễn đạt tương đương.

Exact shared frame qua split cần ghi `shared_frame_reviewed=true` cùng `shared_frame_explanation` có nội dung. Nếu footage/sự kiện thực sự trùng, phải gộp group và thay sampling plan/dataset version trước seal; giải thích không phải quyền miễn trừ group collision. Không đổi split trong revision nhãn. Giữ plan v1 và record rejected/pending, lập v2 với lý do và số lượng thay thế, trước khi chạy model. Không lấy chất lượng model làm tiêu chí thay item.

## Tạo query/GT từ nguồn

KIS: mô tả người quan sát có thể kiểm trực tiếp; ghi video, một/nhiều cửa sổ frame tuyệt đối và reference frames. QA: ghi region, evidence, acceptable answer forms, answerability và policy chuẩn hóa. TRAKE: ghi ordered events, cửa sổ riêng, evidence keys và lý do cho tolerance khác 0. Không suy frame từ số thứ tự tên JPG; tất cả reference lấy từ catalog tạo qua shared resolver + frame_map.

9.257 keyframe của 44 video đã có trong packet; hiện không có video MP4 nguồn local cho cả 44. Ảnh thưa có thể đủ xác minh một số nội dung tĩnh/QA, nhưng không chứng minh onset/order hoặc toàn bộ acceptable window. Item cần video/dense frame phải PENDING; không tự nới cửa sổ để bù thiếu bằng chứng. Không tải video hàng loạt trong E01 này. Khi human xác định item cần clip nào, ghi đúng nhu cầu và source archive/hash cho bước bổ sung nguồn sau.

Người duyệt ghi tên, thời điểm, notes và xác nhận không dùng system output/AI proposal. Agent có thể nhập quyết định human đã gửi rõ ràng; không tự điền verified. Không có người duyệt thứ hai thì báo disagreement chưa đo, không báo agreement 100%.

## Version và seal

`dataset_v1/revisions/*.json` lưu snapshot nhãn và old/new label/actor/reason qua hash chain. Query/video/split/source hash khóa trong version; thay nguồn hay split cần version/plan mới. Không sửa lại nhãn đã seal; `fork-correction` tạo version mới, giữ parent seal/hash và lý do; `record` lưu nhãn cũ/mới + verifier/date. Version phát sinh từ set consumed luôn giữ consumed, không được seal lại thành independent.

Trước seal: đủ 44 verified, đủ grouping/exposure review, không collision, source/evidence/map hash khớp, task schema hợp lệ. `seal.json` ghi dataset version, revision hash, query/GT/annotation hashes, split/group/provenance, sealed_at/by; `seal_sha256.json` khóa bytes. Seal immutable qua CLI và phát hiện sửa file, không phải bảo mật chống người có toàn quyền filesystem.

Sealed-heldout chỉ được mở cho quyết định cuối một lần; ghi `consume` TRƯỚC model execution/output inspection. Validation được dùng để chọn trong variants đã preregister; held-out không grid search. Tool E01 không chạy evaluator và chưa nối entrypoint cũ vào dataset này: H03a phải có loader/gate kiểm seal/hash/consumption và chỉ xuất query cho người chạy; model input không chứa GT/video nguồn. Không truyền annotation template vào production solve_query.

## Gate

Chưa có human verification → NOT READY FOR H03A. Không chạy evaluation để lấp khoảng trống GT. Selfcheck holdout13 6/13 và round1 0/25 giữ nguyên; không sửa manifest lịch sử. E01 chỉ chuẩn bị protocol H03a, không thay retrieval/config chạy hiện hành hay bắt đầu H03b.
