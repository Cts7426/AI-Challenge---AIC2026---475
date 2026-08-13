# app/debug_ui.py — D2.1: UI debug (Streamlit).  Chạy: streamlit run app/debug_ui.py
#
# File này CHỈ VẼ. Logic nằm ở app/labels.py, app/evidence.py, app/offline_search.py —
# ba module thường, có test. Streamlit không chạy trong pytest, nhét logic vào đây là
# vừa mất test vừa buộc E4.2/D3.5 viết lại (viết lại = lệch nhau).
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

from app.evidence import bang_chung, keyframe_cung_shot  # noqa: E402
from app.labels import BangNhan, Label, ghi_nhan  # noqa: E402
from app.offline_search import tim as tim_offline  # noqa: E402
from data.config.debug_ui import (  # noqa: E402
    DEV_SET_DIR,
    KEYFRAMES_DIR,
    LABELER,
    TOP_K_MAC_DINH,
)

st.set_page_config(page_title="AIC 2026 · UI debug", layout="wide")

NHANH = ("vector", "metadata", "objects", "ocr", "asr")
MAU_NHAN = {"correct": "🟢", "wrong": "🔴", "unsure": "🟡"}


# --------------------------------------------------------------- tiện ích nhỏ

def query_id_cua(q: str) -> str:
    """`query_id` ổn định từ câu truy vấn, để nhãn của cùng một câu gom về một chỗ.

    Băm thay vì dùng nguyên câu: gõ thừa một dấu cách là thành query khác, nhãn
    tách làm hai đống.
    """
    return "q_" + hashlib.sha1(q.strip().lower().encode("utf-8")).hexdigest()[:8]


# Gói mà chế độ live BẮT BUỘC phải có → tên hiển thị khi thiếu.
GOI_CAN_CHO_LIVE = {
    "elasticsearch": "elasticsearch",   # nhánh metadata/ocr/asr/objects
    "pymilvus": "pymilvus",             # nhánh vector
    "torch": "torch",                   # encode câu hỏi
    "open_clip": "open_clip_torch",
}


@st.cache_resource(show_spinner=False)
def _tang_search():
    """(hàm search, danh sách gói còn thiếu). Thiếu gói nào thì live không chạy được.

    Phải kiểm TỪNG GÓI chứ không chỉ thử `import backend.retrieval.search`: module đó
    nạp lười (`import torch` nằm trong thân hàm) nên nó import trót lọt trên máy trắng
    trơn. Chỉ dựa vào phép import ấy thì UI mặc định chọn `live`, người dùng bấm Tìm
    kiếm rồi mới nhận lỗi — trong khi biết trước được từ lúc mở app.
    """
    import importlib.util

    thieu = [pip for mod, pip in GOI_CAN_CHO_LIVE.items()
             if importlib.util.find_spec(mod) is None]
    try:
        from backend.retrieval.search import search
    except Exception as e:
        print(f"  [cảnh báo] không nạp được backend.retrieval.search: {e}")
        return None, thieu
    return search, thieu


def _bang_nhan() -> BangNhan:
    """Dựng lại chỉ mục nhãn sau mỗi lần vẽ — nhãn vừa ghi phải hiện ra ngay."""
    return BangNhan()


# --------------------------------------------------------------- vùng A: sidebar

