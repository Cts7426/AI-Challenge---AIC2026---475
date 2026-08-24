# run.py — A6.0: ORCHESTRATOR ĐẦY ĐỦ (file truy vấn → file nộp)
#
# ===== Khác gì run_minimal.py =====
#   run_minimal.py — kịch bản DỰ PHÒNG: chỉ CLIP + BM25 + slot, đọc hết trong
#                    một lượt, không có gì để hỏng. Giữ nguyên, đừng thêm gì.
#   run.py         — đường chạy THẬT ngày nộp: đủ ba dạng bài (KIS · Q&A · TRAKE),
#                    checkpoint từng câu, chạy tiếp khi một câu hỏng, log truy được.
#
# ===== Vì sao CHECKPOINT là tính năng số 1, không phải progress bar =====
# Một lượt 50 câu có Q&A và TRAKE là hàng trăm lần gọi LLM + hàng nghìn truy vấn
# Milvus/ES — hàng chục phút và tiền thật. Mất điện / Milvus chập chờn / Ctrl-C
# nhầm ở câu thứ 47 mà phải chạy lại từ câu 1 là mất cả buổi tối, đúng vào đêm
# trước hạn nộp. Nên MỖI CÂU XONG được ghi ngay xuống đĩa (JSONL, append +
# flush + fsync) — cùng luật với job OCR/ASR (CLAUDE.md bất biến 7), vì cùng
# một lý do: job dài thì phải resume được.
#
# ⚠️ Checkpoint có một cửa tử riêng: chạy lại với FILE TRUY VẤN ĐÃ SỬA mà vẫn
# dùng checkpoint cũ = nộp câu trả lời của câu hỏi CŨ dưới query_id mới, im
# lặng hoàn toàn. Nên mỗi bản ghi mang theo `query_hash` — đề đổi thì bản ghi
# đó bị coi là hết hạn và chạy lại, không cần ai nhớ xoá file.
#
# ===== Câu hỏng thì làm gì =====
# Chạy tiếp, KHÔNG ghi checkpoint cho nó (lần chạy sau tự thử lại — lỗi thường
# là ES/Milvus chập chờn chứ không phải bug), và KHÔNG sinh file nộp giả cho nó.
# Một file 100 dòng độn trông y hệt file thật ở thư mục nộp; hai ngày sau không
# ai phân biệt được nữa. Thà thiếu file và biết mình thiếu.
#
# ===== Chạy =====
#   docker compose up -d                       # Milvus + ES (Milvus cần ~90s)
#   python run.py --queries dev_set/queries/full_test.jsonl --out submissions/lan_1
#   python run.py --queries ... --out ... --zip          # gói .zip chuẩn BTC
#   python run.py --queries ... --out ...                # chạy lại = chạy tiếp
#   python run.py --queries ... --out ... --only q003,q007   # chỉ chạy lại 2 câu
#   python run.py --queries ... --out ... --fresh        # bỏ checkpoint, làm lại từ đầu
#
# File truy vấn — JSON (một list) hoặc JSONL (mỗi dòng một object):
#   {"query_id": "q001", "task_type": "KIS", "query_vi": "...", "query_en": "..."}
#   {"query_id": "q002", "task_type": "QA",  "query_vi": "... là gì?"}
#   {"query_id": "q003", "task_type": "TRAKE", "query_vi": "a . b . c",
#    "event_descs": ["a", "b", "c"]}      # có sẵn thì khỏi tốn 1 lần gọi LLM
#
# Exit code: 0 = mọi câu xong, file đã ghi · 1 = có câu hỏng / không ghi được
#            · 2 = sai đầu vào (file truy vấn hỏng, thiếu khoá...).

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.export import (  # noqa: E402
    ANSWERS_PER_QUERY,
    QuerySubmission,
    write_submission_zip,
    write_submissions,
)
from backend.export.qa_variants import apply_qa_submission_policy  # noqa: E402
from backend.tasks.runner import (  # noqa: E402
    QueryRun,
    SolveQueryError,
    failure_trace,
    runtime_fingerprint as build_runtime_fingerprint,
    solve_query,
)
from data.config.qa_evaluation import QA_SUBMISSION_POLICIES  # noqa: E402
from data.config.submit_format import TASK_TYPES, Answer, suggest_filename  # noqa: E402

