import csv, json
from pathlib import Path

SUB = Path("submissions/eval_full")
GT_PATH = Path("dev_set/ground_truth/tune_gt.jsonl")

gt = {}
if GT_PATH.exists():
    for line in GT_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        gt[rec["query_id"]] = rec

found_count = 0
total_kis = 0

print("=== RECALL EVALUATION (23 KIS QUERIES) ===")
for qid, truth in sorted(gt.items()):
    if truth.get("task_type") != "KIS":
        continue
    total_kis += 1
    f = SUB / f"{qid}.csv"
    if not f.exists():
        print(f"{qid:<6} KHÔNG CÓ FILE")
        continue
    rows = list(csv.reader(f.open(encoding="utf-8")))
    
    # Ground truth format: frame_start, frame_end or frame_range
    if "frame_range" in truth:
        lo, hi = truth["frame_range"]
    else:
        lo, hi = truth["frame_start"], truth["frame_end"]
        
    target_vid = truth["video_id"]
    
    rank = next(
        (i for i, r in enumerate(rows, 1)
         if r[0] == target_vid and lo <= int(r[1]) <= hi),
        None,
    )
    
    if rank:
        found_count += 1
        print(f"{qid:<6} -> Trúng hạng {rank:<3} (video: {target_vid}, frames [{lo}-{hi}])")
    else:
        # Check if video was found at all
        video_ranks = [i for i, r in enumerate(rows, 1) if r[0] == target_vid]
        if video_ranks:
            print(f"{qid:<6} -> MISS frame (video {target_vid} trúng hạng {video_ranks[0]}, nhưng frame sai)")
        else:
            print(f"{qid:<6} -> MISS video")

print(f"\nTỔNG KẾT RECALL: Trúng {found_count}/{total_kis} câu trong Top 100 ({found_count/total_kis*100:.1f}%)")
