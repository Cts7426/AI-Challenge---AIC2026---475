# KẾ HOẠCH NGHIỆM THU — LUỒNG B (DATA FACTORY)

**Chủ sở hữu:** Hoàng Công Lý · **Phạm vi:** toàn bộ `data/derived/` · **Ngày lập:** 07/08/2026

---

## 0. Nguyên tắc nghiệm thu

### 0.1. Ba tầng kiểm tra

| Tầng | Tên | Bản chất | Quy tắc |
|---|---|---|---|
| **L1** | Assertion tự động | Đúng/sai nhị phân, chạy bằng script | **Bắt buộc 100% xanh.** Một assertion đỏ = task chưa được nghiệm thu, không thương lượng. |
| **L2** | Phân phối thống kê | Số liệu + ngưỡng cảnh báo | Vượt ngưỡng → điều tra trước khi ký, có thể ký kèm ghi chú rủi ro. |
| **L3** | Mắt người | Lấy mẫu, người thật xem | Có tên người ký, có ảnh chứng cứ lưu lại. |

**Lý do tách 3 tầng:** lỗi nguy hiểm nhất của Luồng B là *lỗi im lặng* — pipeline chạy xong, file đầy đủ, không có exception, nhưng nội dung sai lệch một frame. L1 bắt lỗi cấu trúc, L2 bắt lỗi phân phối, chỉ L3 bắt được lỗi "đúng cấu trúc nhưng sai nội dung".

### 0.2. Nguyên tắc bất di bất dịch

1. **Khoá join duy nhất toàn hệ thống là `(video_id, frame_idx)`.** Mọi artifact phải join được bằng khoá này. Không có ngoại lệ, không có biến thể float, không có timestamp làm khoá.
2. **`frame_idx` luôn là `int`**, suy ra từ `fps = fps_num / fps_den` dạng phân số. Bất kỳ chỗ nào trong code xuất hiện `float(fps)` để tính frame là một lỗi cần chặn ở review.
3. **Nghiệm thu chạy trên 20-video dev subset trước** (vòng lặp nhanh, < 10 phút), rồi mới chạy full corpus.
4. **Không teammate nào được bắt đầu dùng artifact khi gate của nó chưa xanh.** Luồng B là critical path — cho người khác dùng dữ liệu chưa nghiệm thu là nhân lỗi lên 4 lần.
5. **Mọi lần ký nghiệm thu phải ghi commit hash.** Artifact sinh từ commit khác = chưa nghiệm thu.

### 0.3. Hạ tầng nghiệm thu cần dựng trước

```
scripts/audit/
  __init__.py
  common.py            # load schema, phash, contact_sheet, report writer
  b01_video_audit.py
  b01_mapping_check.py # công cụ neighbor-check — quan trọng nhất
  b11_shots.py
  b12_keyframes.py
  b13_asr.py
  b14_ocr.py
  b17_bm25.py
  b_integration.py     # nghiệm thu tổng, join xuyên suốt
  run_all.py           # sinh REPORT.html
data/config/schemas/
  video_manifest.schema.json
  keyframe_map.schema.json
  shots.schema.json
  keyframe_index.schema.json
  asr.schema.json
  ocr_voted.schema.json
  bm25_docs.schema.json
data/derived/_audit/
  REPORT.html          # bảng đèn xanh/đỏ toàn bộ gate
  metrics.json         # số liệu thô để so sánh giữa các lần chạy
  signoff.md           # nhật ký ký nghiệm thu
  evidence/            # ảnh contact sheet, mẫu L3
```

Một lệnh duy nhất: `python -m scripts.audit.run_all --scope dev|full`

### 0.4. Mẫu bản ghi ký nghiệm thu (`signoff.md`)

