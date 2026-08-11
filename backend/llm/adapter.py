# backend/llm/adapter.py — C0.1: ADAPTER llm(), điểm gọi LLM DUY NHẤT
#
# Nguyên tắc sống còn (CLAUDE.md bất biến 1): MỌI lần gọi LLM/VLM trong repo đi
# qua llm() ở đây. Không import SDK nhà cung cấp ở bất kỳ file nào khác — đổi
# backend chỉ sửa một dòng config, không phải lùng sửa từng chỗ gọi rải rác.
#
# ===== Cấu hình bằng biến môi trường =====
#   LLM_BACKEND      = "api" (mặc định) | "local"
#   LLM_API_MODEL    = model khi dùng API (mặc định claude-opus-5)
#   ANTHROPIC_API_KEY= bắt buộc khi LLM_BACKEND=api
#   LLM_LOCAL_MODEL  = model Ollama khi chạy offline (mặc định qwen2.5:7b-instruct)
#   LLM_LOCAL_URL    = địa chỉ Ollama (mặc định http://localhost:11434)
#   LLM_CACHE_DIR    = thư mục cache (mặc định data/cache/llm)
#   LLM_NO_CACHE=1   → tắt cache (khi muốn đo độ trễ thật)
#
# ===== Bốn thứ file này lo, để chỗ gọi khỏi phải lo =====
# 1. CACHE trên đĩa theo hash(prompt+ảnh+model+tham số): cùng một truy vấn hỏi
#    lại là 0 đồng, 0 giây. Lúc thi người thao tác hay gõ lại query gần giống —
#    và lúc dev thì chạy đi chạy lại cùng một câu hàng chục lần.
# 2. ĐẾM TOKEN + CHI PHÍ tích luỹ: không đo thì không biết job OCR/QA đốt bao nhiêu.
# 3. JSON CÓ SCHEMA: dùng structured outputs của API (ép đúng schema ngay từ
#    phía server) thay vì bắt LLM "nhớ" trả JSON rồi tự parse — cách cũ hỏng ngầm.
# 4. RETRY: lỗi mạng/429/5xx đã được SDK tự retry (backoff mũ). Ở đây chỉ retry
#    thêm cho trường hợp output JSON hỏng — thứ SDK không biết là lỗi.
#
# ⚠️ `temperature` KHÔNG gửi lên API được nữa: Claude Opus 5 / Fable 5 / Sonnet 5
# bỏ hẳn temperature/top_p/top_k, gửi lên là lỗi 400. Tham số vẫn còn trong chữ
# ký hàm cho khớp BUILD_TASKS C0.1, nhưng bị BỎ QUA ở backend api (có cảnh báo).
# Cần đa dạng đầu ra thì dùng n>1 + yêu cầu trong prompt, không dùng temperature.

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_API_MODEL = "claude-opus-5"
DEFAULT_LOCAL_MODEL = "qwen2.5:7b-instruct"

# Giá USD / 1 triệu token (bảng giá Anthropic). Chỉ để ƯỚC LƯỢNG chi phí —
# sai số vài % không quan trọng, biết đang đốt $0.2 hay $200 mới quan trọng.
PRICING = {
    "claude-opus-5": (5.0, 25.0),
    "claude-fable-5": (10.0, 50.0),
    "claude-sonnet-5": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}

# Mặc định effort thấp: việc của llm() trong đường ONLINE là dịch/mở rộng câu
# ngắn — không cần suy nghĩ sâu, và ngân sách chỉ 30s cho cả pipeline.
# Task nào cần nghĩ kỹ (Q&A suy luận) thì tự truyền effort="high".
DEFAULT_EFFORT = "low"
DEFAULT_MAX_TOKENS = 2048

_api_client = None
_usage = {"calls": 0, "cache_hits": 0, "input_tokens": 0, "output_tokens": 0, "usd": 0.0}


# ----------------------------------------------------------------------- cache

def _cache_dir() -> Path:
    return Path(os.environ.get("LLM_CACHE_DIR", REPO_ROOT / "data" / "cache" / "llm"))


def _cache_key(payload: dict) -> str:
    """Hash ổn định của toàn bộ thứ ảnh hưởng tới câu trả lời.

    sort_keys=True: dict trong Python giữ thứ tự chèn, không sort thì cùng một
    yêu cầu lại ra hai hash khác nhau → cache không bao giờ trúng.
    """
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _cache_get(key: str) -> list[str] | None:
    if os.environ.get("LLM_NO_CACHE"):
        return None
    path = _cache_dir() / f"{key}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))["output"]
    except Exception:
        return None  # cache hỏng thì coi như không có, không làm sập chỗ gọi


