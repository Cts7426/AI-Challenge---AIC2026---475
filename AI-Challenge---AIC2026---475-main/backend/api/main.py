# backend/api/main.py — FastAPI tối thiểu (Task 0.2)
#
# Vì sao có /health riêng? Frontend, docker healthcheck, và chính mình khi debug
# đều cần một cách rẻ nhất để hỏi "backend còn sống không?" mà không đụng
# tới Milvus/Elasticsearch. Endpoint này KHÔNG check DB — đó là việc của
# endpoint khác sau này (vd /health/deps).

from fastapi import FastAPI

app = FastAPI(
    title="HCMAIC 2026 Retrieval API",
    description="Search engine truy xuất khoảnh khắc video — AI Challenge HCMC 2026",
)


@app.get("/health")
def health():
    return {"status": "ok"}