```markdown
## B1.2 — Keyframe extraction
- Ngày: 2026-08-11 21:40
- Commit: a3f9c21
- Scope: full corpus (1,842 videos)
- L1: 14/14 PASS
- L2: 6/7 trong ngưỡng — cảnh báo: blank-frame ratio 2.4% (ngưỡng 2%), nguyên nhân: 3 video có letterbox đen, đã whitelist
- L3: 50/50 pHash khớp, người kiểm: Công Lý; đối chứng chéo: Thạch (10 mẫu)
- Kết luận: PASS
- Rủi ro còn lại: chưa test video VFR nào trong mẫu L3 → bổ sung ở lần chạy sau
```

---

## 1. B0.1 — VIDEO AUDIT + XÁC MINH MAPPING FRAME INDEX

> **Gate cứng: 06/08 — đã đến hạn.** Nếu chưa ký, đây là việc phải xong **trước tiên, hôm nay**. Mọi task còn lại của Luồng B đều xây trên giả định mapping đúng; nghiệm thu B0.1 muộn nghĩa là nghiệm thu B1.2 có thể phải làm lại từ đầu.

### 1.1. Sản phẩm bàn giao

| File | Nội dung |
|---|---|
| `data/derived/audit/video_manifest.parquet` | `video_id, source_path, container, codec, duration_sec, fps_num, fps_den, nb_frames_container, nb_frames_decoded, width, height, is_vfr, has_audio, audio_sr, audio_channels, file_size, md5` |
| `data/derived/audit/keyframe_map.parquet` | `video_id, btc_ordinal, btc_filename, frame_idx, pts_time, mapping_source, verified` |
| `data/config/frame_convention.md` | **Một câu** khẳng định quy ước: frame_id của BTC là 0-based hay 1-based, và công thức chuyển đổi chính thức |
| `data/derived/_audit/evidence/b01/` | 20 contact sheet neighbor-check |
| `data/derived/audit/audit_report.md` | Tổng hợp + danh sách video bất thường |

### 1.2. L1 — Assertion tự động (bắt buộc 100%)

| # | Assertion | Cách kiểm |
|---|---|---|
| L1-1 | Tập `video_id` trong manifest **bằng đúng** tập video BTC công bố (không thiếu, không thừa) | So sánh set, in ra phần chênh lệch hai chiều |
| L1-2 | `fps_num > 0 AND fps_den > 0` cho 100% dòng; không cột nào lưu fps dạng float | Kiểm dtype + giá trị |
| L1-3 | `nb_frames_decoded > 0` và `duration_sec > 0` cho 100% video | — |
| L1-4 | 100% `frame_idx` trong `keyframe_map` là kiểu int, không NaN, và `0 <= frame_idx < nb_frames_decoded` | Join với manifest rồi assert |
| L1-5 | `(video_id, btc_ordinal)` là unique key; `(video_id, frame_idx)` cũng unique | Đếm duplicate = 0 |
| L1-6 | Số keyframe BTC map được = số file keyframe BTC thực tế trên đĩa, từng video một | So khớp count theo video |
| L1-7 | **Round-trip test:** với 1000 cặp `(video, frame_idx)` ngẫu nhiên, `frame_idx → time → frame_idx` trả về **đúng int ban đầu**, 1000/1000 | Dùng `Fraction(fps_num, fps_den)`, không dùng float |
| L1-8 | Không video nào có `duration_sec * fps` lệch `nb_frames_decoded` quá 2 frame (trừ video đã gắn cờ `is_vfr`) | Sai lệch lớn = decode lỗi hoặc metadata rác |

### 1.3. L2 — Phân phối (báo cáo + ngưỡng)

