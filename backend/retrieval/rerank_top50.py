# backend/retrieval/rerank_top50.py — R3.K4: xếp lại top-50 sau RRF
#
# ===== Vì sao cần một tầng NỮA sau RRF =====
# RRF cố tình chỉ nhìn THỨ HẠNG và vứt điểm đi. Đó là lựa chọn đúng cho việc
# hợp nhất các nhánh khác thang đo (cosine [-1,1] vs BM25 không chặn trên).
# Nhưng nó cũng vứt luôn ba thứ có ích:
#   1. "hạng 1 bỏ xa phần còn lại" hay "hạng 1 chỉ nhỉnh hơn hạng 2 một tí"
#   2. một nhánh đẩy mạnh, hay bốn nhánh cùng gật đầu
#   3. hai encoder KHÁC KHÔNG GIAN có cùng đề cử một keyframe hay không
# Tầng này lấy lại ba thứ đó và chỉ dùng để xáo lại TOP_N dòng đầu.
#
# ===== Nguyên tắc =====
# · Không gọi LLM. Đây là đường chạy online của KIS (bất biến 9 + ngân sách 30s).
# · Không ngưỡng cứng trên cosine (bất biến 5) — chỉ dùng z-score TRONG một
#   truy vấn, nơi so sánh tương đối mới có nghĩa.
# · Không đụng dòng thứ TOP_N+1 trở đi: xáo sâu chỉ thêm cơ hội đẩy nhầm.
# · Trả về danh sách MỚI, không sửa tại chỗ — chỗ gọi còn cần bản RRF gốc để
#   đối chiếu khi phân tích lỗi.
#
# ===== Chạy thử =====
#   python -m backend.retrieval.rerank_top50 --demo

from __future__ import annotations

from statistics import mean, pstdev

from data.config.rerank import (
    ENABLED,
    TOP_N,
    W_CONSENSUS,
    W_COSINE,
    W_VECTOR_AGREE,
)

NHANH_VECTOR = ("vector", "vector_siglip2")


def _chuan_hoa(gia_tri: list[float]) -> list[float]:
    """Đưa về [0,1] theo min–max TRONG một truy vấn.

    Vì sao min–max chứ không z-score: đầu ra cần cùng thang với nhau để cộng
    theo trọng số. z-score cho số âm, cộng vào thành TRỪ điểm — dễ thành trừng
    phạt ngầm một dòng chỉ vì nó dưới trung bình, chứ không phải vì nó xấu.
    Danh sách phẳng (mọi giá trị bằng nhau) → trả 0 hết: không có thông tin thì
    không thưởng ai, chứ không chia đều.
    """
    if not gia_tri:
        return []
    lo, hi = min(gia_tri), max(gia_tri)
    if hi - lo < 1e-12:
        return [0.0] * len(gia_tri)
    return [(v - lo) / (hi - lo) for v in gia_tri]


def _diem_dong_thuan(r: dict) -> float:
    """Bao nhiêu nhánh độc lập đề cử dòng này (đếm thô, chuẩn hoá ở ngoài)."""
    return float(len(r.get("ranks") or {}))


def _diem_cosine(r: dict) -> float | None:
    """Cosine tốt nhất trong các nhánh vector, `None` nếu không nhánh nào có.

    Lấy MAX chứ không lấy trung bình: một keyframe chỉ nằm trong pool của một
    encoder thì trung bình sẽ phạt nó vì thiếu số của encoder kia — mà thiếu ở
    đây nghĩa là "ngoài pool", không phải "điểm thấp".
    """
    cos = r.get("cos") or {}
    co = [v for v in cos.values() if v is not None]
    return max(co) if co else None


def _hai_nhanh_cung_de_cu(r: dict) -> float:
    """1.0 nếu CẢ HAI nhánh vector cùng đề cử keyframe này, ngược lại 0.0."""
    ranks = r.get("ranks") or {}
    return 1.0 if all(ten in ranks for ten in NHANH_VECTOR) else 0.0


