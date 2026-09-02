# backend/llm/adapter.py — C0.1: ADAPTER llm(), điểm gọi LLM DUY NHẤT
#
# Nguyên tắc sống còn (CLAUDE.md bất biến 1): MỌI lần gọi LLM/VLM trong repo đi
# qua llm() ở đây. Không import SDK nhà cung cấp ở bất kỳ file nào khác — đổi
# backend chỉ sửa một dòng config, không phải lùng sửa từng chỗ gọi rải rác.
#
# ===== Cấu hình bằng biến môi trường =====
#   LLM_BACKEND      = "api" (mặc định) | "gemini" | "local"
#   LLM_API_MODEL    = model khi dùng API (mặc định claude-opus-5)
#   ANTHROPIC_API_KEY= bắt buộc khi LLM_BACKEND=api
#   LLM_GEMINI_MODEL = model khi dùng Gemini (mặc định gemini-3.6-flash — xem
#                      lý do không mặc định "pro"/"-latest" ở DEFAULT_GEMINI_MODEL)
#   GEMINI_API_KEY   = bắt buộc khi LLM_BACKEND=gemini, lấy tại aistudio.google.com/apikey
#   LLM_LOCAL_MODEL  = model Ollama khi chạy offline (mặc định qwen2.5:7b-instruct)
#   LLM_LOCAL_URL    = địa chỉ Ollama (mặc định http://localhost:11434)
#   LLM_CACHE_DIR    = thư mục cache (mặc định data/cache/llm)
#   LLM_NO_CACHE=1   → tắt cache (khi muốn đo độ trễ thật)
#
# ===== Vì sao thêm backend "gemini" =====
# Team chưa có ngân sách cho ANTHROPIC_API_KEY (thẻ thanh toán) trong lúc dev/test
# — Google AI Studio cấp API key MIỄN PHÍ. Thêm ở ĐÚNG MỘT chỗ (file này) là lý
# do toàn bộ pattern adapter tồn tại (CLAUDE.md bất biến 1): qa.py, trake.py,
# query_understanding.py không đổi một dòng nào khi đổi LLM_BACKEND.
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
# ⚠️ `temperature` chỉ CÓ TÁC DỤNG ở backend "gemini". Ở backend "api": Claude
# Opus 5 / Fable 5 / Sonnet 5 bỏ hẳn temperature/top_p/top_k, gửi lên là lỗi
# 400 — tham số vẫn còn trong chữ ký hàm cho khớp BUILD_TASKS C0.1, nhưng bị
# BỎ QUA (có cảnh báo). Cần đa dạng đầu ra ở backend "api" thì dùng n>1 + yêu
# cầu trong prompt, không dùng temperature — nhưng ở "gemini" vẫn dùng được
# temperature bình thường nếu muốn.

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

# "gemini-3.6-flash" — CỐ ĐỊNH, không dùng "-latest"/"-pro". Vẫn giữ nguyên tắc
# chốt bản cố định, chỉ đổi số hiệu. Đo thật trên key free-tier của team:
#   - (14/08) mọi model đuôi "-pro" (kể cả gemini-pro-latest) → 429
#     RESOURCE_EXHAUSTED, quota free tier = 0 cho tier Pro
#   - (14/08) "gemini-flash-latest" (alias) → hay 503 "quá tải", có lần TREO
#     NHIỀU PHÚT không timeout (alias trỏ model/route không ổn định phía Google)
#   - ⚠️ (21/08) "gemini-2.5-flash" — bản cũ chốt ở đây — nay trả 404 NOT_FOUND:
#     "no longer available to new users ... use models/gemini-3.6-flash".
#     Google KHÔNG gỡ model với key đã dùng nó từ trước, nên lỗi chỉ nổ ra trên
#     key mới → đây là loại hỏng "chạy được trên máy người khác". Đã đo lại
#     "gemini-3.6-flash" trên key của team (21/08): dịch VI→EN đúng, ~9s cho
#     lệnh gọi đầu (gồm dựng client), JSON schema + ảnh chạy đúng.
# Đổi model chỉ cần set LLM_GEMINI_MODEL, không sửa code.
DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"

