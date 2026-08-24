"""Gate provenance phải chặn promotion khi nhãn chưa được người xác minh."""

from __future__ import annotations

import pytest

from dev_set.tools import run_evaluation as evaluation
from dev_set.tools.schema import GroundTruthKIS, GroundTruthQA
from dev_set.tools.scoring import (
    assess_promotion_ground_truth,
    require_promotion_ground_truth,
)


def test_gt_cu_mac_dinh_unknown_va_phan_tich_bao_khong_du_dieu_kien_promotion():
    """Bỏ metadata khỏi GT cũ phải vẫn đọc được, nhưng không thể promotion im lặng."""
    legacy = GroundTruthKIS(
        query_id="KIS_LEGACY", video_id="L21_V001", frame_start=10, frame_end=20,
    )

    readiness = assess_promotion_ground_truth([legacy])

    assert legacy.verification_status == "unknown"
    assert readiness.eligible is False
    assert readiness.unverified_query_ids == ("KIS_LEGACY",)
    assert "không đủ điều kiện promotion" in readiness.message


def test_gt_verified_bat_buoc_co_du_provenance_nguoi_va_thoi_diem_xac_minh():
    """Một nhãn tự nhận verified nhưng thiếu dấu vết phải bị schema từ chối."""
    with pytest.raises(ValueError, match="verified_by"):
        GroundTruthKIS(
            query_id="KIS_MISSING_AUDIT", video_id="L21_V002", frame_start=10, frame_end=20,
            verification_status="verified", provenance="human-review/2026-08-24",
            verified_at="2026-08-24T10:00:00+07:00",
        )


def test_promotion_chi_nhan_toan_bo_gt_verified_co_provenance():
    """Đổi gate để bỏ qua một nhãn unknown phải làm test này fail."""
    verified = GroundTruthQA(
        query_id="QA_VERIFIED", video_id="L21_V003", frame_start=10, frame_end=20,
        answer_text="ba", answer_variants=["ba", "3", "three"],
        verification_status="verified", provenance="human-review/2026-08-24",
        verified_by="operator", verified_at="2026-08-24T10:00:00+07:00",
    )
    unknown = GroundTruthKIS(
        query_id="KIS_UNKNOWN", video_id="L21_V004", frame_start=10, frame_end=20,
    )

    assert assess_promotion_ground_truth([verified]).eligible is True
    require_promotion_ground_truth([verified])
    with pytest.raises(ValueError, match="KIS_UNKNOWN"):
        require_promotion_ground_truth([verified, unknown])


def test_promotion_tu_choi_query_khong_co_gt_da_parse():
    """GT parse lỗi/thiếu không được biến thành một promotion thiếu dữ liệu."""
    verified = GroundTruthKIS(
        query_id="KIS_PRESENT", video_id="L21_V005", frame_start=10, frame_end=20,
        verification_status="verified", provenance="human-review/2026-08-24",
        verified_by="operator", verified_at="2026-08-24T10:00:00+07:00",
    )

    readiness = assess_promotion_ground_truth(
        [verified], expected_query_ids=["KIS_PRESENT", "KIS_MISSING"],
    )

    assert readiness.eligible is False
    assert readiness.missing_query_ids == ("KIS_MISSING",)
    with pytest.raises(ValueError, match="KIS_MISSING"):
        require_promotion_ground_truth(
            [verified], expected_query_ids=["KIS_PRESENT", "KIS_MISSING"],
        )


def test_entrypoint_promotion_chan_gt_legacy_truoc_khi_ket_noi_db(
    tmp_path, monkeypatch, capsys,
):
    """Gate fail-closed phải chạy trước resource ngoài để lỗi provenance rõ ràng."""
    queries_dir = tmp_path / "dev_set" / "queries"
    gt_dir = tmp_path / "dev_set" / "ground_truth"
    queries_dir.mkdir(parents=True)
    gt_dir.mkdir(parents=True)
    (queries_dir / "tune_kis.jsonl").write_text(
        '{"query_id":"KIS_LEGACY","task_type":"KIS","query_vi":"câu test","split":"tune"}\n',
        encoding="utf-8",
    )
    (gt_dir / "tune_gt.jsonl").write_text(
        '{"query_id":"KIS_LEGACY","task_type":"KIS","video_id":"L21_V001","frame_start":10,"frame_end":20}\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(evaluation, "es_connect", lambda: pytest.fail("không được chạm ES"))
    monkeypatch.setattr(evaluation, "milvus_connect", lambda: pytest.fail("không được chạm Milvus"))
    monkeypatch.setattr("sys.argv", ["run_evaluation", "--promotion"])

    with pytest.raises(SystemExit) as exc:
        evaluation.run_evaluation()

    assert exc.value.code == 2
    assert "KIS_LEGACY" in capsys.readouterr().err
