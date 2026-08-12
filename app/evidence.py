# app/evidence.py — D2.1: gom mọi bằng chứng của MỘT keyframe
#
# Trả lời câu "frame này thật sự chứa gì" — thứ quyết định khi chấm nhãn đúng/sai,
# và cũng là thứ giải thích được "vì sao frame này lên hạng cao mà nhìn chẳng liên quan".
#
# ⚠️ ===== HAI KIỂU TÊN KEYFRAME — đọc trước khi sửa file này =====
# Trong data/derived/ có HAI cách đặt tên keyframe, KHÔNG thay thế nhau được:
#
#   kiểu BTC      "L21_V001#k0001"     = keyframe thứ 1 trong thư mục BTC
#                 → frame_map · ocr · MILVUS (nên `search()` luôn trả kiểu này)
#
#   kiểu tự trích "L21_V001_0000090"   = keyframe tự cắt 1fps, hậu tố LÀ frame_idx
#                 → keyframes · docs_bm25
#
# Đo trên dữ liệu thật:
#   clip_kf_id (BTC)      có trong ocr       : 224.284 / 371.702
#   kf_id (tự trích)      có trong docs_bm25 : 371.702 / 371.702
#
# Nối thẳng keyframe_id của search vào docs_bm25 → RỖNG TRẮNG. Không crash, không
# cảnh báo, chỉ là panel "vì sao frame này lên hạng" lúc nào cũng trống. Đúng loại
# lỗi im lặng cả dự án đang phòng.
#
# `clip_kf_map.parquet` là ĐIỂM NỐI DUY NHẤT giữa hai hệ (có cả hai cột). Mọi phép
# tra chéo phải đi qua `_cau_noi()` bên dưới.
#
# ===== Vì sao đọc parquet thẳng, không qua backend/indexing =====
# Đây là công cụ dev, KHÔNG nằm trên đường nộp bài. Nó chỉ HIỂN THỊ con số chứ không
# nộp, nên không tạo ra rủi ro "hai nguồn sự thật" cho bài nộp. Ngược lại, việc nó
# độc lập là có chủ ý: soi được dữ liệu ngay cả khi tầng indexing đang hỏng.

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from data.config.debug_ui import ASR_PAD_S, KEYFRAMES_DIR

DERIVED = Path(__file__).resolve().parents[1] / "data" / "derived"

# "L21_V001_0000090" — hậu tố 6+ chữ số là frame_idx của keyframe tự trích
_KIEU_TU_TRICH = re.compile(r"^(?P<video>[A-Za-z0-9]+_V\d+)_(?P<frame>\d{6,})$")
# "L21_V001#k0001" — hậu tố sau #k là số thứ tự file trong thư mục BTC
_KIEU_BTC = re.compile(r"^(?P<video>[A-Za-z0-9]+_V\d+)#k(?P<ordinal>\d+)$")


@dataclass
class BangChung:
    """Mọi thứ biết được về một keyframe. Trường nào không có thì rỗng, không raise."""

    kf_id_btc: str | None
    kf_id_tu_trich: str | None
    video_id: str
    frame_idx: int | None = None
    shot_id: str | None = None
    shot_bien: tuple[int, int] | None = None
    n_frames_video: int | None = None
    timestamp_s: float | None = None
    ocr: list[dict] = field(default_factory=list)
    asr: list[dict] = field(default_factory=list)
    doc_text: str | None = None
    anh: Path | None = None
    canh_bao: list[str] = field(default_factory=list)


# ------------------------------------------------------------------ nạp bảng

# Sự cố lược đồ đã gặp: tên bảng → mô tả. `bang_chung()` đẩy hết lên UI.
# Vì sao cần biến này: in ra console là vô dụng — người dùng UI đang nhìn trình duyệt,
# không nhìn terminal. Data Factory đã đổi tên cột một lần (07/08), sẽ còn đổi nữa.
_LOI_LUOC_DO: dict[str, str] = {}


