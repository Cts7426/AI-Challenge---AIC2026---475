# tests/test_run.py — A6.0: test orchestrator đầy đủ (run.py)
#
# `giai_mot_query()` bị thay bằng hàm giả trong hầu hết test: cái cần kiểm ở đây
# KHÔNG phải chất lượng search (đã có test riêng) mà là BỘ KHUNG chạy lô —
# checkpoint, chạy tiếp khi hỏng, exit code, ghi file. Bộ khung đó phải đúng kể
# cả khi mọi thứ bên dưới hỏng, nên nó phải test được mà không cần Docker/LLM.
#
# Video/frame dùng số THẬT từ video_info + frame_map (qua conftest): validator
# ngữ nghĩa của D0.2 kiểm frame_id ∈ [0, n_frames) nên dữ liệu bịa sẽ bị từ chối
# vì lý do chẳng liên quan gì tới thứ đang test.
#
# Chạy: python -m pytest tests/test_run.py -q

from __future__ import annotations

import json
import hashlib
import zipfile
from pathlib import Path

import pytest

import run as R
from data.config.submit_format import Answer
from dev_set.tools.scorer_contract import scorer_contract_sha256


# ------------------------------------------------------------------ tiện ích

@pytest.fixture(autouse=True)
def explicit_test_llm_runtime(monkeypatch):
    """Test batch dùng solver giả nhưng vẫn phải tuân gate cấu hình release."""
    monkeypatch.setenv("LLM_BACKEND", "local")
    monkeypatch.setenv("LLM_LOCAL_MODEL", "test-only-model")

@pytest.fixture
def video(real_videos):
    """Một video thật + số frame của nó."""
    return real_videos[0]


def _answers(video_id: str, n_frames: int, total: int, *, answer_text=None,
             n_trake: int = 1) -> list[Answer]:
    """`total` Answer hợp lệ, không trùng nhau, frame nằm trong video."""
    ra = []
    for i in range(total):
        frames = tuple(i * (n_trake + 1) + j for j in range(n_trake))
        assert frames[-1] < n_frames, "video test quá ngắn"
        ra.append(Answer(video_id=video_id, frame_ids=frames,
                         answer_text=answer_text, keyframe_id=f"kf{i}"))
    return ra


@pytest.fixture
def viet_queries(tmp_path):
    """Ghi file truy vấn ra đĩa, trả đường dẫn."""
    def _viet(queries, ten="q.json"):
        p = tmp_path / ten
        if ten.endswith(".jsonl"):
            p.write_text("\n".join(json.dumps(q, ensure_ascii=False) for q in queries),
                         encoding="utf-8")
        else:
            p.write_text(json.dumps(queries, ensure_ascii=False), encoding="utf-8")
        return p
    return _viet


@pytest.fixture
def chay(monkeypatch, tmp_path, viet_queries, video):
    """Chạy run.main() với `giai_mot_query` giả. Trả (exit_code, out_dir, gọi[])."""
    vid, n_frames = video

    def _chay(queries, *, hong_qid=(), extra_args=(), total=5, out="ra"):
        goi: list[str] = []

        def _gia(q, tong):
            goi.append(q["query_id"])
            if q["query_id"] in hong_qid:
                raise RuntimeError("giả vờ hỏng")
            n = len(q.get("event_descs", [])) if q["task_type"] == "TRAKE" else 1
            return (
                _answers(vid, n_frames, tong,
                         answer_text="5" if q["task_type"] == "QA" else None,
                         n_trake=max(n, 2) if q["task_type"] == "TRAKE" else 1),
                {"answer_text": "5" if q["task_type"] == "QA" else None,
                 "n_trake": max(n, 2) if q["task_type"] == "TRAKE" else None},
            )

        monkeypatch.setattr(R, "giai_mot_query", _gia)
        # Preflight gọi deep check thật (cần Docker) — không phải thứ test này
        # kiểm; nó có test riêng ở tests/test_health.py.
        monkeypatch.setattr(R, "_preflight", lambda log, bo_qua: True)
        qp = viet_queries(queries)
        out_dir = tmp_path / out
        argv = ["run.py", "--queries", str(qp), "--out", str(out_dir),
                "--answers", str(total), *extra_args]
        monkeypatch.setattr(R.sys, "argv", argv)
        return R.main(), out_dir, goi

    return _chay