def rerank(
    ket_qua: list[dict],
    top_n: int | None = None,
    enabled: bool | None = None,
) -> list[dict]:
    """Xếp lại `top_n` dòng đầu. Trả danh sách MỚI.

    `enabled=None` → đọc `data/config/rerank.ENABLED`. Truyền tường minh để đo
    (bật/tắt trong cùng một tiến trình mà không phải sửa config).

    Mỗi dòng được xếp lại nhận thêm hai khoá:
        `rrf_rank`   — hạng TRƯỚC khi rerank (bắt buộc: không có nó thì không
                       biết tầng này đã đẩy dòng nào lên/xuống — bất biến 7)
        `rerank`     — {score, các tín hiệu đã chuẩn hoá}
    """
    bat = ENABLED if enabled is None else enabled
    n = TOP_N if top_n is None else top_n
    if not bat or len(ket_qua) < 2:
        return list(ket_qua)

    dau, duoi = ket_qua[:n], ket_qua[n:]

    rrf = _chuan_hoa([r.get("score", 0.0) for r in dau])
    dong_thuan = _chuan_hoa([_diem_dong_thuan(r) for r in dau])

    # Dòng không có cosine ở nhánh vector nào (vd: chỉ do OCR/ASR đề cử) nhận 0 —
    # không thưởng, cũng không phạt. Điền giá trị trung bình vào đó sẽ là bịa ra
    # một tín hiệu không tồn tại.
    cos_tho = [_diem_cosine(r) for r in dau]
    co_cos = [v for v in cos_tho if v is not None]
    if co_cos:
        lo, hi = min(co_cos), max(co_cos)
        khoang = hi - lo
        cos_chuan = [
            0.0 if v is None or khoang < 1e-12 else (v - lo) / khoang
            for v in cos_tho
        ]
    else:
        cos_chuan = [0.0] * len(dau)

    dong_y = [_hai_nhanh_cung_de_cu(r) for r in dau]
    # Không nhánh vector thứ hai → tín hiệu này không tồn tại, tắt hẳn trọng số
    # thay vì cộng 0 cho mọi dòng (kết quả giống nhau nhưng ý nghĩa khác: ở đây
    # ta muốn NÓI RÕ trong log là tín hiệu vắng mặt).
    w_dong_y = W_VECTOR_AGREE if any(dong_y) else 0.0

    moi = []
    for i, r in enumerate(dau):
        diem = (
            rrf[i]
            + W_CONSENSUS * dong_thuan[i]
            + W_COSINE * cos_chuan[i]
            + w_dong_y * dong_y[i]
        )
        r2 = dict(r)
        r2["rrf_rank"] = i + 1
        r2["rerank"] = {
            "score": round(diem, 6),
            "rrf_norm": round(rrf[i], 4),
            "consensus": round(dong_thuan[i], 4),
            "cosine": round(cos_chuan[i], 4),
            "vector_agree": dong_y[i],
            "w_vector_agree": w_dong_y,
        }
        moi.append(r2)

    # `sorted` ổn định: hai dòng cùng điểm giữ nguyên thứ tự RRF cũ — không tạo
    # ra xáo trộn ngẫu nhiên ở chỗ tầng này không có ý kiến gì.
    moi.sort(key=lambda r: r["rerank"]["score"], reverse=True)
    return moi + list(duoi)


def _demo() -> None:
    """Ba dòng giả, đủ để thấy tầng này đổi thứ tự theo hướng nào."""
    mau = [
        {"keyframe_id": "A", "score": 0.30, "ranks": {"vector": 1},
         "cos": {"vector": 0.31}},
        {"keyframe_id": "B", "score": 0.28,
         "ranks": {"vector": 3, "vector_siglip2": 2, "ocr": 5, "objects": 9},
         "cos": {"vector": 0.29, "vector_siglip2": 0.33}},
        {"keyframe_id": "C", "score": 0.10, "ranks": {"ocr": 40}, "cos": {}},
    ]
    print("trước:", [r["keyframe_id"] for r in mau])
    sau = rerank(mau, enabled=True)
    print("sau  :", [r["keyframe_id"] for r in sau])
    for r in sau:
        if "rerank" in r:
            print(f"  {r['keyframe_id']}  {r['rerank']}")
    print("\nB lên đầu: RRF thấp hơn A một chút, nhưng bốn nhánh cùng đề cử và "
          "CẢ HAI encoder đồng ý — bằng chứng rộng hơn một nhánh đẩy mạnh.")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()
    if a.demo:
        _demo()
    else:
        ap.print_help()
