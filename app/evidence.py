# app/evidence.py — gom mọi bằng chứng của MỘT keyframe.
#
# ⚠️ HAI KIỂU TÊN KEYFRAME — đọc trước khi sửa file này:
#   kiểu BTC       "L21_V001#k0001"    → frame_map · ocr · Milvus (search trả kiểu này)
#   kiểu tự trích  "L21_V001_0000090"  → keyframes · docs_bm25 (hậu tố LÀ frame_idx)
#
# Hai hệ không thay nhau được. Nối thẳng keyframe_id của search vào docs_bm25 thì ra
# rỗng trắng: không crash, không cảnh báo, panel lúc nào cũng trống. clip_kf_map.parquet
# là điểm nối duy nhất; mọi phép tra chéo phải đi qua `_id_bridge()`. Số đo độ phủ:
# reports/D21_TECHNICAL_REPORT.md §3.
#
# Đọc parquet thẳng thay vì qua backend/indexing là có chủ ý: đây là công cụ dev,
# không nộp bài, nên phải soi được dữ liệu ngay cả khi tầng indexing đang hỏng.

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from backend.common.frame_assets import clear_frame_asset_cache, resolve_frame_path
from data.config.debug_ui import ASR_PAD_S, KEYFRAMES_DIR

DERIVED = Path(__file__).resolve().parents[1] / "data" / "derived"

_OWN_ID = re.compile(r"^(?P<video>[A-Za-z0-9]+_V\d+)_(?P<frame>\d{6,})$")
_BTC_ID = re.compile(r"^(?P<video>[A-Za-z0-9]+_V\d+)#k(?P<ordinal>\d+)$")


@dataclass
class Evidence:
    """Mọi thứ biết được về một keyframe. Trường nào không có thì rỗng, không raise."""

    kf_id_btc: str | None
    kf_id_own: str | None
    video_id: str
    frame_idx: int | None = None
    shot_id: str | None = None
    shot_bounds: tuple[int, int] | None = None
    n_frames: int | None = None
    timestamp_s: float | None = None
    ocr: list[dict] = field(default_factory=list)
    asr: list[dict] = field(default_factory=list)
    doc_text: str | None = None
    image: Path | None = None
    warnings: list[str] = field(default_factory=list)


# ------------------------------------------------------------------ nạp bảng

# Sự cố lược đồ đã gặp: tên bảng → mô tả. `evidence_of()` đẩy hết lên UI.
# In ra console là vô dụng: người dùng UI đang nhìn trình duyệt, không nhìn terminal.
_SCHEMA_ERRORS: dict[str, str] = {}


def _read_table(name: str, columns: list[str], video_id: str | None = None):
    """Đọc một bảng derived, LỌC SẴN theo video nếu có.

    Ra: DataFrame. Thiếu file / thiếu cột → rỗng đúng cột, KHÔNG raise, nhưng ghi vào
    `_SCHEMA_ERRORS` kèm danh sách cột đang có — để UI nói được "Data Factory đổi lược
    đồ" chứ không đoán mò thành "không có dữ liệu".

    Lọc bằng `filters` chứ không nạp hết rồi cắt: nạp hết docs_bm25 là ăn cả GB RAM
    cho thứ chỉ dùng vài dòng. Thiếu file trả rỗng vì UI phải mở được cả khi Data
    Factory chưa giao đủ bảng — nhưng không được im lặng, im lặng thì panel trống bị
    đọc thành "frame này không có OCR" rồi người ta chấm nhãn theo đó.
    """
    import pandas as pd
    import pyarrow.parquet as pq

    path = DERIVED / f"{name}.parquet"
    if not path.exists():
        _SCHEMA_ERRORS[name] = f"chưa có {path.name} — chờ Data Factory giao"
        return pd.DataFrame(columns=columns)

    # Đọc lược đồ trước rồi mới đọc dữ liệu: read_schema() chỉ chạm phần đầu file nên
    # gần như miễn phí, mà báo lỗi rõ hơn hẳn thông báo của pyarrow.
    try:
        available = list(pq.read_schema(path).names)
    except Exception as e:
        _SCHEMA_ERRORS[name] = f"{path.name} hỏng, không đọc nổi lược đồ: {e}"
        return pd.DataFrame(columns=columns)

    missing = [c for c in columns if c not in available]
    if missing:
        _SCHEMA_ERRORS[name] = (
            f"{path.name} thiếu cột {missing} (đang có: {available}). "
            "Nhiều khả năng Data Factory vừa đổi lược đồ — sửa tên cột trong app/evidence.py."
        )
        return pd.DataFrame(columns=columns)

    where = [("video_id", "==", video_id)] if video_id else None
    try:
        _SCHEMA_ERRORS.pop(name, None)
        return pd.read_parquet(path, columns=columns, filters=where)
    except Exception as e:
        _SCHEMA_ERRORS[name] = f"không đọc được {path.name}: {e}"
        return pd.DataFrame(columns=columns)


