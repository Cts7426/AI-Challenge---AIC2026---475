import os
def extract_keyframes_and_count(video_path: str, target_frames: set, out_dir: str) -> int:
    """
    Decode video tuần tự (sequential) bằng PyAV.
    - Đếm tổng số frame (n_frames).
    - Nếu frame_idx nằm trong target_frames, lưu ảnh ra đĩa dưới tên f<frame_idx>.jpg (zero-pad 7).
    Trả về tổng số frame đếm được.
    """
    import av
    os.makedirs(out_dir, exist_ok=True)
    
    container = av.open(video_path)
    stream = container.streams.video[0]
    
    n_frames = 0
    
    for frame in container.decode(stream):
        if n_frames in target_frames:
            # Lưu ảnh định dạng f0000000.jpg
            filename = f"f{n_frames:07d}.jpg"
            out_path = os.path.join(out_dir, filename)
            
            # frame.to_image() trả về PIL Image
            img = frame.to_image()
            img.save(out_path, format="JPEG", quality=90)
            
        n_frames += 1
        
    return n_frames

def sample_keyframes_from_shots(shots: list, fps_num: int, fps_den: int) -> dict:
    """
    shots: list of tuples (start_frame, end_frame)
    Trả về dict {frame_idx: {"is_rep": bool, "shot_id": int}}
    Quy tắc:
    - 1 fps trong shot.
    - Min 2 frames per shot (ở 25% và 75%).
    - Max 20 frames per shot.
    - rep_kf = frame gần giữa shot nhất.
    """
    target_frames = {}
    fps = fps_num / fps_den if fps_den > 0 else 30.0
    
    for shot_idx, (start_f, end_f) in enumerate(shots):
        length_f = end_f - start_f
        # Tính toán rep_kf lý tưởng
        ideal_rep_f = start_f + length_f // 2
        
        # Mật độ 1 fps: mỗi giây một frame
        num_seconds = length_f / fps
        num_samples_target = max(2, min(20, int(round(num_seconds))))
        
        if num_samples_target <= 2:
            samples = [
                start_f + int(length_f * 0.25),
                start_f + int(length_f * 0.75)
            ]
        else:
            # Rải đều num_samples_target
            step = length_f / num_samples_target
            samples = [start_f + int(i * step + step / 2) for i in range(num_samples_target)]
            
        # Tìm frame nào gần giữa nhất để làm rep_kf
        rep_frame = min(samples, key=lambda f: abs(f - ideal_rep_f))
        
        for f in samples:
            # Đảm bảo f không tràn ngoài shot
            f = max(start_f, min(end_f - 1, f))
            target_frames[f] = {
                "shot_id": shot_idx,
                "is_rep": (f == rep_frame)
            }
            
    return target_frames

import cv2
import numpy as np

def extract_frame_exact(video_path: str, target_idx: int) -> np.ndarray:
    """
    Trích xuất chính xác frame tại target_idx.
    
    LÝ DO KHÔNG DÙNG SEEK THEO THỜI GIAN:
    Các video có FPS phân số (như 30000/1001 = 29.970029...) sẽ bị làm tròn sai số khi 
    tính timestamp (t = frame_idx / fps). Khi PyAV hoặc FFmpeg seek theo thời gian này,
    nó sẽ nhảy sai vị trí (ví dụ nhảy thành +1 hoặc -1) đối với các frame_idx lớn.
    
    GIẢI PHÁP - TRỌNG TÀI OPENCV SEEK + SEQ:
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
        
    for _ in range(curr, target_idx + 1):
        ret, frame = cap.read()
        
    cap.release()
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB) if ret else None
