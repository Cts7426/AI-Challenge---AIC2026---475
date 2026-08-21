import unittest
from dev_set.tools.schema import (
    Query,
    GroundTruthKIS,
    GroundTruthQA,
    GroundTruthTRAKE,
)

class TestSchema(unittest.TestCase):
    def test_query_validation(self):
        q = Query(query_id="Q1", task_type="KIS", query_vi="test", split="tune")
        self.assertEqual(q.query_id, "Q1")

        with self.assertRaisesRegex(ValueError, "task_type invalid"):
            Query(query_id="Q1", task_type="INVALID", query_vi="test", split="tune")

        with self.assertRaisesRegex(ValueError, "split invalid"):
            Query(query_id="Q1", task_type="KIS", query_vi="test", split="invalid")

        with self.assertRaisesRegex(ValueError, "TRAKE query must have integer n_events >= 2"):
            Query(query_id="Q1", task_type="TRAKE", query_vi="test", split="tune")

        with self.assertRaisesRegex(ValueError, "event_descs length"):
            Query(
                query_id="Q1", task_type="TRAKE", query_vi="test", split="tune",
                n_events=3, event_descs=["a", "b"],
            )

        Query(
            query_id="Q1", task_type="TRAKE", query_vi="test", split="tune",
            n_events=2, event_descs=["a", "b"],
        )

    def test_gt_kis_validation(self):
        gt = GroundTruthKIS(query_id="Q1", video_id="V1", frame_start=10, frame_end=20)
        self.assertEqual(gt.frame_start, 10)

        with self.assertRaisesRegex(ValueError, "frame_start.*> frame_end"):
            GroundTruthKIS(query_id="Q1", video_id="V1", frame_start=20, frame_end=10)

        with self.assertRaisesRegex(ValueError, "frame_start < 0"):
            GroundTruthKIS(query_id="Q1", video_id="V1", frame_start=-1, frame_end=10)

    def test_gt_qa_validation(self):
        gt = GroundTruthQA(
            query_id="Q1", video_id="V1", frame_start=10, frame_end=20,
            answer_text="đáp án", answer_variants=["a", "b", "c"]
        )
        self.assertEqual(gt.answer_text, "đáp án")

        with self.assertRaisesRegex(ValueError, "QA must have answer_text"):
            GroundTruthQA(
                query_id="Q1", video_id="V1", frame_start=10, frame_end=20,
                answer_text="", answer_variants=["a", "b", "c"]
            )

        with self.assertRaisesRegex(ValueError, "QA must have >= 3 answer_variants"):
            GroundTruthQA(
                query_id="Q1", video_id="V1", frame_start=10, frame_end=20,
                answer_text="đáp án", answer_variants=["a", "b"]
            )

    def test_gt_trake_validation(self):
        gt = GroundTruthTRAKE(
            query_id="Q1", video_id="V1",
            frames=[{"start": 10, "end": 20}, {"start": 30, "end": 40}]
        )
        self.assertEqual(len(gt.frames), 2)

        with self.assertRaisesRegex(ValueError, "TRAKE must have at least 1 frame window"):
            GroundTruthTRAKE(query_id="Q1", video_id="V1", frames=[])

        with self.assertRaisesRegex(ValueError, "overlaps or is unordered"):
            GroundTruthTRAKE(
                query_id="Q1", video_id="V1",
                frames=[{"start": 10, "end": 20}, {"start": 15, "end": 25}]
            )

        with self.assertRaisesRegex(ValueError, "overlaps or is unordered"):
            GroundTruthTRAKE(
                query_id="Q1", video_id="V1",
                frames=[{"start": 30, "end": 40}, {"start": 10, "end": 20}]
            )

if __name__ == '__main__':
    unittest.main()
