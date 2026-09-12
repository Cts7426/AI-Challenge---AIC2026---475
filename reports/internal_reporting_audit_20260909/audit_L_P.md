# Audit bổ sung L–P — INTERNAL, chưa phải technical report

> **Quyết định mới nhất:** [Final closure + strategy](C:/dev/aic2026/reports/internal_reporting_audit_20260909/final_report_strategy.md) đã bỏ các historical-provenance blockers bằng chính sách claim có qualification. Không dùng các gap/gate lịch sử dưới đây để yêu cầu forensic tiếp trước khi drafting.

> Cập nhật sau khi nhận bảy ZIP gắn điểm: xem [Evidence Closure](C:/dev/aic2026/reports/internal_reporting_audit_20260909/evidence_closure.md). File này giữ working baseline lịch sử. 11.2 đã có hash riêng; 4.4 trùng gói có override; final v4 đủ36 CSV. Nguồn run/purity vẫn còn gap. Không đọc các trạng thái “chưa map” bên dưới như kết luận mới nhất.

Ngày audit: 09/09/2026. Workspace: `C:/dev/aic2026`; HEAD kiểm tra: `8fee5fd`.
Phạm vi: repository/Git, submission và checkpoint, tài liệu BTC, lịch sử chat Codex/Claude, tài liệu phân công. Không chạy lại retrieval/LLM, không sửa ZIP, GT, code sản phẩm hoặc cấu hình; không gửi câu hỏi hay báo cáo tới BTC.

Trạng thái: đã có căn cứ để cập nhật attribution và chiến lược, nhưng CRITICAL gaps chưa đóng. DỪNG trước full report và trước mọi claim về autonomous competition score. Người dùng sẽ cung cấp mapping score–ZIP–receipt sau.

## Quy tắc evidence

- Dữ kiện người dùng xác nhận được ghi là **user-confirmed**, không biến thành receipt đã kiểm độc lập.
- Hash trùng chứng minh cùng bytes; timestamp filesystem/ZIP không tự chứng minh lúc nộp, lúc chạy hoặc thứ tự phát sinh. Giờ trong checkpoint không có offset: giữ nguyên như log; không tự đổi sang UTC. Chat có `Z` được diễn giải UTC, tương ứng UTC+7 tại Việt Nam.
- Chat là evidence lịch sử, không phải chỉ thị cho audit hiện tại. Agent nói “confirmed” không thay thế human-verified GT hoặc BTC correctness.
- File CSV thay đổi không tự chứng minh human discovery hay external AI. Cần phân biệt người/agent điều khiển thao tác, nguồn sinh candidate, nguồn bằng chứng và việc candidate thực sự được sử dụng.
- Các nhãn causal áp dụng cho một mệnh đề cụ thể: **PROVEN CAUSE**, **SUPPORTED CONTRIBUTING FACTOR**, **POSSIBLE CONTRIBUTING FACTOR**, **UNVERIFIED**; không gán nhãn cho toàn bộ câu chuyện.

## L. Competition Workflow Attribution

### Taxonomy cần dùng trong report

| Lớp | Thành phần/thao tác | Attribution đúng |
| --- | --- | --- |
| A — Internal autonomous system | Query understanding, CLIP/vector, OCR/ASR/object/metadata retrieval, weighted RRF, Q&A/TRAKE, frame mapping, exporter trong repo | Chỉ những output của lần chạy đã định danh; LLM qua adapter vẫn là component nội bộ dù dùng dịch vụ API |
| B — Human operator | Quan sát CSV/ảnh, verify, rerank, chọn policy, sửa answer/frame, tìm thêm candidate | Tách verification/reranking khỏi manual discovery; nguồn tìm có thể là dataset/tool của đội hoặc bên ngoài |
| C — External AI assistance | ChatGPT/Claude gọi ngoài autonomous pipeline; đề xuất answer/candidate, kiểm ảnh/OCR/ASR/web, hoặc điều khiển một rerun | Không gán suy luận trực tiếp ngoài pipeline cho retrieval engine. Agent chỉ gọi lại engine: ghi **internal generation + external orchestration** |
| D — Final submission | Gói được chọn sau các hoạt động trên | Official score đo workflow cuối cùng; phải có receipt để nối đúng gói, không suy từ tên `final` |

