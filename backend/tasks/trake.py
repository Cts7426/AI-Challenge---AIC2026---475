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
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from backend.export import n_frames_of
from backend.llm.adapter import llm
from backend.retrieval.search import search
from data.config.search_weights import (
    TRAKE_ASR_CONTEXT_BONUS_WEIGHT,
    TRAKE_CANDIDATES_PER_EVENT,
    TRAKE_EVENT_SEARCH_POOL,
    TRAKE_MIN_BLEND_LAMBDA,
    TRAKE_MIN_FRAME_GAP,
    TRAKE_ORDER_BONUS,
)
from data.config.submit_format import Answer

REPO_ROOT = Path(__file__).resolve().parents[2]
ASR_PATH = REPO_ROOT / "data" / "derived" / "asr.parquet"

TOP_VIDEOS = 10  # BUILD_TASKS C3.2: "trả top-10 video xếp hạng"

PARSE_EVENTS_SCHEMA = {
    "type": "object",
    "properties": {"events_vi": {"type": "array", "items": {"type": "string"}}},
    "required": ["events_vi"],
    "additionalProperties": False,
}


def _parse_events_llm(query_vi: str) -> list[str]:
    """Thân hàm gốc của parse_events() — tách bằng LLM. Raise khi LLM lỗi hoặc
    tách được <2 sự kiện; parse_events() bên dưới bắt cả hai trường hợp và rơi
    về _split_events_heuristic() (C4.4 — không bao giờ để 1 câu hỏng làm mất
    trắng cả câu TRAKE, xem parse_events())."""
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


# C4.4 — thứ tự ưu tiên: dấu câu/liên từ tuần tự tiếng Việt RÕ RÀNG nhất trước,
# dấu phẩy (yếu nhất, dễ cắt nhầm giữa câu) thử SAU CÙNG trước khi chẻ đôi mù.
_HEURISTIC_DELIMITERS = [
    r"\s*\.\s+",
    r"\s*,?\s*sau\s+đó\s+",
    r"\s*,?\s*rồi\s+",
    r"\s*,?\s*tiếp\s+theo\s*,?\s*",
    r"\s*,?\s*kế\s+(?:đó|tiếp)\s*,?\s*",
    r"\s*,?\s*xong\s+(?:thì\s+)?",
    r"\s*,?\s*cuối\s+cùng\s*,?\s*",
    r"\s*;\s*",
    r"\s*,\s*",
]


