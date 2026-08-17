# backend/tasks/trake.py — C3.2/C4.4: TRAKE hợp nhất — DP theo VỊ TRÍ sự kiện
#
# ===== Vì sao KHÔNG nối N mô tả sự kiện thành 1 câu rồi search() 1 lần =====
# BUILD_TASKS gốc viết "ghép truy vấn tổng hợp" — nhưng CLIP chặn CỨNG 77 token
# (skill aic2026-retrieval bất biến 5: "nhiều câu ngắn encode riêng rồi hợp
# nhất, không nối thành đoạn dài"). Nối N≥3 mô tả sự kiện thường vượt 77 token,
# CLIP tự CẮT CỤT phần đuôi LẶNG LẼ — sự kiện cuối chuỗi biến mất khỏi vector mà
# không có cảnh báo nào (đúng loại lỗi "chạy được nhưng sai").
#
# ===== SỬA 16/08 — gộp stage1 (xếp hạng video) + stage2 (định vị N khoảnh khắc)
# thành MỘT hàm DP duy nhất =====
# Bản trước tách 2 giai đoạn: stage1 (`_best_per_video`) chỉ giữ 1 khung hình
# điểm cao nhất mỗi (video, sự kiện) rồi CỘNG điểm; stage2 (trake_fallback.py,
# đã XOÁ) search lại top-1 mỗi sự kiện TRONG video hạng nhất rồi vá thứ tự bằng
# "+1 liên tục". Hai lỗi của cách đó:
#   1. Order bonus hên xui: khung hình điểm cao nhất mỗi sự kiện hiếm khi tình
#      cờ tăng dần — video ĐÚNG thứ tự vẫn trượt bonus vì chỉ có đúng 1 khung
#      hình đại diện mỗi sự kiện để so.
#   2. Chỉ 1 ứng viên mỗi sự kiện (top-1) → không có phương án B khi nó phá vỡ
#      thứ tự, phải "+1 nudge"/rescale toàn chuỗi — phá bằng chứng thật.
#
# ⚠️ Vì sao KHÔNG gộp khung hình của MỌI sự kiện vào 1 rổ rồi tìm "dãy tăng dần
# tổng điểm cao nhất bất kỳ" (cách trực giác nhất, và cũng là cách một bản đề
# xuất sửa lỗi trước đó định làm): docs/contest.md chấm TRAKE THEO VỊ TRÍ —
#     R-Score = (1/N) · Σⱼ I(frame_j ∈ [sⱼ, eⱼ])
# — khung hình ở VỊ TRÍ j phải là bằng chứng của ĐÚNG sự kiện j, không phải bất
# kỳ khung hình nào miễn tăng dần. Gộp rổ sẽ cho phép khung hình mạnh của sự
# kiện 3 chiếmvị trí 1 — TÁI SINH đúng bug "sắp xếp lại theo giá trị" mà bản
# fallback cũ từng tìm ra và sửa (xem lịch sử git + tests/test_trake_fallback.py
# ::test_khong_sap_xep_lai_theo_gia_tri, bài học vẫn giữ nguyên ở đây).
#
# ===== Thiết kế mới =====
#   với mỗi sự kiện: search(event_i, group_by_shot=True) [KIS pipeline KHÔNG
#     SỬA] → giữ TOP-K khung hình mỗi video (không chỉ 1 — `_topk_per_video`)
#   với mỗi video ứng viên (xuất hiện ở >=1 sự kiện): `_align_events_in_video`
#     — DP chọn ĐÚNG 1 ứng viên cho mỗi vị trí j trong rổ CỦA SỰ KIỆN j, ràng
#     buộc frame tăng dần ngặt qua các vị trí ĐÃ CHỌN, tối đa tổng điểm.
#   DP phủ đủ CẢ N vị trí bằng bằng chứng thật, tăng dần ngặt → video_score =
#     tổng điểm DP × TRAKE_ORDER_BONUS, frame_ids = đúng dãy DP (không cần vá).
#   DP KHÔNG phủ đủ N (thiếu bằng chứng ở 1 số sự kiện, hoặc bằng chứng có mà
#     không thể xếp tăng dần cùng lúc) → video_score = tổng điểm CAO NHẤT từng
#     vị trí có bằng chứng (không bonus, giữ đúng Ý ĐỒ log-sum gốc: phủ rộng
#     thắng chói loá đơn lẻ) — vị trí thiếu được LẤP bằng nội suy tuyến tính
#     giữa 2 vị trí có bằng chứng gần nhất (`_fill_missing`, giữ nguyên từ bản
#     cũ, đã có test), rồi chốt an toàn tăng dần ngặt (`_repair_strictly_increasing`,
#     cũng giữ nguyên — chỉ còn là LƯỚI AN TOÀN cuối, không phải đường chính).
#
# Kết quả: trake_search() trả list[TrakeCandidate] — vừa có điểm để xếp hạng
# video (thay trake_stage1), vừa có ĐÚNG frame_ids định vị N khoảnh khắc (thay
# trake_stage2_fallback đã xoá) — trong CÙNG một lượt DP, không cần search lại
# lần 2 trong video đã chọn.
#
# Chạy thử (cần Docker ES+Milvus sống, ANTHROPIC_API_KEY hoặc LLM_BACKEND=local):
#   python -m backend.tasks.trake "cầu thủ sút phạt . thủ môn bay người cản phá . trọng tài thổi còi"

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from backend.export import n_frames_of
from backend.llm.adapter import llm
from backend.retrieval.search import search
from data.config.search_weights import (
    TRAKE_CANDIDATES_PER_EVENT,
    TRAKE_EVENT_SEARCH_POOL,
    TRAKE_MIN_FRAME_GAP,
    TRAKE_ORDER_BONUS,
)
from data.config.submit_format import Answer

