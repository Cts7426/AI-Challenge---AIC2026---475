# HCMAIC 2026 — Multimedia Retrieval System

A video moment retrieval system for AI Challenge HCMC 2026.

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
+-- docker-compose.yml        # Milvus + Elasticsearch (2 containers)
+-- embedEtcd.yaml            # Milvus standalone embedded etcd config
+-- backend/
|   +-- indexing/             # Load CLIP features, objects, metadata, OCR, ASR
|   +-- retrieval/            # Search + fusion + rerank
|   +-- llm/                  # LLM adapter llm() - single swap point
|   +-- agent/                # KISC + auto-tracking (TODO)
|   \-- api/                  # FastAPI endpoints
+-- frontend/                 # Search-and-submit UI
+-- preprocessing/            # OCR, ASR jobs (run on Colab/Kaggle)
\-- data/
    +-- sample/               # Sample data for testing
    \-- config/               # submit_format.py, clip_model.py
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