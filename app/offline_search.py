# app/offline_search.py — BM25 trên docs_bm25.parquet, không cần Milvus/Elasticsearch.
#
# Công cụ DEV, không phải đường thi. Đường thi là `backend.retrieval.search.search()`.
# Tồn tại để mở được UI khi Docker chưa lên và để soi chất lượng `doc_text`.
#
# Số đo cho từng lựa chọn: reports/D21_TECHNICAL_REPORT.md §6.3.

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path

DOCS_PATH = Path(__file__).resolve().parents[1] / "data" / "derived" / "docs_bm25.parquet"

# Mặc định của Elasticsearch — giữ nguyên để offline và live cùng thang điểm.
BM25_K1 = 1.5
BM25_B = 0.75

BATCH_SIZE = 50_000   # quét theo lô: nạp cả cột doc_text tốn ~845 MB RAM
SNIPPET_WIDTH = 90

# Ranh giới từ, viết cho RE2 (công cụ regex của pyarrow).
#
# ⚠️ KHÔNG được thay bằng `\b`. `\b` của RE2 chỉ coi [A-Za-z0-9_] là chữ cái nên 'ù'
# bị tính là dấu ngắt từ: `\btù\b` KHÔNG khớp 'tù nhân' (sau 'ù' là dấu cách, hai bên
# đều "không phải chữ" nên không có ranh giới) nhưng LẠI khớp 'tùng' (sau 'ù' là 'n',
# có ranh giới). Sai ngược hoàn toàn, không dấu hiệu gì. `\p{L}` là lớp chữ cái
# Unicode nên hiểu đúng nguyên âm có dấu.
_WORD_BOUNDARY = r"(?:^|[^\p{L}\p{N}_])%s(?:[^\p{L}\p{N}_]|$)"


@dataclass(frozen=True)
class OfflineHit:
    kf_id: str
    video_id: str
    shot_id: str | None
    frame_idx: int
    score: float
    snippet: str   # đoạn doc_text quanh từ khớp


def tokenize(query: str) -> list[str]:
    """Truy vấn → từ khoá viết thường, bỏ trùng, giữ thứ tự.

    KHÔNG bỏ dấu: bỏ dấu cả kho tốn 40,4 s mỗi truy vấn → gõ tiếng Việt CÓ DẤU.
    Bỏ từ dưới 2 ký tự: không phân biệt được tài liệu nào với tài liệu nào.
    """
    words = [t for t in re.split(r"\W+", query.lower()) if len(t) >= 2]
    return list(dict.fromkeys(words))


def _count_whole_word(texts, word: str):
    """Số lần `word` xuất hiện NHƯ MỘT TỪ trong từng tài liệu.

    Đếm chuỗi con là sai: tiếng Việt đơn âm nên 'ba' khớp cả trong 'baothanhnien',
    thổi phồng tần suất tới 45 lần và đẩy rác lên hạng 1.

    Hai lượt. Lượt 1 đếm chuỗi con — rẻ, và là CẬN TRÊN nên không bỏ sót tài liệu nào.
    Lượt 2 đếm đúng ranh giới từ, chỉ trên số tài liệu đã lọt lượt 1. Tổng 14,2 s cho
    5 từ khoá trên toàn kho, bằng đúng bản đếm chuỗi con.

    Gọi thẳng pyarrow.compute chứ không qua pandas.str.count: pandas 3.0 tự chọn
    backend theo dtype (str → RE2, object → module `re`), hai backend cho kết quả
    KHÁC NHAU ở đây, và pandas không hứa giữ nguyên cách chọn.
    """
    import numpy as np
    import pyarrow as pa
    import pyarrow.compute as pc

    candidates = texts.str.count(re.escape(word)).to_numpy() > 0
    counts = np.zeros(len(texts), dtype=np.float32)
    if candidates.any():
        hit = pc.count_substring_regex(
            pa.array(texts[candidates]), _WORD_BOUNDARY % re.escape(word)
        )
        counts[candidates] = hit.to_numpy(zero_copy_only=False)
    return counts


