# Claim review nội bộ

> Editorial revision được người dùng duyệt sau bản review này: latency chính xác chỉ giữ internal; caption điểm và disclosure đổi theo wording người dùng, không nâng score thành receipt-verified. Các caveat trùng lặp được gộp; scope GT/diagnostic/timeline vẫn giữ. Xem [changelog](C:/dev/aic2026/reports/technical_report_draft_20260910/editorial_changelog.md) và [checklist cuối](C:/dev/aic2026/reports/technical_report_draft_20260910/final_btc_requirements_checklist.md). Nội dung review chi tiết dưới đây ghi lại bản draft đầu.

Ngày 10/09/2026. Review bản thảo hoàn chỉnh sau khi viết, không đưa tài liệu này vào báo cáo BTC. Nguồn chính sách: [approval mới](C:/Users/lehon/.codex/attachments/5efa2f47-4178-4dd6-8138-d52f54415962/pasted-text.txt), [final claim ledger](C:/dev/aic2026/reports/internal_reporting_audit_20260909/final_report_strategy.md). Không mở lại historical forensics.

## Rà soát claim theo section

| Report section | Important claim | Evidence | Confidence | Issue? |
| --- | --- | --- | --- | --- |
| 1 | Có KIS, QA, TRAKE dùng search chung | backend/tasks/runner.py; qa.py; trake.py | VERIFIED implementation | Không claim mọi feature hoạt động trong mọi scored run |
| 1 | Có diagnostic và rollback theo query | docs/evaluation/2026-08-28-multi-anchor-live-measurement.md; single-anchor-final-check.md | VERIFIED case cụ thể | Không coi regression là feature success |
| 2 | Milvus vector và Elasticsearch text/metadata/objects | backend/retrieval/search.py; backend/indexing loaders | VERIFIED implementation | Mô tả cơ chế, không chứng nhận live deployment từng lượt |
| 2 | 873 video, 177.321 keyframe | reports/data_audit.md:8,32; BATCH1_DATA_AUDIT_20260821.md | VERIFIED recorded audit | Qualification ngay sau số; không live-index count mọi round |
| 2 | keyframe_id liên kết nguồn và frame map | backend/common/frame_assets.py; search.py; frame_map records | VERIFIED implementation | Không đổi ordinal thành frame bằng suy tên file |
| 2 | Kiểm cấu trúc không là pixel parity toàn kho | audit_L_P.md; AGENTS.md; frame_assets tests | VERIFIED distinction | Không claim 873/873 pixel verified |
| Hình 1 | Core khác operator và external AI | Source modules + accepted workflow disclosures | VERIFIED implementation / TEAM-REPORTED workflow | External assistants ở ngoài core; internal adapter không đồng nghĩa local model |
| 3 | VI→EN caption và expansion kiểm độ dài | backend/retrieval/query_understanding.py:89,115; token guard | VERIFIED implementation | Không đảm bảo bản dịch luôn đúng; nêu limitation |
| 3 | CLIP ViT-B/32, 512 chiều, 77 token, L2/COSINE | data/config/clip_model.py; text_query.py; load_clip.py; query_understanding.py | VERIFIED implementation/config | Không gán mọi query/mọi round chỉ dùng một encoder |
| 3 | CLIP như cơ chế text/image retrieval | Radford et al., ICML 2021, nguồn PMLR đã mở | VERIFIED primary reference | Không lấy benchmark trong paper làm kết quả đội |
| 3 | ASR đoạn và metadata video quy về keyframe | search.py: phần branches và fusion | VERIFIED implementation | Không trộn đơn vị trước fusion |
| 3 | Weighted RRF theo trọng số/(hằng số+rank) | search.py:654; data/config/search_weights.py; Cormack et al. | VERIFIED code + primary RRF reference | Comment cũ nói không trọng số không được ưu tiên hơn implementation; không đưa weight hiện tại như config thi |
| 3 | Một nhánh lỗi có thể trả rỗng | search.py branch exception handling | VERIFIED implementation | Không gọi runner-success là all-branches-success |
| 3 | Gom shot, cấp slot/frame riêng | backend/slot/allocator.py; data/config/slot_budget.py | VERIFIED implementation | Không đưa bảng slot hiện tại thành hằng số mọi round |
| 3 | QA evidence → LLM/VLM adapter → answer/frame, cache | qa.py:collect_evidence, capture_evidence, ask_llm, cache; qa_portfolio.py | VERIFIED implementation | Theo kiểu câu hỏi/chế độ; không hứa mọi answer có evidence đủ |
| 3 | TRAKE tách sự kiện, DP thứ tự, min gap, fallback nội suy | trake.py:238; parse_events, _fill_missing, _localize_in_video; tests/test_trake.py | VERIFIED implementation | Nội suy được disclose; không nói mọi frame có bằng chứng trực tiếp |
| 3 | Validator/CSV/ZIP và giới hạn dòng/task | backend/export/exporter.py; data/config/submit_format.py; tests/test_validator.py | VERIFIED implementation | Không chứng nhận bytes của mọi competition ZIP đã qua đúng validator |
| 3 | Runtime fingerprint gồm config, critical sources, model choice | backend/tasks/runner.py:233 | VERIFIED implementation | Không claim snapshot DB/dependency đầy đủ; roadmap nêu phần thiếu |
| 4 | KIS R@k và điểm trung bình 5 cutoffs | dev_set/tools/scoring.py:87,115; data/config/scoring.py | VERIFIED code | Chỉ giải thích diagnostic KIS, không tự chấm lại score BTC |
| 4 | Multi 19/19, không fallback/crash/mapping violation | docs/evaluation/2026-08-28-multi-anchor-live-measurement.md | VERIFIED diagnostic | Không nói semantic frame correctness đạt 100% |
| 4 | Final 0,4000→0,3263; R@100 0,5789→0,5263; 4 tăng/5 giảm/10 giữ | Cùng diagnostic doc, 19 KIS dress25 | VERIFIED recorded metrics | Ground truth legacy/unverified và runtime caveat sát số liệu |
| 4 | Single recheck 19/19, Final 0,4000, R@100 0,5789 | docs/evaluation/2026-08-28-round2-single-anchor-final-check.md | VERIFIED diagnostic | Không gọi điểm final BTC phục hồi; không infer controlled causal effect |
| Bảng 1 | 12 mẫu CLIP cosine mean 0,9999, min 0,9993 | reports/BATCH1_DATA_AUDIT_20260821.md:71 | VERIFIED recorded sample test | Không mở rộng thành full parity hoặc recall |
| Bảng 1 và 4 | Q&A refusal 2→0, QA0,200/overall0,363 giữ nguyên | git 43c9adf và f6af471; docs/release trên branch codex/qa-last-3h | VERIFIED branch-level artifacts; deployment UNKNOWN | Nêu rõ sau R2/trước R3, chưa chứng minh deployment trong scored submission |
| 4 | R3 local 26 KIS×100; median6,675s; QA359,605s/n8; TRAKE76,575s/n2 | submissions/round3/checkpoint.jsonl; trace.jsonl; audit_L_P.md:57–59 | VERIFIED historical trace | Không gán H7/score; không gồm toàn operator time; 100 rows không là correct/independent candidates |
| 5 | Human verification/reranking và manual discovery | User addendum; internal_attribution.md; selected checkpoint/chat chains | TEAM-REPORTED tổng thể, selected cases VERIFIED | Không “humans only reranked”; không định lượng contribution |
| 5 | ChatGPT/Claude ngoài pipeline, direct proposals có dùng final | User confirmation; internal_attribution.md; evidence_closure.md q9 linkage | TEAM-REPORTED tổng thể, selected transfer VERIFIED | Có chữ “theo xác nhận của đội”; không gán toàn bộ external-reviewed queries cho external model |
| Bảng 2 | 8,6/13;13,6/15;11,8/17 là final scores | Identified H1/H6/H5; score_labeled_artifacts.json; user mapping | TEAM-REPORTED scores; VERIFIED artifact identities | Caption nêu nguồn đội, không receipt-verified/autonomous accuracy |
| 6 | Retrieval miss/wrong frame/missing evidence/refusal | Diagnostic failure classes; rehearsal; trake fallback implementation; accepted workflow | VERIFIED diagnostic / SUPPORTED broader limitation | Không gán failure cho mọi query hoặc quantify score loss |
| 6 | Bốn hướng tiếp theo | Kết nối tới limitation ở 3–5 | Proposed future work | Không gọi đã triển khai/passed release |

