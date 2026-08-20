# backend/common/frame_assets.py — nguồn duy nhất giải keyframe thành file ảnh.
#
# Ảnh BTC đặt tên bằng ordinal, còn ảnh tự trích đặt tên bằng frame index tuyệt
# đối. Gom vào đây để Q&A và UI không còn hai phép đoán đường dẫn khác nhau.

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from data.config.frame_assets import DERIVED_KEYFRAMES_DIR, RAW_KEYFRAMES_DIR

_BTC_ID = re.compile(r"^(?P<video>[A-Za-z0-9]+_V\d+)#k(?P<ordinal>\d+)$")


@dataclass(frozen=True)
class FramePathResolution:
    """Kết quả tra ảnh, gồm lý do rõ ràng khi không tìm thấy.

    Input của resolver là định danh đã biết; output không bao giờ tự biến hậu tố
    keyframe tự trích thành frame nộp. Invariant: `path` tồn tại nếu khác None.
    """

    path: Path | None
    source: str | None = None       # raw | derived
    reason: str | None = None
    warning: str | None = None


@lru_cache(maxsize=64)
def _raw_video_dir(raw_root: str, video_id: str) -> Path | None:
    """Tìm thư mục video trong hai bố cục archive BTC đang gặp."""
    root = Path(raw_root)
    part = video_id.split("_")[0]
    candidates = [
        root / f"keyframes_{part}" / video_id,
        root / video_id,
    ]
    # L26/L28 được BTC chia archive a/b/c...; nếu giữ nguyên lớp bọc sau giải
    # nén thì parent có thể là keyframes_L26_a. Chỉ glob đúng part, không quét
    # đệ quy toàn kho.
    if root.is_dir():
        candidates.extend(
            parent / video_id
            for parent in root.glob(f"keyframes_{part}*")
            if parent.is_dir()
        )
    return next((path for path in candidates if path.is_dir()), None)


@lru_cache(maxsize=64)
def _raw_naming(video_dir: str) -> tuple[int, int] | None:
    """Đọc quy ước ordinal từ file thật, trả `(base, width)`.

    Không thử `ordinal` rồi `ordinal-1`: cả hai tên thường cùng tồn tại và cách
    thử đó sẽ chọn nhầm ảnh kế bên mà không báo lỗi.
    """
    stems = [
        path.stem
        for path in Path(video_dir).glob("*.jpg")
        if path.stem.isdigit()
    ]
    if not stems:
        return None
    first = min(stems, key=int)
    return (0 if int(first) == 0 else 1), len(first)


@lru_cache(maxsize=1)
def _btc_frame_lookup() -> tuple[dict[str, int], dict[tuple[str, int], str]]:
    """Hai chiều BTC keyframe ↔ frame index, chỉ từ frame_map đã kiểm chứng."""
    from backend.indexing.frame_map import load_frame_map

    by_id: dict[str, int] = {}
    by_frame: dict[tuple[str, int], str] = {}
    for keyframe_id, frame_idx in load_frame_map().items():
        match = _BTC_ID.fullmatch(keyframe_id)
        if not match:
            continue
        frame_idx = int(frame_idx)
        by_id[keyframe_id] = frame_idx
        # Nếu hai ordinal cùng trỏ một frame, giữ ordinal nhỏ nhất để kết quả ổn
        # định; cả hai vẫn là bằng chứng của đúng frame đã map.
        key = (match.group("video"), frame_idx)
        current = by_frame.get(key)
        if current is None or int(match.group("ordinal")) < int(
            _BTC_ID.fullmatch(current).group("ordinal")
        ):
            by_frame[key] = keyframe_id
    return by_id, by_frame


def _derived_candidates(root: Path, video_id: str, frame_idx: int) -> list[Path]:
    """Các bố cục cache derived tương thích, theo frame index tường minh."""
    name = f"f{frame_idx:07d}.jpg"
    candidates = [root / video_id / name]
    # Hỗ trợ caller cũ truyền root=data/derived thay vì .../derived/keyframes.
    candidates.append(root / "keyframes" / video_id / name)
    return list(dict.fromkeys(candidates))