def _doc(ten: str, cot: list[str], video_id: str | None = None):
    """Đọc một bảng derived, LỌC SẴN theo video nếu có.

    Vào: tên file (không đuôi) · cột cần · video_id.
    Ra: DataFrame. Thiếu file / thiếu cột → rỗng đúng cột, KHÔNG raise.
    Bất biến: thiếu CỘT thì ghi vào `_LOI_LUOC_DO` kèm tên cột thiếu và danh sách cột
    đang có — để UI nói được "Data Factory đổi lược đồ" chứ không đoán mò thành
    "không có dữ liệu".

    Vì sao lọc bằng `filters` chứ không nạp hết rồi cắt: `docs_bm25` 69.7 MB và `ocr`
    44.6 MB. Đo thật cho 1 video: 512 ms và 89 ms — nạp hết là ăn cả GB RAM cho thứ
    chỉ dùng vài dòng. Máy 16 GB còn phải chạy Docker.

    Thiếu file trả rỗng thay vì gãy: UI phải mở được cả khi Data Factory chưa giao
    đủ bảng — mất một panel còn hơn không mở được cái nào. Nhưng KHÔNG được im lặng:
    im lặng thì panel trống bị đọc nhầm thành "frame này không có OCR", rồi người ta
    chấm nhãn dựa trên một kết luận sai.
    """
    import pandas as pd
    import pyarrow.parquet as pq

    p = DERIVED / f"{ten}.parquet"
    if not p.exists():
        _LOI_LUOC_DO[ten] = f"chưa có {p.name} — chờ Data Factory giao"
        return pd.DataFrame(columns=cot)

    # Đọc lược đồ trước rồi mới đọc dữ liệu: `read_schema()` chỉ chạm phần đầu file
    # nên gần như miễn phí, mà báo lỗi thì rõ hơn hẳn thông báo của pyarrow.
    # Cùng cách làm với `_doc_cot()` của D0.2 — đó là hàm đã cứu đúng sự cố này.
    try:
        dang_co = list(pq.read_schema(p).names)
    except Exception as e:
        _LOI_LUOC_DO[ten] = f"{p.name} hỏng, không đọc nổi lược đồ: {e}"
        return pd.DataFrame(columns=cot)

    thieu = [c for c in cot if c not in dang_co]
    if thieu:
        _LOI_LUOC_DO[ten] = (
            f"{p.name} thiếu cột {thieu} (đang có: {dang_co}). "
            "Nhiều khả năng Data Factory vừa đổi lược đồ — sửa tên cột trong app/evidence.py."
        )
        return pd.DataFrame(columns=cot)

    loc = [("video_id", "==", video_id)] if video_id else None
    try:
        _LOI_LUOC_DO.pop(ten, None)
        return pd.read_parquet(p, columns=cot, filters=loc)
    except Exception as e:
        _LOI_LUOC_DO[ten] = f"không đọc được {p.name}: {e}"
        return pd.DataFrame(columns=cot)


