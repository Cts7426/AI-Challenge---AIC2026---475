import unittest
import numpy as np
from dev_set.tools.stats import paired_bootstrap, noise_threshold

class TestStats(unittest.TestCase):
    def test_paired_bootstrap_identical(self):
        # Nếu 2 bộ điểm giống hệt nhau, chênh lệch = 0, p-value = 1.0
        scores_a = [1.0, 0.0, 1.0, 0.0, 0.5]
        scores_b = [1.0, 0.0, 1.0, 0.0, 0.5]
        
        diff_mean, ci_lower, ci_upper, p_val, std_err = paired_bootstrap(scores_a, scores_b, n_boot=1000)
        self.assertAlmostEqual(diff_mean, 0.0)
        self.assertAlmostEqual(ci_lower, 0.0)
        self.assertAlmostEqual(ci_upper, 0.0)
        self.assertAlmostEqual(std_err, 0.0)
        self.assertAlmostEqual(p_val, 1.0)

    def test_paired_bootstrap_different(self):
        # Nếu a luôn lớn hơn b
        scores_a = [1.0, 1.0, 1.0, 1.0, 1.0]
        scores_b = [0.0, 0.0, 0.0, 0.0, 0.0]
        
        diff_mean, ci_lower, ci_upper, p_val, std_err = paired_bootstrap(scores_a, scores_b, n_boot=1000)
        self.assertAlmostEqual(diff_mean, 1.0)
        self.assertAlmostEqual(ci_lower, 1.0)
        self.assertAlmostEqual(ci_upper, 1.0)
        self.assertAlmostEqual(std_err, 0.0)
        self.assertAlmostEqual(p_val, 0.0)

    def test_paired_bootstrap_mixed(self):
        scores_a = [1.0, 0.0, 1.0, 0.0, 1.0]
        scores_b = [0.0, 1.0, 0.0, 0.0, 0.0]
        # diffs: [1.0, -1.0, 1.0, 0.0, 1.0] -> mean = 0.4
        
        diff_mean, ci_lower, ci_upper, p_val, std_err = paired_bootstrap(scores_a, scores_b, n_boot=1000, seed=42)
        self.assertAlmostEqual(diff_mean, 0.4)
        # CI sẽ bao quanh 0.4
        self.assertTrue(ci_lower <= 0.4 <= ci_upper)
        self.assertTrue(std_err > 0)
        self.assertTrue(0 <= p_val <= 1)

    def test_noise_threshold(self):
        se, margin = noise_threshold(60, 0.5)
        # SE = sqrt(0.25 / 60) ≈ 0.0645
        self.assertAlmostEqual(se, 0.0645497, places=5)
        # margin = 1.96 * se * sqrt(2) ≈ 0.1788
        self.assertAlmostEqual(margin, 0.178885, places=4)

if __name__ == '__main__':
    unittest.main()
