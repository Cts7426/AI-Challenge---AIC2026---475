# scripts/make_queries.py — gói đề BTC → file truy vấn cho run.py
#
# ===== Vì sao cần file này =====
# `run.py` đòi JSON/JSONL với đúng ba khoá `query_id`, `task_type`, `query_vi`.
# BTC phát đề dưới dạng nào thì tới lúc mở gói mới biết: có mùa là một thư mục
# .txt (mỗi câu một file), có mùa là .csv một dòng một câu. Gõ tay 30 câu lúc
# 19:35 là cách chắc chắn nhất để sai `task_type` hoặc trùng `query_id` — hai
# lỗi mà run.py chỉ báo SAU khi đã kiểm, còn sai kiểu bài thì đi hết pipeline.
#
# Script này CHỈ đọc và ghi file truy vấn. Không đụng parquet, index hay
# submission — chạy sai thì chạy lại, không hỏng gì.
#
# ===== Chạy =====
#   python scripts/make_queries.py <đường dẫn gói đề> --out data/queries/round1.jsonl
#   python scripts/make_queries.py queries/ --out ... --task KIS   # ép cả gói một kiểu
#   python scripts/make_queries.py de.csv --out ... --preview       # xem, chưa ghi
#
# Nhận vào:
#   - thư mục .txt : mỗi file một câu; tên file quyết định query_id và task_type
#   - .csv / .tsv  : tự dò cột id / kiểu bài / mô tả (VI, EN)
#   - .json/.jsonl : chuẩn hoá tên khoá lệch (type → task_type, text → query_vi)
#
# LUÔN in bảng xem trước rồi mới ghi. Người thao tác phải liếc qua cột `kiểu`
# trước khi bấm chạy — đoán sai kiểu bài là nộp sai định dạng, 0 điểm cả câu.

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from data.config.submit_format import TASK_TYPES, suggest_filename  # noqa: E402

# Tên khoá/cột mà các mùa trước từng dùng, gom về một chỗ để khỏi sửa code lúc thi.
ALIAS_ID = ("query_id", "id", "query", "ten", "name", "stt", "no")
ALIAS_TASK = ("task_type", "task", "type", "kieu", "loai", "dang")
ALIAS_VI = ("query_vi", "vi", "text", "content", "mo_ta", "description", "cau_hoi")
ALIAS_EN = ("query_en", "en", "english", "text_en")
ALIAS_N_EVENTS = ("n_events", "num_events", "event_count", "so_su_kien")


def _event_list(value) -> list[str] | None:
    """Chỉ nhận list thật hoặc JSON array; không đoán cách tách nội dung BTC."""
    if isinstance(value, list):
        items = value
    elif isinstance(value, str) and value.strip().startswith("["):
        try:
            items = json.loads(value)
        except json.JSONDecodeError:
            return None
        if not isinstance(items, list):
            return None
    else:
        return None
    out = [str(item).strip() for item in items]
    return out if out and all(out) else None


def _official_task_from_id(query_id: str) -> str | None:
    """Tên file BTC dùng hậu tố -kis/-qa/-trake; id khác vẫn được dùng cho dev."""
    match = re.search(r"-(kis|qa|trake)$", query_id.strip(), flags=re.IGNORECASE)
    return match.group(1).upper() if match else None


def _doan_task(text: str) -> str | None:
    """Đoán kiểu bài từ một chuỗi bất kỳ (tên file, id, ô trong bảng).

    Chỉ đoán khi thấy từ khoá rõ ràng. Không đoán mò theo nội dung câu hỏi:
    đoán sai im lặng còn tệ hơn bắt người thao tác gõ thêm một cờ.
    """
    t = text.lower()
    if "trake" in t:
        return "TRAKE"
    if "qa" in t or "q&a" in t or "hoi" in t:
        return "QA"
    if "kis" in t or "textual" in t:
        return "KIS"
    return None


def _chuan_hoa(raw: dict, stt: int, task_ep: str | None) -> dict:
    """Một bản ghi thô (dict từ csv/json) → bản ghi đúng schema run.py."""
    thap = {str(k).strip().lower(): v for k, v in raw.items()}

    def lay(aliases):
        for a in aliases:
            v = thap.get(a)
            if v is not None and str(v).strip():
                return str(v).strip()
        return ""

    qid = lay(ALIAS_ID) or f"q{stt:03d}"
    task = task_ep or _doan_task(lay(ALIAS_TASK)) or _doan_task(qid)
    ban_ghi = {
        "query_id": qid,
        "task_type": task,          # có thể None → báo lỗi ở bước kiểm bên dưới
        "query_vi": lay(ALIAS_VI),
    }
    if lay(ALIAS_EN):
        ban_ghi["query_en"] = lay(ALIAS_EN)
    # Chỉ giữ metadata TRAKE nếu input nói tường minh; không suy số event từ câu.
    ds = _event_list(thap.get("event_descs") or thap.get("events"))
    if ds:
        ban_ghi["event_descs"] = ds
    n_raw = lay(ALIAS_N_EVENTS)
    if n_raw:
        try:
            ban_ghi["n_events"] = int(n_raw)
        except ValueError:
            ban_ghi["n_events"] = n_raw  # kiem() báo lỗi có query_id rõ ràng
    elif ds:
        ban_ghi["n_events"] = len(ds)
    return ban_ghi


