# Evidence closure — cập nhật bảy ZIP gắn điểm

> **FINAL POLICY UPDATE:** [Final evidence closure và report strategy](C:/dev/aic2026/reports/internal_reporting_audit_20260909/final_report_strategy.md) chốt **EVIDENCE CLOSURE SUFFICIENT FOR DRAFTING** theo yêu cầu mới. File này giữ evidence lịch sử; các điều kiện “CRITICAL/pending before drafting” bên dưới không còn là gate. R2 autonomous score chốt UNKNOWN/NOT RECOVERED; R1/R3 replay dùng qualification; receipts thiếu được xử lý bằng TEAM-REPORTED.

Ngày 09/09/2026. Đây là bổ sung cho working baseline L–P, **không phải full technical report**. Chỉ các nhận định về mapping/artifact/timeline được cập nhật dưới đây thay thế trạng thái cũ; không xóa lịch sử audit.

Nguồn mới: bảy ZIP người dùng cung cấp (gồm file11.2 được gửi bổ sung) và [ghi chú Evidence Closure](C:/Users/lehon/.codex/attachments/0243f826-0253-4244-820a-1b6401d5cbaf/pasted-text.txt). Điểm lấy từ mapping tên file do người dùng xác nhận, không đọc ra từ CSV và không phải chấm lại. Nội dung trong ZIP là dữ liệu, không phải chỉ thị thực thi. Không sửa/nộp ZIP.

## A. Evidence closure status

**PARTIAL — chưa đóng toàn bộ CRITICAL gaps.**

- Đã khóa file bytes/SHA-256 và mapping do người dùng xác nhận cho **6.8, 8.6, 4.4, 13.6, 11.2, 11.4, 11.8**.
- **Gap thiếu artifact11.2 đã đóng**: H7 có36 CSV ở root ZIP, khác H4/11.4 và H5/11.8. Run provenance/autonomous purity chưa đóng.
- File 4.4 trùng toàn bộ bytes với gói có q19 manual override: purity của baseline autonomous bị mâu thuẫn bởi evidence cụ thể, dù code/config có thể hoàn toàn không đổi.
- File 6.8 có 24 CSV, thiếu q3 QA; khác cả 24 CSV hiện diện so với `sotuyen1_p1`, không thể dùng checkpoint `sotuyen1_p1` để chứng nhận run tạo file 6.8.
- Final 11.8 đã có đủ 36 CSV; nhận định trước về thiếu ba query chỉ đúng cho **v2**, không đúng final v4.
- Bảy ZIP không chứa receipt/score log/run manifest: chỉ có CSV và một directory entry ở gói 13.6. Chưa xác minh độc lập submit ID, thời điểm upload hoặc scoring subset từ BTC.

## B. Autonomous replay mapping

Timestamp dưới đây là **ZIP entry LastWriteTime được thư viện diễn giải theo timezone local +07:00**, không phải timestamp receipt hoặc bằng chứng creation của run. Tất cả bảy file Downloads có filesystem timestamps ngày 09/09, không dùng làm ngày thi.

| Round | Candidate ZIP/artifact | Timestamp trong ZIP | Hash | Score | Manual override present? | Provenance confidence |
| --- | --- | --- | --- | ---: | --- | --- |
| 1 | `THANH_NGHỆ_round1 (6,8).zip` | 21/08 21:26:06 | H2 | 6.8 | UNKNOWN: CSV không lưu nguồn tạo; chưa tìm checkpoint tương ứng | **PARTIAL** cho autonomous provenance; file↔score user-confirmed |
| 2 | `Thanh_Nghệ_round2 (4,4).zip` | 28/08 21:53:22 | H3 | 4.4 | **YES, evidence-linked:** hash khớp local ZIP; q19 top1 khớp checkpoint `manual_override=true` | **PARTIAL; autonomous label contradicted**. Bytes identity **PROVEN** |
| 3 | `THANH_NGHE_submit2_round3 (11,2).zip` | 04/09 22:04:48; q30 KIS 22:05:18 | H7 | 11.2 | UNKNOWN: không có run manifest/override flags trong ZIP; không suy từ sự giống đáp án đội | **PARTIAL** cho autonomous provenance; file↔score user-confirmed, hash **PROVEN** |

