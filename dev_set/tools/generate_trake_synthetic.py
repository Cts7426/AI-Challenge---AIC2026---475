# dev_set/tools/generate_trake_synthetic.py — mở rộng bộ đề TRAKE tổng hợp
#
# ===== Vì sao cần =====
# Dev-set TRAKE hiện chỉ có 2 câu (TR01/TR02, người viết tay) — không đủ để
# kiểm chứng bất kỳ thay đổi công thức xếp hạng nào (kế hoạch
# reports/trake_hardening.md). Không có khả năng xem video trực tiếp để viết
# thêm câu như người thật — bù bằng cách SINH câu tổng hợp có GT CHẮC CHẮN
# ĐÚNG: chọn N shot thật (ranh giới frame chính xác từ shots.parquet — không
# có sai số), gọi VLM (llm() với ảnh) tự mô tả từng shot bằng 1 câu ngắn theo
# đúng văn phong TR01/TR02.
#
# ⚠️ GHI RÕ RỦI RO: câu do VLM tự mô tả khung hình nó THẤY có thể "dễ" hơn câu
# thi thật (văn phong sát điều CLIP dễ nhận ra vì cùng nguồn gốc mô hình) —
# KHÔNG ghi đè/trộn vào tune_trake.jsonl (2 câu người viết = chuẩn vàng). Ghi
# riêng data/split "synth" — mọi báo cáo phải tách riêng kết quả 2 tập, không
# gộp mập mờ.
#
# Chạy (cần ANTHROPIC_API_KEY hoặc LLM_BACKEND phù hợp):
#   python -m dev_set.tools.generate_trake_synthetic

from __future__ import annotations

import json
import random
from pathlib import Path

import pandas as pd

from backend.llm.adapter import llm, print_usage

ROOT_DIR = Path(__file__).resolve().parents[2]
DERIVED_DIR = ROOT_DIR / "data" / "derived"
QUERIES_OUT = ROOT_DIR / "dev_set" / "queries" / "synth_trake.jsonl"
GT_OUT = ROOT_DIR / "dev_set" / "ground_truth" / "synth_gt.jsonl"

# Video đã dùng cho TR01/TR02 (người viết) — không chọn lại để tránh trùng GT.
EXCLUDE_VIDEO_IDS = {"L26_V380", "L26_V458"}

# (video_id cụ thể chọn tay bằng seed cố định bên dưới, n_events mỗi câu) —
# đa dạng N để bao phủ nhiều độ dài DP khác nhau, giống phổ N thật (2-6 theo
# comment TRAKE_CANDIDATES_PER_EVENT trong search_weights.py).
N_EVENTS_PLAN = [2, 3, 3, 4, 4, 5]
MIN_SHOT_DURATION_S = 1.0  # loại shot quá ngắn — dễ là cắt cảnh giả/nhiễu
RANDOM_SEED = 42

CAPTION_PROMPT = (
    "Đây là MỘT khung hình trong một video nấu ăn tiếng Việt. Mô tả NGẮN GỌN "
    "(một câu ngắn, không quá 10 từ) hành động hoặc sự vật CHÍNH đang diễn ra "
    "trong ảnh — đúng văn phong: 'sườn non chặt khúc trong tô', 'cà chua được "
    "cắt', 'đổ nước vào nồi trên bếp'.\n"
    "HARD RULE: CHỈ mô tả những gì THẤY được trong ảnh, KHÔNG suy đoán ngữ "
    "cảnh trước/sau, không thêm chi tiết không có trong ảnh, không dùng câu "
    "đầy đủ chủ ngữ 'trong ảnh là...' — chỉ trả về đúng mô tả ngắn."
)