def _snippet(doc: str, words: list[str], width: int = SNIPPET_WIDTH) -> str:
    """Cắt đoạn doc_text quanh từ khớp đầu tiên — nhìn phát biết vì sao lên hạng."""
    lower = doc.lower()
    for w in words:
        i = lower.find(w)
        if i >= 0:
            a, b = max(0, i - width // 2), min(len(doc), i + width)
            return ("…" if a else "") + doc[a:b].replace("\n", " ") + ("…" if b < len(doc) else "")
    return doc[:width].replace("\n", " ")


def _str_or_none(v) -> str | None:
    """Ô rỗng của parquet ra NaN/NaT chứ không phải None — `str()` thẳng sẽ ra chuỗi
    'nan' rồi trôi vào file nhãn mà không ai nhận ra."""
    if v is None or v != v:
        return None
    return str(v)


def search(query: str, top_k: int = 20, docs_path: Path | None = None) -> list[OfflineHit]:
    """BM25 trên docs_bm25.parquet, trả top-K keyframe đã xếp hạng.

    Vào: truy vấn tiếng Việt · số kết quả. Ra: list OfflineHit, điểm giảm dần.
    Bất biến: không nạp cả cột `doc_text` vào RAM · không đặt ngưỡng điểm cứng.

    Một lượt quét gom tần suất từ + độ dài tài liệu; tính điểm sau vì IDF cần thống
    kê toàn kho.
    """
    import numpy as np
    import pandas as pd
    import pyarrow.parquet as pq

    path = docs_path or DOCS_PATH
    words = tokenize(query)
    if not words or not path.exists():
        return []

    tf_batches: list[np.ndarray] = []
    len_batches: list[np.ndarray] = []
    meta_batches: list[pd.DataFrame] = []

    t0 = time.time()
    for batch in pq.ParquetFile(path).iter_batches(
        batch_size=BATCH_SIZE,
        columns=["kf_id", "video_id", "shot_id", "frame_idx", "doc_text"],
    ):
        df = batch.to_pandas()
        if df.empty:
            continue
        texts = df.doc_text.fillna("").str.lower()
        # Độ dài đo bằng KÝ TỰ: str.len() tốn 1,0 s, đếm khoảng trắng tốn 29,7 s.
        # BM25 chỉ cần một thước đo nhất quán để phạt tài liệu dài.
        len_batches.append(texts.str.len().to_numpy(dtype=np.float32))
        tf_batches.append(np.stack([_count_whole_word(texts, w) for w in words]))
        meta_batches.append(df.drop(columns=["doc_text"]))

    if not tf_batches:
        return []

    tf = np.concatenate(tf_batches, axis=1)   # (số_từ, số_tài_liệu)
    lengths = np.concatenate(len_batches)
    meta = pd.concat(meta_batches, ignore_index=True)

    n_docs = len(lengths)
    avg_len = float(lengths.mean())
    if not avg_len > 0:   # kho rỗng hoặc doc_text toàn rỗng; bắt luôn cả NaN
        return []
    df_word = (tf > 0).sum(axis=1)
    idf = np.log(1.0 + (n_docs - df_word + 0.5) / (df_word + 0.5))

    denom = tf + BM25_K1 * (1.0 - BM25_B + BM25_B * lengths / avg_len)
    scores = (idf[:, None] * (tf * (BM25_K1 + 1.0)) / np.maximum(denom, 1e-9)).sum(axis=0)

    scored = np.flatnonzero(scores > 0)
    if scored.size == 0:
        return []
    order = scored[np.argsort(-scores[scored])[:top_k]]

    # Đọc lại doc_text CHỈ cho vài dòng thắng cuộc, rẻ hơn giữ cả cột trong RAM
    doc_texts = _doc_texts_for(path, set(meta.iloc[order].kf_id))

    print(f"  [offline] {n_docs} tài liệu · {len(words)} từ khoá · {time.time() - t0:.1f}s")
    return [
        OfflineHit(
            kf_id=str(r.kf_id),
            video_id=str(r.video_id),
            shot_id=_str_or_none(r.shot_id),
            frame_idx=int(r.frame_idx),
            score=round(float(scores[i]), 4),
            snippet=_snippet(doc_texts.get(str(r.kf_id), ""), words),
        )
        for i, r in zip(order, meta.iloc[order].itertuples(index=False))
    ]


def _doc_texts_for(path: Path, kf_ids: set[str]) -> dict[str, str]:
    """doc_text của đúng vài kf_id — quét lại theo lô, không giữ gì thừa."""
    import pyarrow.parquet as pq

    out: dict[str, str] = {}
    for batch in pq.ParquetFile(path).iter_batches(
        batch_size=BATCH_SIZE, columns=["kf_id", "doc_text"]
    ):
        d = batch.to_pydict()
        for k, v in zip(d["kf_id"], d["doc_text"]):
            if k in kf_ids:
                out[k] = v or ""
        if len(out) == len(kf_ids):
            break
    return out


def main() -> int:
    """CLI soi nhanh: `python -m app.offline_search "tên riêng hiếm"`."""
    import argparse

    ap = argparse.ArgumentParser(description="BM25 trên docs_bm25.parquet (dev).")
    ap.add_argument("query")
    ap.add_argument("--top-k", type=int, default=10)
    args = ap.parse_args()

    hits = search(args.query, args.top_k)
    if not hits:
        print("Không có kết quả (thử từ khoá khác, hoặc kiểm docs_bm25.parquet).")
        return 1
    for i, r in enumerate(hits, 1):
        print(f"{i:>3}. {r.score:>7.3f}  {r.kf_id:<22} frame {r.frame_idx:<7} {r.video_id}")
        print(f"      {r.snippet}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