KIS = {"query_id": "q1", "task_type": "KIS", "query_vi": "xe máy qua ngã tư"}
QA = {"query_id": "q2", "task_type": "QA", "query_vi": "biển số là gì?"}
TRAKE = {"query_id": "q3", "task_type": "TRAKE", "query_vi": "a . b",
         "event_descs": ["a", "b"]}


# --------------------------------------------------------- đọc file truy vấn

def test_doc_duoc_ca_json_va_jsonl(viet_queries):
    assert len(R._doc_queries(viet_queries([KIS, QA], "q.json"))) == 2
    assert len(R._doc_queries(viet_queries([KIS, QA], "q.jsonl"))) == 2


def test_tu_choi_task_type_sai(viet_queries):
    xau = {"query_id": "x", "task_type": "kis", "query_vi": "a"}   # chữ thường
    with pytest.raises(SystemExit, match="task_type"):
        R._doc_queries(viet_queries([xau]))


def test_tu_choi_query_id_trung(viet_queries):
    """Trùng id = hai câu ghi đè lên cùng một file nộp, mất một câu trong im lặng."""
    with pytest.raises(SystemExit, match="trùng"):
        R._doc_queries(viet_queries([KIS, dict(KIS, query_vi="khác")]))


def test_tu_choi_thieu_khoa(viet_queries):
    with pytest.raises(SystemExit, match="query_vi"):
        R._doc_queries(viet_queries([{"query_id": "a", "task_type": "KIS"}]))


def test_tu_choi_trake_it_hon_2_su_kien(viet_queries):
    """Sai N ở TRAKE = 0 điểm dù mọi frame đều đúng."""
    with pytest.raises(SystemExit, match="event_descs phải là list ít nhất 2"):
        R._doc_queries(viet_queries([dict(TRAKE, event_descs=["a"])]))


def test_trake_derive_n_events_tu_event_descs_tuong_minh(viet_queries):
    [q] = R._doc_queries(viet_queries([TRAKE]))
    assert q["n_events"] == 2


@pytest.mark.parametrize("n_events", [None, 1, True, "2"])
def test_tu_choi_trake_thieu_hoac_sai_n_events(viet_queries, n_events):
    q = {"query_id": "q3", "task_type": "TRAKE", "query_vi": "a . b"}
    if n_events is not None:
        q["n_events"] = n_events
    with pytest.raises(SystemExit, match="n_events nguyên >=2"):
        R._doc_queries(viet_queries([q]))


def test_tu_choi_trake_n_events_lech_event_descs(viet_queries):
    with pytest.raises(SystemExit, match="n_events=3.*event_descs có 2"):
        R._doc_queries(viet_queries([dict(TRAKE, n_events=3)]))


def test_tu_choi_hau_to_ten_file_khong_khop_task(viet_queries):
    q = {"query_id": "query-4-trake", "task_type": "KIS", "query_vi": "x"}
    with pytest.raises(SystemExit, match="hậu tố tên file là TRAKE"):
        R._doc_queries(viet_queries([q]))


def test_trake_parse_ra_sai_n_thi_dung_truoc_search(monkeypatch):
    import backend.tasks.trake as trake

    monkeypatch.setattr(trake, "parse_events", lambda _: ["a", "b"])
    monkeypatch.setattr(
        trake, "trake_search",
        lambda *a, **kw: pytest.fail("không được search khi số event đã sai"),
    )
    q = {
        "query_id": "query-4-trake", "task_type": "TRAKE",
        "query_vi": "nội dung chưa biết cách phân tách", "n_events": 3,
    }
    with pytest.raises(RuntimeError, match="n_events=3.*tách được 2"):
        R.giai_mot_query(q, total=5)


def test_batch_can_llm_nhung_chua_set_env_thi_dung_truoc_preflight(
    monkeypatch, tmp_path, viet_queries,
):
    monkeypatch.delenv("LLM_BACKEND", raising=False)
    monkeypatch.delenv("LLM_LOCAL_MODEL", raising=False)
    monkeypatch.setattr(
        R, "_preflight", lambda *a, **kw: pytest.fail("không được connect/preflight"),
    )
    monkeypatch.setattr(
        R, "giai_mot_query", lambda *a, **kw: pytest.fail("không được gọi pipeline"),
    )
    out = tmp_path / "ra-gate"
    monkeypatch.setattr(R.sys, "argv", [
        "run.py", "--queries", str(viet_queries([QA], "gate.json")),
        "--out", str(out),
    ])
    assert R.main() == 2
    assert "LLM_BACKEND chưa được set tường minh" in (out / R.LOG_NAME).read_text("utf-8")


