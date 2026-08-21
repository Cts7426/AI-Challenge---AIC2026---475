import json
from pathlib import Path
from backend.indexing.es_client import connect as es_connect
from backend.indexing.milvus_client import connect as milvus_connect
from backend.retrieval.search import search
from backend.slot.allocator import allocate
from dev_set.tools.run_evaluation import _to_shot_hits
from dev_set.tools.schema import GroundTruthKIS, Query
from dev_set.tools.scoring import final_score, recall_at_k, rscore_kis
from backend.indexing.frame_map import load_frame_map

def main():
    print("Connecting to DB...")
    es_connect()
    milvus_connect()
    fmap = load_frame_map()
    
    with open("queries001.txt", "r", encoding="utf-8") as f:
        lines = f.readlines()
        
    rows = []
    for line in lines:
        if not line.strip(): continue
        try:
            data = json.loads(line.strip())
        except Exception as e:
            continue
            
        if "KIS" in data.get("type", "") and data.get("query_id", "").endswith("_NEW"):
            try:
                if data.get("frame_start") is None or data.get("frame_end") is None:
                    continue
                q = Query(
                    query_id=data["query_id"],
                    task_type="KIS",
                    query_vi=data["query_vi"],
                    query_en=data.get("query_en"),
                    split="tune"
                )
                gt = GroundTruthKIS(
                    query_id=data["query_id"],
                    video_id=data["video_id"],
                    frame_start=data["frame_start"],
                    frame_end=data["frame_end"]
                )
                
                res = search(q.query_vi, q.query_en, top_k=100, group_by_shot=True)
                hits = _to_shot_hits(res)
                ans = allocate(hits, "KIS", answer_text=None)
                
                r1 = recall_at_k(ans, gt, "KIS", 1)
                r5 = recall_at_k(ans, gt, "KIS", 5)
                r20 = recall_at_k(ans, gt, "KIS", 20)
                r50 = recall_at_k(ans, gt, "KIS", 50)
                r100 = recall_at_k(ans, gt, "KIS", 100)
                fin = final_score(ans, gt, "KIS")
                
                raw_rank = None
                for i, row in enumerate(res, 1):
                    kf = row.get("keyframe_id")
                    if kf not in fmap:
                        continue
                    if rscore_kis(row["video_id"], fmap[kf], gt) > 0:
                        raw_rank = i
                        break

                rows.append({
                    "id": q.query_id,
                    "fin": fin,
                    "r1": r1, "r5": r5, "r20": r20, "r50": r50, "r100": r100,
                    "raw": raw_rank,
                    "vi": q.query_vi[:60]
                })
                print(f"{q.query_id} -> fin={fin:.3f}")
            except Exception as e:
                print("Err:", e)

    print("\n--- RESULTS ---")
    if not rows:
        print("No NEW KIS queries found.")
        return
        
    for r in rows:
        tick = "✅" if r["r1"] >= 1.0 else ("🟡" if r["r100"] >= 1.0 else "❌")
        print(f" {tick} {r['id']:12s} R@1={r['r1']:.2f} R@5={r['r5']:.2f} R@20={r['r20']:.2f} R@100={r['r100']:.2f} Final={r['fin']:.3f} (raw={r['raw']})")
        
    n = len(rows)
    avg = lambda k: sum(r[k] for r in rows) / n
    print(f"\nAvg Final Score ({n} q): {avg('fin'):.3f}")

if __name__ == "__main__":
    main()