## Nguồn nội bộ để mở nhanh

- [Source retrieval](C:/dev/aic2026/backend/retrieval/search.py), [query processing](C:/dev/aic2026/backend/retrieval/query_understanding.py), [runner](C:/dev/aic2026/backend/tasks/runner.py:233).
- [Q&A](C:/dev/aic2026/backend/tasks/qa.py), [TRAKE](C:/dev/aic2026/backend/tasks/trake.py:238), [exporter](C:/dev/aic2026/backend/export/exporter.py).
- [Data audit](C:/dev/aic2026/reports/data_audit.md), [CLIP sample check](C:/dev/aic2026/reports/BATCH1_DATA_AUDIT_20260821.md:71).
- [Multi-anchor measurement](C:/dev/aic2026/docs/evaluation/2026-08-28-multi-anchor-live-measurement.md), [single recheck](C:/dev/aic2026/docs/evaluation/2026-08-28-round2-single-anchor-final-check.md).
- [Historical trace/latency summary](C:/dev/aic2026/reports/internal_reporting_audit_20260909/audit_L_P.md:57), [artifact closure](C:/dev/aic2026/reports/internal_reporting_audit_20260909/evidence_closure.md), [internal attribution](C:/dev/aic2026/reports/internal_reporting_audit_20260909/internal_attribution.md).
- [CLIP paper](https://proceedings.mlr.press/v139/radford21a.html), [RRF paper](https://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf): kiểm primary references ngày10/09, không phải mở lại compliance forensics.

## Review tách khỏi bước viết

Đã rà bản hoàn chỉnh theo 8 trục người dùng yêu cầu: BTC format, score attribution, external AI, human discovery, timeline, metrics, architecture và tone. Chỉnh trong vòng review:

1. Giữ explicit statement một số external proposals được dùng trực tiếp trong final, không rút thành “hỗ trợ chung”.
2. Bổ sung định nghĩa diagnostic KIS R@k/Final để số đo có thước rõ.
3. Đặt qualification legacy GT/runtime sát multi-anchor metrics; branch-only/deployment caveat sát Q&A fix.
4. Không đưa replay scores, personnel, receipts, hashes, local paths, dirty state hay selfcheck vào report chính.
5. Sửa đường nối hình tránh chữ và giảm nhãn quá dài; sửa renderer để bốn mục roadmap thành bốn đoạn riêng.
6. Rút các câu lặp ở workflow để giữ 4 trang mà không bỏ disclosure.

Không còn contradiction factual cần mở lại forensic trong phạm vi claim của bản thảo. Đây là review tài liệu, không phải tái chạy retrieval, xác nhận đúng đáp án hay chứng nhận tuân thủ mọi quy định thi. Compliance ambiguity vẫn giữ nội bộ theo chính sách đã duyệt.

## Kiểm tra bàn giao

- PDF:4 trang, MediaBox A4,132.765 byte; đã mở và kiểm cả4 ảnh render cuối. Kiểm text sau chuẩn hóa whitespace xác nhận đủ3 điểm, ChatGPT/Claude, manual discovery, direct use và qualification không phải autonomous benchmark; không có các internal markers bị cấm. Phép tìm nguyên chuỗi ban đầu gặp linebreak PDF, đã kiểm lại bằng whitespace-normalized extraction; không phải mất disclosure trong file.
- Tóm tắt form:178 đơn vị tách bằng khoảng trắng, trong khoảng100–200.
- `git diff --check`: exit0, chỉ có warning CRLF tại file người dùng sửa sẵn ngoài phạm vi.
- `python scripts/selfcheck.py`: exit1; test suite không đọc được kết quả, preflight5 đạt/13 hỏng/3 bỏ qua, holdout6/13 verified, round1 GT0/25. Đây là trạng thái môi trường/hệ thống hiện tại, không dùng suy ngược contest-time hay chặn bản thảo có claim đã giới hạn. Không sửa môi trường, GT hoặc production để phục vụ báo cáo.
- Builder PDF chạy bằng runtime artifact đóng gói. Không coi runtime này là môi trường test production và không tuyên bố production tests đạt.
- Không upload, submit, gửi BTC hoặc thay đổi competition artifacts. Chờ người dùng review draft.
