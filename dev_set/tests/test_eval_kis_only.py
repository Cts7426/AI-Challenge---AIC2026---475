"""KIS-only chỉ được chạy khi mọi query có bản dịch cố định, không gọi LLM."""

from __future__ import annotations

import json
import sys
from unittest.mock import Mock

import pytest

from dev_set.tools import eval_kis_only as K


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def test_dien_query_en_thieu_theo_query_id_tu_tune_all(tmp_path):
    primary = tmp_path / "tune_kis.jsonl"
    fallback = tmp_path / "tune_all.json"
    _write_jsonl(primary, [{
        "query_id": "K01", "task_type": "KIS", "query_vi": "bác sĩ khám bệnh",
        "query_en": "", "split": "tune",
    }])
    fallback.write_text(json.dumps([{
        "query_id": "K01", "task_type": "KIS", "query_vi": "khác cũng không sao",
        "query_en": "doctor examining patient", "split": "tune",
    }]), encoding="utf-8")

    queries = K.load_zero_llm_queries(primary, fallback)
    assert len(queries) == 1
    assert queries[0].query_en == "doctor examining patient"


def test_giu_query_en_chinh_khong_bi_fallback_ghi_de(tmp_path):
    primary = tmp_path / "tune_kis.jsonl"
    fallback = tmp_path / "tune_all.json"
    _write_jsonl(primary, [{
        "query_id": "K01", "task_type": "KIS", "query_vi": "bác sĩ khám bệnh",
        "query_en": "primary translation", "split": "tune",
    }])
    fallback.write_text(json.dumps([{
        "query_id": "K01", "task_type": "KIS", "query_vi": "bác sĩ khám bệnh",
        "query_en": "fallback translation", "split": "tune",
    }]), encoding="utf-8")
    assert K.load_zero_llm_queries(primary, fallback)[0].query_en == "primary translation"


def test_van_thieu_thi_fail_truoc_connect_va_search(tmp_path, monkeypatch):
    q_path = tmp_path / "dev_set" / "queries" / "tune_kis.jsonl"
    _write_jsonl(q_path, [{
        "query_id": "K_MISSING", "task_type": "KIS", "query_vi": "câu chưa dịch",
        "query_en": None, "split": "tune",
    }])
    es = Mock()
    milvus = Mock()
    search = Mock()
    monkeypatch.setattr(K, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(K, "es_connect", es)
    monkeypatch.setattr(K, "milvus_connect", milvus)
    monkeypatch.setattr(K, "search", search)
    monkeypatch.setattr(sys, "argv", ["eval_kis_only", "--split", "tune"])

    with pytest.raises(SystemExit) as exc:
        K.main()
    assert exc.value.code == 2
    es.assert_not_called()
    milvus.assert_not_called()
    search.assert_not_called()


def test_main_truyen_query_en_tuong_minh_va_khong_goi_llm(tmp_path, monkeypatch, capsys):
    queries_dir = tmp_path / "dev_set" / "queries"
    gt_dir = tmp_path / "dev_set" / "ground_truth"
    results_dir = tmp_path / "dev_set" / "results"
    results_dir.mkdir(parents=True)
    _write_jsonl(queries_dir / "tune_kis.jsonl", [{
        "query_id": "K01", "task_type": "KIS", "query_vi": "bác sĩ khám bệnh",
        "query_en": None, "split": "tune",
    }])
    (queries_dir / "tune_all.json").write_text(json.dumps([{
        "query_id": "K01", "task_type": "KIS", "query_vi": "bác sĩ khám bệnh",
        "query_en": "doctor examining patient", "split": "tune",
    }]), encoding="utf-8")
    _write_jsonl(gt_dir / "tune_gt.jsonl", [{
        "query_id": "K01", "task_type": "KIS", "video_id": "L21_V001",
        "frame_start": 1, "frame_end": 20,
    }])

    search_calls = []

    def fake_search(query_vi, *, query_en, **kwargs):
        search_calls.append((query_vi, query_en))
        assert query_en == "doctor examining patient"
        return [{
            "shot_id": "L21_V001#s0001", "score": 1.0,
            "keyframe_id": "L21_V001#k0001", "video_id": "L21_V001",
        }]

    monkeypatch.setattr(K, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(K, "es_connect", Mock())
    monkeypatch.setattr(K, "milvus_connect", Mock())
    monkeypatch.setattr(K, "load_frame_map", lambda: {"L21_V001#k0001": 10})
    monkeypatch.setattr(K, "search", fake_search)
    monkeypatch.setattr(K, "allocate", lambda *args, **kwargs: [])
    monkeypatch.setattr(K, "recall_at_k", lambda *args, **kwargs: 1.0)
    monkeypatch.setattr(K, "final_score", lambda *args, **kwargs: 1.0)
    monkeypatch.setattr(K, "rscore_kis", lambda *args, **kwargs: 1.0)
    monkeypatch.setattr(
        "backend.llm.adapter.llm",
        lambda *args, **kwargs: pytest.fail("KIS-only không được gọi llm()"),
    )
    monkeypatch.setattr(sys, "argv", ["eval_kis_only", "--split", "tune"])

    K.main()
    assert search_calls == [("bác sĩ khám bệnh", "doctor examining patient")]
    assert "0 lượt gọi llm()" in capsys.readouterr().out