def _pick_candidate_videos(n: int) -> list[str]:
    shots = pd.read_parquet(DERIVED_DIR / "shots.parquet", columns=["video_id"])
    kf = pd.read_parquet(DERIVED_DIR / "keyframes.parquet", columns=["video_id"])
    l26_shots = set(shots[shots.video_id.str.startswith("L26")].video_id.unique())
    l26_kf = set(kf[kf.video_id.str.startswith("L26")].video_id.unique())
    candidates = sorted((l26_shots & l26_kf) - EXCLUDE_VIDEO_IDS)
    rng = random.Random(RANDOM_SEED)
    rng.shuffle(candidates)
    return candidates[:n]


INTRO_SKIP_SECONDS = 20.0  # bỏ toàn bộ shot trong N giây đầu — đo thật (chạy
                            # lần 1, N_INTRO_SHOTS_SKIP=3 shot): CẢ 6/6 video
                            # vẫn cho event 1 là "Logo Món Ngon Mỗi Ngày nền đỏ
                            # với đôi đũa" GẦN Y HỆT NHAU dù đã bỏ 3 shot đầu —
                            # bumper logo của chương trình dài hơn ước lượng
                            # ban đầu (còn thấy ở frame 258 ~ giây thứ 10). Ép
                            # theo GIÂY (không phải số shot) vì bumper là thời
                            # lượng cố định của ĐỊNH DẠNG chương trình, ổn định
                            # hơn số shot (thay đổi theo tốc độ cắt cảnh từng
                            # video). Logo lặp lại y hệt nhau cũng làm event 1
                            # KHÔNG PHÂN BIỆT được giữa các video cùng show —
                            # đúng loại nhiễu sẽ làm sai lệch phép đo xếp hạng
                            # (mục tiêu chính của bộ đề tổng hợp này).


def _pick_event_shots(video_id: str, n_events: int, fps: float,
                       shots_df: pd.DataFrame) -> list[dict]:
    """Chọn n_events shot cách đều theo shot_seq trong video, loại shot quá
    ngắn và mọi shot trong INTRO_SKIP_SECONDS giây đầu (logo/bumper chương
    trình). Trả list dict {shot_id, start_frame, end_frame} ĐÚNG thứ tự thời
    gian (shot_seq tăng dần — đây LÀ ranh giới frame thật, GT không có sai số)."""
    g = shots_df[shots_df.video_id == video_id].sort_values("shot_seq")
    g = g[g.duration_s >= MIN_SHOT_DURATION_S]
    g = g[g.start_frame >= INTRO_SKIP_SECONDS * fps]
    if len(g) < n_events:
        return []
    # linspace theo vị trí trong danh sách đã lọc — tránh dồn hết vào đầu/cuối
    idxs = [round(i * (len(g) - 1) / (n_events - 1)) for i in range(n_events)]
    idxs = sorted(set(idxs))
    if len(idxs) < n_events:
        return []
    rows = g.iloc[idxs]
    return [
        {"shot_id": r.shot_id, "start_frame": int(r.start_frame), "end_frame": int(r.end_frame)}
        for r in rows.itertuples()
    ]


