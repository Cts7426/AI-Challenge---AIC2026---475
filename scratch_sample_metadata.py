from backend.indexing.es_client import connect
from elasticsearch import Elasticsearch
import random

es = connect()
res = es.search(index="metadata", body={
    "query": {"match_all": {}},
    "size": 500,
    "_source": ["video_id", "title", "description", "keywords"]
})

hits = res["hits"]["hits"]
random.shuffle(hits)
for hit in hits[:10]:
    src = hit["_source"]
    print(f"Video: {src.get('video_id')}")
    print(f"Title: {src.get('title')}")
    print(f"Desc: {src.get('description', '')[:100]}")
    print(f"Keywords: {src.get('keywords', [])[:5]}")
    print("-" * 40)
