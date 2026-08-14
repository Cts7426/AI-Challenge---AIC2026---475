import sys
import pandas as pd
import numpy as np
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "preprocessing"))
from common.frame_map import load_frame_map

REPORT_PATH = ROOT_DIR / "reports" / "shot_keyframe_coverage.md"
SHOTS_PATH = ROOT_DIR / "data" / "derived" / "shots.parquet"
VIDEO_INFO_PATH = ROOT_DIR / "data" / "derived" / "video_info.parquet"
FRAME_MAP_PATH = ROOT_DIR / "data" / "derived" / "frame_map.parquet"

def main():
    if not SHOTS_PATH.exists():
        print(f"Không tìm thấy {SHOTS_PATH}. Cần chạy merge_shots_parts.py trước.")
        sys.exit(1)
        
    df_shots = pd.read_parquet(SHOTS_PATH)
    df_vi = pd.read_parquet(VIDEO_INFO_PATH)
    
    # Prefix
    df_vi['prefix'] = df_vi['video_id'].str[:3]
    df_shots['prefix'] = df_shots['video_id'].str[:3]
    
    # Load frame_map (1 dòng = 1 keyframe BTC, đã có frame_idx chuẩn)
    df_fm = load_frame_map()
    
    print("Đang join shots với frame_map...")
    # Ta cần biết mỗi shot có bao nhiêu keyframe BTC rơi vào nó.
    # df_shots có start_frame và end_frame. 
    # Do số lượng shot không quá lớn (~200k), ta dùng merge/cắt khoảng thay vì iterrows
    
    # Cách nhanh nhất: sort frame_map theo video_id, frame_idx. Sort shots theo video_id, start_frame.
    # Dùng pd.merge_asof
    df_fm_sorted = df_fm[['video_id', 'frame_idx', 'kf_id']].sort_values(['video_id', 'frame_idx'])
    df_shots_sorted = df_shots.sort_values(['video_id', 'start_frame'])
    
    # Đếm số lượng keyframe trong mỗi shot
    # Vì pd.merge_asof chỉ map 1-1, để đếm nhiều ta có thể dùng groupby / pd.cut, hoặc đơn giản là merge
    # Cách tốt hơn: groupby video_id, dùng searchsorted
    kf_counts = []
    
    df_fm_grp = df_fm_sorted.groupby('video_id')
    for vid, grp in df_shots_sorted.groupby('video_id'):
        if vid in df_fm_grp.groups:
            fm_v = df_fm_grp.get_group(vid)['frame_idx'].values
            starts = grp['start_frame'].values
            ends = grp['end_frame'].values
            
            # Đếm số phần tử trong fm_v nằm trong đoạn [starts[i], ends[i]]
            idx_start = np.searchsorted(fm_v, starts, side='left')
            idx_end = np.searchsorted(fm_v, ends, side='right')
            counts = idx_end - idx_start
            kf_counts.extend(counts)
        else:
            kf_counts.extend([0] * len(grp))
            
    df_shots_sorted['kf_count'] = kf_counts
    df_s = df_shots_sorted
    
    # Has dup
    has_dup_map = df_fm.groupby('video_id')['has_duplicate_frames'].any()
    df_s['has_dup'] = df_s['video_id'].map(has_dup_map).fillna(False)
    
    # FPS
    df_s = df_s.merge(df_vi[['video_id', 'fps_num', 'fps_den']], on='video_id', how='left')
    df_s['fps'] = (df_s['fps_num'] / df_s['fps_den']).round(2)
    
    lines = []
    lines.append("# B1.2: Shot & Keyframe Coverage Report\n")
    lines.append(f"**Tổng số video đã segment:** {df_s['video_id'].nunique()}")
    lines.append(f"**Tổng số shot:** {len(df_s):,}\n")
    
    # 1. % shot có 0 / 1 / >=2 kf
    total = len(df_s)
    c0 = len(df_s[df_s['kf_count'] == 0])
    c1 = len(df_s[df_s['kf_count'] == 1])
    c2 = len(df_s[df_s['kf_count'] >= 2])
    
    lines.append("## Phân bố Keyframe trong Shot\n")
    lines.append("| Số keyframe BTC | Số lượng shot | Tỷ lệ % |")
    lines.append("|---|---|---|")
    lines.append(f"| 0 keyframe | {c0:,} | {c0/total*100:.1f}% |")
    lines.append(f"| 1 keyframe | {c1:,} | {c1/total*100:.1f}% |")
    lines.append(f"| ≥2 keyframe | {c2:,} | {c2/total*100:.1f}% |\n")
    
    # Tách theo Prefix
    lines.append("### Phân tách theo Prefix\n")
    lines.append("| Prefix | Tổng shot | 0 kf | 1 kf | ≥2 kf |")
    lines.append("|---|---|---|---|---|")
    for pref, grp in df_s.groupby('prefix'):
        t = len(grp)
        p0 = len(grp[grp['kf_count'] == 0]) / t * 100
        p1 = len(grp[grp['kf_count'] == 1]) / t * 100
        p2 = len(grp[grp['kf_count'] >= 2]) / t * 100
        lines.append(f"| {pref} | {t:,} | {p0:.1f}% | {p1:.1f}% | {p2:.1f}% |")
    lines.append("\n")
    
    # Tách theo FPS
    lines.append("### Phân tách theo FPS\n")
    lines.append("| FPS | Tổng shot | 0 kf | 1 kf | ≥2 kf |")
    lines.append("|---|---|---|---|---|")
    for fps_val, grp in df_s.groupby('fps'):
        t = len(grp)
        p0 = len(grp[grp['kf_count'] == 0]) / t * 100
        p1 = len(grp[grp['kf_count'] == 1]) / t * 100
        p2 = len(grp[grp['kf_count'] >= 2]) / t * 100
        lines.append(f"| {fps_val} | {t:,} | {p0:.1f}% | {p1:.1f}% | {p2:.1f}% |")
    lines.append("\n")
    
    # Tách theo has_dup
    lines.append("### Phân tách theo Frame nhân đôi (has_duplicate_frames)\n")
    lines.append("| Duplicate | Tổng shot | 0 kf | 1 kf | ≥2 kf |")
    lines.append("|---|---|---|---|---|")
    for dup_val, grp in df_s.groupby('has_dup'):
        t = len(grp)
        p0 = len(grp[grp['kf_count'] == 0]) / t * 100
        p1 = len(grp[grp['kf_count'] == 1]) / t * 100
        p2 = len(grp[grp['kf_count'] >= 2]) / t * 100
        lines.append(f"| {dup_val} | {t:,} | {p0:.1f}% | {p1:.1f}% | {p2:.1f}% |")
    lines.append("\n")
    
    # Phân tích shot 0 keyframe
    lines.append("## Phân tích Shot 0 Keyframe (Mù/Blind Spots)\n")
    df_0 = df_s[df_s['kf_count'] == 0]
    total_blind_s = df_0['duration_s'].sum()
    lines.append(f"- **Số lượng:** {len(df_0):,} shot")
    lines.append(f"- **Tổng thời lượng bỏ trống:** {total_blind_s/3600:.1f} giờ ({total_blind_s:.0f}s)")
    lines.append(f"- **Độ dài trung bình:** {df_0['duration_s'].mean():.2f}s")
    lines.append(f"- **Độ dài tối đa:** {df_0['duration_s'].max():.2f}s")
    
    lines.append("\n**Phân bố độ dài của shot 0 keyframe:**\n")
    bins = [0, 0.5, 1, 2, 5, 10, 30, 60, 999]
    labels = ['<0.5s', '0.5-1s', '1-2s', '2-5s', '5-10s', '10-30s', '30-60s', '>60s']
    df_0_bins = pd.cut(df_0['duration_s'], bins=bins, labels=labels)
    counts = df_0_bins.value_counts(sort=False)
    lines.append("| Khoảng độ dài | Số lượng shot | Tỷ lệ % |")
    lines.append("|---|---|---|")
    for lab, c in counts.items():
        if c > 0:
            lines.append(f"| {lab} | {c:,} | {c/len(df_0)*100:.1f}% |")
    lines.append("\n")
    
    # Mật độ BTC cho CẢ 873 video
    lines.append("## Mật độ Keyframe BTC trên toàn kho (873 video)\n")
    lines.append("Dựa trên `video_info.parquet` và `frame_map.parquet` để đo tần suất BTC trích keyframe.\n")
    
    # Tính duration cho mọi video trong df_vi
    df_vi['duration_s'] = df_vi['n_frames'] / (df_vi['fps_num'] / df_vi['fps_den'])
    # Đếm số kf mỗi video
    kf_cnt = df_fm.groupby('video_id').size().reset_index(name='n_kf')
    df_vi_kf = df_vi.merge(kf_cnt, on='video_id', how='left').fillna(0)
    
    lines.append("| Prefix | Số video | Tổng thời lượng (giờ) | Tổng keyframe | Mật độ (KF/phút) | Khoảng cách trung bình (s) |")
    lines.append("|---|---|---|---|---|---|")
    
    for pref, grp in df_vi_kf.groupby('prefix'):
        n_vid = len(grp)
        dur_h = grp['duration_s'].sum() / 3600
        n_k = grp['n_kf'].sum()
        kf_per_min = n_k / (grp['duration_s'].sum() / 60) if grp['duration_s'].sum() > 0 else 0
        dist_s = 60 / kf_per_min if kf_per_min > 0 else 0
        lines.append(f"| {pref} | {n_vid} | {dur_h:.1f} | {n_k:,.0f} | {kf_per_min:.2f} | {dist_s:.2f} |")
        
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
        
    print(f"✅ Đã ghi báo cáo tại {REPORT_PATH}")

if __name__ == "__main__":
    main()