# Giá USD / 1 triệu token. Claude: bảng giá Anthropic. Gemini: giá công khai
# Google AI (flash) — CHỈ để ƯỚC LƯỢNG chi phí, sai số vài % không quan trọng,
# biết đang đốt $0.2 hay $200 mới quan trọng. Model lạ không có trong bảng thì
# _ghi_nhan() rơi về (0.0, 0.0), không crash.
PRICING = {
    "claude-opus-5": (5.0, 25.0),
    "claude-fable-5": (10.0, 50.0),
    "claude-sonnet-5": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "gemini-flash-latest": (0.30, 2.50),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-3.6-flash": (0.30, 2.50),
}

# Mặc định effort thấp: việc của llm() trong đường ONLINE là dịch/mở rộng câu
# ngắn — không cần suy nghĩ sâu, và ngân sách chỉ 30s cho cả pipeline.
# Task nào cần nghĩ kỹ (Q&A suy luận) thì tự truyền effort="high".
DEFAULT_EFFORT = "low"
DEFAULT_MAX_TOKENS = 2048

# Token "thinking" của Gemini 3.x nằm TRONG `max_output_tokens`, khác hẳn Claude
# nơi `max_tokens` chỉ đếm đáp án. Đo thật (02/09, gemini-3.6-flash) trên đúng
# prompt dịch của `text_query.translate_to_english()`: thinking tốn 119 rồi 330
# token cho cùng một câu hỏi — biến thiên lớn, không đoán được bằng hệ số nhân.
# Nên cộng thẳng một khoản dư rộng rãi; token thinking không dùng hết thì không
# bị tính tiền, còn thiếu một token là đáp án cụt và sai IM LẶNG.
GEMINI_THINKING_HEADROOM = 2048

_api_client = None
_gemini_client_singleton = None
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

def _ghi_nhan(model: str, vao: int, ra: int, doc_cache: int = 0) -> None:
    """Cộng dồn token + ước lượng chi phí sau mỗi lần gọi API thật.

    Nhận SỐ ĐÃ TRÍCH SẴN, không nhận usage object thô: mỗi SDK đặt tên field
    khác nhau (Anthropic: input_tokens/output_tokens, Gemini SDK:
    prompt_token_count/candidates_token_count) — việc trích số làm ở _call_*
    của từng backend, hàm này chỉ lo cộng dồn + tính tiền, không cần biết SDK.
    """
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

def _nap_dotenv() -> None:
    """Điền các biến còn THIẾU từ `.env` vào os.environ.

    Hai sửa so với bản cũ (bản cũ nằm lọt trong `_anthropic_client()`):

    1. KHÔNG ghi đè biến operator đã export. Bản cũ gán thẳng
       `os.environ[k] = v`, nên `.env` LUÔN thắng — operator export
       `LLM_API_MODEL=claude-sonnet-5` mà `.env` ghi opus thì chạy opus, im
       lặng, không cảnh báo. Đúng thứ `_llm_runtime_errors()` trong run.py sinh
       ra để chặn ("một biến bị quên không âm thầm rơi về API/Opus mặc định"),
       nhưng preflight kiểm os.environ TRƯỚC khi adapter nạp `.env` nên không
       thấy. Nay `.env` chỉ VÁ CHỖ TRỐNG, export tường minh luôn thắng.

    2. Gọi được từ mọi backend, không riêng Anthropic. Trước đây `.env` chỉ
       được nạp bên trong `_anthropic_client()`, nên `LLM_BACKEND=gemini` với
       GEMINI_API_KEY nằm trong `.env` sẽ QUA được preflight của run.py (hàm
       đó có đọc `.env`) rồi mới chết ở adapter với "Thiếu GEMINI_API_KEY" —
       lệch hợp đồng giữa hai tầng.
    """
    env_path = REPO_ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and v and not os.environ.get(k):
            os.environ[k] = v