CHECKPOINT_NAME = "checkpoint.jsonl"
LOG_NAME = "run.log"
TRACE_NAME = "trace.jsonl"


# ============================================================ đọc file truy vấn

def _official_task_from_id(query_id: str) -> str | None:
    """Suy task chỉ từ hậu tố tên file BTC đã công bố, không đoán nội dung đề."""
    match = re.search(r"-(kis|qa|trake)$", query_id, flags=re.IGNORECASE)
    return match.group(1).upper() if match else None

def _doc_queries(path: Path) -> list[dict]:
    """Đọc .json (list) hoặc .jsonl (mỗi dòng một object), kiểm tra ngặt.

    Vì sao kiểm ngặt hơn run_minimal.py: đây là đường nộp THẬT. Một `task_type`
    gõ nhầm ("kis" thường) hay hai câu trùng `query_id` sẽ đi hết pipeline rồi
    mới hỏng ở tận bước ghi file — sau khi đã đốt hàng chục phút và tiền LLM.
    Bắt ở đây, trước khi tốn gì.
    """
    if not path.exists():
        raise SystemExit(f"[đầu vào] Không thấy file truy vấn: {path}")

    raw = path.read_text(encoding="utf-8").strip()
    try:
        if path.suffix.lower() == ".jsonl":
            data = [json.loads(d) for d in raw.splitlines() if d.strip()]
        else:
            data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise SystemExit(f"[đầu vào] {path} không phải JSON hợp lệ: {e}")

    if not isinstance(data, list) or not data:
        raise SystemExit(f"[đầu vào] {path} phải chứa một LIST truy vấn khác rỗng.")

    loi: list[str] = []
    da_thay: dict[str, int] = {}
    for i, q in enumerate(data, 1):
        if not isinstance(q, dict):
            loi.append(f"truy vấn thứ {i}: phải là object, đang là {type(q).__name__}")
            continue
        for khoa in ("query_id", "task_type", "query_vi"):
            if not str(q.get(khoa, "")).strip():
                loi.append(f"truy vấn thứ {i}: thiếu hoặc rỗng khoá '{khoa}'")
        qid, task = str(q.get("query_id", "")), q.get("task_type")
        if qid != qid.strip():
            loi.append(f"[{qid!r}] query_id có khoảng trắng đầu/cuối — tên file nộp sẽ sai")
        try:
            suggest_filename(qid)
        except ValueError as e:
            loi.append(str(e))
        if task not in TASK_TYPES:
            loi.append(f"[{qid}] task_type '{task}' không hợp lệ, phải là {TASK_TYPES}")
        official_task = _official_task_from_id(qid)
        if official_task and task in TASK_TYPES and task != official_task:
            loi.append(
                f"[{qid}] hậu tố tên file là {official_task} nhưng task_type={task}"
            )
        if qid in da_thay:
            loi.append(f"[{qid}] query_id trùng với truy vấn thứ {da_thay[qid]} — "
                       "mỗi truy vấn một file nộp, trùng id là ghi đè lên nhau")
        da_thay[qid] = i
        # TRAKE cần ≥2 khoảnh khắc; sai N là 0 điểm dù mọi frame đều đúng
        if task == "TRAKE":
            ds = q.get("event_descs")
            ds_hop_le = (
                isinstance(ds, list)
                and len(ds) >= 2
                and all(isinstance(event, str) and event.strip() for event in ds)
            )
            if ds is not None and not ds_hop_le:
                loi.append(f"[{qid}] event_descs phải là list ít nhất 2 chuỗi không rỗng")

            n_events = q.get("n_events")
            if n_events is None and ds_hop_le:
                # Đây là suy luận cấu trúc an toàn duy nhất: list tường minh có
                # bao nhiêu phần tử thì bài nộp cần đúng bấy nhiêu frame/event.
                n_events = len(ds)
                q["n_events"] = n_events
            if isinstance(n_events, bool) or not isinstance(n_events, int) or n_events < 2:
                loi.append(f"[{qid}] TRAKE cần n_events nguyên >=2")
            elif ds_hop_le and len(ds) != n_events:
                loi.append(
                    f"[{qid}] n_events={n_events} nhưng event_descs có {len(ds)} phần tử"
                )

    if loi:
        raise SystemExit("[đầu vào] File truy vấn có lỗi:\n  " + "\n  ".join(loi[:20]))
    return data