def sidebar() -> dict:
    st.sidebar.title("Điều khiển")

    q = st.sidebar.text_area("Truy vấn (tiếng Việt)", height=80,
                             placeholder="thủ môn cản phá quả penalty")
    # Bỏ trống ô này thì `search()` gọi `translate_to_english()` → `llm()`. Không có
    # khoá API thì `llm()` ném RuntimeError TRƯỚC khi nhánh nào chạy, nên chết cả 5
    # nhánh chứ không riêng nhánh vector. Nói trước còn hơn để người dùng nhận một
    # vệt stack trace không liên quan gì tới điều họ vừa bấm.
    co_khoa = bool(os.environ.get("ANTHROPIC_API_KEY")) or os.environ.get("LLM_BACKEND") == "local"
    q_en = st.sidebar.text_input(
        "Bản dịch tiếng Anh" + ("" if co_khoa else " — BẮT BUỘC"),
        help="CLIP nhận tiếng Anh. Có ANTHROPIC_API_KEY thì để trống, hệ tự dịch.",
    )
    task = st.sidebar.selectbox("Dạng bài", ("KIS", "QA", "TRAKE"))
    top_k = st.sidebar.slider("Số kết quả", 5, 100, TOP_K_MAC_DINH, step=5)

    search, thieu_goi = _tang_search()
    co_search = search is not None and not thieu_goi
    che_do = st.sidebar.radio(
        "Nguồn kết quả",
        ("live", "offline"),
        index=0 if co_search else 1,
        help="live = search thật (cần Milvus + Elasticsearch). "
             "offline = BM25 trên docs_bm25.parquet, ~14 giây/truy vấn, không cần Docker.",
    )
    if che_do == "live" and thieu_goi:
        st.sidebar.error(
            "Chế độ live thiếu gói: **" + "**, **".join(thieu_goi) + "**\n\n"
            "`pip install " + " ".join(thieu_goi) + "`\n\n"
            "torch dùng bản CPU: `pip install torch --index-url "
            "https://download.pytorch.org/whl/cpu`"
        )
    elif che_do == "live" and search is None:
        st.sidebar.error("Không nạp được tầng search — hãy dùng chế độ offline.")

    # Offline chỉ có MỘT nguồn (BM25 trên doc_text) nên mấy ô dưới không có tác dụng.
    # Khoá lại thay vì để bật được: ô bật mà không đổi gì là lời nói dối về công cụ
    # chẩn đoán — người dùng tưởng đã tắt vector rồi kết luận sai về nguồn nào gánh điểm.
    khoa = che_do == "offline"
    st.sidebar.markdown("**Bật/tắt từng nhánh**")
    if khoa:
        st.sidebar.caption("Chế độ offline chỉ có một nguồn — các ô dưới bị khoá.")
    bat = {
        n: st.sidebar.checkbox(n, value=True, key=f"nhanh_{n}", disabled=khoa) for n in NHANH
    }
    gom_shot = st.sidebar.checkbox(
        "Gom về shot", value=True, disabled=khoa,
        help="Tắt để xem các keyframe liền nhau trong cùng một shot — kiểm xem phép "
             "gom có nuốt mất keyframe đúng không.",
    )

    st.sidebar.divider()
    st.sidebar.caption(f"Người chấm: **{LABELER}** · nhãn ghi vào `{DEV_SET_DIR.name}/`")
    if LABELER == "unknown":
        st.sidebar.warning("Chưa đặt tên người chấm. Set biến môi trường `AIC_LABELER`.")
    if not KEYFRAMES_DIR.is_dir():
        st.sidebar.info(f"Chưa có ảnh keyframe ở `{KEYFRAMES_DIR}` — sẽ vẽ thẻ xám.")

    chay = st.sidebar.button("Tìm kiếm", type="primary", use_container_width=True)
    return dict(q=q, q_en=q_en, task=task, top_k=top_k, che_do=che_do,
                bat=bat, gom_shot=gom_shot, chay=chay, co_khoa=co_khoa)


# ------------------------------------------------------- gọi search / offline

def chay_search(cf: dict, chi_nhanh: str | None = None) -> list[dict]:
    """Một lượt tìm kiếm → list dict đã chuẩn hoá cho phần vẽ.

    `chi_nhanh` khác None → chỉ bật đúng nhánh đó, bằng cách gọi lại chính `search()`
    thay vì viết lại logic truy xuất trong UI.
    """
    if cf["che_do"] == "offline":
        return [
            {"keyframe_id": r.kf_id, "video_id": r.video_id, "shot_id": r.shot_id,
             "frame_idx": r.frame_idx, "score": r.score, "ranks": {}, "contrib": {},
             "trich": r.trich}
            for r in tim_offline(cf["q"], cf["top_k"])
        ]

    search, thieu_goi = _tang_search()
    if search is None or thieu_goi:
        return []
    if not cf["q_en"].strip() and not cf.get("co_khoa", True):
        st.error(
            "Chưa có `ANTHROPIC_API_KEY` mà ô **Bản dịch tiếng Anh** đang trống. "
            "`search()` sẽ gọi LLM để dịch và ném lỗi trước khi chạy nhánh nào — "
            "chết cả 5 nhánh. Điền bản dịch tay, hoặc set khoá rồi mở lại app."
        )
        return []
    bat = {n: False for n in NHANH} | {chi_nhanh: True} if chi_nhanh else cf["bat"]
    try:
        return search(cf["q"], query_en=cf["q_en"] or None, top_k=cf["top_k"],
                      branches=bat, group_by_shot=cf["gom_shot"])
    except Exception as e:
        st.error(f"Search lỗi: {e}")
        return []


