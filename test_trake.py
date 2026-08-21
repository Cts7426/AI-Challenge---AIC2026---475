import sys
sys.path.append('.')
from backend.tasks.trake import parse_events, trake_search

events = parse_events("bỏ muối vào nước . bỏ cải vô nước . khuấy lên")
print("Events:", events)

# SỬA 16/08: _best_per_video() đã bị xoá — trake_search() gộp ứng viên +
# xếp chuỗi DP trong 1 lượt (backend/tasks/trake.py).
candidates = trake_search(events, pool_per_event=200, top_videos=50)

for c in candidates:
    if c.n_hit_events >= 2:
        print(f"{c.video_id}: {c.n_hit_events} hits, score={c.score:.4f}, "
              f"full_order={c.has_full_order}, frames={c.frame_ids}")

print("Done")