@lru_cache(maxsize=8)
def _cau_noi(video_id: str) -> tuple[dict[str, str], dict[str, str], dict[str, float]]:
    """Bảng dịch giữa HAI hệ tên keyframe, cho một video.

    Ra: (btc→tự_trích, tự_trích→btc, btc→frame_drift).
    Nguồn: `clip_kf_map.parquet` — bảng DUY NHẤT có cả hai cột.

    `frame_drift` = khoảng lệch frame giữa keyframe BTC và keyframe tự trích của
    cùng một chỗ (đo toàn kho: median 11, p95 21, max 25 — cỡ nửa giây). Giữ lại để
    panel chẩn đoán nói được "anh đang nhìn frame nào" khi soi một câu trượt.

    ⚠️ Ánh xạ BTC → tự trích là NHIỀU-VỀ-MỘT. Keyframe tự trích dày hơn (1 fps) nên
    nhiều cái cùng trỏ về một keyframe BTC: 75.124/166.661 keyframe BTC bị trùng,
    nhiều nhất 6 cái. Phải lấy cái có `frame_drift` NHỎ NHẤT — tức gần nhất về thời
    gian. Lấy bừa (dòng cuối thắng) thì bằng chứng hiển thị có thể lệch tới 22 frame
    so với ảnh người ta đang nhìn, mà không có dấu hiệu gì.
    """
    df = _doc("clip_kf_map", ["kf_id", "clip_kf_id", "frame_drift"], video_id)
    btc2own: dict[str, str] = {}
    own2btc: dict[str, str] = {}
    drift: dict[str, float] = {}
    for r in df.itertuples(index=False):
        if not (isinstance(r.clip_kf_id, str) and isinstance(r.kf_id, str)):
            continue
        # NaN != NaN → ô rỗng coi như lệch vô hạn, luôn thua một dòng có số thật
        d = float(r.frame_drift) if r.frame_drift == r.frame_drift else float("inf")
        own2btc[r.kf_id] = r.clip_kf_id
        if r.clip_kf_id not in btc2own or d < drift[r.clip_kf_id]:
            btc2own[r.clip_kf_id] = r.kf_id
            drift[r.clip_kf_id] = d
    return btc2own, own2btc, drift


@lru_cache(maxsize=8)
def _frame_map_video(video_id: str) -> dict[str, int]:
    """kf_id kiểu BTC → frame_idx thật, cho một video.

    Đọc thẳng cột `frame_idx` của `frame_map.parquet` — chính là cột đã bù offset mà
    `backend/indexing/frame_map.py` cũng đọc, nên KHÔNG phải nguồn sự thật thứ hai:
    cùng một file, cùng một cột. Đọc thẳng để UI soi được dữ liệu ngay cả khi module
    kia đang hỏng.
    """
    df = _doc("frame_map", ["kf_id", "frame_idx"], video_id)
    return {r.kf_id: int(r.frame_idx) for r in df.itertuples(index=False)}


@lru_cache(maxsize=8)
def _shots_video(video_id: str) -> dict[str, tuple[int, int]]:
    df = _doc("shots", ["shot_id", "start_frame", "end_frame"], video_id)
    return {r.shot_id: (int(r.start_frame), int(r.end_frame)) for r in df.itertuples(index=False)}


@lru_cache(maxsize=8)
def _video_meta(video_id: str) -> tuple[int | None, float | None]:
    """(n_frames, fps) của một video. fps ở dạng thập phân, chỉ để quy ra giây."""
    df = _doc("video_info", ["video_id", "nb_frames_decoded", "fps_num", "fps_den"], video_id)
    if df.empty:
        return None, None
    r = df.iloc[0]
    fps = float(r.fps_num) / float(r.fps_den) if r.fps_den else None
    return int(r.nb_frames_decoded), fps


@lru_cache(maxsize=8)
def _ocr_video(video_id: str):
    return _doc("ocr", ["kf_id", "frame_idx", "text_raw", "text_clean", "n_boxes", "avg_conf"],
                video_id)


@lru_cache(maxsize=8)
def _asr_video(video_id: str):
    return _doc("asr", ["seg_id", "start_s", "end_s", "start_frame", "end_frame", "text_vi"],
                video_id)


@lru_cache(maxsize=8)
def _docs_video(video_id: str):
    return _doc("docs_bm25", ["kf_id", "frame_idx", "shot_id", "doc_text"], video_id)


@lru_cache(maxsize=8)
def _keyframes_video(video_id: str):
    return _doc("keyframes", ["kf_id", "frame_idx", "shot_id", "path"], video_id)


# --------------------------------------------------------------- chuẩn hoá id

