"""Cách ly các bản dịch VI→EN hỏng đang nằm trong cache `llm()`.

VÌ SAO CẦN: cache khoá theo hash(prompt+model+…) và KHÔNG biết nội dung bên trong
tốt hay xấu. Trước 02/09 backend Gemini còn dính lỗi "token thinking ăn hết
max_output_tokens" (đã sửa, xem backend/llm/adapter.py), sinh ra những bản dịch
cụt như 'Lions and zook' cho câu về sư tử ở sở thú London. Sửa adapter KHÔNG dọn
được rác cũ — lần gọi sau vẫn trúng cache và nhận lại đúng chuỗi hỏng đó.
Đợt 2 thi 28/08, tức là SAU khi rác được ghi.

CÁCH TÌM — dựng lại khoá, không đoán theo nội dung:
    Cache chỉ lưu kết quả, không lưu câu hỏi. Nhưng prompt của
    `translate_to_english()` là hàm thuần của `query_text`, nên với mỗi câu trong
    ground truth ta DỰNG LẠI ĐÚNG khoá cache và soi thẳng entry đó.
    Nhờ vậy không đụng nhầm entry của TRAKE/Q&A — những chỗ mà output ngắn
    ('Plating food', 'Racers starting') là hoàn toàn hợp lệ.

KHÔNG XOÁ, chỉ CHUYỂN sang thư mục cách ly — để còn dựng lại được lịch sử một
lượt chạy cũ nếu cần đối chiếu.

Chạy thử (mặc định, không đụng gì):
    python scripts/purge_bad_translations.py
Làm thật:
    python scripts/purge_bad_translations.py --apply
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backend.llm.adapter import DEFAULT_EFFORT, _cache_key  # noqa: E402
# Dùng CHUNG phép kiểm với production. Hai bản luật riêng là hai bản sẽ lệch
# nhau, rồi script báo sạch trong khi runtime vẫn từ chối (hoặc ngược lại).
from backend.retrieval.text_query import ly_do_ban_dich_hong  # noqa: E402

GT_PATH = REPO_ROOT / "dev_set" / "ground_truth" / "official_r1r2.jsonl"
CACHE_DIR = REPO_ROOT / "data" / "cache" / "llm"
QUARANTINE = REPO_ROOT / "data" / "cache" / "llm_quarantine"

# Mọi (backend, model) từng chạy trong repo. Cache khoá theo cả hai nên một câu
# có thể có nhiều entry — phải soi hết, không chỉ backend đang bật.
CAU_HINH = [
    ("gemini", "gemini-3.6-flash"),
    ("gemini", "gemini-2.5-flash"),
    ("api", "claude-haiku-4-5"),
    ("api", "claude-sonnet-5"),
    ("api", "claude-opus-5"),
]

MAX_TOKENS_DICH = 128  # đúng giá trị text_query.translate_to_english() truyền vào


def _prompt_dich(query_vi: str) -> str:
    """Sao y prompt trong text_query.translate_to_english().

    Cố tình chép lại thay vì import: nếu prompt production đổi thì khoá cache cũ
    KHÔNG còn dựng lại được, và ta phải biết điều đó (script báo 0 entry) chứ
    không phải im lặng soi nhầm khoá mới.
    """
    return (
        "Translate this Vietnamese description of a video moment into ONE short "
        "English phrase for a CLIP image search engine. Keep it visual and concrete. "
        "Reply with ONLY the English phrase, nothing else.\n\n"
        f"Vietnamese: {query_vi}"
    )


def _khoa(prompt: str, backend: str, model: str) -> str:
    return _cache_key({
        "prompt": prompt, "schema": None, "model": model, "n": 1,
        "effort": DEFAULT_EFFORT, "max_tokens": MAX_TOKENS_DICH, "backend": backend,
        "temperature": 0, "images": [],
    })


def ly_do_hong(ban_dich: str, query_vi: str) -> str | None:
    """Uỷ thác cho phép kiểm của production — xem text_query.ly_do_ban_dich_hong."""
    return ly_do_ban_dich_hong(ban_dich, query_vi)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true",
                    help="chuyển thật; không có cờ này thì chỉ liệt kê")
    args = ap.parse_args()

    if not GT_PATH.is_file():
        print(f"Không thấy {GT_PATH.relative_to(REPO_ROOT)} — không dựng lại khoá được.")
        return 1

    gts = [json.loads(l) for l in GT_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"{len(gts)} câu ground truth × {len(CAU_HINH)} cấu hình model\n")

    thay, hong = 0, []
    for g in gts:
        prompt = _prompt_dich(g["query_text"])
        for backend, model in CAU_HINH:
            f = CACHE_DIR / f"{_khoa(prompt, backend, model)}.json"
            if not f.is_file():
                continue
            try:
                out = json.loads(f.read_text(encoding="utf-8"))["output"][0]
            except Exception:
                continue
            thay += 1
            ly_do = ly_do_hong(str(out), g["query_text"])
            if ly_do:
                hong.append((f, g["query_id"], model, str(out), ly_do))

    print(f"Tìm thấy {thay} bản dịch trong cache · {len(hong)} bản hỏng\n")
    for f, qid, model, out, ly_do in hong:
        print(f"  {qid}  [{model}]")
        print(f"      {out!r}")
        print(f"      └─ {ly_do}  [{f.name[:12]}]")

    if not hong:
        print("Không có bản dịch hỏng nào ứng với ground truth hiện tại.")
        return 0

    if not args.apply:
        print(f"\nCHẠY THỬ — chưa đụng gì. Thêm --apply để chuyển "
              f"{len(hong)} entry sang {QUARANTINE.name}/.")
        return 0

    QUARANTINE.mkdir(parents=True, exist_ok=True)
    for f, *_ in hong:
        shutil.move(str(f), str(QUARANTINE / f.name))
    print(f"\nĐã chuyển {len(hong)} entry → {QUARANTINE.relative_to(REPO_ROOT)}/")
    print("Lần gọi sau sẽ dịch lại thật thay vì nhận lại bản hỏng.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
