import numpy as np

def paired_bootstrap(scores_a: list[float], scores_b: list[float], n_boot: int = 10000, seed: int = 42):
    """
    So sánh hai bộ điểm (cùng độ dài) bằng bootstrap ghép cặp.
    Trả về tuple: (diff_mean, ci_lower, ci_upper, p_value, std_err)
    """
    if len(scores_a) != len(scores_b):
        raise ValueError("scores_a và scores_b phải cùng độ dài")
    if not scores_a:
        raise ValueError("Danh sách điểm trống")
        
    n = len(scores_a)
    rng = np.random.default_rng(seed)
    diffs = np.array(scores_a) - np.array(scores_b)
    
    # Lấy mẫu có hoàn lại từ diffs
    # Dùng numpy để vector hóa vòng lặp giúp chạy nhanh hơn
    indices = rng.integers(0, n, size=(n_boot, n))
    boot_samples = diffs[indices]
    boot_means = np.mean(boot_samples, axis=1)
    
    diff_mean = float(np.mean(diffs))
    ci_lower = float(np.percentile(boot_means, 2.5))
    ci_upper = float(np.percentile(boot_means, 97.5))
    std_err = float(np.std(boot_means))
    
    # p-value 2 chiều
    p_val = min(np.sum(boot_means <= 0), np.sum(boot_means >= 0)) * 2 / n_boot
    p_val = min(float(p_val), 1.0)
    
    return diff_mean, ci_lower, ci_upper, p_val, std_err

def noise_threshold(n: int, expected_score: float = 0.5) -> tuple[float, float]:
    """
    Tính sai số chuẩn (SE) và ngưỡng chênh lệch tối thiểu (margin)
    Dựa trên xấp xỉ phân phối chuẩn cho tỷ lệ.
    """
    if n <= 0:
        return 0.0, 0.0
    se = np.sqrt(expected_score * (1 - expected_score) / n)
    margin = 1.96 * se * np.sqrt(2) # nhân căn 2 vì đang so sánh 2 phân phối
    return float(se), float(margin)
