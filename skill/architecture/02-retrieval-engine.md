# Architecture 02: Retrieval Engine (Động cơ Tìm kiếm)

Luồng tìm kiếm (Search Flow) nằm chủ yếu trong `backend/retrieval/search.py`. 

## 1. Luồng chạy của một truy vấn
Mọi query sẽ đi qua 5 nhánh song song (bắn bằng `ThreadPoolExecutor` để giảm độ trễ):
1. **Vector (Milvus):** Encode câu tiếng Anh bằng CLIP → Tìm Keyframe.
2. **Metadata (ES):** BM25 tiếng Việt trên thông tin Video → Gán thứ hạng video cho mọi keyframe bên trong nó.
3. **Objects (ES):** BM25 tiếng Anh trên tập nhãn `labels.txt` → Tìm Keyframe.
4. **OCR (ES):** BM25 tiếng Việt trên chữ nhận diện được → Tìm Keyframe.
5. **ASR (ES):** BM25 tiếng Việt trên lời nói (chỉ định vị khoảng thời gian) → Tìm Keyframe tương ứng nhờ `_nominate_from_asr`.

## 2. Hợp nhất bằng RRF (Reciprocal Rank Fusion)
Không dùng cộng điểm trọng số tĩnh (Static Weights), hệ thống hợp nhất các nhánh bằng thuật toán RRF. 
Công thức: `score(d) = Σ_nhánh 1 / (K + rank_nhánh(d))`

**Lý do chọn RRF:**
- Triệt tiêu sự khác biệt về thang đo (Cosine [-1,1] vs BM25 không giới hạn).
- Không cần phải Hardcode Threshold (Không cần thiết lập ngưỡng điểm chết).

## 3. Gom nhóm theo Cảnh quay (Group by Shot)
Để tránh 10 kết quả top đầu đều là 1 cảnh duy nhất kéo dài, hệ thống sử dụng bảng tra `clip_kf_map.parquet` (keyframe_id → shot_id). 
Kết quả trả về luôn lọc lại để giữ mỗi `shot_id` chỉ 1 đại diện có điểm RRF cao nhất.

## 4. Ràng buộc Debug
Hàm `search()` bắt buộc phải trả về thuộc tính `ranks` cho mỗi kết quả, ghi rõ thứ hạng gốc của kết quả đó ở từng nhánh. Nếu thiếu dữ liệu này, việc phân tích lỗi (Error Analysis) sẽ trở thành đoán mò.
