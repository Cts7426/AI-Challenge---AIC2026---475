import unittest
from dev_set.tools.schema import (
    GroundTruthKIS,
    GroundTruthQA,
    GroundTruthTRAKE,
    Answer,
)
from dev_set.tools.scoring import (
    recall_at_k,
    final_score,
    rscore_kis,
    rscore_qa,
    rscore_trake,
    answer_matches,
)

class TestScoring(unittest.TestCase):
    def test_rscore_kis(self):
        gt = GroundTruthKIS(query_id="Q1", video_id="V1", frame_start=10, frame_end=20)
        self.assertEqual(rscore_kis("V1", 15, gt), 1.0)
        self.assertEqual(rscore_kis("V1", 5, gt), 0.0)  # sai frame
        self.assertEqual(rscore_kis("V2", 15, gt), 0.0)  # sai video

    def test_rscore_qa(self):
        gt = GroundTruthQA(
            query_id="Q1", video_id="V1", frame_start=10, frame_end=20,
            answer_text="năm", answer_variants=["5", "nam", "five"]
        )
        # Đúng video, đúng frame, đúng answer
        self.assertEqual(rscore_qa("V1", 15, "năm", gt), 1.0)
        self.assertEqual(rscore_qa("V1", 15, "5", gt), 1.0)  # tier 2 match
        self.assertEqual(rscore_qa("V1", 15, "nam", gt), 1.0) # tier 1 match
        
        # QA frame đúng + answer sai -> 0.0
        self.assertEqual(rscore_qa("V1", 15, "sai rồi", gt), 0.0)
        
        # QA answer đúng + frame sai -> 0.0
        self.assertEqual(rscore_qa("V1", 5, "năm", gt), 0.0)

    def test_rscore_trake(self):
        gt = GroundTruthTRAKE(
            query_id="Q1", video_id="V1",
            frames=[{"start": 10, "end": 20}, {"start": 30, "end": 40}, {"start": 50, "end": 60}, {"start": 70, "end": 80}]
        )
        
        # Trúng 3/4 -> 0.75
        self.assertEqual(rscore_trake("V1", (15, 35, 55, 90), gt), 0.75)
        
        # Trúng 4/4 -> 1.0
        self.assertEqual(rscore_trake("V1", (10, 30, 50, 70), gt), 1.0)
        
        # Sai video -> 0.0
        self.assertEqual(rscore_trake("V2", (15, 35, 55, 75), gt), 0.0)

    def test_final_score(self):
        gt = GroundTruthKIS(query_id="Q1", video_id="V1", frame_start=10, frame_end=20)
        
        # Nộp 100 dòng sai
        answers_wrong = [Answer(video_id="V2", frame_ids=(0,)) for _ in range(100)]
        self.assertEqual(final_score(answers_wrong, gt, "KIS"), 0.0)
        
        # Đáp án đúng ở hạng 1 -> 1.00
        answers_rank1 = [Answer(video_id="V1", frame_ids=(15,))] + answers_wrong[:99]
        self.assertEqual(final_score(answers_rank1, gt, "KIS"), 1.0)
        
        # Đáp án đúng ở hạng 6 -> R@1=0, R@5=0, R@20=1, R@50=1, R@100=1 -> 3/5 = 0.60
        # (SỬA 14/08: R@k là "có trúng trong k câu đầu hay không" — nhị phân theo
        # k, KHÔNG tra bảng rút gọn theo hạng. Bản cũ ra 0.36 vì nhân nhầm với
        # _score_for_rank(6)=0.6, xem lịch sử sửa ở scoring.py.)
        answers_rank6 = answers_wrong[:5] + [Answer(video_id="V1", frame_ids=(15,))] + answers_wrong[:94]
        self.assertAlmostEqual(final_score(answers_rank6, gt, "KIS"), 0.60)
        
        # Đáp án đúng ở hạng 101 -> (nộp 101 dòng)
        answers_rank101 = answers_wrong[:100] + [Answer(video_id="V1", frame_ids=(15,))]
        self.assertEqual(final_score(answers_rank101, gt, "KIS"), 0.00)
        
        # Nộp 40 dòng (thiếu dòng)
        answers_short = answers_wrong[:40]
        self.assertEqual(final_score(answers_short, gt, "KIS"), 0.00)
        
        # Đúng ở hạng 40 -> R@1=R@5=R@20=0, R@50=R@100=1 -> 2/5 = 0.40
        answers_short_hit = answers_wrong[:39] + [Answer(video_id="V1", frame_ids=(15,))]
        self.assertAlmostEqual(final_score(answers_short_hit, gt, "KIS"), 0.40)

    def test_final_score_VI_DU_CO_DAP_SO_cua_BTC(self):
        """docs/contest.md dòng 60-62 — ví dụ CÓ ĐÁP SỐ của chính BTC:
        câu 1 = 0.5, câu 3 = 0.8 (cao nhất), câu 15 = 0.6 → Final = 0.74.

        Test này CHỐT CỨNG công thức 2 tầng đúng (R@k = max R-Score trong k câu
        đầu, Final = trung bình 5 R@k) — không cho phép ai "tối ưu" lại bằng
        cách tra bảng rút gọn theo hạng như bug đã tìm thấy 14/08 (final_score
        ra 0.612 thay vì 0.74 khi còn bug).
        """
        gt = GroundTruthTRAKE(
            query_id="Q1", video_id="V1",
            frames=[{"start": 0, "end": 100}],  # không dùng tới, rscore bị monkeypatch
        )
        scores_by_rank = {1: 0.5, 3: 0.8, 15: 0.6}
        import dev_set.tools.scoring as sc
        goc = sc.rscore_trake
        try:
            sc.rscore_trake = lambda video_id, frames, gt: scores_by_rank.get(frames[0], 0.0)
            rows = [Answer(video_id="V1", frame_ids=(i,)) for i in range(1, 101)]
            self.assertAlmostEqual(sc.recall_at_k(rows, gt, "TRAKE", 1), 0.5)
            self.assertAlmostEqual(sc.recall_at_k(rows, gt, "TRAKE", 5), 0.8)
            self.assertAlmostEqual(sc.recall_at_k(rows, gt, "TRAKE", 20), 0.8)
            self.assertAlmostEqual(sc.recall_at_k(rows, gt, "TRAKE", 50), 0.8)
            self.assertAlmostEqual(sc.recall_at_k(rows, gt, "TRAKE", 100), 0.8)
            self.assertAlmostEqual(sc.final_score(rows, gt, "TRAKE"), 0.74)
        finally:
            sc.rscore_trake = goc

if __name__ == '__main__':
    unittest.main()
