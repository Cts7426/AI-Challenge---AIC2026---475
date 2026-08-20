# tests/test_frame_assets.py — bảo vệ ranh giới ordinal ảnh ↔ frame tuyệt đối.

from __future__ import annotations

from backend.common import frame_assets as assets


def setup_function():
    assets.clear_frame_asset_cache()


def test_raw_btc_one_based_is_preferred(tmp_path):
    raw = tmp_path / "raw" / "keyframes_L21" / "L21_V001"
    raw.mkdir(parents=True)
    (raw / "001.jpg").write_bytes(b"one")
    (raw / "002.jpg").write_bytes(b"two")

    result = assets.resolve_frame_path(
        "L21_V001",
        keyframe_id="L21_V001#k0001",
        raw_root=tmp_path / "raw",
        derived_root=tmp_path / "derived",
    )

    assert result.path == raw / "001.jpg"
    assert result.source == "raw"
    assert result.warning is None


def test_raw_btc_zero_based_is_detected_and_warned(tmp_path):
    raw = tmp_path / "raw" / "L21_V001"
    raw.mkdir(parents=True)
    (raw / "0000.jpg").write_bytes(b"zero")
    (raw / "0001.jpg").write_bytes(b"one")

    result = assets.resolve_frame_path(
        "L21_V001",
        keyframe_id="L21_V001#k0001",
        raw_root=tmp_path / "raw",
        derived_root=tmp_path / "derived",
    )

    assert result.path == raw / "0000.jpg"
    assert result.warning and "0000.jpg" in result.warning


def test_split_archive_wrapper_is_supported(tmp_path):
    raw = tmp_path / "raw" / "keyframes_L26_a" / "L26_V001"
    raw.mkdir(parents=True)
    (raw / "001.jpg").write_bytes(b"one")

    result = assets.resolve_frame_path(
        "L26_V001",
        keyframe_id="L26_V001#k0001",
        raw_root=tmp_path / "raw",
        derived_root=tmp_path / "derived",
    )

    assert result.path == raw / "001.jpg"


def test_raw_wins_over_derived(tmp_path):
    raw = tmp_path / "raw" / "L21_V001"
    raw.mkdir(parents=True)
    (raw / "001.jpg").write_bytes(b"raw")
    derived = tmp_path / "derived" / "L21_V001"
    derived.mkdir(parents=True)
    (derived / "f0001234.jpg").write_bytes(b"derived")
    assets._btc_frame_lookup.cache_clear()
    # Cùng keyframe/frame đã xác nhận; test không phụ thuộc parquet thật.
    original = assets._btc_frame_lookup
    assets._btc_frame_lookup = lambda: (
        {"L21_V001#k0001": 1234},
        {("L21_V001", 1234): "L21_V001#k0001"},
    )
    try:
        result = assets.resolve_frame_path(
            "L21_V001",
            frame_idx=1234,
            keyframe_id="L21_V001#k0001",
            raw_root=tmp_path / "raw",
            derived_root=tmp_path / "derived",
        )
    finally:
        assets._btc_frame_lookup = original

    assert result.path == raw / "001.jpg"
    assert result.source == "raw"


def test_derived_uses_explicit_absolute_frame(tmp_path):
    derived = tmp_path / "derived" / "keyframes" / "L21_V001"
    derived.mkdir(parents=True)
    image = derived / "f0001234.jpg"
    image.write_bytes(b"derived")

    result = assets.resolve_frame_path(
        "L21_V001",
        frame_idx=1234,
        raw_root=tmp_path / "missing-raw",
        derived_root=tmp_path / "derived",
    )

    assert result.path == image
    assert result.source == "derived"


def test_own_keyframe_suffix_is_never_inferred(tmp_path):
    derived = tmp_path / "derived" / "L21_V001"
    derived.mkdir(parents=True)
    (derived / "f0001234.jpg").write_bytes(b"tempting")

    result = assets.resolve_frame_path(
        "L21_V001",
        keyframe_id="L21_V001_0001234",
        raw_root=tmp_path / "raw",
        derived_root=tmp_path / "derived",
    )

    assert result.path is None
    assert result.reason and "không suy từ hậu tố" in result.reason


def test_mismatched_video_id_is_rejected(tmp_path):
    result = assets.resolve_frame_path(
        "L21_V002",
        keyframe_id="L21_V001#k0001",
        raw_root=tmp_path,
        derived_root=tmp_path,
    )
    assert result.path is None
    assert result.reason and "không phải video_id" in result.reason
