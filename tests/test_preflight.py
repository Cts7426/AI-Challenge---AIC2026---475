# tests/test_preflight.py — D6.1: preflight check
#
# Trọng tâm: MỖI MỤC KIỂM PHẢI FAIL ĐƯỢC.
#
# Một preflight không bao giờ đỏ thì tệ hơn không có preflight — nó cấp một cảm
# giác an toàn mà không kiểm gì cả, đúng lúc người vận hành mệt nhất và tin nó
# nhất. Nên phần lớn test dưới đây làm HỎNG có chủ đích một thứ rồi khẳng định
# mục tương ứng chuyển sang KHÔNG ĐẠT.
#
# Hai bất biến khác cũng phải giữ:
#   · SKIP không bao giờ được đếm thành PASS (mục cần Docker mà máy không có
#     Docker phải hiện ra là CHƯA KIỂM)
#   · một mục ném ngoại lệ KHÔNG được giết cả script — các mục sau vẫn phải chạy
#
# Dữ liệu: parquet THẬT của Data Factory, giống test_allocator.py. Preflight mà
# chỉ chạy được trên mock thì không chứng minh được gì về tối thi.

from __future__ import annotations

from scripts import preflight_check as pf


# ------------------------------------------------ khung: ba trạng thái rạch ròi

def test_three_distinct_statuses():
    """PASS / FAIL / SKIP là ba chuỗi phân biệt — không cái nào trùng cái nào."""
    assert len({pf.PASS, pf.FAIL, pf.SKIP}) == 3


def test_none_becomes_skip():
    """`None` = không kết luận được → SKIP, KHÔNG được thành PASS.

    Đây là luật quan trọng nhất của cả khung: mọi mục thiếu điều kiện chạy đều
    đi qua đường này. Gộp nhầm vào PASS là biến 'chưa kiểm' thành màu xanh.
    """
    check = pf.Check("X", "thử", lambda: (None, "chưa đủ điều kiện"))
    assert pf.run_check(check, quick=False).status == pf.SKIP


def test_false_becomes_fail():
    check = pf.Check("X", "thử", lambda: (False, "sai rồi"))
    result = pf.run_check(check, quick=False)
    assert result.status == pf.FAIL
    assert "sai rồi" in result.detail


def test_exception_does_not_kill_script():
    """Mục ném ngoại lệ → FAIL kèm tên lỗi, KHÔNG được ném ra ngoài.

    Vì sao: chạy hết một lượt rồi đưa TOÀN BỘ danh sách việc phải sửa. Gãy ở mục
    đầu thì người vận hành sửa xong lại phát hiện lỗi thứ hai, sửa xong lại lỗi
    thứ ba — ba vòng như vậy lúc 2 giờ sáng là hết đêm.
    """
    def boom():
        raise ValueError("hỏng ngầm")

    result = pf.run_check(pf.Check("X", "thử", boom), quick=False)
    assert result.status == pf.FAIL
    assert "ValueError" in result.detail


def test_connection_error_on_infra_check_is_skip():
    """Hạ tầng chưa lên ≠ code hỏng. ConnectionError ở mục `needs_infra` → SKIP."""
    def cannot_connect():
        raise ConnectionError("Không kết nối được Milvus tại localhost:19530")

    check = pf.Check("B", "thử", cannot_connect, needs_infra=True)
    assert pf.run_check(check, quick=False).status == pf.SKIP


def test_connection_error_on_normal_check_is_fail():
    """Nhưng mục KHÔNG cần hạ tầng mà ném ConnectionError thì đó là lỗi thật."""
    def boom():
        raise ConnectionError("lạ")

    check = pf.Check("C", "thử", boom, needs_infra=False)
    assert pf.run_check(check, quick=False).status == pf.FAIL


