# Kiểm thử

Mục tiêu kiểm thử là chặn lỗi im lặng: sai `frame_id`, lệch không gian CLIP,
resume trộn model/query, hoặc ZIP hợp lệ bề ngoài nhưng sai luật BTC.

## Môi trường

Từ gốc repo, cài đúng dependency của backend vào môi trường Python đang dùng:

```powershell
python -m pip install -r backend/requirements.txt
```

`pytest.ini` chỉ thu thập `tests/` và `dev_set/tests/`; các script tay ở gốc
repo không thuộc test suite vì có thể cần model/index thật.

## Lệnh kiểm tra

```powershell
# Unit và integration test không cần tự gọi script tay ở root
python -m pytest

# Regression tune (cần dữ liệu và index tương ứng)
python -m dev_set.tools.run_evaluation --split tune

# Cổng chẩn đoán cho máy phát triển
python scripts/preflight_check.py --profile development

# Cổng bắt buộc trước release; đặt LLM_BACKEND/model trước khi chạy
python scripts/preflight_check.py --profile release
```

Đừng coi một test xanh trên interpreter khác là kết quả hợp lệ. Khi dependency
thiếu, sửa môi trường/`backend/requirements.txt` trước rồi chạy lại cùng lệnh.

## Lớp kiểm thử

| Lớp | Vị trí chính | Bảo vệ |
|---|---|---|
| Unit | `tests/` | format CSV/ZIP, frame resolver, LLM adapter, search/API, QA/TRAKE |
| Dev-set unit | `dev_set/tests/` | schema, scorer, thống kê và QA variant |
| Regression | `dev_set/tools/run_evaluation.py` | query-level diff trên tune |
| Promotion | holdout và artefact trong `dev_set/results/` | xác minh thay đổi không hồi quy ngoài tune |
| Preflight | `scripts/preflight_check.py` | dependency, service, parquet/map, index, image coverage, validator và runtime config |

## Quy tắc khi thay đổi

- Hành vi mới hoặc bug fix cần test tập trung tại `tests/` hoặc `dev_set/tests/`.
- Sửa vector phải kiểm L2 norm và, khi có feature BTC, chạy
  `python scripts/verify_clip_space.py` để đối chiếu cosine không gian CLIP.
- Sửa format/export phải chạy test validator và tạo ZIP thử để kiểm thư mục
  gốc `submission/`.
- Sửa retrieval chỉ promotion theo tiêu chí tune/holdout trong `AGENTS.md`,
  đồng thời lưu config snapshot và query-level diff.
- Trước khi kết luận hoàn thành: chạy các lệnh phù hợp, xem `git diff`, và đối
  chiếu acceptance criteria của task.
