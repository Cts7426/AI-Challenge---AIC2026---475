# backend/tasks/trake_fallback.py — C4.4: Fallback TRAKE (định vị N khoảnh khắc)
#
# Phương án sinh tồn khi DP (C4.1, P2, có thể cắt) không kịp làm hoặc không đạt
# R-Score mục tiêu. LÀM SỚM theo BUILD_TASKS — đây là thứ cứu 1/3 số câu khỏi 0
# điểm nếu DP toang, không phải phương án dự phòng chờ tới lúc cần mới viết.
#
# ===== ⚠️ SỬA quan trọng so với đặc tả gốc — đọc trước khi động vào file này =====
# docs/contest.md xác nhận rõ: "frame thứ j phải rơi vào khoảng [sⱼ, eⱼ] của
# khoảnh khắc thứ j. KHÔNG PHẢI khớp bất kỳ thứ tự nào." — nghĩa là chấm điểm
# THEO VỊ TRÍ, không phải theo "list có tăng dần hay không".
#
# Đặc tả gốc (và bản BUILD_TASKS đầu tiên) nói "chạy N lần độc lập rồi SẮP XẾP
# kết quả theo thời gian tăng dần" — đây là BUG: nếu search của event-3 (do
# false positive) trả frame SỚM HƠN frame của event-1, sort sẽ đẩy frame đó vào
# vị trí 1 (đại diện event-1) — TỰ TAY phá vỡ tương ứng vị trí↔sự kiện mà công
# thức chấm dựa vào, thay vì chỉ đơn thuần "không tăng dần thì mất điểm".
#
# Thuật toán ĐÚNG ở đây: giữ NGUYÊN mỗi frame ở đúng vị trí event của nó (event
# thứ j luôn ở vị trí j), CHỈ sửa vi phạm đơn điệu CỤC BỘ bằng cách đẩy frame
# sau lên +1 khi cần — không bao giờ sort toàn chuỗi theo giá trị.
#
# ===== Đường đi =====
#   với mỗi sự kiện (ĐÚNG thứ tự trong câu hỏi): search(event_i,
#     filter_video_id=video_hạng_1, top_k=1) → frame_idx tốt nhất TRONG video đó
#   event không có hit nào trong video → nội suy tuyến tính giữa 2 event lân
#     cận có bằng chứng thật (KHÔNG crash — search filter hẹp có thể trả rỗng
#     cho 1-2 sự kiện dù video đúng)
#   quét trái→phải sửa đơn điệu ngặt tại chỗ, GIỮ VỊ TRÍ — không sort giá trị
#   → 1 Answer hoàn chỉnh (hạng 1 của bài nộp TRAKE)
#
# Dòng 2-100 của câu TRAKE do backend.slot.allocate() (D3.1, cơ chế rải-trong-
# shot có sẵn) lấp từ các shot ứng viên của trake_stage1 — trake_fallback.py
# CHỈ chịu trách nhiệm cho dòng hạng 1, vì đó là dòng duy nhất có bằng chứng
# THẬT theo đúng N sự kiện (dòng 2-100 chỉ là lưới an toàn thống kê).
#
# Chạy thử (cần Docker ES+Milvus sống, ANTHROPIC_API_KEY hoặc LLM_BACKEND=local):
#   python -m backend.tasks.trake_fallback L21_V001 "cầu thủ sút phạt . thủ môn cản phá"

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor

from backend.export import n_frames_of
from backend.retrieval.search import search
from data.config.submit_format import Answer

EVENT_TOP_K = 1  # chỉ cần hạng 1 TRONG video đã filter — không cần pool rộng hơn


def _search_best_in_video(event_vi: str, video_id: str) -> dict | None:
    """search() 1 sự kiện, ép trong 1 video — trả kết quả hạng 1 hoặc None.

    branches={"metadata": False}: nhánh metadata (mức VIDEO) vô nghĩa khi đã
    biết trước đúng 1 video — tắt hẳn để đỡ 1 query ES vô ích (kiến trúc đã
    duyệt ở Phase 2, xem comment filter_video_id trong search.py).
    """
    try:
        hits = search(
            event_vi, top_k=EVENT_TOP_K, filter_video_id=video_id,
            branches={"metadata": False},
        )
    except Exception as e:
        print(f"  [cảnh báo] search lỗi cho sự kiện '{event_vi}' trong video {video_id}: {e}")
        return None
    return hits[0] if hits else None


def _fill_missing(frame_or_none: list[int | None]) -> list[int]:
    """Event không có bằng chứng trong video → nội suy TUYẾN TÍNH giữa 2 event
    lân cận có bằng chứng thật. Thiếu ở đầu/cuối dãy (không có gì để nội suy
    hai phía) → dùng nguyên giá trị lân cận gần nhất.

    KHÔNG bao giờ trả None: mọi vị trí phải có 1 số nguyên để bước sửa đơn điệu
    (_repair_strictly_increasing) chạy được. Chỉ raise khi TOÀN BỘ N sự kiện
    đều không có bằng chứng — lúc đó không còn gì để nội suy từ đâu cả.
    """
    n = len(frame_or_none)
    known = [(i, f) for i, f in enumerate(frame_or_none) if f is not None]
    if not known:
        raise RuntimeError(
            "Không sự kiện nào có bằng chứng trong video này — trake_stage1 có thể đã "
            "chọn nhầm video, hoặc filter_video_id đang lọc quá chặt (kiểm tra index có "
            "đủ dữ liệu cho video này không)."
        )

    out: list[int] = list(frame_or_none)  # type: ignore[assignment]
    for i in range(n):
        if out[i] is not None:
            continue
        before = max((k for k in known if k[0] < i), default=None)
        after = min((k for k in known if k[0] > i), default=None)
        if before is not None and after is not None:
            (i0, f0), (i1, f1) = before, after
            out[i] = round(f0 + (f1 - f0) * (i - i0) / (i1 - i0))
        elif before is not None:
            out[i] = before[1]
        else:
            out[i] = after[1]
        print(f"  [cảnh báo] sự kiện #{i + 1} không có bằng chứng trong video — nội suy frame={out[i]}")
    return out  # type: ignore[return-value]


