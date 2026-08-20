# tests/test_audit_batch_manifest.py — manifest URL không được bị hiểu là data.

from __future__ import annotations

import csv

import pytest

from scripts.audit_batch_manifest import audit_manifest, load_manifest


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
