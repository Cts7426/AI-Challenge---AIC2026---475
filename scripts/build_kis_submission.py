"""Sinh submission KIS bằng đường ống đã đo được là tốt nhất.

Đây là bản sản xuất của thiết kế rút ra sau 11 thí nghiệm đo đạc; ba luật dưới
đây đều đổi bằng điểm số thật, không phải trực giác:

1. KHÔNG XÁO TRỘN ĐẦU BẢNG. Bảng điểm BTC: hạng 1 -> Final 1.00, hạng 5 ->
   0.64, hạng 62 -> 0.04. Đẩy một câu từ hạng 1 xuống 5 mất 0.36 — đúng bằng
   lợi ích cứu một câu chết lên top-20. Nên `KEEP` slot đầu giữ y nguyên thứ tự
   của anchor chính, mọi cải tiến chỉ đắp vào phần đuôi.

2. KHÔNG RRF CÁC ANCHOR TẢ KHOẢNH KHẮC KHÁC NHAU. Đề KIS hay kể một chuỗi, mỗi
   anchor tả một khoảnh khắc, nên frame đúng chỉ khớp mạnh với MỘT anchor. RRF
   cộng dồn thưởng cho shot khớp lờ mờ với cả ba và dìm shot khớp hoàn hảo với
   một — đo được R@1 tụt từ 6/17 xuống 1/17. Mỗi nguồn giữ bảng riêng rồi XEN KẼ.

3. CHỌN VIDEO VÀ ĐỊNH VỊ FRAME LÀ HAI VIỆC KHÁC NHAU. Anchor giả thuyết giỏi
   chọn video, anchor trung thành giỏi tìm frame trong video đó. Khi đào một
   video phải đào bằng MỌI anchor.

Đầu vào là file plan do người/Claude viết lúc chạy:
    {"query-p1-1-kis": {"anchors": [...], "hyp": [...], "ocr": [...], "asr": [...]}}

Chạy:
    .venv/bin/python3.14 scripts/build_kis_submission.py --out submissions/kis_v2
    VECTOR_BACKEND=siglip2 .venv/bin/python3.14 scripts/build_kis_submission.py --out submissions/kis_v2_siglip2
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.indexing.es_client import connect as es_connect  # noqa: E402
from backend.retrieval.search import search  # noqa: E402

TOTAL = 100
KEEP = 10          # số slot đầu giữ nguyên thứ tự anchor chính
RARE_COVER = 60    # probe xuất hiện ở dưới ngần này video -> bằng chứng cứng
COVER_MAX = 0.45   # probe phủ hơn 45% kho -> không phân biệt được, bỏ
N_VIDEOS = 873


def _q(term: str) -> dict:
    return {"match_phrase": {"text": term}} if " " in term else {"match": {"text": term}}


def _probe_hits(es, index: str, term: str, size: int = 300):
    """(video theo hạng, {video: hit thô}). Lỗi một probe không được kéo sập câu."""
    try:
        hits = es.search(index=index, body={"query": _q(term), "size": size})["hits"]["hits"]
    except Exception:
        return [], {}
    order, by_v = [], defaultdict(list)
    for h in hits:
        v = h["_source"]["video_id"]
        if v not in by_v:
            order.append(v)
        by_v[v].append(h["_source"])
    return order, by_v


def _hit_frames(index: str, video_id: str, srcs: list, kf2frame: dict, fps: dict, nframes: dict):
    """Frame mà chính hit trỏ tới — chính xác hơn nhiều so với nhờ CLIP tìm lại."""
    out = []
    for src in srcs[:8]:
        if index == "ocr":
            f = kf2frame.get(src.get("keyframe_id"))
            if f is not None:
                out.append(int(f))
        else:
            num, den = fps.get(video_id, (25, 1))
            nmax = nframes.get(video_id, 1 << 62)
            for ms in range(int(src["start_ms"]), int(src["end_ms"]) + 1, 2000):
                f = int(ms * num / (den * 1000))
                if 0 <= f < nmax:
                    out.append(f)
    return out


def _interleave(streams: list[list], seed: list, total: int = TOTAL) -> list:
    """Chia lượt giữa các nguồn: mỗi nguồn góp 1 dòng rồi mới vòng lại."""
    rows, seen = list(seed), set(seed)
    idx = [0] * len(streams)
    while len(rows) < total and any(i < len(st) for i, st in zip(idx, streams)):
        for j, st in enumerate(streams):
            while idx[j] < len(st) and st[idx[j]] in seen:
                idx[j] += 1
            if idx[j] < len(st) and len(rows) < total:
                rows.append(st[idx[j]])
                seen.add(st[idx[j]])
                idx[j] += 1
    return rows



def _shot_agg_head(qid, plan, query_vi, s, shot_of, pool=400, topn=3) -> list[tuple[str, int]]:
    """Đầu bảng xếp theo SHOT gộp điểm nhiều frame, không theo một frame may mắn.

    Đo được: một shot có 3-4 frame cùng ăn điểm là bằng chứng mạnh hơn hẳn shot
    có đúng một frame trúng — Final 0.2988 -> 0.3953 khi so cùng điều kiện.
    Shot mạnh nhất được cấp 2 frame (như SLOT_BUDGET của allocator) vì cửa sổ
    đáp án rộng ~150 frame, hai điểm neo phủ chắc hơn một.
    """
    per_shot, rep = defaultdict(list), {}
    for a in plan["anchors"] + plan.get("hyp", []):
        for r in s(a, pool, None, False):
            f = r["frame_idx"]
            if f is None:
                continue
            sid = r.get("shot_id") or shot_of(r["video_id"], f)
            if sid is None:
                continue
            per_shot[sid].append((r["score"], r["video_id"], int(f)))

    scored = []
    for sid, items in per_shot.items():
        items.sort(key=lambda x: -x[0])
        agg = sum(sc for sc, _, _ in items[:topn])
        scored.append((agg, items))
    scored.sort(key=lambda x: -x[0])

    head = []
    for i, (_, items) in enumerate(scored):
        n_take = 2 if i < 2 else 1          # 2 frame cho 2 shot mạnh nhất
        for _, v, f in items[:n_take]:
            if (v, f) not in head:
                head.append((v, f))
    return head


def build_one(qid: str, plan: dict, query_vi: str, es, kf2frame, fps, nframes,
              pool: int = 120, per_video: int = 12,
              base: list[tuple[str, int]] | None = None,
              shot_of=None, head_mode: str = "base") -> list[tuple[str, int]]:
    anchors = plan["anchors"]
    all_anchors = anchors + plan.get("hyp", [])

    def s(en, k, vid=None, grouped=True):
        try:
            return search(query_vi, query_en=en, top_k=k, filter_video_id=vid,
                          group_by_shot=grouped)
        except Exception as e:
            print(f"    [{qid}] search lỗi ({en[:32]}...): {e}")
            return []

    # --- phần đầu: ƯU TIÊN output của slot allocator (`run.py`) nếu có.
    # Allocator cấp 2 frame cho shot mạnh nhất (SLOT_BUDGET) nên xác suất trúng
    # ở hạng đầu cao hơn hẳn lấy thẳng output search — đo thật: dùng allocator
    # làm đầu bảng cho Final 0.4894, lấy thẳng search chỉ 0.3035.
    # ĐO THẬT trên bộ đề đợt 1, cùng mọi điều kiện khác:
    #     head_mode=base     Final 0.5788 · hạng-1 7/17 · top-50 13/17
    #     head_mode=shotagg  Final 0.4024 · hạng-1 2/17 · top-50 12/17
    # Nên mặc định là `base`. Nhánh `shotagg` giữ lại để đo tiếp, KHÔNG dùng khi thi.
    if head_mode == "shotagg" and shot_of is not None:
        head = _shot_agg_head(qid, plan, query_vi, s, shot_of)
        if base:                      # ghép đuôi allocator vào sau shot-agg
            head += [k for k in base if k not in head]
    elif base:
        head = list(base)
    else:
        head = [(r["video_id"], int(r["frame_idx"])) for r in s(anchors[0], pool)
                if r["frame_idx"] is not None]

    # --- probe chữ: luồng bằng chứng cứng + phiếu chọn video
    rare, vscore = [], defaultdict(float)
    for terms, index, w in ((plan.get("ocr", []), "ocr", 1.5), (plan.get("asr", []), "asr", 1.0)):
        for t in terms:
            order, by_v = _probe_hits(es, index, t)
            if not order:
                continue
            if len(order) <= RARE_COVER:
                for v in order[:6]:
                    rare += [(v, f) for f in _hit_frames(index, v, by_v[v], kf2frame, fps, nframes)]
            if len(order) <= N_VIDEOS * COVER_MAX:
                idf = math.log(N_VIDEOS / max(1, len(order)))
                for rank, v in enumerate(order, 1):
                    vscore[v] += w * idf / (7 + rank)

    # --- mỗi anchor tự đề cử video của nó (không cộng điểm giữa các anchor:
    #     cộng dồn thưởng cho video được mọi anchor thích lờ mờ — đã đo và thua)
    noms: list[list[str]] = []
    for a in all_anchors:
        vids, seen_v = [], set()
        for r in s(a, pool):
            v = r["video_id"]
            if v not in seen_v:
                vids.append(v)
                seen_v.add(v)
        noms.append(vids[:3])
    noms.append([v for v, _ in sorted(vscore.items(), key=lambda kv: -kv[1])[:3]])

    ordered, taken = [], set()
    for i in range(3):
        for nl in noms:
            if i < len(nl) and nl[i] not in taken:
                ordered.append(nl[i])
                taken.add(nl[i])

    # --- đào từng video ứng viên bằng MỌI anchor.
    # Chỉ 3 video được luồng RIÊNG; số còn lại gộp vào một luồng chung. Lý do:
    # số luồng càng nhiều thì bảng đầu càng ít slot — đo thật với 12 luồng,
    # Final tụt từ 0.4894 xuống 0.2471 vì các dòng hạng 11-20 của bảng đầu bị
    # đẩy xuống tận đuôi. Đây đúng là luật 1 ở docstring, và tôi đã vi phạm nó.
    def drill(v: str) -> list[tuple[str, int]]:
        best: dict[int, float] = {}
        for a in all_anchors:
            for r in s(a, per_video, v):
                f = r["frame_idx"]
                if f is not None:
                    best[int(f)] = max(best.get(int(f), 0.0), r["score"])
        return [(v, f) for f, _ in sorted(best.items(), key=lambda kv: -kv[1])]

    video_streams = [rows for v in ordered[:3] if (rows := drill(v))]
    spill: list[tuple[str, int]] = []
    for v in ordered[3:7]:
        spill.extend(drill(v))

    # KHÔNG thăng probe lên đầu bảng. Đã đo hai lần và thua nặng:
    # - thăng vô điều kiện: Final 0.3976, hạng-1 còn 1/17
    # - thăng khi có nhánh vector đồng thuận: Final 0.3812, hạng-1 còn 1/17
    # Lý do: chèn 2 dòng lên đầu đẩy đáp án đúng từ hạng 1 xuống hạng 3-4 ở MỌI
    # câu vốn đã đúng. Đầu bảng đúng 7/17 lần, nên nguồn khác phải chính xác
    # hơn 41% mới đáng thay chỗ — không nguồn nào đạt.
    rows = _interleave([head, rare, *video_streams, spill], seed=head[:KEEP])
    for k in head:                      # còn thiếu thì lấy nốt bảng đầu
        if len(rows) >= TOTAL:
            break
        if k not in rows:
            rows.append(k)
    return rows[:TOTAL]


def _load_query_vi(path: Path) -> dict[str, str]:
    """Đọc câu hỏi tiếng Việt từ CẢ HAI dạng file đang tồn tại trong repo:
    manifest `.json` (`{"queries": [...]}`) và file đề `.jsonl` một dòng một câu.
    `exam.py` truyền dạng thứ hai — trước đây script chỉ hiểu dạng thứ nhất nên
    `exam.py run` chết ở bước này với `JSONDecodeError: Extra data`."""
    text = path.read_text(encoding="utf-8")
    try:
        rows = json.loads(text)["queries"]
    except (json.JSONDecodeError, KeyError, TypeError):
        rows = [json.loads(l) for l in text.splitlines() if l.strip()]
    return {q["query_id"]: q["query_vi"] for q in rows}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plans", type=Path, default=REPO / "dev_set/queries/round1_kis_plans.json")
    ap.add_argument("--manifest", type=Path, default=REPO / "dev_set/manifests/batch1_round1_queries.json")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--base", type=Path, default=None,
                    help="thư mục submission của run.py dùng làm đầu bảng (rất nên có)")
    ap.add_argument("--head", default="base", choices=("base", "shotagg"),
                    help="cách dựng đầu bảng; `base` đo được tốt hơn hẳn (0.5788 vs 0.4024)")
    args = ap.parse_args()

    plans = json.loads(args.plans.read_text(encoding="utf-8"))
    qvi = _load_query_vi(args.manifest)

    fm = pd.read_parquet(REPO / "data/derived/frame_map.parquet")
    kf2frame = dict(zip(fm.kf_id, fm.frame_idx_corrected.astype(int)))
    vi = pd.read_parquet(REPO / "data/derived/video_info.parquet")
    fps = {str(r.video_id): (int(r.fps_num), int(r.fps_den)) for r in vi.itertuples()}
    nframes = {str(r.video_id): int(r.n_frames) for r in vi.itertuples()}

    from backend.retrieval.search import _shot_of_frame as shot_of

    es = es_connect()
    args.out.mkdir(parents=True, exist_ok=True)

    for qid in sorted(plans, key=lambda x: int(x.split("-")[2])):
        base = None
        if args.base and (args.base / f"{qid}.csv").exists():
            base = [(r[0], int(r[1])) for r in csv.reader((args.base / f"{qid}.csv").open())]
        rows = build_one(qid, plans[qid], qvi[qid], es, kf2frame, fps, nframes,
                         base=base, shot_of=shot_of, head_mode=args.head)
        # Đủ 100 dòng là bắt buộc: không có hình phạt cho câu sai, bỏ trống ô
        # 51-100 là vứt điểm miễn phí (CLAUDE.md mục 6 luật 1).
        assert len(rows) == TOTAL, f"{qid}: {len(rows)} dòng, phải đúng {TOTAL}"
        with (args.out / f"{qid}.csv").open("w", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerows([[v, f] for v, f in rows])
        print(f"  {qid:22s} {len({v for v, _ in rows}):>3d} video khác nhau")

    print(f"XONG · {len(plans)} file trong {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
