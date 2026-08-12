# app/debug_ui.py — D2.1: UI debug (Streamlit)
#
# Chạy:  streamlit run app/debug_ui.py
#
# ===== File này CHỈ VẼ =====
# Mọi logic nằm ở module thường và có test:
#   app/labels.py         — đọc/ghi nhãn, hàm chấm điểm dùng chung với E4.2 và D3.5
#   app/evidence.py       — gom bằng chứng, cầu nối hai hệ tên keyframe
#   app/offline_search.py — BM25 thô khi không có Docker
# Streamlit không chạy trong pytest. Nhét logic vào đây là vừa mất test, vừa buộc
# E4.2/D3.5 phải viết lại — mà viết lại là lệch nhau.
#
# ===== UI này trả lời ba câu =====
#   1. Frame này lên hạng nhờ NGUỒN NÀO?     → thứ hạng từng nhánh (`ranks` của A2.2)
#   2. Frame này thật sự CHỨA GÌ?            → OCR · ASR · doc_text · ảnh
#   3. Kết quả này ĐÚNG hay SAI?             → nút chấm, ghi vào dev_set/
# Câu 3 mới là lý do tồn tại: nhãn sinh ra ở đây là đề tự chấm của cả nhóm, và là
# đầu vào bắt buộc của E4.2 (eval) lẫn D3.5 (mô phỏng chấm điểm).
#
# ===== KHÔNG nằm trên đường chạy lúc thi =====
# Đây là công cụ dev. Nó không sinh file nộp, không đụng vào tầng export.

from __future__ import annotations

import hashlib
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


# --------------------------------------------------------------- tiện ích nhỏ

def query_id_cua(q: str) -> str:
    """Sinh `query_id` ổn định từ câu truy vấn.

    Ổn định để nhãn của cùng một câu hỏi luôn gom về một chỗ giữa các phiên. Dùng
    hash chứ không dùng nguyên câu: gõ thừa một dấu cách là thành query khác, nhãn
    tách làm hai đống.
    """
    return "q_" + hashlib.sha1(q.strip().lower().encode("utf-8")).hexdigest()[:8]


@st.cache_resource(show_spinner=False)
def _tang_search():
    """Nạp tầng search thật. Thiếu Milvus/ES/torch → trả None, UI lùi về offline."""
    try:
        from backend.retrieval.search import search

        return search
    except Exception as e:  # thiếu gói, thiếu service...
        print(f"  [cảnh báo] không nạp được backend.retrieval.search: {e}")
        return None


def _bang_nhan() -> BangNhan:
    """Dựng lại chỉ mục nhãn sau mỗi lần bấm — nhãn vừa ghi phải hiện ra ngay."""
    return BangNhan()


# --------------------------------------------------------------- vùng A: sidebar

def sidebar() -> dict:
    st.sidebar.title("Điều khiển")

    q = st.sidebar.text_area("Truy vấn (tiếng Việt)", height=80,
                             placeholder="thủ môn cản phá quả penalty")
    q_en = st.sidebar.text_input(
        "Bản dịch tiếng Anh (tuỳ chọn)",
        help="Chưa set ANTHROPIC_API_KEY thì nên điền tay — CLIP nhận tiếng Anh.",
    )
    task = st.sidebar.selectbox("Dạng bài", ("KIS", "QA", "TRAKE"))
    top_k = st.sidebar.slider("Số kết quả", 5, 100, TOP_K_MAC_DINH, step=5)

    co_search = _tang_search() is not None
    che_do = st.sidebar.radio(
        "Nguồn kết quả",
        ("live", "offline"),
        index=0 if co_search else 1,
        help="live = search thật (cần Milvus + Elasticsearch). "
             "offline = BM25 thô trên docs_bm25.parquet, ~8 giây/truy vấn, không cần Docker.",
    )
    if che_do == "live" and not co_search:
        st.sidebar.error("Không nạp được tầng search — hãy dùng chế độ offline.")

    st.sidebar.markdown("**Bật/tắt từng nhánh**")
    bat = {n: st.sidebar.checkbox(n, value=True, key=f"nhanh_{n}") for n in NHANH}
    gom_shot = st.sidebar.checkbox(
        "Gom về shot", value=True,
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
                bat=bat, gom_shot=gom_shot, chay=chay)


