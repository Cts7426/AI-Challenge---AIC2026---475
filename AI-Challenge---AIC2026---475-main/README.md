# HCMAIC 2026 — Multimedia Retrieval System

Hệ thống truy xuất khoảnh khắc video cho AI Challenge HCMC 2026.
Kiến trúc & quy ước: xem [CLAUDE.md](CLAUDE.md).

## Yêu cầu

- Docker Desktop (Windows/macOS) hoặc Docker Engine + Compose plugin (Linux)
- ~4GB RAM trống cho 2 container

## Khởi động hạ tầng (Milvus + Elasticsearch)

```bash
docker compose up -d
```

Lần đầu sẽ tải image (~2–3GB), chờ vài phút. Milvus khởi động chậm (~60–90s).

## Kiểm tra 2 container lên được

```bash
docker compose ps
```

Cả 2 service phải ở trạng thái `running (healthy)`. Kiểm tra trực tiếp:

```bash
# Elasticsearch — trả về JSON có "status": "green" hoặc "yellow"
curl http://localhost:9200/_cluster/health

# Milvus — trả về "OK"
curl http://localhost:9091/healthz
```

## Cổng dịch vụ

| Service | Cổng | Dùng cho |
|---------|------|----------|
| Milvus (gRPC) | 19530 | `pymilvus` kết nối từ backend |
| Milvus (HTTP) | 9091 | healthcheck / metrics |
| Elasticsearch | 9200 | REST API full-text search |

## Dừng

```bash
docker compose down      # dừng, GIỮ data (named volumes)
docker compose down -v   # dừng và XOÁ sạch data
```

## Cấu trúc thư mục

```
/
├── CLAUDE.md                 # ngữ cảnh dự án cho Claude Code
├── BUILD_TASKS.md            # lộ trình task
├── docker-compose.yml        # Milvus + Elasticsearch (2 container)
├── embedEtcd.yaml            # config etcd nhúng của Milvus standalone
├── backend/
│   ├── indexing/             # nạp CLIP features, objects, metadata, ocr, asr
│   ├── retrieval/            # search + fusion + rerank
│   ├── llm/                  # adapter llm() — điểm tháo lắp duy nhất
│   ├── agent/                # KISC + track tự động (làm SAU)
│   └── api/                  # FastAPI endpoints
├── frontend/                 # UI search-and-submit
├── preprocessing/            # job OCR, ASR (chạy Colab/Kaggle)
└── data/
    ├── sample/               # data mẫu để test
    └── config/               # submit_format.py, clip_model.py (thứ CHƯA chốt)
```

## Lỗi thường gặp

- **Elasticsearch thoát ngay với lỗi `vm.max_map_count`** (Linux/WSL2):

  ```bash
  # Linux
  sudo sysctl -w vm.max_map_count=262144
  # Windows + Docker Desktop (WSL2 backend)
  wsl -d docker-desktop sysctl -w vm.max_map_count=262144
  ```

- **Milvus mãi chưa `healthy`**: bình thường nếu < 90s. Xem log:

  ```bash
  docker compose logs -f milvus
  ```