def test_kis_co_query_en_khong_bi_gate_llm():
    assert R._llm_runtime_errors([dict(KIS, query_en="motorcycle at intersection")]) == []


def test_tu_choi_file_rong_va_json_hong(tmp_path):
    (tmp_path / "rong.json").write_text("[]", encoding="utf-8")
    with pytest.raises(SystemExit, match="khác rỗng"):
        R._doc_queries(tmp_path / "rong.json")

    (tmp_path / "hong.json").write_text("{khong phai json", encoding="utf-8")
    with pytest.raises(SystemExit, match="không phải JSON"):
        R._doc_queries(tmp_path / "hong.json")


# ------------------------------------------------------- vân tay của truy vấn

def test_hash_doi_khi_noi_dung_doi():
    assert R._query_hash(KIS) != R._query_hash(dict(KIS, query_vi="câu khác"))
    assert R._query_hash(KIS) != R._query_hash(dict(KIS, query_en="english"))


def test_hash_khong_doi_khi_them_truong_khong_lien_quan():
    """Thêm `split`/ghi chú không được làm mất công chạy lại cả lô."""
    assert R._query_hash(KIS) == R._query_hash(dict(KIS, split="tune", note="x"))


# ----------------------------------------------------------- vòng chạy chính

def test_chay_het_va_ghi_du_file(chay):
    ma, out, goi = chay([KIS, QA, TRAKE])
    assert ma == 0
    assert goi == ["q1", "q2", "q3"]
    for qid in ("q1", "q2", "q3"):
        assert (out / f"{qid}.csv").exists(), f"thiếu file nộp của {qid}"
    assert (out / R.CHECKPOINT_NAME).exists() and (out / R.LOG_NAME).exists()
    traces = [
        json.loads(line)
        for line in (out / R.TRACE_NAME).read_text(encoding="utf-8").splitlines()
    ]
    assert [trace["query_id"] for trace in traces] == ["q1", "q2", "q3"]
    assert all(trace["status"] == "success" for trace in traces)


def test_mot_cau_hong_thi_cac_cau_khac_van_chay(chay):
    ma, out, goi = chay([KIS, QA, TRAKE], hong_qid={"q2"})
    assert goi == ["q1", "q2", "q3"], "phải thử hết mọi câu, không dừng ở câu hỏng"
    assert not list(out.glob("*.csv")), \
        "thiếu một câu thì không được để lại submission bán phần có thể bị nộp nhầm"
    assert not list(out.glob("*.zip"))
    assert set(R.Checkpoint(out / R.CHECKPOINT_NAME).doc()) == {"q1", "q3"}, \
        "câu chạy được vẫn phải được checkpoint để lần sau chỉ làm lại câu hỏng"
    failed_trace = next(
        json.loads(line)
        for line in (out / R.TRACE_NAME).read_text(encoding="utf-8").splitlines()
        if json.loads(line)["query_id"] == "q2"
    )
    assert failed_trace["status"] == "failed"
    assert failed_trace["answers"] == []
    assert failed_trace["failure_class"] == "missing_evidence"
    assert ma == 1, "có câu hỏng thì exit code phải khác 0"


def test_log_ghi_ro_cau_nao_hong_va_hong_gi(chay):
    _, out, _ = chay([KIS, QA], hong_qid={"q2"})
    log = (out / R.LOG_NAME).read_text(encoding="utf-8")
    assert "q2" in log and "RuntimeError" in log and "giả vờ hỏng" in log
    assert "Traceback" in log, "log file phải có traceback đầy đủ để truy nguyên nhân"


def test_goi_y_lenh_chay_lai_cau_hong(chay, capsys):
    chay([KIS, QA], hong_qid={"q2"})
    assert "--only q2" in capsys.readouterr().out


# ------------------------------------------------------------- checkpoint

