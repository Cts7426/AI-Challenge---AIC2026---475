"""H01A: lỗi lựa chọn runtime phải lộ trước cache/provider/DB I/O."""
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize("alpha", [-0.1, 1.5, float("nan"), float("inf"), "bad"])
def test_invalid_alpha_fails_before_translation(monkeypatch, alpha):
    search = importlib.import_module("backend.retrieval.search")
    translation = importlib.import_module("backend.retrieval.text_query")
    calls = []
    def translate(query):
        calls.append(query)
        return "translated"
    monkeypatch.setattr(translation, "translate_to_english", translate)
    with pytest.raises(ValueError):
        search._search_core("query", branches={name: False for name in search.BRANCHES},
                            video_prior_alpha=alpha)
    assert calls == [], "alpha sai phải dừng trước cả dịch query"


def test_preflight_import_preserves_environment(tmp_path):
    (tmp_path / ".env").write_text("LLM_BACKEND=api\nLLM_API_MODEL=not-selected\n", encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))
    env.pop("LLM_BACKEND", None)
    env.pop("LLM_API_MODEL", None)
    script = "import os,json; from scripts.preflight_check import check_core_libs; before=dict(os.environ); check_core_libs(); print(json.dumps(dict(os.environ)==before))"
    result = subprocess.run([sys.executable, "-c", script], cwd=tmp_path, env=env,
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) is True


def test_dotenv_loads_secret_without_selecting_runtime(monkeypatch, tmp_path):
    from backend.llm import adapter
    monkeypatch.setattr(adapter, "REPO_ROOT", tmp_path)
    for key in ("LLM_BACKEND", "LLM_API_MODEL", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    (tmp_path / ".env").write_text("LLM_BACKEND=api\nLLM_API_MODEL=not-selected\nANTHROPIC_API_KEY=test-secret\n", encoding="utf-8")
    adapter._nap_dotenv()
    assert os.environ.get("LLM_BACKEND") is None
    assert os.environ.get("LLM_API_MODEL") is None
    assert os.environ["ANTHROPIC_API_KEY"] == "test-secret"


@pytest.mark.parametrize("backend,model", [(None, None), ("api", None), ("api", " ")])
def test_llm_requires_explicit_selection_before_cache(monkeypatch, backend, model):
    from backend.llm import adapter
    for key, value in (("LLM_BACKEND", backend), ("LLM_API_MODEL", model)):
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    def cache_must_not_run(key):
        pytest.fail("runtime chưa chọn mà đã đọc cache")
    monkeypatch.setattr(adapter, "_cache_get", cache_must_not_run)
    with pytest.raises(ValueError):
        adapter.llm("query")


def test_preflight_reports_unselected_model(monkeypatch):
    from scripts import preflight_check
    monkeypatch.delenv("LLM_BACKEND", raising=False)
    ok, detail = preflight_check.check_qa_runtime()
    assert ok is False
    assert "LLM_BACKEND" in detail


def test_search_does_not_hide_unselected_runtime_as_translation_fallback(monkeypatch):
    search = importlib.import_module("backend.retrieval.search")
    monkeypatch.delenv("LLM_BACKEND", raising=False)
    with pytest.raises(ValueError):
        search.search("query", branches={name: False for name in search.BRANCHES})


def test_selfcheck_does_not_report_default_backend_as_selected(monkeypatch):
    from scripts import selfcheck
    monkeypatch.delenv("LLM_BACKEND", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy-present")
    assert selfcheck.check_llm_backend().ok is False


def test_llm_cannot_override_operator_model_inside_run(monkeypatch):
    from backend.llm import adapter
    monkeypatch.setenv("LLM_BACKEND", "api")
    monkeypatch.setenv("LLM_API_MODEL", "selected-model")
    monkeypatch.setattr(adapter, "_cache_get", lambda key: pytest.fail("model khác chưa bị chặn trước cache"))
    with pytest.raises(ValueError, match="model"):
        adapter.llm("query", model="different-model")


@pytest.mark.parametrize("use_cache,cached", [(True, None), (False, ["cached"]), (True, ["invalid"])])
def test_cache_only_never_dispatches_provider_on_miss(monkeypatch, use_cache, cached):
    """Cache thiếu/tắt/hỏng đều phải dừng trước API, giữ ngân sách mới bằng 0."""
    from backend.llm import adapter
    monkeypatch.setenv("LLM_BACKEND", "api")
    monkeypatch.setenv("LLM_API_MODEL", "claude-sonnet-5")
    monkeypatch.setenv("LLM_CACHE_ONLY", "1")
    monkeypatch.setattr(adapter, "_usage", dict(adapter.usage_report()))
    before = adapter.usage_report().get("cache_only_misses", 0)
    monkeypatch.setattr(adapter, "_cache_get", lambda key: cached)
    monkeypatch.setattr(adapter, "_mot_lan", lambda *a: pytest.fail("cache-only đã gọi provider"))
    with pytest.raises(RuntimeError, match="cache-only"):
        adapter.llm("query", use_cache=use_cache, validate=lambda text: "bad" if text == "invalid" else None)
    assert adapter.usage_report()["cache_only_misses"] == before + 1


def test_cache_only_returns_same_cached_output(monkeypatch):
    from backend.llm import adapter
    monkeypatch.setenv("LLM_BACKEND", "api")
    monkeypatch.setenv("LLM_API_MODEL", "claude-sonnet-5")
    monkeypatch.setenv("LLM_CACHE_ONLY", "1")
    monkeypatch.setattr(adapter, "_cache_get", lambda key: ["original answer"])
    monkeypatch.setattr(adapter, "_mot_lan", lambda *a: pytest.fail("cache hit đã gọi provider"))
    assert adapter.llm("query") == "original answer"


def test_cache_only_policy_changes_runtime_identity(monkeypatch):
    from backend.tasks.runner import runtime_fingerprint
    from data.config.experiment import RUNTIME_ENV_KEYS
    monkeypatch.setenv("LLM_CACHE_ONLY", "0")
    regular = runtime_fingerprint()
    monkeypatch.setenv("LLM_CACHE_ONLY", "1")
    assert runtime_fingerprint() != regular
    assert "LLM_CACHE_ONLY" in RUNTIME_ENV_KEYS
