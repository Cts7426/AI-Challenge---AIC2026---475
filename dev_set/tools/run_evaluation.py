import sys
import json
import argparse
import traceback
from datetime import datetime
from pathlib import Path
from tqdm import tqdm

from backend.indexing.es_client import connect as es_connect
from backend.indexing.milvus_client import connect as milvus_connect
from backend.retrieval.search import search
from backend.indexing.frame_map import load_frame_map
from backend.slot.allocator import allocate, ShotHit, shot_bounds
from backend.export import write_submissions
from backend.tasks.qa import qa_pipeline

from data.config.submit_format import Answer
from dev_set.tools.schema import Query, GroundTruthKIS, GroundTruthQA, GroundTruthTRAKE
from dev_set.tools.scoring import recall_at_k, final_score, rscore_kis, rscore_trake


def load_jsonl(path: Path):
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def get_failure_class(r_at_100: float) -> str:
    # Phân loại failure đơn giản. Chi tiết F1-F7 sẽ do evaluate.py làm với metadata.
    if r_at_100 >= 1.0:
        return "SUCCESS"
    return "F_UNKNOWN"


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


def run_evaluation():
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["tune", "holdout"], default="tune")
    parser.add_argument("--resume", help="Thư mục run cũ (vd: dev_set/results/run_20260812_1000) để chạy tiếp")
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

    # 1. Connect DBs
    print("Kết nối database...")
    try:
        es_connect()
        milvus_connect()
    except Exception as e:
        print(f"LỖI DB: {e}. Bạn đã chạy Docker chưa?")
        sys.exit(1)

    fmap = load_frame_map()

    # 2. Load Queries and GT — mỗi dòng lỗi bị cô lập, không crash cả batch (#5)
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

    gt_path = Path(f"dev_set/ground_truth/{args.split}_gt.jsonl")
    gts = {}
    for row in load_jsonl(gt_path):
        qid = row.get("query_id")
        try:
            row_clean = {k: v for k, v in row.items() if k != "task_type"}
            t = row.get("task_type")
            if t == "KIS":
                gts[qid] = GroundTruthKIS(**row_clean)
            elif t == "QA":
                gts[qid] = GroundTruthQA(**row_clean)
            elif t == "TRAKE":
                gts[qid] = GroundTruthTRAKE(**row_clean)
            else:
                raise ValueError(f"task_type lạ: {t}")
        except Exception as e:
            print(f"LỖI parse GT {qid}: {e} — bỏ qua dòng này")

    if not queries:
        print("Không có query nào để chạy.")
        return

    # 3. Thư mục output — tạo mới, hoặc tiếp tục run cũ (#3)
    if args.resume:
        out_dir = Path(args.resume)
        if not out_dir.exists():
            print(f"LỖI: không tìm thấy thư mục resume {out_dir}")
            sys.exit(1)
        run_id = out_dir.name.replace("run_", "")
        print(f"Tiếp tục run cũ tại {out_dir}")
    else:
        run_id = datetime.now().strftime("%Y%m%d_%H%M")
        out_dir = Path(f"dev_set/results/run_{run_id}")
        out_dir.mkdir(parents=True, exist_ok=True)

        config_snapshot = {}
        for cfg in Path("data/config").glob("*.py"):
            config_snapshot[cfg.name] = cfg.read_text()

        (out_dir / "config_snapshot.json").write_text(json.dumps({
            "commit": get_git_commit(),
            "configs": config_snapshot
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    scores_jsonl_path = out_dir / "scores.jsonl"
    answers_jsonl_path = out_dir / "answers.jsonl"

    # Tiến độ cũ: CHỈ coi "đã xong" các câu THÀNH CÔNG — câu từng crash được
    # thử lại (lỗi lần trước có thể chỉ là ES/Milvus chập chờn, không phải bug).
    done_qids: set[str] = set()
    if scores_jsonl_path.exists():
        for line in scores_jsonl_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            if rec.get("failure_class") != "F0_CRASH":
                done_qids.add(rec["query_id"])
    if done_qids:
        print(f"Đã có {len(done_qids)} câu hoàn thành từ trước, sẽ bỏ qua.")

    # 4. Search loop — flush TỪNG câu ngay lập tức (JSONL append), không giữ
    # kết quả trong RAM tới cuối vòng lặp: crash giữa chừng không mất câu đã
    # xong (bất biến #7 CLAUDE.md, áp cho MỌI job chạy lâu, không riêng OCR/ASR).
    err_count = 0

    print("Bắt đầu truy xuất...")
    with open(scores_jsonl_path, "a", encoding="utf-8") as scores_f, \
         open(answers_jsonl_path, "a", encoding="utf-8") as answers_f:

        for q in tqdm(queries):
            if q.query_id not in gts:
                print(f"\n[BỎ QUA] {q.query_id} không có Ground Truth.")
                continue
            if q.query_id in done_qids:
                continue

            gt = gts[q.query_id]

            try:
                q_en = q.query_en or q.query_vi
                best_hit_ranks = {}

                if q.task_type == "QA":
                    # ⚠️ SỬA 14/08 (code review phát hiện): bản cũ gán
                    # `answer_text = gt.answer_text` — nghĩa là so sánh đáp án
                    # với CHÍNH NÓ, R-Score của QA LUÔN LÀ 1.0 bất kể hệ thống
                    # thật trả lời gì (đo thật: "màu xanh"/"CHUA_CO_ANSWER"/
                    # "màu đỏ" đều ra R@1=1.0 với code cũ). Giờ gọi ĐÚNG
                    # pipeline production (backend.tasks.qa.qa_pipeline, C3.1)
                    # để answer_text là câu hệ THẬT SỰ sinh ra — 482 dòng
                    # qa.py trước đây chưa từng được đo lần nào qua đường này.
                    #
                    # KHÔNG có best_hit_ranks debug ở nhánh này: qa_pipeline()
                    # tự search trên event_vi đã tách (khác q.query_vi gốc),
                    # không trả lại thứ hạng thô từng nhánh — chấp nhận mất
                    # tính năng debug phụ để giữ đúng hành vi production, đo
                    # ranks riêng cho QA là việc làm thêm sau nếu cần.
                    hits, answer_text = qa_pipeline(q.query_vi, query_en=q_en)
                else:
                    res = search(q.query_vi, q_en, top_k=100, group_by_shot=True)
                    hits = _to_shot_hits(res)
                    answer_text = None

                n_trake = q.n_events if q.task_type == "TRAKE" else None
                ans = allocate(hits, q.task_type, answer_text=answer_text, n_trake=n_trake)

                r_1 = recall_at_k(ans, gt, q.task_type, 1)
                r_5 = recall_at_k(ans, gt, q.task_type, 5)
                r_20 = recall_at_k(ans, gt, q.task_type, 20)
                r_50 = recall_at_k(ans, gt, q.task_type, 50)
                r_100 = recall_at_k(ans, gt, q.task_type, 100)
                fin = final_score(ans, gt, q.task_type)

                # Thứ hạng của câu đúng trên từng nhánh search — để debug thất
                # bại. Chỉ có cho KIS/TRAKE (dùng res thô của q.query_vi gốc);
                # QA xem comment ở trên.
                if q.task_type != "QA":
                    for row in res:
                        video_id = row["video_id"]
                        kf = row["keyframe_id"]
                        if kf not in fmap:
                            continue
                        frame_idx = fmap[kf]

                        hit = False
                        if q.task_type == "KIS":
                            hit = (rscore_kis(video_id, frame_idx, gt) > 0)
                        elif q.task_type == "TRAKE":
                            if video_id == gt.video_id:
                                for w in gt.frames:
                                    if w["start"] <= frame_idx <= w["end"]:
                                        hit = True
                                        break

                        if hit:
                            best_hit_ranks = row.get("ranks", {})
                            break

                if fin >= 1.0:
                    fc = "SUCCESS"
                elif q.task_type == "QA":
                    retrieval_success = False
                    for h in hits:
                        try:
                            vid, start, end = shot_bounds(h.shot_id)
                            if vid == gt.video_id and start <= gt.frame_idx <= end:
                                retrieval_success = True
                                break
                        except KeyError:
                            pass
                    fc = "F_QA_REASONING_FAILED" if retrieval_success else "F_QA_RETRIEVAL_FAILED"
                else:
                    fc = get_failure_class(r_100)

                record = {
                    "query_id": q.query_id,
                    "task_type": q.task_type,
                    "r_at_1": r_1,
                    "r_at_5": r_5,
                    "r_at_20": r_20,
                    "r_at_50": r_50,
                    "r_at_100": r_100,
                    "final": fin,
                    "failure_class": fc,
                    "ranks": best_hit_ranks,
                }
                scores_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                scores_f.flush()

                # Chỉ ghi answers khi câu THÀNH CÔNG — câu crash không được lẫn
                # vào file nộp trong khi scores.json báo F0_CRASH (fix #9).
                answers_f.write(json.dumps({
                    "query_id": q.query_id,
                    "answers": [_answer_to_dict(a) for a in ans],
                }, ensure_ascii=False) + "\n")
                answers_f.flush()

            except Exception as e:
                err_count += 1
                print(f"\n[LỖI] Query {q.query_id} ném ngoại lệ:")
                traceback.print_exc()
                record = {
                    "query_id": q.query_id,
                    "task_type": q.task_type,
                    "r_at_1": 0.0,
                    "r_at_5": 0.0,
                    "r_at_20": 0.0,
                    "r_at_50": 0.0,
                    "r_at_100": 0.0,
                    "final": 0.0,
                    "failure_class": "F0_CRASH",
                    "ranks": {},
                }
                scores_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                scores_f.flush()
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

    scores = {
        "run_id": run_id,
        "commit": get_git_commit(),
        "split": args.split,
        "per_query": list(per_query_by_id.values()),
    }
    (out_dir / "scores.json").write_text(
        json.dumps(scores, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    ans_dict: dict[str, list[Answer]] = {}
    for line in answers_jsonl_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        qid = rec["query_id"]
        # Nếu bản ghi THÀNH CÔNG cuối cùng của qid lại là F0_CRASH (câu từng
        # thành công ở lần chạy trước, nhưng đã bị xoá/hỏng dữ liệu và giờ
        # crash) thì đừng nộp answers cũ của nó.
        if qid not in per_query_by_id or per_query_by_id[qid]["failure_class"] == "F0_CRASH":
            continue
        ans_dict[qid] = [_answer_from_dict(d) for d in rec["answers"]]

    if ans_dict:
        write_submissions(ans_dict, str(out_dir))

    print(f"\nĐã hoàn thành! Kết quả lưu tại: {out_dir}")
    print(f"Tổng query lỗi (lần chạy này): {err_count} / {len(queries) - len(done_qids)}")


if __name__ == "__main__":
    run_evaluation()
