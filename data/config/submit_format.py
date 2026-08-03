# TODO: BTC — format submit chưa chốt (xem CLAUDE.md bảng cuối).
# Chưa rõ nộp theo frame_id hay timestamp ms — chờ buổi tập huấn.
#
# TOÀN BỘ cấu trúc file nộp nằm ở đây: BTC công bố format thật thì sửa
# build_submission() + SUBMIT_FORMAT, backend/frontend không phải đổi dòng nào.
#
# ⚠️ W0.2 — BÀI HỌC về bug frame_id (đã sửa, giữ lại để không tái phạm):
# Bản cũ lấy frame_id bằng cách cắt hậu tố keyframe_id ("L03_V001_0007" → "0007").
# Đó là SỐ THỨ TỰ FILE KEYFRAME, không phải FRAME INDEX TRONG VIDEO mà BTC chấm
# (keyframe 0007 có thể là frame 175 của video). Lỗi thuộc loại IM LẶNG nguy hiểm
# nhất: file nộp nhìn hợp lệ, không crash, nhưng LỆCH HỆ THỐNG mọi câu → 0 điểm
# toàn giải dù tìm đúng video đúng khoảnh khắc. Vì vậy: frame_id CHỈ được tra từ
# frame_map; thiếu map thì RAISE, tuyệt đối không đoán.

from datetime import datetime, timezone

SUBMIT_FORMAT = "frame_id"  # TODO: BTC — hoặc "timestamp_ms"


def _answer_value(item: dict, frame_map: dict[str, int] | None) -> str | int:
    """1 keyframe → giá trị nộp theo SUBMIT_FORMAT.

    frame_map: dict keyframe_id → frame index TRONG VIDEO (nguồn:
    backend/indexing/frame_map.py — file map-keyframes của BTC khi có).
    """
    if SUBMIT_FORMAT == "frame_id":
        kf = item["keyframe_id"]
        if kf not in frame_map:
            # Thiếu 1 keyframe cũng phải gãy to: nộp số bịa cho riêng câu này
            # là mất điểm câu này mà không ai biết
            raise KeyError(
                f"keyframe '{kf}' không có trong frame_map — "
                "kiểm tra loader frame_map đã phủ đủ video này chưa."
            )
        return frame_map[kf]
    return item["timestamp_ms"]


def build_submission(
    task_type: str, items: list[dict], frame_map: dict[str, int] | None = None
) -> dict:
    """Dựng nội dung file nộp. items: [{keyframe_id, video_id, timestamp_ms}].

    Cấu trúc GIẢ ĐỊNH trong lúc chờ BTC — giữ cả keyframe_id gốc để truy vết.
    """
    if SUBMIT_FORMAT == "frame_id" and frame_map is None:
        raise RuntimeError(
            "SUBMIT_FORMAT='frame_id' nhưng chưa có frame_map "
            "(keyframe_id → frame index trong video). "
            "KHÔNG được sinh file nộp với số tự đoán — nhầm chỗ này là 0 điểm "
            "dù đúng video (CLAUDE.md bất biến 5). "
            "Nạp map qua backend/indexing/frame_map.load_frame_map() trước."
        )
    return {
        "task_type": task_type,          # "KIS" | "AVS"
        "format": SUBMIT_FORMAT,         # TODO: BTC
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "answers": [
            {
                "video_id": it["video_id"],
                "value": _answer_value(it, frame_map),
                "keyframe_id": it["keyframe_id"],  # để truy vết, có thể bỏ khi BTC chốt
            }
            for it in items
        ],
    }
