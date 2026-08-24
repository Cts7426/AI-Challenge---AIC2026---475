import argparse
import hashlib
import json
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path
from tqdm import tqdm

from backend.indexing.es_client import connect as es_connect
from backend.indexing.milvus_client import connect as milvus_connect
from backend.indexing.frame_map import load_frame_map
from backend.slot.allocator import ShotHit, shot_bounds
from backend.export import QuerySubmission, write_submissions
from backend.tasks.qa import validate_evidence_capture
from backend.tasks.runner import QueryRun, SolveQueryError, failure_trace, solve_query

from data.config.submit_format import Answer
from data.config.qa_evaluation import QA_MATCH_POLICIES
from dev_set.tools.schema import Query, GroundTruthKIS, GroundTruthQA, GroundTruthTRAKE
from dev_set.tools.scoring import (
    assess_promotion_ground_truth,
    final_score,
    recall_at_k,
    require_promotion_ground_truth,
    rscore_kis,
)


RUN_SNAPSHOT_SCHEMA_VERSION = 2


def _hash_json(payload: dict) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _runtime_snapshot(split: str) -> tuple[dict, dict[str, str], dict[str, str]]:
    """Hash QA knobs/source + LLM env đã chọn; không tự chọn hay đổi model."""
    from backend.llm.adapter import (
        DEFAULT_API_MODEL,
        DEFAULT_GEMINI_MODEL,
        DEFAULT_LOCAL_MODEL,
    )
    from data.config.qa_inference import qa_runtime_config

    configs = {
        cfg.name: cfg.read_text(encoding="utf-8")
        for cfg in sorted(Path("data/config").glob("*.py"))
    }
    critical_sources = {
        label: hashlib.sha256(path.read_bytes()).hexdigest()
        for label, path in {
            "backend/tasks/qa.py": Path("backend/tasks/qa.py"),
            "dev_set/tools/run_evaluation.py": Path(__file__),
        }.items()
    }
    backend = os.environ.get("LLM_BACKEND", "api")
    model_by_backend = {
        "api": os.environ.get("LLM_API_MODEL", DEFAULT_API_MODEL),
        "gemini": os.environ.get("LLM_GEMINI_MODEL", DEFAULT_GEMINI_MODEL),
        "local": os.environ.get("LLM_LOCAL_MODEL", DEFAULT_LOCAL_MODEL),
    }
    llm_provenance = {
        "backend": backend,
        "model": model_by_backend.get(backend, "<invalid-backend>"),
        "source": "environment override or adapter default",
    }
    manifest = {
        "commit": get_git_commit(),
        "split": split,
        "qa_runtime": qa_runtime_config(),
        "llm_provenance": llm_provenance,
        "config_sources_sha256": _hash_json(configs),
        "critical_sources_sha256": critical_sources,
    }
    return manifest, configs, llm_provenance


def _validate_resume_snapshot(snapshot: dict, current_fingerprint: str) -> str:
    """Fail closed nếu run cũ không cùng LLM env/QA knobs/config/source."""
    if snapshot.get("schema_version") != RUN_SNAPSHOT_SCHEMA_VERSION:
        raise RuntimeError("run cũ không có fingerprint schema v2")
    prior_fingerprint = snapshot.get("runtime_fingerprint")
    if prior_fingerprint != current_fingerprint:
        raise RuntimeError(
            "LLM env/QA mode/knobs/config/code hiện tại khác run cũ: "
            f"cũ={prior_fingerprint}, mới={current_fingerprint}"
        )
    return str(snapshot.get("run_id") or "")


def load_jsonl(path: Path):
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


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
    query: object, *, total: int, runtime_fingerprint: str
) -> QueryRun:
    """Evaluator dùng đúng dispatch production và ghim fingerprint run hiện có."""
    return solve_query(
        query, total=total, runtime_fingerprint=runtime_fingerprint,
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


def run_evaluation():
    parser = argparse.ArgumentParser()
    # "dress25" (20/08): bộ 25 câu mô phỏng 1 buổi thi thật, sinh bởi
    # generate_dress_rehearsal.py — KHÔNG qua hạn mức holdout (không phải bộ đề
    # chuẩn dùng để đánh giá cuối, chỉ để đo điểm hệ thống hiện tại một lần).
    parser.add_argument("--split", choices=["tune", "holdout", "dress25", "gen10", "gen2"], default="tune")
    parser.add_argument("--resume", help="Thư mục run cũ (vd: dev_set/results/run_20260812_1000) để chạy tiếp")
    parser.add_argument(
        "--promotion",
        action="store_true",
        help="chỉ chạy khi toàn bộ GT đã verification_status=verified có provenance",
    )
    args = parser.parse_args()

    print(f"Khởi động bộ đo trên tập '{args.split}'...")

    if args.split == "holdout":
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
    queries = []
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

    # 3. Thư mục output — fingerprint khóa model/mode/config khi resume.
    runtime_manifest, config_sources, llm_provenance = _runtime_snapshot(args.split)
    runtime_fingerprint = _hash_json(runtime_manifest)
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
            snapshot_run_id = _validate_resume_snapshot(prior_snapshot, runtime_fingerprint)
        except RuntimeError as e:
            print(f"LỖI: {e}; từ chối resume")
            sys.exit(1)
        run_id = snapshot_run_id or out_dir.name.replace("run_", "")
        print(f"Tiếp tục run cũ tại {out_dir}")
    else:
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + f"_{runtime_fingerprint[:8]}"
        out_dir = Path(f"dev_set/results/run_{run_id}")
        out_dir.mkdir(parents=True, exist_ok=False)

        (out_dir / "config_snapshot.json").write_text(json.dumps({
            "schema_version": RUN_SNAPSHOT_SCHEMA_VERSION,
            "run_id": run_id,
            "runtime_fingerprint": runtime_fingerprint,
            "runtime_manifest": runtime_manifest,
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
                    q, total=100, runtime_fingerprint=runtime_fingerprint,
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
                        runtime_fingerprint=runtime_fingerprint,
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

    scores = {
        "run_id": run_id,
        "commit": get_git_commit(),
        "split": args.split,
        "runtime_fingerprint": runtime_fingerprint,
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

    os.environ.pop("LLM_QUERY_ID", None)
    os.environ.pop("LLM_RUN_ID", None)
    os.environ.pop("QA_EVIDENCE_LOG_PATH", None)

    print(f"\nĐã hoàn thành! Kết quả lưu tại: {out_dir}")
    print(f"Tổng query lỗi (lần chạy này): {err_count} / {len(queries) - len(done_qids)}")


if __name__ == "__main__":
    run_evaluation()
