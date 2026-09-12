"""Kho nhãn E01 append-only: kiểm source, tách split, seal và ghi lần mở held-out.

Không gọi retrieval/evaluator/LLM. CLI record chỉ dành cho quyết định người đã
xem source; --human-reviewed là lời xác nhận của người vận hành, không phải
máy tự kiểm chứng ai đã xem ảnh. Mỗi sửa nhãn tạo revision mới, giữ nhãn cũ.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import unicodedata

from data.config.evaluation_foundation import SPLIT_TARGETS, WORDING_JACCARD_THRESHOLD
from dev_set.tools.e01_schema import Annotation

ROOT = Path(__file__).resolve().parents[2]


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def file_hash(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_new(path, value):
    """Ghi exclusive và flush; nếu dở dang thì lần đọc sau fail, không đè evidence."""
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.flush()


def load(dataset):
    """Input dataset dir; output revision mới nhất sau kiểm đủ hash-chain và seal."""
    files = sorted((Path(dataset) / "revisions").glob("*.json"))
    if not files:
        raise ValueError("Dataset chưa có revision")
    previous = None
    for index, path in enumerate(files, 1):
        value = read(path)
        if path.name != f"{index:06d}.json" or value["revision"] != index or value["previous_sha256"] != previous:
            raise ValueError("Revision chain sai hoặc thiếu")
        if value["content_sha256"] != digest(value["content"]):
            raise ValueError("Revision content hash sai")
        previous = file_hash(path)
    seal_path = Path(dataset) / "seal.json"
    if seal_path.exists() and read(seal_path)["revision_sha256"] != previous:
        raise ValueError("Dataset đã thay đổi sau seal")
    if seal_path.exists():
        if read(Path(dataset) / "seal_sha256.json")["sha256"] != file_hash(seal_path):
            raise ValueError("Seal manifest hash sai")
        consumed_path = Path(dataset) / "consumed.json"
        if consumed_path.exists() and read(consumed_path)["seal_sha256"] != file_hash(seal_path):
            raise ValueError("Consumed marker không khớp seal")
    content = value["content"]
    # Bổ sung default schema cùng v1 cho draft cũ, không ghi lại bytes revision.
    content["entries"] = [Annotation.model_validate(e).model_dump() for e in content["entries"]]
    return content, previous, len(files)


def append_revision(dataset, content, previous, index):
    write_new(Path(dataset) / "revisions" / f"{index:06d}.json",
              {"revision": index, "previous_sha256": previous, "created_at": now(),
               "content_sha256": digest(content), "content": content})


def initialize(dataset, plan):
    """Khởi tạo split khóa trước model evaluation; mọi entry phải pending và query trống."""
    entries = [Annotation.model_validate(e).model_dump() for e in plan["entries"]]
    ids = [e["query_id"] for e in entries]
    if len(ids) != len(set(ids)):
        raise ValueError("Query ID trùng")
    counts = Counter((e["split"], e["task_type"]) for e in entries)
    expected = Counter({(s, t): n for s, tasks in SPLIT_TARGETS.items() for t, n in tasks.items()})
    if counts != expected:
        raise ValueError("Cần đúng 12 KIS/6 QA/4 TRAKE mỗi split")
    if any(e["verification"]["status"] != "pending" or e["query_text"] or e["label"]["evidence"] for e in entries):
        raise ValueError("Init chỉ nhận nguồn đề xuất, không tự điền query/GT")
    content = {"dataset_version": plan["dataset_version"], "created_at": now(),
               "source_catalog": plan["source_catalog"], "source_catalog_sha256": plan["source_catalog_sha256"],
               "entries": entries, "inherited_consumed": False, "changes": []}
    if any(e["source_manifest_sha256"] != content["source_catalog_sha256"] for e in entries):
        raise ValueError("Source manifest hash không khớp")
    path = Path(dataset)
    path.mkdir(parents=True, exist_ok=False)
    (path / "revisions").mkdir()
    append_revision(path, content, None, 1)


def check_evidence(entry, content, root=ROOT):
    """Kiểm asset và map đã đóng trong source catalog; không suy frame từ tên ảnh."""
    path = root / content["source_catalog"]
    if file_hash(path) != content["source_catalog_sha256"]:
        raise ValueError("Source catalog đã đổi")
    catalog = read(path)
    if file_hash(root / catalog["frame_map"]["path"]) != catalog["frame_map"]["sha256"]:
        raise ValueError("Frame map đã đổi; cần version nguồn mới")
    refs = {r["keyframe_id"]: r for r in catalog["videos"][entry["video_id"]]["frames"]}
    for evidence in entry["label"]["evidence"]:
        ref = refs.get(evidence["keyframe_id"])
        fields = ("video_id", "keyframe_id", "frame_idx", "path", "sha256")
        if not ref or any(ref[k] != evidence[k] for k in fields):
            raise ValueError("Evidence không khớp source/map identity")
        if file_hash(root / evidence["path"]) != evidence["sha256"]:
            raise ValueError("Evidence bytes đã đổi")


def record(dataset, entry, *, actor, reason, human_reviewed=False, root=ROOT):
    """Append quyết định có người chịu trách nhiệm; source/task/video/split không sửa tại chỗ."""
    if (Path(dataset) / "seal.json").exists():
        raise ValueError("Đã seal: tạo dataset version sửa lỗi, không sửa tại chỗ")
    content, previous, index = load(dataset)
    if not actor.strip() or not reason.strip():
        raise ValueError("Cần actor và lý do sửa")
    updated = deepcopy(entry)
    is_verified = updated.get("verification", {}).get("status") == "verified"
    group_verified = updated.get("grouping", {}).get("review_status") == "verified"
    if (is_verified or group_verified) and not human_reviewed:
        raise ValueError("Thiếu xác nhận human review")
    if is_verified:
        updated["verification"].update(verifier=actor, verified_at=now(), source_only_attestation=True)
    if group_verified:
        updated["grouping"].update(verifier=actor, reviewed_at=now())
    updated = Annotation.model_validate(updated).model_dump()
    items = {e["query_id"]: e for e in content["entries"]}
    old = items[updated["query_id"]]
    for field in ("query_id", "task_type", "split", "video_id", "source_manifest_sha256", "source_version"):
        if old[field] != updated[field]:
            raise ValueError(f"Không sửa {field}; cần version/sampling plan mới")
    check_evidence(updated, content, root)
    items[updated["query_id"]] = updated
    content["entries"] = list(items.values())
    content["changes"].append({"query_id": updated["query_id"], "actor": actor, "at": now(),
                               "reason": reason, "old_label": old, "new_label": updated})
    append_revision(dataset, content, previous, index + 1)


def normalized(text):
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def leakage_audit(entries):
    """Cross-split: video/group/event trùng hoặc wording gần nhau; pending không coi là clear."""
    issues = []
    for i, left in enumerate(entries):
        for right in entries[i + 1:]:
            if left["split"] == right["split"]:
                continue
            reasons = []
            if left["video_id"] == right["video_id"]:
                reasons.append("same_video")
            for key in ("duplicate_group", "event_group"):
                if left["grouping"].get(key) and left["grouping"].get(key) == right["grouping"].get(key):
                    reasons.append(key)
            a, b = normalized(left["query_text"]), normalized(right["query_text"])
            ta, tb = set(re.findall(r"\w+", a)), set(re.findall(r"\w+", b))
            if a and b and (a == b or (min(len(ta), len(tb)) >= 4 and len(ta & tb) / len(ta | tb) >= WORDING_JACCARD_THRESHOLD)):
                reasons.append("similar_wording")
            if reasons:
                issues.append({"left": left["query_id"], "right": right["query_id"], "reasons": reasons})
    pending = [e["query_id"] for e in entries if not (
        e["grouping"]["review_status"] == "verified" and e["grouping"]["verifier"]
        and e["grouping"]["reviewed_at"] and e["grouping"]["duplicate_group"]
        and e["grouping"]["event_group"] and e["grouping"]["prior_exposure_checked"]
        and e["grouping"]["prior_exposure_found"] is False)]
    return {"cross_split_issues": issues, "grouping_or_exposure_pending": pending,
            "clear": not issues and not pending}


def quality(dataset):
    content, revision_hash, _ = load(dataset)
    entries = content["entries"]
    audit = leakage_audit(entries)
    verified = sum(e["verification"]["status"] == "verified" for e in entries)
    consumed = content["inherited_consumed"] or (Path(dataset) / "consumed.json").exists()
    sealed = (Path(dataset) / "seal.json").exists()
    labels_ready = verified == len(entries) and audit["clear"] and not consumed
    return {"dataset_version": content["dataset_version"], "revision_sha256": revision_hash,
            "reserved_source_packets": len(entries), "queries_proposed": sum(bool(e["query_text"].strip()) for e in entries),
            "human_verified": verified, "verification_status": dict(Counter(e["verification"]["status"] for e in entries)),
            "tasks": dict(Counter(e["task_type"] for e in entries)),
            "videos": dict(Counter(e["video_id"] for e in entries)),
            "split_counts": dict(Counter(e["split"] for e in entries)),
            "duplicate_groups": dict(Counter(e["grouping"]["duplicate_group"] or "unreviewed" for e in entries)),
            "ambiguous_events": sum(ev["support_status"] == "ambiguous" for e in entries for ev in e["label"]["events"]),
            "ambiguity_review_pending": len(entries) - verified,
            "reviewers": sorted({e["verification"]["verifier"] for e in entries if e["verification"]["verifier"]}),
            "disagreements": "not_measured_no_independent_second_review",
            "leakage": audit, "sealed": sealed, "consumed": consumed,
            "labels_ready_for_seal_checks": labels_ready,
            "independence_established": labels_ready and sealed}


def seal(dataset, *, actor, root=ROOT):
    """Seal chỉ khi đủ 44 nhãn human/source/group verified; viết exclusive manifest/hash."""
    content, revision_hash, _ = load(dataset)
    report = quality(dataset)
    if not actor.strip() or not report["labels_ready_for_seal_checks"] or report["consumed"]:
        raise ValueError("Không seal: GT/grouping/exposure chưa đủ hoặc version đã consumed")
    catalog = read(root / content["source_catalog"])
    # Ảnh giống byte có thể là footage lặp hoặc frame chung; bắt buộc người giải thích,
    # không tự suy toàn video là duplicate hoặc mặc nhiên bỏ qua cảnh trùng.
    hashes = {e["video_id"]: {f["sha256"] for f in catalog["videos"][e["video_id"]]["frames"]}
              for e in content["entries"]}
    for i, left in enumerate(content["entries"]):
        for right in content["entries"][i + 1:]:
            if left["split"] != right["split"] and hashes[left["video_id"]] & hashes[right["video_id"]]:
                if any(not e["grouping"]["shared_frame_reviewed"] or not e["grouping"]["shared_frame_explanation"].strip()
                       for e in (left, right)):
                    raise ValueError("Exact shared frames giữa hai split chưa được human review")
    for e in content["entries"]:
        Annotation.model_validate(e)
        check_evidence(e, content, root)
    manifest = {"dataset_version": content["dataset_version"], "sealed_at": now(), "sealed_by": actor,
                "revision_sha256": revision_hash, "source_catalog_sha256": content["source_catalog_sha256"],
                "entries": [{"query_id": e["query_id"], "split": e["split"], "video_id": e["video_id"],
                             "query_sha256": digest({"task_type": e["task_type"], "query_text": e["query_text"]}),
                             "gt_sha256": digest(e["label"]), "annotation_sha256": digest(e),
                             "verification": e["verification"], "grouping": e["grouping"]} for e in content["entries"]]}
    write_new(Path(dataset) / "seal.json", manifest)
    write_new(Path(dataset) / "seal_sha256.json", {"sha256": file_hash(Path(dataset) / "seal.json")})
    return file_hash(Path(dataset) / "seal.json")


def consume(dataset, *, actor, protocol):
    """Ghi mở held-out TRƯỚC model/output inspection, một lần cho development decision."""
    load(dataset)
    path = Path(dataset) / "seal.json"
    if not path.exists() or not actor.strip() or not protocol.strip():
        raise ValueError("Cần seal, actor và protocol trước khi mở held-out")
    write_new(Path(dataset) / "consumed.json", {"opened_at": now(), "opened_by": actor,
              "protocol": protocol, "seal_sha256": file_hash(path), "role": "consumed_for_development_decision"})


def fork_correction(dataset, destination, *, version, actor, reason):
    """Giữ seal cũ, tạo version mới; consumed không thể trở lại independent sau sửa GT."""
    content, old_hash, _ = load(dataset)
    if not (Path(dataset) / "seal.json").exists() or not all(s.strip() for s in (version, actor, reason)):
        raise ValueError("Correction cần sealed parent, version, actor, reason")
    if version == content["dataset_version"]:
        raise ValueError("Cần dataset_version mới")
    content["inherited_consumed"] = content["inherited_consumed"] or (Path(dataset) / "consumed.json").exists()
    content["parent"] = {"dataset_version": content["dataset_version"], "revision_sha256": old_hash,
                         "seal_sha256": file_hash(Path(dataset) / "seal.json"), "actor": actor, "reason": reason, "at": now()}
    content["dataset_version"] = version
    for e in content["entries"]:
        e["verification"]["status"] = "pending"
    Path(destination).mkdir(parents=True, exist_ok=False)
    (Path(destination) / "revisions").mkdir()
    append_revision(destination, content, None, 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["init", "quality", "record", "seal", "consume", "fork-correction"])
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--by", default="")
    parser.add_argument("--reason", default="")
    parser.add_argument("--protocol", default="")
    parser.add_argument("--version", default="")
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--human-reviewed", action="store_true")
    args = parser.parse_args()
    if args.action in ("init", "record") and args.input is None:
        parser.error("Cần --input")
    if args.action == "init":
        initialize(args.dataset, read(args.input))
    elif args.action == "quality":
        print(json.dumps(quality(args.dataset), ensure_ascii=False, indent=2))
    elif args.action == "record":
        record(args.dataset, read(args.input), actor=args.by, reason=args.reason, human_reviewed=args.human_reviewed)
    elif args.action == "seal":
        print(seal(args.dataset, actor=args.by))
    elif args.action == "consume":
        consume(args.dataset, actor=args.by, protocol=args.protocol)
    else:
        if args.destination is None:
            parser.error("Cần --destination")
        fork_correction(args.dataset, args.destination, version=args.version, actor=args.by, reason=args.reason)


if __name__ == "__main__":
    main()
