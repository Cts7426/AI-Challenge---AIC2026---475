# backend/slot/allocator.py — D3.1: top-K shot → ĐÚNG 100 câu trả lời đã xếp hạng
#
# Đây là nơi CUỐI CÙNG còn biết `frame_idx` thật. Submit_format.py
# chỉ ghi ra con số nhận được. Nghĩa là nếu file này cấp sai frame thì không còn
# chốt chặn nào phía sau.
#
# Ba câu hỏi file này trả lời:
#   1. 100 slot chia cho shot nào, mỗi shot mấy slot?  → data/config/slot_budget.py
#   2. Thứ tự nộp ra sao?                              → xen kẽ, mục "vòng tròn" bên dưới
#   3. Trong một shot thì lấy frame nào?               → _frames_of_shot(), 4 mức ưu tiên
#
# Vì sao XEN KẼ mà không gom theo shot?
# → R@1 + R@5 = 40% điểm. Gom 8 slot đầu vào shot hạng 1, shot đó
#   sai là mất trắng cả R@1 lẫn R@5. Xen kẽ thì 5 slot đầu là 5 shot khác nhau.
#
# Nguồn dữ liệu — đều là thứ Data Factory đã giao, file này KHÔNG tự tính lại:
#   shots.parquet                      → biên [start_frame, end_frame] của shot
#   backend.indexing.frame_map         → keyframe_id → frame_idx
#   video_info.parquet qua export      → n_frames, để kẹp frame trong [0, n_frames)
#
# Chạy thử (từ thư mục gốc repo):
#     python -m backend.slot --demo

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache

from backend.export import REPO_ROOT, n_frames_of
from data.config.slot_budget import (
    ANSWERS_PER_QUERY,
    SHOT_EDGE_INSET,
    SLOT_BUDGET,
    TRAKE_DEFAULT_N,
    budget_per_shot,
)
from data.config.submit_format import Answer

SHOTS_PATH = REPO_ROOT / "data" / "derived" / "shots.parquet"


@dataclass(frozen=True)
class ShotHit:
    """Một shot ứng viên do tầng search đưa xuống.

    `score` chỉ dùng để XẾP HẠNG, không so với ngưỡng nào — cosine CLIP thực tế chỉ
    quanh 0.2–0.3, đặt ngưỡng cứng là lọc sạch kết quả đúng (CLAUDE.md bất biến 6).

    `best_keyframe_id` = keyframe điểm cao nhất trong shot. Đây là frame mình thực sự
    CÓ BẰNG CHỨNG, nên nó luôn được cấp slot đầu tiên của shot — không phải điểm giữa
    shot tính toán ra.
    """

    shot_id: str
    score: float
    best_keyframe_id: str | None = None


# ------------------------------------------------------- dữ liệu của Data Factory

@lru_cache(maxsize=1)
def _shots() -> dict[str, tuple[str, int, int]]:
    """shot_id → (video_id, start_frame, end_frame). Đọc đĩa đúng 1 lần cho cả tiến trình.

    Ra: dict 100.810 shot. Biên là bao gồm cả hai đầu (end_frame nằm trong shot).
    """
    from backend.export.exporter import _read_columns

    df = _read_columns(
        SHOTS_PATH, ["shot_id", "video_id", "start_frame", "end_frame"], "Công Lý (B1.1)"
    )
    return {
        r.shot_id: (r.video_id, int(r.start_frame), int(r.end_frame))
        for r in df.itertuples(index=False)
    }


def _frame_of_keyframe(keyframe_id: str) -> int | None:
    """keyframe_id → frame_idx thật, hoặc None nếu không có trong frame_map.

    Dùng thẳng hàm của Công Lý (`backend/indexing/frame_map.py`) chứ không tự đọc
    parquet: bảng đó có bù offset, tự đọc lại là mở đường cho hai nguồn sự thật.

    Trả None thay vì raise: một keyframe lạ chỉ làm mất mức ưu tiên ① của một shot,
    không đáng làm hỏng cả bài nộp. Các mức sau vẫn cấp đủ frame.
    """
    from backend.indexing.frame_map import load_frame_map

    return load_frame_map().get(keyframe_id)


# --------------------------------------------------- chọn frame trong MỘT shot

