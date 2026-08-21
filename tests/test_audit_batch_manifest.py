# tests/test_audit_batch_manifest.py — manifest URL không được bị hiểu là data.

from __future__ import annotations

import csv
import zipfile

import pytest

from scripts.audit_batch_manifest import (
    ROUND1_DEFERRED,
    ROUND1_REQUIRED,
    audit_manifest,
    build_payload,
    load_reusable_hashes,
    load_manifest,
    summarize_report,
)


def _write_manifest(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["", "Filenames", "Download link"])
        writer.writeheader()
        for filename, url in rows:
            writer.writerow({"": "", "Filenames": filename, "Download link": url})


def test_audit_distinguishes_present_and_missing_archive(tmp_path):
    manifest = tmp_path / "batch1.csv"
    _write_manifest(manifest, [
        ("Keyframes_L21.zip", "https://example.test/Keyframes_L21.zip"),
        ("Videos_L21.zip", "https://example.test/Videos_L21.zip"),
    ])
    archives = tmp_path / "downloads"
    archives.mkdir()
    (archives / "Keyframes_L21.zip").write_bytes(b"archive")

    report = audit_manifest(manifest, archives, calculate_hash=True)

    assert [entry.download_status for entry in report] == ["present", "missing"]
    assert report[0].size_bytes == len(b"archive")
    assert len(report[0].sha256 or "") == 64
    assert report[0].category == "keyframes"
    assert report[0].round1_requirement == ROUND1_REQUIRED
    assert report[1].round1_requirement == ROUND1_DEFERRED

    summary = summarize_report(report)
    assert summary["missing"] == 1
    assert summary["required_round1_missing"] == 0
    assert summary["deferred_not_required_round1"] == 1
    assert summary["round1_download_ready"] is True


def test_manifest_rejects_filename_url_mismatch(tmp_path):
    manifest = tmp_path / "bad.csv"
    _write_manifest(manifest, [
        ("Keyframes_L21.zip", "https://example.test/Keyframes_L22.zip"),
    ])
    with pytest.raises(ValueError, match="không khớp"):
        load_manifest(manifest)


def test_extracted_batch_is_not_confused_with_other_part(tmp_path):
    manifest = tmp_path / "batch1.csv"
    _write_manifest(manifest, [
        ("Keyframes_L21.zip", "https://example.test/Keyframes_L21.zip"),
        ("Keyframes_L22.zip", "https://example.test/Keyframes_L22.zip"),
    ])
    archives = tmp_path / "downloads"
    archives.mkdir()
    extracted = tmp_path / "raw" / "keyframes" / "L21_V001"
    extracted.mkdir(parents=True)
    (extracted / "001.jpg").write_bytes(b"image")

    report = audit_manifest(
        manifest,
        archives,
        extracted_root=tmp_path / "raw",
        count_extracted=True,
    )

    assert report[0].extracted_status == "present"
    assert report[0].extracted_files == 1
    assert report[1].extracted_status == "missing"


def test_core_archives_match_real_raw_layouts(tmp_path):
    """Bốn archive lõi phải nhận đúng layout sau giải nén đang dùng thật."""
    rows = [
        ("clip-features-32-aic25-b1.zip", "clip_features"),
        ("map-keyframes-aic25-b1.zip", "frame_maps"),
        ("media-info-aic25-b1.zip", "metadata"),
        ("objects-aic25-b1.zip", "objects"),
    ]
    manifest = tmp_path / "batch1.csv"
    _write_manifest(manifest, [
        (filename, f"https://example.test/{filename}")
        for filename, _ in rows
    ])
    archives = tmp_path / "downloads"
    archives.mkdir()
    raw = tmp_path / "raw"
    files = [
        raw / "clip-features-32" / "L21_V001.npy",
        raw / "metadata" / "map-keyframes" / "L21_V001.csv",
        raw / "metadata" / "media-info" / "L21_V001.json",
        raw / "objects" / "L21_V001" / "001.json",
    ]
    for path in files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"raw")

    report = audit_manifest(
        manifest,
        archives,
        extracted_root=raw,
        count_extracted=True,
    )

    assert [entry.category for entry in report] == [category for _, category in rows]
    assert [entry.extracted_status for entry in report] == ["present"] * 4
    assert [entry.extracted_files for entry in report] == [1, 1, 1, 1]
    assert all(entry.round1_requirement == ROUND1_REQUIRED for entry in report)