TOP_VIDEOS = 10  # BUILD_TASKS C3.2: "trả top-10 video xếp hạng"

PARSE_EVENTS_SCHEMA = {
    "type": "object",
    "properties": {"events_vi": {"type": "array", "items": {"type": "string"}}},
    "required": ["events_vi"],
    "additionalProperties": False,
}


def parse_events(query_vi: str) -> list[str]:
    """Câu hỏi TRAKE → list N mô tả sự kiện, ĐÚNG thứ tự thời gian đề bài nói.

    N = len(kết quả) — KHÔNG đọc TRAKE_DEFAULT_N từ config. dev_set/tools/scoring
    (rscore_trake) cho 0 điểm TUYỆT ĐỐI nếu số khoảnh khắc nộp khác N thật của
    đề — đoán N sai là mất trắng dù mọi frame đều đúng.
    """
    raw = llm(
        "Câu sau mô tả MỘT CHUỖI các sự kiện liên tiếp xảy ra trong một video "
        "(bài toán TRAKE — định vị từng khoảnh khắc theo đúng thứ tự). Tách thành "
        "danh sách các mô tả sự kiện RIÊNG BIỆT, mỗi mô tả là MỘT khoảnh khắc "
        "ngắn, GIỮ NGUYÊN đúng thứ tự thời gian như câu gốc.\n"
        "HARD RULE: không thêm sự kiện không có trong câu gốc, không gộp 2 sự "
        "kiện làm 1, không đổi thứ tự. Mỗi mô tả đủ ngắn để dùng làm caption "
        "tìm kiếm ảnh (không quá 1 câu).\n\n"
        f"Câu hỏi: {query_vi}",
        json_schema=PARSE_EVENTS_SCHEMA,
    )
    events = [e.strip() for e in json.loads(raw)["events_vi"] if e and e.strip()]
    if len(events) < 2:
        raise ValueError(
            f"TRAKE cần ít nhất 2 sự kiện, parse_events() chỉ tách được {len(events)} "
            f"từ câu: '{query_vi}'. Kiểm tra câu hỏi có đúng là dạng bài TRAKE không."
        )
    return events