# ------------------------------------------------------------ vùng B: một thẻ

def _ve_anh(bc, frame_idx) -> None:
    if bc.anh and bc.anh.exists():
        st.image(str(bc.anh), use_container_width=True)
        return
    st.markdown(
        f"<div style='background:#2b2b2b;color:#bbb;padding:14px;border-radius:6px;"
        f"text-align:center;font-size:12px;line-height:1.5'>không có ảnh<br>"
        f"<b>{frame_idx if frame_idx is not None else '?'}</b></div>",
        unsafe_allow_html=True,
    )


def ve_the(r: dict, cf: dict, qid: str, bn: BangNhan, khoa: str) -> None:
    """Một kết quả: ảnh + thứ hạng từng nhánh + nút chấm nhãn."""
    kf = r.get("keyframe_id") or ""
    video_id = r.get("video_id") or ""
    frame_idx = r.get("frame_idx")
    bc = bang_chung(kf)  # gọi MỘT lần, dùng lại cho cả ảnh lẫn nút "cả shot"

    c1, c2 = st.columns([1, 3])
    with c1:
        _ve_anh(bc, frame_idx)
    with c2:
        st.markdown(f"**{kf}** · `{video_id}` · shot `{r.get('shot_id') or '—'}`")
        # frame_idx in ĐẬM: đây là con số duy nhất BTC chấm
        st.markdown(f"frame **{frame_idx}** · điểm {r.get('score', 0):.4f}")

        # Hai nguồn cùng nói về một con số: search (Milvus/docs_bm25) và frame_map.
        # Lệch thì nhãn ghi một số mà panel bằng chứng hiện số khác — phải nói ra.
        # Ở chế độ offline lệch là BÌNH THƯỜNG: keyframe tự trích và keyframe BTC
        # cách nhau trung vị 11 frame (frame_drift), không phải lỗi.
        if frame_idx is not None and bc.frame_idx is not None and bc.frame_idx != frame_idx:
            st.caption(f"⚠️ frame_map nói **{bc.frame_idx}** (lệch {bc.frame_idx - frame_idx:+d}) "
                       f"— nhãn ghi theo số đang hiện. Không chắc thì bấm **✓ Cả shot**.")

        ranks = r.get("ranks") or {}
        if ranks:
            st.caption(" · ".join(f"{n}#{ranks[n]}" for n in NHANH if n in ranks))
        elif cf["che_do"] == "live":
            st.caption("(search không trả `ranks` — không phân tích được nhánh nào đóng góp)")
        if r.get("trich"):
            st.caption(r["trich"])

        if frame_idx is None:
            st.caption("Không có frame_idx — không chấm nhãn được cho kết quả này.")
            return

        dat = {"query_id": qid, "query_vi": cf["q"], "task_type": cf["task"],
               "video_id": video_id, "kf_id": kf, "shot_id": r.get("shot_id"),
               # Ghi rõ nhãn này chấm từ nguồn nào: chấm toàn bộ từ offline sẽ làm
               # lệch bộ nhãn (xem báo cáo §10.3), và chỉ cột này phát hiện ra được.
               "source": f"debug_ui/{cf['che_do']}"}

        def cham(nhan: str, s: int, e: int) -> None:
            ghi_nhan(Label(frame_start=s, frame_end=e, label=nhan, labeler=LABELER, **dat))
            st.rerun()

        b1, b2, b3, b4 = st.columns(4)
        with b1:
            if st.button("✓ Đúng", key=f"d{khoa}", use_container_width=True):
                cham("correct", frame_idx, frame_idx)
        with b2:
            if st.button("✗ Sai", key=f"s{khoa}", use_container_width=True):
                cham("wrong", frame_idx, frame_idx)
        with b3:
            if st.button("? Chưa chắc", key=f"c{khoa}", use_container_width=True):
                cham("unsure", frame_idx, frame_idx)
        with b4:
            if bc.shot_bien and st.button("✓ Cả shot", key=f"a{khoa}", use_container_width=True,
                                          help="Đánh dấu đúng cả khoảng shot — "
                                               "một cú bấm ra hàng chục frame nhãn"):
                cham("correct", *bc.shot_bien)

        nhan_hien_tai = bn.nhan_cua_frame(qid, video_id, frame_idx)
        if nhan_hien_tai:
            st.caption(f"{MAU_NHAN[nhan_hien_tai]} đã chấm: **{nhan_hien_tai}**")


