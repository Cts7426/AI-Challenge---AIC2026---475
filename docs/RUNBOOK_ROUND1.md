# RUNBOOK — Đợt 1 sơ tuyển (T−30 phút chuẩn bị + 3 giờ thi)

> Bản in ra để chạy tay lúc thi. Không đọc code, không suy nghĩ kiến trúc — chỉ
> gõ theo thứ tự. Mọi lệnh chạy từ `C:\dev\aic2026`, dùng `.venv\Scripts\python.exe`.
>
> `T0` là lúc BTC mở gói truy vấn. Dùng mốc tương đối vì ảnh hướng dẫn không ghi
> giờ tuyệt đối.
>
> ⚠️ **Mỗi gói chỉ được nộp tối đa 3 LẦN và LẦN NỘP CUỐI CÙNG được tính điểm.**
> Hệ thống không tự chọn gói tốt nhất. Nộp sai định dạng vẫn mất một lượt; nộp
> một bản thử kém hơn sau bản tốt sẽ khiến bản kém hơn trở thành bài được chấm.

---

## 0. T−30 → T0 — chuẩn bị, chưa tối ưu gì thêm

| Mốc | Việc phải xong |
|---|---|
| **T−30 → T−25** | Đăng nhập đúng tài khoản BTC, vào đúng gói, ghi số lượt còn lại (phải là 3), kiểm mạng và dung lượng đĩa. |
| **T−25 → T−10** | Khởi động dịch vụ, khóa Sonnet + Q&A `legacy`, chạy release preflight. Có `HỎNG` thì xử lý ngay; không dùng `--skip-health`. |
| **T−10 → T−5** | Tạo sẵn `data\queries\`, `submissions\round1\`, `reports\round1\`; mở trang upload và đồng bộ đồng hồ. |
| **T−5 → T0** | Đóng băng code/config. Chỉ theo dõi dịch vụ; không chạy tuning, không đổi model, không xoá checkpoint. |

```powershell
$env:LLM_BACKEND = "api"
$env:LLM_API_MODEL = "claude-sonnet-5"
$env:QA_INFERENCE_MODE = "legacy"
docker ps
.venv\Scripts\python.exe scripts\preflight_check.py --profile release
```
`preflight` phải **exit 0** và in đúng `model=claude-sonnet-5`. Nó không tự chọn
model và không gọi API; sai model thì sửa hai biến môi trường trên. Có dòng
`HỎNG` → xem mục 5.

`legacy` và `robust` không phải hai lựa chọn thay thế nhau:

- `QA_INFERENCE_MODE=legacy` chọn **cách suy luận Q&A** đã regression.
- `--qa-submission-policy robust` chọn **cách ghi answer vào 100 dòng nộp**.
- Không có `--qa-submission-policy legacy`; CLI thật chỉ nhận
  `semantic|exact|robust|all`.

---

## 1. T0 → T+10 — nhận đề và khóa danh sách truy vấn

Giải nén gói đề của BTC ra một thư mục, ví dụ `data/queries/round1_raw/`.

```powershell
.venv\Scripts\python.exe scripts\make_queries.py data\queries\round1_raw --preview
```

**Nhìn bảng in ra và kiểm 4 thứ bằng mắt:**
1. Số câu khớp với đề BTC.
2. Cột `kiểu` đúng KIS / QA / TRAKE cho từng câu.
3. Cột `query_id` **giống hệt tên file BTC phát** (`query-1-kis`, không phải `kis_001`).
   Sai tên = BTC không ghép được đáp án với câu hỏi, **không có báo lỗi**.
4. Mỗi TRAKE có cột `N` đúng số event BTC yêu cầu. File `.txt` không mang
   field cấu trúc thì khai báo tường minh, ví dụ:

```powershell
.venv\Scripts\python.exe scripts\make_queries.py data\queries\round1_raw --n-events query-4-trake=4 --preview
```

Lặp `--n-events query-id=N` cho từng câu TRAKE. Không suy `N` từ dấu câu hoặc
đoạn mô tả; sai `N` làm mọi dòng TRAKE sai format.

Đúng rồi thì ghi ra:

```powershell
.venv\Scripts\python.exe scripts\make_queries.py data\queries\round1_raw --out data\queries\round1.jsonl
```

Nếu preview đã dùng `--n-events`, lệnh ghi file phải truyền lại đúng các
`--n-events` đó.

Nếu đề ở dạng .csv / .json thì truyền thẳng file đó. Nếu tên file không có chữ
KIS/QA/TRAKE thì thêm `--task KIS` (chạy 3 lần, mỗi kiểu một gói).

Đối chiếu thêm với ảnh BTC: tên file kết quả phải khớp `query_id`; tên video
không có `.mp4`; frame là số nguyên không có khoảng trắng bên trong.

---

## 2. T+10 → mục tiêu T+100 — chạy baseline đầy đủ

```powershell
$env:QA_INFERENCE_MODE = "legacy"
.venv\Scripts\python.exe run.py --queries data\queries\round1.jsonl --out submissions\round1 --zip --qa-submission-policy robust
```

- `--qa-submission-policy robust` là **bắt buộc gõ tường minh**, không dựa vào mặc định.
- Mỗi câu xong được ghi checkpoint ngay. **Ctrl-C hay mất điện thì chạy lại đúng
  lệnh trên — nó chạy tiếp, không làm lại từ đầu.**
- Một câu hỏng → nó chạy tiếp các câu khác và **không** sinh file nộp giả cho câu đó.
- Không bật `two_stage` trong buổi thi. Không đổi inference mode giữa một
  checkpoint; nếu đã lỡ đổi thì dừng và quay lại `legacy` trước khi resume.

Chạy lại vài câu cụ thể:
```powershell
.venv\Scripts\python.exe run.py --queries data\queries\round1.jsonl --out submissions\round1 --zip --qa-submission-policy robust --only query-3-qa,query-7-trake
```

Khi checkpoint đã đủ mọi câu, có thể sinh ba biến thể answer từ **cùng evidence**
mà không chạy lại retrieval/LLM:

```powershell
.venv\Scripts\python.exe run.py --queries data\queries\round1.jsonl --out submissions\round1 --zip --qa-submission-policy all
```

Lệnh này tạo `submission_semantic.zip`, `submission_exact.zip` và
`submission_robust.zip`. Gói mặc định đợt 1 vẫn là `robust`; chỉ chọn biến thể
khác nếu có xác nhận chính thức mới từ BTC hoặc replay cố định chứng minh nó tốt
hơn. Không dùng một lượt nộp chỉ để thử policy.

---

## 3. Chốt một candidate: validator → checksum → snapshot

Exit code phải là 0. Rồi mở `submissions\round1\submission\` và kiểm:

- Đủ **một file .csv cho mỗi câu** trong đề. Thiếu file = câu đó chưa chạy được,
  quay lại mục 2 với `--only`.
- Mỗi file **đúng 100 dòng** (mức tối đa BTC cho phép và là target release).
  Mỗi dòng TRAKE phải có đúng `N` frame theo đúng thứ tự event.
- Tên file khớp tên câu BTC phát.
- CSV là text UTF-8, không header, không phải `.xlsx/.xls`; Q&A tối đa 100 ký
  tự và phải quote/escape đúng CSV khi answer có dấu phẩy hoặc dấu `"`.