def _doc_thu_muc_txt(path: Path, task_ep: str | None) -> list[dict]:
    """Thư mục .txt: mỗi file một câu. Tên file là nguồn duy nhất của id/kiểu."""
    ban_ghi = []
    for i, f in enumerate(sorted(path.glob("*.txt")), 1):
        noi_dung = f.read_text(encoding="utf-8-sig").strip()
        if not noi_dung:
            continue
        ban_ghi.append({
            "query_id": f.stem,
            "task_type": task_ep or _doan_task(f.stem),
            "query_vi": noi_dung,
        })
    return ban_ghi


def _doc_mot_txt(path: Path, task_ep: str | None) -> list[dict]:
    """Một file .txt chỉ sinh đúng một query, không hút nhầm mọi file cùng thư mục."""
    noi_dung = path.read_text(encoding="utf-8-sig").strip()
    if not noi_dung:
        raise SystemExit(f"[đầu vào] File truy vấn rỗng: {path}")
    return [{
        "query_id": path.stem,
        "task_type": task_ep or _doan_task(path.stem),
        "query_vi": noi_dung,
    }]


def _doc_bang(path: Path, task_ep: str | None) -> list[dict]:
    """CSV/TSV có dòng tiêu đề. Tự dò dấu phân cách để khỏi hỏi."""
    raw = path.read_text(encoding="utf-8-sig")
    dau = "\t" if path.suffix.lower() == ".tsv" or raw.count("\t") > raw.count(",") else ","
    rows = list(csv.DictReader(raw.splitlines(), delimiter=dau))
    return [_chuan_hoa(r, i, task_ep) for i, r in enumerate(rows, 1) if any(r.values())]


def _doc_json(path: Path, task_ep: str | None) -> list[dict]:
    raw = path.read_text(encoding="utf-8-sig").strip()
    if path.suffix.lower() == ".jsonl":
        data = [json.loads(d) for d in raw.splitlines() if d.strip()]
    else:
        data = json.loads(raw)
        if isinstance(data, dict):          # {"queries": [...]} cũng nhận
            data = next((v for v in data.values() if isinstance(v, list)), [])
    return [_chuan_hoa(r, i, task_ep) for i, r in enumerate(data, 1)]


def doc_goi_de(path: Path, task_ep: str | None) -> list[dict]:
    if path.is_dir():
        ban_ghi = _doc_thu_muc_txt(path, task_ep)
        if not ban_ghi:
            raise SystemExit(f"[đầu vào] Không thấy .txt nào trong {path}")
        return ban_ghi
    suffix = path.suffix.lower()
    if suffix in (".csv", ".tsv"):
        return _doc_bang(path, task_ep)
    if suffix in (".json", ".jsonl"):
        return _doc_json(path, task_ep)
    if suffix == ".txt":
        return _doc_mot_txt(path, task_ep)
    raise SystemExit(f"[đầu vào] Chưa hỗ trợ đuôi '{suffix}'. Nhận: thư mục .txt, .csv, .tsv, .json, .jsonl")


