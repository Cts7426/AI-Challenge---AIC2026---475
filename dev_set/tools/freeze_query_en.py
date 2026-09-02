"""Đóng băng bản dịch VI→EN của bộ đề chính thức thành MỘT file cố định.

===== Vì sao phải đóng băng thay vì để search() tự dịch mỗi lần =====
`eval_official.py` gọi `search(query_text, query_en=None)`, và `search()` sẽ tự
dịch qua `llm()`. Điều đó biến bản dịch thành một BIẾN TRÔI trong phép đo:

  1. Hết credit / mất mạng / 429 → `_search_core()` NUỐT lỗi và rơi về nguyên
     câu tiếng Việt. Nhánh vector CLIP (model tiếng Anh) tụt điểm IM LẶNG, còn
     SigLIP2 (đa ngữ) không hề gì. So hai encoder như vậy là so hai thứ khác
     nhau và tự phong cho SigLIP2 phần thắng nó chưa chắc có.
  2. Kể cả khi LLM chạy trơn, hai lần gọi có thể ra hai câu khác nhau. Chênh
     lệch đo được lúc đó lẫn cả "encoder khác nhau" và "câu dịch khác nhau".

Đóng băng một lần rồi truyền cho MỌI nhánh bake-off qua `--query-en` thì encoder
là biến DUY NHẤT còn lại — đúng luật "một biến mỗi lần" của `AGENTS.md`.

===== Vì sao dùng lại đúng `translate_to_english()` =====
Bản đóng băng phải bằng ĐÚNG thứ production sinh ra, nếu không phép đo mô tả một
hệ thống không tồn tại. Nên file này KHÔNG tự viết prompt — nó gọi thẳng hàm
production `backend.retrieval.text_query.translate_to_english()`.

===== Fail-closed =====
Thiếu dù một câu là KHÔNG ghi file. Một file dịch thiếu câu trông y hệt file đủ,
và câu thiếu sẽ lặng lẽ rơi về tiếng Việt ở đúng chỗ ta đang cố loại bỏ biến đó.
Thà không có file và biết mình không có.

===== Chạy =====
    export LLM_BACKEND=api
    export LLM_API_MODEL=claude-haiku-4-5     # model nào cũng được, miễn GHI LẠI
    export ANTHROPIC_API_KEY=...              # trong ĐÚNG terminal sẽ chạy

    python -m dev_set.tools.freeze_query_en --part p1
    python -m dev_set.tools.freeze_query_en --part all      # cả p1 lẫn p2

Chạy lại chỉ dịch những câu còn thiếu (idempotent) — trừ khi `--force`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

GT_PATH = REPO_ROOT / "dev_set" / "ground_truth" / "official_r1r2.jsonl"
OUT_PATH = REPO_ROOT / "dev_set" / "ground_truth" / "official_r1r2.en.json"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_gt(part: str) -> list[dict]:
    """Đọc GT, lọc theo `part`. KHÔNG lọc theo confidence: bản dịch dùng chung
    cho mọi mức lọc phía sau, dịch dư vài câu rẻ hơn nhiều so với phải chạy lại
    khi đổi `--min-confidence`."""
    if not GT_PATH.is_file():
        raise SystemExit(f"KHÔNG THẤY {GT_PATH}")
    out = []
    for line in GT_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if part != "all" and r.get("part") != part:
            continue
        if not r.get("query_text"):
            continue
        out.append(r)
    return out


def _current_model() -> tuple[str, str]:
    """(backend, model) đang được cấu hình — ghi vào `_meta` để đọc lại biết ai dịch.

    Đọc từ os.environ chứ không hỏi adapter: adapter chỉ chốt model lúc gọi thật,
    còn ta cần in ra TRƯỚC khi tốn một đồng nào để người chạy kịp nhìn và huỷ.
    """
    backend = (os.environ.get("LLM_BACKEND") or "").strip()
    if not backend:
        raise SystemExit(
            "LLM_BACKEND chưa được set tường minh.\n"
            "  export LLM_BACKEND=api        (hoặc gemini / local)\n"
            "Không đoán hộ: chọn provider là quyết định của người vận hành, và một\n"
            "biến bị quên không được âm thầm rơi về mặc định."
        )
    env_name = {
        "api": "LLM_API_MODEL",
        "gemini": "LLM_GEMINI_MODEL",
        "local": "LLM_LOCAL_MODEL",
    }.get(backend)
    if env_name is None:
        raise SystemExit(f"LLM_BACKEND={backend!r} không hợp lệ (api / gemini / local).")
    model = (os.environ.get(env_name) or "").strip()
    if not model:
        raise SystemExit(
            f"Thiếu {env_name}. Phải chọn model tường minh để bản đóng băng ghi được\n"
            "ai đã dịch — cùng lý do run.py bắt buộc điều này trước mỗi batch."
        )
    return backend, model


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--part", choices=["p1", "p2", "all"], default="p1")
    ap.add_argument("--force", action="store_true",
                    help="dịch lại cả những câu đã có trong file")
    ap.add_argument("--out", type=Path, default=OUT_PATH)
    args = ap.parse_args()

    backend, model = _current_model()
    gts = _load_gt(args.part)
    if not gts:
        raise SystemExit(f"Không có câu nào cho --part {args.part}")

    da_co: dict[str, str] = {}
    if args.out.is_file() and not args.force:
        try:
            da_co = {
                k: v for k, v in json.loads(args.out.read_text(encoding="utf-8")).items()
                if k != "_meta" and isinstance(v, str)
            }
        except Exception as e:
            print(f"  [cảnh báo] không đọc lại được {args.out.name} ({e}) — dịch lại từ đầu")

    can_dich = [g for g in gts if g["query_id"] not in da_co]
    print(f"{len(gts)} câu · đã có {len(gts) - len(can_dich)} · cần dịch {len(can_dich)}")
    print(f"backend={backend} · model={model}")
    if not can_dich:
        print("Không có gì để dịch.")

    # Import muộn: chỉ chạm adapter/LLM sau khi đã qua hết kiểm tra đầu vào.
    from backend.retrieval.text_query import translate_to_english

    ket_qua: dict[str, str] = dict(da_co)
    that_bai: list[tuple[str, str]] = []
    for i, g in enumerate(can_dich, 1):
        qid = g["query_id"]
        try:
            en = translate_to_english(g["query_text"]).strip()
        except Exception as e:
            that_bai.append((qid, f"{type(e).__name__}: {e}"))
            print(f"  [{i}/{len(can_dich)}] ✗ {qid} — {type(e).__name__}: {e}", flush=True)
            continue
        if not en:
            that_bai.append((qid, "bản dịch rỗng"))
            print(f"  [{i}/{len(can_dich)}] ✗ {qid} — bản dịch rỗng", flush=True)
            continue
        ket_qua[qid] = en
        print(f"  [{i}/{len(can_dich)}] ✓ {qid} — {en[:70]}", flush=True)

    thieu = [g["query_id"] for g in gts if g["query_id"] not in ket_qua]
    if thieu:
        # FAIL-CLOSED: không ghi file nửa vời. File thiếu câu trông y hệt file đủ,
        # và câu thiếu sẽ lặng lẽ rơi về tiếng Việt trong eval — đúng thứ file này
        # sinh ra để loại bỏ.
        print(f"\nKHÔNG GHI FILE: còn {len(thieu)}/{len(gts)} câu chưa có bản dịch.")
        for qid, ly_do in that_bai[:10]:
            print(f"    {qid:24s} {ly_do}")
        print("\nSửa nguyên nhân (thường là thiếu API key / hết credit) rồi chạy lại — "
              "các câu đã dịch được giữ nguyên, chỉ dịch phần còn thiếu.")
        return 1

    payload = {
        "_meta": {
            "created_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "part": args.part,
            "n": len(ket_qua),
            "llm_backend": backend,
            "llm_model": model,
            "translate_fn": "backend.retrieval.text_query.translate_to_english",
            "gt_source": str(GT_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
            "gt_sha256": _sha256_file(GT_PATH),
        },
        **{k: ket_qua[k] for k in sorted(ket_qua)},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"\nĐã ghi {len(ket_qua)} bản dịch → {args.out}")
    print(f"  SHA-256 GT nguồn: {payload['_meta']['gt_sha256'][:16]}...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
