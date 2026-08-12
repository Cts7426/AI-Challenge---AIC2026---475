# app/offline_search.py — D2.1: tìm kiếm bằng chữ KHÔNG cần Milvus/Elasticsearch
#
# ⚠️ ĐÂY LÀ CÔNG CỤ DEV, KHÔNG PHẢI ĐƯỜNG CHẠY LÚC THI.
# Đường thi là `backend.retrieval.search.search()` (RRF trên 5 nhánh). File này chậm
# hơn và dở hơn — nó chỉ có một việc: cho soi dữ liệu khi Docker chưa lên.
#
# Vì sao vẫn đáng viết:
#   1. Mở được UI ngay cả khi Milvus/ES chết — kể cả 2h sáng ngày nộp.
#   2. Kiểm được chất lượng `doc_text` của Công Lý ngay hôm nay (BUILD_TASKS B1.7:
#      "tra thử một tên riêng hiếm → phải ra đúng frame").
#   3. Không cần torch, không cần GPU, không cần nạp loader nào.
#
# ===== Vì sao quét theo LÔ chứ không nạp cả bảng =====
# Đo thật: nạp hết cột `doc_text` (371.702 dòng, dài trung bình 1.977 ký tự) tốn
# ~845 MB RAM. Máy 16 GB còn phải nuôi Docker (Milvus ăn vài GB) + Streamlit.
# Quét theo lô thì đỉnh bộ nhớ chỉ bằng MỘT lô, còn thứ giữ lại là mấy mảng số đếm
# (371k × vài số = chục MB).
#
# ===== Vì sao đếm bằng str.count thay vì tách từ =====
# Tách từ 371k tài liệu × 2.000 ký tự bằng Python thuần mất hàng chục giây mỗi truy
# vấn. `str.count` của pandas chạy ở tầng C, mỗi từ khoá một lượt quét — truy vấn
# 3–5 từ là 3–5 lượt, đủ nhanh để dùng tay.
#
# ===== Hai thứ đã BỎ sau khi đo (toàn kho 371.702 tài liệu) =====
#   bỏ dấu tiếng Việt (NFD + regex)  : 40,4 s  → BỎ, xem `tach_tu()`
#   đo độ dài bằng str.count(r"\s+") : 29,7 s  → thay bằng str.len(), 1,0 s
#   giữ lại: lower() 6,2 s · str.count mỗi từ 0,8 s · str.len() 1,0 s
# Tổng cho một truy vấn 4 từ: ~10 s. Chậm, nhưng đây là đường lui chứ không phải
# đường thi — và 10 s vẫn hơn hẳn "không mở được UI".

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path

DOCS_PATH = Path(__file__).resolve().parents[1] / "data" / "derived" / "docs_bm25.parquet"

# Tham số BM25 chuẩn (Robertson & Walker). k1 điều tiết mức bão hoà khi một từ lặp
# nhiều lần, b điều tiết mức phạt tài liệu dài. Không tune: đây là công cụ dev, và
# đường thi dùng BM25 của Elasticsearch với chính hai giá trị mặc định này.
BM25_K1 = 1.5
BM25_B = 0.75

LO = 50_000  # số dòng mỗi lô


@dataclass(frozen=True)
class KetQuaOffline:
    kf_id: str
    video_id: str
    shot_id: str | None
    frame_idx: int
    score: float
    trich: str  # đoạn doc_text quanh từ khớp, để nhìn phát biết vì sao lên hạng


def tach_tu(q: str) -> list[str]:
    """Truy vấn → danh sách từ khoá, viết thường, bỏ trùng, giữ thứ tự.

    ⚠️ **KHÔNG bỏ dấu.** Đường thi có `VI_FOLDED_ANALYSIS` của Elasticsearch nên gõ
    không dấu vẫn tra được; ở đây thì không. Lý do là số đo: bỏ dấu cả kho tốn
    **40,4 s mỗi truy vấn** (NFD + regex trên 371k tài liệu), so với 6,2 s chỉ viết
    thường. Đổi 34 s lấy tiện ích "gõ không dấu" là không đáng cho một đường lui.

    → Gõ tiếng Việt CÓ DẤU khi dùng chế độ offline. Gõ thiếu dấu vẫn chạy, chỉ là
    ít kết quả hơn — không sai, chỉ hụt.

    Bỏ từ dưới 2 ký tự: 'ở', 'và' không phân biệt được tài liệu nào với tài liệu nào,
    mà mỗi từ là một lượt quét toàn kho.
    """
    tu = [t for t in re.split(r"\W+", q.lower()) if len(t) >= 2]
    return list(dict.fromkeys(tu))