def _query_hash(q: dict) -> str:
    """Vân tay của NỘI DUNG một truy vấn — đổi đề thì checkpoint cũ hết hạn.

    Chỉ băm những trường ẢNH HƯỞNG câu trả lời. Thêm `split`/ghi chú vào file
    truy vấn không được làm mất công chạy lại.
    """
    loi = json.dumps(
        [q.get("task_type"), q.get("query_vi"), q.get("query_en"),
         q.get("event_descs"), q.get("n_events")],
        ensure_ascii=False, sort_keys=True,
    )
    return hashlib.sha256(loi.encode("utf-8")).hexdigest()[:12]


def _llm_runtime_errors(queries: list[dict]) -> list[str]:
    """Chặn gọi nhầm provider/model mặc định trước khi batch chạm search/LLM.

    Chỉ kiểm các query thực sự sắp compute. Hàm không chọn model và không đọc
    `.env`: operator phải chủ động export backend/model/key trong đúng terminal
    chạy release, nhờ đó một biến bị quên không âm thầm rơi về API/Opus mặc định.
    """
    need_llm = [
        q["query_id"] for q in queries
        if q["task_type"] in ("QA", "TRAKE")
        or (q["task_type"] == "KIS" and not str(q.get("query_en") or "").strip())
    ]
    if not need_llm:
        return []

    backend = str(os.environ.get("LLM_BACKEND") or "").strip()
    if not backend:
        return [
            "batch có query cần LLM nhưng LLM_BACKEND chưa được set tường minh "
            f"(ví dụ: {', '.join(need_llm[:5])})"
        ]
    config = {
        "api": ("LLM_API_MODEL", "ANTHROPIC_API_KEY"),
        "gemini": ("LLM_GEMINI_MODEL", "GEMINI_API_KEY"),
        "local": ("LLM_LOCAL_MODEL", None),
    }
    if backend not in config:
        return [f"LLM_BACKEND={backend!r} không hợp lệ; chọn api, gemini hoặc local"]

    model_env, key_env = config[backend]
    errors = []
    if not str(os.environ.get(model_env) or "").strip():
        errors.append(
            f"thiếu {model_env}; phải chọn model tường minh trước batch để không dùng default ẩn"
        )
    if key_env and not str(os.environ.get(key_env) or "").strip():
        # Adapter hiện hành chỉ nạp SECRET từ `.env`; model/backend vẫn phải do
        # operator export tường minh. Chỉ kiểm sự hiện diện, tuyệt đối không log
        # hay đưa giá trị key vào artefact.
        env_path = REPO_ROOT / ".env"
        key_in_dotenv = False
        if env_path.is_file():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                name, sep, value = line.partition("=")
                if sep and name.strip() == key_env and value.strip().strip('"\''):
                    key_in_dotenv = True
                    break
        if not key_in_dotenv:
            errors.append(f"thiếu {key_env} cho LLM_BACKEND={backend}")
    return errors


# ================================================================== checkpoint