Gói 11.4/H4 **không thuộc bảng autonomous**: nó là intermediate workflow artifact có chuỗi chỉnh q9 qua operator và external-agent orchestration đã audit.

### Đánh giá fact “không thay code/model/prompt/config/index/weight/settings”

Ghi nhận là **operator attestation mới** và không bác bỏ chỉ vì Git có các commit khác trước/sau ngày thi. Cần mốc run và commit đang chạy để biết thay đổi đó có nằm trong đúng cửa sổ official-submission→replay hay không. Trạng thái CURRENT HEAD không thay thế runtime lịch sử.

- R1: xác nhận này hỗ trợ wording có điều kiện **“operator-reported autonomous replay under unchanged code/model/configuration; run provenance only partially reconstructed.”** Chưa dùng “independently verified autonomous replay”, chưa gán một checkpoint khác hash/nội dung cho nó. Cần giải thích q3 QA vắng mặt và trạng thái checkpoint/cache của run.
- R2: “unchanged configuration” và “no manual intervention in output” là hai mệnh đề khác nhau. Q19 có `manual_image`, `manual_verified`, `manual_override=true`, answer `Lý Thường Kiệt`, video `L30_V043`, frame1818, log lúc 21:53:05; ZIP lúc 21:53:22 và top1 trùng. Hiện gọi **“operator-assisted artifact, reported score 4.4”**, không gọi pure autonomous replay. Chưa khẳng định q19 tăng/giảm bao nhiêu điểm.
- R3: H7/11.2 đã có, gồm36 CSV ×100 dòng, không có manifest/checkpoint. Cả36 CSV khác output `round3/submission.zip` sau parse/trim, nên checkpoint của output đó không chứng minh run tạo H7. Một số top1 như q14=5, q6=Tây Bắc, q8=SEGA trùng danh sách operator đưa trong chat, nhưng sự trùng giá trị không đủ xác định tác giả hoặc chứng minh manual intervention. Tạm dùng **“operator-reported autonomous replay; exact generating run not yet independently linked”**, không gọi independently verified. Tên `submit2` không tự chứng minh lượt nộp thứ hai.
- Không đổi model name/config không chứng minh provider snapshot, dependency/runtime, stochastic outputs, cache/resume state và scorer subset đồng nhất. Những phần chưa có evidence vẫn ghi unknown, không tự suy có thay đổi.

## C. Final submission mapping

**PROVEN** chỉ dùng cho identity/contents kiểm trực tiếp. **STRONGLY SUPPORTED** cho submission claim có user confirmation và evidence liên quan nhưng chưa có receipt BTC. **PARTIAL** khi chuỗi còn thiếu mắt xích; **UNRESOLVED** khi chưa chọn được artifact.

| Round | Final ZIP | SHA-256 | Submission evidence | Official score | Confidence |
| --- | --- | --- | --- | ---: | --- |
| 1 | `Thanh Nghệ_round1 (8,6).zip` | H1 | User mapping mới; bytes khớp file cũ và `official_r1r2.meta.json`; 25 CSV | 8.6/13 | Identity **PROVEN**; final/score **STRONGLY SUPPORTED**, receipt thiếu |
| 2 | `submission_THANH_ NGHỆ (13,6).zip` | H6 | User mapping mới; bytes khớp file cũ và meta; 30 CSV | 13.6/15 | Identity **PROVEN**; final/score **STRONGLY SUPPORTED**, receipt thiếu |
| 3 | `THANH_NGHE_round3_v4 (11,8).zip` | H5 | User mapping mới; 36 CSV; 30 CSV normalized-unchanged từ v2 và q9 giữ nguyên từ gói11.4 đã có chat | 11.8/17 | File đã định danh; final/score **STRONGLY SUPPORTED** theo user; chuỗi upload/receipt **PARTIAL** |