def _cache_put(key: str, output: list[str], meta: dict) -> None:
    if os.environ.get("LLM_NO_CACHE"):
        return
    d = _cache_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{key}.json").write_text(
        json.dumps({"output": output, **meta}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ------------------------------------------------------------ đếm token & tiền

def _ghi_nhan(model: str, usage) -> None:
    """Cộng dồn token + ước lượng chi phí sau mỗi lần gọi API thật."""
    vao = getattr(usage, "input_tokens", 0) or 0
    ra = getattr(usage, "output_tokens", 0) or 0
    doc_cache = getattr(usage, "cache_read_input_tokens", 0) or 0
    gia_vao, gia_ra = PRICING.get(model, (0.0, 0.0))
    _usage["input_tokens"] += vao + doc_cache
    _usage["output_tokens"] += ra
    # token đọc từ cache của API rẻ ~10 lần token thường
    _usage["usd"] += (vao * gia_vao + doc_cache * gia_vao * 0.1 + ra * gia_ra) / 1e6


def usage_report() -> dict:
    """Số liệu tích luỹ của tiến trình hiện tại. Gọi cuối job để biết đã đốt bao nhiêu."""
    return dict(_usage)


def print_usage() -> None:
    u = _usage
    print(f"[llm] {u['calls']} lần gọi ({u['cache_hits']} trúng cache) · "
          f"{u['input_tokens']:,} token vào · {u['output_tokens']:,} token ra · "
          f"≈ ${u['usd']:.4f}")


# -------------------------------------------------------------------- backends

def _anthropic_client():
    global _api_client
    if _api_client is None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError(
                "Thiếu ANTHROPIC_API_KEY. PowerShell: $env:ANTHROPIC_API_KEY='sk-ant-...' "
                "(hoặc đặt LLM_BACKEND=local để chạy model offline)."
            )
        # Import lười: chạy LLM_BACKEND=local thì không cần cài package anthropic.
        from anthropic import Anthropic

        # max_retries: SDK tự retry 429/5xx/lỗi mạng với backoff mũ — không tự
        # viết lại vòng retry cho mấy lỗi này nữa.
        _api_client = Anthropic(max_retries=4, timeout=120.0)
    return _api_client


def _noi_dung(prompt: str, images: list | None) -> list[dict]:
    """Dựng content blocks. images: đường dẫn file ảnh hoặc bytes."""
    blocks: list[dict] = []
    for img in images or []:
        raw = Path(img).read_bytes() if isinstance(img, (str, Path)) else img
        duoi = str(img).lower() if isinstance(img, (str, Path)) else ".jpg"
        media = "image/png" if duoi.endswith(".png") else "image/jpeg"
        blocks.append({
            "type": "image",
            "source": {"type": "base64", "media_type": media,
                       "data": base64.standard_b64encode(raw).decode("ascii")},
        })
    blocks.append({"type": "text", "text": prompt})
    return blocks


def _call_api(prompt: str, images, json_schema, model: str, effort: str,
              max_tokens: int) -> str:
    client = _anthropic_client()
    kwargs: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": _noi_dung(prompt, images)}],
        "output_config": {"effort": effort},
    }
    if json_schema is not None:
        # Structured outputs: server ép output khớp schema. Chắc chắn hơn nhiều
        # so với dặn LLM "chỉ trả JSON" rồi tự parse và cầu may.
        kwargs["output_config"]["format"] = {"type": "json_schema", "schema": json_schema}

    resp = client.messages.create(**kwargs)
    _ghi_nhan(model, resp.usage)

    # Bộ lọc an toàn có thể từ chối: HTTP vẫn 200, content rỗng → phải kiểm
    # stop_reason TRƯỚC khi đọc content, nếu không sẽ IndexError khó hiểu.
    if resp.stop_reason == "refusal":
        raise RuntimeError(
            f"Model từ chối yêu cầu (stop_reason=refusal). Đổi cách diễn đạt prompt."
        )
    return "".join(b.text for b in resp.content if b.type == "text").strip()