def _trich_quanh(doc: str, tu_khoa: list[str], rong: int = 90) -> str:
    """Cắt một đoạn `doc_text` quanh từ khớp đầu tiên — nhìn phát biết vì sao lên hạng."""
    thuong = doc.lower()
    for t in tu_khoa:
        i = thuong.find(t)
        if i >= 0:
            a, b = max(0, i - rong // 2), min(len(doc), i + rong)
            return ("…" if a else "") + doc[a:b].replace("\n", " ") + ("…" if b < len(doc) else "")
    return doc[:rong].replace("\n", " ")


def tim(query: str, top_k: int = 20, docs_path: Path | None = None) -> list[KetQuaOffline]:
    """BM25 thô trên `docs_bm25.parquet`. Trả top-K keyframe đã xếp hạng.

    Vào: truy vấn tiếng Việt (có dấu hay không đều được) · số kết quả.
    Ra: list `KetQuaOffline` xếp theo điểm giảm dần. Truy vấn không có từ nào ≥2 ký
    tự → trả rỗng.
    Bất biến: KHÔNG nạp cả cột `doc_text` vào RAM · không đặt ngưỡng điểm cứng (cùng
    lý do với CLAUDE.md bất biến 6 — lọc theo ngưỡng là vứt kết quả đúng).

    Một lượt quét duy nhất: vừa đếm tần suất từ, vừa đo độ dài tài liệu, vừa đếm số
    tài liệu chứa mỗi từ. Tính điểm sau khi quét xong vì IDF cần thống kê toàn kho.
    """
    import numpy as np
    import pandas as pd
    import pyarrow.parquet as pq

    p = docs_path or DOCS_PATH
    tu_khoa = tach_tu(query)
    if not tu_khoa or not p.exists():
        return []

    tf_lo: list[np.ndarray] = []      # tần suất từng từ trong từng tài liệu
    dai_lo: list[np.ndarray] = []     # độ dài tài liệu (số từ)
    meta_lo: list[pd.DataFrame] = []

    t0 = time.time()
    for lo in pq.ParquetFile(p).iter_batches(
        batch_size=LO, columns=["kf_id", "video_id", "shot_id", "frame_idx", "doc_text"]
    ):
        df = lo.to_pandas()
        van = df.doc_text.fillna("").str.lower()
        # Độ dài tính bằng KÝ TỰ, không phải số từ: `str.count(r"\s+")` tốn 29,7 s
        # còn `str.len()` tốn 1,0 s trên cùng bộ dữ liệu. BM25 chỉ cần một thước đo
        # NHẤT QUÁN để phạt tài liệu dài — ký tự hay từ đều được, miễn cùng đơn vị
        # với `dai_tb`.
        dai_lo.append(van.str.len().to_numpy(dtype=np.float32))
        tf_lo.append(np.stack(
            [van.str.count(re.escape(t)).to_numpy(dtype=np.float32) for t in tu_khoa]
        ))
        meta_lo.append(df.drop(columns=["doc_text"]))

    if not tf_lo:
        return []

    tf = np.concatenate(tf_lo, axis=1)          # (số_từ, số_tài_liệu)
    dai = np.concatenate(dai_lo)
    meta = pd.concat(meta_lo, ignore_index=True)

    n = len(dai)
    dai_tb = float(dai.mean()) or 1.0
    df_tu = (tf > 0).sum(axis=1)                # số tài liệu chứa mỗi từ
    # IDF chuẩn BM25: từ có mặt khắp nơi thì gần như không mang thông tin
    idf = np.log(1.0 + (n - df_tu + 0.5) / (df_tu + 0.5))

    mau = tf + BM25_K1 * (1.0 - BM25_B + BM25_B * dai / dai_tb)
    diem = (idf[:, None] * (tf * (BM25_K1 + 1.0)) / np.maximum(mau, 1e-9)).sum(axis=0)

    co_diem = np.flatnonzero(diem > 0)
    if co_diem.size == 0:
        return []
    thu_tu = co_diem[np.argsort(-diem[co_diem])[:top_k]]

    # Đọc lại doc_text CHỈ cho vài dòng thắng cuộc — rẻ hơn nhiều so với giữ cả cột
    can = set(meta.iloc[thu_tu].kf_id)
    doc_text = _doc_text_cua(p, can)

    print(f"  [offline] {n} tài liệu · {len(tu_khoa)} từ khoá · {time.time() - t0:.1f}s")
    return [
        KetQuaOffline(
            kf_id=str(r.kf_id),
            video_id=str(r.video_id),
            shot_id=str(r.shot_id) if r.shot_id is not None else None,
            frame_idx=int(r.frame_idx),
            score=round(float(diem[i]), 4),
            trich=_trich_quanh(doc_text.get(str(r.kf_id), ""), tu_khoa),
        )
        for i, r in zip(thu_tu, meta.iloc[thu_tu].itertuples(index=False))
    ]


def _doc_text_cua(p: Path, kf_ids: set[str]) -> dict[str, str]:
    """Lấy `doc_text` của đúng vài kf_id — quét lại theo lô, không giữ gì thừa."""
    import pyarrow.parquet as pq

    ra: dict[str, str] = {}
    for lo in pq.ParquetFile(p).iter_batches(batch_size=LO, columns=["kf_id", "doc_text"]):
        d = lo.to_pydict()
        for k, v in zip(d["kf_id"], d["doc_text"]):
            if k in kf_ids:
                ra[k] = v or ""
        if len(ra) == len(kf_ids):
            break
    return ra


def main() -> int:
    """CLI soi nhanh: `python -m app.offline_search "tên riêng hiếm"`."""
    import argparse

    ap = argparse.ArgumentParser(description="BM25 thô trên docs_bm25.parquet (D2.1, dev).")
    ap.add_argument("query")
    ap.add_argument("--top-k", type=int, default=10)
    args = ap.parse_args()

    kq = tim(args.query, args.top_k)
    if not kq:
        print("Không có kết quả (thử từ khoá khác, hoặc kiểm docs_bm25.parquet).")
        return 1
    for i, r in enumerate(kq, 1):
        print(f"{i:>3}. {r.score:>7.3f}  {r.kf_id:<22} frame {r.frame_idx:<7} {r.video_id}")
        print(f"      {r.trich}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
