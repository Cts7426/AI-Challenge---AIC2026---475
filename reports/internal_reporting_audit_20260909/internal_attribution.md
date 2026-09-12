# Query attribution ledger — INTERNAL, partial reconstruction

> Classification/gate cuối cùng theo [final strategy](C:/dev/aic2026/reports/internal_reporting_audit_20260909/final_report_strategy.md): phần chưa exhaustive là non-blocking; không tự suy contribution counts. R2/4.4 chốt operator-assisted, autonomous-only score UNKNOWN/NOT RECOVERED.

> Cập nhật final-v4: xem phần E của [Evidence Closure](C:/dev/aic2026/reports/internal_reporting_audit_20260909/evidence_closure.md). Matrix dưới đây là snapshot trước khi nhận final11.8: final mới đủ36 CSV; q5=13, q24 dùng L26_V311, q27 dùng L26_V178; q9 giữ nguyên từ gói11.4. Không gán proposal cũ cho final chỉ vì cùng query ID.

Audit 09/09/2026. Không công bố raw chat hay coi nhãn agent `confirmed` là GT. Prefix `query-p2-*` xuất hiện trong cả bộ đợt 2 và đợt 3: mọi khóa dưới đây phải đọc cùng **round + query_hash** trong checkpoint/raw query, không join chỉ bằng tên file.

## Nguồn chat đã định danh

| ID | Nguồn | Mốc dùng trong audit |
| --- | --- | --- |
| C1 | Claude project log [a0c0a2f8…jsonl](C:/Users/lehon/.claude/projects/C--dev-aic2026/a0c0a2f8-a749-4947-8039-66f56a45a72e.jsonl:392) | 04/09 13:31–13:44 UTC: tool calls đọc OCR/ASR, frame map và candidate QA; dòng 392/396/400/407/411 tìm q6 trên dữ liệu đội; dòng 496 summary. Dòng 523/531 xây evidence page từ raw BTC images |
| C2 | Claude project log [9214043c…jsonl](C:/Users/lehon/.claude/projects/C--dev-aic2026/9214043c-f767-48a8-bb64-3e67fe176bdd.jsonl:167) | 04/09 14:03 UTC user nhờ tìm q9; 14:11:43 UTC assistant đưa top-20 từ rerun pipeline, không phải câu trả lời từ internet |
| C3 | Claude project log [0f0adc06…jsonl](C:/Users/lehon/.claude/projects/C--dev-aic2026/0f0adc06-5ae6-43bf-912f-9ae095578407.jsonl:135) | 04/09 13:34 UTC đối chiếu q18; đồng thời có thao tác môi trường/UI trong phiên này, nên không giả định mọi run cùng runtime |
| X1 | Task Codex **“xác nhận lại các đáp án ứng viên này, tôi muốn chính bạn tự…”**, ID `01a06cac-a2fb-7311-a94b-ff2520355cb3` | Lượt kiểm chứng QA/TRAKE; các lượt 04/09 14:17:55, 14:21:37, 14:27:29 UTC chỉnh q9 từ Downloads `exam_final.zip`; output hash đã đối chiếu với file thật |
| X2 | Task Codex **“Sửa đáp án file ZIP đợt 2”**, ID `01a06cec-2eac-7790-9265-20fa346fdce3` | Tên task giữ nguyên nhưng nội dung thực tế là R3: 04/09 14:58:13 UTC user nói 11,4/17, đưa 11 đáp án team-confirmed; 15:04:23 đưa thêm 14, 15:05:01 thêm TRAKE34 |
| X3 | Task Codex **“Cập nhật đáp án submission P2”**, ID `01a048f1-8d72-71d3-8da9-e86927e15c43` | R2 28/08: user đưa danh sách đáp án đội xác nhận để agent sửa file; không mặc nhiên agent là người phát hiện |

Codex là bề mặt thao tác; tên ứng dụng không tự chứng minh model/backend là ChatGPT. Một số lịch sử được import từ external agent. User-confirmed ChatGPT/Claude assistance được giữ riêng với định danh model thực tế của từng phiên, phần chưa thấy ghi unknown.

## Matrix query-level

“System candidate available” dưới đây so với `submissions/round3/checkpoint.jsonl` (hoặc checkpoint R2 nêu riêng), không mặc nhiên đúng file ngay trước human intervention. “Final result” ghi **artifact outcome**, còn BTC final correctness/receipt chưa nối. Các cột không loại trừ nhau và không cộng thành tỷ lệ contribution.

