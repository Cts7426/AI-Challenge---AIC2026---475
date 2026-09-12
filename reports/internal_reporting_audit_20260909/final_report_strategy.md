# Final evidence closure và report strategy — chờ duyệt, chưa phải full report

Ngày chốt: 09/09/2026. Áp dụng [yêu cầu Final Evidence Closure của người dùng](C:/Users/lehon/.codex/attachments/54775ea9-3a20-41e7-ac83-0ea24fc5ec49/pasted-text.txt). Tài liệu này chốt chính sách claim và outline, thay thế các điều kiện chặn drafting trong audit L–P/Evidence Closure trước đó. Không thay đổi bytes, điểm hoặc lịch sử artifact.

## A. Kết luận và điểm dừng

**EVIDENCE CLOSURE SUFFICIENT FOR DRAFTING.**

**Không còn CRITICAL gap bắt buộc phải giải quyết trước khi chốt strategy, với phạm vi claim dưới đây.** Điều này không có nghĩa mọi sự kiện lịch sử đã được chứng minh độc lập. Những sự kiện chưa truy nguyên được được giới hạn bằng wording, bỏ khỏi claim hoặc ghi UNKNOWN. Không tiếp tục forensic chỉ để nâng confidence. Viết full report vẫn cần người dùng duyệt strategy/outline này.

### Kết quả lượt tìm cuối có giới hạn

| Vấn đề | Evidence sau lượt cuối | Quyết định đóng |
| --- | --- | --- |
| R2 trước override | Có checkpoint/trace `before-query-p2-19-qa`; checkpoint29 query, chưa có q19, cả29 record giữ nguyên trong checkpoint30 query. Run log ghi ba lần q19 thất bại và chặn export; sau override, export30 CSV lúc21:53:22. Không thu hồi được ZIP được chấm/scorer output gắn trạng thái29-query | **Autonomous-only score: UNKNOWN / NOT RECOVERED. H3/4.4: operator-assisted artifact with reported score4.4.** Không dựng ZIP giả định hoặc ước tính điểm bỏ q19 |
| R1 q3 vắng trong H2 | H2 có24 CSV, không có q3. Log local khác ghi q3 lỗi credit lúc20:05:20 rồi chạy lại ra câu từ chối lúc20:35:32. Chưa nối log đó với run tạo H2 | **Exact query coverage of the Round-1 6.8 replay cannot be fully reconstructed.** Unknown về scored subset, cố ý bỏ hay generation failure của đúng H2. Không claim replay query-complete |
| R3 H7/11.2 | Hash và36 CSV×100 rows đã kiểm; mapping/unchanged configuration do operator xác nhận. Tìm exact hash/tên file trong logs workspace, Claude project và Codex sessions ngày04/09 không thu hồi được generating command/manifest/checkpoint | Chấp nhận **qualified operator-reported autonomous replay**. Không tìm được mâu thuẫn trực tiếp chứng minh intervention trong H7; khác output khác run hoặc trùng candidate của operator không tự chứng minh mâu thuẫn |
| Receipt official scores | Inventory ZIP/ảnh và tìm receipt/submission ID/history/upload confirmation trong workspace không tìm được receipt nhận diện được. Các hit `RELEASE_RECEIPT_SCHEMA_VERSION` là schema/config, không phải biên nhận BTC | Dùng **team-reported official competition scores associated with identified final artifacts**. Không tự gọi BTC-receipt-verified; không còn blocker |

Lượt cuối giới hạn ở `submissions`, `reports`, `docs`, `scratch`, cấu hình/log cục bộ và inventory ZIP/ảnh workspace ngoài kho raw/cache/dependencies; tra exact H7 identifier trong project chat logs đã biết. Không kiểm mọi byte của kho ảnh/video hoặc tài khoản khác. “Không thu hồi được” nói về phạm vi đã tìm, không khẳng định artifact chưa từng tồn tại. Không thực hiện thêm personnel forensics.

H7 có CSV ở root ZIP. Packaging này đã ghi lại, nhưng không chứng minh hình thức gói thực tế lúc upload hoặc source của candidate. Không sửa/nén lại H7, không claim packaging hợp lệ được BTC xác nhận, không dùng chi tiết này để bác score team-reported.