def test_chay_lai_thi_bo_qua_cau_da_xong(chay):
    ma, out, goi1 = chay([KIS, QA])
    assert ma == 0 and goi1 == ["q1", "q2"]

    ma2, out2, goi2 = chay([KIS, QA])
    assert ma2 == 0
    assert goi2 == [], "câu đã xong không được chạy lại"
    assert (out2 / "q1.csv").exists() and (out2 / "q2.csv").exists(), \
        "lần chạy tiếp vẫn phải ghi ĐỦ bộ file, kể cả câu xong từ lần trước"


def test_chay_lai_chi_lam_cau_hong_lan_truoc(chay):
    """Câu hỏng KHÔNG vào checkpoint — lỗi thường là DB chập chờn, đáng thử lại."""
    ma, _, _ = chay([KIS, QA], hong_qid={"q2"})
    assert ma == 1
    ma2, out2, goi2 = chay([KIS, QA])
    assert goi2 == ["q2"] and ma2 == 0
    assert (out2 / "q2.csv").exists()


def test_doi_de_thi_checkpoint_het_han(chay):
    """Cửa tử của checkpoint: nộp câu trả lời của đề CŨ dưới query_id mới."""
    chay([KIS, QA])
    _, _, goi2 = chay([dict(KIS, query_vi="ĐỀ ĐÃ SỬA"), QA])
    assert goi2 == ["q1"], "câu bị sửa đề phải chạy lại, câu không đổi thì không"


def test_doi_model_thi_checkpoint_het_han(chay, monkeypatch):
    """Bắt lỗi resume trộn answers sinh bởi hai model trong cùng checkpoint."""
    monkeypatch.setenv("LLM_LOCAL_MODEL", "model-a")
    chay([KIS, QA])
    monkeypatch.setenv("LLM_LOCAL_MODEL", "model-b")
    _, _, goi2 = chay([KIS, QA])
    assert goi2 == ["q1", "q2"]


def test_fresh_bo_qua_checkpoint(chay):
    chay([KIS, QA])
    _, _, goi2 = chay([KIS, QA], extra_args=["--fresh"])
    assert goi2 == ["q1", "q2"]


def test_checkpoint_ghi_ngay_sau_moi_cau(chay, monkeypatch, tmp_path, viet_queries, video):
    """Chết giữa chừng KHÔNG được mất câu đã xong — kiểm bằng cách chết thật."""
    vid, n_frames = video
    qs = [KIS, QA, TRAKE]

    def _gia(q, tong):
        if q["query_id"] == "q3":
            raise KeyboardInterrupt
        return _answers(vid, n_frames, tong), {}

    monkeypatch.setattr(R, "giai_mot_query", _gia)
    monkeypatch.setattr(R, "_preflight", lambda log, bo_qua: True)
    out_dir = tmp_path / "ra"
    monkeypatch.setattr(R.sys, "argv", [
        "run.py", "--queries", str(viet_queries(qs)), "--out", str(out_dir),
        "--answers", "5"])
    R.main()

    ck = R.Checkpoint(out_dir / R.CHECKPOINT_NAME).doc()
    assert set(ck) == {"q1", "q2"}, "hai câu xong trước lúc chết phải còn nguyên"


def test_checkpoint_dong_hong_khong_lam_sap(tmp_path):
    p = tmp_path / R.CHECKPOINT_NAME
    p.write_text('{"query_id": "a", "answers": []}\n{khong phai json\n',
                 encoding="utf-8")
    assert set(R.Checkpoint(p).doc()) == {"a"}


def test_checkpoint_giu_answer_text_cua_QA(chay):
    """answer_text phải sống sót qua checkpoint — mất nó là Q&A 0 điểm."""
    _, out, _ = chay([QA])
    rec = R.Checkpoint(out / R.CHECKPOINT_NAME).doc()["q2"]
    assert rec["answer_text"] == "5"
    assert all(a["answer_text"] == "5" for a in rec["answers"])

    # và lần chạy tiếp (đọc từ checkpoint) vẫn ghi answer vào file nộp
    _, out2, _ = chay([QA])
    assert ',"5"' in (out2 / "q2.csv").read_text(encoding="utf-8")


# ------------------------------------------------------------------- --only

def test_only_chi_chay_cau_duoc_chon(chay):
    ma, out, goi = chay([KIS, QA, TRAKE], extra_args=["--only", "q2,q3"])
    assert goi == ["q2", "q3"]
    assert ma == 1
    assert not list(out.glob("*.csv")), \
        "checkpoint thiếu q1 thì không được xuất một submission subset dễ nộp nhầm"


