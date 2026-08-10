# tests/conftest.py — tiện ích dùng chung cho test D0.2
# Cụ thể: `video_id` và `n_frames` lấy từ video_info; `frame_id` lấy từ cột
#   frame_idx_corrected của frame_map — đúng những con số mà slot allocator (D3.1)
#   sẽ đưa xuống khi chạy thật.

from __future__ import annotations

from functools import lru_cache

import pytest

from backend.export import QuerySubmission, all_video_ids, n_frames_of
from data.config.submit_format import Answer


@lru_cache(maxsize=1)
def _frame_map():
    """frame_map.parquet — nguồn frame_id thật. Nạp 1 lần cho cả phiên test."""
    import pandas as pd

    from backend.export import REPO_ROOT

    duong_dan = REPO_ROOT / "data" / "derived" / "frame_map.parquet"
    if not duong_dan.exists():
        pytest.skip(f"Chưa có {duong_dan} — cần Data Factory giao frame_map trước")

    # Vì sao dò tên cột: BUILD_TASKS đặt tên `btc_kf_ordinal` / `frame_idx_corrected`,
    # còn frame_map.parquet thực tế sinh ra `btc_ordinal` / `frame_idx` (đã bù offset).
    # Hardcode tên theo spec → ArrowInvalid, cả bộ test đỏ trên data thật.
    df = pd.read_parquet(duong_dan)
    doi_ten = {}
    for chuan, ung_vien in (
        ("btc_ordinal", ("btc_ordinal", "btc_kf_ordinal")),
        ("frame_idx", ("frame_idx", "frame_idx_corrected")),
    ):
        thay = next((c for c in ung_vien if c in df.columns), None)
        if thay is None:
            pytest.skip(f"frame_map.parquet thiếu cột {ung_vien} (đang có: {list(df.columns)})")
        doi_ten[thay] = chuan
    return df.rename(columns=doi_ten)[["video_id", "btc_ordinal", "frame_idx"]]


@lru_cache(maxsize=8)
def frames_of(video_id: str) -> tuple[int, ...]:
    """Mọi frame_idx THẬT của một video, sắp tăng dần.

    Input: video_id. Output: tuple frame_idx (đã bù offset) theo thứ tự keyframe.
    """
    df = _frame_map()
    s = df[df.video_id == video_id].sort_values("btc_ordinal")
    return tuple(int(x) for x in s.frame_idx)


@pytest.fixture(scope="session")
def real_videos() -> list[tuple[str, int]]:
    """3 video thật, mỗi cái đủ keyframe để dựng 100 câu trả lời khác nhau."""
    du = []
    for v in all_video_ids():
        if len(frames_of(v)) >= 104:  # 100 dòng + 4 frame cho TRAKE
            du.append((v, n_frames_of(v)))
        if len(du) == 3:
            break
    assert len(du) == 3, "Cần ít nhất 3 video có ≥104 keyframe để dựng dữ liệu test"
    return du


def build_sub(
    video_id: str,
    n_frames: int,
    *,
    task_type: str = "KIS",
    query_id: str = "q001",
    count: int = 100,
    n_trake: int = 4,
) -> QuerySubmission:
    """Sinh một QuerySubmission HỢP LỆ từ frame_id THẬT của video đó.

    Input: video có thật + n_frames của nó (chỉ dùng để assert).
    Output: QuerySubmission qua được cả 7 luật.
    Bất biến:
      - mọi frame_id đều là frame_idx_corrected có thật trong frame_map
      - TRAKE luôn tăng dần ngặt (lấy các keyframe liên tiếp, vốn đã tăng dần)
    """
    frames = frames_of(video_id)
    assert len(frames) >= count + n_trake, f"{video_id} không đủ keyframe"
    assert frames[-1] < n_frames, f"{video_id} có keyframe vượt quá độ dài video"

    answers = []
    for i in range(count):
        if task_type == "TRAKE":
            # N keyframe LIÊN TIẾP — thật, và tự nhiên đã tăng dần ngặt
            chon = frames[i : i + n_trake]
        else:
            chon = (frames[i],)
        answers.append(Answer(
            video_id=video_id,
            frame_ids=chon,
            answer_text="5" if task_type == "QA" else None,
        ))
    return QuerySubmission(query_id, task_type, tuple(answers))


def replace_answer(sub: QuerySubmission, i: int, **thay_doi) -> QuerySubmission:
    """Đổi một câu trả lời ở vị trí i (0-based), trả bản sao.

    QuerySubmission và Answer đều bất biến nên không sửa tại chỗ được —
    lợi ích phụ: test này không thể làm bẩn dữ liệu của test khác.
    """
    import dataclasses

    ds = list(sub.answers)
    ds[i] = dataclasses.replace(ds[i], **thay_doi)
    return dataclasses.replace(sub, answers=tuple(ds))


def cat_bot(sub: QuerySubmission, n: int) -> QuerySubmission:
    """Giữ lại n câu trả lời đầu — dùng để tạo ca thiếu dòng."""
    import dataclasses

    return dataclasses.replace(sub, answers=sub.answers[:n])


@pytest.fixture
def kis(real_videos):
    vid, n = real_videos[0]
    return build_sub(vid, n, task_type="KIS", query_id="kis_001")


@pytest.fixture
def qa(real_videos):
    vid, n = real_videos[1]
    return build_sub(vid, n, task_type="QA", query_id="qa_001")


@pytest.fixture
def trake(real_videos):
    vid, n = real_videos[2]
    return build_sub(vid, n, task_type="TRAKE", query_id="trake_001")


@pytest.fixture
def all_subs(kis, qa, trake):
    """Bài nộp đủ ba dạng bài."""
    return [kis, qa, trake]


def rules_of(issues) -> set[str]:
    """Tập slug luật bị vi phạm — test bám vào slug, không bám vào câu chữ."""
    return {i.rule for i in issues}