### Nhãn evidence sử dụng từ đây

- **VERIFIED:** trực tiếp kiểm được file/hash/log hoặc implementation; luôn chỉ rõ đối tượng kiểm. “Artifact identity verified” không có nghĩa “score/answer/runtime verified”.
- **SUPPORTED:** nhiều nguồn phù hợp nhưng thiếu một mắt xích trực tiếp.
- **TEAM-REPORTED:** xác nhận của operator/team; không biến thành kiểm chứng độc lập.
- **UNKNOWN:** không reconstruct đáng tin cậy; không biến thành claim.

Nhãn evidence không thay thế nhãn causal: một sự kiện VERIFIED chưa tự chứng minh nó gây score loss. Các mối liên hệ causal vẫn phải nêu đúng giới hạn.

## B. Final claim ledger

Mỗi dòng là một claim có phạm vi; status hỗn hợp được tách rõ trong ô thay vì nâng cả claim lên VERIFIED.

| Claim | Status | Evidence | Allowed wording | Forbidden wording |
| --- | --- | --- | --- | --- |
| Kho dữ liệu/kiến trúc đa phương thức đã được triển khai | VERIFIED ở repository và data audit lịch sử | S1, S6 | “The repository implements multimodal video retrieval using vector and text-based indices.” | “Every branch and feature was active in all three competition runs.” |
| Quy mô873 video/177.321 keyframe | VERIFIED trong metadata/audit lịch sử | S6 | “A recorded data audit covered873 videos and177,321 keyframes.” | “The live competition index was independently verified at this size for every round.” |
| Query processing, nhiều nguồn retrieval, weighted RRF | VERIFIED implementation/trace; exact scored-runtime linkage chưa đầy đủ | S1, S6 | Mô tả cơ chế và source ranks được ghi trong trace đã định danh | Gán cùng config/weights/model cho tất cả ZIP từ code HEAD |
| Frame mapping và resolver là contribution | VERIFIED implementation và audit cấu trúc | S1, S6 | Join qua keyframe identity, tra absolute video frame; phân biệt ordinal/cache | “All frame mappings were pixel-verified.” |
| Candidate output giới hạn để inspect | VERIFIED cho trace R3 local | S6 | “The inspected trace returned100 rows for each of26 KIS queries.” | “100 correct/independent candidates”; “proved millions-to-one search reduction” |
| Latency đo được | VERIFIED ở checkpoint đã audit, không phải benchmark final/H7 | S6 | Nếu dùng: medianKIS6.675s/n26, QA359.605s/n8, TRAKE76.575s/n2; ghi run và excluded human time | Gán latency này cho H7, cả workflow, hoặc mọi round |
| Các gói final H1/H6/H5 đã được định danh | VERIFIED file/hash/contents; final selection TEAM-REPORTED | S2, S3 | “Identified final artifacts associated with team-reported official scores.” | Hash chứng minh receipt upload hoặc correctness |
| Official scores8.6/13,13.6/15,11.8/17 | TEAM-REPORTED; file association có evidence | S2, S3, S10 | “Team-reported official competition scores.” | “Independently verified by BTC receipts”; “autonomous model scores” |
| R1 replay6.8 | TEAM-REPORTED replay/score; identity VERIFIED; coverage/run UNKNOWN một phần | S2, S4, S10 | “Operator-reported replay, score6.8; exact runtime/query coverage partially reconstructed.” | “Complete autonomous competition-time submission” |
| Vì sao H2 thiếu q3 | UNKNOWN | S2, S4 | “Exact query coverage of the Round-1 6.8 replay cannot be fully reconstructed.” | “q3 was unscored/intentionally omitted/failed in this replay” |
| R2 H3 có operator override | VERIFIED qua hash, checkpoint và export log | S2, S5 | “Operator-assisted artifact with reported score4.4.” | “4.4 pure autonomous score” |
| R2 autonomous-only score | UNKNOWN / NOT RECOVERED | S5; bounded final search | “Autonomous-only performance could not be reliably reconstructed for Round2.” | Suy điểm từ29 query, trừ contribution q19 hoặc tạo gói hypothetical |
| R3 H7/11.2 | TEAM-REPORTED replay/score/unchanged configuration; identity VERIFIED | S2, S3, S10 | “Operator-reported autonomous replay under unchanged system configuration; artifact identity verified, exact runtime provenance partially reconstructed.” | “Independently reproduced/verified autonomous run”; “original pre-intervention submission” |
| Không thay code/model/prompt/config/index/weights/settings giữa submission và replay | TEAM-REPORTED | S10 | “Operators report unchanged system configuration.” | “Full historical environment equivalence independently established.” |
| Official scores đại diện final workflow | SUPPORTED workflow evidence + TEAM-REPORTED thực tế thi | S3, S7, S10 | “Final operator-assisted workflow performance.” | “Humans only reranked system-generated results.” |
| Có manual candidate discovery ngoài initial candidate list | TEAM-REPORTED; chi tiết từng query chưa đầy đủ | S7, S10 | Mô tả có manual discovery, không định lượng tỷ trọng | CSV row mới chứng minh human discovery; mọi candidate do engine tạo |
| External ChatGPT/Claude được operator dùng cho một subset, có direct proposals | TEAM-REPORTED tổng thể; selected sessions VERIFIED | S7, S10 | Factual disclosure ở mụcH | Đồng nhất external sessions với LLM qua internal adapter |
| Ít nhất một chain external-assisted processing tới final artifact | VERIFIED candidate transfer/contents, final identification TEAM-REPORTED | S2, S7: R3 q9 | “A traceable externally orchestrated retrieval/editing chain propagated into the identified final artifact.” | “External model independently discovered all20 candidates”; “proved score uplift” |
| Mọi query được external review đều nhờ external AI mà đúng | UNKNOWN, không dùng | S7, S3 | Chỉ nêu case đã nối và giới hạn | Matching final answer chứng minh external discovery; cộng số reviewed thành accepted |
| External assistance được BTC cho phép/cấm | UNKNOWN; COMPLIANCE AMBIGUITY | S8 | “No explicit prohibition was identified in the official materials reviewed.” Nếu cần compliance note | “Allowed by BTC” hoặc “prohibited by BTC” khi chưa có direct2026 rule |
| Multi-anchor regression và rollback | VERIFIED trong diagnostic artifacts/config snapshots | S9 | KIS-only diagnostic0.3263 vs0.4000, rollback và kiểm lại0.4000; legacy/unverified GT | Official accuracy gain, controlled causal human uplift, promotion-ready claim |
| Q&A refusal/export/stale-trace validation improvement | VERIFIED trên branch/run tương ứng; deployment vào scored runs UNKNOWN | S9 | “Subsequent branch-level validation removed two refusal rows from the inspected replay; scores unchanged.” | “All competition submissions had end-to-end protection”; “increased QA accuracy” |
| Reassignment/giảm engineering capacity và validation window | Reassignment SUPPORTED/VERIFIED ở records; capacity/tác động window TEAM-REPORTED, được timeline hỗ trợ | S1, S10; không tìm thêm nhân sự | Wording có qualification tạiI, không tên | Quy trách nhiệm cá nhân, số giờ/điểm mất không có evidence |
| Current selfcheck fail chứng minh contest system fail | UNKNOWN đối với contest-time inference; current dependency errors VERIFIED | S1, S3 | Giữ trong INTERNAL: audit environment thiếu dependencies; không suy ngược lịch sử | “The competition system was not release ready” chỉ từ selfcheck09/09 |
| Recall/generalization/đóng góp nhân quả toàn bộ pipeline | UNKNOWN ngoài các diagnostics có phạm vi | S1, S6, S9 | Nêu chỉ số theo set/run/scorer và GT status thực tế | “No overfitting”, “reliable recall floor0.6421”, “verified top1 GT” từ aggregate final score |

