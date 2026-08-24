# HCMAIC 2026 — Multimedia Retrieval System

Hệ thống truy xuất khoảnh khắc video cho AI Challenge HCMC 2026. Hệ thống
phục vụ vòng sơ tuyển theo lô với ba dạng bài KIS, Q&A và TRAKE.

## Tài liệu bắt đầu từ đây

- [Kiến trúc hệ thống](ARCHITECTURE.md): ranh giới module, luồng dữ liệu và
  các nguồn sự thật.
- [Đặc tả sản phẩm](docs/product-spec.md): phạm vi, người dùng và tiêu chí
  thành công của vòng sơ tuyển.
- [Kiểm thử](docs/testing.md): lệnh kiểm tra và ý nghĩa từng lớp test.
- [Triển khai/vận hành](docs/deployment.md): hạ tầng local, preflight và batch
  release.
- [Thể thức cuộc thi](docs/contest.md): luật BTC và cách chấm hiện hành.
- [Runbook đợt 1](docs/RUNBOOK_ROUND1.md): thao tác theo thời điểm thi.
- [Lộ trình công việc](BUILD_TASKS.md): các task P0/P1 và bằng chứng hoàn thành.

`AGENTS.md` là hướng dẫn bắt buộc cho agent. Đọc `ARCHITECTURE.md` trước khi
thay đổi ranh giới module, luồng dữ liệu hoặc hợp đồng giữa các tầng.

## Requirements

- Docker Desktop (Windows/macOS) or Docker Engine + Compose plugin (Linux)
- ~4GB free RAM for 2 containers

## Start Infrastructure (Milvus + Elasticsearch)

```bash
docker compose up -d
```

The first run will pull images (~2-3GB), wait a few minutes. Milvus takes a while to start (~60-90s).

## Verify Both Containers Are Running

```bash
docker compose ps
```

Both services should be in `running (healthy)` state. Direct health checks:

```bash
# Elasticsearch - should return JSON with "status": "green" or "yellow"
curl http://localhost:9200/_cluster/health

# Milvus - should return "OK"
curl http://localhost:9091/healthz
```

## Service Ports

| Service | Port | Used For |
|---------|------|----------|
| Milvus (gRPC) | 19530 | `pymilvus` backend connection |
| Milvus (HTTP) | 9091 | healthcheck / metrics |
| Elasticsearch | 9200 | REST API full-text search |

## Stop

```bash
docker compose down      # stop, KEEP data (named volumes)
docker compose down -v   # stop and DELETE all data
```

## Project Structure

```
/
+-- AGENTS.md                 # Quy ước bắt buộc và bất biến vận hành
+-- ARCHITECTURE.md           # Bản đồ kiến trúc ngắn, cập nhật theo code
+-- backend/                  # Indexing, retrieval, task, export, API và LLM
+-- data/
|   +-- config/               # Model, metric, trọng số, format và policy
|   +-- raw/btc/              # Asset gốc BTC (không chỉnh sửa bởi loader)
|   \-- derived/              # Parquet, map và cache có provenance
+-- dev_set/                  # Tune/holdout, scorer và artefact regression
+-- docs/                     # Spec, vận hành, kiểm thử, thiết kế và kế hoạch
+-- preprocessing/            # Job offline/Colab/Kaggle có checkpoint
+-- tests/                    # Unit/integration tests của ứng dụng
\-- run.py                   # Batch orchestrator để tạo submission
```

## Troubleshooting

- **Elasticsearch exits immediately with `vm.max_map_count` error** (Linux/WSL2):

  ```bash
  # Linux
  sudo sysctl -w vm.max_map_count=262144
  # Windows + Docker Desktop (WSL2 backend)
  wsl -d docker-desktop sysctl -w vm.max_map_count=262144
  ```

- **Milvus stays unhealthy**: Normal if under 90s. Check logs:

  ```bash
  docker compose logs -f milvus
  ```
