import argparse
import json

from backend.llm.adapter import llm


VARIANTS_SCHEMA = {
    "type": "object",
    "properties": {
        "variants": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "adds_detail": {"type": "boolean"},
                },
                "required": ["text", "adds_detail"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["variants"],
    "additionalProperties": False,
}

def generate_variants(query: str) -> list[str]:
    """
    Sinh biến thể qua LLM. 
    Lưu ý: chưa tích hợp OpenCLIP để lọc Cosine > 0.85 ở file này
    do yêu cầu giữ script độc lập. Cần bổ sung metric Cosine nếu có CLIP.
    """
    prompt = (
        "Tạo đúng 5 biến thể ngắn của truy vấn dưới đây. Không thêm màu sắc, số "
        "lượng, vật thể, người, địa điểm hay hành động không có trong câu gốc. "
        "Với mỗi biến thể, đánh dấu adds_detail=true nếu chính biến thể đó thêm "
        "bất kỳ chi tiết mới nào.\n\n"
        f"Truy vấn gốc: {query}"
    )
    payload = json.loads(llm(
        prompt, json_schema=VARIANTS_SCHEMA, max_tokens=512,
    ))
    # Một structured request thay cho 1 lượt sinh + tối đa 5 lượt kiểm riêng.
    # Vẫn fail-safe: chỉ nhận dòng model tự đánh dấu không thêm chi tiết.
    return [
        row["text"].strip() for row in payload["variants"]
        if row.get("text", "").strip() and not row.get("adds_detail", True)
    ][:5]

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", type=str, required=True)
    args = parser.parse_args()
    
    print(f"Câu gốc: {args.query}")
    print("Đang sinh biến thể...")
    res = generate_variants(args.query)
    print("Các biến thể hợp lệ:")
    for r in res:
        print("-", r)
