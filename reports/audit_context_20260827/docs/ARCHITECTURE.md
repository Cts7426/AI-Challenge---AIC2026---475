# Kiến trúc HCMAIC 2026

Tài liệu này là bản đồ ngắn của code đang chạy. `AGENTS.md` quy định bất biến
phải tuân thủ; `docs/B_DATA_PIPELINE_SPEC.md` mô tả chi tiết dữ liệu và pipeline.
Khi hai tài liệu mâu thuẫn, ưu tiên `AGENTS.md`, rồi kiểm tra code và cấu hình.

## Mục tiêu và phạm vi

Hệ thống tìm khoảnh khắc trong video cho ba bài sơ tuyển:

- **KIS:** tìm các cặp `video_id`, `frame_id` phù hợp mô tả.
- **Q&A:** tìm bằng chứng rồi trả lời ngắn tại đúng frame.
- **TRAKE:** chọn một video và nhiều frame theo đúng thứ tự sự kiện.

Hệ thống tối ưu batch/replay/release; không đưa model nặng hoặc UI thi đấu vào
đường `/search`.

## Luồng chính

```text
Archive BTC / metadata
        │
        ▼
data/raw/btc/ ──offline jobs──► data/derived/ (parquet, frame_map, cache)
        │                                   │
        │                                   ▼
        └──────────────────────────► backend/indexing/ ──► Elasticsearch + Milvus
                                                        │
Query ──► backend/retrieval/search.py ──weighted RRF───┤
                                                        ▼
                         backend/tasks/ (KIS / Q&A / TRAKE)
                                                        │
                                                        ▼
                              backend/export/ ──► CSV + ZIP `submission/`
```

`run.py` điều phối batch: kiểm đầu vào, checkpoint append-only theo từng query,
gọi task phù hợp và ghi submission. FastAPI ở `backend/api/` dùng cùng tầng
retrieval/common, không tự tạo một pipeline khác.

## Ranh giới module

| Vị trí | Trách nhiệm | Không được làm |
|---|---|---|
| `backend/indexing/` | Kết nối ES/Milvus duy nhất; loader idempotent cho metadata, object, CLIP, OCR, ASR | Tạo client ES/Milvus ở module khác |
| `backend/retrieval/` | Hiểu query, gọi năm nhánh tìm kiếm, hợp nhất weighted RRF, giữ rank/contribution để debug | Đặt ngưỡng cosine cứng hoặc phụ thuộc model nặng trong request |
| `backend/tasks/` | Áp retrieval cho Q&A/TRAKE và lưu evidence có thể replay | Chép lại search engine |
| `backend/common/` | Invariant dùng chung: frame asset resolver, answer matching | Suy `frame_idx` từ hậu tố keyframe |
| `backend/export/` | Validate/ghi CSV, ZIP và portfolio Q&A | Tự map hoặc làm tròn frame |
| `backend/llm/adapter.py` | Điểm gọi LLM duy nhất, chọn backend bằng biến môi trường | Import SDK provider ở caller |
| `data/config/` | Model, metric, path, trọng số, policy và format thay đổi được | Hardcode các giá trị đó tại caller |
| `dev_set/` | Tune/holdout, scorer và artefact regression | Dùng holdout để tuning thường xuyên |

## Dữ liệu và định danh

`keyframe_id` là khoá join giữa Milvus, Elasticsearch và `frame_map`. Hai lớp
ảnh không được lẫn:

- `data/raw/btc/`: asset BTC; ordinal ảnh chỉ là thứ tự trong archive.
- `data/derived/`: dữ liệu dẫn xuất/cache với `frame_idx` tuyệt đối và provenance.

Mọi nơi cần đường dẫn ảnh phải gọi
`backend.common.frame_assets.resolve_frame_path()`. Frame nộp lấy từ
`frame_map.parquet`; không bao giờ suy từ tên file ảnh/keyframe.

## Retrieval và task

`backend/retrieval/search.py` chạy độc lập, có lỗi cục bộ thì trả nhánh rỗng:

1. CLIP vector trên Milvus;
2. metadata BM25 theo video;
3. object labels theo keyframe;
4. OCR BM25 theo keyframe;
5. ASR BM25 theo đoạn thời gian.

Kết quả được hợp nhất bằng weighted RRF với tham số trong
`data/config/search_weights.py`, sau đó có thể gom theo shot. Query CLIP và
vector index đều L2-normalize; Milvus dùng COSINE. Query expansion là nhiều
caption ngắn, encode riêng, tránh vượt giới hạn 77 token của CLIP.

Q&A thu evidence OCR/ASR/metadata trước khi gọi `llm()`. TRAKE tách sự kiện,
tìm video ứng viên rồi định vị frame theo thứ tự. Cả hai đều gọi retrieval thay
vì tự truy vấn index.

## Vận hành và thay đổi

- Xem [testing](docs/testing.md) trước khi sửa code; thay đổi hành vi cần test.
- Xem [deployment](docs/deployment.md) trước batch/release.
- Lệnh chi tiết và cổng release nằm trong [runbook đợt 1](docs/RUNBOOK_ROUND1.md).
- Thiết kế mới ghi vào [docs/design](docs/design/README.md); kế hoạch thực thi
  ghi vào [docs/plans](docs/plans/README.md). Không thay thế lịch sử/bằng chứng
  trong `BUILD_TASKS.md` hoặc `reports/`.