def tach_id(kf_id: str) -> tuple[str, str | None, str | None]:
    """Một keyframe_id bất kỳ → (video_id, id kiểu BTC, id kiểu tự trích).

    Vào: id thuộc MỘT trong hai hệ. Ra: cả hai dạng nếu dịch được, None nếu không.
    Bất biến: KHÔNG tự bịa ra dạng còn lại bằng cách ghép chuỗi — phải tra
    `clip_kf_map`. Ghép chuỗi là đúng kiểu suy diễn mà W0.2 đã cấm.

    Nhận cả hai hệ vì `search()` trả kiểu BTC, còn `docs_bm25`/`keyframes` dùng kiểu
    tự trích — người dùng UI có thể dán vào id lấy từ chỗ nào cũng được.

    Đầu vào không phải chuỗi (ô rỗng của parquet ra `NAType`, UI dán nhầm `None`)
    → trả về rỗng chứ không ném `TypeError` từ tận trong regex.
    """
    if not isinstance(kf_id, str) or not kf_id:
        return "", None, None

    m = _KIEU_BTC.match(kf_id)
    if m:
        video = m.group("video")
        return video, kf_id, _cau_noi(video)[0].get(kf_id)

    m = _KIEU_TU_TRICH.match(kf_id)
    if m:
        video = m.group("video")
        return video, _cau_noi(video)[1].get(kf_id), kf_id

    # Không khớp hệ nào → vẫn cố lấy video_id để panel không trống trơn
    video = kf_id.split("#")[0].rsplit("_", 1)[0] if ("#" in kf_id or "_" in kf_id) else kf_id
    return video, None, None


def _duong_dan_anh(video_id: str, kf_btc: str | None, kf_own: str | None) -> Path | None:
    """Tìm file ảnh của keyframe, ưu tiên bộ BTC vì search trả id kiểu BTC.

    Chưa tải ảnh về → trả None, UI vẽ thẻ xám. Không raise: thiếu ảnh làm UI kém vui
    chứ không làm sai một con số nào.
    """
    if kf_btc:
        m = _KIEU_BTC.match(kf_btc)
        if m:
            stt = int(m.group("ordinal"))
            # BTC đánh số file từ 0, còn btc_ordinal trong frame_map đếm từ 1
            for ten in (f"{stt - 1:04d}.jpg", f"{stt:04d}.jpg"):
                p = KEYFRAMES_DIR / video_id / ten
                if p.exists():
                    return p
    if kf_own:
        df = _keyframes_video(video_id)
        hang = df[df.kf_id == kf_own]
        if not hang.empty:
            p = DERIVED / str(hang.iloc[0].path)
            if p.exists():
                return p
    return None


# -------------------------------------------------------------------- API chính

