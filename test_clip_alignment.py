import os
import torch
import numpy as np
import open_clip
from PIL import Image
from pymilvus import MilvusClient
from pathlib import Path

# Cấu hình hiện tại của hệ thống
CLIP_MODEL_NAME = "ViT-B-32-quickgelu"
CLIP_PRETRAINED = "openai"

print(f"Loading {CLIP_MODEL_NAME}...")
model, _, preprocess = open_clip.create_model_and_transforms(
    model_name=CLIP_MODEL_NAME, pretrained=CLIP_PRETRAINED
)
model.eval()

# Tìm một ảnh bất kỳ trong thư mục
# Ví dụ: L27_V005/245.jpg
img_path = Path("data/raw/btc/keyframes/keyframes_L27/L27_V005/245.jpg")
if not img_path.exists():
    print(f"Không tìm thấy ảnh: {img_path}")
    exit(1)

# Encode ảnh bằng model hiện tại
image = preprocess(Image.open(img_path)).unsqueeze(0)
with torch.no_grad():
    image_features = model.encode_image(image)
    image_features /= image_features.norm(dim=-1, keepdim=True)
current_vector = image_features.cpu().numpy()[0]

# Lấy vector tương ứng từ Milvus (dữ liệu BTC)
client = MilvusClient(uri="http://localhost:19530")
kf_id = "L27_V005#k0245"
res = client.query(collection_name="keyframes", filter=f"keyframe_id == '{kf_id}'", output_fields=["embedding"])

if not res:
    print(f"Không tìm thấy vector cho {kf_id} trong Milvus!")
    exit(1)

btc_vector = np.array(res[0]["embedding"])

# Tính cosine similarity
similarity = np.dot(current_vector, btc_vector)
print(f"Cosine Similarity giữa model hiện tại ({CLIP_MODEL_NAME}) và data BTC: {similarity:.4f}")

if similarity < 0.8:
    print("=> CẢNH BÁO: Model CLIP không khớp! Không gian vector bị lệch.")
else:
    print("=> OK: Model CLIP khớp với data BTC.")