- Tên video không có `.mp4`; mọi frame là số nguyên.

Kiểm lại chính file ZIP sắp upload (phải in `HỢP LỆ`; exit code phải là 0):

```powershell
.venv\Scripts\python.exe -c "from backend.export import validate_zip,format_issues; p=r'submissions\round1\submission.zip'; e=validate_zip(p); print(format_issues(e)); raise SystemExit(1 if e else 0)"
```

`run.py` đã kiểm nội dung từng CSV trước khi đóng gói; lệnh trên mở lại ZIP để
chặn file hỏng hoặc thiếu lớp thư mục top-level `submission/`. Đừng tự nén tay.

```powershell
$policy = "robust"
$candidate = Resolve-Path submissions\round1\submission.zip
$sha = (Get-FileHash -Algorithm SHA256 -LiteralPath $candidate).Hash.ToLowerInvariant()
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
New-Item -ItemType Directory -Force reports\round1\candidates | Out-Null
$snapshot = "reports\round1\candidates\${stamp}_${policy}_$($sha.Substring(0,12)).zip"
Copy-Item -LiteralPath $candidate -Destination $snapshot
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $snapshot).Hash.ToLowerInvariant() -ne $sha) { throw "Checksum snapshot không khớp" }
Copy-Item -LiteralPath submissions\round1\checkpoint.jsonl -Destination "reports\round1\${stamp}_checkpoint.jsonl"
Copy-Item -LiteralPath submissions\round1\run.log -Destination "reports\round1\${stamp}_run.log"
"$stamp`t$snapshot`t$sha`tlegacy`t$policy`t$(git rev-parse HEAD)" | Add-Content -Encoding utf8 reports\round1\candidate_ledger.tsv
$sha
```

Đổi cả `$policy` và `$candidate` sang `submission_robust.zip`,
`submission_semantic.zip` hoặc `submission_exact.zip` nếu chủ ý chọn portfolio
đó. **Upload bản snapshot trong
`reports\round1\candidates\`, không upload file làm việc có thể bị ghi đè.**

---

## 4. Ba lượt nộp — lần sau cùng thay thế lần trước

| Lượt | Khi nào dùng | Hạn nội bộ | Không dùng khi |
|---|---|---|---|
| **1 — baseline an toàn** | Candidate `legacy + robust` đầu tiên đủ mọi CSV, validator sạch và đã có SHA/snapshot. Đây là đường lui nếu máy hoặc mạng chết sau đó. | Mục tiêu trước **T+120**. | Còn thiếu file/câu, ZIP chưa kiểm, hoặc portal báo sai format. Sai format vẫn mất lượt. |
| **2 — sửa lỗi có bằng chứng** | Đã sửa query hỏng/missing evidence/wrong mapping hoặc có candidate cố định được chứng minh tốt hơn; chạy lại validator và tạo SHA mới. | Nếu dùng, trước **T+145**. | Chỉ vì muốn “xem điểm”, đổi policy theo cảm tính, hoặc candidate không hơn lượt đang được tính. |
| **3 — final có chủ đích** | Candidate tốt nhất đã chọn, bất biến từ lúc hash đến lúc upload. Đây là lượt dự phòng cuối, không bắt buộc phải dùng. | Bắt đầu upload chậm nhất **T+165**, xác nhận trước **T+175**. | Candidate không chắc tốt hơn lượt cuối hiện tại. Không nộp lại chỉ để dùng hết 3 lượt. |

Sau **mỗi** lần portal báo thành công:

1. Kiểm tên gói/vòng và số lượt còn lại trên portal.
2. Chụp màn hình trang xác nhận. Ảnh BTC không cam kết có file receipt tải về,
   nên screenshot + thông tin dưới đây là receipt vận hành của đội.
3. Ghi ngay: số lượt, giờ, tên file snapshot, SHA-256, policy `robust|semantic|exact`,
   inference `legacy`, trạng thái portal và số lượt còn lại.
4. Không sửa/xóa candidate, checkpoint, `run.log` hoặc screenshot tương ứng.

Public Leaderboard chỉ chấm 50% đáp án. Dùng nó để phát hiện sự cố lớn (điểm 0,
portal không parse, thiếu query), không dùng dao động nhỏ để kết luận candidate
mới tốt hơn trên Private 100%.

Mẫu ledger tay trong `reports\round1\submission_ledger.tsv`:

```text
attempt<TAB>submitted_at<TAB>candidate_file<TAB>sha256<TAB>inference<TAB>policy<TAB>portal_status<TAB>remaining_attempts<TAB>receipt_image
```

### Hard stop

- **T+145:** dừng sửa code/config, dừng tuning và không đổi model/policy theo cảm
  tính. Chỉ được hoàn tất query đang chạy hoặc xuất portfolio từ checkpoint đủ.
- **T+150:** dừng mọi LLM/retrieval rerun; chọn candidate cuối từ các snapshot đã
  qua validator.
- **T+165:** bắt đầu upload cuối nếu thực sự cần lượt mới. Không tạo candidate mới.
- **T+175:** không bấm nộp candidate khác; chỉ xác nhận portal, screenshot và ghi
  ledger. Chừa 5 phút cuối cho lỗi mạng/giao diện, không cho thay đổi nội dung.

Nhớ: nếu lượt 1 đang tốt nhất và không có cải thiện có bằng chứng, lượt 1 phải
tiếp tục là **lần cuối cùng** — bỏ lượt 2/3 là quyết định đúng.

---

## 5. Sự cố — thang dự phòng

Đi từ trên xuống, **không nhảy cóc**.

| Triệu chứng | Làm gì |
|---|---|
| Sonnet báo hết credit | Không đổi model/provider giữa run. Kiểm số dư trên Anthropic Console, bổ sung credit rồi chạy lại cùng lệnh để resume checkpoint. |
| Sonnet timeout/429/5xx | Giữ nguyên Sonnet và cho retry hoàn tất. Nếu vẫn hỏng, dừng run mới, sửa mạng/provider rồi resume; không chuyển Opus/Haiku/Gemini giữa release. |
| Sonnet không phục hồi trước hạn | Nộp ZIP gần nhất đã qua validator. Không tắt preflight hoặc sinh Q&A bằng model chưa regression chỉ để đủ file. |
| Một câu hỏng giữa chừng | Kệ nó, để `run.py` chạy hết. Xong rồi chạy lại riêng câu đó bằng `--only`. |
| ES hoặc Milvus chết | `docker compose restart` rồi chạy lại lệnh mục 2 (checkpoint giữ nguyên phần đã xong). Milvus cần ~90s mới nhận request. |
| Máy/Docker chết hẳn | Không có đường cứu trong buổi. Nộp bản .zip gần nhất đã qua validator. |

---

## 6. Ba số cần nhớ

- **100 dòng mỗi câu, luôn luôn.** Không có hình phạt cho câu sai ở sơ tuyển,
  bỏ trống slot 51–100 là vứt điểm miễn phí.
- **Thứ hạng là tất cả.** Hạng 2 lên hạng 1 = +0.20, bằng giá trị cứu một câu từ
  trượt lên hạng 51.
- **TRAKE sai video = 0 tuyệt đối**, nhưng đúng video thì có điểm từng phần →
  luôn nộp đủ N khoảnh khắc, đoán còn hơn bỏ trống.

---

## 7. ⏱️ LLM: khóa cấu hình vận hành

Ngay trước mỗi lệnh run, đặt `LLM_BACKEND=api` và
`LLM_API_MODEL=claude-sonnet-5` như mục 0; preflight phải in lại đúng hai giá trị.
Baseline `run_20260820_2349` được tạo bằng cấu hình cũ nên chỉ dùng để phát hiện
hồi quy retrieval; chưa dùng để khẳng định chất lượng Sonnet.

### Thời gian mỗi câu (đo 21/08)

| Dạng | Thời gian | Vì sao |
|---|---|---|
| KIS | **3–7 giây** | 1 lần gọi LLM (dịch VI→EN), phần còn lại là search |
| TRAKE | ~20–30 giây | 1 lần gọi tách sự kiện + nhiều vòng search |
| Q&A | tốn nhất | release `legacy` gọi n=3/shot; worst case còn có text→image và candidate mở rộng |

Q&A là thứ ăn hết thời gian, không phải retrieval. **Chạy `run.py` một lần cho
TOÀN BỘ đề ngay khi mở đề**, đừng chạy từng câu — checkpoint lo phần an toàn.

`QA_INFERENCE_MODE=two_stage` có thể giảm mạnh request ở candidate yếu, nhưng
release vẫn dùng `legacy` cho tới khi replay trên tune + holdout vượt cổng
promotion. Không bật cờ này lần đầu ngay trong buổi thi.