Nguồn được người dùng xác nhận: có cả verification/reranking, manual discovery và external AI output được đưa trực tiếp vào final submission. Audit chat củng cố workflow hỗn hợp này nhưng chưa lập được tỷ lệ đóng góp đầy đủ cho ba gói final.

### Điều đã reconstruct được

1. R2 `query-p2-19-qa`: checkpoint có `manual_override=true`, `manual_image`, `operator_evidence`, answer “Lý Thường Kiệt”, video `L30_V043`, frame `1818`. Bản checkpoint trước đó có 29 record, bản hiện tại giữ nguyên 29 record và thêm override này. Vì vậy ZIP R2 hiện tại không được gọi là hoàn toàn tự động hoặc tự gán cho score 4.4. Chat sửa P2 còn cung cấp frame 3740 cho cùng video/answer; phải giữ hai trạng thái riêng.
2. R3 `query-p2-9-kis`: Claude chạy lại retrieval của đội, đưa danh sách top-20; người dùng chuyển đúng danh sách sang task Codex để sửa ZIP. Chat có kiểm tra 100 dòng, xử lý ba trùng lặp, hash đầu ra `219433E3…5C7BD8`. Hash này khớp cả file Downloads `THANH_NGHE_round3.zip` và `THANH_NGHE_round3.original.zip`. Chỉ 1/26 CSV thay đổi so với Downloads `exam_final.zip`; 25 CSV còn lại giữ nguyên. Đây là bằng chứng đầu-cuối ở **artifact**, không phải bằng chứng Claude tự tìm candidate ngoài engine.
3. Chat sau đó gọi gói `219433E3…` là **11,4/17**. Ghi riêng là điểm trung gian do người dùng nói trong chat, chưa có receipt; không thay thế official final **11,8/17** trong addendum.
4. R3 QA: Claude truy vấn trực tiếp OCR/ASR của đội để đề xuất “Tây Bắc” cho q6; task kiểm chứng trên Codex có đề xuất q14=5, q35=3, q8=SUBMARINE, v.v. Một số giá trị xuất hiện trong các ZIP sửa sau đó, nhưng q8 trong bản sửa là **SEGA**, không phải SUBMARINE. Không đánh dấu mọi đề xuất đã được chấp nhận. Q14 có sử dụng nguồn bài báo ngoài dataset để đối chiếu.
5. Task chỉnh ZIP R2/R3 chứa danh sách người dùng nói là đáp án đội tìm được. Bằng chứng này xác nhận agent **thực hiện sửa gói**, không tự xác định ai tìm ra từng đáp án ban đầu.

Chi tiết query-level và trích dẫn chat: [internal_attribution.md](C:/dev/aic2026/reports/internal_reporting_audit_20260909/internal_attribution.md). Các nhãn trong đó không phải xác nhận GT.

### Số liệu so sánh artifact — không phải số lượng human interventions

Đọc 11 đường dẫn ZIP, 10 hash khác nhau; thực hiện 9 phép so sánh. CSV được parse, trim field và so cả thứ tự lẫn multiset; không chỉ diff whitespace. Script/JSON lưu toàn bộ query-level differences.

