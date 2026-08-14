# backend/tasks/trake.py — C3.2: TRAKE giai đoạn 1 (lọc video ứng viên)
#
# ===== Vì sao KHÔNG nối N mô tả sự kiện thành 1 câu rồi search() 1 lần =====
# BUILD_TASKS gốc viết "ghép truy vấn tổng hợp" — nhưng CLIP chặn CỨNG 77 token
# (CLAUDE.md bất biến 6 / skill bất biến 5: "nhiều câu ngắn encode riêng rồi hợp
# nhất, không nối thành đoạn dài"). Nối N≥3 mô tả sự kiện thường vượt 77 token,
# CLIP tự CẮT CỤT phần đuôi LẶNG LẼ — sự kiện cuối chuỗi biến mất khỏi vector mà
# không có cảnh báo nào (đúng loại lỗi "chạy được nhưng sai" CLAUDE.md nói tới).
# Quyết định đổi hướng này đã duyệt ở Phase 2 (Upgraded Implementation Plan).
#
# ===== Thiết kế thay thế: N search() song song, gộp điểm ở cấp VIDEO =====
#   với mỗi sự kiện: search(event_i) [KIS pipeline KHÔNG SỬA] → shot tốt nhất
#     của MỖI video ứng viên cho sự kiện đó
#   video_score = Σᵢ best_shot_score(event_i, video)  — video có bằng chứng cho
#     CẢ N sự kiện tự nhiên cao điểm hơn video chỉ khớp 1 sự kiện dù khớp rất
#     mạnh — đạt đúng Ý ĐỒ log-sum gốc (thưởng ĐỘ PHỦ) mà không vi phạm giới
#     hạn token và không cần sửa search.py (không cần filter_video_id ở đây).
#   thưởng thứ tự thời gian: video có CẢ N sự kiện khớp, và frame đại diện của
#     event 1 < event 2 < ... < event N (đúng trình tự đề bài) → nhân
#     TRAKE_ORDER_BONUS (data/config/search_weights.py — CHỈ xếp lại hạng trong
#     nhóm ứng viên đã hợp lý, KHÔNG dùng làm bộ lọc cứng — sai video ở TRAKE là
#     0 điểm tuyệt đối, loại nhầm 1 video đúng vì phạt quá tay còn tệ hơn xếp
#     nó hạng thấp).
#
# Chạy thử (cần Docker ES+Milvus sống, ANTHROPIC_API_KEY hoặc LLM_BACKEND=local):
#   python -m backend.tasks.trake "cầu thủ sút phạt . thủ môn bay người cản phá . trọng tài thổi còi"

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor

from backend.llm.adapter import llm
from backend.retrieval.search import search
from data.config.search_weights import TRAKE_EVENT_SEARCH_POOL, TRAKE_ORDER_BONUS

TOP_VIDEOS = 10  # BUILD_TASKS C3.2: "trả top-10 video xếp hạng"

PARSE_EVENTS_SCHEMA = {
    "type": "object",
    "properties": {"events_vi": {"type": "array", "items": {"type": "string"}}},
    "required": ["events_vi"],
    "additionalProperties": False,
}


def parse_events(query_vi: str) -> list[str]:
    """Câu hỏi TRAKE → list N mô tả sự kiện, ĐÚNG thứ tự thời gian đề bài nói.

    N = len(kết quả) — KHÔNG đọc TRAKE_DEFAULT_N từ config. dev_set/tools/scoring
    (rscore_trake) cho 0 điểm TUYỆT ĐỐI nếu số khoảnh khắc nộp khác N thật của
    đề — đoán N sai là mất trắng dù mọi frame đều đúng.
    """
    raw = llm(
        "Câu sau mô tả MỘT CHUỖI các sự kiện liên tiếp xảy ra trong một video "
        "(bài toán TRAKE — định vị từng khoảnh khắc theo đúng thứ tự). Tách thành "
        "danh sách các mô tả sự kiện RIÊNG BIỆT, mỗi mô tả là MỘT khoảnh khắc "
        "ngắn, GIỮ NGUYÊN đúng thứ tự thời gian như câu gốc.\n"
        "HARD RULE: không thêm sự kiện không có trong câu gốc, không gộp 2 sự "
        "kiện làm 1, không đổi thứ tự. Mỗi mô tả đủ ngắn để dùng làm caption "
        "tìm kiếm ảnh (không quá 1 câu).\n\n"
        f"Câu hỏi: {query_vi}",
        json_schema=PARSE_EVENTS_SCHEMA,
    )
    events = [e.strip() for e in json.loads(raw)["events_vi"] if e and e.strip()]
    if len(events) < 2:
        raise ValueError(
            f"TRAKE cần ít nhất 2 sự kiện, parse_events() chỉ tách được {len(events)} "
            f"từ câu: '{query_vi}'. Kiểm tra câu hỏi có đúng là dạng bài TRAKE không."
        )
    return events


