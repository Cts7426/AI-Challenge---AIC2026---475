import argparse
from backend.llm.adapter import llm

def generate_variants(query: str) -> list[str]:
    """
    Sinh biến thể qua LLM. 
    Lưu ý: chưa tích hợp OpenCLIP để lọc Cosine > 0.85 ở file này
    do yêu cầu giữ script độc lập. Cần bổ sung metric Cosine nếu có CLIP.
    """
    prompt = f"Tạo 5 biến thể của câu truy vấn sau: '{query}'. Không được thêm thắt chi tiết mới."
    resp = llm(prompt)
    # Parse resp to list (giả định LLM trả về danh sách có đánh số)
    variants = [line.strip("- 1234567890.") for line in resp.split("\n") if line.strip()]
    
    valid_variants = []
    for v in variants:
        if not v: continue
        # Call LLM lần 2 để kiểm tra "bịa"
        check_prompt = f"Câu '{v}' có thêm chi tiết nào không có trong câu '{query}' không? Trả lời YES hoặc NO."
        check_resp = llm(check_prompt)
        if "NO" in check_resp.upper():
            valid_variants.append(v)
            
    return valid_variants

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
