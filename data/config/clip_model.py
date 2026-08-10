# data/config/clip_model.py — model CLIP dùng cho CẢ hai phía (ảnh BTC + query text)
#
# ✅ ĐÃ CHỐT (CLAUDE.md mục 11): BTC phát features bằng `clip-ViT-B-32`, 512 chiều.
#
# Vì sao có 2 tên model?
#   CLIP_BTC_MODEL_NAME  — tên BTC công bố (theo cách gọi của sentence-transformers)
#   CLIP_MODEL_NAME      — tên TƯƠNG ĐƯƠNG trong open_clip (thư viện ta dùng để encode)
# Cùng một bộ trọng số OpenAI gốc, chỉ khác cách đặt tên giữa hai thư viện.
#
# ⚠️ Hậu tố -quickgelu KHÔNG được bỏ: trọng số OpenAI train bằng activation QuickGELU;
# open_clip >= 3.x hiểu tên "ViT-B-32" trần là GELU thường → nạp trọng số openai vào
# sẽ LỆCH không gian vector (chỉ có warning "QuickGELU mismatch", không crash).
# Đây đúng loại lỗi im lặng CLAUDE.md bất biến 2 nói tới.
#
# Sự tương đương này là GIẢ ĐỊNH cho tới khi chạy `scripts/verify_clip_space.py`
# (A1.0b) trên data thật: encode lại ảnh BTC → cosine với vector BTC phải ≈ 1.0.
# Chưa chạy kiểm chứng thì chưa được tin kết quả search nào.
#
# Đổi model ở đây → PHẢI nạp lại toàn bộ features (embedding cũ khác không gian);
# loader sẽ tự chặn nhờ .meta.json (xem backend/indexing/load_clip.py).

CLIP_BTC_MODEL_NAME = "clip-ViT-B-32"    # ✅ BTC công bố
CLIP_MODEL_NAME = "ViT-B-32-quickgelu"   # tương đương trong open_clip
CLIP_PRETRAINED = "openai"               # bộ trọng số gốc OpenAI
CLIP_EMBEDDING_DIM = 512                 # ✅ BTC công bố