def _best_per_video(hits: list[dict]) -> dict[str, dict]:
    """1 danh sách kết quả search() (nhiều shot, có thể trùng video) → mỗi
    video giữ lại shot điểm CAO NHẤT của nó cho sự kiện này."""
    best: dict[str, dict] = {}
    for h in hits:
        vid = h["video_id"]
        cur = best.get(vid)
        if cur is None or h["score"] > cur["score"]:
            best[vid] = {"score": h["score"], "frame_idx": h.get("frame_idx")}
    return best


def _is_strictly_increasing(seq: list[int]) -> bool:
    return all(a < b for a, b in zip(seq, seq[1:]))


def trake_stage1(
    events: list[str],
    *,
    pool_per_event: int = TRAKE_EVENT_SEARCH_POOL,
    top_videos: int = TOP_VIDEOS,
) -> list[tuple[str, float]]:
    """N mô tả sự kiện → top-10 (video_id, score) xếp hạng giảm dần.

    Sai video ở TRAKE là 0 điểm tuyệt đối (docs/contest.md) nên giai đoạn này
    quan trọng hơn việc định vị N khoảnh khắc chính xác (đó là việc của
    backend/tasks/trake_fallback.py, chạy SAU KHI đã có video ở đây).
    """
    n = len(events)
    if n < 2:
        raise ValueError(f"TRAKE cần ít nhất 2 sự kiện, nhận {n}")

    def _search_one(event_vi: str) -> list[dict]:
        # Một sự kiện lỗi (ES/Milvus tạm chết) không được kéo sập cả stage —
        # đúng tinh thần try/except từng nhánh của search.py (skill retrieval).
        try:
            return search(event_vi, top_k=pool_per_event, group_by_shot=True)
        except Exception as e:
            print(f"  [cảnh báo] search lỗi cho sự kiện '{event_vi}': {e}")
            return []

    with ThreadPoolExecutor(max_workers=min(n, 8)) as pool:
        per_event_hits = list(pool.map(_search_one, events))

    best_per_event_video = [_best_per_video(hits) for hits in per_event_hits]

    all_videos: set[str] = set()
    for best in best_per_event_video:
        all_videos.update(best)
    if not all_videos:
        return []

    scored: list[tuple[str, float]] = []
    for vid in all_videos:
        total = 0.0
        frame_seq: list[int] = []
        n_hit_events = 0
        for best in best_per_event_video:
            entry = best.get(vid)
            if entry is None:
                continue
            total += entry["score"]
            n_hit_events += 1
            if entry["frame_idx"] is not None:
                frame_seq.append(entry["frame_idx"])

        # Thưởng thứ tự: CHỈ khi video có bằng chứng cho CẢ N sự kiện (không
        # thưởng video mới khớp 1 phần — đó là tín hiệu quá yếu để suy ra thứ tự)
        if n_hit_events == n and len(frame_seq) == n and _is_strictly_increasing(frame_seq):
            total *= TRAKE_ORDER_BONUS

        scored.append((vid, total))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_videos]


def main() -> None:
    ap = argparse.ArgumentParser(description="TRAKE giai đoạn 1 — lọc video ứng viên (C3.2)")
    ap.add_argument("query", help="câu hỏi TRAKE tiếng Việt, các sự kiện cách nhau bởi ' . '")
    ap.add_argument("--parse", action="store_true",
                     help="tự tách sự kiện bằng llm() thay vì split thủ công theo ' . '")
    args = ap.parse_args()

    events = parse_events(args.query) if args.parse else [e.strip() for e in args.query.split(" . ")]
    if len(events) < 2:
        ap.error(f"cần >= 2 sự kiện (tách theo ' . ' hoặc dùng --parse), nhận: {events}")

    print(f"{len(events)} sự kiện:")
    for i, e in enumerate(events, 1):
        print(f"  {i}. {e}")

    ranked = trake_stage1(events)
    print(f"\nTop {len(ranked)} video ứng viên:")
    for i, (vid, score) in enumerate(ranked, 1):
        print(f"  hạng {i:>2}: {vid}  score={score:.5f}")

    from backend.llm.adapter import print_usage
    print()
    print_usage()


if __name__ == "__main__":
    main()
