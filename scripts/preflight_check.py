# scripts/preflight_check.py — D6.1: MỘT LỆNH tự kiểm toàn bộ checklist trước giờ nộp
#
# ===== Vì sao script này tồn tại =====
# Checklist tick tay lúc 2 giờ sáng ngày nộp là công thức bỏ sót (BUILD_TASKS D6.1).
# Người mệt sẽ tick "chắc là được" cho mục mình không kiểm nổi trong 30 giây.
# Máy thì không mệt, và nó tick bằng cách CHẠY THẬT.
#
# ===== Nguyên tắc: KHÔNG viết lại phép kiểm nào =====
# Mọi mục dưới đây gọi lại code đã có và đã có test:
#   backend.export          → validate_all / validate_zip (D0.2)
#   backend.slot            → allocate() (D3.1)
#   backend.indexing        → load_frame_map, es_client, milvus_client, assert_index_meta
#   data.config             → slot_budget, scoring, submit_format
# Viết lại ở đây = có bản thứ hai của cùng một luật, và hai bản sẽ lệch nhau
# đúng vào hôm cần nhất. Script này chỉ GHÉP và IN.
#
# ===== Ba trạng thái, không phải hai =====
#   PASS — đã chạy thật và đúng
#   FAIL — đã chạy thật và sai  → exit code khác 0
#   SKIP — chưa chạy được (thiếu Docker/thư viện), KÈM LÝ DO
# Gộp SKIP vào PASS là điều tệ nhất một preflight có thể làm: nó biến "chưa
# kiểm" thành màu xanh, tức là đúng cái cảm giác an toàn giả mà script này sinh
# ra để phá.
#
# ===== Chạy =====
#   python scripts/preflight_check.py --profile development
#   python scripts/preflight_check.py --profile release  # SKIP bắt buộc thành FAIL
#   python scripts/preflight_check.py --quick    # bỏ mọi mục cần Docker/model
#   python scripts/preflight_check.py --json     # cho E6.1 nhét vào log diễn tập
#
# Exit code: 0 = không mục nào FAIL · 1 = có mục hỏng.

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

PASS = "ĐẠT"
FAIL = "KHÔNG ĐẠT"
SKIP = "BỎ QUA"

# Ngân sách độ trễ của MỘT truy vấn, tính bằng giây (CLAUDE.md mục 2, luật 2:
# "≤ 30s từ lúc gõ query tới lúc có kết quả trên màn hình").
#
# Để ở đây chứ không trong data/config/ vì đây không phải tham số tune — nó là
# ràng buộc THỂ THỨC (3 giờ cho 20-30 câu), đổi khi lịch thi đổi chứ không đổi
# khi tune hệ thống. Vượt ngưỡng là FAIL chứ không phải cảnh báo: một pipeline
# 45s không "hơi chậm", nó là câu không kịp làm.
LATENCY_BUDGET_S = 30.0

# Truy vấn dùng để đo độ trễ. Có sẵn bản dịch EN để KHÔNG phụ thuộc LLM — mục
# này đo đường ống search, không đo tốc độ của nhà cung cấp API.
LATENCY_QUERY_VI = "một người đàn ông mặc áo đỏ phát biểu tại họp báo ngoài trời"
LATENCY_QUERY_EN = "a man in a red shirt speaking at an outdoor press conference"


@dataclass
class CheckResult:
    """Kết quả một mục kiểm. `ms` để biết mục nào đang ăn thời gian người vận hành."""

    group: str
    name: str
    status: str
    detail: str = ""
    ms: float = 0.0


@dataclass
class Check:
    """Một mục trong checklist.

    `needs_infra=True` → mục chạm Docker/model nặng, bị --quick bỏ qua.
    `fn` trả `(bool | None, str)`: None = không kết luận được → SKIP.
    """

    group: str
    name: str
    fn: Callable[[], tuple[bool | None, str]]
    needs_infra: bool = False
    # Release không được biến "chưa kiểm" thành xanh. Chỉ các tiện ích không nằm
    # trên đường batch (UI/API tuỳ chọn) mới đặt False.
    required_in_release: bool = True


# ============================================================ A. MÔI TRƯỜNG

def _try_import(module_name: str) -> tuple[bool, str]:
    import importlib

    try:
        mod = importlib.import_module(module_name)
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
    return True, getattr(mod, "__version__", "?")


def check_python() -> tuple[bool | None, str]:
    """Interpreter nào đang chạy — in ĐƯỜNG DẪN, không chỉ số phiên bản.

    Vì sao đường dẫn quan trọng hơn phiên bản: máy nào cũng có vài Python (hệ
    thống, venv, Store). Cài `pip install` vào cái này rồi chạy bằng cái kia là
    lỗi "thiếu thư viện" khó hiểu nhất, và nó chỉ lộ ra khi so đường dẫn.
    """
    v = sys.version_info
    return True, f"{v.major}.{v.minor}.{v.micro} tại {sys.executable}"