@dataclass(frozen=True)
class TrakeCandidate:
    """Kết quả định vị TRAKE cho MỘT video ứng viên — thay cho cặp
    (video_id, score) của trake_stage1 cũ + Answer riêng của trake_stage2_fallback cũ.

    frame_ids[j] / keyframe_ids[j] ứng với ĐÚNG sự kiện thứ j của câu hỏi (vị
    trí, không sort theo giá trị — xem cảnh báo đầu file).
    keyframe_ids[j] = None nghĩa là vị trí j không có bằng chứng thật trong
    video này, frame_ids[j] là giá trị NỘI SUY (debug/UI cần biết để không
    hiển thị nhầm thành "đã tìm thấy").
    """

    video_id: str
    score: float
    frame_ids: tuple[int, ...]
    keyframe_ids: tuple[str | None, ...]
    n_hit_events: int  # số vị trí có bằng chứng thật (trước nội suy)
    has_full_order: bool  # True: cả N vị trí có bằng chứng thật VÀ tăng dần ngặt


def _topk_per_video(hits: list[dict], k: int) -> dict[str, list[dict]]:
    """1 danh sách kết quả search() của MỘT sự kiện → mỗi video giữ tối đa `k`
    ứng viên điểm cao nhất (KHÔNG chỉ 1 khung hình như bản cũ `_best_per_video`
    — giữ nhiều để DP có phương án B khi ứng viên điểm cao nhất phá thứ tự).

    Bỏ hit không có frame_idx (chưa có trong Milvus — SearchHit ghi rõ có thể
    None): DP cần frame_idx thật để so sánh tăng dần, không đoán được.
    Trả về mỗi video 1 list đã sắp theo frame_idx TĂNG DẦN (không phải theo
    điểm) — `_align_events_in_video` duyệt tuyến tính theo thời gian.
    """
    by_video: dict[str, list[dict]] = {}
    for h in hits:
        if h.get("frame_idx") is None:
            continue
        by_video.setdefault(h["video_id"], []).append(h)

    out: dict[str, list[dict]] = {}
    for vid, lst in by_video.items():
        top = sorted(lst, key=lambda h: h["score"], reverse=True)[:k]
        top.sort(key=lambda h: h["frame_idx"])
        out[vid] = top
    return out