@lru_cache(maxsize=8)
def _id_bridge(video_id: str) -> tuple[dict[str, str], dict[str, str], dict[str, float]]:
    """Bảng dịch giữa HAI hệ tên keyframe, cho một video.

    Ra: (btc→own, own→btc, btc→frame_drift). Nguồn: clip_kf_map.parquet, bảng duy
    nhất có cả hai cột. `frame_drift` = khoảng lệch frame giữa hai hệ ở cùng một chỗ
    (toàn kho: median 11, p95 21, max 25).

    ⚠️ Chiều btc→own là NHIỀU-VỀ-MỘT: 75.124/166.661 keyframe BTC có hơn một ứng viên,
    nhiều nhất 6. Phải lấy cái `frame_drift` NHỎ NHẤT. Lấy bừa (dòng cuối thắng) thì
    bằng chứng lệch tới 22 frame so với ảnh đang nhìn, không dấu hiệu gì.

    CẢ HAI chiều đều lấy drift nhỏ nhất. Chiều own→btc hiện là 1-1 trên dữ liệu đang
    có, nhưng đó là tính chất của bảng chứ không phải ràng buộc ai bảo đảm — để dòng
    cuối thắng ở một chiều là gài sẵn đúng cái bẫy vừa gỡ ở chiều kia, cho lần Data
    Factory dựng lại `clip_kf_map`.
    """
    df = _read_table("clip_kf_map", ["kf_id", "clip_kf_id", "frame_drift"], video_id)
    btc2own: dict[str, str] = {}
    own2btc: dict[str, str] = {}
    drift: dict[str, float] = {}
    drift_own: dict[str, float] = {}
    for r in df.itertuples(index=False):
        if not (isinstance(r.clip_kf_id, str) and isinstance(r.kf_id, str)):
            continue
        # NaN != NaN → ô rỗng coi như lệch vô hạn, luôn thua một dòng có số thật
        d = float(r.frame_drift) if r.frame_drift == r.frame_drift else float("inf")
        if r.kf_id not in own2btc or d < drift_own[r.kf_id]:
            own2btc[r.kf_id] = r.clip_kf_id
            drift_own[r.kf_id] = d
        if r.clip_kf_id not in btc2own or d < drift[r.clip_kf_id]:
            btc2own[r.clip_kf_id] = r.kf_id
            drift[r.clip_kf_id] = d
    return btc2own, own2btc, drift


@lru_cache(maxsize=8)
def _frame_map_of(video_id: str) -> dict[str, int]:
    """kf_id kiểu BTC → frame_idx thật.

    Đọc thẳng cột `frame_idx` của frame_map.parquet — cùng file cùng cột mà
    backend/indexing/frame_map.py đọc, nên không phải nguồn sự thật thứ hai. Đọc thẳng
    để UI soi được dữ liệu ngay cả khi module kia đang hỏng.
    """
    df = _read_table("frame_map", ["kf_id", "frame_idx"], video_id)
    return {r.kf_id: int(r.frame_idx) for r in df.itertuples(index=False)}


@lru_cache(maxsize=8)
def _shots_of(video_id: str) -> dict[str, tuple[int, int]]:
    df = _read_table("shots", ["shot_id", "start_frame", "end_frame"], video_id)
    return {r.shot_id: (int(r.start_frame), int(r.end_frame)) for r in df.itertuples(index=False)}


@lru_cache(maxsize=8)
def _video_meta(video_id: str) -> tuple[int | None, float | None]:
    """(n_frames, fps) của một video. fps dạng thập phân, chỉ để quy ra giây."""
    df = _read_table("video_info", ["video_id", "nb_frames_decoded", "fps_num", "fps_den"],
                     video_id)
    if df.empty:
        return None, None
    r = df.iloc[0]
    fps = float(r.fps_num) / float(r.fps_den) if r.fps_den else None
    return int(r.nb_frames_decoded), fps


@lru_cache(maxsize=8)
def _ocr_of(video_id: str):
    return _read_table("ocr", ["kf_id", "frame_idx", "text_raw", "text_clean",
                               "n_boxes", "avg_conf"], video_id)


@lru_cache(maxsize=8)
def _asr_of(video_id: str):
    return _read_table("asr", ["seg_id", "start_s", "end_s", "start_frame",
                               "end_frame", "text_vi"], video_id)


@lru_cache(maxsize=8)
def _docs_of(video_id: str):
    return _read_table("docs_bm25", ["kf_id", "frame_idx", "shot_id", "doc_text"], video_id)


@lru_cache(maxsize=8)
def _keyframes_of(video_id: str):
    return _read_table("keyframes", ["kf_id", "frame_idx", "shot_id", "path"], video_id)