def test_only_rerun_sau_full_van_zip_du_toan_bo_query(chay):
    ma1, _, _ = chay([KIS, QA, TRAKE])
    assert ma1 == 0

    # Chỉ q2 đổi nội dung nên checkpoint q2 hết hạn; q1/q3 phải lấy lại từ
    # checkpoint rồi cùng xuất vào ZIP mới, không bị --only làm biến mất.
    qa_moi = dict(QA, query_vi="biển số xe là gì?")
    ma2, out, goi2 = chay(
        [KIS, qa_moi, TRAKE], extra_args=["--only", "q2", "--zip"]
    )
    assert ma2 == 0 and goi2 == ["q2"]
    zip_path = next(out.glob("*.zip"))
    with zipfile.ZipFile(zip_path) as z:
        assert set(z.namelist()) == {
            "submission/q1.csv", "submission/q2.csv", "submission/q3.csv",
        }


def test_only_voi_query_id_khong_ton_tai_thi_bao_loi(chay):
    ma, _, goi = chay([KIS], extra_args=["--only", "khong_co"])
    assert ma == 2 and goi == []


def test_only_id_la_dong_log_truoc_khi_return(monkeypatch, tmp_path, viet_queries):
    """Main được gọi lặp trong process dài không được giữ file handle của Log."""
    opened = []
    real_log = R.Log

    class TrackingLog(real_log):
        def __init__(self, path):
            super().__init__(path)
            opened.append(self)

    monkeypatch.setattr(R, "Log", TrackingLog)
    out = tmp_path / "only-invalid"
    monkeypatch.setattr(R.sys, "argv", [
        "run.py", "--queries", str(viet_queries([KIS])), "--out", str(out),
        "--only", "khong_co",
    ])

    assert R.main() == 2
    assert len(opened) == 1
    assert opened[0].f.closed is True


# --------------------------------------------------------------------- --zip

def test_zip_dung_chuan_btc(chay):
    ma, out, _ = chay([KIS, QA], extra_args=["--zip"])
    assert ma == 0
    assert list(out.glob("*.zip")), "không thấy file zip nào"