| Cặp file | Kết quả | Giới hạn diễn giải |
| --- | --- | --- |
| R1 local `sotuyen1_p1` → final được meta nối hash | 25/25 CSV thay đổi; 4 top-1 phía sau có nguyên row trong top-100 phía trước | Không chứng minh 21 query còn lại do người tự tìm; không phải recall |
| R1 manual `222703` → final được meta nối hash | 10 thay đổi, 15 giữ nguyên | Tên/time không chứng minh manual này là cha của final |
| R2 local đã có override → final được meta nối hash | 28 thay đổi nội dung; 1 chỉ hoán vị; 1 giữ nguyên | q14 KIS rank 4→1 là permutation; tác nhân rerank cần chat. 3 top-1 có trong file phía trước; không phải autonomous recall |
| R3 local → `original` | 26 thay đổi, thiếu 10 query ở phía sau | `original` chỉ có 26 KIS, không phải full 36-query batch |
| R3 `original` → corrected → v2 | Thêm 3 rồi thêm 4 CSV; mỗi bước đổi 2 CSV KIS | v2 có 33/36 CSV; còn thiếu q5/q24/q27 QA, không tự gán score 11.8 |

### Giá trị đo được của hệ thống đội

- Metadata/data audit lịch sử ghi **873 video, 177.321 keyframe**; đây không phải kiểm kê DB live ngày thi. Pixel parity mới 84/873 video, chưa phủ toàn bộ kho.
- Trace R3 có 36 query thành công ở cấp runner: 26 KIS, 8 QA, 2 TRAKE. 26 KIS có 100 search rows và 100 answer rows mỗi query, lưu ranks/source gồm vector, OCR, ASR, objects, metadata, OCR probe. Có bằng chứng về bounded candidate output và hạ tầng đa phương thức hoạt động; **100 rows không đồng nghĩa 100 shot độc lập hoặc 100 kết quả đúng**.
- Timing checkpoint R3: median KIS **6,675 s** (26 query), QA **359,605 s** (8), TRAKE **76,575 s** (2). Đây là thời gian lịch sử được runner ghi; không phải benchmark mới, không gồm toàn bộ thao tác người dùng, không được nối với 11.2 khi thiếu artifact mapping.
- Frame map/resolver, query hashing, checkpoint/resume, export/validation có implementation và trace; đó là contribution kỹ thuật. Case q9 ở trên chứng minh engine còn cung cấp candidate trong một rerun được sử dụng để chỉnh artifact.
- Chưa có GT độc lập đủ mạnh để claim official recall, precision/top-K accuracy, tỷ lệ recovery, lượng thời gian tiết kiệm, hay engine là nguồn **primary** của mọi final candidate. Có thể viết “reduced the output presented for inspection to a bounded candidate list” với phạm vi trace; chưa viết “reliably reduced millions of frames to the correct candidates”.

Nguồn kiểm lại: [data audit lịch sử](C:/dev/aic2026/reports/data_audit.md), [checkpoint R3](C:/dev/aic2026/submissions/round3/checkpoint.jsonl), [trace R3](C:/dev/aic2026/submissions/round3/trace.jsonl), [runtime manifest implementation](C:/dev/aic2026/backend/tasks/runner.py:233). Không lấy các số này từ official-score ledger.

## M. Compliance Assessment

Các nguồn ưu tiên đã đọc/đối chiếu:

