# TODO: BTC — format submit chưa chốt (xem CLAUDE.md mục 7).
# Chưa rõ nộp theo frame_id (vd "0007") hay timestamp ms — chờ buổi tập huấn.
#
# TOÀN BỘ cấu trúc file nộp nằm ở đây: BTC công bố format thật thì sửa
# build_submission() + SUBMIT_FORMAT, backend/frontend không phải đổi dòng nào.

from datetime import datetime, timezone

SUBMIT_FORMAT = "frame_id"  # TODO: BTC — hoặc "timestamp_ms"


def _answer_value(item: dict) -> str | int:
    """1 keyframe → giá trị nộp theo SUBMIT_FORMAT.

    Giả định frame_id = hậu tố sau dấu '_' cuối của keyframe_id
    ("L03_V001_0007" → "0007") — TODO: BTC xác nhận quy ước đặt tên keyframe.
    """
    if SUBMIT_FORMAT == "frame_id":
        return item["keyframe_id"].rsplit("_", 1)[-1]
    return item["timestamp_ms"]


def build_submission(task_type: str, items: list[dict]) -> dict:
    """Dựng nội dung file nộp. items: [{keyframe_id, video_id, timestamp_ms}].

    Cấu trúc GIẢ ĐỊNH trong lúc chờ BTC — đủ thông tin để map sang mọi
    format hợp lý (giữ cả keyframe_id gốc để đối chiếu lại được).
    """
    return {
        "task_type": task_type,          # "KIS" | "AVS"
        "format": SUBMIT_FORMAT,         # TODO: BTC
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "answers": [
            {
                "video_id": it["video_id"],
                "value": _answer_value(it),
                "keyframe_id": it["keyframe_id"],  # để truy vết, có thể bỏ khi BTC chốt
            }
            for it in items
        ],
    }