def _spread_evenly(a: int, b: int, m: int) -> list[int]:
    """m điểm rải đều trên đoạn [a, b], gồm cả hai đầu. m<=0 → rỗng, m==1 → điểm giữa."""
    if m <= 0 or b < a:
        return []
    if m == 1:
        return [(a + b) // 2]
    return [a + round(i * (b - a) / (m - 1)) for i in range(m)]


def _segment_bounds(start: int, end: int, k: int, m: int) -> tuple[int, int]:
    """Đoạn thứ k trong m phần bằng nhau của [start, end]. k đếm từ 0.

    Vào: biên shot · chỉ số đoạn · tổng số đoạn. Ra: biên đoạn con, gồm cả hai đầu.
    Bất biến: luôn trả về đoạn có ít nhất 1 frame, và các đoạn không chồng lấn nhau.

    Dùng khi một video có ÍT shot ứng viên hơn số khoảnh khắc TRAKE cần. Xem
    `_allocate_trake` để biết vì sao chia đoạn chứ không dùng lại nguyên shot.
    """
    if m <= 1:
        return start, end
    span = end - start + 1
    a = start + span * k // m
    b = start + span * (k + 1) // m - 1
    return (a, b) if b >= a else (a, a)


def _frames_of_shot(
    start: int, end: int, quota: int, best_frame: int | None, n_frames_video: int
) -> Iterator[int]:
    """Máy phát frame của một shot, xả theo ĐỘ TIN CẬY giảm dần.

    Input: biên shot (gồm cả hai đầu) · hạn mức slot · frame của keyframe tốt nhất · độ dài video.
    Output: iterator số nguyên, mỗi cái là một frame_id nộp được.
    Bất biến:
      - mọi giá trị nằm trong [0, n_frames_video)
      - KHÔNG BAO GIỜ phát lại một frame đã phát — bốn mức dưới chồng lấn nhau, khử
        trùng ngay tại đây để chỗ gọi không phải tự lo (TRAKE rút thẳng, không lọc)
      - chỉ cạn khi đã quét hết video → đây là thứ bảo đảm allocator luôn đủ 100 dòng

    Bốn mức:
      ① frame của keyframe điểm cao nhất — bằng chứng thật, luôn đi trước
      ② rải đều trong vùng đã thụt 10% mỗi đầu — tránh frame chuyển cảnh (mờ, lẫn cảnh)
      ③ mọi frame còn lại trong shot — khi ② hết vì shot được cấp nhiều slot
      ④ nới dần ra ngoài biên shot — chốt chặn cuối, chỉ chạm tới khi shot quá ngắn
    """
    emitted: set[int] = set()

    def emit(f: int) -> bool:
        """True nếu f hợp lệ và chưa phát bao giờ."""
        if 0 <= f < n_frames_video and f not in emitted:
            emitted.add(f)
            return True
        return False

    # ① — dùng nguyên vẹn, KHÔNG kẹp về biên shot. Nếu frame_map và shots.parquet
    # lệch nhau thì tin frame_map.
    has_level1 = best_frame is not None and emit(best_frame)
    if has_level1:
        yield best_frame

    span = end - start + 1
    inset = int(span * SHOT_EDGE_INSET)
    a, b = start + inset, end - inset
    if b < a:  # shot quá ngắn để thụt được → dùng nguyên shot
        a, b = start, end

    # ② — trừ 1 CHỈ KHI mức ① thật sự đã phát (có `best_frame` mà nó nằm ngoài
    # [0, n_frames) thì cũng coi như chưa phát). Trừ vô điều kiện thì shot không có
    # keyframe bị hụt một điểm rải, và slot cuối rơi xuống mức ③ — nơi quét từ `a`
    # lên nên nhả ra frame dính sát điểm rải đầu tiên (đo được: 415 rồi 416).
    # Một slot mua đúng cái đã có là một slot vứt đi.
    for f in _spread_evenly(a, b, max(quota - (1 if has_level1 else 0), 0)):
        if emit(f):
            yield f

    # ③ — vùng giữa trước (đáng tin hơn), rồi mới tới hai mép shot
    for f in list(range(a, b + 1)) + list(range(start, a)) + list(range(b + 1, end + 1)):
        if emit(f):
            yield f

    # ④ — nới đối xứng ra hai phía cho tới khi hết video
    for d in range(1, n_frames_video):
        exhausted = True
        for f in (end + d, start - d):
            if emit(f):
                yield f
                exhausted = False
            elif 0 <= f < n_frames_video:
                exhausted = False  # frame hợp lệ nhưng đã phát → vẫn còn đất, đi tiếp
        if exhausted:
            return


# ------------------------------------------------------------ vòng tròn xen kẽ

def _round_robin(
    sources: list[tuple[str, ShotHit]], quotas: list[int], needed: int
) -> list[tuple[str, int, str | None]]:
    """Rút frame theo VÒNG TRÒN: vòng r phát frame thứ r của mọi nguồn còn hạn mức.

    Input: list (video_id, ShotHit) đã xếp hạng · hạn mức từng nguồn · số dòng cần.
    Output: list (video_id, frame_id, keyframe_id) đúng `needed` phần tử, không trùng.
      `keyframe_id` chỉ khác None khi frame đó ĐÚNG LÀ frame của keyframe tốt nhất —
      các frame rải sâu không có keyframe nào nên không được gán bừa.
    Bất biến: hai phần tử đầu tiên đến từ hai nguồn KHÁC NHAU (khi có ≥2 nguồn).

    Khử trùng theo cặp (video_id, frame): cùng số frame ở hai video khác nhau là hai
    câu trả lời khác nhau, không phải trùng.

    Máy phát dựng LƯỜI: shot hạng > 31 nhận hạn mức 0 và thường không bao giờ được
    rút. Dựng sẵn cho chúng là tra `frame_map` thừa (search trả 500 shot → 469 lượt
    tra vô ích) và mở rộng bề mặt lỗi sang những shot không hề dùng tới.

    ⚠️ Chỉ MÁY PHÁT mới lười. `video_id` đã được chỗ gọi tra sẵn cho MỌI shot — tra
    biên shot chỉ là một phép tra dict, mà làm sớm thì `shot_id` lạ ở hạng 50 cũng nổ
    ngay lúc gọi. Lười cả phần đó thì lỗi "search và Data Factory dùng hai bản shot
    khác nhau" chỉ lộ khi shot đó tình cờ được rút — bắt lúc có lúc không còn tệ hơn
    là không bắt.
    """
    used: set[tuple[str, int]] = set()
    out: list[tuple[str, int, str | None]] = []
    gens: dict[int, tuple[Iterator[int], int | None]] = {}
    round_no = 0

    while len(out) < needed:
        progress = False
        for i, (video_id, hit) in enumerate(sources):
            if quotas[i] <= round_no:
                continue
            if i not in gens:  # lần đầu nguồn này được gọi tên → mới dựng
                gens[i] = _make_generator(hit, quotas[i])
            gen, best_frame = gens[i]
            for f in gen:  # bỏ qua frame đã dùng, lấy cái đầu tiên còn mới
                if (video_id, f) not in used:
                    used.add((video_id, f))
                    kf = hit.best_keyframe_id if f == best_frame else None
                    out.append((video_id, f, kf))
                    progress = True
                    break
            if len(out) >= needed:
                return out
        round_no += 1

        # Hết hạn mức mà chưa đủ dòng → nới hạn mức cho mọi nguồn rồi quay tiếp.
        # Xảy ra khi trùng lặp ăn mất slot; nới đều để giữ thế xen kẽ.
        if all(q <= round_no for q in quotas):
            quotas = [q + 1 for q in quotas]

        if not progress:
            raise RuntimeError(
                f"Cạn frame ở dòng {len(out)}/{needed}: tất cả video ứng viên đã hết "
                "frame chưa dùng. Cần thêm shot ứng viên từ tầng search."
            )

    return out


# -------------------------------------------------------------------- API chính

def allocate(
    hits: list[ShotHit],
    task_type: str = "KIS",
    *,
    answer_text: str | None = None,
    n_trake: int | None = None,
    total: int = ANSWERS_PER_QUERY,
    table: list[tuple[int, int]] = SLOT_BUDGET,
) -> list[Answer]:
    """Top-K shot → ĐÚNG `total` câu trả lời đã xếp hạng, sẵn sàng nộp.

    Input:
      hits        — shot ứng viên, tự sắp lại theo `score` giảm dần
      task_type   — "KIS" | "QA" | "TRAKE"
      answer_text — chỉ Q&A: câu trả lời do module Q&A (C-series) cấp
      n_trake     — chỉ TRAKE: số khoảnh khắc mỗi dòng; None → TRAKE_DEFAULT_N
    Output: list[Answer] dài ĐÚNG `total`, thứ tự phần tử = thứ hạng nộp.
    Bất biến:
      - KHÔNG BAO GIỜ trả ít hơn `total` dòng, kể cả khi chỉ có 1 shot ứng viên
      - không hai dòng nào trùng nhau
      - mọi frame_id là số nguyên trong [0, n_frames) của video nó
    """
    if not hits:
        raise ValueError("Không có shot ứng viên nào — tầng search phải trả ít nhất 1 shot")
    # NaN làm `sorted()` trả thứ tự TUỲ Ý mà không báo gì: NaN so sánh với mọi số
    # đều False, nên phép sắp xếp mất tính bắc cầu và thứ hạng shot thành ngẫu
    # nhiên. Bài nộp vẫn đủ 100 dòng, validator vẫn xanh — chỉ là xếp hạng vô
    # nghĩa. Đúng loại lỗi im lặng cả dự án đang phòng.
    #
    # Rủi ro có thật từ khi A2.2 dùng RRF: `1/(K + rank)` sinh NaN nếu rank hỏng.
    # Không dùng math.isnan() để khỏi vỡ khi score là kiểu số khác của numpy.
    nan_shots = [h.shot_id for h in hits if h.score != h.score]
    if nan_shots:
        raise ValueError(
            f"{len(nan_shots)} shot có score = NaN (ví dụ: {nan_shots[:3]}). Sắp xếp với NaN cho "
            "thứ tự tuỳ ý → thứ hạng shot thành ngẫu nhiên mà không có dấu hiệu gì. "
            "Tầng search phải lọc hoặc thay NaN trước khi đưa xuống."
        )
    if total < 1:
        # BUILD_TASKS D3.1: "KHÔNG BAO GIỜ trả < 100 dòng". Trả rỗng lặng lẽ khi tầng
        # trên truyền total sai (biến chưa gán, đọc config hỏng) là biến một bug nhỏ
        # thành BÀI NỘP TRẮNG mà không ai biết.
        raise ValueError(f"total phải >= 1, nhận {total}. Lúc thi luôn là {ANSWERS_PER_QUERY}.")
    if task_type == "QA" and not (answer_text or "").strip():
        raise ValueError("Q&A phải có answer_text — tầng slot không tự bịa câu trả lời")
    if task_type != "QA" and answer_text is not None:
        # Nuốt lặng một tham số truyền nhầm là đúng loại lỗi im lặng file này đang
        # phòng: người gọi tưởng đã đặt answer, validator D0.2 thì cấm KIS/TRAKE có
        # answer — hai bên cùng "đúng" mà kết quả không như ai nghĩ.
        raise ValueError(f"{task_type} không được có answer_text (chỉ Q&A mới có)")

    ranked = sorted(hits, key=lambda h: h.score, reverse=True)
    if task_type == "TRAKE":
        # `is None` chứ KHÔNG dùng `or`: n_trake=0 là số 0 falsy, `or` sẽ âm thầm
        # thay bằng 4 thay vì báo lỗi — đúng kiểu thay số lặng lẽ mà W0.2 cấm.
        n = TRAKE_DEFAULT_N if n_trake is None else n_trake
        # Validator của D0.2 (`_check_shape`) bắt TRAKE phải có ÍT NHẤT 2 frame. Không
        # chặn ở đây thì allocator đẻ ra thứ chính validator của mình từ chối.
        if n < 2:
            raise ValueError(f"TRAKE phải có ít nhất 2 khoảnh khắc, nhận n_trake={n}")
        return _allocate_trake(ranked, n, total, table)

    quotas = budget_per_shot(len(ranked), table, total)
    # `_video_of` cho MỌI shot ngay tại đây: shot_id lạ phải nổ lúc gọi allocate(),
    # không phải lúc đã rút được nửa danh sách.
    sources = [(_video_of(h), h) for h in ranked]
    return [
        Answer(video_id=vid, frame_ids=(f,), answer_text=answer_text, keyframe_id=kf)
        for vid, f, kf in _round_robin(sources, quotas, total)
    ]


def _video_of(h: ShotHit) -> str:
    return _bounds_of(h)[0]


def _bounds_of(h: ShotHit) -> tuple[str, int, int]:
    try:
        return _shots()[h.shot_id]
    except KeyError:
        raise KeyError(
            f"shot_id '{h.shot_id}' không có trong shots.parquet. "
            "Tầng search và Data Factory đang dùng hai bản shot khác nhau."
        ) from None


def _make_generator(
    h: ShotHit, quota: int, segment: tuple[int, int] | None = None
) -> tuple[Iterator[int], int | None]:
    """Dựng máy phát frame cho một ShotHit.

    Vào: ShotHit · hạn mức slot · `segment` = biên con thay cho cả shot (TRAKE dùng).
    Ra: (máy phát, frame của keyframe tốt nhất). Trả kèm `best_frame` để chỗ gọi
    biết dòng nào lấy đúng keyframe thật mà gắn `keyframe_id` — không phải đoán lại.

    `best_frame` bị bỏ khi nằm ngoài `segment`: một khoảnh khắc TRAKE ở đoạn giữa shot
    không được phép nhận keyframe của đoạn đầu, nếu không N khoảnh khắc lại chụm về
    cùng một chỗ — đúng cái đang sửa.
    """
    video_id, start, end = _bounds_of(h)
    best = _frame_of_keyframe(h.best_keyframe_id) if h.best_keyframe_id else None
    if segment is not None:
        start, end = segment
        if best is not None and not (start <= best <= end):
            best = None
    return _frames_of_shot(start, end, quota, best, n_frames_of(video_id)), best


# ------------------------------------------------------------------------ TRAKE

def _allocate_trake(
    ranked: list[ShotHit], n: int, total: int, table: list[tuple[int, int]]
) -> list[Answer]:
    """TRAKE v1 — mỗi dòng là MỘT video kèm N khoảnh khắc tăng dần ngặt.

    Vì sao xếp hạng theo VIDEO chứ không theo shot: sai video là 0 tuyệt đối, đúng
    video thì được điểm từng phần theo tỉ lệ khoảnh khắc khớp (tài liệu BTC, dạng bài TRAKE).
    Nên 100 dòng đầu nên phủ NHIỀU VIDEO, không phải nhiều phương án của một video.

    Cách dựng một dòng: lấy N shot điểm cao nhất của video đó, mỗi shot góp 1 frame,
    sắp tăng dần. Dòng thứ j của cùng một video lấy frame thứ j của từng shot.

    ⚠️ Video có ÍT shot hơn N → **chia mỗi shot thành nhiều đoạn**, mỗi khoảnh khắc
    lấy từ một đoạn riêng. KHÔNG được dựng nhiều máy phát trên cùng một biên: chúng
    xả ra dãy GIỐNG HỆT nhau (mỗi máy có bộ khử trùng riêng), rồi phép đẩy +1 ở
    `_trake_row` tách chúng thành N frame LIỀN NHAU — đo được `(34,35,36,37)`,
    tức 4 khoảnh khắc cách nhau 0,16 giây ở 25fps. Một chuỗi sự kiện TRAKE trải vài
    giây thì cụm đó giỏi lắm trúng 1/N cửa sổ đáp án.

    Không biết khoảnh khắc nằm đâu thì đoán TRẢI RA vẫn hơn đoán DỒN một chỗ: dồn
    thì hoặc trúng cả cụm hoặc trượt cả cụm, trải thì gần như chắc được vài phần.
    """
    by_video: dict[str, list[ShotHit]] = {}
    for h in ranked:
        by_video.setdefault(_video_of(h), []).append(h)

    videos = list(by_video)  # `ranked` đã sắp giảm dần nên thứ tự này là hạng video
    quotas = budget_per_shot(len(videos), table, total)

    generators: dict[str, list[Iterator[int]]] = {}
    for rank, vid in enumerate(videos):
        ds = by_video[vid]
        # Shot thứ j phải gánh mấy khoảnh khắc → chia nó ra ngần ấy đoạn
        n_segments = [(n - 1 - j) // len(ds) + 1 for j in range(len(ds))]
        used_per_shot: dict[int, int] = {}
        gens = []
        for i in range(n):
            j = i % len(ds)
            k = used_per_shot.get(j, 0)
            used_per_shot[j] = k + 1
            _, start, end = _bounds_of(ds[j])
            segment = _segment_bounds(start, end, k, n_segments[j]) if n_segments[j] > 1 else None
            gens.append(_make_generator(ds[j], quotas[rank], segment)[0])
        generators[vid] = gens

    rows: list[Answer] = []
    used: set[tuple[str, tuple[int, ...]]] = set()
    round_no = 0
    while len(rows) < total:
        progress = False
        for i, vid in enumerate(videos):
            if quotas[i] <= round_no:
                continue
            frames = _trake_row(generators[vid], n_frames_of(vid))
            if frames is None:
                continue
            key = (vid, frames)
            if key in used:
                continue
            used.add(key)
            rows.append(Answer(video_id=vid, frame_ids=frames))
            progress = True
            if len(rows) >= total:
                return rows
        round_no += 1
        if all(q <= round_no for q in quotas):
            quotas = [q + 1 for q in quotas]
        if not progress:
            raise RuntimeError(
                f"Cạn phương án TRAKE ở dòng {len(rows)}/{total} — cần thêm video ứng viên"
            )
    return rows


def _trake_row(gens: list[Iterator[int]], n_frames_video: int) -> tuple[int, ...] | None:
    """Rút một khoảnh khắc từ mỗi máy phát → tuple tăng dần NGẶT, hoặc None nếu cạn.

    Sau khi sắp tăng dần vẫn có thể có hai khoảnh khắc trùng frame (khi hai máy phát
    dùng chung một shot). Đẩy lên 1 đơn vị cho tách ra — thà lệch 1 frame còn hơn nộp
    dòng bị validator loại vì không tăng dần ngặt.
    """
    picked = []
    for g in gens:
        f = next(g, None)
        if f is None:
            return None
        picked.append(f)

    picked.sort()
    for i in range(1, len(picked)):
        if picked[i] <= picked[i - 1]:
            picked[i] = picked[i - 1] + 1
    if picked[-1] >= n_frames_video:  # đẩy tràn khỏi video → dòng này bỏ
        return None
    return tuple(picked)


# ------------------------------------------------------------------------- demo

def main() -> int:
    """CLI kiểm nhanh: dựng shot ứng viên giả từ shots.parquet THẬT rồi cấp phát.

    Không thay cho test — chỉ để người vận hành nhìn tận mắt 100 dòng trông thế nào
    mà không cần dựng cả Milvus/ES.
    """
    import argparse

    import pandas as pd

    from backend.export import QuerySubmission, format_issues, validate_submission

    ap = argparse.ArgumentParser(description="Cấp phát 100 slot từ shot thật (D3.1).")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--task", default="KIS", choices=("KIS", "QA", "TRAKE"))
    ap.add_argument("--shots", type=int, default=31, help="số shot ứng viên giả lập")
    args = ap.parse_args()
    if not args.demo:
        ap.print_help()
        return 0

    df = pd.read_parquet(SHOTS_PATH)
    # Lấy vài shot của nhiều video khác nhau — giống kết quả search thật hơn là
    # lấy liền một mạch các shot đầu của cùng một video
    df = df.groupby("video_id", sort=True).head(3).head(args.shots)
    hits = [
        ShotHit(r.shot_id, 1.0 - i * 0.01)
        for i, r in enumerate(df.itertuples(index=False))
    ]

    answers = allocate(hits, args.task, answer_text="5" if args.task == "QA" else None)
    print(f"== {len(answers)} dòng từ {len(hits)} shot ứng viên ==")
    for i, a in enumerate(answers[:8], 1):
        print(f"  hạng {i:>3}: {a.video_id}, {', '.join(map(str, a.frame_ids))}")
    print("  ...")

    sub = QuerySubmission("demo", args.task, tuple(answers))
    print(format_issues(validate_submission(sub)))
    return 0