def test_quick_skips_infra_checks_without_running_them():
    called = []
    check = pf.Check("B", "thử", lambda: (called.append(1), (True, ""))[1],
                     needs_infra=True)
    assert pf.run_check(check, quick=True).status == pf.SKIP
    assert called == [], "--quick phải bỏ qua HẲN, không được chạy rồi mới bỏ kết quả"


def test_release_turns_required_skip_into_fail():
    check = pf.Check("C", "ảnh Q&A", lambda: (None, "chưa có ảnh"))
    result = pf.run_check(check, quick=False, profile="release")
    assert result.status == pf.FAIL
    assert "release bắt buộc" in result.detail


def test_release_keeps_optional_skip_as_skip():
    check = pf.Check(
        "B", "API UI", lambda: (None, "không chạy UI"), required_in_release=False,
    )
    assert pf.run_check(check, quick=False, profile="release").status == pf.SKIP


# ------------------------------------------------------- checklist: cấu trúc

def test_checklist_has_no_duplicate_names():
    """Trùng (nhóm, tên) thì bảng in ra có hai dòng giống hệt — không truy được dòng nào hỏng."""
    names = [(c.group, c.name) for c in pf.CHECKLIST]
    assert len(names) == len(set(names))


def test_every_check_honours_the_contract():
    """Mọi mục phải trả đúng hợp đồng `(bool | None, str)` — không mục nào lệch kiểu."""
    for check in pf.CHECKLIST:
        result = pf.run_check(check, quick=False)
        assert result.status in (pf.PASS, pf.FAIL, pf.SKIP), check.name
        assert isinstance(result.detail, str), check.name


# ------------------------- B. hạ tầng: "chưa bật" phải khác "bật mà hỏng"

def test_elasticsearch_down_is_skip(monkeypatch):
    """Cổng 9200 không ai nghe → CHƯA KIỂM ĐƯỢC, không phải hỏng."""
    monkeypatch.setattr(pf, "_port_responds", lambda url, timeout=3.0: False)
    ok, detail = pf.check_elasticsearch()
    assert ok is None
    assert "docker compose" in detail


def test_elasticsearch_alive_but_client_rejected_is_fail(monkeypatch):
    """ES sống nhưng client không dùng được → FAIL, tuyệt đối không được SKIP.

    Đo thật 19/08: server 8.13.4 + client python 9.5.0 → cả 4 nhánh ES chết câm,
    `search()` vẫn chạy bằng mỗi nhánh vector và không báo gì. Preflight mà xếp
    ca này vào 'chưa kiểm' là nhìn thẳng vào hệ thống hỏng rồi im lặng.
    """
    import backend.indexing.es_client as es_client

    monkeypatch.setattr(pf, "_port_responds", lambda url, timeout=3.0: True)

    def rejected(*args, **kwargs):
        raise ConnectionError("Elasticsearch ĐANG CHẠY nhưng từ chối client: lệch phiên bản.")

    monkeypatch.setattr(es_client, "connect", rejected)
    ok, detail = pf.check_elasticsearch()
    assert ok is False, "phải là KHÔNG ĐẠT, không phải BỎ QUA"
    assert "đang sống" in detail