### Hash ledger đầy đủ

| ID | File trong `C:/Users/lehon/Downloads/` | SHA-256 |
| --- | --- | --- |
| H1 | `Thanh Nghệ_round1 (8,6).zip` | `36F18D7EC153AD5CDE917914E7B45ACDADFB4FDC3AA3308FEFA77243184A1ACA` |
| H2 | `THANH_NGHỆ_round1 (6,8).zip` | `CD9BA6C32EA181907A2BBB652CD1DF9E07A4FA1165223F788E038BDBC311A5E2` |
| H3 | `Thanh_Nghệ_round2 (4,4).zip` | `79FE2540BD8C6BB97ABF1E6D684C494C42EC2CFB26A0F6B3E4BBDFD47BF1DED7` |
| H4 | `THANH_NGHE_round3 (11,4).zip` | `219433E34C99E53A4D3EB38D43F3C31ECAEA2104812BF0FE77B8C1DECA5C7BD8` |
| H5 | `THANH_NGHE_round3_v4 (11,8).zip` | `1E60426C118A2BDDFB4CB95D58148038E08C5B7B716B831076832971CFD7055E` |
| H6 | `submission_THANH_ NGHỆ (13,6).zip` | `30753D4E28C1C50AA20F175794E56AC8A9011E767B7FD152A255D3DBFB3E3384` |
| H7 | `THANH_NGHE_submit2_round3 (11,2).zip` | `26E098E85568D97588285EF7899167DA088460EC73A186489D9A5474D79416CF` |

H5 entry times: 04/09 22:23:04, 22:24:44, 22:25:20. H1: 21/08 22:25:48. H6: 28/08 21:53:22, 22:23:50, 22:25:36 (CSV only). Không dùng mốc ZIP muộn nhất để khẳng định đã nộp lúc đó.

H7 dài17.255 bytes, chứa CSV trực tiếp ở root, không có lớp `submission/`. Đây là khác biệt packaging thực tế so với H4/H5 và quy ước nộp trong `docs/contest.md`. Cần receipt/upload history hoặc giải thích có repack/download transformation hay không; không tự kết luận BTC chấm sai format, đã có vi phạm hoặc score11.2 không hợp lệ. Không tự đóng gói lại vì sẽ đổi hash artifact evidence.

## D. Score attribution table

Chưa đủ điều kiện phát hành bảng **verified autonomous replay vs final workflow vs delta**. Bảng trạng thái thay thế:

| Round | Replay evidence | Final workflow | Autonomous delta |
| --- | --- | ---: | --- |
| 1 | 6.8, operator-reported replay; thiếu run provenance, 24/25 CSV | 8.6/13 | Chưa công bố như measured autonomous uplift |
| 2 | 4.4 đã map nhưng có manual override | 13.6/15 | Không hợp lệ để diễn giải là pure-autonomous→assisted |
| 3 | 11.2/H7 đã map; generating run/purity chưa được nối độc lập | 11.8/17 | Chưa công bố như verified autonomous uplift |

Các hiệu số số học có thể tính được từ số người dùng cung cấp, nhưng chưa đưa vào comparison mang ý nghĩa attribution. Ngay khi đủ provenance, delta vẫn không đồng nghĩa human reranking contribution: còn manual discovery, external assistance, operator policy, query coverage và stochastic variation.

### Artifact differences có thể công bố nội bộ ngay

