import json
import argparse
import sys
from pathlib import Path
import pandas as pd
import cv2
import numpy as np
from dev_set.tools.schema import Query, GroundTruthKIS, GroundTruthQA, GroundTruthTRAKE, GroundTruth
from backend.export.exporter import n_frames_of
from dev_set.tools.video_utils import extract_frame_exact

def load_jsonl(path: Path):
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f]

def check_gt():
    parser = argparse.ArgumentParser(description="Validate Ground Truth and Queries for Dev Set")
    parser.add_argument("--split", choices=["tune", "holdout"], default="tune")
    args = parser.parse_args()

    q_paths = [
        Path(f"dev_set/queries/{args.split}_kis.jsonl"),
        Path(f"dev_set/queries/{args.split}_qa.jsonl"),
        Path(f"dev_set/queries/{args.split}_trake.jsonl")
    ]
    gt_path = Path(f"dev_set/ground_truth/{args.split}_gt.jsonl")

    queries_dict = {}
    for p in q_paths:
        for row in load_jsonl(p):
            try:
                q = Query(**row)
                if q.query_id in queries_dict:
                    print(f"LỖI: Trùng query_id {q.query_id}")
                    sys.exit(1)
                queries_dict[q.query_id] = q
            except Exception as e:
                print(f"LỖI parse Query {row.get('query_id')}: {e}")
                sys.exit(1)

    print(f"Đã tải {len(queries_dict)} queries.")

    if not gt_path.exists():
        print(f"Chưa có GT file tại {gt_path}. Hoàn thành kiểm tra Query.")
        return

    # Load shots
    shots_df = None
    shots_path = Path("data/derived/shots.parquet")
    if shots_path.exists():
        shots_df = pd.read_parquet(shots_path)
    else:
        print("CẢNH BÁO: Không tìm thấy data/derived/shots.parquet để kiểm tra cửa sổ shot.")

    preview_dir = Path("dev_set/gt_preview")
    preview_dir.mkdir(parents=True, exist_ok=True)

    errors = 0
    warnings = 0

    gt_rows = load_jsonl(gt_path)
    seen_gt_ids: set[str] = set()

    for row in gt_rows:
        qid = row.get("query_id")
        if qid in seen_gt_ids:
            print(f"LỖI: GT có query_id {qid} bị trùng — dòng sau sẽ đè lặng lẽ dòng trước ở run_evaluation.py")
            errors += 1
            continue
        seen_gt_ids.add(qid)
        
        if qid not in queries_dict:
            print(f"LỖI: GT có query_id {qid} nhưng không tồn tại trong Queries!")
            errors += 1
            continue
            
        q = queries_dict[qid]
        try:
            row_clean = {k: v for k, v in row.items() if k != "task_type"}
            if q.task_type == "KIS":
                gt = GroundTruthKIS(**row_clean)
                windows = [(gt.frame_start, gt.frame_end)]
                if gt.frame_end - gt.frame_start > 300:
                    print(f"CẢNH BÁO: KIS {qid} có cửa sổ > 300 frame")
                    warnings += 1
            elif q.task_type == "QA":
                gt = GroundTruthQA(**row_clean)
                windows = [(gt.frame_start, gt.frame_end)]
            elif q.task_type == "TRAKE":
                gt = GroundTruthTRAKE(**row_clean)
                if len(gt.frames) != q.n_events:
                    print(
                        f"LỖI: {qid} Query.n_events={q.n_events} nhưng GT có "
                        f"{len(gt.frames)} cửa sổ — rscore_trake sẽ luôn = 0 nếu không sửa"
                    )
                    errors += 1
                windows = [(w["start"], w["end"]) for w in gt.frames]
                for w in windows:
                    if w[1] - w[0] > 30:
                        print(f"CẢNH BÁO: TRAKE {qid} có cửa sổ > 30 frame")
                        warnings += 1
        except Exception as e:
            print(f"LỖI parse GT {qid}: {e}")
            errors += 1
            continue

        # Check bounds
        vid = gt.video_id
        try:
            nb_frames = n_frames_of(vid)
            for w in windows:
                if w[1] >= nb_frames:
                    print(f"LỖI: {qid} frame_end {w[1]} vượt quá nb_frames_decoded ({nb_frames}) của {vid}")
                    errors += 1
        except Exception as e:
            print(f"LỖI không tra được frames của video {vid}: {e}")
            errors += 1

        # Check shot boundary
        if shots_df is not None:
            vid_shots = shots_df[shots_df["video_id"] == vid]
            for w in windows:
                # Tìm xem có shot nào bao trọn w không
                enclosing = vid_shots[(vid_shots["start_frame"] <= w[0]) & (vid_shots["end_frame"] >= w[1])]
                if enclosing.empty:
                    print(f"CẢNH BÁO: {qid} cửa sổ {w} không nằm gọn trong 1 shot!")
                    warnings += 1

        # Generate contact sheet
        vid_path = Path(f"data/video/{vid}.mp4")
        if vid_path.exists():
            try:
                out_path = preview_dir / f"{qid}.jpg"
                if not out_path.exists():
                    f1 = extract_frame_exact(str(vid_path), windows[0][0])
                    f2 = extract_frame_exact(str(vid_path), windows[0][1])
                    if f1 is not None and f2 is not None:
                        # concat horizontal
                        h1, w1 = f1.shape[:2]
                        h2, w2 = f2.shape[:2]
                        # resize f2 to match f1 height if needed
                        if h1 != h2:
                            f2 = cv2.resize(f2, (int(w2 * h1 / h2), h1))
                        contact = np.concatenate((f1, f2), axis=1)
                        cv2.imwrite(str(out_path), contact)
            except Exception as e:
                print(f"CẢNH BÁO: Lỗi trích xuất contact sheet cho {qid}: {e}")
                warnings += 1

    print(f"--- THỐNG KÊ ---")
    print(f"Tổng GT: {len(gt_rows)}")
    print(f"Lỗi (Errors): {errors}")
    print(f"Cảnh báo (Warnings): {warnings}")
    
    if errors > 0:
        print("=> KIỂM TRA GT THẤT BẠI. Sửa lỗi trước khi chạy tiếp.")
        sys.exit(1)
    else:
        print("=> KIỂM TRA GT THÀNH CÔNG.")

if __name__ == "__main__":
    check_gt()