def resolve_frame_path(
    video_id: str,
    frame_idx: int | None = None,
    keyframe_id: str | None = None,
    btc_ordinal: int | None = None,
    *,
    raw_root: Path | None = None,
    derived_root: Path | None = None,
) -> FramePathResolution:
    """Định danh frame/keyframe → ảnh raw BTC hoặc derived đã tồn tại.

    Input: `video_id` và ít nhất một trong frame index tuyệt đối, keyframe BTC
    hoặc ordinal BTC; root có thể override trong test/máy khác. Output:
    `FramePathResolution`. Invariant: raw luôn được ưu tiên; frame index chỉ lấy
    từ tham số hoặc `frame_map`, không bao giờ cắt hậu tố keyframe tự trích.
    """
    raw_root = Path(raw_root) if raw_root is not None else RAW_KEYFRAMES_DIR
    derived_root = (
        Path(derived_root) if derived_root is not None else DERIVED_KEYFRAMES_DIR
    )

    reasons: list[str] = []
    match = _BTC_ID.fullmatch(keyframe_id or "")
    btc_id_for_map: str | None = None
    if match:
        if match.group("video") != video_id:
            return FramePathResolution(
                None,
                reason=(f"keyframe_id thuộc {match.group('video')}, không phải "
                        f"video_id={video_id}"),
            )
        ordinal_from_id = int(match.group("ordinal"))
        if btc_ordinal is not None and int(btc_ordinal) != ordinal_from_id:
            return FramePathResolution(
                None,
                reason=(f"btc_ordinal={btc_ordinal} lệch keyframe_id={keyframe_id}"),
            )
        btc_ordinal = ordinal_from_id
        btc_id_for_map = keyframe_id
        mapped_frame = (
            _btc_frame_lookup()[0].get(keyframe_id)
            if frame_idx is not None else None
        )
        if mapped_frame is not None and int(frame_idx) != mapped_frame:
            return FramePathResolution(
                None,
                reason=(f"frame_idx={frame_idx} lệch frame_map={mapped_frame} cho "
                        f"{keyframe_id}"),
            )
    elif keyframe_id and frame_idx is None and btc_ordinal is None:
        # Keyframe tự trích có thể có hậu tố giống frame, nhưng dùng nó làm frame
        # là đúng lỗi im lặng ở tầng submit. Caller phải truyền frame_idx đã tra.
        reasons.append(
            f"keyframe_id={keyframe_id!r} không phải id BTC; cần frame_idx đã tra, "
            "không suy từ hậu tố"
        )

    video_dir = _raw_video_dir(str(raw_root), video_id)
    if btc_ordinal is None and frame_idx is not None and video_dir is not None:
        try:
            btc_id = _btc_frame_lookup()[1].get((video_id, int(frame_idx)))
        except Exception as exc:
            btc_id = None
            reasons.append(f"không đọc được frame_map để thử raw: {exc}")
        if btc_id:
            btc_ordinal = int(_BTC_ID.fullmatch(btc_id).group("ordinal"))

    # Raw là nguồn ảnh chuẩn. Base và độ rộng được đọc từ chính thư mục để không
    # lệch một keyframe giữa bộ đánh số từ 0 và từ 1.
    if btc_ordinal is not None and video_dir is not None:
        naming = _raw_naming(str(video_dir))
        if naming is not None:
            base, width = naming
            raw_path = video_dir / f"{int(btc_ordinal) - 1 + base:0{width}d}.jpg"
            if raw_path.exists():
                warning = None
                if base == 0:
                    warning = (
                        f"ảnh {raw_path.name} thuộc bộ đánh số từ 0; kiểm lại phiên "
                        "bản archive trước khi gán nhãn"
                    )
                return FramePathResolution(raw_path, "raw", warning=warning)
            reasons.append(
                f"thư mục {video_dir} có ảnh nhưng thiếu {raw_path.name} "
                f"(ordinal {btc_ordinal})"
            )
        else:
            reasons.append(f"thư mục {video_dir} không có file JPG đánh số")
    elif btc_ordinal is not None:
        reasons.append(f"không có thư mục raw cho {video_id} dưới {raw_root}")

    # Raw không có hoặc thiếu đúng ordinal: lúc này mới đọc frame_map để thử cache
    # derived. Nhờ thứ tự này, UI vẫn mở ảnh raw khi môi trường pandas/parquet hỏng.
    if frame_idx is None and btc_id_for_map is not None:
        try:
            frame_idx = _btc_frame_lookup()[0].get(btc_id_for_map)
        except Exception as exc:
            reasons.append(f"không đọc được frame_map để thử derived: {exc}")

    if frame_idx is not None:
        for derived_path in _derived_candidates(derived_root, video_id, int(frame_idx)):
            if derived_path.exists():
                return FramePathResolution(derived_path, "derived")
        reasons.append(
            f"không có derived f{int(frame_idx):07d}.jpg dưới {derived_root}"
        )

    if not reasons:
        reasons.append("cần frame_idx, keyframe_id BTC hoặc btc_ordinal để tra ảnh")
    return FramePathResolution(None, reason="; ".join(reasons))


def clear_frame_asset_cache() -> None:
    """Xóa cache sau khi giải nén thêm ảnh hoặc cập nhật frame_map."""
    _raw_video_dir.cache_clear()
    _raw_naming.cache_clear()
    _btc_frame_lookup.cache_clear()