def _keyframe_image_for_shot(shot_id: str, kf_df: pd.DataFrame) -> Path | None:
    """1 shot → đường dẫn ảnh keyframe gần GIỮA shot nhất (đại diện tốt hơn
    frame đầu/cuối, hay là khung chuyển cảnh còn nhoè)."""
    rows = kf_df[kf_df.shot_id == shot_id].sort_values("frame_idx")
    if rows.empty:
        return None
    mid = rows.iloc[len(rows) // 2]
    path = DERIVED_DIR / mid.path
    return path if path.exists() else None


def _caption_frame(image_path: Path) -> str:
    text = llm(CAPTION_PROMPT, images=[str(image_path)], effort="low", max_tokens=100)
    return text.strip().strip('"').strip("'")


def main() -> None:
    shots_df = pd.read_parquet(
        DERIVED_DIR / "shots.parquet",
        columns=["video_id", "shot_id", "shot_seq", "start_frame", "end_frame", "duration_s"],
    )
    kf_df = pd.read_parquet(DERIVED_DIR / "keyframes.parquet",
                             columns=["shot_id", "frame_idx", "path"])
    video_info_df = pd.read_parquet(DERIVED_DIR / "video_info.parquet",
                                     columns=["video_id", "fps_num", "fps_den"])
    fps_of = {r.video_id: r.fps_num / r.fps_den for r in video_info_df.itertuples()}

    videos = _pick_candidate_videos(len(N_EVENTS_PLAN))
    print(f"Video ứng viên đã chọn ({len(videos)}): {videos}")

    queries: list[dict] = []
    gts: list[dict] = []
    q_no = 0

    for video_id, n_events in zip(videos, N_EVENTS_PLAN):
        fps = fps_of.get(video_id, 25.0)
        event_shots = _pick_event_shots(video_id, n_events, fps, shots_df)
        if not event_shots:
            print(f"  ⚠️ bỏ {video_id}: không đủ {n_events} shot hợp lệ (>= "
                  f"{MIN_SHOT_DURATION_S}s)")
            continue

        captions: list[str] = []
        ok = True
        for es in event_shots:
            img = _keyframe_image_for_shot(es["shot_id"], kf_df)
            if img is None:
                print(f"  ⚠️ bỏ {video_id}: shot {es['shot_id']} không có ảnh keyframe local")
                ok = False
                break
            try:
                cap = _caption_frame(img)
            except Exception as e:
                print(f"  ⚠️ bỏ {video_id}: llm() lỗi khi caption {img.name}: {e}")
                ok = False
                break
            if not cap:
                print(f"  ⚠️ bỏ {video_id}: caption rỗng cho {img.name}")
                ok = False
                break
            captions.append(cap)
        if not ok or len(captions) != n_events:
            continue

        q_no += 1
        qid = f"STR{q_no:02d}"
        query_vi = " . ".join(captions)
        # ⚠️ `split` phải là "tune" hay "holdout" (dev_set/tools/schema.py::Query
        # chỉ chấp nhận 2 giá trị này, KHÔNG có "synth") — nhãn "tune" ở ĐÂY chỉ
        # để qua được validation của dataclass, KHÔNG liên quan tới việc file này
        # nằm ở dev_set/queries/synth_trake.jsonl và được nạp qua
        # `run_evaluation.py --split synth` (CLI arg chọn TÊN FILE, không đọc
        # field này). Query dataclass KHÔNG nhận field lạ (source/gt_video_id) —
        # metadata đó chỉ in ra console, không ghi vào JSON nộp cho evaluator.
        queries.append({
            "query_id": qid, "task_type": "TRAKE", "query_vi": query_vi,
            "split": "tune", "n_events": n_events, "event_descs": captions,
        })
        gts.append({
            "query_id": qid, "task_type": "TRAKE", "video_id": video_id,
            "frames": [
                {"start": es["start_frame"], "end": es["end_frame"], "desc": cap}
                for es, cap in zip(event_shots, captions)
            ],
        })
        print(f"  ✓ {qid} ({video_id}, {n_events} sự kiện): {query_vi}")

    if not queries:
        print("\n❌ Không sinh được câu nào — kiểm tra ANTHROPIC_API_KEY/LLM_BACKEND "
              "và dữ liệu keyframe local.")
        return

    QUERIES_OUT.parent.mkdir(parents=True, exist_ok=True)
    GT_OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(QUERIES_OUT, "w", encoding="utf-8") as f:
        for q in queries:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")
    with open(GT_OUT, "w", encoding="utf-8") as f:
        for g in gts:
            f.write(json.dumps(g, ensure_ascii=False) + "\n")

    print(f"\n📦 Đã ghi {len(queries)} câu TRAKE tổng hợp:")
    print(f"   {QUERIES_OUT}")
    print(f"   {GT_OUT}")
    print_usage()


if __name__ == "__main__":
    main()