def check_core_libs() -> tuple[bool | None, str]:
    """Thư viện KHÔNG CÓ thì pipeline chết hẳn — parquet, vector store, ES."""
    required = ["pandas", "pyarrow", "numpy", "elasticsearch", "pymilvus"]
    missing = []
    for name in required:
        ok, detail = _try_import(name)
        if not ok:
            missing.append(f"{name} ({detail.split(':')[0]})")
    if missing:
        return False, ("thiếu: " + ", ".join(missing)
                       + " — cài: pip install -r backend/requirements.txt")
    return True, "đủ: " + ", ".join(required)


def check_optional_libs() -> tuple[bool | None, str]:
    """Thư viện thiếu thì MẤT MỘT TÍNH NĂNG chứ không sập: API, LLM, CLIP, UI.

    Tách khỏi nhóm lõi để không báo đỏ ở máy chỉ chạy phần của mình — nhưng vẫn
    phải HIỆN RA, vì thiếu `anthropic` nghĩa là Q&A không chạy, mà Q&A im lặng
    không chạy thì tới lúc chấm mới biết.
    """
    optional = {
        "fastapi": "API /search + /submit",
        "anthropic": "llm() backend=api",
        "torch": "encode query CLIP",
        "open_clip": "encode query CLIP",
        "streamlit": "UI debug (D2.1)",
    }
    missing = [f"{name} → mất {role}" for name, role in optional.items()
               if not _try_import(name)[0]]
    if missing:
        return None, "; ".join(missing)
    return True, f"đủ {len(optional)} thư viện tuỳ chọn"


def check_vector_backend() -> tuple[bool | None, str]:
    """In encoder đang chạy + số vector của collection nó thật sự dùng.

    ⚠️ Vì sao đáng một dòng riêng (R3.K2c, đóng finding M1 của review 28/08):
    preflight in `LLM_BACKEND`/model/QA mode nhưng KHÔNG in cổng vector. Đổi
    encoder là đổi cả không gian vector — thứ hỏng im lặng nhất trong hệ này —
    mà người vận hành tối 04/09 lại không có cách nào NHÌN THẤY mình đang chạy
    encoder nào ngoài việc tin vào trí nhớ.

    Không tự chọn hộ, không đổi gì: chỉ đọc `VECTOR_BACKEND` và đếm hàng trong
    đúng collection tương ứng — cùng nguyên tắc với `check_qa_runtime()`.
    """
    from data.config.siglip2_model import SIGLIP2_COLLECTION, use_siglip2
    from backend.indexing.milvus_client import COLLECTION_NAME

    backend = os.environ.get("VECTOR_BACKEND", "clip").strip().lower()
    if backend not in ("clip", "siglip2"):
        return False, (
            f"VECTOR_BACKEND={backend!r} không hợp lệ (chỉ 'clip' hoặc 'siglip2'). "
            "search() sẽ im lặng chạy nhánh CLIP mặc định."
        )
    collection = SIGLIP2_COLLECTION if use_siglip2() else COLLECTION_NAME

    try:
        from backend.indexing.milvus_client import connect

        client = connect()
        if not client.has_collection(collection):
            return False, (
                f"VECTOR_BACKEND={backend} nhưng collection {collection!r} KHÔNG TỒN TẠI — "
                "nhánh vector sẽ chết và search chỉ còn 4 nhánh text."
            )
        n = int(client.get_collection_stats(collection)["row_count"])
    except Exception as e:
        return None, f"VECTOR_BACKEND={backend} · collection={collection} · không đếm được ({e})"

    if n == 0:
        return False, f"VECTOR_BACKEND={backend} · collection {collection} RỖNG"
    return True, f"VECTOR_BACKEND={backend} · collection={collection} · {n:,} vector"