| Query | System candidate available? | Human verify/rerank/edit | Manual discovery | External AI | Final result / evidence limit |
| --- | --- | --- | --- | --- | --- |
| R2 q19 QA | Bản trước override chưa có record thành công q19; chưa xác định original candidates đầy đủ | Checkpoint có operator evidence, manual override; X3 đưa frame 3740 | Nguồn tìm ban đầu chưa rõ; không gọi absence trong checkpoint là discovery proof | Agent chỉnh gói theo user; origin answer unknown | Local checkpoint `L30_V043,1818,Lý Thường Kiệt`; X3 yêu cầu frame 3740. Cần nối row cuối với receipt, không gán ZIP local cho 4.4 |
| R2 q14 KIS | Exact final top-1 ở rank 4 của ZIP local | Artifact chỉ thay thứ tự; X3 có thao tác operator-assisted | Không suy discovery từ permutation | Có phiên external editing, cần nối instruction đúng row để định danh tác nhân | Một permutation-only trong cặp ZIP R2; BTC query score unknown |
| R3 q9 KIS | Engine sinh candidate mới trong rerun do Claude điều khiển; không đồng nhất batch ban đầu | User chuyển top-20, quyết định cách thay ba dòng trùng | Chưa có evidence human discovery riêng trong case này | C2 gọi pipeline; X1 chỉnh ZIP và kiểm mapping/dedup | Chuỗi tới ZIP hash `219433E3…` được kiểm bằng file thật; 100 dòng q9, chỉ q9 thay đổi trong 26 CSV. Chat gọi intermediate 11.4, chưa phải receipt/final11.8 |
| R3 q14 QA | Video `L30_V047` ở rank1, frame4911; answer `TODO`, không có answer exact `5` trong 100 rows | X2 cung cấp `L30_V047,5540,5` | Ai phát hiện đầu tiên chưa xác định | X1 đề xuất 5, dùng ảnh và bài báo ngoài để đối chiếu | v2 thêm q14 với answer5, frame5540; giá trị phù hợp đề xuất nhưng causal origin và BTC final acceptance chưa khóa |
| R3 q18 QA | `L30_V010,3013,Trường tiểu học Công Hải` đã ở rank1 | X2 chốt frame3550, cùng answer | Không thấy bằng chứng cần discovery mới để có video/answer | C3/X1 đối chiếu lại output có sẵn | v2 có school answer; không quy answer này thành external discovery mới |
| R3 q6 QA | Video `L25_V018` đã ở rank10/frame8100, answer `TODO`; không có “Tây Bắc” trong 100 answers | X2 chốt `L25_V018,14150,Tây Bắc` | Không có evidence độc lập ai tìm ra trước | C1 trực tiếp query OCR trên 10 video candidates của đội; tìm region, đề xuất Tây Bắc; X1 corroborates | corrected/v2 có cùng video/answer, khác frame. Evidence hỗ trợ external reasoning dựa trên internal candidates; chưa chứng minh nguồn duy nhất hay receipt final |
| R3 q8 QA | `L21_V018,21220,SUBMARINE` đã ở rank4; pipeline top1 lại `L30_V075,4592,Tuổi Trẻ TV`; không thấy `SEGA` trong 100 answers | X2 chốt `L21_V018,21385,SEGA` | Nguồn cụ thể của SEGA chưa rõ | C1/X1 đề xuất/kiểm SUBMARINE dựa trên candidate đã có | corrected/v2 dùng SEGA; không tính SUBMARINE là external answer được nhận. Có hỗ trợ xác định video nhưng không đồng nhất answer |
| R3 q35 QA | `L25_V014` không có trong 100 exported answers; top1 `L25_V057,32225,0,03 mol`; record-level `answer_text=4` khác top1 row | X2 chốt `L25_V014,40519,3` | Team có thể tìm độc lập; origin cuối unknown | X1 bác video trước, đề xuất `L25_V014,39983,3` | v2 thêm video/answer tương ứng, frame khác; cho thấy external proposal ngoài exported set, không chứng minh ngoài toàn bộ internal retrieval pool |
| R3 q24 QA | Top1 `L26_V229,1976,TODO`; `L26_V283` không trong 100 answers | Chưa nối final human action | Unknown | X1 bác candidate, đề xuất `L26_V283,3422,2 muỗng` | Không có q24 trong v2 đã audit; không nói đề xuất đã nộp hoặc đúng |
| R3 q27 QA | Có nhiều hypotheses; top1 `L26_V207,4656,1 màu`, không phải candidate `L26_V332,4435` được đem ra review | Unknown | Unknown | X1 bác candidate L26_V332; không tìm được answer xác nhận trong lượt đọc | q27 không có trong v2; không dùng summary review thay cho actual ranked output |
| R3 q5 QA | “10 tỉnh, thành” đã có; rank1 frame557 và rank2 frame4109 ở `L25_V024` | Unknown | Không chứng minh discovery | X1 kiểm lại, cuối cùng đề xuất10 | Không có q5 trong v2; không tính đây là contribution answer mới |
| R3 q21 TRAKE | Pipeline có candidate `L26_V156`; frame tuple phải so riêng | X2 chốt `3260,3780,4784,6730` | Unknown | X1 kiểm sparse frames và đề xuất khoảng event, không khẳng định exact event bằng video dày | corrected/v2 thêm tuple user chốt; không coi sparse-frame check là BTC exact frame validation |
| R3 q34 TRAKE | Candidate review từ pipeline là `L24_V026` | X2 chốt `L24_V013,9880,10230,10355,10600` | Nguồn tìm L24_V013 chưa khóa | X1 bác candidate trước, không tìm tuple final trong lượt đọc | v2 thêm tuple từ user; không quy discovery final cho agent |
| Các R2/R3 KIS khác trong X2/X3 | Xem JSON diffs; có những top1 đã ở ZIP trước, có những row mới | Có instruction team-confirmed và agent editing | Unknown cho nguồn ban đầu nếu không có chat tìm kiếm | Editing được chứng minh; discovery không tự suy | Giữ unknown cho query chưa reconstruct; không tạo số query human/agent-correct |

