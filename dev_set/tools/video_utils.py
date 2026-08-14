# dev_set/tools/video_utils.py — tiện ích trích frame chính xác cho Dev Set.
#
# Chuyển từ backup_running/decode.py vào đây vì: (1) backup_running/ chưa được
# commit (untracked theo git status) — clone mới sẽ thiếu file này; (2) Dev Set
# là client độc lập, không nên phụ thuộc một script tên "backup" nằm ngoài
# dev_set/ cho một tiện ích mà chỉ check_gt.py dùng.

from __future__ import annotations

import cv2
import numpy as np


def extract_frame_exact(video_path: str, target_idx: int) -> np.ndarray | None:
    """
    Trích xuất chính xác frame tại target_idx.

    LÝ DO KHÔNG DÙNG SEEK THEO THỜI GIAN:
    Các video có FPS phân số (như 30000/1001 = 29.970029...) sẽ bị làm tròn sai số khi
    tính timestamp (t = frame_idx / fps). Khi PyAV hoặc FFmpeg seek theo thời gian này,
    nó sẽ nhảy sai vị trí (ví dụ nhảy thành +1 hoặc -1) đối với các frame_idx lớn.

    GIẢI PHÁP - SEEK GẦN + ĐỌC TUẦN TỰ:
    OpenCV set CAP_PROP_POS_FRAMES nhảy theo cấu trúc I-frame/P-frame, nó có thể nhảy
    gần đúng. Ta sẽ seek lùi lại 60 frame (để đảm bảo qua một keyframe của h.264),
    rồi đọc tuần tự (seq) bằng hàm read() cho đến đúng target_idx.
    Phương pháp này đã được đối chiếu với việc đọc tuần tự từ frame 0 và cho MSE = 0.00.
    """
    cap = cv2.VideoCapture(str(video_path))
    seek_idx = max(0, target_idx - 60)

    cap.set(cv2.CAP_PROP_POS_FRAMES, seek_idx)
    curr = int(cap.get(cv2.CAP_PROP_POS_FRAMES))

    # Đề phòng seek lố qua target
    if curr > target_idx:
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        curr = 0

    ret, frame = False, None
    for _ in range(curr, target_idx + 1):
        ret, frame = cap.read()

    cap.release()
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB) if ret else None
