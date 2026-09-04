"""Làm nóng + kiểm sống trước giờ thi — bấm một lệnh, đọc một màn hình.

===== Việc này giải quyết cái gì =====
Lần gọi search() ĐẦU TIÊN trong một process phải nạp encoder từ đĩa. Đo 03/09
trên làn KIS hai nhánh vector: câu 1 mất 25,5s, các câu sau 1,0–1,7s. Encoder
giữ trong biến global nên chi phí đó trả ĐÚNG MỘT LẦN cho mỗi process.

⚠️ Hệ quả quan trọng, đừng hiểu nhầm: `exam.py run` chạy CẢ LÔ KIS trong MỘT
subprocess `run.py`, nên nó tự trả 25s một lần rồi chạy tiếp ~1,4s/câu. Script
này KHÔNG làm lô đó nhanh hơn — process khác nhau không dùng chung model.

Vậy nó để làm gì:
  · Kiểm TRƯỚC 19:30 rằng Milvus, Elasticsearch và encoder của MỌI NHÁNH ĐANG
    BẬT đều sống — biết hỏng lúc 19:00 thì còn sửa được, biết lúc 19:35 thì mất
    câu. Nhánh tắt trong config thì bỏ qua, không kiểm và không tính là hỏng.
  · Kéo model vào cache đĩa của OS, nên lần nạp thật sau đó nhanh hơn.
  · Làm nóng API/UI nếu đang chạy qua uvicorn (process đó sống lâu).

===== Chạy =====
    .venv/bin/python scripts/warmup.py

Exit code: 0 = sẵn sàng · 1 = có thứ hỏng (đọc dòng HỎNG).
"""
from __future__ import annotations

import contextlib
import io
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# `search()` báo mọi sự cố xuống cấp bằng đúng tiền tố này rồi CHẠY TIẾP: nhánh
# chết, dịch VI→EN hỏng, không đọc được shots.parquet... Lúc thi đó là hành vi
# đúng (một nhánh chết không được kéo sập cả câu). Lúc làm nóng thì ngược lại:
# còn 2 tiếng để sửa, nên bất kỳ dòng nào như vậy đều phải làm warmup ĐỎ.
# `tests/test_warmup.py` ghim tiền tố này khớp với search.py.
CANH_BAO = "[cảnh báo]"

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


def _nhanh_bat() -> dict[str, bool]:
    """Tập nhánh làn KIS thật sự chạy = `BRANCHES` gộp override của runner.

    IMPORT chứ không chép giá trị, đúng lý do đã ghi ở `preflight_check.py`:
    chép tay thì warmup và đường thi trôi khỏi nhau, mà cái trôi đó không crash.
    """
    from backend.tasks.runner import KIS_BRANCH_OVERRIDE
    from data.config.search_weights import BRANCHES

    return {**BRANCHES, **KIS_BRANCH_OVERRIDE}


def _dung_nhanh_vector_thu_hai() -> bool:
    return bool(_nhanh_bat().get("vector_siglip2"))


def _kiem_milvus() -> str:
    """Kiểm collection vector mà nhánh ĐANG BẬT dựa vào, kèm provenance.

    04/09 — chỉ kiểm collection của nhánh đang bật, không kiểm cứng cả hai.
    Nhánh TẮT là quyết định đã ghi trong config, không phải hỏng hóc; bắt warmup
    đỏ vì nó thì người vận hành học cách bỏ qua màn hình đỏ, và lần sau có nhánh
    chết thật cũng không ai tin nữa. Nhánh BẬT thì vẫn kiểm gắt như cũ.
    """
    from backend.indexing.load_clip import assert_index_meta
    from backend.indexing.load_siglip2 import assert_siglip2_index_meta
    from backend.indexing.milvus_client import COLLECTION_NAME, connect
    from data.config.siglip2_model import SIGLIP2_COLLECTION

    # Mirror `encoder_chinh`/`encoder_phu` trong search.py: nhánh thứ hai luôn là
    # encoder CÒN LẠI, không phải "luôn SigLIP2".
    from data.config.siglip2_model import use_siglip2

    if use_siglip2():
        can_kiem = [(SIGLIP2_COLLECTION, assert_siglip2_index_meta)]
        phu = (COLLECTION_NAME, assert_index_meta)
    else:
        can_kiem = [(COLLECTION_NAME, assert_index_meta)]
        phu = (SIGLIP2_COLLECTION, assert_siglip2_index_meta)
    if _dung_nhanh_vector_thu_hai():
        can_kiem.append(phu)

    client = connect()
    thong_ke: list[str] = []
    for collection_name, assert_meta in can_kiem:
        if not client.has_collection(collection_name):
            raise RuntimeError(f"thiếu collection {collection_name}")
        row_count = int(client.get_collection_stats(collection_name)["row_count"])
        if row_count <= 0:
            raise RuntimeError(f"collection {collection_name} rỗng")
        assert_meta(strict=True)
        thong_ke.append(f"{collection_name}: {row_count:,} vector")

    if not _dung_nhanh_vector_thu_hai():
        thong_ke.append(f"bỏ qua {phu[0]} (nhánh vector_siglip2 TẮT)")
    return " · ".join(thong_ke)


def main() -> int:
    print(f"LÀM NÓNG — {QUERY_VI!r}\n")
    ok = True

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

    buoc = [("Milvus", _kiem_milvus), ("Elasticsearch", _es), ("encoder CLIP", _clip)]
    if _dung_nhanh_vector_thu_hai():
        buoc.append(("encoder SigLIP2", _siglip2))
    else:
        # Nạp encoder SigLIP2 mất ~84s đo 04/09. Không nhánh nào dùng nó thì đó
        # là 84 giây trả cho một model sẽ không được gọi lần nào trong buổi thi.
        print(f"  bỏ qua {'encoder SigLIP2':34s}         nhánh vector_siglip2 TẮT")
    for ten, fn in buoc:
        dat, _ = _buoc(ten, fn)
        ok = ok and dat

    # Một truy vấn thật qua ĐÚNG làn KIS — cùng tham số `backend/tasks/runner.py`
    # truyền lúc thi. Chạy hai lần: lần đầu gồm nạp model, lần sau là tốc độ thật.
    def _lan_kis():
        from backend.retrieval.search import search
        from backend.tasks.runner import KIS_BRANCH_OVERRIDE
        from data.config.search_weights import KIS_CANDIDATE_MULTIPLIER

        # Bắt stdout của `search()` thay vì chỉ nhìn số dòng trả về. `_an_toan()`
        # nuốt lỗi từng nhánh rồi in một dòng cảnh báo và đi tiếp — nên một nhánh
        # chết vẫn cho ĐỦ 100 dòng và bước này vẫn xanh. Đúng chuyện đã xảy ra
        # 04/09: `keyframes_siglip2` biến mất, warmup in cảnh báo rồi vẫn kết
        # luận "SẴN SÀNG — mọi nhánh sống".
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            rows = search(QUERY_VI, query_en=QUERY_EN, top_k=100, group_by_shot=True,
                          branches=dict(KIS_BRANCH_OVERRIDE),
                          candidate_multiplier=KIS_CANDIDATE_MULTIPLIER)
        log = buffer.getvalue().splitlines()
        for dong in log:  # không nuốt log của search()
            print(f"    {dong.strip()}")
        xuong_cap = [d.strip() for d in log if CANH_BAO in d]
        if xuong_cap:
            raise RuntimeError(
                f"{len(xuong_cap)} sự cố xuống cấp trong lượt search: " + " | ".join(xuong_cap)
            )
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
