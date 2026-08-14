# app/debug_ui.py — UI debug.  Chạy: streamlit run app/debug_ui.py
#
# File này CHỈ VẼ. Logic nằm ở app/labels.py, app/evidence.py, app/offline_search.py —
# ba module thường, có test. Streamlit không chạy trong pytest, nhét logic vào đây là
# vừa mất test vừa buộc eval.py/D3.5 viết lại (viết lại = lệch nhau).
#
# UI trả lời ba câu: frame này lên hạng nhờ nguồn nào · thật sự chứa gì · đúng hay sai.
# Câu ba là lý do tồn tại — nhãn sinh ra ở đây là đầu vào của E4.2 và D3.5.
# Không nằm trên đường thi: không sinh file nộp, không đụng tầng export.

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

import streamlit as st

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.evidence import evidence_of, keyframes_in_shot  # noqa: E402
from app.labels import Label, LabelIndex, append_label  # noqa: E402
from app.offline_search import search as offline_search  # noqa: E402
from data.config.debug_ui import (  # noqa: E402
    DEFAULT_TOP_K,
    DEV_SET_DIR,
    KEYFRAMES_DIR,
    LABELER,
)

st.set_page_config(page_title="AIC 2026 · UI debug", layout="wide")

BRANCHES = ("vector", "metadata", "objects", "ocr", "asr")
LABEL_ICON = {"correct": "🟢", "wrong": "🔴", "unsure": "🟡"}

# Gói mà chế độ live bắt buộc phải có → tên để cài bằng pip.
LIVE_PACKAGES = {
    "elasticsearch": "elasticsearch",   # nhánh metadata/ocr/asr/objects
    "pymilvus": "pymilvus",             # nhánh vector
    "torch": "torch",                   # encode câu hỏi
    "open_clip": "open_clip_torch",
}


# --------------------------------------------------------------- tiện ích nhỏ

def query_id_of(query: str) -> str:
    """`query_id` ổn định từ câu truy vấn, để nhãn của cùng một câu gom về một chỗ.

    Băm thay vì dùng nguyên câu: gõ thừa một dấu cách là thành query khác, nhãn tách
    làm hai đống.
    """
    return "q_" + hashlib.sha1(query.strip().lower().encode("utf-8")).hexdigest()[:8]


@st.cache_resource(show_spinner=False)
def _load_search():
    """(hàm search, danh sách gói còn thiếu). Thiếu gói nào thì live không chạy được.

    Phải kiểm TỪNG GÓI chứ không chỉ thử import backend.retrieval.search: module đó
    nạp lười (`import torch` nằm trong thân hàm) nên nó import trót lọt trên máy trắng
    trơn. Chỉ dựa vào phép import ấy thì UI mặc định chọn live, người dùng bấm Tìm
    kiếm rồi mới nhận lỗi.
    """
    import importlib.util

    missing = [pip for mod, pip in LIVE_PACKAGES.items()
               if importlib.util.find_spec(mod) is None]
    try:
        from backend.retrieval.search import search
    except Exception as e:
        print(f"  [cảnh báo] không nạp được backend.retrieval.search: {e}")
        return None, missing
    return search, missing


# --------------------------------------------------------------- vùng A: sidebar