def _align_events_in_video(
    candidates_by_position: list[list[dict]],
    min_gap: int = TRAKE_MIN_FRAME_GAP,
) -> tuple[list[tuple[int, int, str | None, float]], float]:
    """N rổ ứng viên CỦA MỘT VIDEO (rổ thứ j = ứng viên của ĐÚNG sự kiện j,
    sắp theo frame_idx tăng dần) → dãy con tăng dần ngặt tổng điểm CAO NHẤT,
    ĐÚNG 1 ứng viên mỗi vị trí đã chọn, không bao giờ 2 vị trí chọn cùng 1 rổ.

    Đây là bài toán "longest increasing subsequence có trọng số, chọn tối đa
    1 phần tử mỗi nhóm, nhóm phải tăng dần theo THỨ TỰ NHÓM" — khác LIS thường
    ở chỗ ràng buộc kép: cả chỉ số VỊ TRÍ (j) lẫn frame_idx đều phải tăng dần.
    Ràng buộc vị trí là thứ khiến hàm này AN TOÀN để dùng thẳng — nó không thể
    xếp bằng chứng của sự kiện 3 vào vị trí 1 (xem cảnh báo đầu file).

    N, K (số ứng viên mỗi vị trí) đều nhỏ (N thường <= 6, K = TRAKE_CANDIDATES_
    PER_EVENT) nên DP O((N·K)²) rẻ, không cần tối ưu bằng cấu trúc dữ liệu.

    ⚠️ SỬA 16/08 (đo thật trên "bỏ muối . bỏ cải . khuấy"): CLIP không phân
    biệt nổi "đổ muối vào nước" với "đổ rau vào nước" bằng caption ngắn — cả
    hai câu ra ĐÚNG CÙNG 1 khung hình top-1 trong video đúng (cách nhau vài
    chục mili giây thực tế). DP tối đa TỔNG điểm sẽ ưu tiên ghép 2 khung hình
    dính sát nhau đó làm "2 sự kiện riêng biệt" vì tổng điểm cao — SAI về mặt
    thời gian dù không sai luật tăng dần. `min_gap` bắt khoảng cách frame tối
    thiểu giữa 2 vị trí LIÊN TIẾP trong chuỗi: không sửa được việc CLIP nhầm
    lẫn (đó là giới hạn model, xem docs/contest.md mục "chiến lược 2 tầng"),
    nhưng ép DP bỏ qua tổ hợp "2 sự kiện chụm cùng 1 khoảnh khắc" để ưu tiên
    phương án dàn trải hợp lý hơn trên các ứng viên còn lại.

    Trả: (chuỗi đã chọn [(vị_trí, frame_idx, keyframe_id, điểm), ...] tăng dần
    CẢ vị trí lẫn frame_idx (cách nhau >= min_gap), tổng điểm của chuỗi đó).
    Vị trí KHÔNG có mặt trong chuỗi = không có bằng chứng dùng được (thiếu
    hẳn, hoặc có nhưng không ghép được với phần còn lại) — chỗ gọi tự nội suy.
    """
    flat: list[tuple[int, dict]] = [
        (j, c) for j, cands in enumerate(candidates_by_position) for c in cands
    ]
    if not flat:
        return [], 0.0

    n = len(flat)
    dp = [c["score"] for _, c in flat]
    parent: list[int | None] = [None] * n

    for i in range(n):
        j_i, c_i = flat[i]
        for k in range(i):
            j_k, c_k = flat[k]
            if j_k < j_i and c_k["frame_idx"] + min_gap <= c_i["frame_idx"]:
                cand_total = dp[k] + c_i["score"]
                if cand_total > dp[i]:
                    dp[i] = cand_total
                    parent[i] = k

    best_i = max(range(n), key=lambda i: dp[i])
    chain: list[tuple[int, int, str | None, float]] = []
    i: int | None = best_i
    while i is not None:
        j, c = flat[i]
        chain.append((j, c["frame_idx"], c.get("keyframe_id"), c["score"]))
        i = parent[i]
    chain.reverse()
    return chain, dp[best_i]


def _is_strictly_increasing(seq: list[int]) -> bool:
    return all(a < b for a, b in zip(seq, seq[1:]))


def _fill_missing(frame_or_none: list[int | None]) -> list[int]:
    """Vị trí không có bằng chứng thật trong video → nội suy TUYẾN TÍNH giữa 2
    vị trí lân cận có bằng chứng thật. Thiếu ở đầu/cuối dãy (không có gì để
    nội suy hai phía) → dùng nguyên giá trị lân cận gần nhất.

    KHÔNG bao giờ trả None: mọi vị trí phải có 1 số nguyên để bước sửa đơn điệu
    (`_repair_strictly_increasing`) chạy được. Chỉ raise khi TOÀN BỘ N vị trí
    đều không có bằng chứng — lúc đó không còn gì để nội suy từ đâu cả (không
    xảy ra trong `trake_search`: video chỉ vào danh sách ứng viên khi có ít
    nhất 1 vị trí có bằng chứng).
    """
    n = len(frame_or_none)
    known = [(i, f) for i, f in enumerate(frame_or_none) if f is not None]
    if not known:
        raise RuntimeError(
            "Không sự kiện nào có bằng chứng trong video này — trake_search() không "
            "nên đưa video vào danh sách ứng viên nếu không có bằng chứng nào."
        )

    out: list[int] = list(frame_or_none)  # type: ignore[assignment]
    for i in range(n):
        if out[i] is not None:
            continue
        before = max((k for k in known if k[0] < i), default=None)
        after = min((k for k in known if k[0] > i), default=None)
        if before is not None and after is not None:
            (i0, f0), (i1, f1) = before, after
            out[i] = round(f0 + (f1 - f0) * (i - i0) / (i1 - i0))
        elif before is not None:
            out[i] = before[1]
        else:
            out[i] = after[1]
    return out  # type: ignore[return-value]