# ------------------------------------------------- vùng C: bằng chứng một frame

def ve_bang_chung(kf: str) -> None:
    bc = bang_chung(kf)

    st.subheader("Bằng chứng")
    for c in bc.canh_bao:
        st.warning(c)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("frame_idx", bc.frame_idx if bc.frame_idx is not None else "—",
              help="Con số DUY NHẤT BTC chấm. Không phải số thứ tự keyframe.")
    c2.metric("thời điểm", f"{bc.timestamp_s}s" if bc.timestamp_s is not None else "—")
    c3.metric("shot", str(bc.shot_bien) if bc.shot_bien else "—")
    c4.metric("độ dài video", bc.n_frames_video or "—")

    st.caption(f"id BTC `{bc.kf_id_btc}` · id tự trích `{bc.kf_id_tu_trich}`")

    if bc.shot_id:
        dai = keyframe_cung_shot(bc.video_id, bc.shot_id)
        if len(dai) > 1:
            st.caption("**Cùng shot:** " + " · ".join(
                f"**{d['frame_idx']}**" if d["kf_id"] == bc.kf_id_tu_trich else str(d["frame_idx"])
                for d in dai
            ))

    t1, t2, t3, t4 = st.tabs(["OCR", "ASR", "doc_text (BM25)", "Objects"])
    with t1:
        _tab_ocr(bc)
    with t2:
        _tab_asr(bc)
    with t3:
        _tab_doc_text(bc)
    with t4:
        # Không phải "chưa nối" mà là CHƯA CÓ DỮ LIỆU: không có objects.parquet, cũng
        # không có data/sample/objects.json (đường dẫn mặc định của load_objects.py).
        # Nói đúng nguyên nhân, nếu không người dùng sẽ đi dựng Docker rồi vẫn trống.
        st.caption(
            "Chưa có dữ liệu objects — không có `data/derived/objects.parquet`, cũng "
            "không có `data/sample/objects.json`. Dựng Elasticsearch cũng chưa nạp "
            "được gì, phải chờ Data Factory sinh nguồn trước.\n\n"
            "Lưu ý khi có: số lượng object bị BÃO HOÀ ở 100/keyframe — đừng dùng nó "
            "làm tín hiệu xếp hạng."
        )


def _tab_ocr(bc) -> None:
    if not bc.ocr:
        st.caption("Không có chữ nào đọc được ở frame này.")
    # Khoá widget theo kf_id + thứ tự. Dùng id() của dict là sai: đó là địa chỉ bộ
    # nhớ, được cấp lại sau khi GC, nên hai lần vẽ khác nhau có thể trùng khoá.
    for i, o in enumerate(bc.ocr):
        a, b = st.columns(2)
        # text_raw cạnh text_clean: bất biến B1.4 là giữ nguyên text_raw vì LLM đôi
        # khi "sửa" hỏng tên riêng — muốn thấy nó sửa gì thì phải nhìn được cả hai.
        a.text_area("text_raw", str(o["text_raw"]), height=90, key=f"ocr_raw_{bc.kf_id_btc}_{i}")
        b.text_area("text_clean", str(o["text_clean"]), height=90,
                    key=f"ocr_clean_{bc.kf_id_btc}_{i}")
        st.caption(f"{o['n_boxes']} vùng chữ · độ tin cậy TB {o['avg_conf']}")