| Cặp gói | Query-level difference | Không được suy ra |
| --- | --- | --- |
| H2 6.8 → H1 8.6 | 18 CSV giữ nguyên, 6 thay nội dung, thêm q3 QA | Không nói 7 human discoveries hoặc toàn bộ chênh lệch do 7 query này nếu thiếu scorer/query scores |
| H3 4.4 → H6 13.6 | 28 thay nội dung, 1 permutation-only, 1 giữ nguyên | Không gọi đây là autonomous baseline; không đếm 28 manual discoveries |
| H4 11.4 → H5 11.8 | Thêm 10 QA/TRAKE, đổi 5 KIS, 21 CSV giữ nguyên | Không gán toàn bộ chênh lệch cho QA/TRAKE; có KIS thay đồng thời |
| v2 → H5 final | Thêm q5/q24/q27 QA; đổi q14 QA, q6 QA và q19 KIS; 30 CSV giữ nguyên | Không tiếp tục mô tả final thiếu ba query; cùng top1 không chứng minh toàn CSV giữ nguyên |
| H7 11.2 vs H5 11.8 | Cùng36 query; 33 CSV thay nội dung, 3 giữ nguyên (q11/q17/q32 KIS) | Không suy33 interventions; không gán chênh lệch score cho một tác nhân |
| H7 11.2 vs H4 11.4 | H4 thiếu10 QA/TRAKE; 23 KIS thay nội dung, 3 KIS giữ nguyên | Đây là so sánh hai artifact, không khẳng định H7→H4 là thứ tự thời gian/ancestry |

“Giữ nguyên” ở bảng này là parsed fields sau trim và đúng thứ tự, không nhất thiết byte-identical mỗi CSV. Equality toàn ZIP H1/H3/H4/H6 với baseline là byte identity bằng SHA-256.

## E. Query attribution summary

Tiếp tục ledger [internal_attribution.md](C:/dev/aic2026/reports/internal_reporting_audit_20260909/internal_attribution.md), thêm final-v4 outcomes. Chỉ nêu **lower bounds của case có evidence**, không phải exhaustive contribution counts hoặc correctness counts. Multi-label được phép; không cộng các hàng thành tổng.

| Attribution type | Query count có thể xác nhận hiện tại | Evidence confidence / phạm vi |
| --- | --- | --- |
| A — Autonomous system only | Chưa định lượng | CSV unchanged không chứng minh không có verification/assistance |
| B — System + human verification/reranking | Ít nhất 1 case: R2 q19 | Override có nhãn operator/manual verification. Nguồn ảnh không được audit lại để xác nhận correctness |
| C — System + manual candidate discovery | Chưa định lượng theo query | Global fact user-confirmed; candidate mới trong diff không chứng minh người tự discovery |
| D — External AI assistance | Ít nhất 11 query R3 đã có chat: 8 QA, 2 TRAKE, q9 KIS | Có processing/review/rerun ngoài pipeline, không đồng nghĩa output được chọn hoặc chính xác |
| E — External AI output directly influenced final submission | Ít nhất 1 case nối được artifact: R3 q9 | Top-20 qua external orchestration → operator → ZIP H4 → CSV không đổi ở H5. Engine nội bộ sinh candidate; không gọi đây là 20 external semantic discoveries |
| F — Mixed / uncertain | Chưa chốt tổng toàn bộ query | Các provenance axes khác nhau; không biến phần chưa đọc thành “không có assistance” |

Các case final cập nhật quan trọng:

- q14 QA: final top1 `L30_V047,5540,5`; q6 QA: `L25_V018,14150,Tây Bắc`; q35 QA: `L25_V014,40519,3`. Có external proposals tương ứng trong chat nhưng user cũng cung cấp đáp án team-confirmed: chưa độc quyền attribution nguồn đầu tiên.
- q8 QA: final `L21_V018,21385,SEGA`, không phải SUBMARINE của lượt external review.
- q5 QA: final `L25_V024,22950,13`, không phải “10 tỉnh, thành” của checkpoint/lượt review đã đọc.
- q24 QA: final `L26_V311,3675,2 muỗng`, không phải `L26_V283` từ lượt external review đã đọc. Trùng answer string không đủ chứng minh cùng discovery.
- q27 QA: final `L26_V178,5375,1 màu`. Chưa tìm evidence đủ cho source discovery; không gán cho agent bác candidate L26_V332 trước đó.

### Bổ sung H7/11.2 — không thay final-v4 ledger