| Nguồn 2026 | Điều xác định được | Implication và uncertainty |
| --- | --- | --- |
| Ảnh form BTC người dùng cung cấp | Tóm tắt khoảng 100–200 từ; report khoảng 4 A4, Việt/Anh, PDF/DOC/DOCX, tối đa 100 MB, tên khuyến nghị `TeamName_TechnicalReport.pdf` | Chỉ yêu cầu deliverable, không phải yêu cầu của người dùng viết report ngay; không thấy yêu cầu contribution theo tên |
| [Hướng dẫn sơ tuyển BTC](https://drive.google.com/file/d/1CKmOJSieXInMmV6UMlt27L-yiXAUCHxC/view), được email BTC 01/08 dẫn qua `263.org.vn/AIC2026-TTSOTUYEN` | KIS/QA/TRAKE, dataset BTC, submission và cách chấm theo cutoff | Không tìm thấy điều khoản cụ thể giải quyết direct answer từ ChatGPT/Claude; đây không mặc nhiên là bộ thể lệ đầy đủ |
| [FAQ BTC 2026](https://docs.google.com/spreadsheets/d/1uEVQud21OR8r5-kv8Tzjkh7CuJ_GFp-NMNp6B_G5kzk/edit), STT 7 và 14 | Cho phép lựa chọn mô hình/thuật toán/công cụ xây hệ thống; định hướng có cả tương tác người dùng và tự động, vẫn phải tuân thủ quy định công bố; tích hợp agent là định hướng | Căn cứ thuận cho human-interactive system, không phải phê chuẩn mọi cách dùng dịch vụ ngoài hoặc nộp trực tiếp đáp án ngoài hệ thống |
| FAQ STT 19, 24, 27, 42, 49, 55, 72 | Các câu hỏi API/tool/internet/AI coding/GPT API chưa có câu trả lời trong nội dung đọc | Câu hỏi trống không phải điều khoản cho phép hay cấm. FAQ được sửa đến 06/09; không có lịch sử từng ô để khẳng định nội dung tồn tại trước từng vòng |
| [Website chính thức](https://aichallenge.hochiminhcity.gov.vn/) | Mô tả hướng tương tác người–hệ thống, công cụ đội thi và định hướng autonomous/generative AI | Mô tả định hướng, không đủ chốt direct external assistance ở sơ tuyển |
| [Tập huấn 1](https://drive.google.com/file/d/1SD2z_-pM-z6rDSq7r6uRNNkVvidnF7YH/view) | Ví dụ generative AI/chatbot | Nội dung giảng dạy không thay thế thể lệ cho phép external answer submission |

Đã tìm các chủ đề: external tools, ChatGPT/Claude, generative AI/agents, human interaction/verification/reranking/selection, manual search, internet, third-party services, own-system origin, audit/verification. Không tìm được văn bản 2026 bổ sung giải quyết dứt điểm các trường hợp ngoài pipeline. Không dùng luật năm trước làm luật 2026.

**COMPLIANCE AMBIGUITY:** direct external AI answers/candidates, manual discovery qua internet/công cụ ngoài, và ranh giới “kết quả từ hệ thống của đội”. Kết luận chính xác hiện tại: **“No explicit prohibition was identified in the official materials reviewed.”** Không kết luận “This was allowed”, cũng không kết luận đã vi phạm. Đề xuất xin BTC giải thích trước khi chốt wording; chưa liên hệ BTC trong audit này. Dù quy định chưa rõ, disclosure phương pháp vẫn phải trung thực.

## N. Autonomous Score Provenance

### Score ledger

| Đợt | Official final — user-confirmed | Automated artifact — user-confirmed | Trạng thái evidence hiện tại |
| --- | ---: | ---: | --- |
| 21/08 | 8.6/13 | 6.8 | File final Downloads có hash khớp `official_r1r2.meta.json`; chưa có receipt. Chưa nối 6.8 với exact artifact/runtime |
| 28/08 | 13.6/15 | 4.4 | File final Downloads có hash khớp meta; chưa có receipt. ZIP `round2` hiện tại chứa manual override, không gán cho 4.4 |
| 04/09 | 11.8/17 | 11.2 | Có nhiều gói trung gian, một hash nối được chat 11.4/17; final 11.8 và automated 11.2 vẫn chưa nối receipt/hash |

Không lấy chênh lệch hai cột làm human/AI uplift; không chia score thành tỷ lệ query đúng. Số CSV 25/30/36 khác mẫu số 13/15/17: cần receipt/scorer subset/policy, không suy mẫu số là số query đã audit hoặc bỏ query một cách hợp lệ.

### Hash của các mốc quan trọng

| File | SHA-256 |
| --- | --- |
| Downloads `Thanh Nghệ_round1 (1).zip` | `36F18D7EC153AD5CDE917914E7B45ACDADFB4FDC3AA3308FEFA77243184A1ACA` |
| Downloads `submission_THANH_ NGHỆ.zip` | `30753D4E28C1C50AA20F175794E56AC8A9011E767B7FD152A255D3DBFB3E3384` |
| `submissions/round2/submission.zip` — có override | `79FE2540BD8C6BB97ABF1E6D684C494C42EC2CFB26A0F6B3E4BBDFD47BF1DED7` |
| `submissions/round3/submission.zip` — chưa nối score | `11C881D4E3C917CB7034C7FCDB99A6A2ECCD8737FEFF5E714438A05789174929` |
| Downloads `exam_final.zip` — 26 KIS | `785B61D4BFE290522B70C035043FB6C58C8191E400CBF9CF0252E78B82179C72` |
| Downloads `THANH_NGHE_round3.zip` = repo `THANH_NGHE_round3.original.zip` | `219433E34C99E53A4D3EB38D43F3C31ECAEA2104812BF0FE77B8C1DECA5C7BD8` |
| `submissions/THANH_NGHE_round3_corrected_v2.zip` — 33 CSV | `D07A2BDFAFF0B33A19C65223B6D8BB55FCFFE2AFCD7A94E864A610C1E507DE45` |

### Audit tương đương môi trường

| Thành phần | Đã thấy | Chưa chứng minh |
| --- | --- | --- |
| Timestamp | R1 checkpoint 21/08 20:04:49–20:42:14; R2 28/08 20:39:09–21:53:05 có override; R3 04/09 19:46:41–20:38:54 | Liên hệ tới lượt nộp đầu/cuối và artifact 6.8/4.4/11.2; độ chính xác đồng hồ |
| Git / config | Có commit history; R2/R3 có fingerprint | Commit + dirty diff + snapshot của đúng mỗi scored run |
| Model | Các diagnostic multi-anchor có model/config cụ thể | Model release thật của ba automated scored artifacts; không thể suy ngược tên model từ digest |
| Index / database | Repo có loader, metadata/data manifests | DB/index snapshot khi nộp và khi chạy lại, ingest/update/cache/data equivalence |
| Runtime | `runner.runtime_manifest()` hash config, một tập critical source, env backend/model/mode | Không bao phủ toàn repo/Git, dependencies, DB contents; digest trùng không đủ chứng minh môi trường tương đương |
| Query / scorer | Checkpoint có query hash; diagnostic có query/scorer hashes | Exact query set, scorer version, scoring subset, BTC receipt của các score đang xét |
| Modifications | Có QA sửa ngày 28/08, nhánh sentinel 01/09, thay đổi tích hợp/config ngày 03–04/09; chat còn chạy lại pipeline | Chưa gắn được cửa sổ thay đổi giữa official submission và từng scored automated run |

Tạm gọi ba điểm 6.8/4.4/11.2 là **“user-reported scores of post-submission automated artifacts; provenance pending”**. Khi nối được artifact nhưng chưa đủ equivalence: **post-submission diagnostic autonomous run** (chỉ nếu thực sự không có intervention bên trong run). Chỉ nâng thành **autonomous replay / unmodified automated run** với mô tả điều kiện sau khi kiểm đủ provenance. Không dùng “raw score before human intervention”, “original autonomous submission”, “competition-time autonomous performance”.

## O. Personnel/Timeline Evidence

Danh tính và original/actual contribution giữ trong [bảng INTERNAL riêng](C:/dev/aic2026/reports/internal_reporting_audit_20260909/internal_contributions.md); không đưa tên người ngừng tham gia vào narrative.

| Mệnh đề | Evidence | Đánh giá |
| --- | --- | --- |
| Một số task quan trọng đã chuyển người thực hiện | Phân công gốc; `BUILD_TASKS.md` C0.1/C1.1; commit `a33b09f` 11/08 ghi làm thay adapter/query understanding | Việc reassignment có chứng cứ trực tiếp; lý do ngừng trao đổi là user-confirmed, chưa có timeline giao tiếp đầy đủ |
| Code tích hợp tập trung ở ba danh tính kỹ thuật | Git `--all --no-merges` 01/08–05/09: 185 human-authored commits ở ba nhóm alias; 2 commit author Claude | Bằng chứng implementation ownership; commit count không đo workload/giờ công hoặc phủ mọi đóng góp phi-code |
| Integration/validation còn diễn ra sát giờ thi | Multi-anchor rollback 28/08; QA fixes 28/08 16:45/20:17; preflight/runtime/config fixes 04/09 17:24/18:19; rehearsal 28/08 dừng Phase 0 | **SUPPORTED CONTRIBUTING FACTOR** cho rủi ro late integration/validation; không chứng minh tất cả rehearsal đều bị hủy |
| Resource loss gây giảm testing và giảm official score | Chưa có actual task durations, testing plan vs actual, cancellation logs và query-level causal link | **POSSIBLE CONTRIBUTING FACTOR** đối với compressed testing; ảnh hưởng định lượng tới official score **UNVERIFIED** |
| Kế hoạch ban đầu lệch lịch thi thực tế | Plan 6 tuần đặt freeze 09/09, submit 11/09, trong khi ba vòng user-confirmed kết thúc 04/09 | Một nguồn schedule compression khả dĩ khác; plan không phải bằng chứng giờ làm thực tế |

Wording đủ thận trọng để đề xuất: “Critical workstreams were reassigned during development, and integration and validation continued close to the preliminary-round deadlines. The effect of reduced engineering capacity on testing coverage has not been quantified.”

Chưa dùng nguyên câu “This compressed the integration and validation window” như quan hệ nhân quả đã chứng minh. Nếu có thêm kế hoạch/actual timestamps, có thể nâng mức. Chuỗi trình bày: constraint → observed effect → mitigation → process improvement, không phải lý do bào chữa cho điểm.

### Engineering timeline và case studies đáng giữ

| Chuỗi | Evidence kiểm được | Cách trình bày |
| --- | --- | --- |
| Multi-anchor → lỗi compatibility → sửa → đo regression → rollback → kiểm lại | `edd6343` 24/08; `38f6d45` 27/08 bỏ `maxItems` không tương thích; 19/19 query thực thi multi, diagnostic Final 0.3263 vs single-fallback 0.4000; 4 tăng/5 giảm/10 giữ; `d3eb66d` 28/08 disable; single check trở về 0.4000 | Evidence-driven rollback, **không phải success metric**. Legacy/unverified dress25 GT, KIS-only, không promotion hay điểm thi. Hai run không phải suy luận counterfactual hoàn hảo do runtime/LLM variability |
| Q&A refusal lọt validation → sửa upstream → phát hiện stale traces/export gap → thêm end-to-end predicate → clean replay | Rehearsal/review 28/08; `fe7faca`; `f6af471` + `43c9adf` 01/09: hai sentinel rows trong old RUN3, new run 0; QA 0.200 và overall 0.363 không tăng | Sửa correctness/validation, không “tăng accuracy”. **Quan trọng:** hai commit 01/09 chỉ nằm trên `codex/qa-last-3h`, không là ancestor HEAD audit; chưa chứng minh full fix được deploy khi thi R3 |
| Rehearsal operational | `docs/release/2026-08-28-round2-rehearsal.md` Phase 0 BLOCKED, phase 1–8 NOT RUN ở lần ghi đó; các gate/preflight được phát triển | Có cải thiện quy trình và phát hiện lỗi; không gọi rehearsal hoàn chỉnh đã pass. Số test xanh trích trong tài liệu là lịch sử, không phải test vừa chạy |
| Runtime/config R3 | `5b18974`, `8fee5fd` 04/09: warmup/preflight, tránh backend/env bị auto-load, xử lý nhánh vector không có collection | Bằng chứng failure mode và mitigation gần deadline; không tự gán mức ảnh hưởng tới 11.8 hoặc 11.2 |

Nguồn chính: [multi-anchor diagnostic](C:/dev/aic2026/docs/evaluation/2026-08-28-multi-anchor-live-measurement.md), [single-anchor check](C:/dev/aic2026/docs/evaluation/2026-08-28-round2-single-anchor-final-check.md), [rehearsal](C:/dev/aic2026/docs/release/2026-08-28-round2-rehearsal.md), [review](C:/dev/aic2026/docs/reviews/2026-08-28-round2-precontest-review.md). Các addendum branch-only phải xem bằng Git tại commit, không đọc bản HEAD rồi giả định đồng nhất.

### Hai cạm bẫy evaluation cần loại khỏi narrative

1. `build_official_gt.py`/`official_r1r2.meta.json` dùng final top-1 và heuristic confidence. Official aggregate score không xác minh top-1 của từng query và không thể biến thành xác suất đúng 66%/90%. Labels từ assisted final không phải independent verified GT; dùng để diagnostic phải disclose nguồn, không claim generalization/no-overfit.
2. Tài liệu A/B 03/09 ghi video metric 0.3895→0.6421 nhưng strict frame ±5 lại 0.042→0.032. Run directory gốc được dẫn không có trong workspace audit. Chỉ ghi **document-reported diagnostic**, không coi 0.6421 là “floor” performance hay thành công chính thức; không bỏ metric regression.

## P. Disclosure Strategy

### Phải disclose để tránh mô tả sai phương pháp

- Official scores là final mixed-workflow scores; có human verification/reranking, manual candidate discovery và external ChatGPT/Claude assistance, gồm direct suggestions được sử dụng theo user confirmation.
- Internal API LLM khác external AI session; nêu agent chỉ gọi engine hay thực sự tự suy luận/tìm candidate ở case tương ứng.
- Automated artifacts phát sinh sau submission đầu và provenance/equivalence chưa hoàn tất. Không làm biểu đồ “before/after human intervention” từ hai cột hiện tại.
- Diagnostic GT/scorer/split, tính không độc lập của labels lấy từ assisted submissions; branch-only vs deployed implementation.
- Compliance còn mơ hồ. Không ngụy trang external assistance bằng cụm “LLM component in our system”.

Đây là yêu cầu minh bạch phương pháp để report không misleading; không tự khẳng định BTC đã có biểu mẫu disclosure riêng bắt buộc khi chưa tìm được điều khoản.

### Nên disclose nếu evidence và dung lượng cho phép

- Hai case tiêu biểu: multi-anchor measured rollback; Q&A refusal validation với trạng thái integration chính xác.
- Vai trò candidate infrastructure bằng trace/output bound, multimodal sources, frame mapping và latency có phạm vi.
- Resource constraint không nêu tên, chỉ mô tả reassignment có evidence và late integration; không gán causal score loss.
- Một đoạn limitations/autonomy roadmap: đóng freeze manifest toàn môi trường; immutable submission ledger; provenance tags cho mọi thao tác; verified GT độc lập; rehearsal + end-to-end checks trên branch release thực tế.

### Chỉ giữ INTERNAL trừ khi BTC yêu cầu hoặc người dùng duyệt

- Contribution theo tên, nội dung trao đổi nhân sự, raw chat, email/PII và danh tính liên quan.
- Toàn bộ query-level edit ledger, file paths cá nhân, checksum inventory dài, debug logs/caches.
- Không đưa nguyên bảng contribution vào report hiện tại: ảnh form không yêu cầu; nếu có yêu cầu theo tên sau này, ghi actual contribution, không tạo thành tích cho người chưa có evidence.

### Candidate thesis sau audit — chưa phải đoạn report được duyệt

“The preliminary-round scores represent the final outputs of a human-in-the-loop workflow, not a purely autonomous model. The team's system provided multimodal retrieval, candidate generation, frame mapping and submission tooling. Human verification, manual candidate discovery and external AI assistance also contributed to the workflow. Repository and run evidence document measured regressions, rollback decisions and validation improvements; their deployment status and the provenance of post-submission automated scores must be stated separately.”

Đã bỏ claim **primary**, **occasional**, **compensate for failures** trên toàn bộ query vì chưa đo được tỷ trọng/tần suất/counterfactual. Có thể thêm vào từng case cụ thể khi evidence đủ. Narrative “substantial system” nên thay bằng architecture và measurements cụ thể thay vì tính từ.

## PHASE 3 — CRITICAL information gaps còn lại

| Gap | Đã giải quyết được một phần | Cần gì để đóng |
| --- | --- | --- |
| 1. Score → artifact | R1/R2 final hash khớp meta; R3 intermediate 11.4 nối được chat/hash | Exact ZIP/hash + receipt/time cho sáu điểm; user sẽ gửi sau |
| 2. Automated provenance | Có checkpoints/fingerprints của vài local runs | Commit, dirty diff, config, model, index/DB snapshot, runtime, cache policy của đúng 6.8/4.4/11.2 |
| 3. Tương đương lúc thi | Git có timeline thay đổi nhưng chưa nối scored runs | Lượt submission trước run, mọi tuning/modification/ingest giữa hai mốc; archived query/scorer/subset |
| 4. External AI query attribution | Đã tìm chat Claude/Codex và case q9/QA; không cần user chép lại các case đã tìm | Các phiên ChatGPT khác hoặc tài khoản/project khác nếu ngoài logs đã đọc; confirm source-to-final những case còn ambiguity |
| 5. Nguồn dữ liệu external AI | Có trực tiếp OCR/ASR/raw BTC của đội; q14 đối chiếu bài báo ngoài | Nguồn của các manual/external candidates còn lại; tách internet discovery khỏi dataset inspection |
| 6. Manual discovery | User xác nhận có; chat đưa nhiều team-confirmed answers | Ai/tool nào tìm ở đâu trong từng case còn thiếu; không suy từ CSV diff |
| 7. Compliance | Đã đọc ảnh, BTC email/link, hướng dẫn, FAQ, website/tập huấn 2026 | Thể lệ/thông báo/email bổ sung hoặc BTC clarification về direct external answers/internet/own-system origin |
| 8. Personnel/testing | Phân công gốc, reassignment trong Git, late integration | Actual reassign dates cho các workstream, plan vs actual test/rehearsal; không cần narrative về mâu thuẫn cá nhân |

## Kiểm tra và bàn giao audit

- [Inventory và query diffs JSON](C:/dev/aic2026/reports/internal_reporting_audit_20260909/artifact_inventory_and_diffs.json); [script đọc lại](C:/dev/aic2026/reports/internal_reporting_audit_20260909/inspect_artifacts.ps1). Lệnh: `& ./reports/internal_reporting_audit_20260909/inspect_artifacts.ps1` — chỉ đọc ZIP/checkpoint, xuất JSON ra stdout.
- `python scripts/selfcheck.py` trong môi trường audit trả exit 1: test suite/preflight chưa đạt, thiếu dependencies ở Python 3.14 hiện hành; holdout mới 6/13 verified và round1 manifest 0/25 GT. Không sửa môi trường ngoài phạm vi, không dùng test lịch sử/venv khác để tuyên bố hệ thống ready.
- Kiểm lại lần cuối 09/09: selfcheck vẫn exit 1, test suite “không đọc được kết quả”, preflight 5 đạt/13 hỏng/3 bỏ qua, cùng hai gap GT trên. `git diff --check` exit 0; link local trong ba file Markdown đều tồn tại. Hai commit branch-only có `merge-base --is-ancestor ... HEAD` exit 1. Inventory JSON xác nhận 11 path / 10 hash / 9 comparisons. Đây là verification của tài liệu/artifact audit, không phải chứng nhận correctness của hệ thống.
- Các số liệu chấm/lỗi ở trên là evidence lịch sử được đọc lại, không phải lần evaluation mới. Không đánh dấu GT verified, không submit, không gửi report.
- Chờ evidence CRITICAL và duyệt của người dùng. **Không viết full report ở bước này.**