def _call_local(prompt: str, images, json_schema, model: str, max_tokens: int) -> str:
    """Backup offline qua Ollama. Dùng urllib để không thêm dependency mới.

    Cài trước ngày thi: `ollama pull qwen2.5:7b-instruct` (~4.7GB).
    Máy 16GB CPU chạy được nhưng chậm — chỉ dùng khi mất internet.
    """
    import urllib.error
    import urllib.request

    if images:
        raise NotImplementedError(
            "Backend local chưa hỗ trợ ảnh. Q&A cần ảnh thì phải dùng LLM_BACKEND=api."
        )

    url = os.environ.get("LLM_LOCAL_URL", "http://localhost:11434") + "/api/chat"
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"num_predict": max_tokens},
    }
    if json_schema is not None:
        body["format"] = json_schema  # Ollama nhận JSON Schema để ép định dạng

    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.loads(r.read())["message"]["content"].strip()
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"Không gọi được Ollama tại {url}: {e}. Đã chạy `ollama serve` chưa?"
        ) from e


# -------------------------------------------------------------------- API chính

def llm(
    prompt: str,
    images: list | None = None,
    json_schema: dict | None = None,
    n: int = 1,
    temperature: float | None = 0,
    *,
    model: str | None = None,
    effort: str = DEFAULT_EFFORT,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    use_cache: bool = True,
) -> str | list[str]:
    """Gọi LLM/VLM. Trả str khi n=1, list[str] khi n>1.

    json_schema: JSON Schema → output đảm bảo parse được bằng json.loads.
    temperature: BỊ BỎ QUA ở backend api (model mới không nhận) — xem đầu file.
    """
    backend = os.environ.get("LLM_BACKEND", "api")
    if backend == "api":
        model = model or os.environ.get("LLM_API_MODEL", DEFAULT_API_MODEL)
        if temperature not in (None, 0):
            print(f"[llm] bỏ qua temperature={temperature}: model {model} không nhận "
                  "tham số này. Cần đa dạng thì dùng n>1 hoặc mô tả trong prompt.")
    elif backend == "local":
        model = model or os.environ.get("LLM_LOCAL_MODEL", DEFAULT_LOCAL_MODEL)
    else:
        raise ValueError(f"LLM_BACKEND={backend!r} không hợp lệ (chỉ 'api' hoặc 'local').")

    key = _cache_key({
        "prompt": prompt, "schema": json_schema, "model": model, "n": n,
        "effort": effort, "max_tokens": max_tokens, "backend": backend,
        # ảnh vào hash theo nội dung, không theo đường dẫn: đổi tên file mà ảnh
        # y hệt thì vẫn phải trúng cache
        "images": [hashlib.sha256(
            Path(i).read_bytes() if isinstance(i, (str, Path)) else i
        ).hexdigest() for i in (images or [])],
    })

    if use_cache:
        cached = _cache_get(key)
        if cached is not None:
            _usage["cache_hits"] += 1
            return cached[0] if n == 1 else cached

    ket_qua: list[str] = []
    for _ in range(n):
        text = _mot_lan(prompt, images, json_schema, backend, model, effort, max_tokens)
        ket_qua.append(text)
        _usage["calls"] += 1

    if use_cache:
        _cache_put(key, ket_qua, {"model": model, "at": time.strftime("%Y-%m-%d %H:%M:%S")})
    return ket_qua[0] if n == 1 else ket_qua


def _mot_lan(prompt, images, json_schema, backend, model, effort, max_tokens) -> str:
    """Một lần sinh, có retry riêng cho trường hợp JSON hỏng.

    Vì sao chỉ retry JSON: lỗi mạng/429/5xx đã do SDK retry. Còn "trả về chữ
    không phải JSON" thì SDK coi là thành công — chỉ mình mới biết đó là lỗi.
    """
    for lan in range(2):
        if backend == "api":
            text = _call_api(prompt, images, json_schema, model, effort, max_tokens)
        else:
            text = _call_local(prompt, images, json_schema, model, max_tokens)

        if json_schema is None:
            return text
        try:
            json.loads(text)
            return text
        except json.JSONDecodeError as e:
            if lan == 1:
                raise ValueError(
                    f"LLM trả về JSON hỏng sau 2 lần thử: {e}\n--- output ---\n{text[:400]}"
                ) from e
            print(f"[llm] output không phải JSON hợp lệ, thử lại lần 2 ({e}).")
    raise AssertionError("không tới được đây")


def parse_json(prompt: str, json_schema: dict, **kw) -> dict | list:
    """Tiện ích: gọi llm() với schema rồi trả thẳng object đã parse."""
    return json.loads(llm(prompt, json_schema=json_schema, **kw))


if __name__ == "__main__":
    # Thử nhanh:  python -m backend.llm.adapter
    print("backend:", os.environ.get("LLM_BACKEND", "api"))
    print(llm("Dịch sang tiếng Anh, chỉ trả câu dịch: người đàn ông đội nón lá"))
    print_usage()
