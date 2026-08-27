"""Bộ đề BTC (thư mục .txt) → JSONL cho run.py --queries.

Đúng định dạng gói `SOTUYEN*-bo-de-thi/`: MỖI CÂU HỎI là MỘT file riêng, tên
`query-p1-<N>-<kis|qa|trake>.txt`. Nội dung file:
  - KIS/QA:  một đoạn văn (có thể xuống dòng nhiều lần), toàn bộ là query_vi.
  - TRAKE:   dòng 1 = mô tả tổng quan; các dòng sau `E1 ...`, `E2 ...`, `E3 ...`
             là từng khoảnh khắc — script tách sẵn thành `event_descs`.

run.py chỉ đọc .json (list) hoặc .jsonl, cần khoá `task_type` + `query_vi`,
và (bất biến `suggest_filename()` trong `data/config/submit_format.py`)
**`query_id` PHẢI đúng y nguyên tên file BTC phát** (không đuôi `.txt`) —
tự đặt id khác là nộp sai tên file, BTC không ghép được đáp án với câu hỏi.
Script này lấy `query_id` = tên file (bỏ `.txt`), không suy diễn gì thêm.

Ngoài ra vẫn đọc được `.txt` kiểu JSON-list / JSONL (một object mỗi dòng,
khoá `type` thay cho `task_type`) — phòng khi BTC đổi cách phát ở đợt sau.

Kiểm ngặt bằng đúng luật của run.py (query_id/task_type/query_vi không rỗng,
task_type hợp lệ, query_id không trùng, TRAKE ≥2 sự kiện) TRƯỚC khi ghi —
sai ở đây rẻ hơn nhiều so với sai sau khi đã tốn LLM/Milvus.

Chạy:
    python scripts/txt_to_run_queries.py SOTUYEN1-bo-de-thi -o dev_set/queries/sotuyen1.jsonl
    python scripts/txt_to_run_queries.py queries001.txt -o out.jsonl   # chế độ JSON/JSONL cũ
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

TASK_TYPES = ("KIS", "QA", "TRAKE")
_SENTENCE_SPLIT = re.compile(r"\s*\.\s+|\s*\.\s*$")
_EVENT_LINE = re.compile(r"^E\d+\s*(.*)$")
_FILENAME_TASK = re.compile(r"-(kis|qa|trake)$", re.IGNORECASE)


def _load_query_dir(dir_path: Path) -> list[dict]:
    """Một file BTC = một truy vấn. Tên file → query_id + task_type."""
    files = sorted(dir_path.glob("*.txt"))
    if not files:
        raise SystemExit(f"[{dir_path}] không có file .txt nào")

    data: list[dict] = []
    for path in files:
        stem = path.stem  # bỏ .txt — chính là query_id BTC dùng để ghép điểm
        m = _FILENAME_TASK.search(stem)
        if not m:
            raise SystemExit(
                f"[{path.name}] không đoán được task_type từ tên file "
                f"(cần kết thúc bằng -kis/-qa/-trake)"
            )
        task = m.group(1).upper()

        raw_lines = path.read_text(encoding="utf-8").splitlines()
        lines = [ln.strip() for ln in raw_lines if ln.strip()]
        if not lines:
            raise SystemExit(f"[{path.name}] file rỗng")

        q: dict = {"query_id": stem, "task_type": task}
        if task == "TRAKE":
            overview, *rest = lines
            events = []
            for ln in rest:
                em = _EVENT_LINE.match(ln)
                events.append(em.group(1).strip() if em else ln)
            q["query_vi"] = " . ".join(p.rstrip(" .") for p in [overview, *events])
            if len(events) >= 2:
                q["event_descs"] = events
        else:
            q["query_vi"] = " ".join(lines)
        data.append(q)
    return data


def _load_raw(path: Path) -> list[dict]:
    """Đọc .txt mà không biết trước là JSON list hay JSONL — thử cả hai."""
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
    except json.JSONDecodeError:
        pass

    data = []
    for i, line in enumerate(raw.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            data.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise SystemExit(f"[{path}] dòng {i} không phải JSON hợp lệ: {e}\n  {line[:120]}")
    return data


def _split_events(query_vi: str) -> list[str]:
    parts = [p.strip() for p in _SENTENCE_SPLIT.split(query_vi)]
    return [p for p in parts if p]


def _normalize(q: dict, src: str, idx: int) -> dict:
    q = dict(q)  # không sửa object gốc
    if "task_type" not in q and "type" in q:
        q["task_type"] = q.pop("type")
    if q.get("task_type") == "TRAKE" and not q.get("event_descs"):
        events = _split_events(str(q.get("query_vi", "")))
        if len(events) >= 2:
            q["event_descs"] = events
    return q


def _validate(data: list[dict]) -> list[str]:
    """Bản sao logic kiểm tra của run.py::_doc_queries — bắt lỗi sớm."""
    loi: list[str] = []
    da_thay: dict[str, int] = {}
    for i, q in enumerate(data, 1):
        for khoa in ("query_id", "task_type", "query_vi"):
            if not str(q.get(khoa, "")).strip():
                loi.append(f"truy vấn thứ {i}: thiếu hoặc rỗng khoá '{khoa}'")
        qid, task = str(q.get("query_id", "")), q.get("task_type")
        if task not in TASK_TYPES:
            loi.append(f"[{qid}] task_type '{task}' không hợp lệ, phải là {TASK_TYPES}")
        if qid in da_thay:
            loi.append(f"[{qid}] query_id trùng với truy vấn thứ {da_thay[qid]}")
        da_thay[qid] = i
        if task == "TRAKE":
            ds = q.get("event_descs")
            if ds is not None and len(ds) < 2:
                loi.append(f"[{qid}] TRAKE cần ≥2 sự kiện, event_descs có {len(ds)}")
    return loi


def _warn_duplicate_content(all_q: list[dict]) -> list[str]:
    """Hai query_id khác nhau nhưng query_vi giống hệt — không phải lỗi ĐỊNH
    DẠNG (vẫn ghi file bình thường) nhưng đáng ngờ, đáng nói ra trước khi
    đốt LLM/Milvus giải hai lần cùng một câu.
    """
    seen: dict[str, str] = {}
    canh_bao = []
    for q in all_q:
        key = q.get("query_vi", "")
        if key in seen:
            canh_bao.append(f"[{q['query_id']}] nội dung giống hệt [{seen[key]}]")
        else:
            seen[key] = q["query_id"]
    return canh_bao


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "inputs", nargs="+",
        help="thư mục bộ đề BTC (mỗi câu một .txt) hoặc file .txt dạng JSON/JSONL",
    )
    ap.add_argument("-o", "--out", required=True, help="file .jsonl để ghi ra (dùng cho run.py --queries)")
    args = ap.parse_args()

    all_q: list[dict] = []
    for p in args.inputs:
        path = Path(p)
        if not path.exists():
            raise SystemExit(f"Không thấy: {path}")
        if path.is_dir():
            all_q.extend(_load_query_dir(path))
        else:
            raw = _load_raw(path)
            all_q.extend(_normalize(q, str(path), i) for i, q in enumerate(raw, 1))

    loi = _validate(all_q)
    if loi:
        print("LỖI — chưa ghi file nào:", file=sys.stderr)
        for l in loi[:30]:
            print(f"  {l}", file=sys.stderr)
        return 2

    for canh_bao in _warn_duplicate_content(all_q):
        print(f"  [cảnh báo] {canh_bao}", file=sys.stderr)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for q in all_q:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")

    dem: dict[str, int] = {}
    for q in all_q:
        dem[q["task_type"]] = dem.get(q["task_type"], 0) + 1
    print(f"Đã ghi {len(all_q)} truy vấn → {out_path}")
    print("  " + " · ".join(f"{k}: {v}" for k, v in sorted(dem.items())))
    n_trake_auto = sum(1 for q in all_q if q["task_type"] == "TRAKE" and q.get("event_descs"))
    n_trake = dem.get("TRAKE", 0)
    if n_trake:
        print(f"  TRAKE có event_descs tách sẵn: {n_trake_auto}/{n_trake} (đỡ tốn LLM)")
    print(f"\nChạy: python run.py --queries {out_path} --out submissions/lan_1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
