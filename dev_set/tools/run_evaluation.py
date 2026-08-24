import argparse
import hashlib
import json
import os
import sys
import traceback
from datetime import datetime
from functools import wraps
from pathlib import Path
from tqdm import tqdm

from backend.indexing.es_client import connect as es_connect
from backend.indexing.milvus_client import connect as milvus_connect
from backend.indexing.frame_map import load_frame_map
from backend.slot.allocator import ShotHit, shot_bounds
from backend.export import QuerySubmission, write_submissions
from backend.tasks.qa import validate_evidence_capture
from backend.tasks.runner import (
    QueryRun,
    SolveQueryError,
    failure_trace,
    runtime_fingerprint as build_query_runtime_fingerprint,
    runtime_manifest as build_query_runtime_manifest,
    solve_query,
)

from data.config.submit_format import Answer
from data.config.qa_evaluation import DEFAULT_QA_MATCH_POLICY, QA_MATCH_POLICIES
from data.config.release_gate import (
    HOLDOUT_MANIFEST_ID,
    HOLDOUT_QUERY_SET_SHA256,
    PROMOTION_SCORER_CONTRACT,
    REGRESSION_MANIFEST_ID,
    REGRESSION_QUERY_SET_SHA256,
)
from dev_set.tools.promotion_provenance import (
    ground_truth_record_sha256,
    ground_truth_set_sha256,
    is_sha256,
    query_record_sha256,
    query_set_sha256,
)
from dev_set.tools.schema import Query, GroundTruthKIS, GroundTruthQA, GroundTruthTRAKE
from dev_set.tools.scoring import (
    assess_promotion_ground_truth,
    final_score,
    recall_at_k,
    require_promotion_ground_truth,
    rscore_kis,
)
from dev_set.tools.scorer_contract import scorer_contract_sha256


RUN_SNAPSHOT_SCHEMA_VERSION = 2
EVALUATION_ENV_NAMES = (
    "LLM_RUN_ID",
    "LLM_QUERY_ID",
    "QA_EVIDENCE_LOG_PATH",
)
_ENV_MISSING = object()


def _restore_evaluation_environment(func):
    """Bọc evaluator bằng finally để không leak env sang run/query kế tiếp."""
    @wraps(func)
    def wrapped(*args, **kwargs):
        previous = {
            name: os.environ.get(name, _ENV_MISSING)
            for name in EVALUATION_ENV_NAMES
        }
        try:
            return func(*args, **kwargs)
        finally:
            for name, value in previous.items():
                if value is _ENV_MISSING:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

    return wrapped


def _hash_json(payload: dict) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _runtime_snapshot(
    split: str, *, evaluation_paths: list[Path] | None = None,
) -> tuple[dict, dict[str, str], dict[str, str]]:
    """Snapshot artefact evaluation; query identity lấy nguyên từ runner chung."""
    configs = {
        cfg.name: cfg.read_text(encoding="utf-8")
        for cfg in sorted(Path("data/config").glob("*.py"))
    }
    critical_sources = {
        label: hashlib.sha256(path.read_bytes()).hexdigest()
        for label, path in {
            "backend/tasks/qa.py": Path("backend/tasks/qa.py"),
            "backend/common/answer_match.py": Path("backend/common/answer_match.py"),
            "dev_set/tools/run_evaluation.py": Path(__file__),
            "dev_set/tools/scoring.py": Path("dev_set/tools/scoring.py"),
            "data/config/qa_evaluation.py": Path("data/config/qa_evaluation.py"),
        }.items()
    }
    input_paths = evaluation_paths or [
        *(Path(f"dev_set/queries/{split}_{task}.jsonl")
          for task in ("kis", "qa", "trake")),
        Path(f"dev_set/ground_truth/{split}_gt.jsonl"),
    ]
    evaluation_inputs = {
        path.as_posix(): (
            hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "missing"
        )
        for path in input_paths
    }
    query_manifest = build_query_runtime_manifest()
    query_fingerprint = build_query_runtime_fingerprint()
    llm_provenance = {
        **query_manifest["llm"],
        "source": "backend.tasks.runner.runtime_manifest",
    }
    manifest = {
        "commit": get_git_commit(),
        "split": split,
        "query_runtime_fingerprint": query_fingerprint,
        "llm_provenance": llm_provenance,
        "config_sources_sha256": _hash_json(configs),
        "critical_sources_sha256": critical_sources,
        "evaluation_inputs_sha256": evaluation_inputs,
    }
    return manifest, configs, llm_provenance


