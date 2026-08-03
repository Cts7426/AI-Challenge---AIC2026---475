import hashlib

def get_zip_shard(zip_name: str, num_shards: int) -> int:
    """
    Tính toán shard_id cho file ZIP dựa vào MD5.
    (Ingest chia theo ZIP để tối ưu băng thông tải).
    """
    return int(hashlib.md5(zip_name.encode('utf-8')).hexdigest(), 16) % num_shards

def get_video_shard(video_id: str, num_shards: int) -> int:
    """
    Tính toán shard_id cho file video (dùng cho các job như ASR, OCR).
    Sử dụng hàm băm xác định để chia việc cho 5 người.
    """
    return int(hashlib.md5(video_id.encode('utf-8')).hexdigest(), 16) % num_shards