| Query | Top1 trong H7/11.2 | Top1 trong H5/11.8 |
| --- | --- | --- |
| q5 QA | `L25_V024,3509,10` | `L25_V024,22950,13` |
| q24 QA | `L26_V448,2816,2 muỗng cà phê` | `L26_V311,3675,2 muỗng` |
| q27 QA | `L26_V296,5392,3` | `L26_V178,5375,1 màu` |
| q9 KIS | `L30_V015,3451` | `L22_V005,11530` |

H7 q9 không đồng nhất CSV q9 của H4/H5; không kéo chuỗi external-orchestration đã chứng minh ở H4/H5 sang H7. Những query có top1 giống nhau vẫn có thể khác99 dòng còn lại. Chưa bổ sung nhãn A/B/C/D/E chỉ từ diffs mới.

## F. Competition-time vs post-competition timeline

Phải định nghĩa “post-competition” **theo từng vòng**: fix ngày 01/09 là sau R1/R2 nhưng trước R3. Ngày commit không chứng minh deployment vào một run.

| Mốc | COMPETITION-TIME evidence | Development sau một vòng | CURRENT HEAD / giới hạn |
| --- | --- | --- | --- |
| R1 21/08 | H1/H2 ZIP entry times; score user-confirmed; chưa khóa exact commit/runtime H2 | Các fix/experiments 24–28/08 là sau R1 | Không suy từ HEAD09/09 về trạng thái R1 |
| R2 28/08 | H3/H6; q19 override timestamp; multi-anchor rollback/measurement có snapshot riêng trước vòng | Sentinel validation 01/09 là subsequent improvement sau R2 | Commit trên branch riêng chưa chứng minh đã chạy trong R2/R3 |
| R3 04/09 | H4/H5/H7 đã map; chat q9/edits; run tạo H7 chưa khóa | Chỉ thay đổi có timestamp sau vòng R3 mới gọi post-R3 | HEAD `8fee5fd` commit 04/09 18:19:31; không tự coi đó là commit của mọi ZIP |
| Audit 09/09 | Không phải một contest run | Audit không tạo performance run mới | Dirty worktree + môi trường Python hiện tại được kiểm riêng |

Multi-anchor: implementation 24/08, diagnostic 27/08, rollback 28/08 — subsequent to R1, pre-R2; không gọi toàn bộ là post-three-round improvement. Sentinel end-to-end `f6af471`/`43c9adf` 01/09 — post-R2, pre-R3, deployment **UNRESOLVED**. Preflight/runtime/config commits 04/09 — pre-R3 theo timestamp, deployment vào exact scored artifact vẫn cần chứng cứ.

### Phân loại current selfcheck failure

Đã kiểm `python -m pytest --version` và `python scripts/preflight_check.py --profile development` tại `C:/Python314/python.exe`:

| Hiện tượng | Phân loại | Cách dùng trong report |
| --- | --- | --- |
| `No module named pytest`; pandas/pyarrow/numpy/elasticsearch/pymilvus thiếu | **Environment/config issue hiện tại** | Không suy test sản phẩm thất bại khi thi; 13 preflight failures chủ yếu do import dependency |
| `/health` không phản hồi; runtime/tùy chọn bị skip | **Current environment/service availability** | Không chứng minh API/LLM tại ngày thi hỏng |
| Holdout 6/13 verified; round1 manifest chưa ghi GT | **Evidence/promotion coverage gap** | Giới hạn claim độc lập về accuracy; không đồng nghĩa submission không chạy hoặc official score vô hiệu |
| Một số end-to-end fixes không là ancestor HEAD | **Current missing integration/merge**, deployment lịch sử chưa khóa | Chỉ claim branch implementation/validation; không tự gán là true production defect ở mỗi vòng |
| True production defect gây mất score | **Chưa chứng minh bằng current selfcheck** | Không viết “not release ready” trong technical report chỉ vì audit environment fail |

Không sửa environment/code vì đây là bước evidence audit. Không dùng interpreter khác để tuyên bố test xanh. Không suy 13 preflight failures thành 13 lỗi production độc lập.

## G. Claims now safe to make