def _validate_resume_snapshot(
    snapshot: dict,
    current_query_fingerprint: str,
    current_artifact_fingerprint: str | None = None,
) -> str:
    """Fail closed nếu query runtime hoặc artefact evaluation khác run cũ."""
    if snapshot.get("schema_version") != RUN_SNAPSHOT_SCHEMA_VERSION:
        raise RuntimeError("run cũ không có fingerprint schema v2")
    prior_fingerprint = snapshot.get(
        "query_runtime_fingerprint", snapshot.get("runtime_fingerprint")
    )
    if prior_fingerprint != current_query_fingerprint:
        raise RuntimeError(
            "query runtime hiện tại khác run cũ: "
            f"cũ={prior_fingerprint}, mới={current_query_fingerprint}"
        )
    if current_artifact_fingerprint is not None:
        prior_artifact = snapshot.get("evaluation_artifact_fingerprint")
        if prior_artifact != current_artifact_fingerprint:
            raise RuntimeError(
                "split/scorer/GT artefact hiện tại khác run cũ: "
                f"cũ={prior_artifact}, mới={current_artifact_fingerprint}"
            )
    return str(snapshot.get("run_id") or "")


def load_jsonl(path: Path):
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def _manifest_rows(manifest: dict) -> list[dict]:
    rows = manifest.get("entries", manifest.get("queries"))
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError("manifest phải có list entries/queries")
    return rows


def _load_frozen_inputs(
    manifest_path: Path,
    ground_truth_path: Path | None,
) -> tuple[str, list[Query], dict[str, object], list[Path]]:
    """Nạp exact frozen IDs/content/GT; không tin hash tự khai trong manifest."""
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"không đọc được frozen manifest: {error}") from error
    if not isinstance(manifest, dict):
        raise ValueError("frozen manifest phải là JSON object")
    manifest_id = str(manifest.get("manifest_id") or "")
    expected_hash = {
        HOLDOUT_MANIFEST_ID: HOLDOUT_QUERY_SET_SHA256,
        REGRESSION_MANIFEST_ID: REGRESSION_QUERY_SET_SHA256,
    }.get(manifest_id)
    if expected_hash is None:
        raise ValueError(f"manifest_id không phải frozen set chính thức: {manifest_id!r}")
    rows = _manifest_rows(manifest)
    ids = [str(row.get("query_id") or "") for row in rows]
    if any(not query_id for query_id in ids) or len(ids) != len(set(ids)):
        raise ValueError("frozen manifest có query_id rỗng/trùng")

    source_paths: list[Path] = [manifest_path]
    query_sources: dict[str, dict] = {}
    if all(isinstance(row.get("query_vi"), str) and row["query_vi"] for row in rows):
        query_sources = {str(row["query_id"]): dict(row) for row in rows}
    elif manifest_id == HOLDOUT_MANIFEST_ID:
        for task in ("kis", "qa", "trake"):
            path = Path(f"dev_set/queries/holdout_{task}.jsonl")
            source_paths.append(path)
            for query in load_jsonl(path):
                query_sources[str(query.get("query_id") or "")] = query
    else:
        raise ValueError("regression manifest thiếu nội dung query_vi đã đóng băng")

    queries: list[Query] = []
    for row in rows:
        query_id = str(row["query_id"])
        source = query_sources.get(query_id)
        if source is None:
            raise ValueError(f"manifest tham chiếu query không tồn tại: {query_id}")
        actual_query_hash = query_record_sha256(source)
        declared_query_hash = row.get("query_sha256")
        if declared_query_hash is not None and declared_query_hash != actual_query_hash:
            raise ValueError(
                f"{query_id} query content hash khác frozen manifest: "
                f"expected={declared_query_hash}, actual={actual_query_hash}"
            )
        if source.get("task_type") != row.get("task_type"):
            raise ValueError(f"{query_id} task_type query khác manifest")
        query_data = {
            key: source[key]
            for key in ("query_id", "task_type", "query_vi", "query_en", "n_events", "event_descs")
            if key in source
        }
        query_data["split"] = source.get("split") or (
            "holdout" if manifest_id == HOLDOUT_MANIFEST_ID else "dress25"
        )
        queries.append(Query(**query_data))
    if query_set_sha256(queries) != expected_hash:
        raise ValueError("tập query đã nạp không khớp frozen query-set digest")

    if ground_truth_path is None:
        if manifest_id == HOLDOUT_MANIFEST_ID:
            ground_truth_path = Path("dev_set/ground_truth/holdout_gt.jsonl")
        else:
            raise ValueError("regression frozen set bắt buộc --ground-truth")
    source_paths.append(ground_truth_path)
    gt_rows = {
        str(row.get("query_id") or ""): row for row in load_jsonl(ground_truth_path)
    }
    task_of = {query.query_id: query.task_type for query in queries}
    gt_class = {"KIS": GroundTruthKIS, "QA": GroundTruthQA, "TRAKE": GroundTruthTRAKE}
    ground_truth: dict[str, object] = {}
    manifest_by_id = {str(row["query_id"]): row for row in rows}
    for query_id, task_type in task_of.items():
        raw = gt_rows.get(query_id)
        if raw is None:
            raise ValueError(f"frozen set thiếu GT cho {query_id}")
        if raw.get("task_type") not in (None, task_type):
            raise ValueError(f"{query_id} task_type GT khác query")
        parsed = gt_class[task_type](**{
            key: value for key, value in raw.items() if key != "task_type"
        })
        manifest_row = manifest_by_id[query_id]
        expected_gt_hash = manifest_row.get("ground_truth_sha256")
        actual_gt_hash = ground_truth_record_sha256(parsed)
        if not is_sha256(expected_gt_hash) or expected_gt_hash != actual_gt_hash:
            raise ValueError(
                f"{query_id} GT hash thiếu/khác frozen manifest: "
                f"expected={expected_gt_hash}, actual={actual_gt_hash}"
            )
        for field in ("verification_status", "provenance", "verified_by", "verified_at"):
            if manifest_row.get(field) != getattr(parsed, field):
                raise ValueError(f"{query_id} metadata {field} của GT khác manifest")
        ground_truth[query_id] = parsed
    return manifest_id, queries, ground_truth, source_paths