# --------------------------------------------------------------- chuẩn hoá id

def split_id(kf_id: str) -> tuple[str, str | None, str | None]:
    """Một keyframe_id bất kỳ → (video_id, id kiểu BTC, id kiểu tự trích).

    Bất biến: KHÔNG bịa dạng còn lại bằng cách ghép chuỗi — phải tra clip_kf_map.
    `L21_V001#k0004` ứng với `L21_V001_0000375`; hậu tố 0000375 là frame_idx, không
    có quan hệ số học nào với 0004.

    Đầu vào không phải chuỗi (ô rỗng parquet ra NAType) → trả rỗng chứ không ném
    TypeError từ tận trong regex.
    """
    if not isinstance(kf_id, str) or not kf_id:
        return "", None, None

    m = _BTC_ID.match(kf_id)
    if m:
        video = m.group("video")
        return video, kf_id, _id_bridge(video)[0].get(kf_id)

    m = _OWN_ID.match(kf_id)
    if m:
        video = m.group("video")
        return video, _id_bridge(video)[1].get(kf_id), kf_id

    # Không khớp hệ nào → vẫn cố lấy video_id để panel không trống trơn.
    #
    # ⚠️ SỬA 20/08 — hai kiểu id cắt bằng hai phép KHÁC NHAU, không được dồn vào
    # một dòng. Bản cũ luôn `rsplit("_", 1)` sau khi đã `split("#")`, nên id có `#`
    # bị cắt HAI LẦN:
    #     "L21_V001#s0006" → split("#") → "L21_V001" → rsplit("_") → "L21"  ✗
    # `_BTC_ID` chỉ khớp `#k`, nên MỌI `shot_id` (`#s0006`) rơi xuống đây — tức
    # nhánh sinh ra để cứu panel lại trả về một video KHÔNG TỒN TẠI, mọi bảng tra
    # ra rỗng, panel vẫn trống. Không crash, không log: đúng thứ nó định tránh.
    if "#" in kf_id:
        video = kf_id.split("#")[0]        # phần trước `#` đã là video_id
    elif "_" in kf_id:
        video = kf_id.rsplit("_", 1)[0]    # bỏ hậu tố số của kiểu tự trích
    else:
        video = kf_id
    return video, None, None


def _image_path(video_id: str, kf_btc: str | None,
                kf_own: str | None) -> tuple[Path | None, str | None]:
    """Tìm file ảnh của keyframe → (đường dẫn, cảnh báo).

    Quy ước tên file KHÔNG đoán, và cũng không thử lần lượt vài mẫu: đọc thẳng cách
    đánh số của thư mục (`_image_naming`) rồi tính đúng một tên file.

    Bộ ảnh THẬT của BTC đánh số **từ 1**, 3 chữ số: `#k0001` → `001.jpg`. Đây là con
    số đã kiểm bằng pixel trong B0.1 (`get_kf_path()` tra theo đúng `ordinal`), nên nó
    thắng dòng `L01_V001/0000.jpg` trong `docs/contest.md` — tài liệu đó mô tả sai.

    Gặp bộ đánh số từ 0 thì VẪN dùng được (tính `ordinal - 1`) nhưng LUÔN kèm cảnh
    báo: bộ ảnh đang cầm khác bộ B0.1 đã kiểm, mà lệch một keyframe thì người chấm
    ngồi soi nhầm frame suốt buổi và không có dấu hiệu gì.
    """
    frame_idx = None
    if kf_own:
        df = _keyframes_of(video_id)
        row = df[df.kf_id == kf_own]
        if not row.empty:
            frame_idx = int(row.iloc[0].frame_idx)

    resolution = resolve_frame_path(
        video_id,
        frame_idx=frame_idx,
        keyframe_id=kf_btc or kf_own,
        raw_root=KEYFRAMES_DIR,
        # DERIVED là data/derived; resolver hỗ trợ root cũ này mà vẫn dùng đường
        # chuẩn data/derived/keyframes/<video>/f....jpg.
        derived_root=DERIVED,
    )
    if resolution.path is not None:
        return resolution.path, resolution.warning
    return None, resolution.reason


# -------------------------------------------------------------------- API chính