def _anthropic_client():
    global _api_client
    if _api_client is None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            _nap_dotenv()
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
    # Chỉ các model hỗ trợ extended thinking mới nhận tham số `effort`.
    # Haiku và các model cũ (claude-3-*) sẽ trả HTTP 400 nếu gửi kèm.
    # Dùng list trắng theo prefix thay vì hardcode tên: an toàn khi BTC đổi version.
    SUPPORTS_EFFORT = ("claude-sonnet", "claude-opus")
    use_effort = any(pat in model for pat in SUPPORTS_EFFORT)

    output_config: dict = {}
    if use_effort:
        output_config["effort"] = effort

    kwargs: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": _noi_dung(prompt, images)}],
        "output_config": output_config,
    }
    if json_schema is not None:
        # Structured outputs: server ép output khớp schema. Chắc chắn hơn nhiều
        # so với dặn LLM "chỉ trả JSON" rồi tự parse và cầu may.
        kwargs["output_config"]["format"] = {"type": "json_schema", "schema": json_schema}

    resp = client.messages.create(**kwargs)
    _ghi_nhan(model, resp.usage.input_tokens or 0, resp.usage.output_tokens or 0,
              getattr(resp.usage, "cache_read_input_tokens", 0) or 0)

    # Bộ lọc an toàn có thể từ chối: HTTP vẫn 200, content rỗng → phải kiểm
    # stop_reason TRƯỚC khi đọc content, nếu không sẽ IndexError khó hiểu.
    if resp.stop_reason == "refusal":
        raise RuntimeError(
            f"Model từ chối yêu cầu (stop_reason=refusal). Đổi cách diễn đạt prompt."
        )
    return "".join(b.text for b in resp.content if b.type == "text").strip()


def _gemini_client():
    global _gemini_client_singleton
    if _gemini_client_singleton is None:
        if not os.environ.get("GEMINI_API_KEY"):
            _nap_dotenv()
        if not os.environ.get("GEMINI_API_KEY"):
            raise RuntimeError(
                "Thiếu GEMINI_API_KEY. Lấy miễn phí tại aistudio.google.com/apikey, "
                "rồi $env:GEMINI_API_KEY='AIzaSy...' (PowerShell) hoặc "
                "export GEMINI_API_KEY='AIzaSy...' (bash/zsh)."
            )
        # Import lười: backend api/local không cần cài package google-genai.
        from google import genai
        from google.genai import types

        # ⚠️ SỬA 18/08 — đo thật: một request `generate_content()` TREO hơn 78
        # phút, CPU gần như 0% (chờ I/O thuần), không raise gì để nhánh retry
        # 429/503 phía trên có cơ hội chạy — client không có timeout NÀO thì
        # một request Gemini bị treo phía server chặn đứng CẢ TIẾN TRÌNH vô
        # thời hạn. Comment cũ (DEFAULT_GEMINI_MODEL) từng ghi nhận đúng triệu
        # chứng này ("có lần TREO NHIỀU PHÚT không timeout") nhưng quy hết cho
        # alias "-latest" không ổn định — chốt model "gemini-2.5-flash" không
        # xoá được gốc rễ: KHÔNG timeout ở tầng client thì DÙ model nào cũng có
        # thể treo. `_anthropic_client()` đã có `timeout=120.0` — cho Gemini
        # cùng ngân sách để nhất quán, và để nhánh retry 429/503 phía trên
        # (_call_gemini) có cơ hội chạy thay vì không bao giờ được gọi tới.
        _gemini_client_singleton = genai.Client(
            api_key=os.environ["GEMINI_API_KEY"],
            http_options=types.HttpOptions(timeout=120_000),  # ms
        )
    return _gemini_client_singleton