### Nguồn cho ledger và outline

- **S1:** [audit L–P](C:/dev/aic2026/reports/internal_reporting_audit_20260909/audit_L_P.md), chỉ các observations, không dùng blocker/wording cũ đã bị tài liệu này thay thế.
- **S2:** [score-labeled artifact JSON](C:/dev/aic2026/reports/internal_reporting_audit_20260909/score_labeled_artifacts.json): H1/H2/H3/H4/H5/H6/H7 theo [Evidence Closure](C:/dev/aic2026/reports/internal_reporting_audit_20260909/evidence_closure.md). Bảy hash đã kiểm lại09/09, không thay đổi.
- **S3:** [Evidence Closure](C:/dev/aic2026/reports/internal_reporting_audit_20260909/evidence_closure.md): file counts, mapping, packaging, query differences; các điều kiện chặn drafting cũ được mụcA thay thế.
- **S4:** [R1 run log](C:/dev/aic2026/submissions/sotuyen1_p1/run.log:120), q3 retry tại dòng238. Không phải generating log đã nối H2.
- **S5:** [R2 pre-override checkpoint](C:/dev/aic2026/submissions/round2/checkpoint.before-query-p2-19-qa.jsonl), [checkpoint có override](C:/dev/aic2026/submissions/round2/checkpoint.jsonl:30), [run log chặn export](C:/dev/aic2026/submissions/round2/run.log:73), [export sau override](C:/dev/aic2026/submissions/round2/run.log:167).
- **S6:** [data audit](C:/dev/aic2026/reports/data_audit.md), [R3 checkpoint](C:/dev/aic2026/submissions/round3/checkpoint.jsonl), [R3 trace](C:/dev/aic2026/submissions/round3/trace.jsonl), [runtime manifest](C:/dev/aic2026/backend/tasks/runner.py:233). R3 local trace chưa phải run tạo H7.
- **S7:** [internal query attribution và chat references](C:/dev/aic2026/reports/internal_reporting_audit_20260909/internal_attribution.md), cập nhật final-v4 tại S3/E.
- **S8:** Bộ2026 đã audit: [FAQ BTC](https://docs.google.com/spreadsheets/d/1uEVQud21OR8r5-kv8Tzjkh7CuJ_GFp-NMNp6B_G5kzk/edit), [hướng dẫn sơ tuyển](https://drive.google.com/file/d/1CKmOJSieXInMmV6UMlt27L-yiXAUCHxC/view), website/tập huấn và ảnh form người dùng; nguồn/phạm vi ở S1/M. Không mở rộng compliance search trong lượt final này.
- **S9:** [multi-anchor diagnostic](C:/dev/aic2026/docs/evaluation/2026-08-28-multi-anchor-live-measurement.md), [single-anchor recheck](C:/dev/aic2026/docs/evaluation/2026-08-28-round2-single-anchor-final-check.md), [rehearsal](C:/dev/aic2026/docs/release/2026-08-28-round2-rehearsal.md). Git `f6af471`/`43c9adf`,01/09 18:51:44/18:51:57, branch `codex/qa-last-3h`; branch-level evidence không tự chuyển thành deployed capability.
- **S10:** Addendum/xác nhận trực tiếp của người dùng, [ghi chú Evidence Closure](C:/Users/lehon/.codex/attachments/0243f826-0253-4244-820a-1b6401d5cbaf/pasted-text.txt), [chính sách final được duyệt](C:/Users/lehon/.codex/attachments/54775ea9-3a20-41e7-ac83-0ea24fc5ec49/pasted-text.txt).

## C. Final central thesis

> Đóng góp của đội là một hệ thống truy xuất video đa phương thức có xử lý query, sinh/xếp hạng candidate, ánh xạ frame và hỗ trợ Q&A/TRAKE cùng xuất submission. Trong các vòng sơ tuyển, hệ thống được vận hành trong workflow có người tham gia và external AI assistance; điểm cuối cùng phản ánh toàn bộ workflow đó. Giá trị kỹ thuật của công trình nên được đánh giá qua kiến trúc, bằng chứng vận hành có phạm vi, phân tích failure/regression, quyết định rollback và quá trình củng cố validation — cùng các giới hạn còn lại trên đường tăng tính tự chủ.

Thesis không cần khẳng định engine là nguồn “primary” của mọi đáp án, không suy hệ thống vô giá trị từ failures và không coi điểm final là chứng minh autonomous strength. Chưa dùng từ “occasional” để định lượng tần suất AI khi chỉ biết subset.

## D. Final narrative strategy

**Chọn architecture-and-engineering-led narrative.**

Trình tự đọc: bài toán → dữ liệu/index/mapping → retrieval/task pipeline → cách operator thực sự dùng hệ thống → kết quả có qualification → hai engineering decisions có measurement → lessons và roadmap.

- Mỗi component trả lời: input/output là gì, được dùng ở đâu, có evidence implementation/run nào, hạn chế nào đáng biết. Không làm catalog mọi file hoặc mọi feature từng thử.
- Phân biệt thuật toán ranking/fusion nội bộ với human reranking; phân biệt internal LLM adapter với external sessions ngay từ sơ đồ đầu tiên.
- Dùng một đoạn ngắn về scores, không tổ chức report thành cuộc so sánh “automatic score vs human score”.
- Dùng multi-anchor rollback làm case chính vì có hypothesis/measurement/decision/recheck rõ. Dùng Q&A end-to-end validation làm case bổ sung, gắn nhãn branch và mốc sau R2.
- Chỉ dùng negative results có scope; không gom current dependency failures vào danh sách contest failures.
- Personnel constraint tối đa1–2 câu nếu giúp giải thích process; có thể bỏ nếu thiếu chỗ, không mất thesis.

Hai hướng không chọn: **score-led** làm contribution bị thu hẹp thành delta chưa kiểm causal; **chronological postmortem-only** dành quá nhiều chỗ cho sự cố và khó hiểu architecture. Chronology chỉ dùng bên trong engineering section.

Ngôn ngữ đề xuất: tiếng Việt; tên module/thuật toán và thuật ngữ cần thiết giữ tiếng Anh. Tựa đề đề xuất: **“Hệ thống truy xuất video đa phương thức và quy trình vận hành có người tham gia tại AI Challenge TP.HCM2026”**. Không dùng “fully autonomous” trong tựa đề.

## E. Updated detailed report outline

Target khoảng4 trang A4 theo ảnh form. Page budget dưới đây **bao gồm** hình/bảng trong mục tương ứng, là kế hoạch dàn trang chứ chưa phải PDF render. Tóm tắt100–200 từ của form là deliverable riêng, chưa viết ở bước này.

| Mục | Nội dung phải có | Evidence/giới hạn | Ngân sách trang |
| --- | --- | --- | ---: |
| 1. Bài toán và contribution | KIS/QA/TRAKE; output video/frame/answer; ba contribution: multimodal retrieval, mapping/export infrastructure, measured engineering decisions | Không mở bằng điểm số hoặc nhân sự | 0.30 |
| 2. Dữ liệu, indexing và kiến trúc | Raw vs derived; ES/Milvus; CLIP/text sources; `keyframe_id` join; absolute-frame map; overview hình1 | Quy mô corpus chỉ là recorded audit. Không claim toàn bộ pixel parity hoặc mọi nhánh active trong mọi round | 0.75 |
| 3. Query-to-candidate và task processing | Query understanding/VI→EN; CLIP token budget/normalization; vector + OCR/ASR/object/metadata; weighted RRF; candidate allocation; QA evidence/answer; TRAKE temporal sequence; validation/export/checkpoint | Mô tả cơ chế quan trọng, không đi sâu mọi ablation. Exact model/weight chỉ nêu khi có snapshot và scope | 1.00 |
| 4. Competition workflow và attribution | Internal output → human inspect/verify/rerank → manual discovery khi có → external help ở subset → selected final artifact; một mini-case q9 | Không nói mọi query đi qua mọi bước; q9 chứng minh transfer chứ không correctness/uplift | 0.40 |
| 5. Evaluation và preliminary results | Tách official team-reported workflow scores, qualified replays, local diagnostics; bảng3 round; GT/metric limitations | Không delta column, không quy official score thành query accuracy. Nhắc R2 autonomous unknown | 0.55 |
| 6. Engineering decisions và subsequent improvements | Multi-anchor diagnostic regression→rollback→recheck; refusal/export/stale trace gates; timeline pre-/post-round; operational lessons | Legacy GT; branch-only fix; không claim rehearsal fully passed hoặc release deployed nếu chưa có evidence | 0.65 |
| 7. Limitations và roadmap | Verified GT độc lập; unified end-to-end gate trên release branch; immutable run/ZIP provenance; controlled ablations; tăng autonomy bằng measurements | Đây là future work, không capability hoàn tất | 0.20 |
| References/ghi chú phương pháp | Nguồn BTC2026, thuật toán/model thực sự mô tả; provenance notes ngắn | Không đưa raw chat, hash ledger dài, tên nhân sự hoặc file paths cá nhân | 0.15 |
| **Tổng** | | | **4.00** |

Nếu vượt4 trang: bỏ latency table riêng, danh sách intermediate ZIPs và chi tiết personnel trước; không cắt disclosure hoặc qualification để giữ claim nghe mạnh hơn. Các reference học thuật/model citations sẽ được kiểm đúng nguồn khi viết draft, không phải historical-provenance blocker.

## F. Score presentation strategy

### Bảng chính duy nhất về điểm thi

Caption đề xuất: **“Team-reported official preliminary-round scores of the final operator-assisted workflow.”**

| Đợt | Ngày | Điểm final workflow |
| --- | --- | ---: |
| 1 | 21/08/2026 | 8.6/13 |
| 2 | 28/08/2026 | 13.6/15 |
| 3 | 04/09/2026 | 11.8/17 |

Ghi chú sát bảng: điểm do đội báo cáo và liên kết với final artifacts đã định danh; chưa đối chiếu receipt BTC độc lập; bao gồm internal retrieval, human inspection/reranking, manual discovery và external assistance khi được sử dụng. Không hiển thị phần trăm “query đúng”, không cộng/chuẩn hóa qua rounds để tạo một accuracy mới.

### Replay: ghi chú phương pháp ngắn, không đặt cạnh như before/after

- **R1 6.8:** chỉ dùng với qualification operator-reported replay,24 CSV và exact query coverage/runtime chưa reconstruct đầy đủ. Không tự thêm mẫu số hoặc scored subset chưa xác minh.
- **R2:** autonomous-only score **UNKNOWN / NOT RECOVERED**. Không dùng4.4 ở cột autonomous; lưu H3/4.4 trong internal evidence như operator-assisted artifact. Nếu phải nhắc công khai để giải thích discrepancy, ghi đúng nhãn này.
- **R3 11.2:** dùng câu qualification đã chốt ở ledger; artifact36×100 VERIFIED, score/config/runtime classification TEAM-REPORTED. Không biến nó thành independently rerun benchmark.
- **11.4:** intermediate workflow artifact, mặc định giữ INTERNAL; chỉ đưa nếu cần mini-case lineage, không dùng làm autonomous reference.

Mặc định thêm2–3 câu qualified replay sau bảng scores, đủ disclose discrepancy mà không làm report xoay quanh delta. Không tính hoặc biểu diễn “human uplift”, không ước lượng R2 counterfactual. Metadata hash dài và chi tiết từng dòng CSV giữ trong audit bundle.

## G. Human-in-the-loop disclosure strategy

Mô tả bốn nguồn trạng thái: system-generated → human-verified/reranked → manually discovered bổ sung khi có → final selection. Cho phép candidate có nhiều nguồn tác động, không vẽ thành một chuỗi bắt buộc cho mọi query.

Wording được phép: **“Operators inspected and verified retrieved candidates, adjusted their ordering and, for some queries, introduced candidates discovered outside the initial retrieved set.”**

Không nói “humans only reranked”. Manual discovery ngoài initial candidate set không đồng nghĩa ngoài dataset BTC; không gán cùng search tool/source cho mọi case. Không báo tỷ lệ B/C hoặc số query rescued khi chưa đủ ledger độc lập. Export tooling góp phần đóng gói/kiểm format nhưng không tự xác minh semantic correctness.

## H. External-AI disclosure strategy

Wording mặc định: **“External AI assistants such as ChatGPT and Claude were used by operators for a subset of queries, including direct answer or candidate suggestions in some cases. The team reports that some of these suggestions were used directly in final submissions. These interactions were separate from the autonomous internal pipeline.”**

- Nêu rõ có direct suggestions được sử dụng theo team report. Không làm nhẹ thành “coding assistance only” hoặc “general advice”.
- Mini-case có thể chọn R3 q9: external session điều khiển retrieval của đội, danh sách chuyển qua user/editor và được giữ trong identified final artifact. Credit candidate generation vẫn thuộc internal engine; orchestration/editing ngoài pipeline được disclose riêng.
- Không gán mọi external-reviewed query cho external model. Ví dụ answer trùng có thể đã có trong pipeline; q8 external review SUBMARINE khác final SEGA. Các counterexamples giúp ledger chính xác, không cần đưa tất cả vào report.
- “At least one traceable case” là lower bound của provenance, không phải chỉ có một query dùng external AI hoặc chỉ có một final đúng.
- Giữ **COMPLIANCE AMBIGUITY**. Không khẳng định cho phép/cấm. Không dùng năm trước làm luật2026. Không cần trì hoãn drafting nếu report chỉ mô tả fact và không claim compliance certification. Nếu BTC bổ sung điều khoản trực tiếp, đánh giá lại đúng claim bị ảnh hưởng.

Không cần đưa một bảng pháp lý dài vào4 trang. Có thể dùng một qualification ngắn ở limitations nếu report bàn đến compliance; statement về việc dùng external tools luôn phải có, bất kể có đoạn compliance riêng hay không.

## I. Personnel/resource wording

Không tìm thêm nhân sự. Không nêu tên, không đưa contribution map vào report mặc định.

Wording cho phép ở operational lessons, với nguồn team-reported được rõ: **“The team reports that a reduction in available engineering capacity required critical workstreams to be redistributed, compressing the integration and validation window.”**

Sau đó chỉ nối observable effect: integration/validation tiếp tục sát vòng thi; mitigation gồm diagnostic measurement, rollback và bổ sung gates. Không viết personnel reduction gây một failure cụ thể hay score loss nếu không có causal evidence. Không lượng hóa hours/tests/rehearsals bị mất.

Nếu BTC yêu cầu contribution theo tên, dùng bảng INTERNAL đã có và evidence thực tế, không chia đều hoặc tạo contribution. Đây là thay đổi yêu cầu deliverable, không phải lý do tiếp tục forensic nhân sự ngay bây giờ.

## J. Competition-time vs subsequent-improvement treatment

| Evidence/feature | Mốc | Cách gắn nhãn trong report |
| --- | --- | --- |
| Scored final artifacts | 21/08,28/08,04/09 theo team report; ZIP timestamps không là receipt | Competition artifacts; không suy exact runtime từ CURRENT HEAD |
| Multi-anchor implementation/measurement/rollback | 24/08→27/08→28/08 | **Sau R1, trước R2**; diagnostic và rollback có snapshot. Không gọi post-all-rounds hoặc feature success |
| Q&A fixes/rehearsal findings | 28/08 | Gắn với log/review cụ thể; có blocked rehearsal không chứng minh mọi rehearsal đều failed |
| Refusal predicate ở export/stale-trace gates, clean replay | 01/09, `f6af471`/`43c9adf` | **Subsequent to R2, before R3; branch-level implementation/validation.** Deployment trong H7/H5 không xác định; không trình bày như protection chắc chắn tại R3 |
| Warmup/preflight/config fixes | 04/09 trước mốc ZIP theo timestamps | Đã có development evidence; không tự gán config đó cho mọi scored artifact |
| Current HEAD/selfcheck ngày09/09 | Audit environment, không contest replay | INTERNAL diagnostic context. Không dùng làm kết luận release readiness tại các vòng thi |

Tên mục đề xuất: **“Engineering decisions and lessons across rounds”**, với nhãn “Subsequent validation improvements” cho đúng case. Không gọi mọi cải tiến là “post-competition” nếu chúng thực ra xảy ra giữa các vòng.

Case multi-anchor có thể ghi0.4000→0.3263→0.4000 trong cùng diagnostic scope; không nói rollback khôi phục official score. Case sentinel: two invalid rows→zero trong inspected replay, QA/overall score không tăng; bảo vệ output validity là contribution độc lập với accuracy. Không promotion hay claim causality từ hai lần gọi LLM không kiểm soát hoàn toàn.

## K. Recommended figures and tables

**Mặc định1 hình +2 bảng** trong4 trang; không render/build artwork ở bước strategy này.

1. **Hình1 — Architecture + assistance boundary.** Nửa trái: BTC assets → derived maps/indices → query understanding → retrieval sources/RRF → task evidence/candidates → exporter. Bên ngoài boundary autonomous: human inspection/manual discovery và external assistants, nối vào final-selection stage hoặc dashed optional retrieval invocation. Internal API LLM nằm bên trong boundary; external sessions ở ngoài. Ghi “optional, query-dependent interactions”, không vẽ mọi query bắt buộc qua external AI. Đây là figure quan trọng nhất.
2. **Bảng1 — Three-round final workflow scores.** Dùng đúng mụcF, team-reported caption và không delta column. Không để replay scores cùng bảng gây ngụ ý paired controlled experiment.
3. **Bảng2 — Two engineering decisions.** Cột: issue/hypothesis; measurement; decision/recheck; timing/deployment scope. Hàng multi-anchor regression/rollback và QA refusal validation. Bảng ngắn, các GT/runtime/branch qualifications không nằm ngoài trang chứa số liệu.

Không dùng: bar chart autonomous-vs-human; pie chart contribution; causal personnel diagram tới score; benchmark radar không có measured inputs; UI screenshots không giải thích cơ chế; toàn bộ per-query ledger. Nếu cần latency, đưa1 câu có n/run scope, không thêm figure thứ tư.

## L. Remaining non-blocking uncertainties

| Uncertainty | Cách xử lý đã chốt | Khi nào mới cần mở lại |
| --- | --- | --- |
| R2 pre-override autonomous score | UNKNOWN / NOT RECOVERED; không cần người dùng tiếp tục truy tìm để chốt strategy | Người dùng chủ động cung cấp scored pre-override artifact/receipt có liên kết |
| H2 q3 coverage/lý do vắng | Qualification rõ; không query-complete claim | Muốn công bố complete autonomous benchmark hoặc tìm được direct run evidence |
| H7 exact runtime/DB/cache | Operator-reported unchanged configuration; không independently verified equivalence | Muốn reproducibility/controlled comparison claim hoặc có evidence trực tiếp mâu thuẫn |
| Official receipts/scored subset | Team-reported official scores; không query-accuracy conversion | BTC yêu cầu receipt provenance hoặc xuất hiện score correction |
| H7 root packaging/upload transformation | Chỉ giữ INTERNAL; không claim submitted-byte format certification | BTC hỏi exact upload package hoặc có receipt/download provenance |
| Exhaustive query source labels | Không có contribution percentages; disclose known mechanisms và selected chain | Muốn định lượng human/AI contribution hoặc attribution correctness từng query |
| Branch validation deployment | Ghi branch-level/subsequent scope | Muốn khẳng định capability đã bảo vệ một scored submission cụ thể |
| Resource causal magnitude | Team-reported constraint, không score causality | BTC yêu cầu contribution detail hoặc muốn claim quantified effect |
| External-tool rules | COMPLIANCE AMBIGUITY, factual disclosure | Có direct2026 rule/official clarification mới; không tự liên hệ BTC trong task này |

Các ô UNKNOWN này **không còn là danh sách yêu cầu người dùng phải trả lời trước drafting**. Bước kế tiếp duy nhất cần người dùng quyết định là duyệt/chỉnh strategy và outline. Không viết full report, không gọi retrieval/LLM, không sửa GT, không submit, không tiếp tục investigation theo lịch tự động.

## Kiểm tra tài liệu và phạm vi bàn giao

Bảy SHA-256 được đối chiếu lại với ledger đã chấp nhận. R2 pre/post record counts và export log được kiểm trực tiếp trong lượt cuối. Không thay đổi source ZIPs, code/config/index hoặc các dirty changes có trước. Current selfcheck được ghi ở evidence nội bộ, không dùng làm gate của kết luận “sufficient for drafting”.

Kiểm tra bàn giao ngày10/09/2026: đủ12 mục A–L,17 liên kết file nội bộ tồn tại; `git diff --check` exit0 (có cảnh báo CRLF ở file sửa sẵn ngoài phạm vi). `python scripts/selfcheck.py` exit1: test suite không đọc được kết quả; preflight5 đạt/13 hỏng/3 bỏ qua; holdout6/13 verified; round1 GT0/25. Không tuyên bố hệ thống đạt selfcheck, không sửa môi trường/GT trong task strategy và không suy kết quả này thành tình trạng contest-time.
