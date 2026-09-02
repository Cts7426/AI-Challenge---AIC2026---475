"""Dựng ground truth THẬT từ hai gói nộp chính thức Đợt 1 + Đợt 2.

Vì sao cần file này
-------------------
`dress25` là legacy, GT chưa ai xác minh, và mọi tài liệu nội bộ đều ghi rõ nó
chỉ là *diagnostic evidence*. Không có bộ đo đáng tin thì mọi thay đổi trước
Đợt 3 đều là đoán mò.

Hai gói nộp chính thức là bằng chứng tốt hơn hẳn vì chúng có ĐIỂM THẬT do BTC
chấm:

    Đợt 1 — 8,6/13  → khoảng 66% câu đúng
    Đợt 2 — 13,6/15 → khoảng 91% câu đúng

Dòng 1 của mỗi file nộp là đáp án người thao tác chốt (máy sinh 100 dòng, người
sửa phần đầu — đúng workflow ở CLAUDE.md mục 2). Điểm tổng vì vậy cho biết
XÁC SUẤT dòng 1 đúng, dù không cho biết CÂU NÀO đúng.

Đó là lý do file này gán `confidence` theo tầng thay vì đánh dấu tất cả là
CONFIRMED. Tầng thấp phải được người kiểm lại bằng mắt trước khi tin.

Chạy
----
    .venv\\Scripts\\python.exe dev_set\\tools\\build_official_gt.py \\
        --r1-zip "C:\\Users\\lehon\\Downloads\\Thanh Nghệ_round1 (1).zip" \\
        --r2-zip "C:\\Users\\lehon\\Downloads\\submission_THANH_ NGHỆ.zip" \\
        --out dev_set/ground_truth/official_r1r2.jsonl
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# Điểm BTC chấm — nguồn duy nhất cho biết dòng 1 đáng tin tới đâu.
ROUND_SCORE = {
    "p1": {"scored": 8.6, "total": 13.0, "label": "Đợt 1 · 21/08/2026"},
    "p2": {"scored": 13.6, "total": 15.0, "label": "Đợt 2 · 28/08/2026"},
}

QUERY_TEXT_DIRS = {
    "p2": REPO / "data" / "queries" / "round2_raw",
}
QUERY_JSONL = {
    "p1": REPO / "data" / "queries" / "sotuyen1_p1.jsonl",
    "p2": REPO / "data" / "queries" / "round2.jsonl",
}
DRAFT_GT = REPO / "dev_set" / "ground_truth" / "sotuyen1_p1_draft_gt.jsonl"

# ─────────────────────────────────────────── phân xử mâu thuẫn bằng ẢNH THẬT
#
# Chín câu Đợt 1 có dòng nộp mâu thuẫn với draft GT. Ba câu mâu thuẫn tới mức
# KHÁC VIDEO — sai video là 0 điểm tuyệt đối nên phải phân xử trước khi dùng.
#
# ⚠ Các phán quyết dưới đây do TRỢ LÝ AI xem keyframe thật trên đĩa + đối chiếu
#   OCR/ASR/metadata đã index, KHÔNG phải người trong nhóm ký. Chúng nâng độ tin
#   lên mức dùng để ĐO được, nhưng `verified_by` vẫn phải có tên người thật
#   trước khi coi là promotion evidence (đúng chuẩn nhóm đã đặt ra sau vụ
#   `batch1_holdout13`).
RESOLVED: dict[str, dict] = {
    "query-p1-18-kis": {
        "video_id": "L26_V389",
        "frame_exact": 6400,
        "video_confidence": "VERIFIED_ASSISTANT",
        "frame_confidence": "VERIFIED_ASSISTANT",
        "evidence": (
            "Keyframe L26_V389/143.jpg (frame 6400) khớp TOÀN BỘ chi tiết đề bài: "
            "bún, thịt gà, cà rốt cắt khoanh, sả, nấm mèo, một cọng ngò trên cùng, "
            "và chén nước chấm nhỏ bên cạnh với ĐÚNG 2 miếng ớt. "
            "Bài nộp L26_V235 SAI: ASR quanh frame 6488 là món sườn + chuối + nghệ, "
            "không có gà/sả/nấm mèo."
        ),
        "rejected": {"video_id": "L26_V235", "frame_exact": 6488, "from": "nộp Đợt 1"},
    },
    "query-p1-17-qa": {
        "video_id": "L22_V008",
        "frame_exact": 5638,
        "answer_text": "đèo Tà Pứa",
        "video_confidence": "LIKELY_ASSISTANT",
        "frame_confidence": "LIKELY_ASSISTANT",
        "evidence": (
            "OCR frame 5638 (keyframe 059.jpg): ticker 'BÌNH THUẬN: SẠT LỞ ĐÈO TÀ PỨA "
            "GÂY ÁCH TẮC GIAO THÔNG' — gọi thẳng tên đèo, đúng thứ câu hỏi hỏi. "
            "Ảnh 059/061 là sạt lở ĐẤT BÙN có cây xanh lẫn vào, khớp 'khu vực bùn lầy' "
            "và 'vật màu xanh lá'. "
            "Bài nộp L22_V025 frame 1858 là TẢNG ĐÁ KHÔ ~100m³ ở Sa Pa→Lai Châu "
            "(ASR xác nhận); đáp án nộp 'Đèo Tằng Quái' KHÔNG có trong OCR/ASR "
            "của bất kỳ video nào đã index."
        ),
        "needs_human": (
            "Chưa nhìn thấy 'cột mốc đường bộ đỉnh đỏ' và cảnh xe máy trong 7 keyframe "
            "của L22_V008 [5540..6207]. Người kiểm nên xem video gốc đoạn này để chốt."
        ),
        "rejected": {"video_id": "L22_V025", "frame_exact": 1858,
                     "answer_text": "Đèo Tằng Quái", "from": "nộp Đợt 1"},
    },
    "query-p1-9-qa": {
        "video_id": "L21_V003",
        "frame_exact": 25100,
        "answer_text": None,  # vẫn chưa đọc được số trên biển báo
        "video_confidence": "LIKELY_ASSISTANT",
        "frame_confidence": "UNKNOWN",
        "evidence": (
            "ASR L21_V003 frame 24930-25504 nói về 'cộng đồng yêu thích xe lội nước "
            "tại châu Âu… sự kiện năm nay tại Hà Lan' — khớp trực tiếp 'xe ô tô lội nước'. "
            "Bài nộp L28_V020 frame 8502 chỉ có OCR 'htv online', không có bằng chứng "
            "văn bản nào ủng hộ."
        ),
        "needs_human": "CHƯA đọc được số trên biển báo bên trái cầu — đáp án QA còn trống.",
        "rejected": {"video_id": "L28_V020", "frame_exact": 8502, "answer_text": "2",
                     "from": "nộp Đợt 1"},
    },
}


# ────────────────────────────────────────────────────────────── đọc gói nộp

@dataclass
class Submission:
    """Một file CSV trong gói nộp: 100 dòng, dòng 1 là đáp án người chốt."""

    query_id: str
    task_type: str
    rows: list[list[str]]

    @property
    def top(self) -> list[str]:
        return self.rows[0]

    @property
    def video_id(self) -> str:
        return self.rows[0][0]

    def frames(self) -> list[int]:
        """Các frame_id ở dòng 1. KIS/QA có 1, TRAKE có N."""
        cells = self.rows[0][1:]
        out = []
        for c in cells:
            c = c.strip()
            if re.fullmatch(r"-?\d+", c):
                out.append(int(c))
            else:
                break  # gặp answer_text của QA thì dừng
        return out

    def answer_text(self) -> str | None:
        if self.task_type != "QA" or len(self.rows[0]) < 3:
            return None
        return self.rows[0][2].strip() or None

    def concentration(self) -> tuple[int, int]:
        """(số dòng trong top-10 cùng video, số dòng trong 100 cùng video).

        top-10 cao = người thao tác đã dồn frame quanh một video đã xác nhận.
        top-10 = 1 = dòng 1 nổi lên trên nền máy xen kẽ theo shot.
        Cả hai đều hợp lệ; đây chỉ là tín hiệu phụ, không phải bằng chứng.
        """
        v = self.video_id
        return (
            sum(1 for r in self.rows[:10] if r and r[0] == v),
            sum(1 for r in self.rows if r and r[0] == v),
        )


def read_zip(path: Path) -> dict[str, Submission]:
    subs: dict[str, Submission] = {}
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if not name.lower().endswith(".csv"):
                continue
            stem = Path(name).stem  # query-p2-7-qa
            m = re.match(r"query-(p\d)-(\d+)-(kis|qa|trake)$", stem)
            if not m:
                print(f"  ! bỏ qua file không đúng quy ước: {name}", file=sys.stderr)
                continue
            raw = z.read(name).decode("utf-8-sig")
            rows = [r for r in csv.reader(io.StringIO(raw)) if r and any(c.strip() for c in r)]
            if not rows:
                print(f"  ! {stem}: file rỗng", file=sys.stderr)
                continue
            subs[stem] = Submission(stem, m.group(3).upper(), rows)
    return subs


def zip_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ─────────────────────────────────────────────────────────── nội dung truy vấn

def load_query_texts(part: str) -> dict[str, str]:
    texts: dict[str, str] = {}
    d = QUERY_TEXT_DIRS.get(part)
    if d and d.is_dir():
        for f in d.glob("query-*.txt"):
            texts[f.stem] = f.read_text(encoding="utf-8").strip()
    j = QUERY_JSONL.get(part)
    if j and j.is_file():
        for line in j.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            qid = o.get("query_id") or o.get("id")
            txt = o.get("query_vi") or o.get("text") or o.get("query")
            if qid and txt and qid not in texts:
                texts[qid] = txt.strip()
    return texts


def load_draft_gt() -> dict[str, dict]:
    if not DRAFT_GT.is_file():
        return {}
    out = {}
    for line in DRAFT_GT.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            continue
        if o.get("query_id"):
            out[o["query_id"]] = o
    return out


# ────────────────────────────────────────────────────────────── phân tầng

def classify(part: str, sub: Submission, draft: dict | None) -> tuple[str, str, list[str]]:
    """Trả (video_confidence, frame_confidence, lý do).

    Tách RIÊNG độ tin của video và của frame — đây là quyết định thiết kế quan
    trọng nhất của file này. Lý do: Tường 1 (recall) và Tường 2 (ranking) chỉ
    cần GT ở MỨC VIDEO là đo được, mà mức video đáng tin hơn hẳn mức frame.
    Trộn chung hai thứ sẽ vứt đi 6 câu mà hai nguồn độc lập đã đồng ý về video
    và chỉ lệch nhau chỗ frame.

    Bậc độ tin, từ cao xuống:
      VERIFIED_ASSISTANT — trợ lý đã xem ảnh thật, mọi chi tiết đề bài khớp
      LIKELY_ASSISTANT   — trợ lý đã xem, bằng chứng mạnh nhưng còn chi tiết chưa thấy
      CORROBORATED       — bài nộp và draft GT (dựng độc lập từ OCR/ASR) khớp nhau
      HIGH               — dòng 1 gói Đợt 2, tiên nghiệm 91% đúng
      MEDIUM             — dòng 1 gói Đợt 1, tiên nghiệm 66% đúng
      DISPUTED           — hai nguồn mâu thuẫn, CHƯA phân xử
      UNKNOWN            — không có căn cứ
    """
    why: list[str] = []
    t10, t100 = sub.concentration()
    frames = sub.frames()
    why.append(f"nộp dòng 1 = {sub.video_id}:{','.join(map(str, frames))}")
    why.append(f"top10 cùng video={t10}, top100={t100}")

    base = "HIGH" if part == "p2" else "MEDIUM"

    if draft and draft.get("video_id"):
        same_video = draft["video_id"] == sub.video_id
        fs, fe = draft.get("frame_start"), draft.get("frame_end")
        in_window = (
            fs is not None and fe is not None and frames
            and any(fs <= f <= fe for f in frames)
        )
        if same_video and in_window:
            why.append(f"khớp draft GT ({draft.get('status')}) cả video lẫn cửa sổ frame")
            return "CORROBORATED", "CORROBORATED", why
        if same_video and fs is None:
            why.append("draft GT xác nhận CÙNG video nhưng chưa chốt frame")
            return "CORROBORATED", base, why
        if same_video:
            why.append(
                f"hai nguồn ĐỒNG Ý video, LỆCH frame: draft=[{fs},{fe}] vs nộp={frames}"
            )
            # Video được hai nguồn độc lập xác nhận → tin ở mức video.
            return "CORROBORATED", "DISPUTED", why
        why.append(f"KHÁC video draft GT: draft={draft['video_id']} vs nộp={sub.video_id}")
        return "DISPUTED", "DISPUTED", why

    if draft and draft.get("status") == "TODO":
        why.append("draft GT bỏ trống (TODO) — không có nguồn đối chiếu")

    return base, base, why


# ────────────────────────────────────────────────────────────────── build

def build(part: str, zip_path: Path, out_records: list[dict], stats: Counter) -> dict:
    print(f"\n=== {ROUND_SCORE[part]['label']} · {zip_path.name} ===")
    subs = read_zip(zip_path)
    texts = load_query_texts(part)
    draft = load_draft_gt() if part == "p1" else {}
    sha = zip_sha256(zip_path)
    score = ROUND_SCORE[part]
    prior = score["scored"] / score["total"]

    print(f"  {len(subs)} file CSV · SHA-256 {sha[:16]}…")
    print(f"  điểm BTC {score['scored']}/{score['total']} → tiên nghiệm dòng 1 đúng ≈ {prior:.0%}")

    for qid in sorted(subs, key=lambda s: int(s.split("-")[2])):
        sub = subs[qid]
        vconf, fconf, why = classify(part, sub, draft.get(qid))
        frames = sub.frames()
        rec = {
            "query_id": qid,
            "part": part,
            "task_type": sub.task_type,
            "query_text": texts.get(qid),
            "video_id": sub.video_id,
            # Cửa sổ [s,e] BTC dùng CHƯA được công bố. Ta chỉ biết frame người
            # thao tác chốt; evaluator tự áp dung sai theo ±tolerance.
            "frame_exact": frames[0] if frames else None,
            "frames": frames if sub.task_type == "TRAKE" else None,
            "answer_text": sub.answer_text(),
            "video_confidence": vconf,
            "frame_confidence": fconf,
            "source": f"{zip_path.name}#{qid}.csv row 1",
            "source_sha256": sha,
            "round_score": f"{score['scored']}/{score['total']}",
            "prior_row1_correct": round(prior, 3),
            "verified_by": None,     # ← người kiểm điền TÊN THẬT vào đây
            "verified_how": None,    # ← và cách kiểm
            "rejected": None,
            "needs_human": None,
            "why": why,
        }

        # Phán quyết bằng ảnh thật ghi đè bài nộp.
        if qid in RESOLVED:
            r = dict(RESOLVED[qid])
            rec["rejected"] = r.pop("rejected", None)
            rec["needs_human"] = r.pop("needs_human", None)
            ev = r.pop("evidence")
            rec.update(r)
            rec["verified_by"] = "claude-opus-5 (trợ lý) — CẦN NGƯỜI TRONG NHÓM KÝ LẠI"
            rec["verified_how"] = ev
            rec["why"] = why + [f"PHÂN XỬ: {ev}"]

        stats[rec["video_confidence"]] += 1
        out_records.append(rec)
        mark = {"DISPUTED": " ⚠", "VERIFIED_ASSISTANT": " ✓", "LIKELY_ASSISTANT": " ~"}
        flag = mark.get(rec["video_confidence"], "  ")
        print(
            f"{flag} {qid:22s} vid={rec['video_confidence']:19s} "
            f"frm={rec['frame_confidence']:19s} {rec['video_id']:9s} "
            f"{rec['frames'] or rec['frame_exact']}"
        )

    return {"zip": zip_path.name, "sha256": sha, "n_queries": len(subs), **score}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--r1-zip", type=Path, required=True)
    ap.add_argument("--r2-zip", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=REPO / "dev_set/ground_truth/official_r1r2.jsonl")
    args = ap.parse_args()

    for p in (args.r1_zip, args.r2_zip):
        if not p.is_file():
            print(f"KHÔNG THẤY FILE: {p}", file=sys.stderr)
            return 2

    records: list[dict] = []
    stats: Counter = Counter()
    prov = [
        build("p1", args.r1_zip, records, stats),
        build("p2", args.r2_zip, records, stats),
    ]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    meta = args.out.with_suffix(".meta.json")
    meta.write_text(
        json.dumps(
            {
                "built_by": "dev_set/tools/build_official_gt.py",
                "n_records": len(records),
                "confidence_counts": dict(stats),
                "sources": prov,
                "window_policy": (
                    "Cửa sổ [s,e] của BTC chưa công bố. File chỉ lưu frame_exact "
                    "(frame người thao tác chốt). Evaluator phải tự áp ±tolerance "
                    "và báo cáo điểm ở nhiều mức dung sai."
                ),
                "warning": (
                    "confidence là TIÊN NGHIỆM từ điểm tổng, KHÔNG phải xác minh "
                    "từng câu. Chỉ nâng lên VERIFIED sau khi người thật kiểm bằng "
                    "mắt và điền verified_by/verified_how."
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print("\n" + "=" * 72)
    print(f"Đã ghi {len(records)} bản ghi → {args.out}")
    print("\nĐộ tin ở MỨC VIDEO (dùng được ngay cho đo recall/ranking):")
    order = ["VERIFIED_ASSISTANT", "LIKELY_ASSISTANT", "CORROBORATED",
             "HIGH", "MEDIUM", "DISPUTED", "UNKNOWN"]
    for k in order:
        if stats.get(k):
            print(f"  {k:20s} {stats[k]:3d}")

    usable = sum(stats.get(k, 0) for k in
                 ("VERIFIED_ASSISTANT", "LIKELY_ASSISTANT", "CORROBORATED", "HIGH"))
    print(f"\n→ {usable} câu dùng được NGAY cho đo mức video "
          f"(≥ HIGH). Đủ để chạy bake-off encoder.")
    n_disp = stats.get("DISPUTED", 0)
    if n_disp:
        print(f"⚠ {n_disp} câu còn tranh chấp video — người kiểm phải xem video gốc.")
    print("\nNhắc: `verified_by` còn None ở hầu hết bản ghi. Chưa có tên người thật "
          "thì file này là DEVELOPMENT evidence, chưa phải promotion evidence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
