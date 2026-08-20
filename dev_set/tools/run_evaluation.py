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
from backend.export import QuerySubmission, write_submissions
from backend.tasks.qa import qa_pipeline

from data.config.submit_format import Answer
from dev_set.tools.schema import Query, GroundTruthKIS, GroundTruthQA, GroundTruthTRAKE
from dev_set.tools.scoring import recall_at_k, final_score, rscore_kis


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
    # "dress25" (20/08): bộ 25 câu mô phỏng 1 buổi thi thật, sinh bởi
    # generate_dress_rehearsal.py — KHÔNG qua hạn mức holdout (không phải bộ đề
    # chuẩn dùng để đánh giá cuối, chỉ để đo điểm hệ thống hiện tại một lần).
    parser.add_argument("--split", choices=["tune", "holdout", "dress25"], default="tune")
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
         open(answers_jsonl_path, "a", encoding="utf-8") as answers_f, \
         open(candidates_jsonl_path, "a", encoding="utf-8") as candidates_f:

        for q in tqdm(queries):
            if q.query_id not in gts:
                print(f"\n[BỎ QUA] {q.query_id} không có Ground Truth.")
                continue
            if q.query_id in done_qids:
                continue

            gt = gts[q.query_id]

            try:
                # KHÔNG fallback về query_vi: search()/qa_pipeline() coi
                # query_en=None là tín hiệu "tự dịch qua llm()" (đúng đường
                # sống thật, xem backend/api/main.py::post_search) — nếu dev
                # set không có sẵn bản dịch tay thì để None, đừng đút thẳng
                # tiếng Việt vào CLIP (huấn luyện trên caption tiếng Anh).
                q_en = q.query_en
                best_hit_ranks = {}
                n_trake = None

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
                    ans = allocate(hits, q.task_type, answer_text=answer_text)
                elif q.task_type == "TRAKE":
                    # ⚠️ SỬA 16/08: bản cũ KHÔNG hề gọi pipeline TRAKE thật
                    # (parse_events + trake_search) — nó ném cả câu multi-event
                    # vào search() NHƯ MỘT CÂU KIS ĐƠN (vi phạm giới hạn 77
                    # token của CLIP, xem backend/tasks/trake.py), rồi để
                    # allocate()/_allocate_trake() tự bịa N khoảnh khắc từ 1
                    # shot của search đơn đó. Nghĩa là MỌI số liệu TRAKE trên
                    # dev_set trước đây đo một pipeline khác hẳn production —
                    # đây chính là gốc rễ "TRAKE hoạt động y hệt KIS" đo được.
                    #
                    # event_descs (nếu dev_set/queries/*_trake.jsonl có sẵn) ưu
                    # tiên hơn parse_events(): tránh gọi LLM lặp lại mỗi lần
                    # tune (tốn tiền + không xác định), và tách sự kiện thủ
                    # công luôn đáng tin hơn LLM đoán trên đúng 1 câu ngắn.
                    from backend.tasks.trake import pad_answers, parse_events, to_answers, trake_search
                    events = q.event_descs if q.event_descs else parse_events(q.query_vi)
                    n_trake = len(events)
                    candidates = trake_search(events, top_videos=100)
                    if not candidates:
                        raise RuntimeError("trake_search() không tìm được video ứng viên nào")
                    ans = to_answers(candidates)
                    if len(ans) < 100:
                        ans = pad_answers(candidates, 100)
                    answer_text = None
                    hits = []  # TRAKE không dùng ShotHit — candidates_f ghi từ `candidates` riêng bên dưới
                    # Debug: hạng của ĐÚNG VIDEO trong danh sách ứng viên TRAKE
                    # — TRAKE xếp hạng theo video (sai video = 0 điểm tuyệt
                    # đối), không phải hạng 1 keyframe đơn lẻ như KIS.
                    for rank, c in enumerate(candidates, 1):
                        if c.video_id == gt.video_id:
                            best_hit_ranks = {"trake_video_rank": rank}
                            break
                else:
                    res = search(q.query_vi, q_en, top_k=100, group_by_shot=True)
                    hits = _to_shot_hits(res)
                    answer_text = None
                    ans = allocate(hits, q.task_type, answer_text=answer_text)

                r_1 = recall_at_k(ans, gt, q.task_type, 1)
                r_5 = recall_at_k(ans, gt, q.task_type, 5)
                r_20 = recall_at_k(ans, gt, q.task_type, 20)
                r_50 = recall_at_k(ans, gt, q.task_type, 50)
                r_100 = recall_at_k(ans, gt, q.task_type, 100)
                fin = final_score(ans, gt, q.task_type)

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
                    fc = "SUCCESS"
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
                    cand_list = [
                        {"video_id": c.video_id, "score": float(c.score),
                         "n_hit_events": c.n_hit_events, "has_full_order": c.has_full_order}
                        for c in candidates
                    ]
                else:
                    cand_list = [
                        {"shot_id": h.shot_id, "score": float(h.score),
                         "best_keyframe_id": h.best_keyframe_id} for h in hits
                    ]
                candidates_f.write(json.dumps({
                    "query_id": q.query_id,
                    "task_type": q.task_type,
                    "answer_text": answer_text,
                    "n_trake": n_trake,
                    "candidates": cand_list,
                }, ensure_ascii=False) + "\n")
                candidates_f.flush()

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
        if qid not in per_query_by_id or per_query_by_id[qid]["failure_class"] == "F0_CRASH":
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
