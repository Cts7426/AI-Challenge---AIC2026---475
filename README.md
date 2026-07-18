# HCMAIC 2026 — Multimedia Retrieval System

He thong truy xuat khoanh khac video cho AI Challenge HCMC 2026.

## Yeu cau

- Docker Desktop (Windows/macOS) hoac Docker Engine + Compose plugin (Linux)
- ~4GB RAM trong cho 2 container

## Khoi dong ha tang (Milvus + Elasticsearch)

```bash
docker compose up -d
```

Lan dau se tai image (~2-3GB), cho vai phut. Milvus khoi dong cham (~60-90s).

## Kiem tra 2 container len duoc

```bash
docker compose ps
```

Ca 2 service phai o trang thai `running (healthy)`. Kiem tra truc tiep:

```bash
# Elasticsearch — tra ve JSON co "status": "green" hoac "yellow"
curl http://localhost:9200/_cluster/health

# Milvus — tra ve "OK"
curl http://localhost:9091/healthz
```

## Cong dich vu

| Service | Cong | Dung cho |
|---------|------|----------|
| Milvus (gRPC) | 19530 | `pymilvus` ket noi tu backend |
| Milvus (HTTP) | 9091 | healthcheck / metrics |
| Elasticsearch | 9200 | REST API full-text search |

## Dung

```bash
docker compose down      # dung, GIU data (named volumes)
docker compose down -v   # dung va XOA sach data
```

## Cau truc thu muc

```
/
├── docker-compose.yml        # Milvus + Elasticsearch (2 container)
├── embedEtcd.yaml            # config etcd nhung cua Milvus standalone
├── backend/
│   ├── indexing/             # nap CLIP features, objects, metadata, ocr, asr
│   ├── retrieval/            # search + fusion + rerank
│   ├── llm/                  # adapter llm() — diem thao lap duy nhat
│   ├── agent/                # KISC + track tu dong (lam SAU)
│   └── api/                  # FastAPI endpoints
├── frontend/                 # UI search-and-submit
├── preprocessing/            # job OCR, ASR (chay Colab/Kaggle)
└── data/
    ├── sample/               # data mau de test
    └── config/               # submit_format.py, clip_model.py
```

## Loi thuong gap

- **Elasticsearch thoat ngay voi loi `vm.max_map_count`** (Linux/WSL2):

  ```bash
  # Linux
  sudo sysctl -w vm.max_map_count=262144
  # Windows + Docker Desktop (WSL2 backend)
  wsl -d docker-desktop sysctl -w vm.max_map_count=262144
  ```

- **Milvus mai chua `healthy`**: binh thuong neu < 90s. Xem log:

  ```bash
  docker compose logs -f milvus
  ```