def _gemini_parts(prompt: str, images: list | None) -> list:
    """Dựng content parts cho Gemini — cùng quy ước ảnh với _noi_dung() (Claude):
    nhận đường dẫn file hoặc bytes, đoán media type từ đuôi file."""
    from google.genai import types

    parts: list = []
    for img in images or []:
        raw = Path(img).read_bytes() if isinstance(img, (str, Path)) else img
        duoi = str(img).lower() if isinstance(img, (str, Path)) else ".jpg"
        media = "image/png" if duoi.endswith(".png") else "image/jpeg"
        parts.append(types.Part.from_bytes(data=raw, mime_type=media))
    parts.append(prompt)
    return parts


# Gemini response_schema dùng phương ngữ OpenAPI 3.0 (KHÔNG PHẢI JSON Schema
# đầy đủ) — gửi thẳng schema viết cho Claude/local (chuẩn JSON Schema, có
# additionalProperties) bị 400 INVALID_ARGUMENT ngay: "Unknown name
# additional_properties". Đo thật trên PARSE_QUESTION_SCHEMA của qa.py (14/08).
_GEMINI_UNSUPPORTED_SCHEMA_KEYS = {"additionalProperties", "$schema", "$id"}


def _sanitize_schema_for_gemini(schema):
    """Bỏ các khoá JSON Schema mà Gemini không hiểu, ĐỆ QUY qua properties/items/
    anyOf. Trả bản SAO — không sửa schema gốc, vì cùng 1 schema constant (vd
    PARSE_QUESTION_SCHEMA) còn dùng cho backend api/local, nơi chuẩn JSON Schema
    đầy đủ vẫn cần additionalProperties để chặt chẽ."""
    if isinstance(schema, dict):
        return {
            k: _sanitize_schema_for_gemini(v)
            for k, v in schema.items()
            if k not in _GEMINI_UNSUPPORTED_SCHEMA_KEYS
        }
    if isinstance(schema, list):
        return [_sanitize_schema_for_gemini(v) for v in schema]
    return schema