def _repair_strictly_increasing(frames: list[int], n_frames_video: int) -> list[int]:
    """Lưới an toàn CUỐI CÙNG: sửa vi phạm tăng dần NGẶT tại chỗ, giữ vị trí —
    không sort theo giá trị. Vì DP (`_align_events_in_video`) đã đảm bảo chuỗi
    nó chọn tăng dần ngặt, hàm này giờ chỉ còn phải xử lý va chạm sinh ra bởi
    NỘI SUY (`_fill_missing` làm tròn `round()` có thể trùng frame lân cận),
    không còn là đường chính như bản `trake_fallback.py` cũ.

    Quét trái→phải, đẩy frame sau lên frame trước +1 khi cần: thà lệch 1 frame
    còn hơn nộp dòng bị validator loại vì không tăng dần ngặt
    (backend/export/exporter.py::_check_shape, luật `trake_not_increasing`).
    """
    out = list(frames)
    for i in range(1, len(out)):
        if out[i] <= out[i - 1]:
            out[i] = out[i - 1] + 1

    overflow = out[-1] - (n_frames_video - 1)
    if overflow > 0:
        out = [f - overflow for f in out]
        if out[0] < 0:
            # Video quá ngắn cho ngần ấy sự kiện đã bị đẩy dồn — không còn cách
            # nào giữ đúng bằng chứng mà vẫn tăng dần ngặt. Rải đều là lựa chọn
            # ít tệ nhất: sai vị trí nhưng còn ĐÚNG VIDEO và ĐÚNG HÌNH DẠNG,
            # validator không loại thẳng cả dòng. Ca này cực hiếm nếu DP có đủ
            # ứng viên (N TRAKE luôn << độ dài video tính bằng frame).
            if len(out) > 1:
                out = [round(i * (n_frames_video - 1) / (len(out) - 1)) for i in range(len(out))]
            else:
                out = [0]
            for i in range(1, len(out)):
                if out[i] <= out[i - 1]:
                    out[i] = out[i - 1] + 1
            out = [max(0, min(f, n_frames_video - 1)) for f in out]
    return out


