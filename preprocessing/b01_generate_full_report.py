import pandas as pd
from pathlib import Path

DATA_DIR = Path("data")
DERIVED_DIR = DATA_DIR / "derived"
REPORTS_DIR = Path("reports")
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

def generate_report():
    df_full = pd.read_parquet(DERIVED_DIR / "full_verification.parquet")
    df_old = pd.read_parquet(DERIVED_DIR / "video_offset.parquet")
    
    lines = ["# Báo Cáo Xác Thực Toàn Diện Keyframe (Full Verification)\n"]
    
    # A. Tổng quan
    total_kfs = len(df_full)
    verdict_counts = df_full["verdict"].value_counts()
    lines.append("## A. Tổng Quan")
    lines.append(f"- **Tổng số keyframe đã kiểm:** {total_kfs:,}")
    lines.append("- **Phân bố kết quả:**")
    for verdict, count in verdict_counts.items():
        pct = count / total_kfs * 100
        lines.append(f"  - `{verdict}`: {count:,} ({pct:.2f}%)")
    lines.append("")
    
    # B. Bảng theo video
    lines.append("## B. Thống Kê Theo Video")
    lines.append("| Video ID | Số KF | % Match | % Shifted | % Weak | % No Match | % Static | Offset Chủ Đạo | Ổn Định |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    
    video_stats = []
    drift_alarms = []
    
    for vid, group in df_full.groupby("video_id"):
        n_kf = len(group)
        counts = group["verdict"].value_counts()
        match_pct = counts.get("match", 0) / n_kf * 100
        shifted_pct = counts.get("shifted", 0) / n_kf * 100
        weak_pct = (counts.get("weak_match", 0) + counts.get("weak_shifted", 0)) / n_kf * 100
        nomatch_pct = counts.get("no_match", 0) / n_kf * 100
        static_pct = counts.get("static_ambiguous", 0) / n_kf * 100
        
        # Dominant offset among non-ambiguous
        non_ambiguous = group[group["verdict"].isin(["match", "shifted", "weak_match", "weak_shifted"])]
        if len(non_ambiguous) > 0:
            dominant_offset = non_ambiguous["best_offset"].mode().iloc[0]
            stable = (non_ambiguous["best_offset"] == dominant_offset).mean() >= 0.95
        else:
            dominant_offset = 0
            stable = False
            
        video_stats.append({
            "video_id": vid,
            "n_kf": n_kf,
            "dominant_offset": dominant_offset,
            "stable": stable,
            "shifted_pct": shifted_pct
        })
            
        lines.append(f"| {vid} | {n_kf} | {match_pct:.1f}% | {shifted_pct:.1f}% | {weak_pct:.1f}% | {nomatch_pct:.1f}% | {static_pct:.1f}% | {dominant_offset} | {'✅' if stable else '❌'} |")
        
        # C. Drift check
        if n_kf >= 10 and not stable:
            group = group.sort_values("frame_idx_raw")
            chunks = np.array_split(group, 10)
            chunk_offsets = []
            for chunk in chunks:
                non_amb_chunk = chunk[chunk["verdict"].isin(["match", "shifted", "weak_match", "weak_shifted"])]
                if len(non_amb_chunk) > 0:
                    chunk_offsets.append(str(non_amb_chunk["best_offset"].mode().iloc[0]))
                else:
                    chunk_offsets.append("?")
            if chunk_offsets[0] != "?" and chunk_offsets[-1] != "?" and chunk_offsets[0] != chunk_offsets[-1]:
                drift_alarms.append(f"- **{vid}**: Offsets qua 10 phần: " + " -> ".join(chunk_offsets))
                
    lines.append("")
    
    # C. Drift
    lines.append("## C. Báo Động Trôi Offset Giữa Video")
    if drift_alarms:
        lines.append("Phát hiện các video sau có hiện tượng đứt gãy/trôi offset theo thời gian:")
        lines.extend(drift_alarms)
    else:
        lines.append("Không phát hiện video nào có offset đầu và cuối khác biệt rõ rệt qua 10 temporal chunks.")
    lines.append("")
    
    # D. Danh sách no_match
    lines.append("## D. Danh Sách Keyframe No_Match")
    df_nomatch = df_full[df_full["verdict"] == "no_match"]
    if len(df_nomatch) > 0:
        lines.append(f"Có {len(df_nomatch)} keyframe không khớp ở mọi offset (MSE >= 50):")
        lines.append("| KF_ID | Ordinal | Best Offset | MSE Best |")
        lines.append("|---|---|---|---|")
        for _, row in df_nomatch.head(50).iterrows():
            lines.append(f"| {row['kf_id']} | {row['btc_kf_ordinal']} | {row['best_offset']} | {row['mse_best']:.1f} |")
        if len(df_nomatch) > 50: lines.append("... (chỉ hiển thị 50 dòng đầu)")
    else:
        lines.append("Tốt! Không có keyframe nào bị `no_match`.")
    lines.append("")
    
    # E. 8 video ambiguous
    lines.append("## E. Kết Luận Về 8 Video Ambiguous (Mẫu Cũ)")
    old_ambiguous = df_old[df_old["offset_status"] == "ambiguous"]["video_id"].tolist()
    lines.append(f"Các video mập mờ ở đợt trước: {', '.join(old_ambiguous)}")
    lines.append("| Video ID | Offset Chủ Đạo Mới | Trạng Thái Ổn Định |")
    lines.append("|---|---|---|")
    for vid in old_ambiguous:
        stat = next((s for s in video_stats if s["video_id"] == vid), None)
        if stat:
            lines.append(f"| {vid} | {stat['dominant_offset']} | {'✅' if stat['stable'] else '❌'} |")
    lines.append("")
    
    # F & G. So sánh với mẫu
    lines.append("## G. Đối Chiếu Kết Luận Mẫu (3-KF) vs Toàn Diện")
    lines.append("| Video ID | Offset Mẫu | Offset Chủ Đạo Thực | % Shifted (Thực) | Kết Luận Mẫu |")
    lines.append("|---|---|---|---|---|")
    old_shifted_videos = []
    for _, row in df_old.iterrows():
        vid = row["video_id"]
        old_offset = row["offset"]
        old_status = row["offset_status"]
        stat = next((s for s in video_stats if s["video_id"] == vid), None)
        if not stat: continue
        
        real_dominant = stat["dominant_offset"]
        real_shifted_pct = stat["shifted_pct"]
        
        if old_offset == 1:
            old_shifted_videos.append((vid, old_offset, real_dominant, real_shifted_pct))
            
        correct = "Đúng" if (old_status != "ambiguous" and old_offset == real_dominant) else "Sai/Khác"
        if old_status == "ambiguous": correct = "Trước mập mờ"
        if correct != "Đúng" or old_offset == 1:
            lines.append(f"| {vid} | {old_offset} | {real_dominant} | {real_shifted_pct:.1f}% | {correct} |")
    lines.append("")
    
    # H. Phân bố kf_offset toàn cục
    lines.append("## H. Phân Bố kf_offset Toàn Cục")
    best_offset_counts = df_full["best_offset"].value_counts()
    lines.append(f"**Phân bố offset thắng cuộc của tất cả {total_kfs:,} keyframes:**")
    for offset, count in best_offset_counts.items():
        pct = count / total_kfs * 100
        lines.append(f"- Offset `{offset}`: {count:,} ({pct:.2f}%)")
        
    shifted_kfs = total_kfs - best_offset_counts.get(0, 0)
    lines.append(f"\n**Tỉ lệ keyframe đứt gãy (khác 0):** {shifted_kfs/total_kfs*100:.2f}%")
    
    broken_videos = [s for s in video_stats if s["shifted_pct"] > 50]
    if broken_videos:
        lines.append("\n**Các video có tỉ lệ đứt gãy vượt 50%:**")
        for s in broken_videos:
            lines.append(f"- {s['video_id']} ({s['shifted_pct']:.1f}%)")
    else:
        lines.append("\n**Không có video nào có tỉ lệ đứt gãy > 50% (lệch thật ở mức toàn video).** Mọi sai số offset đều mang tính cục bộ (đứt gãy lẻ tẻ).")
        
    # I. Keyframes Bị Bỏ Qua (is_after_jump)
    lines.append("## I. Keyframe Đo Sau Khi Jump (is_after_jump)")
    if "is_after_jump" in df_full.columns:
        jumped_kfs = df_full[df_full["is_after_jump"] == True]
        lines.append(f"Có {len(jumped_kfs):,} keyframes được đo trong khoảng thời gian decoder chưa ổn định (chỉ số độ tin cậy thấp).")
        lines.append(f"Tỉ lệ: {len(jumped_kfs) / total_kfs * 100:.2f}%")
        
        # J. Duplicate Frames
        lines.append("\n## J. Video Có Duplicate Frames")
        if "has_duplicate_frames" in df_full.columns:
            dup_videos = df_full[df_full["has_duplicate_frames"] == True]["video_id"].unique()
            lines.append(f"Phát hiện {len(dup_videos)} video có lượng lớn khung hình bị nhân đôi liên tiếp (MSE < 1 vượt 30%):")
            for v in dup_videos:
                lines.append(f"- {v}")
        else:
            lines.append("Không có thông tin về duplicate frames.")
    
    with open(REPORTS_DIR / "b01_full_verification.md", "w") as f:
        f.write("\n".join(lines))
        
    print(f"Report generated at {REPORTS_DIR / 'b01_full_verification.md'}")

if __name__ == "__main__":
    import numpy as np
    generate_report()