@dataclass
class Checkpoint:
    """Sổ ghi từng câu đã xong. Append-only: không bao giờ sửa dòng đã ghi.

    Vì sao append-only thay vì ghi đè cả file mỗi lần: ghi đè mà chết giữa
    chừng là mất SẠCH tiến độ, đúng thứ checkpoint sinh ra để tránh. Dòng cuối
    hỏng (chết đúng lúc đang ghi) thì chỉ mất một câu, và lúc đọc bỏ qua được.
    """

    path: Path
    _f = None

    def doc(self) -> dict[str, dict]:
        """query_id → bản ghi. Dòng hỏng bị bỏ qua, không làm sập cả lần chạy."""
        if not self.path.exists():
            return {}
        ra: dict[str, dict] = {}
        for so, dong in enumerate(self.path.read_text(encoding="utf-8").splitlines(), 1):
            if not dong.strip():
                continue
            try:
                rec = json.loads(dong)
                ra[rec["query_id"]] = rec        # dòng sau đè dòng trước: lần chạy mới thắng
            except Exception:
                print(f"  [cảnh báo] checkpoint dòng {so} hỏng, bỏ qua")
        return ra

    def mo(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._f = self.path.open("a", encoding="utf-8")

    def ghi(self, rec: dict) -> None:
        """Ghi MỘT câu và ép xuống đĩa ngay.

        flush() + fsync() chứ không để Python/OS tự quyết: buffer mặc định giữ
        vài KB trong RAM — mất điện là mất đúng phần chưa kịp ghi, tức là mất
        thứ vừa tốn nhiều thời gian nhất để tính ra.
        """
        assert self._f is not None, "phải gọi mo() trước"
        self._f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self._f.flush()
        os.fsync(self._f.fileno())

    def dong(self) -> None:
        if self._f is not None:
            self._f.close()
            self._f = None


def _answer_to_dict(a: Answer) -> dict:
    return {"video_id": a.video_id, "frame_ids": list(a.frame_ids),
            "answer_text": a.answer_text, "keyframe_id": a.keyframe_id}


def _answer_from_dict(d: dict) -> Answer:
    return Answer(video_id=d["video_id"], frame_ids=tuple(d["frame_ids"]),
                  answer_text=d.get("answer_text"), keyframe_id=d.get("keyframe_id"))


# ================================================================ thanh tiến độ

class ThanhTienDo:
    """Thanh tiến độ + ETA, tự viết để KHÔNG thêm phụ thuộc mới.

    tqdm có sẵn trên máy này nhưng KHÔNG có trong backend/requirements.txt —
    dựa vào nó là mở đường cho "chạy được ở máy tôi" đúng đêm trước hạn nộp.
    Vẽ ra stderr để `python run.py ... > ket_qua.txt` vẫn thấy tiến độ trên
    màn hình mà file không dính ký tự điều khiển.
    """

    def __init__(self, tong: int, rong: int = 28):
        self.tong, self.rong, self.xong, self.t0 = tong, rong, 0, time.perf_counter()

    def _thoi_gian(self, giay: float) -> str:
        return f"{int(giay // 60):d}:{int(giay % 60):02d}"

    def cap_nhat(self, nhan: str = "") -> None:
        self.xong += 1
        ti_le = self.xong / self.tong if self.tong else 1.0
        day = int(self.rong * ti_le)
        troi = time.perf_counter() - self.t0
        con = (troi / self.xong) * (self.tong - self.xong) if self.xong else 0.0
        sys.stderr.write(
            f"\r  [{'█' * day}{'·' * (self.rong - day)}] {self.xong}/{self.tong} "
            f"({ti_le:5.1%})  đã {self._thoi_gian(troi)} · còn ~{self._thoi_gian(con)}  {nhan[:28]:<28}"
        )
        sys.stderr.flush()

    def xuong_dong(self) -> None:
        sys.stderr.write("\n")
        sys.stderr.flush()


class Log:
    """Ghi ra file (đầy đủ, có traceback) và ra màn hình (ngắn gọn).

    Hai mức khác nhau có chủ đích: màn hình đang bận vẽ thanh tiến độ nên chỉ
    nhận một dòng mỗi sự kiện; file mới là thứ đọc lại lúc truy nguyên nhân —
    mà lúc đó cần NGUYÊN traceback, không phải "PIPELINE HỎNG: KeyError".
    """

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.f = path.open("a", encoding="utf-8")
        self.path = path

    def __call__(self, dong: str, ra_man_hinh: bool = True, chi_tiet: str = "") -> None:
        dau = datetime.now().strftime("%H:%M:%S")
        self.f.write(f"[{dau}] {dong}\n")
        if chi_tiet:
            self.f.write(chi_tiet.rstrip() + "\n")
        self.f.flush()
        if ra_man_hinh:
            sys.stderr.write("\r" + " " * 100 + "\r")   # xoá thanh tiến độ trước khi in
            print(dong, flush=True)

    def dong_lai(self) -> None:
        self.f.close()


# ================================================================== preflight

def _preflight(log: "Log", bo_qua: bool) -> bool:
    """Deep check (W0.3) TRƯỚC khi tốn câu nào. True = được phép chạy tiếp.

    Vì sao đáng làm: đo thật hôm nay — Milvus rỗng, nhưng mỗi truy vấn vẫn nạp
    CLIP rồi search rồi mới hỏng, mất 29s cho câu đầu và lặp lại y hệt cho từng
    câu còn lại. Với 50 câu là 25 phút để biết một điều mà `/health` nói trong
    nửa giây. Hỏng cả lô vì cùng MỘT nguyên nhân thì phải phát hiện MỘT lần.
    """
    if bo_qua:
        log("[preflight] --skip-health: bỏ qua kiểm tra hệ thống", ra_man_hinh=False)
        return True
    try:
        from backend.api.health import deep_check, format_report

        kq = deep_check()
    except Exception as e:
        # Bản thân deep check hỏng KHÔNG được chặn đường nộp — nó là thứ phụ trợ.
        log(f"[preflight] không chạy được deep check ({e}) — vẫn chạy tiếp")
        return True

    log(format_report(kq), ra_man_hinh=kq["status"] != "ok")
    if kq["status"] == "down":
        log("\nDỪNG: có thành phần CRITICAL chết (xem bảng trên). Chạy lô bây giờ "
            "chỉ tạo ra 100% câu hỏng vì cùng một nguyên nhân.\n"
            "  Sửa xong chạy lại, hoặc ép chạy bằng --skip-health.")
        return False
    return True


# ============================================================ giải MỘT truy vấn

def giai_mot_query(q: dict, total: int) -> tuple[list[Answer], dict]:
    """Compatibility wrapper; định tuyến thật chỉ còn ở `solve_query()`."""
    result = solve_query(q, total=total)
    return result.answers, result.compatibility_metadata()


# ======================================================================= main

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Orchestrator đầy đủ (A6.0): file truy vấn → file nộp")
    ap.add_argument("--queries", required=True, help="file .json hoặc .jsonl")
    ap.add_argument("--out", required=True, help="thư mục ghi file nộp + checkpoint + log")
    ap.add_argument("--answers", type=int, default=ANSWERS_PER_QUERY,
                    help=f"số dòng mỗi truy vấn (mặc định {ANSWERS_PER_QUERY} — luật BTC)")
    ap.add_argument("--only", help="chỉ chạy các query_id này, ngăn cách bởi dấu phẩy")
    ap.add_argument("--fresh", action="store_true",
                    help="BỎ QUA checkpoint cũ, chạy lại từ đầu")
    ap.add_argument("--zip", action="store_true",
                    help="gói thêm submission.zip theo chuẩn BTC")
    ap.add_argument(
        "--qa-submission-policy",
        choices=(*QA_SUBMISSION_POLICIES, "all"),
        default="semantic",
        help=("chiến lược answer Q&A: semantic (cũ), exact, robust; "
              "all chỉ tạo các zip để so sánh, không chạy lại retrieval"),
    )
    ap.add_argument("--skip-health", action="store_true",
                    help="bỏ qua deep check đầu lượt (chỉ khi biết rõ mình đang làm gì)")
    args = ap.parse_args()

    if args.qa_submission_policy == "all" and not args.zip:
        ap.error("--qa-submission-policy all cần --zip để không ghi đè CSV của các chiến lược")

    all_queries = _doc_queries(Path(args.queries))
    queries = all_queries
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    log = Log(out_dir / LOG_NAME)
    ck = Checkpoint(out_dir / CHECKPOINT_NAME)
    current_runtime_fingerprint = build_runtime_fingerprint()

    if args.only:
        chon = {s.strip() for s in args.only.split(",") if s.strip()}
        la = chon - {q["query_id"] for q in all_queries}
        if la:
            log(f"[đầu vào] --only có query_id không tồn tại: {sorted(la)}")
            return 2
        queries = [q for q in all_queries if q["query_id"] in chon]

    # --- checkpoint: cái nào đã xong, cái nào hết hạn vì đề đã đổi
    cu = {} if args.fresh else ck.doc()
    xong: dict[str, dict] = {}
    het_han: list[str] = []
    # Luôn nạp checkpoint hợp lệ của TOÀN BỘ file query. `--only` chỉ giới hạn
    # câu cần compute, không được làm gói ZIP cuối mất các câu còn lại.
    for q in all_queries:
        rec = cu.get(q["query_id"])
        if not rec:
            continue
        if (
            rec.get("query_hash") != _query_hash(q)
            or rec.get("runtime_fingerprint") != current_runtime_fingerprint
        ):
            het_han.append(q["query_id"])
        else:
            xong[q["query_id"]] = rec

    can_chay = [q for q in queries if q["query_id"] not in xong]
    llm_errors = _llm_runtime_errors(can_chay)
    if llm_errors:
        for error in llm_errors:
            log(f"[cấu hình LLM] {error}")
        log("DỪNG trước preflight/search; chưa có API nào được gọi.")
        log.dong_lai()
        return 2

    log("=" * 72, ra_man_hinh=False)
    log(f"BẮT ĐẦU · {len(all_queries)} truy vấn"
        + (f" · compute --only {len(queries)} câu" if args.only else "")
        + f" · {args.answers} dòng/truy vấn · ra {out_dir}")
    if not _preflight(log, args.skip_health):
        log.dong_lai()
        return 1
    if xong:
        log(f"Checkpoint: {len(xong)} câu đã xong từ lần trước → bỏ qua")
    if het_han:
        log(f"Checkpoint HẾT HẠN cho {len(het_han)} câu (đề hoặc runtime đã đổi): "
            f"{', '.join(het_han[:5])}{'...' if len(het_han) > 5 else ''} → chạy lại")
    if args.fresh and cu:
        log("--fresh: bỏ qua toàn bộ checkpoint cũ")

    # --- vòng chạy chính
    ck.mo()
    trace_log = Checkpoint(out_dir / TRACE_NAME)
    trace_log.mo()
    hong: list[tuple[str, str]] = []
    bar = ThanhTienDo(len(can_chay)) if can_chay else None
    try:
        for q in can_chay:
            qid, task = q["query_id"], q["task_type"]
            t0 = time.perf_counter()
            try:
                answers, phu = giai_mot_query(q, args.answers)
            except KeyboardInterrupt:
                # Ctrl-C không phải lỗi của truy vấn: dừng hẳn, giữ nguyên tiến
                # độ đã ghi, để lần sau chạy tiếp đúng chỗ đang dở.
                log("\nDỪNG theo yêu cầu (Ctrl-C) — tiến độ đã ghi vào checkpoint")
                break
            except Exception as e:
                giay = time.perf_counter() - t0
                if isinstance(e, SolveQueryError):
                    failed_run = e.query_run
                else:
                    failure_class = (
                        "missing_evidence" if task == "QA"
                        else "trake_order" if task == "TRAKE"
                        else "retrieval_miss"
                    )
                    failed_run = failure_trace(
                        q, e, failure_class=failure_class,
                        timings={"total_seconds": round(giay, 6)},
                    )
                trace_log.ghi(failed_run.to_trace_dict())
                hong.append((qid, f"{type(e).__name__}: {e}"))
                log(f"  ✗ {qid:<12} {task:<6} HỎNG sau {giay:5.1f}s — {type(e).__name__}: {e}",
                    chi_tiet=traceback.format_exc())
                if bar:
                    bar.cap_nhat(f"✗ {qid}")
                continue

            giay = time.perf_counter() - t0
            query_run = phu.get("query_run")
            if not isinstance(query_run, QueryRun):
                # Chỉ dùng cho compatibility test doubles/caller cũ. Đường thật
                # luôn nhận QueryRun đầy đủ từ solve_query().
                query_run = QueryRun(
                    query_id=qid,
                    task_type=task,
                    answers=answers,
                    query_plan={
                        "query_vi": q.get("query_vi"),
                        "query_en": q.get("query_en"),
                        "event_descs": q.get("event_descs"),
                        "n_events": q.get("n_events"),
                    },
                    timings={"total_seconds": round(giay, 6)},
                    runtime_fingerprint=current_runtime_fingerprint,
                    answer_text=phu.get("answer_text"),
                    qa_trace=phu.get("qa_trace"),
                    n_trake=phu.get("n_trake"),
                )
            trace_log.ghi(query_run.to_trace_dict())
            # "Thật" = có keyframe_id (bằng chứng thật), phần còn lại là dòng đệm.
            that = sum(1 for a in answers if a.keyframe_id is not None)
            rec = {
                "query_id": qid, "task_type": task, "query_hash": _query_hash(q),
                "runtime_fingerprint": query_run.runtime_fingerprint,
                "n_answers": len(answers), "n_real": that, "seconds": round(giay, 2),
                "at": datetime.now().isoformat(timespec="seconds"),
                "answer_text": phu.get("answer_text"),
                "qa_trace": phu.get("qa_trace"),
                "n_trake": phu.get("n_trake"),
                "answers": [_answer_to_dict(a) for a in answers],
            }
            ck.ghi(rec)
            xong[qid] = rec
            log(f"  ✓ {qid:<12} {task:<6} {that:>3} thật/{len(answers)} dòng · "
                f"{len({a.video_id for a in answers}):>3} video · {giay:5.1f}s"
                + (f' · answer="{phu["answer_text"]}"' if phu.get("answer_text") else ""),
                ra_man_hinh=False)
            if bar:
                bar.cap_nhat(f"✓ {qid}")
    finally:
        ck.dong()
        trace_log.dong()
        if bar:
            bar.xuong_dong()

    # --- dựng bài nộp từ CHECKPOINT (không phải từ RAM): lần chạy tiếp cũng
    # phải ra đủ bộ file, kể cả những câu xong từ lần trước.
    subs, n_trake = [], {}
    export_queries = all_queries
    missing_for_full_export = [
        q["query_id"] for q in export_queries if q["query_id"] not in xong
    ]
    if missing_for_full_export:
        log(
            "\nDỪNG XUẤT GÓI: checkpoint chưa đủ toàn bộ query trong file. "
            "Không ghi ZIP/CSV subset vì có thể bị nộp nhầm như một submission đầy đủ. Thiếu: "
            + ", ".join(missing_for_full_export[:20])
        )
        if hong:
            log(
                f"Chạy lại câu hỏng: python run.py --queries {args.queries} "
                f"--out {args.out} --only {','.join(qid for qid, _ in hong[:20])}"
            )
        log.dong_lai()
        return 1

    for q in export_queries:
        rec = xong.get(q["query_id"])
        if not rec:
            continue
        subs.append(QuerySubmission(
            query_id=rec["query_id"], task_type=rec["task_type"],
            answers=tuple(_answer_from_dict(d) for d in rec["answers"]),
        ))
        if rec.get("n_trake"):
            n_trake[rec["query_id"]] = rec["n_trake"]

    if not subs:
        log("\nKHÔNG có truy vấn nào thành công — không ghi file nào.")
        log.dong_lai()
        return 1

    policies = QA_SUBMISSION_POLICIES if args.qa_submission_policy == "all" else (
        args.qa_submission_policy,
    )
    try:
        for policy in policies:
            # Chỉ Q&A nhận portfolio answer; KIS/TRAKE giữ nguyên tuple Answer
            # và mọi frame index đã do allocator quyết định.
            policy_subs = [
                QuerySubmission(
                    sub.query_id,
                    sub.task_type,
                    tuple(apply_qa_submission_policy(list(sub.answers), policy))
                    if sub.task_type == "QA" else sub.answers,
                )
                for sub in subs
            ]
            if args.zip:
                zip_name = (
                    "submission.zip" if len(policies) == 1 else f"submission_{policy}.zip"
                )
                zip_path, loi_file = write_submission_zip(
                    policy_subs, out_dir, zip_name=zip_name,
                    expect_answers=args.answers, expected_n=n_trake or None)
                log(f"\n[{policy}] Đã ghi {len(policy_subs)} file nộp + gói {zip_path}")
            else:
                da_ghi, loi_file = write_submissions(
                    policy_subs, out_dir, expect_answers=args.answers,
                    expected_n=n_trake or None)
                log(f"\n[{policy}] Đã ghi {len(da_ghi)} file nộp vào {out_dir}/")
            if loi_file:
                raise ValueError(" · ".join(str(issue) for issue in loi_file))
    except ValueError as e:
        log(f"\nVALIDATOR TỪ CHỐI — không ghi file nào:\n{e}")
        log.dong_lai()
        return 1

    if loi_file:
        log("Lỗi khi đọc lại file đã ghi:")
        for i in loi_file[:10]:
            log(f"  {i}")
        log.dong_lai()
        return 1

    # --- tổng kết: nói to phần THIẾU, đừng để nó lẫn vào dòng "đã ghi N file"
    thieu = [q["query_id"] for q in all_queries if q["query_id"] not in xong]
    tong_that = sum(r["n_real"] for r in xong.values())
    log(f"Tổng dòng có bằng chứng thật: {tong_that} / {len(subs) * args.answers}")

    rong = [qid for qid, r in xong.items() if r["n_real"] == 0]
    if rong:
        log(f"⚠️  {len(rong)} câu KHÔNG có dòng nào mang bằng chứng thật "
            f"({', '.join(rong[:5])}{'...' if len(rong) > 5 else ''}) — "
            "thường là chưa nạp index. KHÔNG nộp file của những câu này.")

    if hong:
        log(f"\n⚠️  {len(hong)} truy vấn HỎNG — KHÔNG có file nộp cho chúng:")
        for qid, msg in hong[:20]:
            log(f"    {qid:<12} {msg}")
        log(f"    Traceback đầy đủ: {log.path}")
        log(f"    Chạy lại riêng chúng: python run.py --queries {args.queries} "
            f"--out {args.out} --only {','.join(qid for qid, _ in hong[:20])}")
    if thieu and not hong:
        log(f"\n⚠️  {len(thieu)} truy vấn chưa chạy (dừng giữa chừng): "
            f"{', '.join(thieu[:5])}{'...' if len(thieu) > 5 else ''}")

    try:
        from backend.llm.adapter import print_usage

        print_usage()
    except Exception:
        pass

    log("XONG." if not (hong or thieu) else "XONG (có phần thiếu — xem trên).")
    log.dong_lai()
    return 1 if (hong or thieu) else 0


if __name__ == "__main__":
    raise SystemExit(main())