| # | Chỉ số | Ngưỡng | Ý nghĩa nếu vượt |
|---|---|---|---|
| L2-1 | Số video `is_vfr = True` | Báo cáo tuyệt đối, **không được im lặng bằng 0** | VFR làm công thức `frame = time * fps` sai hoàn toàn. Nếu báo cáo 0 mà không có bằng chứng đã kiểm tra pts, coi như chưa kiểm tra |
| L2-2 | Số video `has_audio = False` | Liệt kê tường minh | Đây là input cho B1.3 — video không tiếng phải được biết trước, không phải "lỗi ASR" |
| L2-3 | Phân bố fps (đếm theo giá trị duy nhất) | — | Nhiều fps khác nhau → càng phải chắc fps lưu dạng phân số |
| L2-4 | Phân bố duration (min/p50/p95/max) | — | Video > 40 phút là nhóm rủi ro cho trôi timestamp ASR |
| L2-5 | Khoảng cách trung bình giữa 2 keyframe BTC liên tiếp (theo frame và theo giây) | — | Cho biết mật độ keyframe BTC, quyết định B1.2 cần bù bao nhiêu frame |

### 1.4. L3 — Neighbor-check (phần quan trọng nhất của toàn bộ Luồng B)

**Đây là hạng mục có rủi ro cao nhất trong cả dự án.** Lỗi off-by-one trong mapping không ném exception, không làm hỏng file, chỉ khiến điểm bằng 0.

**Quy trình:**

1. **Chọn mẫu có chủ đích (20 video), không ngẫu nhiên thuần:**
   - 3 video fps cao nhất
   - 3 video fps thấp nhất
   - 3 video dài nhất
   - 2 video ngắn nhất
   - **toàn bộ video `is_vfr = True`** (nếu > 4 thì lấy 4)
   - 2 video có fps lẻ (29.97, 23.976 — nhóm dễ sai nhất)
   - phần còn lại lấy ngẫu nhiên có seed cố định

2. **Với mỗi video, chọn 3 keyframe BTC** (đầu / giữa / cuối video — vì lỗi trôi tích luỹ chỉ lộ ở cuối).

3. **Sinh contact sheet 7 ô** cho mỗi keyframe: frame giải mã tại `idx-3, idx-2, idx-1, idx, idx+1, idx+2, idx+3` đặt cạnh ảnh keyframe BTC gốc, có nhãn offset rõ ràng.

4. **Chấm bằng máy trước, mắt sau:**
   - Tính `pHash` (64-bit) của ảnh BTC và của 7 frame giải mã.
   - `argmin` khoảng cách Hamming **phải rơi vào offset 0**.
   - Ghi lại `d(offset=0)` và `min d(offset≠0)`.

**Tiêu chí PASS:**

| Điều kiện | Ngưỡng |
|---|---|
| `d(offset=0) <= 2` | **60/60 mẫu** (20 video × 3 keyframe) |
| `argmin` rơi đúng offset 0 | **≥ 57/60**; 3 mẫu được phép hoà (cảnh tĩnh, các frame lân cận giống hệt nhau) — nhưng phải là *hoà*, không được thua |
| `argmin` rơi vào offset ≠ 0 | **0 mẫu.** Chỉ 1 mẫu lệch = **FAIL toàn bộ B0.1**, dừng lại điều tra |
| Mắt người xác nhận | 20/20 video, có chữ ký |

**Nếu FAIL:** không sửa bằng cách cộng trừ 1 rồi chạy tiếp. Phải xác định *tại sao*: 0-based vs 1-based, PTS vs frame count, decode có bỏ frame đầu không. Ghi kết luận vào `frame_convention.md` rồi chạy lại toàn bộ 60 mẫu.

### 1.5. Quyết định gate

```
PASS  = L1 8/8 AND L3 60/60 AND frame_convention.md đã viết
COND  = không tồn tại (không có nghiệm thu có điều kiện cho B0.1)
FAIL  = mọi trường hợp còn lại → chặn toàn bộ Luồng B
```

---

## 8. LỊCH NGHIỆM THU (tính từ 07/08/2026)

| Ngày | Việc | Ghi chú |
|---|---|---|
| **07/08** | Dựng `scripts/audit/common.py` + `b01_mapping_check.py`. Chạy nghiệm thu B0.1 đầy đủ, ký hoặc phát hiện lỗi | Gate B0.1 đã quá hạn 1 ngày — ưu tiên tuyệt đối |
