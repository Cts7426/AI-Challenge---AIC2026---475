import argparse

def calculate_cohens_kappa(labels_a: list[int], labels_b: list[int]) -> float:
    """Tính hệ số thống nhất Cohen's Kappa giữa 2 người gán nhãn."""
    assert len(labels_a) == len(labels_b)
    n = len(labels_a)
    if n == 0: return 0.0
    
    agree = sum(1 for a, b in zip(labels_a, labels_b) if a == b)
    p_o = agree / n
    
    # Tính p_e (xác suất đồng thuận ngẫu nhiên)
    freq_a = {l: labels_a.count(l)/n for l in set(labels_a)}
    freq_b = {l: labels_b.count(l)/n for l in set(labels_b)}
    
    p_e = sum(freq_a.get(l, 0) * freq_b.get(l, 0) for l in set(labels_a) | set(labels_b))
    
    if p_e == 1.0:
        return 1.0
        
    kappa = (p_o - p_e) / (1 - p_e)
    return kappa

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", help="File CSV chứa nhãn của 2 người")
    args = parser.parse_args()
    
    print("Script tính toán báo cáo Human Eval (Cohen's Kappa).")
    print("Yêu cầu hệ số phải >= 0.70")