def _repair_strictly_increasing(frames: list[int], n_frames_video: int) -> list[int]:
    """Sửa vi phạm tăng dần NGẶT TẠI CHỖ, GIỮ VỊ TRÍ — không sort theo giá trị.

    Quét trái→phải, đẩy frame sau lên frame trước +1 khi cần: kỹ thuật Y HỆT
    backend/slot/allocator.py::_trake_row (thà lệch 1 frame còn hơn validator
    (backend/export/exporter.py::_check_shape, luật `trake_not_increasing`)
    loại thẳng cả dòng vì không tăng dần ngặt).
    """
    out = list(frames)
    for i in range(1, len(out)):
        if out[i] <= out[i - 1]:
            out[i] = out[i - 1] + 1

    overflow = out[-1] - (n_frames_video - 1)
    if overflow > 0:
        out = [f - overflow for f in out]
        if out[0] < 0:
            # Video quá ngắn cho ngần ấy sự kiện đã bị đẩy dồn — không còn cách
            # nào giữ đúng bằng chứng mà vẫn tăng dần ngặt. Rải đều là lựa chọn
            # ít tệ nhất: sai vị trí nhưng còn ĐÚNG VIDEO và ĐÚNG HÌNH DẠNG,
            # validator không loại thẳng cả dòng.
            print(f"  [cảnh báo] video chỉ có {n_frames_video} frame, không đủ chỗ cho "
                  f"{len(out)} khoảnh khắc tăng dần ngặt theo đúng bằng chứng — rải đều")
            if len(out) > 1:
                out = [round(i * (n_frames_video - 1) / (len(out) - 1)) for i in range(len(out))]
            else:
                out = [0]
            # round() rải đều có thể vẫn đụng nhau khi khoảng cách < 1 (n_frames_video
            # nhỏ hơn số khoảnh khắc) — chạy lại đúng phép đẩy +1 ở trên cho chuỗi
            # vừa rải, rồi kẹp cứng về biên. Khi n_frames_video < len(out), về mặt
            # TOÁN HỌC không thể có đủ số nguyên PHÂN BIỆT trong [0, n_frames_video) —
            # ca này chấp nhận vài phần tử trùng ở sát biên cuối, còn hơn trả số âm
            # hoặc vượt biên (video kiểu này thực tế không xảy ra: N sự kiện TRAKE
            # luôn ‹‹ độ dài video tính bằng frame).
            for i in range(1, len(out)):
                if out[i] <= out[i - 1]:
                    out[i] = out[i - 1] + 1
            out = [max(0, min(f, n_frames_video - 1)) for f in out]
    return out


def trake_stage2_fallback(video_id: str, events: list[str]) -> Answer:
    """video hạng 1 (từ trake_stage1) + N mô tả sự kiện ĐÚNG THỨ TỰ → 1 Answer.

    Đây LUÔN là dòng hạng 1 của bài nộp TRAKE — dòng duy nhất định vị bằng
    bằng chứng thật cho từng sự kiện, thay vì rải đều thống kê như D3.1.
    """
    n = len(events)
    if n < 2:
        raise ValueError(f"TRAKE cần ít nhất 2 sự kiện, nhận {n}")

    with ThreadPoolExecutor(max_workers=min(n, 8)) as pool:
        per_event = list(pool.map(lambda e: _search_best_in_video(e, video_id), events))

    keyframe_ids = [h["keyframe_id"] if h else None for h in per_event]
    frame_or_none = [h["frame_idx"] if h else None for h in per_event]

    frames = _fill_missing(frame_or_none)
    frames = _repair_strictly_increasing(frames, n_frames_of(video_id))

    return Answer(
        video_id=video_id,
        frame_ids=tuple(frames),
        answer_text=None,
        # 1 keyframe đại diện để debug (không ảnh hưởng chấm điểm) — ưu tiên
        # event đầu tiên THẬT SỰ có hit, không phải event bị nội suy
        keyframe_id=next((k for k in keyframe_ids if k), None),
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="TRAKE fallback — định vị N khoảnh khắc (C4.4)")
    ap.add_argument("video_id", help="video hạng 1 từ trake_stage1 (C3.2)")
    ap.add_argument("events", help="các sự kiện, ĐÚNG thứ tự, cách nhau bởi ' . '")
    args = ap.parse_args()

    events = [e.strip() for e in args.events.split(" . ") if e.strip()]
    if len(events) < 2:
        ap.error(f"cần >= 2 sự kiện tách bởi ' . ', nhận: {events}")

    answer = trake_stage2_fallback(args.video_id, events)
    print(f"video_id: {answer.video_id}")
    print(f"frame_ids ({len(answer.frame_ids)} khoảnh khắc, tăng dần ngặt): {answer.frame_ids}")
    print(f"keyframe_id đại diện (debug): {answer.keyframe_id}")

    from backend.llm.adapter import print_usage
    print()
    print_usage()


if __name__ == "__main__":
    main()
