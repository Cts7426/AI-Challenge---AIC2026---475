import sys
sys.path.append('.')
from backend.tasks.trake import parse_events, trake_search

events = parse_events("bỏ muối vào nước . bỏ cải vô nước . khuấy lên")

# SỬA 16/08: _best_per_video() (chỉ giữ 1 khung hình/video/sự kiện) đã bị xoá
# — trake_search() giờ tự làm cả việc gộp ứng viên (TRAKE_CANDIDATES_PER_EVENT
# khung hình/video/sự kiện) LẪN xếp chuỗi tăng dần bằng DP trong 1 lượt, xem
# backend/tasks/trake.py.
candidates = trake_search(events, pool_per_event=1000, top_videos=50)

found_3 = False
for c in candidates:
    if c.n_hit_events == len(events):
        found_3 = True
        print(f"{c.video_id}: {c.n_hit_events} hits, score={c.score:.4f}, "
              f"full_order={c.has_full_order}, frames={c.frame_ids}")

if not found_3:
    print("No video matched all 3 events even with pool 1000")
