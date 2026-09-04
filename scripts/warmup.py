"""Làm nóng + kiểm sống trước giờ thi — bấm một lệnh, đọc một màn hình.

===== Việc này giải quyết cái gì =====
Lần gọi search() ĐẦU TIÊN trong một process phải nạp encoder từ đĩa. Đo 03/09
trên làn KIS hai nhánh vector: câu 1 mất 25,5s, các câu sau 1,0–1,7s. Encoder
giữ trong biến global nên chi phí đó trả ĐÚNG MỘT LẦN cho mỗi process.

⚠️ Hệ quả quan trọng, đừng hiểu nhầm: `exam.py run` chạy CẢ LÔ KIS trong MỘT
subprocess `run.py`, nên nó tự trả 25s một lần rồi chạy tiếp ~1,4s/câu. Script
này KHÔNG làm lô đó nhanh hơn — process khác nhau không dùng chung model.

Vậy nó để làm gì:
  · Kiểm TRƯỚC 19:30 rằng Milvus, Elasticsearch và CẢ HAI encoder đều sống —
    biết hỏng lúc 19:00 thì còn sửa được, biết lúc 19:35 thì mất câu.
  · Kéo model vào cache đĩa của OS, nên lần nạp thật sau đó nhanh hơn.
  · Làm nóng API/UI nếu đang chạy qua uvicorn (process đó sống lâu).

===== Chạy =====
    .venv/bin/python scripts/warmup.py

Exit code: 0 = sẵn sàng · 1 = có thứ hỏng (đọc dòng HỎNG).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Câu nháp cố ý tầm thường và KHÔNG dính đề thi: mục đích là chạm vào mọi nhánh,
# không phải đo chất lượng. Giữ nguyên văn để lần chạy nào cũng so sánh được.
QUERY_VI = "một người đàn ông đang nói chuyện trước máy quay"
QUERY_EN = "a man talking in front of a camera"


def _buoc(ten: str, fn):
    """Chạy một bước, in thời gian, trả (đạt?, kết quả). Không cho lỗi thoát ra."""
    t0 = time.perf_counter()
    try:
        kq = fn()
    except Exception as e:  # noqa: BLE001 — đây là chỗ gom lỗi có chủ đích
        print(f"  HỎNG  {ten:34s} {time.perf_counter() - t0:6.2f}s  {type(e).__name__}: {e}")
        return False, None
    print(f"  ĐẠT   {ten:34s} {time.perf_counter() - t0:6.2f}s  {kq}")
    return True, kq


def main() -> int:
    print(f"LÀM NÓNG — {QUERY_VI!r}\n")
    ok = True

    def _milvus():
        from backend.indexing.milvus_client import COLLECTION_NAME, connect
        n = connect().get_collection_stats(COLLECTION_NAME)["row_count"]
        return f"{COLLECTION_NAME}: {int(n):,} vector"

    def _es():
        from backend.indexing.es_client import connect
        es = connect()
        if not es.ping():
            raise RuntimeError("ping thất bại")
        return "ping OK"

    def _clip():
        from backend.retrieval.text_query import encode_text
        v = encode_text(QUERY_EN)
        return f"CLIP {v.shape[0]} chiều · |v|={float((v @ v) ** .5):.4f}"

    def _siglip2():
        from backend.retrieval.siglip2_query import encode_text as enc2
        v = enc2(QUERY_EN)
        return f"SigLIP2 {v.shape[0]} chiều · |v|={float((v @ v) ** .5):.4f}"

    for ten, fn in (("Milvus", _milvus), ("Elasticsearch", _es),
                    ("encoder CLIP", _clip), ("encoder SigLIP2", _siglip2)):
        dat, _ = _buoc(ten, fn)
        ok = ok and dat

    # Một truy vấn thật qua ĐÚNG làn KIS — cùng tham số `backend/tasks/runner.py`
    # truyền lúc thi. Chạy hai lần: lần đầu gồm nạp model, lần sau là tốc độ thật.
    def _lan_kis():
        from backend.retrieval.search import search
        from data.config.search_weights import KIS_CANDIDATE_MULTIPLIER
        rows = search(QUERY_VI, query_en=QUERY_EN, top_k=100, group_by_shot=True,
                      branches={"vector_siglip2": True, "ocr_probe": True},
                      candidate_multiplier=KIS_CANDIDATE_MULTIPLIER)
        if len(rows) < 1:
            raise RuntimeError("làn KIS trả 0 dòng — có nhánh nào đang chết lặng")
        return f"{len(rows)} dòng"

    dat1, _ = _buoc("làn KIS (lần 1, gồm nạp model)", _lan_kis)
    dat2, _ = _buoc("làn KIS (lần 2, tốc độ thật)", _lan_kis)
    ok = ok and dat1 and dat2

    print()
    if ok:
        print("SẴN SÀNG — mọi nhánh sống. Lô KIS thật sẽ trả phí nạp model một lần.")
        return 0
    print("CHƯA SẴN SÀNG — sửa dòng HỎNG ở trên trước khi thi.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
