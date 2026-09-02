"""R3.K4 — tầng rerank top-50.

Mỗi test ở đây neo vào một lỗi IM LẶNG đã thật sự xảy ra hoặc suýt xảy ra, chứ
không phải kiểm cho đủ mặt.
"""
from backend.retrieval.rerank_top50 import rerank


def _dong(kf, score, ranks, cos=None):
    return {"keyframe_id": kf, "score": score, "ranks": ranks, "cos": cos or {}}


def test_tat_thi_tra_nguyen_khong_doi_mot_dong():
    """Mặc định phải là KHÔNG-LÀM-GÌ. Q&A/TRAKE gọi chung search()."""
    goc = [_dong("A", 0.3, {"vector": 1}), _dong("B", 0.2, {"ocr": 4})]
    assert [r["keyframe_id"] for r in rerank(goc, enabled=False)] == ["A", "B"]


def test_khong_sua_tai_cho_danh_sach_goc():
    """Chỗ gọi còn cần bản RRF gốc để đối chiếu khi phân tích lỗi."""
    goc = [_dong("A", 0.3, {"vector": 1}), _dong("B", 0.2, {"vector": 2, "ocr": 1})]
    truoc = [dict(r) for r in goc]
    rerank(goc, enabled=True)
    assert goc == truoc


def test_ghi_de_score_chu_khong_chi_them_khoa():
    """LỖI ĐÃ XẢY RA 02/09: `allocate()` tự sắp lại đầu vào theo `score`.

    Bản đầu chỉ thêm `rerank.score` và đổi thứ tự danh sách → thứ tự mới bị vứt
    ngay bước sau, bật/tắt rerank cho ra số liệu GIỐNG HỆT. Không có test này
    thì lần refactor sau lại rơi vào đúng cái bẫy đó.
    """
    # ⚠️ Danh sách phải có ≥ 3 dòng. Min–max trên đúng HAI phần tử luôn cho ra
    # {0; 1} dù hai giá trị sát nhau cỡ nào, nên RRF bị thổi thành chênh lệch
    # tối đa và không tín hiệu nào lật được nó. Thực tế tầng này chạy trên 50
    # dòng nên không gặp; nhưng test dựng 2 dòng sẽ đo nhầm thứ khác.
    goc = [
        _dong("A", 0.30, {"vector": 1}, {"vector": 0.30}),
        _dong("B", 0.28, {"vector": 3, "vector_siglip2": 2, "ocr": 5},
              {"vector": 0.29, "vector_siglip2": 0.33}),
        _dong("C", 0.10, {"ocr": 40}),
    ]
    sau = rerank(goc, enabled=True)
    assert [r["keyframe_id"] for r in sau] == ["B", "A", "C"]
    # Sắp lại theo `score` phải giữ nguyên thứ tự — đó là điều allocate() sẽ làm.
    assert [r["keyframe_id"] for r in sorted(sau, key=lambda r: -r["score"])] == ["B", "A", "C"]
    assert sau[0]["rrf_score"] == 0.28   # điểm RRF gốc vẫn truy được (bất biến 7)


def test_nhom_da_rerank_luon_nam_tren_phan_duoi():
    """Hai nhóm ở hai thang điểm — không nâng nền thì dòng top-50 bị đá xuống.

    Dòng "X" nằm trong top-N nhưng yếu nhất nên được chấm 0,0; dòng đuôi vẫn
    mang điểm RRF gốc 0,05. Thiếu bước nâng nền thì X tụt xuống dưới đuôi —
    mất một ứng viên khỏi vùng nộp mà không có cảnh báo nào.
    """
    dau = [_dong("A", 0.30, {"vector": 1, "ocr": 2}), _dong("X", 0.10, {"ocr": 9})]
    duoi = [_dong("Z", 0.05, {"ocr": 60})]
    sau = rerank(dau + duoi, top_n=2, enabled=True)
    assert [r["keyframe_id"] for r in sau] == ["A", "X", "Z"]
    assert sau[1]["score"] > sau[2]["score"]


def test_thieu_cosine_khong_bi_phat():
    """Dòng chỉ do OCR/ASR đề cử không có cosine — phải nhận 0, không phải âm."""
    goc = [
        _dong("A", 0.30, {"vector": 1}, {"vector": 0.30}),
        _dong("B", 0.30, {"ocr": 1}),          # không có cosine
    ]
    sau = rerank(goc, enabled=True)
    assert all(r["rerank"]["cosine"] >= 0 for r in sau)
    assert sau[0]["keyframe_id"] == "A"        # A hơn nhờ có cosine, không phải B bị trừ


def test_khong_co_nhanh_vector_thu_hai_thi_tat_trong_so_dong_y():
    """Tín hiệu vắng mặt thì tắt hẳn trọng số, không cộng 0 cho mọi dòng."""
    goc = [_dong("A", 0.3, {"vector": 1}), _dong("B", 0.2, {"vector": 2})]
    sau = rerank(goc, enabled=True)
    assert all(r["rerank"]["w_vector_agree"] == 0.0 for r in sau)


def test_danh_sach_phang_thi_khong_thuong_ai():
    """Mọi dòng giống hệt nhau → không có thông tin → giữ nguyên thứ tự."""
    goc = [_dong(k, 0.2, {"vector": 1}) for k in "ABC"]
    assert [r["keyframe_id"] for r in rerank(goc, enabled=True)] == ["A", "B", "C"]
