import json
from pathlib import Path
from backend.indexing.es_client import connect as es_connect
from backend.indexing.milvus_client import connect as milvus_connect
from backend.retrieval.search import search
from backend.slot.allocator import allocate
from dev_set.tools.run_evaluation import _to_shot_hits
from dev_set.tools.schema import GroundTruthQA, GroundTruthTRAKE, Query
from dev_set.tools.scoring import final_score, recall_at_k
from backend.indexing.frame_map import load_frame_map

REPO_ROOT = Path(__file__).resolve().parent

def load_jsonl(path):
    with open(path, 'r', encoding='utf-8') as f:
        return [json.loads(line) for line in f if line.strip()]

def main():
    print("Connecting to DB...")
    es_connect()
    milvus_connect()
    fmap = load_frame_map()
    
    gt_path = REPO_ROOT / "dev_set" / "ground_truth" / "gen10_gt.jsonl"
    gts = load_jsonl(gt_path)
    
    gt_map = {}
    for g in gts:
        if g["task_type"] == "QA":
            gt_map[g["query_id"]] = GroundTruthQA(
                query_id=g["query_id"], video_id=g["video_id"],
                frame_start=g["frame_start"], frame_end=g["frame_end"],
                answer_text=g["answer_text"], answer_variants=g["answer_variants"]
            )
        elif g["task_type"] == "TRAKE":
            gt_map[g["query_id"]] = GroundTruthTRAKE(
                query_id=g["query_id"], video_id=g["video_id"], frames=g["frames"]
            )
            
    for task, path in [("QA", "gen10_qa.jsonl"), ("TRAKE", "gen10_trake.jsonl")]:
        q_path = REPO_ROOT / "dev_set" / "queries" / path
        queries = load_jsonl(q_path)
        
        rows = []
        for q_data in queries:
            q = Query(
                query_id=q_data["query_id"], task_type=q_data["task_type"],
                query_vi=q_data["query_vi"], split="tune",
                n_events=q_data.get("n_events"), event_descs=q_data.get("event_descs")
            )
            gt = gt_map.get(q.query_id)
            if not gt: continue
                
            res = search(q.query_vi, top_k=100, group_by_shot=True, q_obj=q)
            hits = _to_shot_hits(res)
            
            if q.task_type == "QA":
                ans = allocate(hits, "QA", answer_text=gt.answer_text)
            else:
                ans = allocate(hits, "TRAKE", answer_text=None)
                
            fin = final_score(ans, gt, q.task_type)
            r100 = recall_at_k(ans, gt, q.task_type, 100)
            rows.append({"id": q.query_id, "fin": fin, "r100": r100, "vi": q.query_vi})

        print(f"\n=== RESULTS {task} ===")
        for r in rows:
            tick = "✅" if r["fin"] > 0 else "❌"
            print(f" {tick} {r['id']:15s} R@100={r['r100']:.2f} Final={r['fin']:.3f} | Q: {r['vi']}")
            
        n = len(rows)
        avg = sum(r["fin"] for r in rows) / n if n > 0 else 0
        print(f"\nAvg Final Score ({task}) ({n} q): {avg:.3f}")

if __name__ == "__main__":
    main()