def bang_chung(kf_id: str) -> BangChung:
    """Gom mọi bằng chứng của một keyframe.

    Vào: keyframe_id thuộc hệ nào cũng được. Ra: `BangChung`.
    Bất biến: KHÔNG BAO GIỜ raise vì thiếu dữ liệu — mọi thứ thiếu thành trường rỗng
    kèm một dòng trong `canh_bao`. UI phải mở được cả khi nửa kho dữ liệu chưa có.

    Vì sao gom hết vào một hàm thay vì để UI tự tra từng bảng: thứ tự tra và các phép
    dịch id là chỗ dễ sai nhất (mục HAI KIỂU TÊN ở đầu file). Gói lại một chỗ thì chỉ
    phải làm đúng một lần, và test được mà không cần dựng Streamlit.
    """
    video_id, kf_btc, kf_own = tach_id(kf_id)
    bc = BangChung(kf_id_btc=kf_btc, kf_id_tu_trich=kf_own, video_id=video_id)

    if kf_btc is None and kf_own is None:
        bc.canh_bao.append(f"'{kf_id}' không khớp hệ tên nào (BTC '#k' hay tự trích '_')")

    n_frames, fps = _video_meta(video_id)
    bc.n_frames_video = n_frames
    if n_frames is None:
        bc.canh_bao.append(f"video '{video_id}' không có trong video_info.parquet")

    # --- frame_idx: ưu tiên frame_map (thứ BTC chấm), sau đó tới hậu tố id tự trích
    if kf_btc:
        bc.frame_idx = _frame_map_video(video_id).get(kf_btc)
    if bc.frame_idx is None and kf_own:
        m = _KIEU_TU_TRICH.match(kf_own)
        if m:
            bc.frame_idx = int(m.group("frame"))
    if bc.frame_idx is None:
        bc.canh_bao.append("không tra được frame_idx — con số BTC chấm đang thiếu")
    elif fps:
        bc.timestamp_s = round(bc.frame_idx / fps, 2)

    # --- shot + biên shot
    if kf_own is not None:
        df = _docs_video(video_id)
        hang = df[df.kf_id == kf_own]
        if not hang.empty:
            bc.shot_id = str(hang.iloc[0].shot_id)
            bc.doc_text = str(hang.iloc[0].doc_text)
    if bc.shot_id:
        bc.shot_bien = _shots_video(video_id).get(bc.shot_id)
    if bc.doc_text is None:
        bc.canh_bao.append(
            "không có doc_text — BM25 không nhìn thấy gì ở frame này, "
            "hoặc cầu nối clip_kf_map thiếu dòng"
        )

    # --- OCR: khớp theo id kiểu BTC (ocr.parquet dùng hệ BTC)
    if kf_btc:
        df = _ocr_video(video_id)
        for r in df[df.kf_id == kf_btc].itertuples(index=False):
            bc.ocr.append({
                "text_raw": r.text_raw, "text_clean": r.text_clean,
                "n_boxes": r.n_boxes, "avg_conf": r.avg_conf,
            })

    # --- ASR: theo THỜI GIAN, không theo id. Đoạn nói phủ frame này ± ASR_PAD_S.
    if bc.frame_idx is not None and fps:
        pad = ASR_PAD_S * fps
        for r in _asr_video(video_id).itertuples(index=False):
            trong = r.start_frame <= bc.frame_idx <= r.end_frame
            gan = r.start_frame - pad <= bc.frame_idx <= r.end_frame + pad
            if gan:
                bc.asr.append({
                    "seg_id": r.seg_id, "start_s": r.start_s, "end_s": r.end_s,
                    "text_vi": r.text_vi,
                    # phân biệt "lời nói NGAY TẠI frame" với "lời nói gần đó":
                    # cửa sổ ±3s là phép nới có chủ ý, không phải bằng chứng trực tiếp
                    "truc_tiep": bool(trong),
                })

    bc.anh = _duong_dan_anh(video_id, kf_btc, kf_own)

    # Sự cố lược đồ chèn lên ĐẦU danh sách: nếu một bảng không đọc được thì mọi cảnh
    # báo phía sau ("không có doc_text"…) đều là chẩn đoán sai ăn theo nó. Gom ở cuối
    # hàm vì lúc này mới biết bảng nào thật sự đã bị đụng tới.
    for ten, loi in _LOI_LUOC_DO.items():
        bc.canh_bao.insert(0, f"[{ten}] {loi}")
    return bc


def keyframe_cung_shot(video_id: str, shot_id: str) -> list[dict]:
    """Mọi keyframe cùng một shot, theo thứ tự thời gian.

    Dùng cho dải ngữ cảnh: nhìn frame trước/sau mới phán được "shot đúng mà frame lệch".
    """
    df = _docs_video(video_id)
    hang = df[df.shot_id == shot_id].sort_values("frame_idx")
    _, own2btc, _ = _cau_noi(video_id)
    return [
        {"kf_id": r.kf_id, "kf_id_btc": own2btc.get(r.kf_id), "frame_idx": int(r.frame_idx)}
        for r in hang.itertuples(index=False)
    ]


def xoa_cache() -> None:
    """Quên hết bảng đã nạp. Dùng khi Data Factory giao bản dữ liệu mới giữa phiên."""
    for f in (_cau_noi, _frame_map_video, _shots_video, _video_meta,
              _ocr_video, _asr_video, _docs_video, _keyframes_video):
        f.cache_clear()
