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
        
        # Đáp án đúng ở hạng 6 -> R@1=0, R@5=0, R@20=0.6, R@50=0.6, R@100=0.6 -> 1.8/5 = 0.36
        answers_rank6 = answers_wrong[:5] + [Answer(video_id="V1", frame_ids=(15,))] + answers_wrong[:94]
        self.assertAlmostEqual(final_score(answers_rank6, gt, "KIS"), 0.36)
        
        # Đáp án đúng ở hạng 101 -> (nộp 101 dòng)
        answers_rank101 = answers_wrong[:100] + [Answer(video_id="V1", frame_ids=(15,))]
        self.assertEqual(final_score(answers_rank101, gt, "KIS"), 0.00)
        
        # Nộp 40 dòng (thiếu dòng)
        answers_short = answers_wrong[:40]
        self.assertEqual(final_score(answers_short, gt, "KIS"), 0.00)
        
        # Đúng ở hạng 40 -> R@50=0.4, R@100=0.4 -> 0.8/5 = 0.16
        answers_short_hit = answers_wrong[:39] + [Answer(video_id="V1", frame_ids=(15,))]
        self.assertAlmostEqual(final_score(answers_short_hit, gt, "KIS"), 0.16)

if __name__ == '__main__':
    unittest.main()