def sidebar() -> dict:
    st.sidebar.title("Điều khiển")

    query = st.sidebar.text_area("Truy vấn (tiếng Việt)", height=80,
                                 placeholder="thủ môn cản phá quả penalty")

    # Bỏ trống ô tiếng Anh thì search() gọi translate_to_english() → llm(). Không có
    # khoá API thì llm() ném RuntimeError TRƯỚC khi nhánh nào chạy, nên chết cả 5
    # nhánh. Nói trước còn hơn để người dùng nhận một vệt stack trace không liên quan.
    has_key = (bool(os.environ.get("ANTHROPIC_API_KEY"))
               or os.environ.get("LLM_BACKEND") == "local")
    query_en = st.sidebar.text_input(
        "Bản dịch tiếng Anh" + ("" if has_key else " — BẮT BUỘC"),
        help="CLIP nhận tiếng Anh. Có ANTHROPIC_API_KEY thì để trống, hệ tự dịch.",
    )
    task = st.sidebar.selectbox("Dạng bài", ("KIS", "QA", "TRAKE"))
    top_k = st.sidebar.slider("Số kết quả", 5, 100, DEFAULT_TOP_K, step=5)

    # TRAKE: chọn ở sidebar thay vì bấm lại trên từng thẻ. Soạn đáp án thường làm xong
    # khoảnh khắc 1 cho cả loạt kết quả rồi mới sang khoảnh khắc 2.
    moment, n_moments_total = 1, None
    if task == "TRAKE":
        # Khai N trước, vì nó chặn trên cho ô "khoảnh khắc thứ". N là MẪU SỐ của công
        # thức `(1/N)·Σ` — không khai thì eval lấy tạm số khoảnh khắc đã chấm, và chấm
        # dở 3/4 sẽ ra 1.0 thay vì 0.75.
        n_moments_total = int(st.sidebar.number_input(
            "Tổng số khoảnh khắc N (đọc từ đề)", min_value=2, max_value=20, value=4, step=1,
            help="MẪU SỐ khi chấm điểm. Đề có ghi N thì gõ đúng số đó. Không khai thì "
                 "eval.py lấy tạm số khoảnh khắc đã chấm → điểm CAO HƠN THẬT.",
        ))
        moment = st.sidebar.number_input(
            "Đang soạn khoảnh khắc thứ", min_value=1, max_value=n_moments_total, value=1,
            step=1,
            help="TRAKE chấm theo VỊ TRÍ: frame thứ j phải rơi vào khoảng của khoảnh "
                 "khắc thứ j. Mỗi khoảnh khắc là một dòng nhãn riêng.",
        )

    search_fn, missing_pkgs = _load_search()
    can_live = search_fn is not None and not missing_pkgs
    mode = st.sidebar.radio(
        "Nguồn kết quả", ("live", "offline"), index=0 if can_live else 1,
        help="live = search thật (cần Milvus + Elasticsearch). "
             "offline = BM25 trên docs_bm25.parquet, ~14 giây/truy vấn, không cần Docker.",
    )
    if mode == "live" and missing_pkgs:
        st.sidebar.error(
            "Chế độ live thiếu gói: **" + "**, **".join(missing_pkgs) + "**\n\n"
            "`pip install " + " ".join(missing_pkgs) + "`\n\n"
            "torch dùng bản CPU: `pip install torch --index-url "
            "https://download.pytorch.org/whl/cpu`"
        )
    elif mode == "live" and search_fn is None:
        st.sidebar.error("Không nạp được tầng search — hãy dùng chế độ offline.")

    # Offline chỉ có MỘT nguồn (BM25 trên doc_text) nên mấy ô dưới không có tác dụng.
    # Khoá lại thay vì để bật được: ô bật mà không đổi gì là lời nói dối về công cụ
    # chẩn đoán — người dùng tưởng đã tắt vector rồi kết luận sai nguồn nào gánh điểm.
    locked = mode == "offline"
    st.sidebar.markdown("**Bật/tắt từng nhánh**")
    if locked:
        st.sidebar.caption("Chế độ offline chỉ có một nguồn — các ô dưới bị khoá.")
    branches = {
        b: st.sidebar.checkbox(b, value=True, key=f"branch_{b}", disabled=locked)
        for b in BRANCHES
    }
    group_by_shot = st.sidebar.checkbox(
        "Gom về shot", value=True, disabled=locked,
        help="Tắt để xem các keyframe liền nhau trong cùng một shot — kiểm xem phép "
             "gom có nuốt mất keyframe đúng không.",
    )

    st.sidebar.divider()
    st.sidebar.caption(f"Người chấm: **{LABELER}** · nhãn ghi vào `{DEV_SET_DIR.name}/`")
    if LABELER == "unknown":
        st.sidebar.warning("Chưa đặt tên người chấm. Set biến môi trường `AIC_LABELER`.")
    if not KEYFRAMES_DIR.is_dir():
        st.sidebar.info(f"Chưa có ảnh keyframe ở `{KEYFRAMES_DIR}` — sẽ vẽ thẻ xám.")

    run = st.sidebar.button("Tìm kiếm", type="primary", use_container_width=True)
    return dict(query=query, query_en=query_en, task=task, top_k=top_k, mode=mode,
                moment=int(moment), n_moments_total=n_moments_total, branches=branches,
                group_by_shot=group_by_shot, run=run, has_key=has_key)


# ------------------------------------------------------- gọi search / offline