def test_port_responds_treats_http_error_as_alive(monkeypatch):
    """4xx/5xx vẫn là 'có ai đó đang nghe' — dịch vụ sống mà từ chối ta."""
    import urllib.error

    def http_401(*args, **kwargs):
        raise urllib.error.HTTPError("http://x", 401, "Unauthorized", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", http_401)
    assert pf._port_responds("http://x") is True


# ------------------------------------------------- C. dữ liệu: phải fail được

def test_parquet_missing_file_is_fail(monkeypatch, tmp_path):
    """Thiếu một parquet lõi → đỏ, kèm tên người phải đi hỏi."""
    monkeypatch.setattr(pf, "REPO_ROOT", tmp_path)  # thư mục rỗng, không có data/derived
    ok, detail = pf.check_parquet()
    assert ok is False
    assert "THIẾU" in detail
    assert "Thạch" in detail, "task hiện tại chỉ có Thạch vận hành"


def test_frame_assets_missing_is_skip_in_development_but_blocked_in_release(
    monkeypatch, tmp_path,
):
    import data.config.frame_assets as config

    monkeypatch.setattr(config, "RAW_KEYFRAMES_DIR", tmp_path / "raw")
    monkeypatch.setattr(config, "DERIVED_KEYFRAMES_DIR", tmp_path / "derived")
    ok, detail = pf.check_frame_assets()
    assert ok is None and "ảnh phủ 0/" in detail
    check = pf.Check("C", "ảnh Q&A/UI", pf.check_frame_assets)
    assert pf.run_check(check, quick=False, profile="release").status == pf.FAIL


def test_missing_meta_json_is_skip_not_fail(monkeypatch, tmp_path):
    """Thiếu .meta.json là NỢ (bất biến 8), không phải lỗi chặn nộp."""
    derived = tmp_path / "data" / "derived"
    derived.mkdir(parents=True)
    for name in pf.REQUIRED_PARQUET:
        (derived / name).write_bytes(b"x")  # có file, không có meta
    monkeypatch.setattr(pf, "REPO_ROOT", tmp_path)
    ok, detail = pf.check_meta_json()
    assert ok is None
    assert "meta.json" in detail


def test_frame_map_has_both_key_formats():
    """Trên dữ liệu THẬT: frame_map phải tra được cả `#k` lẫn dạng 1fps.

    Mất một dạng thì allocator lặng lẽ mất mức ưu tiên ① — không lỗi, chỉ kém đi.
    """
    ok, detail = pf.check_frame_map()
    assert ok is True, detail


def test_video_info_readable():
    ok, detail = pf.check_video_info()
    assert ok is True, detail


# ----------------------------------------- E. đường nộp: chạy thật, dữ liệu thật

def test_submission_path_all_three_task_types():
    """Diễn tập nộp đầy đủ: allocate → validate → .zip → validate_zip.

    Mục quan trọng nhất của D6.1 — nó đi đúng chuỗi mà tối thi sẽ đi.
    """
    ok, detail = pf.check_submission_path()
    assert ok is True, detail
    assert "3 dạng bài" in detail


# ------------------------------------------------------- F. độ trễ: ngân sách

def test_latency_budget_is_30s():
    """CLAUDE.md mục 2 luật 2: ≤ 30s từ lúc gõ query tới lúc có kết quả."""
    assert pf.LATENCY_BUDGET_S == 30.0


def test_latency_over_budget_is_fail(monkeypatch):
    """Search chậm hơn ngân sách → ĐỎ, không phải cảnh báo.

    Một pipeline 45s không 'hơi chậm' — nó là câu không kịp làm, tức 0 điểm.
    """
    import time

    import backend.retrieval.search as search_module

    def slow(*args, **kwargs):
        time.sleep(0.05)
        return [{"shot_id": "x"}]

    monkeypatch.setattr(search_module, "search", slow)
    monkeypatch.setattr(pf, "LATENCY_BUDGET_S", 0.01)
    ok, detail = pf.check_latency()
    assert ok is False
    assert "ngân sách" in detail


def test_latency_zero_results_is_fail(monkeypatch):
    """0 kết quả cũng là hỏng: nhánh nào cũng câm thì bài nộp không có gì để xếp hạng."""
    import backend.retrieval.search as search_module

    monkeypatch.setattr(search_module, "search", lambda *a, **kw: [])
    ok, detail = pf.check_latency()
    assert ok is False
    assert "0 kết quả" in detail


# --------------------------------------------- G. cấu hình: phải fail được thật

def test_slot_budget_still_fills_100_when_table_under_declares(monkeypatch):
    """Bảng khai thiếu (59 slot) nhưng `budget_per_shot()` phải bù cho đủ 100.

    Mục G canh đúng chuyện đó — không canh việc bảng khai bao nhiêu. Bất biến số
    một của D3.1 là bài nộp có đủ 100 dòng, dù bảng ngân sách viết thế nào.
    """
    import data.config.slot_budget as slot_budget

    monkeypatch.setattr(slot_budget, "SLOT_BUDGET", [(3, 8), (7, 5)])  # 24 + 35 = 59
    ok, detail = pf.check_slot_budget()
    assert ok is True, detail


def test_slot_budget_fails_when_allocation_is_short(monkeypatch):
    """Nếu `budget_per_shot()` trả sai tổng thì mục G phải bắt được."""
    import data.config.slot_budget as slot_budget

    monkeypatch.setattr(slot_budget, "budget_per_shot",
                        lambda n, table=None, total=100: [1] * n)
    ok, detail = pf.check_slot_budget()
    assert ok is False
    assert "tổng slot" in detail


def test_scoring_formula_matches_btc_example():
    """Ví dụ CÓ ĐÁP SỐ của BTC (mục 2.2): 0.5 / 0.8 / 0.6 → Final = 0.74."""
    ok, detail = pf.check_scoring_formula()
    assert ok is True, detail
    assert "0.74" in detail


def test_scoring_formula_fails_when_thresholds_drift(monkeypatch):
    """Sửa nhầm K_THRESHOLDS → mọi bảng điểm dev sai lệch mà không gì crash."""
    import data.config.scoring as scoring

    monkeypatch.setattr(scoring, "K_THRESHOLDS", (1, 5, 10, 50, 100))
    ok, detail = pf.check_scoring_formula()
    assert ok is False
    assert "K_THRESHOLDS" in detail or "Final" in detail


def test_submit_format_fails_when_not_100_rows(monkeypatch):
    """BTC cho tối đa 100 câu trả lời — hằng lệch là nộp thiếu/thừa."""
    import data.config.submit_format as submit_format

    monkeypatch.setattr(submit_format, "ANSWERS_PER_QUERY", 50)
    ok, detail = pf.check_submit_format()
    assert ok is False
    assert "100" in detail


def test_submit_format_fails_when_extension_changes(monkeypatch):
    import data.config.submit_format as submit_format

    monkeypatch.setattr(submit_format, "SUBMIT_EXT", "json")
    ok, _ = pf.check_submit_format()
    assert ok is False


# ------------------------------------------------------------ main(): exit code

def test_main_returns_0_when_nothing_failed(monkeypatch, capsys):
    monkeypatch.setattr(pf, "CHECKLIST", [
        pf.Check("X", "ổn", lambda: (True, "ok")),
        pf.Check("X", "chưa kiểm", lambda: (None, "thiếu Docker")),
    ])
    monkeypatch.setattr("sys.argv", ["preflight_check.py"])
    assert pf.main() == 0
    out = capsys.readouterr().out
    assert "CHƯA KIỂM" in out, "mục SKIP phải hiện ra dù exit code là 0"


def test_main_returns_1_when_something_failed(monkeypatch, capsys):
    monkeypatch.setattr(pf, "CHECKLIST", [pf.Check("X", "hỏng", lambda: (False, "vỡ"))])
    monkeypatch.setattr("sys.argv", ["preflight_check.py"])
    assert pf.main() == 1
    assert "PHẢI SỬA TRƯỚC KHI NỘP" in capsys.readouterr().out


def test_main_json_keeps_exit_code(monkeypatch, capsys):
    """Chế độ --json cho E6.1 phải giữ nguyên exit code, không chỉ in đẹp."""
    import json

    monkeypatch.setattr(pf, "CHECKLIST", [pf.Check("X", "hỏng", lambda: (False, "vỡ"))])
    monkeypatch.setattr("sys.argv", ["preflight_check.py", "--json"])
    assert pf.main() == 1
    report = json.loads(capsys.readouterr().out)
    assert report["failed"] == 1 and report["passed"] == 0
