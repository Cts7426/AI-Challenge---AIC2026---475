"""Fixture tổng hợp trong tmp_path; không xác nhận GT thật hay gọi pipeline/model."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from data.config.evaluation_foundation import SPLIT_TARGETS
from dev_set.tools import e01_dataset as ds
from dev_set.tools.e01_schema import Annotation


@pytest.fixture
def dataset(tmp_path):
    mapping = tmp_path / "frame_map.fixture"
    mapping.write_bytes(b"frozen-map-fixture")
    catalog = {"frame_map": {"path": mapping.name, "sha256": ds.file_hash(mapping)}, "videos": {}}
    rows = []
    for split, tasks in SPLIT_TARGETS.items():
        for task, count in tasks.items():
            for i in range(count):
                video = f"fixture_{len(rows)}"
                asset = tmp_path / f"{video}.jpg"
                asset.write_bytes(video.encode())
                refs = [{"video_id": video, "frame_idx": f, "keyframe_id": f"{video}#k{f}",
                         "path": asset.name, "sha256": ds.file_hash(asset)} for f in (10, 20)]
                catalog["videos"][video] = {"frames": refs}
                rows.append(dict(query_id=f"E01_{'VAL' if split=='validation' else 'HOLD'}_{task}_{i+1:02d}",
                                 task_type=task, split=split, video_id=video))
    ds.write_new(tmp_path / "catalog.json", catalog)
    source_hash = ds.file_hash(tmp_path / "catalog.json")
    entries = [Annotation(**r, source_manifest_sha256=source_hash, source_version="fixture.v1").model_dump() for r in rows]
    plan = {"dataset_version": "fixture.v1", "entries": entries,
            "source_catalog": "catalog.json", "source_catalog_sha256": source_hash}
    folder = tmp_path / "dataset"
    ds.initialize(folder, plan)
    return folder, tmp_path, entries, plan


def valid_entry(entry, root):
    e = deepcopy(entry)
    e["query_text"] = "fixture-query-" + e["query_id"]
    e["verification"]["status"] = "verified"
    e["grouping"].update(duplicate_group=e["video_id"], event_group=e["video_id"], review_status="verified",
                         prior_exposure_checked=True, prior_exposure_found=False)
    e["label"]["evidence"] = [{**r, "support": "human fixture source observation"}
                                for r in ds.read(root / "catalog.json")["videos"][e["video_id"]]["frames"]]
    e["label"]["windows"] = [{"start": 10, "end": 20}]
    if e["task_type"] == "QA":
        e["label"].update(answerability="answerable", acceptable_answers=["0", "Không có người"])
    if e["task_type"] == "TRAKE":
        e["label"]["events"] = [{"description": f"event {i}", "windows": [{"start": f, "end": f}],
                                    "evidence_keys": [f"{e['video_id']}#k{f}"], "support_status": "evidence_backed"}
                                   for i, f in enumerate((10, 20))]
    return e


def verify_all(dataset):
    folder, root, entries, _ = dataset
    for e in entries:
        ds.record(folder, valid_entry(e, root), actor="fixture-human", reason="fixture evidence review",
                  human_reviewed=True, root=root)


def test_pending_packet_cannot_seal_or_claim_independence(dataset):
    folder, root, _, _ = dataset
    report = ds.quality(folder)
    assert report["reserved_source_packets"] == 44
    assert report["queries_proposed"] == report["human_verified"] == 0
    assert not report["independence_established"]
    with pytest.raises(ValueError, match="GT/grouping"):
        ds.seal(folder, actor="fixture-human", root=root)
    assert not (folder / "seal.json").exists()


def test_human_attestation_required_and_revisions_preserve_old_labels(dataset):
    folder, root, entries, _ = dataset
    old = (folder / "revisions/000001.json").read_bytes()
    e = valid_entry(entries[0], root)
    with pytest.raises(ValueError, match="human review"):
        ds.record(folder, e, actor="fixture-human", reason="review", root=root)
    ds.record(folder, e, actor="fixture-human", reason="review", human_reviewed=True, root=root)
    e["query_text"] = "corrected wording before seal"
    ds.record(folder, e, actor="fixture-human", reason="source correction", human_reviewed=True, root=root)
    assert (folder / "revisions/000001.json").read_bytes() == old
    content, _, n = ds.load(folder)
    assert n == 3 and len(content["changes"]) == 2
    assert content["changes"][-1]["old_label"]["query_text"] != e["query_text"]
    assert content["changes"][-1]["new_label"]["verification"]["verifier"] == "fixture-human"


@pytest.mark.parametrize("field,value", [("video_id", "another_video"), ("split", "sealed_heldout"),
                                        ("source_manifest_sha256", "a" * 64)])
def test_cannot_reassign_source_or_split_in_place(dataset, field, value):
    folder, root, entries, _ = dataset
    e = deepcopy(entries[0]); e[field] = value
    with pytest.raises(ValueError):
        ds.record(folder, e, actor="fixture-human", reason="reassign", root=root)
    assert ds.load(folder)[2] == 1


@pytest.mark.parametrize("tamper", ["asset", "map", "catalog", "frame"])
def test_evidence_and_mapping_hashes_are_enforced(dataset, tamper):
    folder, root, entries, _ = dataset
    e = valid_entry(entries[0], root)
    if tamper == "asset":
        (root / e["label"]["evidence"][0]["path"]).write_bytes(b"changed")
    elif tamper == "map":
        (root / "frame_map.fixture").write_bytes(b"changed")
    elif tamper == "catalog":
        (root / "catalog.json").write_text("{}")
    else:
        e["label"]["evidence"][0]["frame_idx"] = 999
    with pytest.raises(ValueError):
        ds.record(folder, e, actor="fixture-human", reason="review", human_reviewed=True, root=root)


@pytest.mark.parametrize("kind", ["same_video", "duplicate_group", "event_group", "similar_wording"])
def test_cross_split_leakage_is_reported(dataset, kind):
    _, _, entries, _ = dataset
    a, b = deepcopy(entries[0]), deepcopy(entries[22])
    if kind == "same_video": b["video_id"] = a["video_id"]
    elif kind == "similar_wording":
        a["query_text"] = "một người đang chạy nhanh trên đường"
        b["query_text"] = "một người đang chạy nhanh trên đường!"
    else: a["grouping"][kind] = b["grouping"][kind] = "same"
    audit = ds.leakage_audit([a, b])
    assert kind in audit["cross_split_issues"][0]["reasons"]
    assert not audit["clear"]


def test_verified_zero_negative_and_ordered_events_can_seal_once(dataset):
    verify_all(dataset)
    folder, root, entries, _ = dataset
    seal_hash = ds.seal(folder, actor="fixture-human", root=root)
    sealed_bytes = (folder / "seal.json").read_bytes()
    assert seal_hash == ds.file_hash(folder / "seal.json")
    with pytest.raises(FileExistsError): ds.seal(folder, actor="fixture-human", root=root)
    with pytest.raises(ValueError, match="Đã seal"):
        ds.record(folder, valid_entry(entries[0], root), actor="fixture-human", reason="change", human_reviewed=True, root=root)
    ds.consume(folder, actor="fixture-human", protocol="fixture H03a final selection")
    assert ds.quality(folder)["consumed"]
    assert not ds.quality(folder)["independence_established"]
    with pytest.raises(FileExistsError): ds.consume(folder, actor="fixture-human", protocol="second opening")
    assert (folder / "seal.json").read_bytes() == sealed_bytes


def test_correction_version_inherits_consumption_and_keeps_old_seal(dataset):
    verify_all(dataset)
    folder, root, _, _ = dataset
    ds.seal(folder, actor="fixture-human", root=root)
    before = (folder / "seal.json").read_bytes()
    ds.consume(folder, actor="fixture-human", protocol="fixture opening")
    child = root / "corrected"
    ds.fork_correction(folder, child, version="fixture.v2", actor="fixture-human", reason="wrong GT interval")
    content, _, _ = ds.load(child)
    assert content["inherited_consumed"]
    assert content["parent"]["reason"] == "wrong GT interval"
    assert all(e["verification"]["status"] == "pending" for e in content["entries"])
    assert (folder / "seal.json").read_bytes() == before
    assert not ds.quality(child)["independence_established"]


@pytest.mark.parametrize("target", ["revision", "seal"])
def test_hash_chain_or_seal_tampering_fails(dataset, target):
    folder, root, _, _ = dataset
    if target == "seal":
        verify_all(dataset); ds.seal(folder, actor="fixture-human", root=root)
        path = folder / "seal.json"
        value = ds.read(path); value["sealed_by"] = "tampered"
    else:
        path = folder / "revisions/000001.json"
        value = ds.read(path); value["content"]["entries"][0]["query_text"] = "tampered"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError): ds.load(folder)


@pytest.mark.parametrize("problem", ["negative_frame", "bool_frame", "reversed_window", "ambiguous_event", "wrong_order", "no_tolerance_reason", "missing_event_reference"])
def test_invalid_trake_label_is_not_verified(dataset, problem):
    folder, root, entries, _ = dataset
    e = valid_entry(next(e for e in entries if e["task_type"] == "TRAKE"), root)
    ev = e["label"]["events"][0]
    if problem == "negative_frame": ev["windows"][0]["start"] = -1
    elif problem == "bool_frame": ev["windows"][0]["start"] = True
    elif problem == "reversed_window": ev["windows"][0]["start"] = 100
    elif problem == "ambiguous_event": ev["support_status"] = "ambiguous"
    elif problem == "wrong_order": e["label"]["events"].reverse()
    elif problem == "no_tolerance_reason": ev["temporal_tolerance_frames"] = 10
    else: ev["evidence_keys"] = ["not_in_evidence"]
    with pytest.raises(ValueError):
        ds.record(folder, e, actor="fixture-human", reason="review", human_reviewed=True, root=root)


def test_seal_rechecks_assets_and_rejects_incomplete_grouping(dataset):
    verify_all(dataset)
    folder, root, entries, _ = dataset
    e = ds.load(folder)[0]["entries"][0]
    e["grouping"]["prior_exposure_found"] = True
    ds.record(folder, e, actor="fixture-human", reason="exposed", human_reviewed=True, root=root)
    with pytest.raises(ValueError): ds.seal(folder, actor="fixture-human", root=root)
    e["grouping"]["prior_exposure_found"] = False
    ds.record(folder, e, actor="fixture-human", reason="fixture correction", human_reviewed=True, root=root)
    (root / e["label"]["evidence"][0]["path"]).write_bytes(b"changed later")
    with pytest.raises(ValueError): ds.seal(folder, actor="fixture-human", root=root)


def test_exact_shared_frames_need_explanation_even_with_different_group_ids(dataset):
    _, root, entries, plan = dataset
    catalog = ds.read(root / "catalog.json")
    for video in catalog["videos"].values():
        for ref in video["frames"]:
            (root / ref["path"]).write_bytes(b"shared-stock-frame")
            ref["sha256"] = ds.file_hash(root / ref["path"])
    (root / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
    plan = deepcopy(plan)
    plan["source_catalog_sha256"] = ds.file_hash(root / "catalog.json")
    for e in plan["entries"]: e["source_manifest_sha256"] = plan["source_catalog_sha256"]
    folder = root / "shared"
    ds.initialize(folder, plan)
    verify_all((folder, root, plan["entries"], plan))
    assert ds.quality(folder)["labels_ready_for_seal_checks"]
    assert not ds.quality(folder)["independence_established"]
    with pytest.raises(ValueError, match="shared frames"):
        ds.seal(folder, actor="fixture-human", root=root)
    assert not ds.quality(folder)["independence_established"]


def test_init_cannot_change_denominator_or_prepopulate_gt(dataset):
    _, root, _, plan = dataset
    wrong = deepcopy(plan); wrong["entries"].pop()
    with pytest.raises(ValueError, match="12 KIS"):
        ds.initialize(root / "wrong_counts", wrong)
    wrong = deepcopy(plan); wrong["entries"][0]["query_text"] = "prefilled answer-derived query"
    with pytest.raises(ValueError, match="Init"):
        ds.initialize(root / "prefilled", wrong)


def test_unanswerable_qa_requires_evidence_and_no_fake_answer(dataset):
    folder, root, entries, _ = dataset
    e = valid_entry(next(e for e in entries if e["task_type"] == "QA"), root)
    e["label"].update(answerability="unanswerable", unanswerable_reason="source does not show the requested field")
    with pytest.raises(ValueError, match="unanswerable"):
        ds.record(folder, e, actor="fixture-human", reason="source review", human_reviewed=True, root=root)
    e["label"]["acceptable_answers"] = []
    ds.record(folder, e, actor="fixture-human", reason="source review", human_reviewed=True, root=root)
    saved = next(x for x in ds.load(folder)[0]["entries"] if x["query_id"] == e["query_id"])
    assert saved["label"]["answerability"] == "unanswerable"