def run_search(cfg: dict, only_branch: str | None = None) -> list[dict]:
    """Một lượt tìm kiếm → list dict đã chuẩn hoá cho phần vẽ.

    `only_branch` khác None → chỉ bật đúng nhánh đó, bằng cách gọi lại chính `search()`
    thay vì viết lại logic truy xuất trong UI.
    """
    if cfg["mode"] == "offline":
        return [
            {"keyframe_id": r.kf_id, "video_id": r.video_id, "shot_id": r.shot_id,
             "frame_idx": r.frame_idx, "score": r.score, "ranks": {}, "contrib": {},
             "snippet": r.snippet}
            for r in offline_search(cfg["query"], cfg["top_k"])
        ]

    search_fn, missing = _load_search()
    if search_fn is None or missing:
        return []
    if not cfg["query_en"].strip() and not cfg.get("has_key", True):
        st.error(
            "Chưa có `ANTHROPIC_API_KEY` mà ô **Bản dịch tiếng Anh** đang trống. "
            "`search()` sẽ gọi LLM để dịch và ném lỗi trước khi chạy nhánh nào — "
            "chết cả 5 nhánh. Điền bản dịch tay, hoặc set khoá rồi mở lại app."
        )
        return []
    enabled = ({b: False for b in BRANCHES} | {only_branch: True}
               if only_branch else cfg["branches"])
    try:
        return search_fn(cfg["query"], query_en=cfg["query_en"] or None, top_k=cfg["top_k"],
                         branches=enabled, group_by_shot=cfg["group_by_shot"])
    except Exception as e:
        st.error(f"Search lỗi: {e}")
        return []


# ------------------------------------------------------------ vùng B: một thẻ

def _draw_image(ev, frame_idx) -> None:
    if ev.image and ev.image.exists():
        st.image(str(ev.image), use_container_width=True)
        return
    st.markdown(
        f"<div style='background:#2b2b2b;color:#bbb;padding:14px;border-radius:6px;"
        f"text-align:center;font-size:12px;line-height:1.5'>không có ảnh<br>"
        f"<b>{frame_idx if frame_idx is not None else '?'}</b></div>",
        unsafe_allow_html=True,
    )