- Bảy file người dùng gắn điểm đã có identity kiểm trực tiếp; ba final ZIP tương ứng 8.6/13, 13.6/15, 11.8/17 theo user confirmation. Score11.2 đã có H7 riêng, không còn gap thiếu file.
- Final R3 chứa 36 CSV; q9 từ chuỗi external orchestration đã tồn tại trong artifact final được người dùng định danh.
- R2 file4.4 có evidence của manual override; phải giữ khỏi nhãn “autonomous-only”.
- Người vận hành xác nhận không thay code/model/prompt/config/index/weights/settings giữa submission và các run được mô tả. Đây là attestation, không phải metadata audit độc lập.
- Official scores mô tả final workflow, không chứng minh autonomous-only performance. External assistance được disclose theo fact, không phóng đại contribution.

## H. Claims still unsafe / unresolved

- 11.4 là 11.2; file11.4 là autonomous; file4.4 unmodified autonomous; checkpoint R1 hiện có là nguồn của file6.8.
- Tên file/time ZIP là receipt hoặc giờ upload; mẫu số score là số query đúng; số query changed là human discovery count.
- Toàn bộ gain do human reranking hoặc external AI; gán output trùng answer cho một nguồn mà không có chain.
- Hiện trạng selfcheck/branch09/09 mô tả chính xác cả ba competition-time states.
- “Allowed/prohibited by BTC” cho external assistants. **COMPLIANCE AMBIGUITY** của working baseline giữ nguyên; đợt cung cấp ZIP này không bổ sung luật.
- Personnel issue là nguyên nhân trực tiếp score loss. Giữ nguyên không nêu tên trong technical narrative.

## I. Missing artifacts / confirmations cần cung cấp

1. **Đã nhận exact ZIP11.2/H7 — không cần gửi lại.** Còn cần checkpoint/trace/command hoặc log sinh đúng H7, cùng thông tin liệu gói đã được repack khi lưu/tải lại hay chưa (CSV hiện nằm ở root). Giữ11.4 là intermediate riêng.
2. **R2 autonomous artifact trước q19 manual override**, nếu có. Nếu 4.4 chính là gói đã override như hash H3, xác nhận để chính thức bỏ nhãn pure autonomous cho score này; không tạo một ZIP mới bằng cách xóa q19 rồi gán lại 4.4.
3. **R1 run bundle tạo H2/CD9BA6C3…**: checkpoint/trace, command hoặc log, commit/config/model manifest nếu còn; giải thích q3 QA không có trong gói24 CSV. Không cần gửi lại H2 đã nhận.
4. **BTC receipts/screenshots/submission history** cho ba final và các score baseline: submit ID, round, score, scoring subset nếu hiển thị, upload time; file name/hash nếu có. Không cần gửi API keys, tài khoản hay credentials.
5. Nếu muốn nâng equivalence từ attestation lên independently reconstructed: runtime/data/index/cache manifests ở đúng run, hoặc log chỉ rõ các mốc đầu/cuối để audit Git changes trong đúng cửa sổ.

Điều kiện của ghi chú đính kèm là chỉ cập nhật toàn bộ A–K strategy/outline sau khi không còn CRITICAL gap ảnh hưởng factual correctness. Gap thiếu ZIP11.2 đã đóng; R2 purity và nguồn run của các replay còn mở, nên **chưa chốt updated full strategy/outline và không viết full report**. Những cập nhật an toàn ở G có thể dùng ngay làm working evidence.

## Verification artifacts

[JSON metadata và query differences](C:/dev/aic2026/reports/internal_reporting_audit_20260909/score_labeled_artifacts.json) lưu đủ SHA, file times, ZIP entry times, query counts/top1, baseline matches và chín cặp diff cho bảy artifact. [Script tái kiểm](C:/dev/aic2026/reports/internal_reporting_audit_20260909/inspect_score_labeled_artifacts.ps1) chỉ đọc, không extract/overwrite ZIP. Các trường `official_result=unlinked` trong low-level diffs nói về query correctness/receipt chưa kiểm, không phủ nhận mapping aggregate score user-confirmed ở bảng C.
