# backend/llm/adapter.py — ADAPTER llm(), điểm tháo lắp DUY NHẤT (CLAUDE.md mục 2)
#
# Nguyên tắc sống còn: MỌI lần gọi LLM trong repo đều đi qua llm() ở đây.
# Vì sao? Vòng thi có thể CẤM internet → lúc đó chỉ cần sửa biến môi trường
# LLM_BACKEND=local (và viết nốt _llm_local) là cả hệ thống đổi não,
# không phải lùng sửa từng chỗ gọi API rải rác.
#
# Cách dùng:
#     from backend.llm import llm
#     answer = llm("Dịch sang tiếng Anh: người đàn ông đội nón lá")
#
# Cấu hình qua biến môi trường (không hardcode — CLAUDE.md mục 7):
#     LLM_BACKEND   = "api" (mặc định) | "local"
#     LLM_API_MODEL = model khi dùng API (mặc định "claude-fable-5")
#     ANTHROPIC_API_KEY = API key (bắt buộc khi LLM_BACKEND=api)

import os

# Cache client ở mức module: tạo client Anthropic hơi tốn (đọc config, tạo
# HTTP session) nên chỉ tạo 1 lần rồi tái sử dụng cho mọi lần gọi.
_api_client = None


def llm(prompt: str) -> str:
    """Gọi LLM, trả về text. Backend chọn qua env LLM_BACKEND."""
    backend = os.environ.get("LLM_BACKEND", "api")
    if backend == "api":
        return _llm_api(prompt)
    if backend == "local":
        return _llm_local(prompt)
    raise ValueError(
        f"LLM_BACKEND={backend!r} không hợp lệ. Chỉ nhận 'api' hoặc 'local'."
    )


def _llm_api(prompt: str) -> str:
    """Backend API: gọi Anthropic (claude-fable-5)."""
    global _api_client

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "Thiếu biến môi trường ANTHROPIC_API_KEY. "
            "Windows cmd: set ANTHROPIC_API_KEY=sk-ant-..."
        )

    if _api_client is None:
        # Import lười (bên trong hàm): chạy LLM_BACKEND=local sẽ không cần
        # cài package `anthropic`.
        from anthropic import Anthropic

        _api_client = Anthropic()  # tự đọc ANTHROPIC_API_KEY từ env

    response = _api_client.messages.create(
        model=os.environ.get("LLM_API_MODEL", "claude-fable-5"),
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    # response.content là list các block; với prompt text thường,
    # block đầu tiên là TextBlock chứa câu trả lời.
    return response.content[0].text


def _llm_local(prompt: str) -> str:
    """Backend local: model quantize nhỏ chạy offline — CHƯA làm.

    Kế hoạch (CLAUDE.md mục 2): Qwen 2.5 3B/7B hoặc Llama 3.2 3B bản
    quantize (GGUF, chạy qua llama-cpp-python hoặc Ollama) vì máy dev
    chỉ có 16GB RAM. Sẽ làm khi biết chắc vòng thi cấm internet.
    """
    raise NotImplementedError(
        "LLM_BACKEND=local chưa được cài đặt. "
        "TODO: nối Qwen 2.5 3B / Llama 3.2 3B quantize (xem docstring)."
    )