def evidence_of(kf_id: str) -> Evidence:
    """Gom mọi bằng chứng của một keyframe.

    Vào: keyframe_id thuộc hệ nào cũng được. Ra: `Evidence`.
    Bất biến: KHÔNG BAO GIỜ raise vì thiếu dữ liệu — thiếu gì thành trường rỗng kèm
    một dòng `warnings`. UI phải mở được cả khi nửa kho dữ liệu chưa có.

    Gom vào một hàm thay vì để UI tự tra từng bảng vì thứ tự tra và các phép dịch id
    là chỗ dễ sai nhất, và ở đây thì test được mà không cần dựng Streamlit.
    """
    video_id, kf_btc, kf_own = split_id(kf_id)
    ev = Evidence(kf_id_btc=kf_btc, kf_id_own=kf_own, video_id=video_id)

    if kf_btc is None and kf_own is None:
        ev.warnings.append(f"'{kf_id}' không khớp hệ tên nào (BTC '#k' hay tự trích '_')")

    n_frames, fps = _video_meta(video_id)
    ev.n_frames = n_frames
    if n_frames is None:
        ev.warnings.append(f"video '{video_id}' không có trong video_info.parquet")

    # frame_idx: ưu tiên frame_map (con số BTC chấm), sau đó tới hậu tố id tự trích
    if kf_btc:
        ev.frame_idx = _frame_map_of(video_id).get(kf_btc)
    if ev.frame_idx is None and kf_own:
        m = _OWN_ID.match(kf_own)
        if m:
            ev.frame_idx = int(m.group("frame"))
    if ev.frame_idx is None:
        ev.warnings.append("không tra được frame_idx — con số BTC chấm đang thiếu")
    elif fps:
        ev.timestamp_s = round(ev.frame_idx / fps, 2)

    # shot + doc_text: cả hai nằm ở bảng dùng hệ TỰ TRÍCH
    if kf_own is not None:
        df = _docs_of(video_id)
        row = df[df.kf_id == kf_own]
        if not row.empty:
            ev.shot_id = str(row.iloc[0].shot_id)
            ev.doc_text = str(row.iloc[0].doc_text)
    if ev.shot_id:
        ev.shot_bounds = _shots_of(video_id).get(ev.shot_id)
    if ev.doc_text is None:
        ev.warnings.append(
            "không có doc_text — BM25 không nhìn thấy gì ở frame này, "
            "hoặc cầu nối clip_kf_map thiếu dòng"
        )

    # OCR khớp theo id kiểu BTC (ocr.parquet dùng hệ BTC)
    if kf_btc:
        df = _ocr_of(video_id)
        for r in df[df.kf_id == kf_btc].itertuples(index=False):
            ev.ocr.append({
                "text_raw": r.text_raw, "text_clean": r.text_clean,
                "n_boxes": r.n_boxes, "avg_conf": r.avg_conf,
            })

    # ASR theo THỜI GIAN, không theo id: đoạn nói phủ frame này ± ASR_PAD_S
    if ev.frame_idx is not None and fps:
        pad = ASR_PAD_S * fps
        for r in _asr_of(video_id).itertuples(index=False):
            inside = r.start_frame <= ev.frame_idx <= r.end_frame
            near = r.start_frame - pad <= ev.frame_idx <= r.end_frame + pad
            if near:
                ev.asr.append({
                    "seg_id": r.seg_id, "start_s": r.start_s, "end_s": r.end_s,
                    "text_vi": r.text_vi,
                    # Phân biệt "lời nói NGAY TẠI frame" với "gần đó": cửa sổ ±3s là
                    # phép nới có chủ ý, không phải bằng chứng trực tiếp.
                    "direct": bool(inside),
                })

    ev.image, image_warning = _image_path(video_id, kf_btc, kf_own)
    if image_warning:
        ev.warnings.append(image_warning)

    # Sự cố lược đồ đứng ĐẦU danh sách: bảng không đọc được thì mọi cảnh báo phía sau
    # đều là chẩn đoán sai ăn theo nó. Ghép cả khối một lần — insert(0, …) trong vòng
    # lặp sẽ lật ngược thứ tự các bảng.
    ev.warnings[:0] = [f"[{name}] {err}" for name, err in _SCHEMA_ERRORS.items()]
    return ev


def keyframes_in_shot(video_id: str, shot_id: str) -> list[dict]:
    """Mọi keyframe cùng một shot, theo thứ tự thời gian.

    Dùng cho dải ngữ cảnh: nhìn frame trước/sau mới phán được "shot đúng mà frame lệch".
    """
    df = _docs_of(video_id)
    rows = df[df.shot_id == shot_id].sort_values("frame_idx")
    _, own2btc, _ = _id_bridge(video_id)
    return [
        {"kf_id": r.kf_id, "kf_id_btc": own2btc.get(r.kf_id), "frame_idx": int(r.frame_idx)}
        for r in rows.itertuples(index=False)
    ]


def clear_cache() -> None:
    """Quên hết bảng đã nạp. Dùng khi Data Factory giao bản dữ liệu mới giữa phiên."""
    for f in (_id_bridge, _frame_map_of, _shots_of, _video_meta,
              _ocr_of, _asr_of, _docs_of, _keyframes_of):
        f.cache_clear()
    clear_frame_asset_cache()