def _record_succeeded(record: dict) -> bool:
    """Đọc được cả artefact legacy F0_CRASH lẫn status mới của QueryRun."""
    if "status" in record:
        return record["status"] == "success"
    return record.get("failure_class") != "F0_CRASH"


def get_git_commit() -> str:
    import subprocess
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def _to_shot_hits(res: list[dict]) -> list[ShotHit]:
    """search(group_by_shot=True) đã gom 1 dòng/shot và gắn shot_id sẵn — chỉ
    còn việc bọc lại thành ShotHit. Bỏ dòng không tra được shot_id (keyframe lạ,
    index lệch phiên bản): allocate() cần shot_id để tra biên shot.
    """
    return [
        ShotHit(r["shot_id"], r["score"], r["keyframe_id"])
        for r in res
        if r.get("shot_id") is not None
    ]


def _solve_for_evaluation(
    query: object, *, total: int, query_runtime_fingerprint: str
) -> QueryRun:
    """Evaluator dùng đúng dispatch production và ghim fingerprint run hiện có."""
    return solve_query(
        query, total=total, runtime_fingerprint=query_runtime_fingerprint,
    )


def _answer_to_dict(a: Answer) -> dict:
    return {
        "video_id": a.video_id,
        "frame_ids": list(a.frame_ids),
        "answer_text": a.answer_text,
        "keyframe_id": a.keyframe_id,
    }


def _answer_from_dict(d: dict) -> Answer:
    return Answer(
        video_id=d["video_id"],
        frame_ids=tuple(d["frame_ids"]),
        answer_text=d.get("answer_text"),
        keyframe_id=d.get("keyframe_id"),
    )


def _score_metrics(ans: list[Answer], gt, task_type: str, qa_match_policy: str) -> dict[str, float]:
    """Một danh sách nộp -> năm R@k và Final dưới một chính sách Q&A.

    Input: 100 Answer, GT, task type và policy. Output: dict metric JSON-safe.
    Invariant: KIS/TRAKE không đổi theo policy; QA luôn đo cả semantic và exact
    từ cùng answer/frame để hai bảng có thể so sánh trực tiếp.
    """
    r_1 = recall_at_k(ans, gt, task_type, 1, qa_match_policy)
    r_5 = recall_at_k(ans, gt, task_type, 5, qa_match_policy)
    r_20 = recall_at_k(ans, gt, task_type, 20, qa_match_policy)
    r_50 = recall_at_k(ans, gt, task_type, 50, qa_match_policy)
    r_100 = recall_at_k(ans, gt, task_type, 100, qa_match_policy)
    return {
        "r_at_1": r_1,
        "r_at_5": r_5,
        "r_at_20": r_20,
        "r_at_50": r_50,
        "r_at_100": r_100,
        "final": final_score(ans, gt, task_type, qa_match_policy),
    }