def test_missing_required_archive_blocks_round1(tmp_path):
    manifest = tmp_path / "batch1.csv"
    _write_manifest(manifest, [
        (
            "map-keyframes-aic25-b1.zip",
            "https://example.test/map-keyframes-aic25-b1.zip",
        ),
    ])
    archives = tmp_path / "downloads"
    archives.mkdir()

    summary = summarize_report(audit_manifest(manifest, archives))

    assert summary["required_round1_missing"] == 1
    assert summary["round1_download_ready"] is False


def test_split_archive_counts_only_its_own_members(tmp_path):
    """Các part L26 dùng chung raw dir nhưng phải có số đếm độc lập."""
    rows = [
        ("Keyframes_L26_a.zip", [
            "keyframes/L26_V001/001.jpg",
            "keyframes/L26_V001/002.jpg",
        ]),
        ("Keyframes_L26_b.zip", [
            "wrapper/keyframes/L26_V002/001.jpg",
        ]),
    ]
    manifest = tmp_path / "batch1.csv"
    _write_manifest(manifest, [
        (filename, f"https://example.test/{filename}")
        for filename, _ in rows
    ])
    archives = tmp_path / "downloads"
    archives.mkdir()
    for filename, members in rows:
        with zipfile.ZipFile(archives / filename, "w") as handle:
            for member in members:
                handle.writestr(member, b"image")

    raw = tmp_path / "raw"
    for relative in (
        "keyframes/L26_V001/001.jpg",
        "keyframes/L26_V001/002.jpg",
        "keyframes/L26_V002/001.jpg",
    ):
        path = raw / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"image")

    report = audit_manifest(
        manifest,
        archives,
        extracted_root=raw,
        calculate_hash=True,
        count_extracted=True,
    )

    assert [entry.archive_member_files for entry in report] == [2, 1]
    assert [entry.extracted_files for entry in report] == [2, 1]
    assert [entry.extracted_status for entry in report] == ["present", "present"]
    assert summarize_report(report)["round1_operational_audit_complete"] is True

    payload = build_payload(
        manifest,
        archives,
        raw,
        report,
        calculate_hash=True,
        count_extracted=True,
    )
    assert payload["generated_at_utc"]
    assert len(str(payload["manifest_sha256"])) == 64
    assert payload["invocation"]["manifest"] == str(manifest.resolve())
    assert payload["invocation"]["archives_dir"] == str(archives.resolve())
    assert payload["invocation"]["extracted_root"] == str(raw.resolve())
    assert payload["invocation"]["calculate_hash"] is True
    assert payload["invocation"]["count_extracted"] is True
    assert payload["invocation"]["reuse_hashes_from"] is None
    assert payload["invocation"]["reuse_hashes_source_sha256"] is None
    raw_keyframes = payload["raw_snapshot"]["categories"]["keyframes"]
    assert raw_keyframes["files"] == 3
    assert raw_keyframes["video_directories"] == 2


def test_reusable_hash_requires_same_archive_size(tmp_path):
    manifest = tmp_path / "batch1.csv"
    _write_manifest(manifest, [
        ("Keyframes_L21.zip", "https://example.test/Keyframes_L21.zip"),
    ])
    archives = tmp_path / "downloads"
    archives.mkdir()
    archive = archives / "Keyframes_L21.zip"
    archive.write_bytes(b"new-size")
    old = tmp_path / "old.json"
    old.write_text(
        '{"entries":[{"filename":"Keyframes_L21.zip",'
        '"size_bytes":3,"sha256":"' + "a" * 64 + '"}]}',
        encoding="utf-8",
    )

    report = audit_manifest(
        manifest,
        archives,
        reusable_hashes=load_reusable_hashes(old),
    )

    assert report[0].sha256 is None
    assert summarize_report(report)["required_round1_hashes_complete"] is False