# ------------------------------------------------------- gọi search / offline

def chay_search(cf: dict, chi_nhanh: str | None = None) -> list[dict]:
    """Chạy một lượt tìm kiếm, trả list dict đã chuẩn hoá cho phần vẽ.

    `chi_nhanh` khác None → chỉ bật đúng nhánh đó. Dùng cho cột "từng nhánh riêng":
    gọi lại chính `search()` thay vì viết lại logic truy xuất trong UI.
    """
    if cf["che_do"] == "offline":
        return [
            {"keyframe_id": r.kf_id, "video_id": r.video_id, "shot_id": r.shot_id,
             "frame_idx": r.frame_idx, "score": r.score, "ranks": {}, "contrib": {},
             "trich": r.trich}
            for r in tim_offline(cf["q"], cf["top_k"])
        ]

    search = _tang_search()
    if search is None:
        return []
    bat = {n: False for n in NHANH} | {chi_nhanh: True} if chi_nhanh else cf["bat"]
    try:
        return search(cf["q"], query_en=cf["q_en"] or None, top_k=cf["top_k"],
                      branches=bat, group_by_shot=cf["gom_shot"])
    except Exception as e:
        st.error(f"Search lỗi: {e}")
        return []


# ------------------------------------------------------------ vùng B: một thẻ

def ve_the(r: dict, cf: dict, qid: str, bn: BangNhan, khoa: str) -> None:
    """Một kết quả: ảnh + thứ hạng từng nhánh + nút chấm nhãn."""
    kf = r.get("keyframe_id") or ""
    video_id = r.get("video_id") or ""
    frame_idx = r.get("frame_idx")

    c1, c2 = st.columns([1, 3])
    with c1:
        bc = bang_chung(kf)
        if bc.anh and bc.anh.exists():
            st.image(str(bc.anh), use_container_width=True)
        else:
            st.markdown(
                f"<div style='background:#2b2b2b;color:#bbb;padding:14px;border-radius:6px;"
                f"text-align:center;font-size:12px;line-height:1.5'>không có ảnh<br>"
                f"<b>{frame_idx if frame_idx is not None else '?'}</b></div>",
                unsafe_allow_html=True,
            )
    with c2:
        st.markdown(f"**{kf}** · `{video_id}` · shot `{r.get('shot_id') or '—'}`")
        # frame_idx in ĐẬM: đây là con số duy nhất BTC chấm
        st.markdown(f"frame **{frame_idx}** · điểm {r.get('score', 0):.4f}")

        ranks = r.get("ranks") or {}
        if ranks:
            st.caption(" · ".join(f"{n}#{ranks[n]}" for n in NHANH if n in ranks))
        elif cf["che_do"] == "live":
            st.caption("(search không trả `ranks` — không phân tích được nhánh nào đóng góp)")
        if r.get("trich"):
            st.caption(r["trich"])

        nhan_hien_tai = (
            bn.nhan_cua_frame(qid, video_id, frame_idx) if frame_idx is not None else None
        )
        b1, b2, b3, b4 = st.columns(4)
        dat = {"query_id": qid, "query_vi": cf["q"], "task_type": cf["task"],
               "video_id": video_id, "kf_id": kf, "shot_id": r.get("shot_id")}

        def cham(nhan: str, s: int, e: int) -> None:
            ghi_nhan(Label(frame_start=s, frame_end=e, label=nhan, labeler=LABELER, **dat))
            st.rerun()

        if frame_idx is not None:
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
                bc2 = bang_chung(kf)
                if bc2.shot_bien and st.button("✓ Cả shot", key=f"a{khoa}",
                                               use_container_width=True,
                                               help="Đánh dấu đúng cả khoảng shot — "
                                                    "một cú bấm ra hàng chục frame nhãn"):
                    cham("correct", *bc2.shot_bien)

        if nhan_hien_tai:
            mau = {"correct": "🟢", "wrong": "🔴", "unsure": "🟡"}[nhan_hien_tai]
            st.caption(f"{mau} đã chấm: **{nhan_hien_tai}**")


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
        if not bc.ocr:
            st.caption("Không có chữ nào đọc được ở frame này.")
        for o in bc.ocr:
            a, b = st.columns(2)
            # text_raw và text_clean CẠNH NHAU: bất biến B1.4 là giữ nguyên text_raw
            # vì LLM đôi khi "sửa" hỏng tên riêng — muốn thấy nó sửa gì thì phải
            # nhìn được cả hai
            a.text_area("text_raw", str(o["text_raw"]), height=90, key=f"r{id(o)}")
            b.text_area("text_clean", str(o["text_clean"]), height=90, key=f"c{id(o)}")
            st.caption(f"{o['n_boxes']} vùng chữ · độ tin cậy TB {o['avg_conf']}")
    with t2:
        if not bc.asr:
            st.caption("Không có lời nói nào quanh frame này.")
        for a in bc.asr:
            nhan = "🔊 ngay tại frame" if a["truc_tiep"] else "· gần đó (±3s)"
            st.markdown(f"**{a['start_s']:.1f}s–{a['end_s']:.1f}s** {nhan}")
            st.write(a["text_vi"])
    with t3:
        if bc.doc_text:
            st.caption("Đây là NGUYÊN VĂN thứ BM25 nhìn thấy ở frame này.")
            st.text_area("doc_text", bc.doc_text, height=220, key="doc")
        else:
            st.caption("Không có — cầu nối `clip_kf_map` thiếu dòng cho keyframe này "
                       "(6% keyframe BTC rơi vào diện này).")
    with t4:
        st.caption("Objects nằm trong Elasticsearch, chưa nối vào UI. "
                   "Lưu ý: số lượng object bị BÃO HOÀ ở 100/keyframe — đừng dùng nó làm tín hiệu.")


