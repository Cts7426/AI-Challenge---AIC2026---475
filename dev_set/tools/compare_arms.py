"""So nhiều arm eval_official cạnh nhau — một bảng, đọc là quyết được.

Vì sao cần: `eval_official.py` in đẹp cho MỘT lượt, nhưng quyết định luôn là so
sánh giữa các lượt. Mở ba file JSON rồi dò bằng mắt là cách tốt nhất để đọc nhầm
cột, nhất là lúc 11 giờ đêm trước ngày thi.

In kèm dòng provenance của từng arm (encoder · nguồn dịch · pool · dual · slot ·
rerank) để không bao giờ so nhầm hai arm khác điều kiện mà tưởng cùng điều kiện.

    python -m dev_set.tools.compare_arms dev_set/results/run_20260903_ab_p1/*.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _hang(j: dict) -> dict:
    a = j.get("aggregate", {})
    rk = a.get("r_at_k_video", {})
    ff = a.get("final_frame", {})

    def _f(d: dict, *keys):
        for k in keys:
            if k in d:
                return d[k]
        return None

    return {
        "final_vid": a.get("final_video"),
        "r1": _f(rk, "1", 1), "r5": _f(rk, "5", 5),
        "r20": _f(rk, "20", 20), "r100": _f(rk, "100", 100),
        "f5": _f(ff, "5", 5), "f15": _f(ff, "15", 15), "f40": _f(ff, "40", 40),
        "found": a.get("video_found_in_100"), "n": a.get("n_queries"),
        "lat": a.get("latency_median_s"),
    }


def _prov(j: dict) -> str:
    slot = j.get("slot_budget")
    slot_s = ",".join(f"{n}x{k}" for n, k in slot) if slot else "?"
    return (f"pool={j.get('candidate_multiplier')}x100 · "
            f"dual={'CÓ' if j.get('dual_vector') else 'không'} · "
            f"slot={slot_s} · rerank={'CÓ' if j.get('rerank_top50') else 'không'} · "
            f"vp={j.get('video_prior_alpha')}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("files", nargs="+", type=Path)
    args = ap.parse_args()

    js = []
    for p in args.files:
        if not p.is_file():
            print(f"  bỏ qua (không thấy): {p}")
            continue
        js.append((p.stem, json.loads(p.read_text(encoding="utf-8"))))
    if not js:
        raise SystemExit("không có file nào đọc được")

    part = {j.get("part") for _, j in js}
    print(f"part={'/'.join(sorted(map(str, part)))} · "
          f"n={js[0][1].get('aggregate', {}).get('n_queries')} câu\n")

    w = max(len(n) for n, _ in js) + 1
    print(f"{'arm':{w}s} {'Final_vid':>9s} {'R@1':>6s} {'R@5':>6s} {'R@20':>6s} "
          f"{'R@100':>6s} {'±5':>6s} {'±15':>6s} {'±40':>6s} {'video':>6s} {'trễ':>6s}")
    print("-" * (w + 74))
    for ten, j in js:
        h = _hang(j)
        print(f"{ten:{w}s} {h['final_vid']:9.4f} {h['r1']:6.3f} {h['r5']:6.3f} "
              f"{h['r20']:6.3f} {h['r100']:6.3f} {h['f5']:6.3f} {h['f15']:6.3f} "
              f"{h['f40']:6.3f} {str(h['found']) + '/' + str(h['n']):>6s} "
              f"{h['lat']:5.2f}s")
    print("\nĐiều kiện từng arm:")
    for ten, j in js:
        print(f"  {ten:{w}s} {_prov(j)}")
    print("\n⚠️ Chỉ tin thay đổi cải thiện ở MỌI mức ±tol. Cột video là trần trên;\n"
          "   BTC chấm frame_id ∈ [s,e] nên cột ± mới là điểm thật.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
