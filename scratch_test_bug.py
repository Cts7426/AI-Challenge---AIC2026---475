from backend.tasks.trake import _localize_in_video, _c, _align_events_in_video

cands_valid = [
    [_c(0.6, 100)], 
    [_c(0.01, 200), _c(0.9, 50)],
    [_c(0.6, 300)]
]
chain, score = _align_events_in_video(cands_valid)
print("CHAIN:", chain)