## Case study q9 — chuỗi đã nối bằng file thật

1. C2, 04/09/2026 14:11:43 UTC: Claude trình top-20 từ pipeline RRF, có vector/OCR probe/metadata/ASR. Đây là external orchestration của internal engine.
2. X1, 14:17:55 UTC: user đưa đúng 20 cặp, yêu cầu sửa Downloads `exam_final.zip`.
3. X1, 14:21:37 UTC: user phát hiện staging chỉ còn 20 dòng và yêu cầu giữ 100. Agent nhận lỗi; phát hiện ba cặp trùng ở tail.
4. X1, 14:27:29 UTC: user quy định lấy dòng cũ14/17/19 thay vào tail23/41/53. Logged checks: 100 unique rows, 20 frame map đúng, 25 CSV khác byte-unchanged.
5. Tool output hash `219433E34C99E53A4D3EB38D43F3C31ECAEA2104812BF0FE77B8C1DECA5C7BD8`; file thật Downloads `THANH_NGHE_round3.zip` và repo `THANH_NGHE_round3.original.zip` cùng hash. Audit lại cho thấy chỉ q9 khác so với Downloads `exam_final.zip` hash `785B61D4…179C72`.
6. X2, 14:58:13 UTC: user gọi ZIP này 11,4/17 rồi yêu cầu sửa tiếp. Có linkage chat→artifact→user-reported intermediate score, **chưa có receipt**, không đủ gán final11.8.

Case còn thể hiện lỗi thao tác của external agent và human correction; không nên kể như một chuỗi hoàn toàn tự động không lỗi. Không có đo lường uplift của 20 candidates này.

## Nguồn ngoài dataset được nhận diện

X1 có viện dẫn bài [lớp dạy bơi ở huyện đảo TP.HCM](https://tuoitre.vn/lop-day-boi-mien-phi-cho-tre-o-huyen-dao-tp-hcm-20240812112110319.htm) khi xác định q14. Trong audit này URL là bằng chứng nguồn mà chat đã dùng, không phải xác nhận mới rằng answer 5 là BTC ground truth. C1 có tool calls trực tiếp OCR/ASR và raw BTC images; không vì chạy Claude bên ngoài mà tự kết luận dữ liệu cũng ở ngoài dataset.

## Gaps và phạm vi tiếp theo

- Global facts về ChatGPT/Claude và direct final use do người dùng xác nhận; matrix hiện chưa nhận diện hết mọi query hoặc mọi ChatGPT session.
- q14/q6/q35 là candidate cases để người dùng xác nhận final origin, không dùng sự trùng answer làm causal proof.
- Bản v2 thiếu ba query không chứng minh final thực sự thiếu: final ZIP/receipt vẫn chờ.
- Không yêu cầu người dùng chép lại C1–C3/X1–X3 đã tìm. Chỉ cần bổ sung link/session hoặc source-to-final confirmation cho case ngoài phạm vi đã đọc.