def _localize_in_video(
    vid: str, candidates_by_position: list[list[dict]]
) -> TrakeCandidate:
    """1 video ứng viên + rổ ứng viên mỗi vị trí (đã lọc riêng cho video này)
    → TrakeCandidate hoàn chỉnh (điểm xếp hạng + N frame_ids đúng vị trí)."""
    n = len(candidates_by_position)
    n_hit_events = sum(1 for c in candidates_by_position if c)
    chain, chain_score = _align_events_in_video(candidates_by_position)
    has_full_order = len(chain) == n

    if has_full_order:
        frame_ids = [f for _, f, _, _ in chain]
        keyframe_ids: list[str | None] = [kf for _, _, kf, _ in chain]
        score = chain_score * TRAKE_ORDER_BONUS
    else:
        # Không đủ/không xếp tăng dần được cả N vị trí bằng 1 dãy DP duy nhất
        # → KHÔNG bonus, nhưng vẫn thưởng ĐỘ PHỦ: mỗi vị trí lấy ứng viên điểm
        # cao nhất CỦA RIÊNG NÓ (không ràng buộc thứ tự với vị trí khác) —
        # đúng ý đồ log-sum gốc: video khớp CẢ N sự kiện (dù thứ tự chưa hoàn
        # hảo) vẫn phải thắng video chỉ khớp 1 sự kiện dù khớp rất mạnh.
        frame_or_none: list[int | None] = [None] * n
        keyframe_ids = [None] * n
        score = 0.0
        # Vị trí đã có trong chuỗi DP (mảnh tăng dần dài nhất tìm được) —
        # dùng nguyên, đây là bằng chứng THẬT và ĐÃ tăng dần giữa chúng.
        chain_positions = {j for j, _, _, _ in chain}
        for j, f, kf, s in chain:
            frame_or_none[j] = f
            keyframe_ids[j] = kf
            score += s
        # Vị trí có bằng chứng nhưng DP bỏ (phá thứ tự với chuỗi đã chọn) —
        # lấy điểm cao nhất của riêng nó cho ĐIỂM xếp hạng (độ phủ), nhưng
        # frame_ids để trống cho bước nội suy xử lý — đưa giá trị KHÔNG tăng
        # dần được vào thẳng đây sẽ chỉ bị `_repair_strictly_increasing` đẩy
        # lung tung, còn nội suy giữa 2 mốc THẬT gần nhất là ước lượng khá hơn.
        for j, cands in enumerate(candidates_by_position):
            if not cands or j in chain_positions:
                continue
            score += max(c["score"] for c in cands)
        frame_ids = _fill_missing(frame_or_none)

    frame_ids = _repair_strictly_increasing(frame_ids, n_frames_of(vid))
    return TrakeCandidate(
        video_id=vid,
        score=score,
        frame_ids=tuple(frame_ids),
        keyframe_ids=tuple(keyframe_ids),
        n_hit_events=n_hit_events,
        has_full_order=has_full_order,
    )


def trake_search(
    events: list[str],
    *,
    pool_per_event: int = TRAKE_EVENT_SEARCH_POOL,
    candidates_per_event: int = TRAKE_CANDIDATES_PER_EVENT,
    top_videos: int = TOP_VIDEOS,
) -> list[TrakeCandidate]:
    """N mô tả sự kiện → top video ứng viên, MỖI video kèm sẵn N frame_ids đã
    định vị đúng vị trí (thay cả trake_stage1 + trake_stage2_fallback cũ).

    Sai video ở TRAKE là 0 điểm tuyệt đối (docs/contest.md) nên thứ tự ưu tiên
    vẫn là: xếp đúng video lên đầu trước, rồi mới tới định vị khoảnh khắc chính
    xác — nhưng giờ cả hai việc được làm trong CÙNG một lượt DP mỗi video,
    không còn phải search lại lần 2 sau khi đã chốt video.
    """
    n = len(events)
    if n < 2:
        raise ValueError(f"TRAKE cần ít nhất 2 sự kiện, nhận {n}")

    def _search_one(event_vi: str) -> list[dict]:
        # Một sự kiện lỗi (ES/Milvus tạm chết) không được kéo sập cả stage —
        # đúng tinh thần try/except từng nhánh của search.py (skill retrieval).
        try:
            return search(event_vi, top_k=pool_per_event, group_by_shot=True)
        except Exception as e:
            print(f"  [cảnh báo] search lỗi cho sự kiện '{event_vi}': {e}")
            return []

    with ThreadPoolExecutor(max_workers=min(n, 8)) as pool:
        per_event_hits = list(pool.map(_search_one, events))

    topk_per_event_video = [_topk_per_video(hits, candidates_per_event) for hits in per_event_hits]

    all_videos: set[str] = set()
    for by_video in topk_per_event_video:
        all_videos.update(by_video)
    if not all_videos:
        return []

    candidates = [
        _localize_in_video(
            vid, [by_video.get(vid, []) for by_video in topk_per_event_video]
        )
        for vid in all_videos
    ]
    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates[:top_videos]