def kiem(ban_ghi: list[dict]) -> list[str]:
    """Kiểm đúng những gì run.py sẽ kiểm, nhưng báo SỚM hơn và gọn hơn."""
    loi, da_thay = [], {}
    for i, q in enumerate(ban_ghi, 1):
        qid = q.get("query_id") or f"(câu {i})"
        if not str(q.get("query_vi", "")).strip():
            loi.append(f"[{qid}] query_vi rỗng")
        if q.get("task_type") not in TASK_TYPES:
            loi.append(f"[{qid}] không đoán được task_type (đang: {q.get('task_type')!r}) "
                       f"— thêm --task hoặc sửa tên file/cột cho có chữ KIS/QA/TRAKE")
        qid_text = str(qid)
        if qid_text != qid_text.strip():
            loi.append(f"[{qid!r}] query_id có khoảng trắng đầu/cuối — tên CSV sẽ sai")
        try:
            suggest_filename(qid_text)
        except ValueError as e:
            loi.append(str(e))
        official_task = _official_task_from_id(qid_text)
        if official_task and q.get("task_type") in TASK_TYPES and q.get("task_type") != official_task:
            loi.append(
                f"[{qid}] hậu tố tên file là {official_task} nhưng task_type={q.get('task_type')}"
            )

        if q.get("task_type") == "TRAKE":
            events = q.get("event_descs")
            n_events = q.get("n_events")
            if events is not None and (
                not isinstance(events, list) or len(events) < 2
                or any(not str(event).strip() for event in events)
            ):
                loi.append(f"[{qid}] event_descs phải là list ít nhất 2 chuỗi không rỗng")
            if isinstance(n_events, bool) or not isinstance(n_events, int) or n_events < 2:
                loi.append(
                    f"[{qid}] TRAKE cần n_events nguyên >=2; BTC chưa công bố format input "
                    "nên phải cung cấp tường minh bằng cột n_events hoặc --n-events ID=N"
                )
            if isinstance(events, list) and isinstance(n_events, int) and len(events) != n_events:
                loi.append(
                    f"[{qid}] n_events={n_events} nhưng event_descs có {len(events)} phần tử"
                )
        if qid in da_thay:
            loi.append(f"[{qid}] trùng query_id với câu {da_thay[qid]}")
        da_thay[qid] = i
    return loi


def in_bang(ban_ghi: list[dict]) -> None:
    print(f"\n{len(ban_ghi)} câu đọc được:\n")
    print(f"  {'query_id':<22} {'kiểu':<7} {'EN':<4} {'N':<3} {'events':<7} mô tả")
    print("  " + "-" * 104)
    for q in ban_ghi:
        mo_ta = re.sub(r"\s+", " ", q.get("query_vi", ""))[:58]
        events = q.get("event_descs")
        print(f"  {str(q.get('query_id'))[:22]:<22} {str(q.get('task_type')):<7} "
              f"{'có' if q.get('query_en') else '—':<4} "
              f"{str(q.get('n_events') or '—'):<3} "
              f"{str(len(events)) if isinstance(events, list) else '—':<7} {mo_ta}")
    dem = {t: sum(1 for q in ban_ghi if q.get("task_type") == t) for t in TASK_TYPES}
    print("\n  Tổng: " + " · ".join(f"{t}={n}" for t, n in dem.items()))


def main() -> int:
    ap = argparse.ArgumentParser(description="Gói đề BTC → file truy vấn cho run.py")
    ap.add_argument("nguon", help="thư mục .txt, hoặc file .csv/.tsv/.json/.jsonl")
    ap.add_argument("--out", help="file .jsonl để ghi ra (bỏ trống = chỉ xem)")
    ap.add_argument("--task", choices=TASK_TYPES,
                    help="ép toàn bộ gói về một kiểu bài, khi tên file không nói gì")
    ap.add_argument(
        "--n-events", action="append", default=[], metavar="QUERY_ID=N",
        help=("khai báo số event TRAKE khi gói .txt không có field cấu trúc; "
              "có thể lặp lại, ví dụ --n-events query-4-trake=4"),
    )
    ap.add_argument("--preview", action="store_true", help="chỉ in bảng, không ghi")
    args = ap.parse_args()

    ban_ghi = doc_goi_de(Path(args.nguon), args.task)

    by_id = {str(q.get("query_id")): q for q in ban_ghi}
    override_errors = []
    seen_overrides: dict[str, int] = {}
    for raw_override in args.n_events:
        try:
            query_id, raw_n = raw_override.rsplit("=", 1)
            query_id = query_id.strip()
            n_events = int(raw_n)
        except (ValueError, AttributeError):
            override_errors.append(f"--n-events {raw_override!r} phải có dạng QUERY_ID=N")
            continue
        if query_id not in by_id:
            override_errors.append(f"--n-events nhắc query_id không tồn tại: {query_id}")
            continue
        if query_id in seen_overrides and seen_overrides[query_id] != n_events:
            override_errors.append(f"--n-events mâu thuẫn cho {query_id}")
            continue
        seen_overrides[query_id] = n_events
        by_id[query_id]["n_events"] = n_events

    in_bang(ban_ghi)

    loi = override_errors + kiem(ban_ghi)
    if loi:
        print("\n✗ Chưa ghi được — sửa các lỗi sau:")
        for d in loi[:20]:
            print("   ", d)
        return 2

    if args.preview or not args.out:
        print("\n(chỉ xem — thêm --out <file.jsonl> để ghi)")
        return 0

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for q in ban_ghi:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")
    print(f"\n✓ Đã ghi {len(ban_ghi)} câu → {out}")
    print(f"  Chạy tiếp: python run.py --queries {out} --out submissions/round1 "
          f"--zip --qa-submission-policy robust")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