def _split_events_heuristic(query_vi: str) -> list[str]:
    """Tách N sự kiện KHÔNG cần LLM — lưới an toàn cuối khi _parse_events_llm()
    hỏng (mạng/API lỗi, LLM trả JSON hỏng, hoặc tách được <2 sự kiện).

    Đoán còn hơn bỏ trống (CLAUDE.md §5.3): thử lần lượt các dấu hiệu tuần tự
    tiếng Việt RÕ RÀNG nhất trước — câu TRAKE thường được viết đúng như một
    danh sách sự kiện nối bằng dấu câu (xem TR01/TR02 dev-set: nối bằng " . ").
    Không có dấu hiệu nào tách được ≥2 phần → chẻ đôi theo số từ (đoán N=2,
    vẫn tốt hơn raise vì rscore_trake cho 0 cả hai trường hợp, nhưng chỉ
    trường hợp NÀY còn cơ hội ăn điểm nếu đoán đúng)."""
    for pat in _HEURISTIC_DELIMITERS:
        parts = [p.strip() for p in re.split(pat, query_vi, flags=re.IGNORECASE) if p.strip()]
        if len(parts) >= 2:
            return parts
    words = query_vi.split()
    if len(words) < 2:
        return [query_vi, query_vi]
    mid = max(1, len(words) // 2)
    return [" ".join(words[:mid]), " ".join(words[mid:])]


def parse_events(query_vi: str) -> list[str]:
    """Câu hỏi TRAKE → list N mô tả sự kiện, ĐÚNG thứ tự thời gian đề bài nói.

    N = len(kết quả) — KHÔNG đọc TRAKE_DEFAULT_N từ config. dev_set/tools/scoring
    (rscore_trake) cho 0 điểm TUYỆT ĐỐI nếu số khoảnh khắc nộp khác N thật của
    đề — đoán N sai là mất trắng dù mọi frame đều đúng.

    ⚠️ C4.4 — KHÔNG BAO GIỜ raise cho câu không rỗng: nếu LLM lỗi (mạng/API/
    JSON hỏng) hoặc tách được <2 sự kiện, rơi về _split_events_heuristic()
    (không cần LLM). trake_fallback.py cũ (đã xoá khi gộp DP 16/08) từng giữ
    vai trò lưới an toàn này ở tầng khác — quan sát thật (run.py::main()):
    parse_events() raise → giai_mot_query() raise → query KHÔNG được ghi
    checkpoint → biến mất hoàn toàn khỏi bài nộp (0 tuyệt đối mọi R@k), tệ hơn
    hẳn một dự đoán N/sự kiện có thể sai.
    """
    try:
        return _parse_events_llm(query_vi)
    except Exception as e:
        print(f"  [cảnh báo] parse_events(): llm() lỗi hoặc tách <2 sự kiện ({e}) "
              "— chuyển sang tách heuristic không LLM.")
        return _split_events_heuristic(query_vi)


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


# ═══════════════════════════════════ 20/08: tín hiệu "cùng mạch nội dung"
#
# ⚠️ Vì sao cần: TRAKE hiện tại = N lần search() ĐỘC LẬP (y hệt KIS) + DP chỉ
# ép thứ tự vị trí/khoảng cách tối thiểu — DP KHÔNG biết "4 khoảnh khắc này
# có cùng 1 mạch chuyện hay không", vì nó chỉ thấy (vị trí, frame_idx, điểm),
# không thấy nội dung. Đo thật (reports/trake_hardening.md §6, truy vấn tai
# nạn giao thông thật): 1 sự kiện diễn đạt chung chung ("lực lượng chức năng
# có mặt tại hiện trường") lọt sang MỘT TIN KHÁC hẳn trong cùng video bản tin
# nhiều mục (đúng thứ tự, đúng khoảng cách, chỉ sai vì thuộc chuyện khác) —
# DP không có cách nào phát hiện.
#
# ⚠️ Vì sao KHÔNG sửa bằng "phạt khoảng cách frame" (đã thử, loại bỏ): so
# TR01 (nấu ăn, ĐÚNG, khoảng cách hợp lệ tới 22.5% độ dài video) với ca tin
# tức trên (SAI, chỉ cách 5.1% video) — khoảng cách "sai" NHỎ HƠN khoảng cách
# "đúng". Không có ngưỡng khoảng cách nào phân biệt được 2 trường hợp: video
# nấu ăn là 1 câu chuyện xuyên suốt (xa vẫn hợp lệ), bản tin nhiều mục là
# NHIỀU câu chuyện độc lập nối lại (gần cũng có thể sai chuyện).
#
# ⚠️ Vì sao KHÔNG dùng `seg_id` của asr.parquet làm ranh giới câu chuyện:
# kiểm tra thật — seg_id chỉ là đoạn CẮT TRANSCRIPT kỹ thuật (~500-600 frame/
# đoạn, đếm liên tục 0..N cho cả video), KHÔNG phải ranh giới chủ đề. 1 câu
# chuyện thật (vd đúng đoạn tai nạn) trải dài qua NHIỀU seg_id liền nhau.
#
# ===== Cơ chế: cộng điểm ứng viên theo mức "cộng hưởng nội dung" =====
# Với mỗi ứng viên ở vị trí j, tra văn bản ASR bao phủ frame đó (nếu có), đếm
# xem có bao nhiêu TỪ KHOÁ CỦA CÁC SỰ KIỆN KHÁC (không phải sự kiện j đang
# tìm) xuất hiện trong đúng văn bản đó. Ứng viên thật của 1 chuỗi sự kiện liên
# quan thường được người dẫn tường thuật LIỀN MẠCH (nhắc luôn các chi tiết
# trước/sau trong cùng câu) — đo thật cả 2 phía: đoạn ASR chứa frame ĐÚNG của
# sự kiện 4 (vụ tai nạn) nhắc tới "va chạm"/"xe ba gác"/"ngã" (từ khoá sự
# kiện 2-3); đoạn ASR chứa frame SAI (tin Phú Yên) không nhắc gì tới vựng của
# 3 sự kiện còn lại. TR01 (nấu ăn) cũng có cùng hiện tượng: đoạn ASR chứa GT
# "mít non cắt" nhắc luôn "vả" (từ khoá sự kiện kế tiếp).
#
# An toàn: KHÔNG có ASR (video câm, hoặc frame ngoài vùng phủ ASR) → bonus=0,
# quay lại hành vi CŨ y hệt (không đổi gì). Đây là CỘNG THÊM, không phải điều
# kiện lọc — ứng viên không có ASR vẫn được xét bình thường theo điểm gốc.

_VI_STOPWORDS = frozenset({
    "va", "voi", "cua", "cho", "khong", "duoc", "nhung", "nhieu", "mot",
    "hai", "ba", "cac", "nay", "do", "tai", "tren", "duong", "sau", "truoc",
    "khi", "thi", "la", "co", "da", "se", "bi", "vao", "ra", "len", "xuong",
    "theo", "nen", "vi", "de", "nhu", "hon", "rat", "cung", "con", "chi",
    "day", "ay", "nao", "gi", "ai", "sao", "vay", "ma", "roi", "luon",
})


def _strip_diacritics_lower(text: str) -> str:
    """Bỏ dấu tiếng Việt + hạ chữ thường — so khớp từ khoá không phân biệt
    dấu (ASR đôi khi thiếu dấu/sai dấu, event_vi từ câu hỏi luôn có dấu chuẩn,
    so trực tiếp có dấu sẽ bỏ sót nhiều khớp thật)."""
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _significant_tokens(text: str) -> set[str]:
    """Tách từ có nghĩa: bỏ dấu, hạ thường, giữ từ >= 3 ký tự và không phải
    hư từ phổ biến. Ngưỡng 3 ký tự lọc bớt từ đơn âm tiếng Việt ít mang nghĩa
    riêng (đo thô, không cần chuẩn NLP đầy đủ — chỉ dùng để tính TRÙNG LẶP
    tương đối, không phải phân tích ngữ nghĩa chính xác)."""
    words = re.findall(r"[a-zđ]+", _strip_diacritics_lower(text))
    return {w for w in words if len(w) >= 3 and w not in _VI_STOPWORDS}


@lru_cache(maxsize=1)
def _asr_by_video() -> dict[str, list[tuple[int, int, str]]]:
    """video_id → [(start_frame, end_frame, text_vi), ...] sort theo
    start_frame. Đọc thẳng asr.parquet (B1.3) — cache 1 lần/tiến trình, cùng
    kiểu với _keyframes_by_shot() trong qa.py. Rỗng nếu chưa có ASR (chưa
    chạy job, hoặc video câm) — KHÔNG raise, để _asr_text_at() trả rỗng."""
    if not ASR_PATH.exists():
        return {}
    import pandas as pd

    df = pd.read_parquet(ASR_PATH, columns=["video_id", "start_frame", "end_frame", "text_vi"])
    out: dict[str, list[tuple[int, int, str]]] = {}
    for vid, s, e, text in df.itertuples(index=False):
        out.setdefault(vid, []).append((int(s), int(e), text or ""))
    for segs in out.values():
        segs.sort()
    return out


def _asr_text_at(video_id: str, frame_idx: int) -> str:
    """Văn bản ASR bao phủ frame_idx trong video, rỗng nếu không có (video
    câm, chưa có ASR, hoặc frame nằm ngoài mọi đoạn đã nhận diện tiếng nói)."""
    for s, e, text in _asr_by_video().get(video_id, []):
        if s <= frame_idx <= e:
            return text
        if s > frame_idx:  # đã sort theo start_frame — qua khỏi điểm cần tìm
            break
    return ""


def _cross_event_bonus(video_id: str, frame_idx: int, own_position: int,
                        events_tokens: list[set[str]],
                        token_weight: dict[str, float]) -> float:
    """Tổng TRỌNG SỐ (không phải đếm thô) các từ khoá CỦA CÁC SỰ KIỆN KHÁC
    (không phải own_position) xuất hiện trong văn bản ASR bao phủ frame_idx.

    ⚠️ SỬA — đo thật (quét trọng số trên dev-set 20/08): đếm thô làm sập điểm
    8/8 câu TRAKE hiện có (R@1 → 0.000) vì video nấu ăn dùng chung một lượng
    lớn từ vựng CHUNG CHUNG giữa các TẬP KHÁC NHAU trong cùng thể loại (vd
    "cắt", "nước", "cho vào" lặp ở HẦU HẾT video nấu ăn) — đếm thô coi những
    từ này ngang hàng với từ khoá THẬT SỰ hiếm/đặc trưng (vd "xe ba gác",
    "lực lượng chức năng"), khiến bonus nhiễu nặng cả trong-video lẫn giữa-
    các-video. `token_weight` (tính 1 lần/lần gọi trake_search(), xem
    _build_token_weight()) hạ giá từ càng xuất hiện càng nhiều ỨNG VIÊN
    TRONG CHÍNH CÂU HỎI NÀY — không cần bảng tần suất toàn kho dữ liệu."""
    text = _asr_text_at(video_id, frame_idx)
    if not text:
        return 0.0
    local_tokens = _significant_tokens(text)
    if not local_tokens:
        return 0.0
    other_tokens: set[str] = set()
    for j, toks in enumerate(events_tokens):
        if j != own_position:
            other_tokens |= toks
    matched = local_tokens & other_tokens
    return sum(token_weight.get(tok, 0.0) for tok in matched)


def _build_token_weight(topk_per_event_video: list[dict[str, list[dict]]]) -> dict[str, float]:
    """Trọng số kiểu IDF cho mỗi từ khoá, tính trên TOÀN BỘ ứng viên (mọi vị
    trí, mọi video) của MỘT lần gọi trake_search() — không phải toàn kho dữ
    liệu (không có sẵn, và cũng không cần: cái cần phân biệt là "từ này có
    đặc trưng cho VIDEO/KHOẢNH KHẮC nào đó trong SỐ CÁC ỨNG VIÊN CỦA CÂU HỎI
    NÀY hay không", không phải độ hiếm tuyệt đối toàn kho).

    weight(từ) = 1 / (số ứng viên có từ đó trong văn bản ASR bao phủ). Từ
    xuất hiện ở 1 ứng viên duy nhất → trọng số 1.0 (tin cậy tối đa). Từ xuất
    hiện ở 50 ứng viên (kiểu "cắt"/"nước" lặp khắp mọi video nấu ăn cùng thể
    loại) → trọng số 0.02 (gần như bỏ qua). Đơn giản hơn log-IDF, đủ dùng vì
    chỉ cần XẾP HẠNG tương đối trong phạm vi 1 câu hỏi, không cần chuẩn hoá
    xác suất."""
    doc_freq: dict[str, int] = {}
    for by_video in topk_per_event_video:
        for vid, cands in by_video.items():
            for c in cands:
                text = _asr_text_at(vid, c["frame_idx"])
                if not text:
                    continue
                for tok in _significant_tokens(text):
                    doc_freq[tok] = doc_freq.get(tok, 0) + 1
    return {tok: 1.0 / n for tok, n in doc_freq.items()}


class _UnitWeight(dict):
    """Giả lập dict trọng số toàn 1.0 — dùng khi chỗ gọi cố tình muốn đếm thô
    (vd test cô lập 1 video, không có ngữ cảnh toàn bộ ứng viên để tính IDF)."""

    def get(self, key, default=None):  # noqa: D102 — override có chủ đích
        return 1.0


def _apply_asr_context_bonus(
    vid: str, candidates_by_position: list[list[dict]], events: list[str] | None,
    token_weight: dict[str, float] | None = None,
) -> list[list[dict]]:
    """Trả bản SAO của candidates_by_position với score đã cộng thêm bonus
    cộng hưởng ASR (xem block comment phía trên). KHÔNG mutate dict gốc —
    cùng dict object có thể còn được đọc ở chỗ khác (vd keyframe_id).

    events=None hoặc TRAKE_ASR_CONTEXT_BONUS_WEIGHT=0 → trả nguyên
    candidates_by_position, KHÔNG tính toán gì thêm (an toàn/nhanh cho chỗ
    gọi không có events, vd test cũ). token_weight=None (có events nhưng
    không truyền bảng trọng số IDF) → coi mọi từ trọng số 1.0 (đếm thô — chỉ
    nên dùng khi test cô lập, KHÔNG dùng trong đường chạy thật vì đếm thô đã
    đo được là làm sập điểm trên corpus từ vựng lặp lại — xem _cross_event_bonus)."""
    if not events or not TRAKE_ASR_CONTEXT_BONUS_WEIGHT:
        return candidates_by_position
    events_tokens = [_significant_tokens(e) for e in events]
    weight_lookup = token_weight if token_weight is not None else _UnitWeight()
    out: list[list[dict]] = []
    for j, cands in enumerate(candidates_by_position):
        new_cands = []
        for c in cands:
            bonus = _cross_event_bonus(vid, c["frame_idx"], j, events_tokens, weight_lookup)
            if bonus:
                # "_orig_score" (điểm search() gốc, CHƯA cộng bonus) giữ lại
                # riêng — DP dùng "score" (đã cộng bonus) để CHỌN ứng viên
                # đúng mạch nội dung trong CÙNG video, nhưng điểm XẾP HẠNG
                # GIỮA CÁC VIDEO (_localize_in_video → _blend_score) phải
                # dùng "_orig_score" gốc. Lý do — đo thật (quét 20/08): dùng
                # điểm đã cộng bonus cho CẢ HAI việc làm TR02 dao động hạng
                # 5↔6 (đúng ranh giới R@5) vì bonus tình cờ ưu ái video KHÁC
                # nhiều hơn — bonus chỉ nên "chọn đúng frame trong video này",
                # KHÔNG nên can thiệp "video nào thắng video nào" (việc đó đã
                # có TRAKE_MIN_BLEND_LAMBDA lo, tune riêng trên dev-set).
                c = {**c, "_orig_score": c["score"],
                     "score": c["score"] + TRAKE_ASR_CONTEXT_BONUS_WEIGHT * bonus}
            new_cands.append(c)
        out.append(new_cands)
    return out


def _blend_score(position_scores: list[float]) -> float:
    """Tổng điểm mỗi vị trí + λ × điểm vị trí YẾU NHẤT — λ=TRAKE_MIN_BLEND_LAMBDA.

    ⚠️ SỬA 20/08 — đo thật (reports/trake_hardening.md): công thức CŨ (chỉ
    tổng) để lọt video sai hạng cao hơn video đúng khi video sai có 1 vị trí
    khớp RẤT MẠNH + các vị trí khác yếu — tổng vẫn thắng dù không NHẤT QUÁN
    bằng video khớp đều cả N vị trí. Cộng thêm điểm vị trí yếu nhất phạt đúng
    kiểu "thắng 1 chỗ, đuối các chỗ còn lại" này. λ=0 quay lại công thức gốc
    (chỉ tổng) — quét dev-set cho λ=2.0 (xem TRAKE_MIN_BLEND_LAMBDA)."""
    return sum(position_scores) + TRAKE_MIN_BLEND_LAMBDA * min(position_scores)


def _localize_in_video(
    vid: str, candidates_by_position: list[list[dict]],
    events: list[str] | None = None,
    token_weight: dict[str, float] | None = None,
) -> TrakeCandidate:
    """1 video ứng viên + rổ ứng viên mỗi vị trí (đã lọc riêng cho video này)
    → TrakeCandidate hoàn chỉnh (điểm xếp hạng + N frame_ids đúng vị trí).

    events: mô tả N sự kiện gốc — dùng để cộng bonus "cộng hưởng nội dung ASR"
    trước khi chạy DP (xem block comment _apply_asr_context_bonus). None →
    bỏ qua bước này, giữ hành vi CŨ y hệt (tương thích ngược cho test cũ gọi
    hàm này không kèm events). token_weight: bảng trọng số IDF tính SẴN trên
    toàn bộ ứng viên của lần gọi trake_search() này (_build_token_weight()) —
    None mà vẫn có events → coi mọi từ trọng số 1.0 (đếm thô, chỉ dùng cho
    test cô lập, xem cảnh báo trong _apply_asr_context_bonus)."""
    candidates_by_position = _apply_asr_context_bonus(vid, candidates_by_position, events, token_weight)
    n = len(candidates_by_position)
    n_hit_events = sum(1 for c in candidates_by_position if c)
    chain, chain_score = _align_events_in_video(candidates_by_position)
    has_full_order = len(chain) == n

    # (vị_trí, frame_idx) → điểm GỐC (chưa cộng bonus ASR) — DP ở trên đã
    # dùng điểm ĐÃ CỘNG BONUS để CHỌN đúng ứng viên (việc bonus nên làm), còn
    # điểm dùng để XẾP HẠNG GIỮA CÁC VIDEO (position_scores → _blend_score)
    # phải là điểm GỐC (xem cảnh báo trong _apply_asr_context_bonus — dùng
    # điểm đã cộng bonus cho cả hai việc làm TR02 dao động hạng qua ranh giới
    # R@5 vì bonus tình cờ ưu ái video khác nhiều hơn).
    orig_score_at: dict[tuple[int, int], float] = {
        (j, c["frame_idx"]): c.get("_orig_score", c["score"])
        for j, cands in enumerate(candidates_by_position) for c in cands
    }

    if has_full_order:
        frame_ids = [f for _, f, _, _ in chain]
        keyframe_ids: list[str | None] = [kf for _, _, kf, _ in chain]
        position_scores = [orig_score_at[(j, f)] for j, f, _, _ in chain]
        score = _blend_score(position_scores) * TRAKE_ORDER_BONUS
    else:
        # Không đủ/không xếp tăng dần được cả N vị trí bằng 1 dãy DP duy nhất
        # → KHÔNG bonus, nhưng vẫn thưởng ĐỘ PHỦ: mỗi vị trí lấy ứng viên điểm
        # cao nhất CỦA RIÊNG NÓ (không ràng buộc thứ tự với vị trí khác) —
        # đúng ý đồ log-sum gốc: video khớp CẢ N sự kiện (dù thứ tự chưa hoàn
        # hảo) vẫn phải thắng video chỉ khớp 1 sự kiện dù khớp rất mạnh.
        frame_or_none: list[int | None] = [None] * n
        keyframe_ids = [None] * n
        position_scores = []
        # Vị trí đã có trong chuỗi DP (mảnh tăng dần dài nhất tìm được) —
        # dùng nguyên, đây là bằng chứng THẬT và ĐÃ tăng dần giữa chúng.
        chain_positions = {j for j, _, _, _ in chain}
        for j, f, kf, _ in chain:
            frame_or_none[j] = f
            keyframe_ids[j] = kf
            position_scores.append(orig_score_at[(j, f)])
        # Vị trí có bằng chứng nhưng DP bỏ (phá thứ tự với chuỗi đã chọn) —
        # lấy điểm cao nhất của riêng nó cho ĐIỂM xếp hạng (độ phủ), nhưng
        # frame_ids để trống cho bước nội suy xử lý — đưa giá trị KHÔNG tăng
        # dần được vào thẳng đây sẽ chỉ bị `_repair_strictly_increasing` đẩy
        # lung tung, còn nội suy giữa 2 mốc THẬT gần nhất là ước lượng khá hơn.
        for j, cands in enumerate(candidates_by_position):
            if not cands or j in chain_positions:
                continue
            position_scores.append(max(c.get("_orig_score", c["score"]) for c in cands))
        score = _blend_score(position_scores) if position_scores else 0.0
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
    # Tính 1 LẦN cho cả lần gọi trake_search() này — token_weight cần nhìn
    # thấy ứng viên của MỌI video để biết từ nào chung chung trong PHẠM VI
    # câu hỏi này (xem _build_token_weight()), không tính lại mỗi video.
    token_weight = (_build_token_weight(topk_per_event_video)
                    if TRAKE_ASR_CONTEXT_BONUS_WEIGHT else {})

    all_videos: set[str] = set()
    for by_video in topk_per_event_video:
        all_videos.update(by_video)
    if not all_videos:
        # C4.4 — toàn bộ N search riêng lẻ đều rỗng (ES/Milvus tạm chết CHO CẢ
        # N sự kiện, hoặc index thật sự không có gì khớp). Thử MỘT lần search
        # cứu cánh bằng câu ghép toàn bộ sự kiện — chấp nhận có thể bị CLIP cắt
        # cụt do vượt 77 token (bất biến CLAUDE.md #4, xem cảnh báo đầu file)
        # vì có ứng viên (dù yếu) còn hơn 0 tuyệt đối. Không đụng nhánh bình
        # thường ở trên — chỉ kích hoạt khi rỗng HOÀN TOÀN.
        print(f"  [cảnh báo] trake_search(): 0 video ứng viên từ {n} tìm kiếm riêng lẻ "
              "theo sự kiện — thử tìm kiếm cứu cánh bằng câu ghép toàn bộ sự kiện.")
        try:
            fallback_hits = search(" . ".join(events), top_k=pool_per_event, group_by_shot=True)
        except Exception as e:
            print(f"  [cảnh báo] trake_search(): tìm kiếm cứu cánh cũng lỗi, trả rỗng: {e}")
            return []
        fallback_by_video = _topk_per_video(fallback_hits, candidates_per_event)
        if not fallback_by_video:
            return []
        # Không biết hit nào khớp sự kiện nào (1 câu ghép, không tách được theo
        # vị trí) → dùng CHUNG một rổ ứng viên cho MỌI vị trí j; DP vẫn chọn
        # đúng 1 ứng viên/vị trí, tăng dần ngặt, cách nhau >= min_gap. Ở nhánh
        # này n_hit_events/has_full_order KHÔNG còn nghĩa "bằng chứng riêng
        # từng sự kiện" — chỉ là tín hiệu độ phủ tạm thời.
        candidates = [
            _localize_in_video(vid, [cands] * n)
            for vid, cands in fallback_by_video.items()
        ]
        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates[:top_videos]

    candidates = [
        _localize_in_video(
            vid, [by_video.get(vid, []) for by_video in topk_per_event_video], events,
            token_weight,
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
