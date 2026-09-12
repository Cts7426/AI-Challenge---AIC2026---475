# Contribution map — INTERNAL ONLY

Ngày audit 09/09/2026. Bảng này không phải technical report, không phải kết luận về mức độ tham gia hoặc trách nhiệm cá nhân. Không đưa tên người được cho là ngừng trao đổi vào narrative công khai. Không suy “không có commit” thành “không có contribution”.

Nguồn phân công gốc: [PHAN_CONG_TASK_AIC2026_6_TUAN.docx](https://drive.google.com/file/d/1elNrWi0An8Zezar8o4ZWqZxn1gVa_hci/view), file metadata tạo 01/08/2026; kế hoạch 6 tuần 03/08–13/09, freeze 09/09, submit 11/09. Các giờ công trong kế hoạch là ước tính, không phải timesheet. Đối chiếu với Git và `BUILD_TASKS.md`, không coi tick checkbox tự nó là verification.

| Member | Original responsibility | Actual implementation đã có evidence | Evidence | Reassigned work / giới hạn |
| --- | --- | --- | --- | --- |
| Thạch (`Cts7426`) | Tech lead, retrieval core; backup query/eval/ops | Retrieval/integration/runner; adapter và query understanding được ghi làm thay; diagnostic/rollback và branch validation | Original plan; `a33b09f` 11/08; `BUILD_TASKS.md` C0.1/C1.1; `d3eb66d`; branch `f6af471`/`43c9adf` | Adapter/query understanding chuyển sang Thạch có evidence trực tiếp. Không gán toàn bộ contribution của branch chưa merge cho release HEAD |
| Hoàng Công Lý | Data factory; backup tooling | Các workstream data/retrieval và QA/TRAKE fixes; integration | Original plan; `327d1ea` 18/08 sửa QA/TRAKE, `0c4bf04` 20/08 TRAKE RRF; Git file diff/ownership | Có actual work vượt phân công data ban đầu; formal reassignment date cho từng phần còn thiếu |
| Ngô Xuân Minh Hoàng (`Ngo Xuan Minh Hoang`, alias `hoangnxm`) | Tooling/UI, slot/export, analytics; backup data | TRAKE depth, QA và các công việc integration/tooling | Original plan; `88238f2` 21/08; `84f9dd0` 28/08; Git diff | Thực hiện QA/TRAKE ngoài workstream ban đầu có evidence; không dùng commit count thay chứng cứ giờ công |
| Thi | Query understanding, answer generation, LLM adapter, QA/TRAKE; backup retrieval | Chưa tìm được implementation độc lập đủ định danh trong tập Git đã xét | Original plan; C0.1/C1.1 trong BUILD_TASKS ghi người khác làm thay | Hai task cụ thể chuyển cho Thạch; không tự gán contribution, cũng không kết luận mọi hoạt động khác bằng 0 |
| Quang Linh | Evaluation/research/ops; backup tech lead | Chưa tìm được commit author đủ định danh trong tập Git đã xét | Original plan; thiếu log hoạt động non-code/thi đấu để reconstruct đầy đủ | Không đồng nhất absence trong Git với ngừng tham gia; contribution vận hành/manual search chưa audit đủ |

## Commit concentration — mô tả activity, không phải effort

Lệnh đã chạy: `git log --all --no-merges --since=2026-08-01 --until=2026-09-05 --format='%an'`.

| Author string / nhóm alias | Số commit |
| --- | ---: |
| Cts7426 | 48 |
| Hoàng Công Lý | 91 |
| Ngo Xuan Minh Hoang | 45 |
| hoangnxm | 1 |
| Claude | 2 |

Tổng 187 commit unique trong tập Git được lệnh chọn; 185 human-authored theo author strings, tập trung ở ba nhóm alias. Alias matching dựa trên project context, không phải xác minh danh tính độc lập. `--all` gồm cả nhánh chưa merge; không phải 187 thay đổi đều đã deploy. Co-author/footer và AI coding assistance cần xét riêng; commit author không chứng minh người đó viết một mình.

## Timeline constraint: điều đã biết và chưa biết

- User-confirmed: một người được giao task kỹ thuật ngừng trao đổi; ba người còn lại phải phân phối lại việc.
- Repository-proven: ít nhất hai task được ghi rõ làm thay; công việc implementation thực tế vượt phân công gốc; nhiều integration/fix sát các vòng thi.
- Plan ban đầu dùng mốc sau ba ngày thi thực tế; đây là biến schedule cần xét cùng resource constraint, không đổ toàn bộ nguyên nhân cho nhân sự.
- Chưa có timesheet, lịch testing trước/sau reassignment, cancellation logs, actual hours hoặc complete operator contribution history.
- Vì vậy không khẳng định số giờ tăng, số test bị cắt, phần trăm effort từng người, hoặc điểm mất do thiếu người.

## Inclusion decision

Ảnh form BTC hiện có không yêu cầu contribution theo tên. Chưa đưa bảng vào report. Nếu BTC bổ sung yêu cầu, chỉ nêu contribution thực tế có evidence, xin bổ sung non-code contributions trước khi kết luận thiếu; không phân bổ đều cho đẹp bảng.

Đề xuất public narrative hiện tại không tên: có reassignment và integration/validation gần deadline; ảnh hưởng của giảm capacity tới testing chưa định lượng. Muốn nâng thành “resource reduction compressed validation” cần evidence plan-vs-actual nối rõ chuỗi.
