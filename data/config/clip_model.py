# TODO: BTC — version model CLIP mà BTC dùng để tạo features (xem CLAUDE.md mục 3, 7).
# Query encoder PHẢI dùng đúng model này, sai model → vector khác không gian → search vô nghĩa.
#
# BTC CHƯA công bố → tạm chọn OpenAI CLIP ViT-B/32 vì:
#   - là model phổ biến nhất được BTC các kỳ AIC/VBS trước dùng phát features;
#   - dim 512, encode text nhanh trên CPU (máy dev 16GB không có GPU);
#   - open_clip với pretrained="openai" cho ĐÚNG trọng số gốc OpenAI
#     → cùng không gian vector với ai dùng package `clip` chính chủ.
# Khi BTC công bố: chỉ sửa 3 hằng dưới đây, không phải sửa code nơi khác.
# Đổi model xong PHẢI nạp lại features (embedding cũ khác không gian).

# Lưu ý hậu tố -quickgelu: trọng số gốc OpenAI dùng activation QuickGELU;
# trong open_clip >= 3.x tên "ViT-B-32" trần mặc định GELU thường → load trọng số
# openai sẽ LỆCH không gian vector (có warning "QuickGELU mismatch").
CLIP_MODEL_NAME = "ViT-B-32-quickgelu"   # TODO: BTC xác nhận — tên theo chuẩn open_clip
CLIP_PRETRAINED = "openai"     # TODO: BTC xác nhận — bộ trọng số ("openai", "laion2b_s34b_b79k", ...)
CLIP_EMBEDDING_DIM = 512       # TODO: BTC xác nhận (phụ thuộc model)