def test_release_rehearsal_tao_receipt_khi_promotion_va_batch_sach(chay, tmp_path):
    audit = tmp_path / "promotion.json"
    payload = {
        "status": "ELIGIBLE", "eligible": True,
        "scorer_contract": "btc-final-score-v1",
        "current_runtime_fingerprint": R.build_runtime_fingerprint(),
        "scorer_policy": "semantic",
        "scorer_source_sha256": scorer_contract_sha256(),
        "input_sha256": {
            "holdout_manifest": "1" * 64,
            "regression_manifest": "2" * 64,
            "holdout_scores": "3" * 64,
            "regression_baseline": "4" * 64,
            "regression_current": "5" * 64,
        },
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload["audit_sha256"] = hashlib.sha256(canonical.encode()).hexdigest()
    audit.write_text(json.dumps(payload), encoding="utf-8")
    ma, out, _ = chay([KIS], extra_args=[
        "--zip", "--release-rehearsal", "--promotion-audit", str(audit),
    ])
    assert ma == 0
    assert (out / "submission.zip").is_file()
    receipt = json.loads((out / "submission.receipt.json").read_text(encoding="utf-8"))
    assert receipt["promotion_audit"]["status"] == "ELIGIBLE"
    assert receipt["runtime_fingerprint"]


def test_release_rehearsal_promotion_blocked_khong_tao_zip(chay, tmp_path):
    audit = tmp_path / "promotion.json"
    audit.write_text(json.dumps({
        "status": "BLOCKED", "eligible": False,
    }), encoding="utf-8")
    ma, out, _ = chay([KIS], extra_args=[
        "--zip", "--release-rehearsal", "--promotion-audit", str(audit),
    ])
    assert ma == 1
    assert not list(out.glob("*.zip"))
    assert not list(out.glob("*.receipt.json"))


# ------------------------------------------------------------- exit code

def test_khong_cau_nao_thanh_cong_thi_exit_1(chay):
    ma, out, _ = chay([KIS, QA], hong_qid={"q1", "q2"})
    assert ma == 1
    assert not list(out.glob("*.csv"))


def test_canh_bao_khi_khong_co_bang_chung_that(chay, monkeypatch, tmp_path,
                                               viet_queries, video, capsys):
    """File đủ 100 dòng mà không dòng nào có bằng chứng = báo xanh giả nguy hiểm nhất."""
    vid, n_frames = video

    monkeypatch.setattr(R, "giai_mot_query", lambda q, tong: (
        [Answer(video_id=vid, frame_ids=(i,), keyframe_id=None) for i in range(tong)], {}))
    monkeypatch.setattr(R, "_preflight", lambda log, bo_qua: True)
    out_dir = tmp_path / "ra"
    monkeypatch.setattr(R.sys, "argv", [
        "run.py", "--queries", str(viet_queries([KIS])), "--out", str(out_dir),
        "--answers", "5"])
    R.main()
    assert "KHÔNG có dòng nào mang bằng chứng thật" in capsys.readouterr().out


# ------------------------------------------------------------ thanh tiến độ

def test_thanh_tien_do_khong_no_khi_rong():
    bar = R.ThanhTienDo(0)
    bar.cap_nhat("x")
    bar.xuong_dong()


def test_thanh_tien_do_chay_het_100_phan_tram(capsys):
    bar = R.ThanhTienDo(3)
    for _ in range(3):
        bar.cap_nhat("q")
    assert "3/3" in capsys.readouterr().err


# --------------------------------------------------------------- preflight

def test_preflight_chan_lo_khi_he_thong_chet(monkeypatch, tmp_path, viet_queries):
    """Hỏng cả lô vì CÙNG một nguyên nhân thì phải phát hiện MỘT lần, ở đầu.

    Đo thật 19/08: Milvus rỗng → mỗi câu vẫn nạp CLIP + search rồi mới hỏng,
    29s cho câu đầu và lặp y hệt cho từng câu còn lại.
    """
    import backend.api.health as health

    monkeypatch.setattr(health, "deep_check", lambda *a, **kw: {
        "status": "down", "latency_ms": 1.0, "import_ms": 0.0,
        "checks": [{"name": "milvus", "status": "down", "latency_ms": 1.0,
                    "critical": True, "detail": "collection RỖNG"}]})
    monkeypatch.setattr(R, "giai_mot_query",
                        lambda q, tong: pytest.fail("không được chạy query nào"))
    out_dir = tmp_path / "ra"
    monkeypatch.setattr(R.sys, "argv", ["run.py", "--queries",
                                        str(viet_queries([KIS])), "--out", str(out_dir)])
    assert R.main() == 1
    assert not list(out_dir.glob("*.csv"))


def test_skip_health_ep_chay_duoc(monkeypatch, tmp_path, viet_queries, video):
    """Vẫn phải có đường ép chạy — deep check sai còn tệ hơn không có nó."""
    import backend.api.health as health

    vid, n_frames = video
    monkeypatch.setattr(health, "deep_check",
                        lambda *a, **kw: pytest.fail("--skip-health mà vẫn gọi deep check"))
    monkeypatch.setattr(R, "giai_mot_query",
                        lambda q, tong: (_answers(vid, n_frames, tong), {}))
    out_dir = tmp_path / "ra"
    monkeypatch.setattr(R.sys, "argv", ["run.py", "--queries", str(viet_queries([KIS])),
                                        "--out", str(out_dir), "--answers", "5",
                                        "--skip-health"])
    assert R.main() == 0


def test_preflight_hong_thi_van_chay_tiep(monkeypatch, tmp_path, viet_queries, video):
    """Deep check là thứ PHỤ TRỢ — nó hỏng không được chặn đường nộp."""
    import backend.api.health as health

    vid, n_frames = video

    def _no(*a, **kw):
        raise RuntimeError("deep check tự hỏng")

    monkeypatch.setattr(health, "deep_check", _no)
    monkeypatch.setattr(R, "giai_mot_query",
                        lambda q, tong: (_answers(vid, n_frames, tong), {}))
    out_dir = tmp_path / "ra"
    monkeypatch.setattr(R.sys, "argv", ["run.py", "--queries", str(viet_queries([KIS])),
                                        "--out", str(out_dir), "--answers", "5"])
    assert R.main() == 0
