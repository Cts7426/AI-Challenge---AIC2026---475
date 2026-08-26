"""VLM-as-a-Judge Agentic Reranker

Mô-đun này nhận danh sách kết quả (từ search gốc), đọc trực tiếp ảnh của từng kết quả,
và yêu cầu VLM chấm điểm xem ảnh đó có thực sự khớp với truy vấn của người dùng không.
"""
from __future__ import annotations

import re
import time
from typing import Any

from backend.common.frame_assets import resolve_frame_path
from mlx_vlm import generate, load
from mlx_vlm.utils import load_config as load_mlx_config


class VLMReranker:
    def __init__(self, model_path: str = "mlx-community/Llama-3.2-11B-Vision-Instruct-4bit"):
        print(f"  [reranker] Khởi tạo VLM {model_path}...")
        self.model, self.processor = load(model_path)
        
        # Monkey patch để lách lỗi thiếu chat_template của MLX
        if not hasattr(self.processor, "chat_template") or self.processor.chat_template is None:
            self.processor.chat_template = "{% for message in messages %}{{ message['content'] }}{% endfor %}"

        self.model_path = model_path
        print("  [reranker] Tải model thành công.")

    def rerank(self, query: str, candidates: list[dict[str, Any]], top_k_to_rerank: int = 50) -> list[dict[str, Any]]:
        """Nhận danh sách candidate từ search, dùng VLM chấm điểm lại top_k_to_rerank."""
        if not candidates:
            return []

        # Giữ lại các candidate ngoài top_k_to_rerank để ghép lại sau
        to_rerank = candidates[:top_k_to_rerank]
        others = candidates[top_k_to_rerank:]

        print(f"  [reranker] VLM đang chấm điểm {len(to_rerank)} ứng viên hàng đầu...")
        
        # Prompt ép VLM chấm điểm
        prompt_template = (
            "You are a strict judge assessing how well an image matches a search query.\n"
            "Search Query: \"{query}\"\n\n"
            "Analyze the image and score its relevance to the query from 0 to 100. "
            "Return ONLY the integer number, nothing else."
        )

        for i, cand in enumerate(to_rerank):
            video_id = cand["video_id"]
            frame_idx = cand.get("frame_idx")

            # Lấy đường dẫn ảnh chuẩn của hệ thống. Fallback keyframe_id: nhánh
            # _fill_from_milvus() trong search() có try/except nuốt lỗi, nên
            # frame_idx có thể None dù candidate vẫn hợp lệ qua keyframe_id.
            img_path = resolve_frame_path(
                video_id, frame_idx, keyframe_id=cand.get("keyframe_id"),
            )
            if not img_path or not img_path.path or not img_path.path.exists():
                cand["vlm_score"] = 0
                continue

            prompt_text = prompt_template.format(query=query)
            
            # Format prompt cho Llama 3
            prompt = f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\nYou are a JSON machine. Only output a number.<|eot_id|><|start_header_id|>user<|end_header_id|>\n\n<|image|>\n{prompt_text}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n"
            
            try:
                output = generate(
                    self.model,
                    self.processor,
                    prompt=prompt,
                    image=[str(img_path.path)],
                    verbose=False,
                    max_tokens=10
                )
                
                text_out = output.text if hasattr(output, "text") else str(output)

                # Trích xuất con số từ text_out. VLM được yêu cầu trả 0-100
                # nhưng không đảm bảo tuân thủ: có thể trả "0.85" (hiểu thang
                # 0-1) hoặc "7.5/10". \d+ đơn thuần cắt "0.85" thành "0" — một
                # ảnh đúng bị chấm 0 điểm âm thầm. Bắt số thập phân trước,
                # rồi quy đổi về thang 0-100 nếu rõ ràng VLM trả thang khác.
                nums = re.findall(r'\d+\.?\d*', text_out)
                score = float(nums[0]) if nums else 0.0
                if 0 < score <= 1:
                    score *= 100  # thang 0-1 → 0-100
                elif "/10" in text_out and score <= 10:
                    score *= 10  # dạng "7.5/10" → 0-100
                # Gán điểm VLM mới
                cand["vlm_score"] = score
                print(f"    - {video_id} f{frame_idx}: {score} điểm")
                
            except Exception as e:
                print(f"  [reranker] Lỗi chấm điểm {video_id} frame {frame_idx}: {e}")
                cand["vlm_score"] = 0
                
        # Sắp xếp lại dựa trên điểm VLM (ai điểm VLM cao nhất sẽ lên đầu)
        # Nếu điểm VLM bằng nhau, ưu tiên điểm hệ thống cũ (RRF score)
        to_rerank.sort(key=lambda x: (x.get("vlm_score", 0), x.get("score", 0)), reverse=True)
        
        return to_rerank + others