def _call_gemini(prompt: str, images, json_schema, model: str, max_tokens: int,
                  temperature: float | None) -> str:
    """Gemini KHÔNG bỏ temperature như Claude — truyền thẳng khi có (khác Claude
    ở llm(), xem nhánh backend=="gemini" không in cảnh báo "bỏ qua temperature")."""
    from google.genai import types
    from google.genai.errors import ClientError, ServerError

    client = _gemini_client()
    # ⚠️ SỬA 02/09 — `max_output_tokens` của Gemini 3.x TÍNH CẢ token "thinking",
    # còn `max_tokens` mà chỗ gọi truyền vào mang nghĩa "độ dài ĐÁP ÁN" (đúng
    # ngữ nghĩa ở backend api). Không bù thì thinking ăn sạch ngân sách và trả
    # về đáp án cụt. Đo thật trên `translate_to_english()` (max_tokens=128):
    #     128 → thinking 119, còn 5 cho đáp án → 'concise, descriptive text'
    #     512 → thinking 330, còn 11 cho đáp án → 'man wearing a conical hat...'
    # Bản cụt KHÔNG rỗng nên mọi kiểm tra phía dưới đều qua, rồi nó đi thẳng vào
    # CLIP làm truy vấn — nhánh vector sập mà không một dòng log nào. Adapter là
    # nơi phải nuốt khác biệt này để chỗ gọi giữ nguyên một ngữ nghĩa cho mọi
    # backend (đó là toàn bộ lý do file này tồn tại).
    cfg: dict = {"max_output_tokens": max_tokens + GEMINI_THINKING_HEADROOM}
    if temperature is not None:
        cfg["temperature"] = temperature
    if json_schema is not None:
        # Structured outputs — ép output khớp schema ngay phía server, giống
        # output_config.format của backend api (Claude). Khử khoá JSON Schema
        # Gemini không hiểu trước khi gửi (xem docstring _sanitize_schema_for_gemini).
        cfg["response_mime_type"] = "application/json"
        cfg["response_schema"] = _sanitize_schema_for_gemini(json_schema)

    # ⚠️ SỬA 18/08 — comment cũ ("google-genai tự retry 429/5xx qua tenacity") SAI:
    # đọc thẳng source `google.genai._api_client.retry_args()` (v2.18.1) — khi
    # `Client(...)` dựng KHÔNG truyền `http_options.retry_options` (đúng như
    # `_gemini_client()` ở đây), hàm trả `tenacity.stop_after_attempt(1)`, tức
    # KHÔNG retry gì cả phía SDK. Toàn bộ việc retry là của lớp này.
    #
    # Và bản trước chỉ bắt `ServerError` (5xx) — 429 RESOURCE_EXHAUSTED (rate
    # limit free-tier: 5 request/phút, xem DEFAULT_GEMINI_MODEL ở đầu file) ném
    # `ClientError` (4xx, theo `APIError.raise_error()`), KHÔNG PHẢI `ServerError`,
    # nên bay thẳng ra ngoài KHÔNG retry giây nào. Đây là nguyên nhân chính khiến
    # Q&A (nhiều lệnh gọi llm() nhất/câu — parse + tới 3 shot × self-consistency
    # n=3 ± ảnh) luôn crash trên key free-tier: chạm 429 ở lệnh gọi thứ 2-3 là
    # ném lỗi ngay, không có cơ hội đợi qua cửa sổ 1 phút.
    #
    # 429 dùng backoff DÀI (15s, 30s, 60s) vì hạn mức free-tier reset THEO PHÚT —
    # backoff kiểu 503 (1s, 2s) sẽ không bao giờ đợi đủ lâu. Các mã 4xx khác
    # (400 sai request, vd schema hỏng) KHÔNG retry — đó là lỗi thật, retry chỉ
    # tốn thời gian mà kết quả không đổi.
    RATE_LIMIT_BACKOFF = (15, 30, 60)
    resp = None
    rate_limit_tries = 0
    server_error_tries = 0
    while resp is None:
        try:
            resp = client.models.generate_content(
                model=model,
                contents=_gemini_parts(prompt, images),
                config=types.GenerateContentConfig(**cfg),
            )
        except ServerError as e:
            if server_error_tries >= 2:
                raise RuntimeError(f"Gemini quá tải liên tục (503), thử lại sau: {e}") from e
            time.sleep(2 ** server_error_tries)
            server_error_tries += 1
        except ClientError as e:
            if e.code != 429:
                raise  # lỗi 4xx thật (vd schema hỏng) — retry không sửa được gì
            if rate_limit_tries >= len(RATE_LIMIT_BACKOFF):
                raise RuntimeError(
                    f"Gemini rate limit (429) liên tục sau {rate_limit_tries} lần đợi — "
                    f"key free-tier có thể đã hết hạn mức phút này: {e}"
                ) from e
            print(f"  [llm] Gemini 429 rate limit, đợi {RATE_LIMIT_BACKOFF[rate_limit_tries]}s "
                  f"(lần {rate_limit_tries + 1}/{len(RATE_LIMIT_BACKOFF)})...")
            time.sleep(RATE_LIMIT_BACKOFF[rate_limit_tries])
            rate_limit_tries += 1

    u = resp.usage_metadata
    _ghi_nhan(
        model,
        getattr(u, "prompt_token_count", 0) or 0,
        getattr(u, "candidates_token_count", 0) or 0,
        getattr(u, "cached_content_token_count", 0) or 0,
    )

    finish = resp.candidates[0].finish_reason if resp.candidates else "UNKNOWN"

    if not resp.text:
        # Bộ lọc an toàn có thể chặn output mà HTTP vẫn 200 — đọc finish_reason
        # để báo rõ vì sao thay vì để chỗ gọi nhận chuỗi rỗng khó hiểu.
        raise RuntimeError(
            f"Gemini không trả nội dung (finish_reason={finish}). Đổi cách diễn đạt prompt."
        )

    # ⚠️ Đáp án BỊ CẮT CỤT nguy hiểm hơn đáp án rỗng: nó không rỗng nên qua được
    # mọi phép kiểm phía sau, rồi đi thẳng vào CLIP/JSON parser như thể hợp lệ.
    # Đo thật 02/09: max_tokens=128 cho ra 'concise, descriptive text' thay vì
    # bản dịch — dùng làm truy vấn ảnh thì nhánh vector sập mà không có dấu hiệu.
    # Gemini CÓ báo qua finish_reason, bản trước chỉ đọc nó khi text rỗng.
    if str(finish).endswith("MAX_TOKENS"):
        raise RuntimeError(
            f"Gemini cắt cụt đáp án (finish_reason={finish}): đã xin "
            f"{max_tokens} token đáp án + {GEMINI_THINKING_HEADROOM} token dư cho "
            f"thinking mà vẫn không đủ. Tăng max_tokens ở chỗ gọi, hoặc nới "
            f"GEMINI_THINKING_HEADROOM.\n--- phần nhận được ---\n{resp.text[:200]}"
        )
    return resp.text.strip()


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
    temperature: BỊ BỎ QUA ở backend "api" (model Claude mới không nhận), CÓ
    tác dụng ở backend "gemini" — xem đầu file.
    """
    backend = os.environ.get("LLM_BACKEND", "api")
    if backend == "api":
        model = model or os.environ.get("LLM_API_MODEL", DEFAULT_API_MODEL)
        if temperature not in (None, 0):
            print(f"[llm] bỏ qua temperature={temperature}: model {model} không nhận "
                  "tham số này. Cần đa dạng thì dùng n>1 hoặc mô tả trong prompt.")
    elif backend == "gemini":
        model = model or os.environ.get("LLM_GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
        # Gemini NHẬN temperature bình thường (không như Claude) — không cảnh
        # báo/bỏ qua ở đây.
    elif backend == "local":
        model = model or os.environ.get("LLM_LOCAL_MODEL", DEFAULT_LOCAL_MODEL)
    else:
        raise ValueError(
            f"LLM_BACKEND={backend!r} không hợp lệ (chỉ 'api', 'gemini' hoặc 'local')."
        )

    key = _cache_key({
        "prompt": prompt, "schema": json_schema, "model": model, "n": n,
        "effort": effort, "max_tokens": max_tokens, "backend": backend,
        # temperature ảnh hưởng thật tới output ở backend gemini (không như api,
        # nơi nó bị bỏ qua) — phải vào hash, không thì đổi temperature mà vẫn
        # trúng cache của lần gọi cũ.
        "temperature": temperature,
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
        text = _mot_lan(prompt, images, json_schema, backend, model, effort, max_tokens, temperature)
        ket_qua.append(text)
        _usage["calls"] += 1

    if use_cache:
        _cache_put(key, ket_qua, {"model": model, "at": time.strftime("%Y-%m-%d %H:%M:%S")})
    return ket_qua[0] if n == 1 else ket_qua


def _mot_lan(prompt, images, json_schema, backend, model, effort, max_tokens, temperature=None) -> str:
    """Một lần sinh, có retry riêng cho trường hợp JSON hỏng.

    Vì sao chỉ retry JSON: lỗi mạng/429/5xx đã do SDK retry (Claude, Gemini) hoặc
    do lớp retry mỏng riêng (Gemini 503 quá tải — xem _call_gemini). Còn "trả về
    chữ không phải JSON" thì SDK coi là thành công — chỉ mình mới biết đó là lỗi.
    """
    for lan in range(2):
        if backend == "api":
            text = _call_api(prompt, images, json_schema, model, effort, max_tokens)
        elif backend == "gemini":
            text = _call_gemini(prompt, images, json_schema, model, max_tokens, temperature)
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