def draw_card(row: dict, cfg: dict, query_id: str, index: LabelIndex, key: str) -> None:
    """Một kết quả: ảnh + thứ hạng từng nhánh + nút chấm nhãn."""
    kf_id = row.get("keyframe_id") or ""
    video_id = row.get("video_id") or ""
    frame_idx = row.get("frame_idx")
    ev = evidence_of(kf_id)   # gọi MỘT lần, dùng lại cho cả ảnh lẫn nút "cả shot"

    left, right = st.columns([1, 3])
    with left:
        _draw_image(ev, frame_idx)
    with right:
        st.markdown(f"**{kf_id}** · `{video_id}` · shot `{row.get('shot_id') or '—'}`")
        # frame_idx in ĐẬM: đây là con số duy nhất BTC chấm
        st.markdown(f"frame **{frame_idx}** · điểm {row.get('score', 0):.4f}")

        # Hai nguồn cùng nói về một con số: search (Milvus/docs_bm25) và frame_map.
        # Lệch thì nhãn ghi một số mà panel bằng chứng hiện số khác — phải nói ra. Ở
        # chế độ offline lệch là BÌNH THƯỜNG: keyframe tự trích và keyframe BTC cách
        # nhau trung vị 11 frame (frame_drift), không phải lỗi.
        if frame_idx is not None and ev.frame_idx is not None and ev.frame_idx != frame_idx:
            st.caption(f"⚠️ frame_map nói **{ev.frame_idx}** "
                       f"(lệch {ev.frame_idx - frame_idx:+d}) — nhãn ghi theo số đang "
                       "hiện. Không chắc thì bấm **✓ Cả shot**.")

        ranks = row.get("ranks") or {}
        if ranks:
            st.caption(" · ".join(f"{b}#{ranks[b]}" for b in BRANCHES if b in ranks))
        elif cfg["mode"] == "live":
            st.caption("(search không trả `ranks` — không phân tích được nhánh nào đóng góp)")
        if row.get("snippet"):
            st.caption(row["snippet"])

        if frame_idx is None:
            st.caption("Không có frame_idx — không chấm nhãn được cho kết quả này.")
            return

        moment = cfg["moment"] - 1 if cfg["task"] == "TRAKE" else None
        base = {"query_id": query_id, "query_vi": cfg["query"], "task_type": cfg["task"],
                "video_id": video_id, "kf_id": kf_id, "shot_id": row.get("shot_id"),
                "moment_idx": moment,
                # N của đề TRAKE — mẫu số lúc chấm. Xem `LabelIndex.n_moments()`.
                "n_moments_total": cfg.get("n_moments_total") if cfg["task"] == "TRAKE" else None,
                # Chấm toàn bộ từ offline sẽ làm lệch bộ nhãn (báo cáo D2.1 §10.3),
                # và chỉ cột này phát hiện ra được.
                "source": f"debug_ui/{cfg['mode']}"}

        def save(label: str, start: int, end: int, **extra) -> None:
            append_label(Label(frame_start=start, frame_end=end, label=label,
                               labeler=LABELER, **{**base, **extra}))
            st.rerun()

        current = index.label_of_frame(query_id, video_id, frame_idx, moment_idx=moment)

        b1, b2, b3, b4 = st.columns(4)
        with b1:
            if st.button("✓ Đúng", key=f"ok{key}", use_container_width=True):
                save("correct", frame_idx, frame_idx)
        with b2:
            if st.button("✗ Sai", key=f"no{key}", use_container_width=True):
                save("wrong", frame_idx, frame_idx)
        with b3:
            if st.button("? Chưa chắc", key=f"maybe{key}", use_container_width=True):
                save("unsure", frame_idx, frame_idx)
        with b4:
            # ⚠️ Cả shot rộng trung vị 69 frame, còn cửa sổ đáp án của BTC thì HẸP —
            # riêng TRAKE là DƯỚI 10 frame (docs/contest.md). Nhãn rộng gấp ~7 lần đáp
            # án thật thì eval nhận cả những frame BTC loại → điểm cao hơn lúc thi.
            # Dùng cho KIS/Q&A khi không chắc frame nào trong shot; đừng dùng cho TRAKE.
            rong = cfg["task"] == "TRAKE"
            if ev.shot_bounds and st.button(
                "✓ Cả shot", key=f"shot{key}", use_container_width=True, disabled=rong,
                help=("TRAKE có cửa sổ dưới 10 frame — nhãn cả shot (~69 frame) sẽ "
                      "cho điểm cao hơn thật. Khoanh tay từng khoảnh khắc."
                      if rong else
                      "Đánh dấu đúng cả khoảng shot — một cú bấm ra hàng chục frame nhãn"),
            ):
                save("correct", *ev.shot_bounds)

        if cfg["task"] == "QA":
            _answer_judgment(row, save, key, current)

        if current:
            st.caption(f"{LABEL_ICON[current]} đã chấm: **{current}**")


def _answer_judgment(row: dict, save, key: str, frame_label: str | None) -> None:
    """Chấm câu trả lời — cửa tử THỨ HAI của Q&A, độc lập với cửa frame.

    BTC: `R-Score = I(video ∧ frame ∈ [s,e] ∧ answer đúng ngữ nghĩa)`. Frame đúng mà
    answer sai vẫn 0 điểm, nên phải chấm riêng chứ không suy ra từ nhãn frame.

    ⚠️ Hai nút dưới ghi ra CÙNG MỘT `Label.key` với nhóm nút chấm frame ở trên
    `(query_id, video_id, frame_start, frame_end, moment_idx)`. Bản trước đặt thẳng
    `label="correct"`/`"wrong"` theo phán quyết ANSWER, nên phán answer đè mất phán
    quyết FRAME: bấm "✗ Sai" (frame sai) rồi bấm "✓ Answer đúng" là frame lật thành
    `correct`, `eval.py` chấm dòng đó 1.0 trong khi BTC chấm 0.

    Sửa: verdict answer chỉ đi vào ô `answer_correct`; ô `label` GIỮ NGUYÊN thứ người
    chấm đã phán về frame. Chưa phán frame thì ghi `unsure` — nhãn không cho điểm, nên
    ca xấu nhất là điểm thấp hơn thật, chứ không phải cao hơn. Chiều ngược lại (chấm
    frame sau, xoá mất answer) do `labels._merge()` chặn.

    Ô nhập tay chứ không chỉ đọc từ kết quả search: backend/tasks/qa.py (C3.1) chưa
    có, run_minimal.py đang điền "CHUA_CO_ANSWER". Gõ tay được thì soạn đáp án cho
    dev set ngay bây giờ, không phải đợi.
    """
    text = st.text_input(
        "Câu trả lời (Q&A)", value=row.get("answer_text") or "", key=f"ans{key}",
        placeholder="vd: màu xanh · 5 · Nguyễn Văn A",
    )
    if not text.strip():
        st.caption("Gõ câu trả lời rồi mới chấm được cửa thứ hai.")
        return

    verdict = frame_label or "unsure"
    if frame_label is None:
        st.caption("Chưa phán frame → nhãn ghi `unsure`, chưa cho điểm. "
                   "Bấm **✓ Đúng**/**✗ Sai** ở trên để chốt cửa thứ nhất.")

    c1, c2 = st.columns(2)
    frame_idx = row["frame_idx"]
    with c1:
        if st.button("✓ Answer đúng", key=f"ansok{key}", use_container_width=True):
            save(verdict, frame_idx, frame_idx, answer_text=text, answer_correct=True)
    with c2:
        if st.button("✗ Answer sai", key=f"ansno{key}", use_container_width=True):
            save(verdict, frame_idx, frame_idx, answer_text=text, answer_correct=False)


