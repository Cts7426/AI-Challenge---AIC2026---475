import subprocess
import json
import os

def get_video_header(video_path: str):
    """
    Sử dụng ffprobe để lấy header thông tin của video (không decode frames).
    Trả về: fps_num, fps_den, duration, width, height, has_audio
    """
    cmd = [
        'ffprobe',
        '-v', 'error',
        '-select_streams', 'v:0',
        '-show_entries', 'stream=r_frame_rate,duration,width,height',
        '-of', 'json',
        video_path
    ]
    
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe error: {result.stderr}")
        
    try:
        info = json.loads(result.stdout)
        stream = info['streams'][0]
        
        # Parse fps from r_frame_rate e.g. "30000/1001"
        r_frame_rate = stream.get('r_frame_rate', '0/1')
        if '/' in r_frame_rate:
            fps_num, fps_den = map(int, r_frame_rate.split('/'))
        else:
            fps_num = int(r_frame_rate)
            fps_den = 1
            
        duration = float(stream.get('duration', 0.0))
        width = int(stream.get('width', 0))
        height = int(stream.get('height', 0))
        
    except (KeyError, IndexError, ValueError) as e:
        raise RuntimeError(f"Could not parse ffprobe output for {video_path}: {e}")

    # Check for audio stream
    cmd_audio = [
        'ffprobe',
        '-v', 'error',
        '-select_streams', 'a:0',
        '-show_entries', 'stream=codec_type',
        '-of', 'json',
        video_path
    ]
    res_audio = subprocess.run(cmd_audio, stdout=subprocess.PIPE, text=True)
    has_audio = False
    if res_audio.returncode == 0:
        try:
            ainfo = json.loads(res_audio.stdout)
            has_audio = len(ainfo.get('streams', [])) > 0
        except Exception:
            pass
            
    return {
        "fps_num": fps_num,
        "fps_den": fps_den,
        "duration": duration,
        "width": width,
        "height": height,
        "has_audio": has_audio
    }

def extract_audio(in_path: str, out_path: str):
    """
    Tách audio từ video và lưu dưới dạng mono 16kHz WAV.
    """
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    cmd = [
        'ffmpeg',
        '-y',               # overwrite
        '-i', in_path,
        '-vn',              # no video
        '-acodec', 'pcm_s16le',
        '-ac', '1',         # mono
        '-ar', '16000',     # 16kHz
        out_path
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg audio extraction error for {in_path}: {result.stderr.decode('utf-8')}")