# ----------------------------------------------------------------------- main

def main() -> None:
    cf = sidebar()
    st.title("UI debug — AIC 2026")

    if not cf["q"].strip():
        st.info("Gõ một truy vấn ở thanh bên trái rồi bấm **Tìm kiếm**.")
        bn = _bang_nhan()
        st.caption(f"Đang có **{len(bn)}** nhãn trong `{DEV_SET_DIR}` "
                   f"trên {len(bn.cac_query())} truy vấn.")
        return

    qid = query_id_cua(cf["q"])
    st.caption(f"`query_id` = **{qid}** — nhãn của câu này luôn gom về một chỗ.")

    # CHỈ chạy khi bấm nút. Chạy tự động lúc vừa gõ xong chữ đầu là bắt người dùng
    # đợi 8 giây mỗi lần chạm bàn phím ở chế độ offline — và Streamlit vẽ lại trang
    # sau MỌI thao tác, kể cả bấm nút chấm nhãn.
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
        st.caption("Mỗi nhánh gọi lại `search()` với đúng nhánh đó bật — "
                   "không viết lại logic truy xuất trong UI.")
        if cf["che_do"] == "offline":
            st.info("Chế độ offline chỉ có một nhánh (BM25 trên doc_text).")
        else:
            cot = st.columns(len(NHANH))
            for c, nhanh in zip(cot, NHANH):
                with c:
                    st.markdown(f"**{nhanh}**")
                    if st.button("chạy", key=f"go_{nhanh}"):
                        st.session_state[f"kq_{nhanh}"] = chay_search(cf, chi_nhanh=nhanh)
                    for j, r in enumerate(st.session_state.get(f"kq_{nhanh}", [])[:10]):
                        st.caption(f"{j + 1}. {r.get('keyframe_id')} · {r.get('score', 0):.4f}")

    with tab_rerank:
        st.info("Rerank (A2.4) chưa bật. Khung để sẵn — có rerank là tự có dữ liệu.")

    st.divider()
    chon = st.selectbox("Soi bằng chứng của keyframe",
                        [r.get("keyframe_id") for r in kq], index=0)
    if chon:
        ve_bang_chung(chon)


main()