# ------------------------------------------------- vùng C: bằng chứng một frame

def draw_evidence(kf_id: str) -> None:
    ev = evidence_of(kf_id)

    st.subheader("Bằng chứng")
    for w in ev.warnings:
        st.warning(w)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("frame_idx", ev.frame_idx if ev.frame_idx is not None else "—",
              help="Con số DUY NHẤT BTC chấm. Không phải số thứ tự keyframe.")
    c2.metric("thời điểm", f"{ev.timestamp_s}s" if ev.timestamp_s is not None else "—")
    c3.metric("shot", str(ev.shot_bounds) if ev.shot_bounds else "—")
    c4.metric("độ dài video", ev.n_frames or "—")

    st.caption(f"id BTC `{ev.kf_id_btc}` · id tự trích `{ev.kf_id_own}`")

    if ev.shot_id:
        siblings = keyframes_in_shot(ev.video_id, ev.shot_id)
        if len(siblings) > 1:
            st.caption("**Cùng shot:** " + " · ".join(
                f"**{s['frame_idx']}**" if s["kf_id"] == ev.kf_id_own else str(s["frame_idx"])
                for s in siblings
            ))

    t1, t2, t3, t4 = st.tabs(["OCR", "ASR", "doc_text (BM25)", "Objects"])
    with t1:
        _tab_ocr(ev)
    with t2:
        _tab_asr(ev)
    with t3:
        _tab_doc_text(ev)
    with t4:
        # Không phải "chưa nối" mà là CHƯA CÓ DỮ LIỆU. Nói đúng nguyên nhân, nếu không
        # người dùng sẽ đi dựng Docker rồi vẫn thấy trống.
        st.caption(
            "Chưa có dữ liệu objects — BTC có phát (1 JSON/keyframe) nhưng chưa tải "
            "về: không có `data/derived/objects.parquet`, cũng không có "
            "`data/sample/objects.json`.\n\n"
            "Lưu ý khi có: số lượng object bị BÃO HOÀ ở 100/keyframe — đừng dùng nó "
            "làm tín hiệu xếp hạng."
        )


def _tab_ocr(ev) -> None:
    if not ev.ocr:
        st.caption("Không có chữ nào đọc được ở frame này.")
    # Khoá widget theo kf_id + thứ tự. Dùng id() của dict là sai: đó là địa chỉ bộ
    # nhớ, được cấp lại sau GC, nên hai lần vẽ khác nhau có thể trùng khoá.
    for i, o in enumerate(ev.ocr):
        a, b = st.columns(2)
        # text_raw cạnh text_clean: bất biến B1.4 là giữ nguyên text_raw vì LLM đôi
        # khi "sửa" hỏng tên riêng — muốn thấy nó sửa gì thì phải nhìn được cả hai.
        a.text_area("text_raw", str(o["text_raw"]), height=90,
                    key=f"ocr_raw_{ev.kf_id_btc}_{i}")
        b.text_area("text_clean", str(o["text_clean"]), height=90,
                    key=f"ocr_clean_{ev.kf_id_btc}_{i}")
        st.caption(f"{o['n_boxes']} vùng chữ · độ tin cậy TB {o['avg_conf']}")


