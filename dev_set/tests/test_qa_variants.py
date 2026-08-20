"""Kiểm portfolio Q&A không làm đổi frame/video hoặc số slot đã cấp."""

from __future__ import annotations

import unittest

from backend.export.qa_variants import apply_qa_submission_policy, answer_surface_forms
from data.config.submit_format import Answer


def _answers(total: int = 5) -> list[Answer]:
    return [
        Answer("L26_V001", (100 + index,), "60g", f"L26_V001#k{index:04d}")
        for index in range(total)
    ]


class TestQAVariants(unittest.TestCase):
    def test_forms_giu_fact_so_don_vi_va_loai_trung(self):
        self.assertEqual(answer_surface_forms("60g"), ["60g", "60 g", "60 gram"])

    def test_semantic_giu_nguyen_danh_sach(self):
        answers = _answers()
        self.assertEqual(apply_qa_submission_policy(answers, "semantic"), answers)

    def test_exact_nhan_bien_the_nhung_giu_frame_va_so_slot(self):
        answers = _answers()
        output = apply_qa_submission_policy(answers, "exact")
        self.assertEqual(len(output), len(answers))
        self.assertEqual([item.answer_text for item in output],
                         ["60g", "60 g", "60 gram", "60g", "60 g"])
        self.assertEqual([item.frame_ids for item in output],
                         [(100,), (100,), (100,), (101,), (101,)])
        self.assertEqual([item.video_id for item in output], ["L26_V001"] * len(answers))

    def test_khoang_trang_sai_de_validator_bat_thay_vi_tu_sua(self):
        self.assertEqual(answer_surface_forms(" 60g"), [" 60g"])


if __name__ == "__main__":
    unittest.main()
