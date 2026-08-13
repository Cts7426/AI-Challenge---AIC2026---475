# app/offline_search.py — D2.1: BM25 trên docs_bm25.parquet, không cần Milvus/ES.
#
# Công cụ DEV, không phải đường thi. Đường thi là `backend.retrieval.search.search()`.
# Tồn tại để mở được UI khi Docker chưa lên và để soi chất lượng `doc_text`.
#
# Số đo và lý do chọn từng cách làm: reports/D21_TECHNICAL_REPORT.md §5.

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path

DOCS_PATH = Path(__file__).resolve().parents[1] / "data" / "derived" / "docs_bm25.parquet"

# Mặc định của Elasticsearch — giữ nguyên để offline và live cùng thang điểm.
BM25_K1 = 1.5
BM25_B = 0.75

CO_LO = 50_000  # dòng mỗi lô; quét theo lô vì nạp cả cột doc_text tốn ~845 MB RAM
DAI_TRICH = 90


@dataclass(frozen=True)
class KetQuaOffline:
    kf_id: str
    video_id: str
    shot_id: str | None
    frame_idx: int
    score: float
    trich: str  # đoạn doc_text quanh từ khớp


def tach_tu(q: str) -> list[str]:
    """Truy vấn → từ khoá viết thường, bỏ trùng, giữ thứ tự.

    KHÔNG bỏ dấu: bỏ dấu cả kho tốn 40,4 s mỗi truy vấn. → gõ tiếng Việt CÓ DẤU.
    Bỏ từ dưới 2 ký tự: không phân biệt được tài liệu nào với tài liệu nào.
    """
    tu = [t for t in re.split(r"\W+", q.lower()) if len(t) >= 2]
    return list(dict.fromkeys(tu))


# Ranh giới từ, viết cho RE2 (công cụ regex của pyarrow — xem `_dem_dung_tu`).
#
# ⚠️ KHÔNG được thay bằng `\b`. `\b` của RE2 chỉ coi [A-Za-z0-9_] là chữ cái, nên
# 'ù' bị tính là dấu ngắt từ: `\btù\b` KHÔNG khớp 'tù nhân' (sau 'ù' là dấu cách,
# hai bên đều "không phải chữ" nên không có ranh giới) nhưng LẠI khớp 'tùng' (sau
# 'ù' là 'n', có ranh giới). Sai ngược hoàn toàn, và không có dấu hiệu gì.
# `\p{L}` là lớp chữ cái Unicode nên nó hiểu đúng nguyên âm có dấu.
_RANH_GIOI_TU = r"(?:^|[^\p{L}\p{N}_])%s(?:[^\p{L}\p{N}_]|$)"


def _dem_dung_tu(van, tu: str):
    """Số lần `tu` xuất hiện NHƯ MỘT TỪ trong từng tài liệu.

    Đếm chuỗi con là sai: tiếng Việt đơn âm nên 'ba' khớp cả trong 'baothanhnien',
    thổi phồng tần suất tới 45 lần (đo trên L21_V001) và đẩy rác lên hạng 1.

    Hai lượt. Lượt 1 đếm chuỗi con — rẻ, và là CẬN TRÊN nên không bỏ sót tài liệu
    nào. Lượt 2 đếm đúng ranh giới từ, chỉ trên số tài liệu đã lọt lượt 1. Tổng
    14,2 s cho 5 từ khoá trên toàn kho, bằng đúng bản đếm chuỗi con.

    Gọi thẳng `pyarrow.compute` chứ không qua `pandas.str.count`: pandas 3.0 tự chọn
    backend theo dtype (str → RE2, object → module `re`), hai backend cho ra kết quả
    KHÁC NHAU ở đây, và pandas không hứa giữ nguyên cách chọn. Gọi thẳng thì luôn
    biết mình đang chạy công cụ nào, và `_RANH_GIOI_TU` viết đúng cho công cụ đó.
    """
    import numpy as np
    import pyarrow as pa
    import pyarrow.compute as pc

    ung_vien = van.str.count(re.escape(tu)).to_numpy() > 0
    dem = np.zeros(len(van), dtype=np.float32)
    if ung_vien.any():
        so = pc.count_substring_regex(
            pa.array(van[ung_vien]), _RANH_GIOI_TU % re.escape(tu)
        )
        dem[ung_vien] = so.to_numpy(zero_copy_only=False)
    return dem