def check_qa_runtime() -> tuple[bool | None, str]:
    """Chỉ báo backend/model người vận hành đã chọn; không tự đổi hay gọi API.

    Model được đặt thủ công ngay trước lệnh chạy. Preflight chỉ kiểm SDK/key và
    in lại giá trị resolve để người vận hành nhìn thấy sai cấu hình mà không tốn
    thêm một network request.
    """
    from backend.llm.adapter import (
        DEFAULT_API_MODEL,
        DEFAULT_GEMINI_MODEL,
        DEFAULT_LOCAL_MODEL,
    )
    from data.config.qa_inference import qa_runtime_config

    try:
        qa_runtime = qa_runtime_config()
    except ValueError as e:
        return False, str(e)
    backend = os.environ.get("LLM_BACKEND", "api")
    if backend == "api":
        model = os.environ.get("LLM_API_MODEL", DEFAULT_API_MODEL)
    elif backend == "gemini":
        model = os.environ.get("LLM_GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
    elif backend == "local":
        model = os.environ.get("LLM_LOCAL_MODEL", DEFAULT_LOCAL_MODEL)
    else:
        return False, f"LLM_BACKEND={backend!r} không hợp lệ"
    env_file = REPO_ROOT / ".env"

    def has_secret(name: str) -> bool:
        if os.environ.get(name):
            return True
        if not env_file.exists():
            return False
        try:
            return any(
                line.strip().startswith(f"{name}=") and line.split("=", 1)[1].strip()
                for line in env_file.read_text(encoding="utf-8").splitlines()
                if "=" in line and not line.lstrip().startswith("#")
            )
        except OSError:
            return False

    if backend == "api":
        sdk_ok = _try_import("anthropic")[0]
        if not sdk_ok or not has_secret("ANTHROPIC_API_KEY"):
            return None, "LLM_BACKEND=api thiếu anthropic hoặc ANTHROPIC_API_KEY"
    elif backend == "gemini":
        sdk_ok = _try_import("google.genai")[0]
        if not sdk_ok or not has_secret("GEMINI_API_KEY"):
            return None, "LLM_BACKEND=gemini thiếu google-genai hoặc GEMINI_API_KEY"
    elif backend == "local":
        return None, "LLM_BACKEND=local chưa hỗ trợ ảnh; chỉ dùng được đường text-first"
    return True, (
        f"LLM_BACKEND={backend} · model={model} · QA mode={qa_runtime['mode']} · "
        f"cohort={qa_runtime['screen_n']}+{qa_runtime['confirm_additional_n']} · "
        f"cap={qa_runtime['two_stage_max_generations']} · SDK/key sẵn sàng"
    )


# ============================================================ B. HẠ TẦNG

def _port_responds(url: str, timeout: float = 3.0) -> bool:
    """Cổng HTTP có ai trả lời không — dùng để PHÂN BIỆT hai ca rất khác nhau.

    Không phải kiểm sức khoẻ: chỉ cần biết có tiến trình nào đang nghe. Trả lời
    HTTP 4xx/5xx vẫn tính là CÓ — dịch vụ sống mà từ chối ta là chuyện cấu hình.
    """
    import urllib.error
    import urllib.request

    try:
        urllib.request.urlopen(url, timeout=timeout)
    except urllib.error.HTTPError:
        return True  # có trả lời, chỉ là mã lỗi → dịch vụ ĐANG SỐNG
    except (urllib.error.URLError, OSError):
        return False
    return True


def check_elasticsearch() -> tuple[bool | None, str]:
    """Ping ES THẬT, và đếm doc từng index mà search() dùng.

    Đếm doc chứ không chỉ ping: một ES sống nhưng index rỗng cho ra search
    "chạy bình thường, không kết quả" — nhánh đó âm thầm biến mất khỏi RRF mà
    `search()` chỉ in một dòng cảnh báo rồi đi tiếp (đúng thiết kế, để một nhánh
    chết không kéo sập cả câu). Preflight là chỗ duy nhất phải nói to chuyện đó.

    ⚠️ Tự phân loại lỗi thay vì để khung xử lý chung đoán, vì hai ca dưới đây
    trông giống hệt nhau (đều là `ConnectionError`) mà ý nghĩa ngược nhau:

        cổng 9200 im lặng       → CHƯA BẬT DOCKER. Chưa kiểm được → SKIP.
        cổng 9200 trả lời, mà
        client vẫn bị từ chối   → LỖI THẬT, sửa được ngay → FAIL.

    Đo thật 19/08 trên máy dev: ES 8.13.4 chạy bình thường, client python 9.5.0
    → `media_type_header_exception`, cả 4 nhánh ES (metadata/objects/ocr/asr)
    chết câm, `search()` chạy tiếp bằng mỗi nhánh vector và KHÔNG báo gì ra
    ngoài. Khung xử lý chung xếp ca này vào SKIP — tức là preflight nhìn thẳng
    vào một hệ thống hỏng nặng rồi nói "chưa kiểm được". Đúng loại im lặng mà cả
    script này sinh ra để phá, nên phải chặn ngay tại đây.
    """
    from backend.indexing.es_client import ES_URL, connect

    if not _port_responds(ES_URL):
        return None, f"không có ai nghe ở {ES_URL} — chạy `docker compose up -d` trước"

    try:
        es = connect()
    except Exception as e:
        return False, (f"{ES_URL} đang sống nhưng client không dùng được — "
                       f"{str(e).splitlines()[0]}")

    counts = []
    for index in ("metadata", "objects", "ocr", "asr"):
        if not es.indices.exists(index=index):
            counts.append(f"{index}=THIẾU")
            continue
        counts.append(f"{index}={es.count(index=index)['count']:,}")
    dead = [c for c in counts if c.endswith("=0") or c.endswith("THIẾU")]
    return (not dead), " · ".join(counts) + (
        f"  ← {len(dead)} nhánh không dùng được" if dead else "")


def check_milvus() -> tuple[bool | None, str]:
    """Milvus sống + collection có entity."""
    from backend.indexing.milvus_client import COLLECTION_NAME, connect

    client = connect()
    if COLLECTION_NAME not in client.list_collections():
        return False, (f"không có collection '{COLLECTION_NAME}' — "
                       "chạy: python -m backend.indexing.load_clip")
    n_rows = int(client.get_collection_stats(COLLECTION_NAME).get("row_count", 0))
    if n_rows == 0:
        return False, f"collection '{COLLECTION_NAME}' rỗng (0 vector)"
    return True, f"{COLLECTION_NAME}: {n_rows:,} vector"


def check_api_health() -> tuple[bool | None, str]:
    """Gọi `/health` deep check và đọc trạng thái tổng, không chỉ ping HTTP."""
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen("http://localhost:8000/health", timeout=3) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            status = json.loads(body).get("status", "unknown")
        except json.JSONDecodeError:
            status = f"HTTP {e.code}"
        return False, f"deep health báo {status} (HTTP {e.code})"
    except (urllib.error.URLError, OSError) as e:
        return None, f"API chưa chạy ({type(e).__name__}) — chỉ cần khi thao tác qua UI"
    try:
        report = json.loads(body)
    except json.JSONDecodeError:
        return False, f"/health không trả JSON hợp lệ: {body[:80]}"
    status = report.get("status")
    if status == "down":
        return False, f"deep health báo down ({report.get('latency_ms', '?')} ms)"
    if status not in {"ok", "degraded"}:
        return False, f"deep health có status lạ: {status!r}"
    return True, f"deep health={status} · {report.get('latency_ms', '?')} ms"


# ============================================================ C. DỮ LIỆU

# File dẫn xuất và người sở hữu — để báo lỗi biết đi hỏi ai (CLAUDE.md mục 13).
REQUIRED_PARQUET = {
    "video_info.parquet": "Thạch (R1.1)",
    "frame_map.parquet": "Thạch (R1.1)",
    "shots.parquet": "Thạch (R1.1)",
    "keyframes.parquet": "Thạch (R1.1)",
    "clip_kf_map.parquet": "Thạch (R1.1)",
}


def check_parquet() -> tuple[bool | None, str]:
    """Mọi parquet lõi phải tồn tại, đọc được, khác rỗng."""
    import pyarrow.parquet as pq

    derived = REPO_ROOT / "data" / "derived"
    issues, ok_files = [], []
    for name, owner in REQUIRED_PARQUET.items():
        path = derived / name
        if not path.exists():
            issues.append(f"{name} THIẾU (hỏi {owner})")
            continue
        try:
            n_rows = pq.read_metadata(path).num_rows
        except Exception as e:
            issues.append(f"{name} không đọc được ({type(e).__name__})")
            continue
        if n_rows == 0:
            issues.append(f"{name} rỗng (0 dòng)")
        else:
            ok_files.append(f"{name.replace('.parquet', '')}={n_rows:,}")
    return (not issues), (" · ".join(issues) if issues else " · ".join(ok_files))


def check_meta_json() -> tuple[bool | None, str]:
    """Mỗi parquet phải đi kèm `.meta.json` (CLAUDE.md bất biến 8).

    Không có meta thì không ai biết file sinh ra lúc nào, từ commit nào, bằng
    tham số gì — và lúc số liệu trông lạ thì không truy được là dữ liệu cũ hay
    code mới. Thiếu meta là NỢ, không phải lỗi chặn nộp: SKIP kèm danh sách.
    """
    derived = REPO_ROOT / "data" / "derived"
    missing = [name for name in REQUIRED_PARQUET
               if (derived / name).exists()
               and not (derived / f"{name}.meta.json").exists()]
    if missing:
        return None, "thiếu .meta.json: " + ", ".join(missing)
    return True, f"đủ .meta.json cho {len(REQUIRED_PARQUET)} file lõi"


def check_frame_map() -> tuple[bool | None, str]:
    """frame_map nạp được và tra được cả HAI dạng khoá.

    Hai dạng vì hai nguồn đặt tên khác nhau — `L21_V001#k0001` (keyframe BTC,
    thứ nằm trong Milvus/OCR) và `L21_V001_0000014` (keyframe tự trích 1fps).
    `backend/indexing/frame_map.py` dựng sẵn cả hai; mất một dạng thì slot
    allocator lặng lẽ mất mức ưu tiên ① — không lỗi, chỉ kém đi.
    """
    from backend.indexing.frame_map import load_frame_map

    frame_map = load_frame_map()
    if not frame_map:
        return False, "frame_map rỗng"
    n_btc = sum(1 for k in frame_map if "#k" in k)
    n_1fps = len(frame_map) - n_btc
    if n_btc == 0 or n_1fps == 0:
        return False, (f"chỉ có MỘT dạng khoá (#k={n_btc}, 1fps={n_1fps}) — "
                       "allocator sẽ mất mức ưu tiên ①")
    return True, f"{len(frame_map):,} khoá ({n_btc:,} dạng #k + {n_1fps:,} dạng 1fps)"


def check_video_info() -> tuple[bool | None, str]:
    """video_info đọc được qua ĐÚNG hàm mà validator dùng (`n_frames_of`).

    Gọi hàm thật chứ không tự đọc parquet: nếu Data Factory đổi tên cột lần nữa
    (đã xảy ra 07/08: `n_frames` → `nb_frames_decoded`), mục này phải đỏ CÙNG
    LÚC với validator, không phải xanh trong khi validator gãy.
    """
    from backend.export import all_video_ids, n_frames_of

    video_ids = all_video_ids()
    if not video_ids:
        return False, "video_info.parquet không có video nào"
    bad = [v for v in video_ids if n_frames_of(v) <= 0]
    if bad:
        return False, f"{len(bad)} video có n_frames <= 0 (vd {bad[:3]})"
    return True, f"{len(video_ids):,} video, n_frames hợp lệ"


def check_frame_assets() -> tuple[bool | None, str]:
    """Mỗi video trong frame_map có ít nhất một ảnh raw/derived thật hay chưa."""
    import pandas as pd

    from data.config.frame_assets import DERIVED_KEYFRAMES_DIR, RAW_KEYFRAMES_DIR

    map_path = REPO_ROOT / "data" / "derived" / "frame_map.parquet"
    if not map_path.exists():
        return None, "chưa có frame_map để biết video nào cần ảnh"
    expected = set(pd.read_parquet(map_path, columns=["video_id"])["video_id"].astype(str))
    if not expected:
        return False, "frame_map không có video_id nào"

    video_dirs: dict[str, list[Path]] = {}

    def register(video_dir: Path) -> None:
        if video_dir.is_dir() and "_V" in video_dir.name:
            video_dirs.setdefault(video_dir.name, []).append(video_dir)

    if RAW_KEYFRAMES_DIR.is_dir():
        for child in RAW_KEYFRAMES_DIR.iterdir():
            if not child.is_dir():
                continue
            if child.name.startswith("keyframes_"):
                for video_dir in child.iterdir():
                    register(video_dir)
            else:
                register(child)
    if DERIVED_KEYFRAMES_DIR.is_dir():
        for child in DERIVED_KEYFRAMES_DIR.iterdir():
            register(child)

    covered = {
        video_id
        for video_id, dirs in video_dirs.items()
        if video_id in expected
        and any(next(directory.glob("*.jpg"), None) is not None for directory in dirs)
    }
    missing = sorted(expected - covered)
    if missing:
        return None, (
            f"ảnh phủ {len(covered):,}/{len(expected):,} video; thiếu "
            f"{len(missing):,} (vd {missing[:5]}) — kiểm KEYFRAMES_DIR và "
            "DERIVED_KEYFRAMES_DIR"
        )
    return True, f"ảnh phủ đủ {len(expected):,}/{len(expected):,} video trong frame_map"


# ============================================================ D. KHÔNG GIAN VECTOR

def check_clip_meta() -> tuple[bool | None, str]:
    """Index và config phải CÙNG không gian vector (CLAUDE.md bất biến 2).

    `strict=True` ở đây (search.py dùng `strict=False`): search phải chạy tiếp
    khi chưa nạp features, còn preflight thì ngược lại — chưa nạp là chưa sẵn
    sàng nộp. Lệch model là lỗi im lặng đắt nhất trong cả dự án: Milvus vẫn trả
    top-k, cosine vẫn 0.2–0.3, mọi thứ trông bình thường và sai toàn bộ.

    ⚠️ SỬA (R3.K2c) — bản cũ LUÔN kiểm meta CLIP, kể cả khi chạy
    `VECTOR_BACKEND=siglip2`. Người vận hành thấy dòng "ĐẠT · ViT-B-32 · 512
    chiều" và yên tâm, trong khi nhánh vector thật sự đang chạy là SigLIP2 và
    meta của nó chưa hề được kiểm. Preflight nói dối về đúng thứ nó sinh ra để
    canh là hỏng tệ hơn không có preflight. Giờ kiểm meta của encoder ĐANG chạy.
    """
    from data.config.siglip2_model import use_siglip2

    if use_siglip2():
        from backend.indexing.load_siglip2 import assert_siglip2_index_meta

        meta = assert_siglip2_index_meta(strict=True)
        return True, (f"{meta.get('model_name')} / {meta.get('pretrained')} "
                      f"· {meta.get('embedding_dim')} chiều · metric {meta.get('metric')} "
                      f"· nạp {meta.get('built_at')}")

    from backend.indexing.load_clip import assert_index_meta

    meta = assert_index_meta(strict=True)
    return True, (f"{meta.get('model_open_clip')} / {meta.get('pretrained')} "
                  f"· {meta.get('dim')} chiều · metric {meta.get('metric')} "
                  f"· nạp {meta.get('built_at')}")


def check_vector_norm() -> tuple[bool | None, str]:
    """Vector trong Milvus phải đã chuẩn hoá L2 (|v| ≈ 1) — bất biến 1.

    Gọi `verify_norms()` của loader, không tự tính: đó là phép kiểm chạy được mà
    A1.0a đã viết kèm. Chưa chuẩn hoá mà metric là IP thì thứ hạng sai một cách
    có hệ thống, và cũng không có dấu hiệu gì.
    """
    from backend.indexing.load_clip import verify_norms
    from backend.indexing.milvus_client import COLLECTION_NAME, connect
    from data.config.siglip2_model import SIGLIP2_COLLECTION, use_siglip2

    # Cùng lý do với check_clip_meta: kiểm collection ĐANG chạy, không phải
    # collection mặc định. Báo "|v| ≈ 1" cho một index không ai dùng là màu xanh
    # rỗng nghĩa — đúng thứ ba-trạng-thái ở đầu file sinh ra để chống.
    collection = SIGLIP2_COLLECTION if use_siglip2() else COLLECTION_NAME
    ok = verify_norms(connect(), n=20, collection=collection)
    return bool(ok), (f"20 vector mẫu trong {collection} có |v| ≈ 1" if ok
                      else f"{collection} có vector chưa chuẩn hoá L2")


# ============================================================ E. ĐƯỜNG NỘP

def _real_shots(n: int) -> list:
    """`n` shot THẬT lấy từ shots.parquet, mỗi video một shot.

    Dùng shot thật chứ không bịa id: mục này phải đi qua đúng đường tra
    `shots.parquet` + `frame_map` + `video_info` mà lúc thi sẽ đi. Shot bịa thì
    `allocate()` ném KeyError và ta kiểm được đúng cái không cần kiểm.
    """
    import pandas as pd

    from backend.slot import ShotHit
    from backend.slot.allocator import SHOTS_PATH

    df = pd.read_parquet(SHOTS_PATH, columns=["shot_id", "video_id"])
    df = df.groupby("video_id", sort=True).head(1).head(n)
    return [ShotHit(row.shot_id, 1.0 - i * 0.01)
            for i, row in enumerate(df.itertuples(index=False))]


def check_submission_path() -> tuple[bool | None, str]:
    """DIỄN TẬP NỘP đầy đủ cho cả 3 dạng bài, trên dữ liệu thật, trong thư mục tạm.

    allocate() → QuerySubmission → validate_all() → ghi .zip → validate_zip().

    Đây là mục quan trọng nhất của cả script: nó chạy đúng chuỗi mà tối thi sẽ
    chạy. Ba dạng bài chứ không phải một, vì luật validator khác nhau ở từng
    dạng (Q&A bắt buộc có answer, TRAKE bắt buộc N frame tăng dần) — kiểm mỗi
    KIS thì hai đường còn lại vẫn có thể gãy lúc nộp thật.
    """
    import shutil
    import tempfile

    from backend.export import (
        QuerySubmission,
        format_issues,
        validate_all,
        validate_zip,
        write_submission_zip,
    )
    from backend.slot import allocate

    hits = _real_shots(100)
    if not hits:
        return False, "shots.parquet không có shot nào để diễn tập"

    subs = [
        QuerySubmission("query-1-kis", "KIS", tuple(allocate(hits, "KIS"))),
        QuerySubmission("query-2-qa", "QA", tuple(allocate(hits, "QA", answer_text="5"))),
        QuerySubmission("query-3-trake", "TRAKE", tuple(allocate(hits, "TRAKE", n_trake=4))),
    ]
    short = [f"{s.query_id}={len(s.answers)}" for s in subs if len(s.answers) != 100]
    if short:
        return False, "KHÔNG đủ 100 dòng: " + ", ".join(short)

    issues = validate_all(subs, expected_n={"query-3-trake": 4})
    if issues:
        return False, format_issues(issues).replace("\n", " ")[:300]

    tmp_dir = Path(tempfile.mkdtemp(prefix="preflight_"))
    try:
        zip_path, zip_issues = write_submission_zip(subs, str(tmp_dir))
        zip_issues = list(zip_issues) + validate_zip(zip_path)
        if zip_issues:
            return False, format_issues(zip_issues).replace("\n", " ")[:300]
        size_kb = Path(zip_path).stat().st_size / 1024
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return True, f"3 dạng bài × 100 dòng → .zip {size_kb:.0f} KB, validator sạch"


# ============================================================ F. ĐỘ TRỄ

def check_latency() -> tuple[bool | None, str]:
    """Đo THẬT một truy vấn KIS end-to-end, đối chiếu ngân sách 30s.

    Truyền sẵn `query_en` để không tính thời gian gọi LLM dịch vào con số này:
    mục này đo ĐƯỜNG ỐNG SEARCH (Milvus + 4 nhánh ES + RRF + gom shot). Bước
    dịch có cache và có đường đi vòng (người thao tác gõ thẳng tiếng Anh), nên
    trộn nó vào đây sẽ giấu mất chỗ chậm thật.

    Không gọi LLM cũng có nghĩa con số này là CẬN DƯỚI của độ trễ lúc thi. Vượt
    30s ở đây thì lúc thi chắc chắn vượt.
    """
    from backend.retrieval import search as search_module

    t0 = time.perf_counter()
    hits = search_module.search(LATENCY_QUERY_VI, query_en=LATENCY_QUERY_EN,
                                top_k=100, group_by_shot=True)
    seconds = time.perf_counter() - t0

    if not hits:
        return False, f"search trả 0 kết quả sau {seconds:.1f}s — nhánh nào cũng câm"
    if seconds > LATENCY_BUDGET_S:
        return False, (f"{seconds:.1f}s > ngân sách {LATENCY_BUDGET_S:.0f}s "
                       f"({len(hits)} shot) — mỗi câu chậm là một câu không kịp làm")
    return True, f"{seconds:.1f}s cho {len(hits)} shot (ngân sách {LATENCY_BUDGET_S:.0f}s)"


# ============================================================ G. CẤU HÌNH

def check_slot_budget() -> tuple[bool | None, str]:
    """Bảng ngân sách phải cấp ĐÚNG 100 slot ở mọi số shot có thể gặp.

    Quét nhiều `n_shots` chứ không chỉ một: `budget_per_shot()` có ba nhánh xử
    lý lệch (ít shot hơn bảng, nhiều hơn bảng, tổng bảng khác 100) và nhánh nào
    trả sai tổng thì bài nộp thiếu dòng — mất điểm miễn phí mà validator chỉ
    phát hiện được ở phút chót.
    """
    import data.config.slot_budget as slot_budget
    from data.config.submit_format import ANSWERS_PER_QUERY

    for n_shots in (1, 2, 3, 7, 31, 73, 99, 100, 137, 500):
        quota = slot_budget.budget_per_shot(
            n_shots, slot_budget.SLOT_BUDGET, ANSWERS_PER_QUERY)
        if len(quota) != n_shots:
            return False, f"n_shots={n_shots}: trả {len(quota)} hạn mức thay vì {n_shots}"
        if sum(quota) != ANSWERS_PER_QUERY:
            return False, (f"n_shots={n_shots}: tổng slot = {sum(quota)}, "
                           f"phải là {ANSWERS_PER_QUERY}")
    covered = sum(n for n, _ in slot_budget.SLOT_BUDGET)
    return True, (f"{slot_budget.SLOT_BUDGET} → đủ {ANSWERS_PER_QUERY} slot, "
                  f"phủ {covered} shot")


def check_scoring_formula() -> tuple[bool | None, str]:
    """Công thức Final Score phải khớp VÍ DỤ CÓ ĐÁP SỐ của BTC.

    Tài liệu vòng Sơ tuyển mục 2.2: câu 1 được 0.5, câu 3 được 0.8 (cao nhất),
    câu 15 được 0.6 → Final = (0.5 + 0.8 + 0.8 + 0.8 + 0.8)/5 = 0.74.

    Vì sao kiểm lại ở preflight dù đã có unit test: đây là con số biến mọi số
    liệu nội bộ thành điểm thi. Một lần sửa nhầm `K_THRESHOLDS` là toàn bộ bảng
    điểm dev sai lệch mà không có gì đỏ lên — và cả nhóm sẽ tune theo số sai.
    """
    import data.config.scoring as scoring

    r_scores = [0.0] * 100
    r_scores[0], r_scores[2], r_scores[14] = 0.5, 0.8, 0.6
    got = scoring.final_score(r_scores)
    if abs(got - 0.74) > 1e-9:
        return False, f"Final = {got:.4f}, ví dụ BTC = 0.74 — công thức chấm đã lệch"
    if scoring.K_THRESHOLDS != (1, 5, 20, 50, 100):
        return False, (f"K_THRESHOLDS = {scoring.K_THRESHOLDS}, "
                       "BTC quy định (1, 5, 20, 50, 100)")
    return True, "khớp ví dụ có đáp số của BTC (0.74)"


def check_submit_format() -> tuple[bool | None, str]:
    """Hằng định dạng phải khớp thứ BTC công bố.

    100 câu/truy vấn (mục 2), CSV, answer ≤ 100 ký tự. Ba hằng này nằm ở ba chỗ
    dùng khác nhau (validator, allocator, tầng format) nhưng chỉ được khai MỘT
    lần — mục này gác chuyện ai đó tiện tay sửa một bản sao.
    """
    import data.config.submit_format as submit_format

    if submit_format.ANSWERS_PER_QUERY != 100:
        return False, (f"ANSWERS_PER_QUERY = {submit_format.ANSWERS_PER_QUERY}, "
                       "BTC cho tối đa 100")
    if submit_format.SUBMIT_EXT != "csv":
        return False, f"SUBMIT_EXT = {submit_format.SUBMIT_EXT!r}, BTC chốt CSV"
    if set(submit_format.TASK_TYPES) != {"KIS", "QA", "TRAKE"}:
        return False, f"TASK_TYPES = {submit_format.TASK_TYPES}"
    return True, (f"{submit_format.ANSWERS_PER_QUERY} dòng/truy vấn · "
                  f".{submit_format.SUBMIT_EXT} · "
                  f"answer ≤ {submit_format.ANSWER_MAX_CHARS} ký tự")


# ============================================================ CHECKLIST

CHECKLIST: list[Check] = [
    Check("A. Môi trường", "interpreter Python", check_python),
    Check("A. Môi trường", "thư viện lõi", check_core_libs),
    Check("A. Môi trường", "runtime Q&A", check_qa_runtime),
    Check("A. Môi trường", "thư viện tuỳ chọn", check_optional_libs,
          required_in_release=False),

    Check("B. Hạ tầng", "Elasticsearch", check_elasticsearch, needs_infra=True),
    Check("B. Hạ tầng", "Milvus", check_milvus, needs_infra=True),
    Check("B. Hạ tầng", "API /health", check_api_health, needs_infra=True,
          required_in_release=False),

    Check("C. Dữ liệu", "parquet lõi", check_parquet),
    Check("C. Dữ liệu", "kèm .meta.json", check_meta_json),
    Check("C. Dữ liệu", "frame_map", check_frame_map),
    Check("C. Dữ liệu", "video_info", check_video_info),
    Check("C. Dữ liệu", "ảnh Q&A/UI", check_frame_assets),

    Check("D. Vector", "encoder đang chạy", check_vector_backend, needs_infra=True),
    Check("D. Vector", "index cùng không gian", check_clip_meta, needs_infra=True),
    Check("D. Vector", "vector đã chuẩn hoá L2", check_vector_norm, needs_infra=True),

    Check("E. Đường nộp", "3 dạng bài → .zip", check_submission_path),

    Check("F. Độ trễ", f"1 truy vấn ≤ {LATENCY_BUDGET_S:.0f}s",
          check_latency, needs_infra=True),

    Check("G. Cấu hình", "bảng slot đủ 100", check_slot_budget),
    Check("G. Cấu hình", "công thức Final Score", check_scoring_formula),
    Check("G. Cấu hình", "hằng định dạng nộp", check_submit_format),
]


def run_check(check: Check, quick: bool, profile: str = "development") -> CheckResult:
    """Chạy một mục, KHÔNG BAO GIỜ để ngoại lệ thoát ra.

    Vì sao nuốt mọi ngoại lệ: một mục ném lỗi mà giết cả script thì các mục phía
    sau không bao giờ được chạy — người vận hành sửa xong lỗi đầu lại phát hiện
    lỗi thứ hai, sửa xong lại lỗi thứ ba. Ba vòng như vậy lúc 2 giờ sáng là hết
    đêm. Chạy hết một lượt rồi đưa TOÀN BỘ danh sách việc phải sửa.

    Ngoại lệ = FAIL, không phải SKIP: mục kiểm mà tự nó gãy thì đúng là có gì đó
    hỏng, chỉ khác là hỏng theo kiểu chưa lường trước. Ngoại lệ KẾT NỐI ở mục
    `needs_infra` là ngoại lệ duy nhất được hạ xuống SKIP — và mục nào phân biệt
    được rõ hơn thì tự xử lý lấy (xem `check_elasticsearch`).
    """
    if quick and check.needs_infra:
        status = FAIL if profile == "release" and check.required_in_release else SKIP
        return CheckResult(
            check.group,
            check.name,
            status,
            "--quick: chưa chạy mục cần Docker/model"
            + (" (release bắt buộc kiểm)" if status == FAIL else ""),
        )

    t0 = time.perf_counter()
    try:
        ok, detail = check.fn()
    except Exception as e:
        ms = (time.perf_counter() - t0) * 1000
        is_conn_error = isinstance(e, (ConnectionError, OSError))
        can_skip = is_conn_error and check.needs_infra
        status = (
            SKIP
            if can_skip and not (profile == "release" and check.required_in_release)
            else FAIL
        )
        return CheckResult(check.group, check.name, status,
                           f"{type(e).__name__}: {str(e).splitlines()[0][:160]}", ms)
    ms = (time.perf_counter() - t0) * 1000
    if ok is None:
        status = FAIL if profile == "release" and check.required_in_release else SKIP
        if status == FAIL:
            detail = f"release bắt buộc kiểm: {detail}"
        return CheckResult(check.group, check.name, status, detail, ms)
    return CheckResult(check.group, check.name, PASS if ok else FAIL, detail, ms)


def print_table(results: list[CheckResult]) -> None:
    current_group = ""
    for r in results:
        if r.group != current_group:
            current_group = r.group
            print(f"\n{current_group}")
        mark = {PASS: "  ĐẠT   ", FAIL: "  HỎNG  ", SKIP: "  bỏ qua"}[r.status]
        elapsed = f"{r.ms:>7.0f}ms" if r.ms >= 1 else " " * 9
        print(f"{mark} {r.name:<28}{elapsed}  {r.detail}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Preflight check trước giờ nộp (D6.1) — chạy thật, không tick tay."
    )
    parser.add_argument("--quick", action="store_true",
                        help="bỏ mọi mục cần Docker/model nặng (chạy được ở mọi máy)")
    parser.add_argument(
        "--profile",
        choices=("development", "release"),
        default="development",
        help=("development cho phép SKIP có giải thích; release biến mọi mục "
              "bắt buộc chưa kiểm thành FAIL"),
    )
    parser.add_argument("--json", action="store_true",
                        help="in JSON cho log diễn tập E6.1")
    args = parser.parse_args()

    results = [run_check(c, args.quick, args.profile) for c in CHECKLIST]
    failed = [r for r in results if r.status == FAIL]
    skipped = [r for r in results if r.status == SKIP]

    if args.json:
        print(json.dumps({
            "passed": sum(1 for r in results if r.status == PASS),
            "failed": len(failed),
            "skipped": len(skipped),
            "profile": args.profile,
            "checks": [vars(r) for r in results],
        }, ensure_ascii=False, indent=2))
        return 1 if failed else 0

    print(
        f"PREFLIGHT — {len(CHECKLIST)} mục · profile={args.profile}"
        + ("  [--quick]" if args.quick else "")
    )
    print_table(results)

    print("\n" + "=" * 72)
    print(f"ĐẠT {len(results) - len(failed) - len(skipped)} · "
          f"HỎNG {len(failed)} · BỎ QUA {len(skipped)}")
    if skipped:
        print("\nCHƯA KIỂM (không phải đã đạt):")
        for r in skipped:
            print(f"  - {r.group} / {r.name}: {r.detail}")
    if failed:
        print("\nPHẢI SỬA TRƯỚC KHI NỘP:")
        for r in failed:
            print(f"  - {r.group} / {r.name}: {r.detail}")
        return 1

    print("\nKhông mục nào hỏng." + (
        "  ⚠️ Nhưng còn mục CHƯA KIỂM — chạy lại không kèm --quick khi hạ tầng lên."
        if skipped else "  Sẵn sàng nộp."))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