def _tab_asr(ev) -> None:
    if not ev.asr:
        st.caption("Không có lời nói nào quanh frame này.")
    for a in ev.asr:
        tag = "🔊 ngay tại frame" if a["direct"] else "· gần đó (±3s)"
        st.markdown(f"**{a['start_s']:.1f}s–{a['end_s']:.1f}s** {tag}")
        st.write(a["text_vi"])


def _tab_doc_text(ev) -> None:
    if not ev.doc_text:
        st.caption("Không có — cầu nối `clip_kf_map` thiếu dòng cho keyframe này "
                   "(6% keyframe BTC rơi vào diện này).")
        return
    st.caption("Đây là NGUYÊN VĂN thứ BM25 nhìn thấy ở frame này.")
    st.text_area("doc_text", ev.doc_text, height=220, key=f"doc_{ev.kf_id_btc}")


def _tab_branches(cfg: dict) -> None:
    if cfg["mode"] == "offline":
        st.info("Chế độ offline chỉ có một nhánh (BM25 trên doc_text).")
        return
    st.caption("Mỗi nhánh gọi lại `search()` với đúng nhánh đó bật — "
               "không viết lại logic truy xuất trong UI.")
    for col, branch in zip(st.columns(len(BRANCHES)), BRANCHES):
        with col:
            st.markdown(f"**{branch}**")
            if st.button("chạy", key=f"go_{branch}"):
                st.session_state[f"hits_{branch}"] = run_search(cfg, only_branch=branch)
            for j, r in enumerate(st.session_state.get(f"hits_{branch}", [])[:10]):
                st.caption(f"{j + 1}. {r.get('keyframe_id')} · {r.get('score', 0):.4f}")


# ----------------------------------------------------------------------- main

def _empty_state() -> None:
    st.info("Gõ một truy vấn ở thanh bên trái rồi bấm **Tìm kiếm**.")
    index = LabelIndex()
    st.caption(f"Đang có **{len(index)}** nhãn trong `{DEV_SET_DIR}` "
               f"trên {len(index.query_ids())} truy vấn.")


def main() -> None:
    cfg = sidebar()
    st.title("UI debug — AIC 2026")

    if not cfg["query"].strip():
        _empty_state()
        return

    query_id = query_id_of(cfg["query"])
    st.caption(f"`query_id` = **{query_id}** — nhãn của câu này luôn gom về một chỗ.")

    # CHỈ chạy khi bấm nút: Streamlit vẽ lại trang sau MỌI thao tác, kể cả lúc bấm nút
    # chấm nhãn — tự chạy search là bắt đợi ~14 giây mỗi lần chạm bàn phím.
    if cfg["run"]:
        with st.spinner("Đang tìm…"):
            st.session_state["hits"] = run_search(cfg)
        st.session_state["hits_query"] = cfg["query"]

    hits = st.session_state.get("hits", [])
    if not hits:
        if cfg["run"]:
            st.warning("Không có kết quả. Thử chế độ offline, hoặc kiểm Milvus/Elasticsearch.")
        else:
            st.info("Bấm **Tìm kiếm** ở thanh bên trái.")
        return

    if st.session_state.get("hits_query") != cfg["query"]:
        st.warning("Kết quả đang hiện là của truy vấn TRƯỚC — bấm Tìm kiếm để chạy lại.")

    index = LabelIndex()   # dựng lại sau mỗi lần vẽ: nhãn vừa ghi phải hiện ra ngay
    tab_rrf, tab_branch, tab_rerank = st.tabs(
        ["Sau hợp nhất (RRF)", "Từng nhánh riêng", "Sau rerank"]
    )

    with tab_rrf:
        for i, row in enumerate(hits):
            with st.container(border=True):
                st.caption(f"hạng {i + 1}")
                draw_card(row, cfg, query_id, index, key=f"rrf{i}")

    with tab_branch:
        _tab_branches(cfg)

    with tab_rerank:
        st.info("Rerank (A2.4) chưa bật. Khung để sẵn — có rerank là tự có dữ liệu.")

    st.divider()
    chosen = st.selectbox("Soi bằng chứng của keyframe",
                          [r.get("keyframe_id") for r in hits], index=0)
    if chosen:
        draw_evidence(chosen)


main()