def to_answers(candidates: list[TrakeCandidate]) -> list[Answer]:
    """list[TrakeCandidate] → list[Answer] cho export/allocate — chuyển thẳng
    frame_ids đã định vị bằng DP, KHÔNG đi qua backend/slot/allocator.py
    (`_allocate_trake` chỉ biết carve đều 1 shot đại diện thành N đoạn giả —
    đúng vấn đề bản sửa 16/08 này giải quyết, xem đầu file)."""
    return [
        Answer(
            video_id=c.video_id,
            frame_ids=c.frame_ids,
            keyframe_id=next((kf for kf in c.keyframe_ids if kf), None),
        )
        for c in candidates
    ]


def pad_answers(candidates: list[TrakeCandidate], total: int) -> list[Answer]:
    """`to_answers(candidates)` thường ngắn hơn `total` (BTC luôn cần đủ
    ANSWERS_PER_QUERY dòng, không phạt câu sai — docs/contest.md) → đệm thêm
    bằng cách LẶP LẠI danh sách ứng viên đã có, dịch frame_ids một khoảng tăng
    dần mỗi vòng lặp (rồi chốt lại tăng dần ngặt) để KHÔNG BAO GIỜ trùng
    (video_id, frame_ids) với dòng đã có — trùng là lỗi `duplicate_answer`,
    validator từ chối ghi CẢ FILE (backend/export/exporter.py::_check_duplicates).

    Vẫn tốt hơn `_allocate_trake`: dòng đệm bám sát video ỨNG VIÊN THẬT (đã có
    bằng chứng cho ít nhất 1 sự kiện) thay vì carve rỗng 1 shot bất kỳ.
    """
    if not candidates:
        raise ValueError("Không có video ứng viên TRAKE nào để đệm")

    answers: list[Answer] = []
    used: set[tuple[str, tuple[int, ...]]] = set()
    shift = 0
    i = 0
    guard = 0
    while len(answers) < total:
        guard += 1
        if guard > total * 20:
            raise RuntimeError(
                f"Không đệm đủ {total} dòng TRAKE — chỉ dựng được {len(answers)} dòng "
                f"KHÔNG TRÙNG từ {len(candidates)} video ứng viên."
            )
        c = candidates[i % len(candidates)]
        if shift == 0:
            frames, kf = c.frame_ids, next((k for k in c.keyframe_ids if k), None)
        else:
            frames = tuple(_repair_strictly_increasing(
                [f + shift for f in c.frame_ids], n_frames_of(c.video_id)
            ))
            kf = None  # dòng đệm dịch khỏi bằng chứng thật — không gán nhầm keyframe
        key = (c.video_id, frames)
        if key not in used:
            used.add(key)
            answers.append(Answer(video_id=c.video_id, frame_ids=frames, keyframe_id=kf))
        i += 1
        if i % len(candidates) == 0:
            shift += 1
    return answers


def main() -> None:
    ap = argparse.ArgumentParser(description="TRAKE — xếp hạng video + định vị N khoảnh khắc (C3.2/C4.4)")
    ap.add_argument("query", help="câu hỏi TRAKE tiếng Việt, các sự kiện cách nhau bởi ' . '")
    ap.add_argument("--parse", action="store_true",
                     help="tự tách sự kiện bằng llm() thay vì split thủ công theo ' . '")
    args = ap.parse_args()

    events = parse_events(args.query) if args.parse else [e.strip() for e in args.query.split(" . ")]
    if len(events) < 2:
        ap.error(f"cần >= 2 sự kiện (tách theo ' . ' hoặc dùng --parse), nhận: {events}")

    print(f"{len(events)} sự kiện:")
    for i, e in enumerate(events, 1):
        print(f"  {i}. {e}")

    ranked = trake_search(events)
    print(f"\nTop {len(ranked)} video ứng viên:")
    for i, c in enumerate(ranked, 1):
        order = "ĐÚNG thứ tự" if c.has_full_order else f"{c.n_hit_events}/{len(events)} sự kiện, KHÔNG bonus"
        print(f"  hạng {i:>2}: {c.video_id}  score={c.score:.5f}  ({order})  frames={c.frame_ids}")

    from backend.llm.adapter import print_usage
    print()
    print_usage()


if __name__ == "__main__":
    main()
