"""A/B hai encoder trên cùng bộ câu hỏi, chấm bằng Final Score thật của BTC.

Vì sao cần script riêng thay vì tin bảng benchmark của model: hai encoder chỉ
so được khi CÙNG anchor, CÙNG tập câu hỏi, CÙNG cách chấm. Và quyết định
"có đổi encoder không" phải dựa trên điểm thi, không phải recall@k chung chung —
theo bảng BTC, hạng 1 đáng 1.00 còn hạng 5 chỉ còn 0.64, nên một thay đổi làm
tăng recall mà tụt hạng đầu là thay đổi LỖ.

Chạy:
    .venv/bin/python3.14 scripts/ab_encoder.py
    .venv/bin/python3.14 scripts/ab_encoder.py --only-encoded   # bỏ câu chưa encode
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

FINDINGS = REPO / "dev_set/ground_truth/round1_kis_findings.json"
MANIFEST = REPO / "dev_set/manifests/batch1_round1_queries.json"
TOL = 75


def r_score(rank: int | None) -> float:
    if rank is None:
        return 0.0
    return 1.0 if rank <= 1 else 0.8 if rank <= 5 else 0.6 if rank <= 20 else 0.4 if rank <= 50 else 0.2 if rank <= 100 else 0.0


def final_score(rank: int | None) -> float:
    """Trung bình R@1..R@100 — đúng công thức BTC, không phải recall thường."""
    return sum(r_score(rank) if rank and rank <= k else 0.0 for k in (1, 5, 20, 50, 100)) / 5


def run_backend(backend: str, plans: dict, qvi: dict, qids: list[str], top_k: int) -> dict[str, list]:
    """Chạy search trong TIẾN TRÌNH RIÊNG: encoder được chọn lúc import, đổi biến
    môi trường giữa chừng trong cùng process sẽ không có tác dụng."""
    payload = json.dumps({"backend": backend, "qids": qids, "top_k": top_k,
                          "plans": plans, "qvi": qvi})
    code = r'''
import json, sys, os
sys.path.insert(0, ".")
cfg = json.loads(sys.stdin.read())
from backend.retrieval.search import search
out = {}
for qid in cfg["qids"]:
    rows = []
    for a in cfg["plans"][qid]["anchors"] + cfg["plans"][qid].get("hyp", []):
        try:
            for r in search(cfg["qvi"][qid], query_en=a, top_k=cfg["top_k"]):
                if r["frame_idx"] is not None:
                    rows.append([r["video_id"], int(r["frame_idx"])])
        except Exception as e:
            print(f"[{qid}] anchor loi: {e}", file=sys.stderr)
    out[qid] = rows
print("@@RESULT@@" + json.dumps(out))
'''
    env = {**os.environ, "VECTOR_BACKEND": backend}
    proc = subprocess.run([sys.executable, "-c", code], input=payload, text=True,
                          capture_output=True, cwd=REPO, env=env)
    for line in proc.stdout.splitlines():
        if line.startswith("@@RESULT@@"):
            return json.loads(line[len("@@RESULT@@"):])
    raise SystemExit(f"backend {backend} không trả kết quả:\n{proc.stderr[-1500:]}")


def rank_of(rows: list, video_id: str, frame: int) -> int | None:
    seen = set()
    rank = 0
    for v, f in rows:
        if (v, f) in seen:
            continue
        seen.add((v, f))
        rank += 1
        if v == video_id and abs(f - frame) <= TOL:
            return rank
        if rank >= 100:
            break
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--top-k", type=int, default=40)
    ap.add_argument("--plans", type=Path, default=REPO / "dev_set/queries/round1_kis_plans.json")
    ap.add_argument("--only-encoded", action="store_true",
                    help="chỉ chấm câu có video đáp án đã encode (dùng khi job chưa xong)")
    args = ap.parse_args()

    findings = json.loads(FINDINGS.read_text(encoding="utf-8"))["entries"]
    qvi = {q["query_id"]: q["query_vi"]
           for q in json.loads(MANIFEST.read_text(encoding="utf-8"))["queries"]}
    plans = json.loads(args.plans.read_text(encoding="utf-8"))

    qids = sorted(findings, key=lambda x: int(x.split("-")[2]))
    if args.only_encoded:
        from data.config.siglip2_model import siglip2_emb_dir
        have = {p.stem for p in siglip2_emb_dir().glob("*.npy") if not p.name.endswith(".frames.npy")}
        skipped = [q for q in qids if findings[q]["video_id"] not in have]
        qids = [q for q in qids if findings[q]["video_id"] in have]
        print(f"bỏ {len(skipped)} câu chưa encode video đáp án: "
              f"{[q.replace('query-','').replace('-kis','') for q in skipped]}")

    results = {b: run_backend(b, plans, qvi, qids, args.top_k) for b in ("clip", "siglip2")}

    print()
    print(f'{"câu":8s} {"CLIP":>7s} {"SigLIP2":>8s}   {"Final CLIP":>10s} {"Final SIG":>10s}')
    print("-" * 50)
    tot = {"clip": 0.0, "siglip2": 0.0}
    hits = {"clip": 0, "siglip2": 0}
    for qid in qids:
        c = findings[qid]
        ranks = {b: rank_of(results[b][qid], c["video_id"], int(c["frame"])) for b in results}
        for b in results:
            tot[b] += final_score(ranks[b])
            hits[b] += 1 if (ranks[b] and ranks[b] <= 50) else 0
        print(f'{qid.replace("query-","").replace("-kis",""):8s} '
              f'{str(ranks["clip"]):>7s} {str(ranks["siglip2"]):>8s}   '
              f'{final_score(ranks["clip"]):>10.2f} {final_score(ranks["siglip2"]):>10.2f}')

    n = len(qids)
    print()
    for b in ("clip", "siglip2"):
        print(f'{b:9s} Final TB = {tot[b]/n:.4f}   trong top-50: {hits[b]}/{n}')
    delta = (tot["siglip2"] - tot["clip"]) / n
    print()
    print(f'CHÊNH LỆCH: {delta:+.4f} Final')
    print("KẾT LUẬN: " + (
        "SigLIP2 tốt hơn -> nên đổi" if delta > 0.02 else
        "CLIP tốt hơn -> GIỮ NGUYÊN" if delta < -0.02 else
        "ngang nhau -> giữ CLIP cho an toàn"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