def _trich_quanh(doc: str, tu_khoa: list[str], rong: int = DAI_TRICH) -> str:
    """Cắt đoạn doc_text quanh từ khớp đầu tiên — nhìn phát biết vì sao lên hạng."""
    thuong = doc.lower()
    for t in tu_khoa:
        i = thuong.find(t)
        if i >= 0:
            a, b = max(0, i - rong // 2), min(len(doc), i + rong)
            return ("…" if a else "") + doc[a:b].replace("\n", " ") + ("…" if b < len(doc) else "")
    return doc[:rong].replace("\n", " ")


def tim(query: str, top_k: int = 20, docs_path: Path | None = None) -> list[KetQuaOffline]:
    """BM25 trên `docs_bm25.parquet`, trả top-K keyframe đã xếp hạng.

    Vào: truy vấn tiếng Việt · số kết quả. Ra: list `KetQuaOffline`, điểm giảm dần.
    Bất biến: không nạp cả cột `doc_text` vào RAM · không đặt ngưỡng điểm cứng.

    Một lượt quét gom tần suất từ + độ dài tài liệu; tính điểm sau vì IDF cần thống
    kê toàn kho.
    """
    import numpy as np
    import pandas as pd
    import pyarrow.parquet as pq

    p = docs_path or DOCS_PATH
    tu_khoa = tach_tu(query)
    if not tu_khoa or not p.exists():
        return []

    tf_lo: list[np.ndarray] = []
    dai_lo: list[np.ndarray] = []
    meta_lo: list[pd.DataFrame] = []

    t0 = time.time()
    for lo in pq.ParquetFile(p).iter_batches(
        batch_size=CO_LO, columns=["kf_id", "video_id", "shot_id", "frame_idx", "doc_text"]
    ):
        df = lo.to_pandas()
        if df.empty:
            continue
        van = df.doc_text.fillna("").str.lower()
        # Độ dài đo bằng KÝ TỰ: str.len() tốn 1,0 s, đếm khoảng trắng tốn 29,7 s.
        # BM25 chỉ cần một thước đo nhất quán để phạt tài liệu dài.
        dai_lo.append(van.str.len().to_numpy(dtype=np.float32))
        tf_lo.append(np.stack([_dem_dung_tu(van, t) for t in tu_khoa]))
        meta_lo.append(df.drop(columns=["doc_text"]))

    if not tf_lo:
        return []

    tf = np.concatenate(tf_lo, axis=1)  # (số_từ, số_tài_liệu)
    dai = np.concatenate(dai_lo)
    meta = pd.concat(meta_lo, ignore_index=True)

    n = len(dai)
    dai_tb = float(dai.mean())
    if not dai_tb > 0:  # kho rỗng hoặc toàn doc_text rỗng — cũng bắt luôn NaN
        return []
    so_tl_chua = (tf > 0).sum(axis=1)
    idf = np.log(1.0 + (n - so_tl_chua + 0.5) / (so_tl_chua + 0.5))

    mau = tf + BM25_K1 * (1.0 - BM25_B + BM25_B * dai / dai_tb)
    diem = (idf[:, None] * (tf * (BM25_K1 + 1.0)) / np.maximum(mau, 1e-9)).sum(axis=0)

    co_diem = np.flatnonzero(diem > 0)
    if co_diem.size == 0:
        return []
    thu_tu = co_diem[np.argsort(-diem[co_diem])[:top_k]]

    # Đọc lại doc_text CHỈ cho vài dòng thắng cuộc, rẻ hơn giữ cả cột trong RAM
    doc_text = _doc_text_cua(p, set(meta.iloc[thu_tu].kf_id))

    print(f"  [offline] {n} tài liệu · {len(tu_khoa)} từ khoá · {time.time() - t0:.1f}s")
    return [
        KetQuaOffline(
            kf_id=str(r.kf_id),
            video_id=str(r.video_id),
            shot_id=_chuoi_hoac_none(r.shot_id),
            frame_idx=int(r.frame_idx),
            score=round(float(diem[i]), 4),
            trich=_trich_quanh(doc_text.get(str(r.kf_id), ""), tu_khoa),
        )
        for i, r in zip(thu_tu, meta.iloc[thu_tu].itertuples(index=False))
    ]


def _chuoi_hoac_none(v) -> str | None:
    """Ô rỗng của parquet ra `NaN`/`NaT`, không phải `None` — `str()` thẳng sẽ ra
    chuỗi 'nan' rồi trôi vào nhãn và không ai nhận ra."""
    if v is None or v != v:
        return None
    return str(v)


def _doc_text_cua(p: Path, kf_ids: set[str]) -> dict[str, str]:
    """`doc_text` của đúng vài kf_id — quét lại theo lô, không giữ gì thừa."""
    import pyarrow.parquet as pq

    ra: dict[str, str] = {}
    for lo in pq.ParquetFile(p).iter_batches(batch_size=CO_LO, columns=["kf_id", "doc_text"]):
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

    ap = argparse.ArgumentParser(description="BM25 trên docs_bm25.parquet (D2.1, dev).")
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