def _tab_asr(bc) -> None:
    if not bc.asr:
        st.caption("Không có lời nói nào quanh frame này.")
    for a in bc.asr:
        nhan = "🔊 ngay tại frame" if a["truc_tiep"] else "· gần đó (±3s)"
        st.markdown(f"**{a['start_s']:.1f}s–{a['end_s']:.1f}s** {nhan}")
        st.write(a["text_vi"])


def _tab_doc_text(bc) -> None:
    if not bc.doc_text:
        st.caption("Không có — cầu nối `clip_kf_map` thiếu dòng cho keyframe này "
                   "(6% keyframe BTC rơi vào diện này).")
        return
    st.caption("Đây là NGUYÊN VĂN thứ BM25 nhìn thấy ở frame này.")
    st.text_area("doc_text", bc.doc_text, height=220, key=f"doc_{bc.kf_id_btc}")


# ----------------------------------------------------------------------- main

def _man_hinh_trong() -> None:
    st.info("Gõ một truy vấn ở thanh bên trái rồi bấm **Tìm kiếm**.")
    bn = _bang_nhan()
    st.caption(f"Đang có **{len(bn)}** nhãn trong `{DEV_SET_DIR}` "
               f"trên {len(bn.cac_query())} truy vấn.")


def main() -> None:
    cf = sidebar()
    st.title("UI debug — AIC 2026")

    if not cf["q"].strip():
        _man_hinh_trong()
        return

    qid = query_id_cua(cf["q"])
    st.caption(f"`query_id` = **{qid}** — nhãn của câu này luôn gom về một chỗ.")

    # CHỈ chạy khi bấm nút: Streamlit vẽ lại trang sau MỌI thao tác, kể cả lúc bấm
    # nút chấm nhãn — tự chạy search là bắt đợi ~18 giây mỗi lần chạm bàn phím.
    if cf["chay"]:
        with st.spinner("Đang tìm…"):
            st.session_state["kq"] = chay_search(cf)
        st.session_state["kq_q"] = cf["q"]

    kq = st.session_state.get("kq", [])
    if not kq:
        if cf["chay"]:
            st.warning("Không có kết quả. Thử chế độ offline, hoặc kiểm Milvus/Elasticsearch.")
        else:
            st.info("Bấm **Tìm kiếm** ở thanh bên trái.")
        return

    if st.session_state.get("kq_q") != cf["q"]:
        st.warning("Kết quả đang hiện là của truy vấn TRƯỚC — bấm Tìm kiếm để chạy lại.")

    bn = _bang_nhan()
    tab_rrf, tab_nhanh, tab_rerank = st.tabs(
        ["Sau hợp nhất (RRF)", "Từng nhánh riêng", "Sau rerank"]
    )

    with tab_rrf:
        for i, r in enumerate(kq):
            with st.container(border=True):
                st.caption(f"hạng {i + 1}")
                ve_the(r, cf, qid, bn, khoa=f"rrf{i}")

    with tab_nhanh:
        _tab_tung_nhanh(cf)

    with tab_rerank:
        st.info("Rerank (A2.4) chưa bật. Khung để sẵn — có rerank là tự có dữ liệu.")

    st.divider()
    chon = st.selectbox("Soi bằng chứng của keyframe",
                        [r.get("keyframe_id") for r in kq], index=0)
    if chon:
        ve_bang_chung(chon)


def _tab_tung_nhanh(cf: dict) -> None:
    if cf["che_do"] == "offline":
        st.info("Chế độ offline chỉ có một nhánh (BM25 trên doc_text).")
        return
    st.caption("Mỗi nhánh gọi lại `search()` với đúng nhánh đó bật — "
               "không viết lại logic truy xuất trong UI.")
    for c, nhanh in zip(st.columns(len(NHANH)), NHANH):
        with c:
            st.markdown(f"**{nhanh}**")
            if st.button("chạy", key=f"go_{nhanh}"):
                st.session_state[f"kq_{nhanh}"] = chay_search(cf, chi_nhanh=nhanh)
            for j, r in enumerate(st.session_state.get(f"kq_{nhanh}", [])[:10]):
                st.caption(f"{j + 1}. {r.get('keyframe_id')} · {r.get('score', 0):.4f}")


main()