@_restore_evaluation_environment
def run_evaluation(argv: list[str] | None = None):
    parser = argparse.ArgumentParser()
    # "dress25" (20/08): bộ 25 câu mô phỏng 1 buổi thi thật, sinh bởi
    # generate_dress_rehearsal.py — KHÔNG qua hạn mức holdout (không phải bộ đề
    # chuẩn dùng để đánh giá cuối, chỉ để đo điểm hệ thống hiện tại một lần).
    parser.add_argument("--split", choices=["tune", "holdout", "dress25", "gen10", "gen2"], default="tune")
    parser.add_argument("--resume", help="Thư mục run cũ (vd: dev_set/results/run_20260812_1000) để chạy tiếp")
    parser.add_argument(
        "--manifest", type=Path,
        help="frozen manifest chính thức; lọc exact IDs/content thay vì toàn split",
    )
    parser.add_argument(
        "--ground-truth", type=Path,
        help="GT JSONL thật phải khớp hash/audit trail trong frozen manifest",
    )
    parser.add_argument("--out", type=Path, help="thư mục artefact cụ thể (không dùng cùng --resume)")
    parser.add_argument(
        "--promotion",
        action="store_true",
        help="chỉ chạy khi toàn bộ GT đã verification_status=verified có provenance",
    )
    args = parser.parse_args(argv)

    if args.resume and args.out:
        parser.error("--resume và --out loại trừ nhau")

    evaluation_name = args.split
    frozen_paths: list[Path] | None = None
    frozen_gts: dict[str, object] | None = None
    if args.manifest:
        try:
            evaluation_name, queries, frozen_gts, frozen_paths = _load_frozen_inputs(
                args.manifest, args.ground_truth,
            )
        except ValueError as error:
            parser.error(str(error))
    else:
        queries = []

    print(f"Khởi động bộ đo trên tập '{evaluation_name}'...")

    if evaluation_name in ("holdout", HOLDOUT_MANIFEST_ID):
        holdout_log = Path("dev_set/holdout_log.md")
        n_used = 0
        if holdout_log.exists():
            content = holdout_log.read_text()
            n_used = content.count("## Lần")

        if n_used >= 5:
            print("LỖI: Đã dùng hết 5/5 hạn mức holdout. Từ chối chạy.")
            sys.exit(1)

        print(f"CẢNH BÁO: Đang chạy holdout! Đã dùng {n_used}/5 lần.")
        ans = input("Xác nhận chạy? (y/N): ")
        if ans.lower() != 'y':
            sys.exit(0)

    # 1. Load Queries and GT — mỗi dòng lỗi bị cô lập, không crash cả batch (#5)
    if not args.manifest:
        q_paths = [
            Path(f"dev_set/queries/{args.split}_kis.jsonl"),
            Path(f"dev_set/queries/{args.split}_qa.jsonl"),
            Path(f"dev_set/queries/{args.split}_trake.jsonl")
        ]
        for p in q_paths:
            for row in load_jsonl(p):
                try:
                    queries.append(Query(**row))
                except Exception as e:
                    print(f"LỖI parse Query {row.get('query_id')}: {e} — bỏ qua dòng này")

    # MỘT nguồn sự thật cho task_type: FILE QUERY.
    #
    # Bản trước dựng lớp GT theo `row["task_type"]` (file GT) nhưng lại CHẤM theo
    # `q.task_type` (file query) — hai file lệch nhau thì một `GroundTruthKIS` rơi
    # vào `rscore_qa()` và nổ `AttributeError: answer_text` giữa vòng lặp, rồi bị
    # `except` ngoài cùng ghi thành F0_CRASH. Câu đó biến mất khỏi bài nộp mà
    # nguyên nhân thật (hai file khai khác nhau) không hiện ra ở đâu cả.
    task_of = {q.query_id: q.task_type for q in queries}
    GT_CLASS = {"KIS": GroundTruthKIS, "QA": GroundTruthQA, "TRAKE": GroundTruthTRAKE}

    if frozen_gts is not None:
        gts = frozen_gts
    else:
        gt_path = Path(f"dev_set/ground_truth/{args.split}_gt.jsonl")
        gts = {}
        for row in load_jsonl(gt_path):
            qid = row.get("query_id")
            try:
                t = task_of.get(qid)
                if t is None:
                    raise ValueError("không có query nào mang query_id này")
                # `task_type` trong file GT chỉ còn vai trò ĐỐI CHỨNG. Có mà lệch thì
                # báo lỗi tường minh, không im lặng chọn một trong hai.
                t_gt = row.get("task_type")
                if t_gt is not None and t_gt != t:
                    raise ValueError(
                        f"task_type mâu thuẫn — file query ghi '{t}', file GT ghi '{t_gt}'"
                    )
                row_clean = {k: v for k, v in row.items() if k != "task_type"}
                gts[qid] = GT_CLASS[t](**row_clean)
            except Exception as e:
                print(f"LỖI parse GT {qid}: {e} — bỏ qua dòng này")

    # GT legacy vẫn hữu ích cho phân tích, nhưng tuyệt đối không được trông như
    # một phép promotion: thiếu metadata mặc định là `unknown` và được báo rõ.
    gt_readiness = assess_promotion_ground_truth(
        gts.values(), expected_query_ids=task_of.keys(),
    )
    print(gt_readiness.message)
    if args.promotion:
        try:
            require_promotion_ground_truth(
                gts.values(), expected_query_ids=task_of.keys(),
            )
        except ValueError as e:
            parser.error(str(e))

    if not queries:
        print("Không có query nào để chạy.")
        return

    # 2. Chỉ kết nối sau khi gate promotion đã pass: thiếu provenance là lỗi
    # input, không được che bởi lỗi service ngoài.
    print("Kết nối database...")
    try:
        es_connect()
        milvus_connect()
    except Exception as e:
        print(f"LỖI DB: {e}. Bạn đã chạy Docker chưa?")
        sys.exit(1)

    fmap = load_frame_map()

    # 3. Tách identity của lời giải khỏi artefact đánh giá: split/scorer/GT chỉ
    # đổi artefact fingerprint, không được làm QueryRun khác production.
    evaluation_artifact_manifest, config_sources, llm_provenance = _runtime_snapshot(
        evaluation_name, evaluation_paths=frozen_paths,
    )
    query_runtime_fingerprint = build_query_runtime_fingerprint()
    query_runtime_manifest = build_query_runtime_manifest()
    evaluation_artifact_fingerprint = _hash_json(evaluation_artifact_manifest)
    if args.resume:
        out_dir = Path(args.resume)
        if not out_dir.exists():
            print(f"LỖI: không tìm thấy thư mục resume {out_dir}")
            sys.exit(1)
        snapshot_path = out_dir / "config_snapshot.json"
        try:
            prior_snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            print(f"LỖI: resume thiếu/hỏng config_snapshot.json: {e}")
            sys.exit(1)
        try:
            snapshot_run_id = _validate_resume_snapshot(
                prior_snapshot,
                query_runtime_fingerprint,
                evaluation_artifact_fingerprint,
            )
        except RuntimeError as e:
            print(f"LỖI: {e}; từ chối resume")
            sys.exit(1)
        run_id = snapshot_run_id or out_dir.name.replace("run_", "")
        print(f"Tiếp tục run cũ tại {out_dir}")
    else:
        run_id = (
            datetime.now().strftime("%Y%m%d_%H%M%S")
            + f"_{evaluation_artifact_fingerprint[:8]}"
        )
        out_dir = args.out or Path(f"dev_set/results/run_{run_id}")
        out_dir.mkdir(parents=True, exist_ok=False)

        (out_dir / "config_snapshot.json").write_text(json.dumps({
            "schema_version": RUN_SNAPSHOT_SCHEMA_VERSION,
            "run_id": run_id,
            # Hai key legacy trỏ về query identity để consumer cũ không dùng
            # nhầm split/scorer/GT làm cache key của lời giải.
            "runtime_fingerprint": query_runtime_fingerprint,
            "runtime_manifest": query_runtime_manifest,
            "query_runtime_fingerprint": query_runtime_fingerprint,
            "query_runtime_manifest": query_runtime_manifest,
            "evaluation_artifact_fingerprint": evaluation_artifact_fingerprint,
            "evaluation_artifact_manifest": evaluation_artifact_manifest,
            "llm_provenance": llm_provenance,
            "configs": config_sources,
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    # Gắn run/query cho evidence capture. Không can thiệp model hoặc gọi API thêm.
    os.environ["LLM_RUN_ID"] = run_id
    os.environ["QA_EVIDENCE_LOG_PATH"] = str(out_dir / "qa_evidence.jsonl")

    scores_jsonl_path = out_dir / "scores.jsonl"
    answers_jsonl_path = out_dir / "answers.jsonl"
    # NGUYÊN LIỆU cho app/score_simulator.py (D3.5): danh sách shot ứng viên TRƯỚC khi
    # allocate() đóng gói thành 100 dòng. Không lưu lại thì muốn thử bảng slot khác
    # phải chạy lại cả vòng search (hàng chục phút, cần Milvus + ES + LLM) — mà cái
    # cần thử lại chỉ là phép chia slot, tốn vài giây.
    candidates_jsonl_path = out_dir / "candidates.jsonl"

    # Tiến độ cũ: CHỈ coi "đã xong" các câu THÀNH CÔNG — câu từng crash được
    # thử lại (lỗi lần trước có thể chỉ là ES/Milvus chập chờn, không phải bug).
    done_qids: set[str] = set()
    if scores_jsonl_path.exists():
        for line in scores_jsonl_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            if _record_succeeded(rec):
                done_qids.add(rec["query_id"])
    if done_qids:
        print(f"Đã có {len(done_qids)} câu hoàn thành từ trước, sẽ bỏ qua.")

    # 4. Search loop — flush TỪNG câu ngay lập tức (JSONL append), không giữ
    # kết quả trong RAM tới cuối vòng lặp: crash giữa chừng không mất câu đã
    # xong (bất biến #7 CLAUDE.md, áp cho MỌI job chạy lâu, không riêng OCR/ASR).
    err_count = 0

    print("Bắt đầu truy xuất...")
    with open(scores_jsonl_path, "a", encoding="utf-8") as scores_f, \
         open(answers_jsonl_path, "a", encoding="utf-8") as answers_f, \
         open(candidates_jsonl_path, "a", encoding="utf-8") as candidates_f:

        for q in tqdm(queries):
            os.environ["LLM_QUERY_ID"] = q.query_id
            if q.query_id not in gts:
                print(f"\n[BỎ QUA] {q.query_id} không có Ground Truth.")
                continue
            if q.query_id in done_qids:
                continue

            gt = gts[q.query_id]

            try:
                query_run = _solve_for_evaluation(
                    q,
                    total=100,
                    query_runtime_fingerprint=query_runtime_fingerprint,
                )
                ans = query_run.answers
                res = query_run.search_rows
                answer_text = query_run.answer_text
                qa_trace = query_run.qa_trace
                n_trake = query_run.n_trake
                hits = _to_shot_hits(res) if q.task_type != "TRAKE" else []
                best_hit_ranks = {}
                if q.task_type == "TRAKE":
                    for rank, row in enumerate(res, 1):
                        if row["video_id"] == gt.video_id:
                            best_hit_ranks = {"trake_video_rank": rank}
                            break

                # Giữ các khoá cũ ở top-level là semantic để consumer cũ không
                # đổi. Lưu song song exact giúp kiểm tra giả thuyết BTC mà không
                # chạy lại search/LLM và không lẫn hai thước đo với nhau.
                score_by_qa_policy = {
                    policy: _score_metrics(ans, gt, q.task_type, policy)
                    for policy in QA_MATCH_POLICIES
                }
                semantic_metrics = score_by_qa_policy["semantic"]
                r_1 = semantic_metrics["r_at_1"]
                r_5 = semantic_metrics["r_at_5"]
                r_20 = semantic_metrics["r_at_20"]
                r_50 = semantic_metrics["r_at_50"]
                r_100 = semantic_metrics["r_at_100"]
                fin = semantic_metrics["final"]

                # Thứ hạng của câu đúng trên từng nhánh search — để debug thất
                # bại. Chỉ có ý nghĩa cho KIS (dùng res thô của q.query_vi gốc);
                # QA xem comment ở trên, TRAKE đã tự tính best_hit_ranks riêng
                # ở nhánh xử lý của nó (hạng VIDEO, không phải hạng keyframe).
                if q.task_type == "KIS":
                    for row in res:
                        video_id = row["video_id"]
                        kf = row["keyframe_id"]
                        if kf not in fmap:
                            continue
                        frame_idx = fmap[kf]

                        if rscore_kis(video_id, frame_idx, gt) > 0:
                            best_hit_ranks = row.get("ranks", {})
                            break

                if fin >= 1.0:
                    fc = None
                elif q.task_type == "QA":
                    # Retrieval coi là THÀNH CÔNG khi có shot ứng viên GIAO với cửa
                    # sổ đáp án — trượt là do suy luận, không do tìm kiếm.
                    #
                    # ⚠️ Bản trước viết `gt.frame_idx`, mà `GroundTruthQA` chỉ có
                    # `frame_start`/`frame_end` (xem dev_set/tools/schema.py) → mọi
                    # câu QA KHÔNG đạt 1.0 đều ném AttributeError ngay tại đây, sau
                    # khi đã tính xong r_1..r_100, rồi bị `except` ngoài cùng ghi đè
                    # thành F0_CRASH với toàn số 0. Điểm QA thật bị vứt, và câu đó
                    # không được ghi vào answers.jsonl. Chỉ câu QA HOÀN HẢO thoát
                    # được, vì nhánh `fin >= 1.0` chạy trước và không đi qua dòng này
                    # → bảng điểm QA chỉ có 0.0 và 1.0, không bao giờ có giá trị giữa.
                    #
                    # Dùng phép GIAO chứ không phải CHỨA: shot chỉ cần chạm cửa sổ
                    # đáp án là người thao tác đã nhìn thấy khoảnh khắc đúng.
                    retrieval_success = False
                    for h in hits:
                        try:
                            vid, start, end = shot_bounds(h.shot_id)
                            if (vid == gt.video_id
                                    and start <= gt.frame_end
                                    and gt.frame_start <= end):
                                retrieval_success = True
                                break
                        except KeyError:
                            pass
                    fc = "qa_reasoning" if retrieval_success else "retrieval_miss"
                elif q.task_type == "TRAKE":
                    fc = (
                        "trake_order"
                        if any(row.get("video_id") == gt.video_id for row in res)
                        else "retrieval_miss"
                    )
                else:
                    fc = (
                        "wrong_frame"
                        if any(row.get("video_id") == gt.video_id for row in res)
                        else "retrieval_miss"
                    )

                record = {
                    "query_id": q.query_id,
                    "task_type": q.task_type,
                    "r_at_1": r_1,
                    "r_at_5": r_5,
                    "r_at_20": r_20,
                    "r_at_50": r_50,
                    "r_at_100": r_100,
                    "final": fin,
                    "score_by_qa_policy": score_by_qa_policy,
                    "status": "success",
                    "failure_class": fc,
                    "ranks": best_hit_ranks,
                    "runtime_fingerprint": query_run.runtime_fingerprint,
                }
                scores_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                scores_f.flush()

                # Chỉ ghi answers khi câu THÀNH CÔNG — câu crash không được lẫn
                # vào file nộp trong khi scores.json báo F0_CRASH (fix #9).
                # `task_type` + `query_vi`: THÊM 19/08 để `app/eval.py` (E4.2) đọc
                # được file này. `eval.py` cần `task_type` để biết chấm theo luật
                # nào (KIS/QA/TRAKE là ba công thức R-Score khác nhau) và nó KHÔNG
                # được phép đoán. Thiếu trường đó thì nó bỏ qua từng dòng một —
                # đo thật trên run_20260818_1739: **bỏ 25/25 dòng**, in ra "Không
                # truy vấn nào có nhãn để chấm", tức E4.2 chưa từng chấm nổi một
                # file thật nào dù đã viết xong từ 13/08.
                #
                # Chỉ THÊM trường, không đổi/bỏ trường cũ: `write_submissions()`
                # phía dưới và mọi file answers.jsonl đã ghi trước đây vẫn đọc
                # được y như cũ.
                answers_f.write(json.dumps({
                    "query_id": q.query_id,
                    "task_type": q.task_type,
                    "query_vi": q.query_vi,
                    "answers": [_answer_to_dict(a) for a in ans],
                }, ensure_ascii=False) + "\n")
                answers_f.flush()

                # Ghi NGUYÊN LIỆU ngay cạnh kết quả, cùng một lần chạy — ghi sau ở
                # một job riêng thì tầng search có thể đã đổi và nguyên liệu không
                # còn khớp bộ điểm nằm cạnh nó.
                if q.task_type == "TRAKE":
                    cand_list = res
                else:
                    cand_list = [
                        {"shot_id": h.shot_id, "score": float(h.score),
                         "best_keyframe_id": h.best_keyframe_id} for h in hits
                    ]
                trace_record = query_run.to_trace_dict()
                trace_record["candidates"] = cand_list
                candidates_f.write(json.dumps(trace_record, ensure_ascii=False) + "\n")
                candidates_f.flush()
                os.fsync(candidates_f.fileno())

            except Exception as e:
                err_count += 1
                print(f"\n[LỖI] Query {q.query_id} ném ngoại lệ:")
                traceback.print_exc()
                if isinstance(e, SolveQueryError):
                    failed_run = e.query_run
                else:
                    failed_run = failure_trace(
                        q,
                        e,
                        failure_class=(
                            "missing_evidence" if q.task_type == "QA"
                            else "trake_order" if q.task_type == "TRAKE"
                            else "retrieval_miss"
                        ),
                        runtime_fingerprint=query_runtime_fingerprint,
                    )
                record = {
                    "query_id": q.query_id,
                    "task_type": q.task_type,
                    "r_at_1": 0.0,
                    "r_at_5": 0.0,
                    "r_at_20": 0.0,
                    "r_at_50": 0.0,
                    "r_at_100": 0.0,
                    "final": 0.0,
                    "status": "failed",
                    "failure_class": failed_run.failure_class,
                    "ranks": {},
                    "runtime_fingerprint": failed_run.runtime_fingerprint,
                }
                scores_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                scores_f.flush()
                candidates_f.write(
                    json.dumps(failed_run.to_trace_dict(), ensure_ascii=False) + "\n"
                )
                candidates_f.flush()
                os.fsync(candidates_f.fileno())
                # KHÔNG ghi answers.jsonl cho câu crash (#9)

    # 5. Gom scores.jsonl + answers.jsonl thành scores.json / file nộp. Đọc lại
    # từ đĩa (không giữ list trong RAM suốt vòng lặp); dòng SAU đè dòng TRƯỚC
    # theo query_id, nên nếu resume biến một câu từng crash thành thành công,
    # bản ghi mới nhất tự nhiên thắng.
    per_query_by_id: dict[str, dict] = {}
    for line in scores_jsonl_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        per_query_by_id[rec["query_id"]] = rec

    successful_qa_qids = {
        qid for qid, rec in per_query_by_id.items()
        if task_of.get(qid) == "QA" and _record_succeeded(rec)
    }
    if successful_qa_qids:
        capture_stats = validate_evidence_capture(
            out_dir / "qa_evidence.jsonl",
            expected_query_ids=successful_qa_qids,
            validate_images=True,
        )
        print(
            "QA evidence capture hợp lệ: "
            f"{capture_stats['evidence_records']} evidence + "
            f"{capture_stats['inference_records']} output"
        )

    ground_truth_by_query_sha256 = {
        query_id: ground_truth_record_sha256(ground_truth)
        for query_id, ground_truth in sorted(gts.items())
    }
    scores = {
        "run_id": run_id,
        "commit": get_git_commit(),
        "split": evaluation_name,
        "evaluation_manifest_id": evaluation_name if args.manifest else None,
        "runtime_fingerprint": query_runtime_fingerprint,
        "query_runtime_fingerprint": query_runtime_fingerprint,
        "evaluation_artifact_fingerprint": evaluation_artifact_fingerprint,
        "scorer_contract": PROMOTION_SCORER_CONTRACT,
        "scorer_policy": DEFAULT_QA_MATCH_POLICY,
        "scorer_source_sha256": scorer_contract_sha256(),
        "promotion_ready": bool(args.promotion and gt_readiness.eligible),
        "verified_query_ids": (
            sorted(ground_truth_by_query_sha256) if gt_readiness.eligible else []
        ),
        "query_set_sha256": query_set_sha256(queries),
        "ground_truth_by_query_sha256": ground_truth_by_query_sha256,
        "ground_truth_set_sha256": ground_truth_set_sha256(
            ground_truth_by_query_sha256
        ),
        "per_query": list(per_query_by_id.values()),
    }
    (out_dir / "scores.json").write_text(
        json.dumps(scores, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # write_submissions() nhận list[QuerySubmission], KHÔNG nhận dict — bản trước
    # đưa thẳng dict vào nên nó lặp qua các KHOÁ (chuỗi) và ném
    # `AttributeError: 'str' object has no attribute 'query_id'` ở dòng cuối cùng
    # của cả lần chạy, sau khi đã tốn toàn bộ thời gian search. Và `task_type` là
    # bắt buộc: thiếu nó thì tầng nộp không biết dòng TRAKE khác dòng KIS chỗ nào.
    # `task_of` đã dựng ở bước nạp ground truth phía trên — dùng lại, không dựng
    # bản thứ hai (hai bản của cùng một bảng tra là cách chắc nhất để chúng lệch).
    subs: list[QuerySubmission] = []
    for line in answers_jsonl_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        qid = rec["query_id"]
        # Nếu bản ghi THÀNH CÔNG cuối cùng của qid lại là F0_CRASH (câu từng
        # thành công ở lần chạy trước, nhưng đã bị xoá/hỏng dữ liệu và giờ
        # crash) thì đừng nộp answers cũ của nó.
        if qid not in per_query_by_id or not _record_succeeded(per_query_by_id[qid]):
            continue
        subs.append(QuerySubmission(
            query_id=qid,
            task_type=task_of.get(qid, per_query_by_id[qid]["task_type"]),
            answers=tuple(_answer_from_dict(d) for d in rec["answers"]),
        ))

    if subs:
        # Bỏ bản ghi cũ của cùng query_id khi resume: file JSONL chỉ nối thêm, mà
        # `validate_all()` coi query_id lặp lại là lỗi và từ chối ghi CẢ LÔ.
        subs = list({s.query_id: s for s in subs}.values())
        # Luật `trake_n_mismatch` (D0.2) có sẵn từ đầu nhưng CHƯA AI TRUYỀN GIÁ TRỊ
        # — kiểm 16/08: `expected_n` chỉ xuất hiện trong test, 0 chỗ gọi sản xuất,
        # nên luật đó luôn ngủ. Nguồn sự thật ở ngay đây: `Query.n_events` là số
        # khoảnh khắc đề TRAKE công bố. Không nối thì allocator nộp sai số frame
        # mà validator vẫn xanh, và `rscore_trake` cho 0 TUYỆT ĐỐI khi lệch N.
        expected_n = {
            q.query_id: q.n_events
            for q in queries
            if q.task_type == "TRAKE" and q.n_events
        }
        _, loi_file = write_submissions(subs, str(out_dir), expected_n=expected_n)
        if loi_file:
            print("CẢNH BÁO: file nộp có vấn đề:")
            for i in loi_file:
                print(f"  {i}")

    print(f"\nĐã hoàn thành! Kết quả lưu tại: {out_dir}")
    print(f"Tổng query lỗi (lần chạy này): {err_count} / {len(queries) - len(done_qids)}")


if __name__ == "__main__":
    run_evaluation()
