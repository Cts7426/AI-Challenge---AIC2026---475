# data/config/search_weights.py — tham số hợp nhất kết quả search (A2.2)
#
# ⚠️ KHÔNG còn trọng số cộng điểm. Từ A2.2 fusion dùng RRF:
#       score(d) = Σ_nhánh 1 / (RRF_K + rank_nhánh(d))
#
# Vì sao bỏ weighted-sum (cách cũ) để đổi sang RRF?
#   Weighted-sum cộng ĐIỂM, mà điểm mỗi nhánh khác thang hoàn toàn (COSINE
#   [-1,1] vs BM25 không chặn trên) → phải chuẩn hoá, mà chuẩn hoá lại phụ
#   thuộc phân bố của đúng lần query đó. RRF chỉ cộng THỨ HẠNG nên miễn nhiễm:
#   nhánh nào cũng chỉ nói được "cái này tôi xếp thứ mấy", không cãi nhau về thang.
#   Hệ quả thực tế: hết cần tune trọng số — thứ mà nhóm nhỏ không có thời gian làm.
#
# RRF_K = 60 là giá trị chuẩn trong bài báo gốc (Cormack 2009) và cũng là mặc
# định của Elasticsearch/Milvus. K lớn → làm phẳng khác biệt giữa các hạng đầu
# (an toàn hơn khi một nhánh hay sai); K nhỏ → tin hạng 1 mạnh hơn.
#
# ⚠️ SỬA 20/08 — đo thật (dev_set/tools/sweep_search_fusion.py, đêm trước Đợt
# 1), K=60 CHƯA TỪNG được kiểm chứng trên dữ liệu thật của dự án — chỉ là số
# mặc định lấy nguyên từ bài báo gốc/ES/Milvus. Chẩn đoán cụ thể: nhiều câu
# KIS/QA/TRAKE có 1 nhánh (thường ASR/OCR) xếp hạng RẤT TỐT (1-3, khớp đúng
# văn bản) nhưng nhánh vector (CLIP) kém (hạng 20-250+, kho dữ liệu có nhiều
# video CÙNG CHỦ ĐỀ khiến CLIP khó phân biệt) — với K=60, chênh lệch hạng 1
# vs hạng 40 chỉ còn 1/61 vs 1/100 (~1.6 lần), KHÔNG đủ để 1 tín hiệu cực
# mạnh thắng 1 đối thủ "khá đều nhưng không xuất sắc ở nhánh nào".
#
# Quét K ∈ {1,3,5,7,10,15,20,30,40,60} trên 2 tập ĐỘC LẬP: 36 câu KIS bộ đề
# đồng đội (holdout, nội dung nhiều video cùng chủ đề — nơi phát hiện vấn đề)
# và 23 câu KIS dev-set gốc (tune, nội dung đa dạng — kiểm KHÔNG hồi quy).
# K=7 tốt nhất trên CẢ HAI, không đánh đổi:
#   K=60 (cũ):  holdout Final=0.122        tune Final=0.513 R@1=0.130
#   K=7 (mới):  holdout Final=0.194 (+59%) tune Final=0.522 (+2%) R@1=0.217 (+67%)
# ĐÃ THỬ tăng trọng số ocr/asr thay vì đổi K — LOẠI BỎ: luôn cải thiện holdout
# nhưng làm hại tune (query đa dạng cần vector làm tín hiệu chính) — đổi K
# không thiên vị nhánh nào, chỉ làm hạng 1 "đáng tin" hơn hạng thấp, nên an
# toàn hơn hẳn cho MỌI loại câu hỏi.
RRF_K = 7

# Bật/tắt từng nhánh. Tắt = nhánh đó không chạy và không đóng góp hạng nào.
# Dùng để đo đóng góp thật của mỗi nhánh (tắt đi, xem điểm rớt bao nhiêu).
BRANCHES = {
    "vector": True,     # CLIP trên Milvus — nhánh lõi
    "metadata": True,   # BM25 title/description/keywords (mức VIDEO)
    "objects": True,    # nhãn OpenImages (mức KEYFRAME)
    "ocr": True,        # chữ trên hình (mức KEYFRAME)
    "asr": True,        # lời thoại tiếng Việt (mức ĐOẠN THỜI GIAN)
}

# Trọng số RRF cho từng nhánh (Weighted RRF).
# Các nhánh nhiễu như OCR/ASR thường sinh ra nhiều kết quả ảo do khớp từng từ,
# trong khi Vector (CLIP) mới là giá trị cốt lõi. Cần áp trọng số để Vector không bị chìm.
BRANCH_WEIGHTS = {
    "vector": 1.0,
    "objects": 0.7,
    "ocr": 0.6,
    "asr": 0.6,
    "metadata": 0.4,
}

# ----------------- Gom nhóm theo shot (B0.1) -----------------
# Mỗi nhánh lấy top_k * hệ số này làm ứng viên. Rộng hơn top_k để keyframe mạnh
# ở nhánh phụ vẫn lọt vào bảng hợp nhất; rộng quá thì tốn thời gian vô ích.
CANDIDATE_MULTIPLIER = 5

# Gom kết quả về SHOT, mỗi shot giữ 1 keyframe điểm cao nhất.
# Vì sao: 3–4 keyframe liền nhau trong cùng một shot là cùng một cảnh — chiếm
# chỗ của nhau trên màn hình mà không thêm thông tin gì cho người duyệt.
GROUP_BY_SHOT = True

# ASR join theo thời gian: đoạn nói [start, end] nới ± ngần này khi so với
# timestamp keyframe — lời bình thường lệch hình vài giây.
ASR_TIME_PAD_MS = 2000

# Số đoạn ASR khớp nhất được quyền ĐỀ CỬ keyframe (tra Milvus theo khoảng thời
# gian). Cap lại để 1 query Milvus không phình filter vô hạn.
ASR_NOMINATE_SEGMENTS = 5

# --------------------------------------------------------------- TRAKE (C3.2)

# Hệ số THƯỞNG (nhân điểm video) khi các sự kiện của TRAKE khớp trong video theo
# ĐÚNG trình tự thời gian đề bài mô tả. Đặt ở config chứ không hardcode trong
# backend/tasks/trake.py vì đây là chiến thuật cần tune trên dev_set (giống mọi
# trọng số khác trong file này), không phải hằng số thuật toán.
#
# ⚠️ Chỉ dùng để XẾP LẠI HẠNG trong nhóm video đã có điểm hợp lý — KHÔNG dùng
# làm ngưỡng lọc cứng: 1 video đúng nhưng có 1 sự kiện bị đảo thứ tự (nhiễu tìm
# kiếm) vẫn phải còn cơ hội lọt top-10, chỉ là xếp thấp hơn video khớp thứ tự
# hoàn hảo. Sai video ở TRAKE là 0 điểm tuyệt đối (docs/contest.md) — loại nhầm
# 1 video đúng khỏi top-10 vì phạt quá tay còn tệ hơn xếp nó hạng 8 thay vì hạng 2.
TRAKE_ORDER_BONUS = 5.0

# Mỗi sự kiện TRAKE lấy top bấy nhiêu shot khi search() riêng (KHÔNG nối chuỗi
# N sự kiện thành 1 câu — vi phạm giới hạn 77 token của CLIP, xem
# backend/tasks/trake.py). Rộng hơn top-10 video cuối cùng để video đúng mà
# chỉ khớp yếu 1-2 sự kiện vẫn có cơ hội lọt vào bảng gộp điểm.
TRAKE_EVENT_SEARCH_POOL = 1000

# Trong TỪNG video ứng viên, mỗi sự kiện giữ lại tối đa bấy nhiêu khung hình
# điểm cao nhất làm ứng viên cho DP xếp chuỗi tăng dần (backend/tasks/trake.py
# ::_align_events_in_video). >1 (khác bản cũ chỉ giữ đúng 1) để DP có phương án
# B khi ứng viên điểm cao nhất của một sự kiện phá thứ tự — không phải "+1
# nudge" giả tạo lên bằng chứng thật. DP là O((N·K)²) nên K lớn vẫn rẻ.
#
# ⚠️ SỬA 20/08 — đo thật (reports/trake_hardening.md, quét trên bộ đề TRAKE
# mở rộng 8 câu — 2 người viết + 6 tổng hợp bằng VLM): chẩn đoán 1 câu bị 0
# điểm dù VIDEO ĐÚNG xếp hạng 1 phát hiện GT frame KHÔNG NẰM TRONG top-6 ứng
# viên của chính video đó — vấn đề RECALL trong video, không phải lỗi DP.
# k=6→20 nới top-6 lên top-20 (dev_set/tools/sweep_trake_config.py quét
# 6/12/20 — 20 là mức tốt nhất đo được, DP vẫn rẻ vì O((N·K)²) với N,K nhỏ)
# giúp GT frame có cơ hội lọt vào rổ ứng viên cao hơn — cải thiện đo được
# trên tập tổng hợp (avg Final 0.172→0.192), KHÔNG đổi tập người viết (đã tìm
# thấy sẵn ở k=6, chỉ là chưa xếp hạng đúng — xem TRAKE_MIN_BLEND_LAMBDA).
TRAKE_CANDIDATES_PER_EVENT = 20

# Khoảng cách FRAME tối thiểu giữa 2 vị trí LIÊN TIẾP mà DP chọn (backend/tasks/
# trake.py::_align_events_in_video). Đo thật: CLIP không phân biệt nổi "đổ
# muối vào nước" với "đổ rau vào nước" bằng caption ngắn — cả hai ra CÙNG 1
# khung hình top-1 (cách nhau ~19 frame), khiến DP ghép chúng thành "2 sự kiện"
# dù đó chỉ là 1 khoảnh khắc CLIP nhầm lẫn. Ràng buộc này không sửa được lỗi
# CLIP (cần "tầng tinh" — docs/contest.md), chỉ ép DP bỏ qua tổ hợp chụm 1 chỗ.
#
# TODO: BTC/D4.1 — chưa biết fps thật của video (docs/contest.md), nên đây là
# số frame THÔ, chưa quy đổi ra giây. 30 là ước lượng "đủ để không phải cùng 1
# khoảnh khắc nhầm lẫn" nhưng "đủ nhỏ để không loại nhầm 2 hành động cắt nhanh
# thật" — cần tune trên dev_set khi có video có timestamp thật để đối chiếu.
#
# ⚠️ Đo thật 20/08 (sweep_trake_config.py, quét 10/20/30 trên 8 câu TRAKE):
# GIỮ NGUYÊN 30 — quét không cho thấy khác biệt R-score nào ở cả 3 giá trị
# trên bộ đề hiện có (khoảng cách frame thật giữa các sự kiện trong dev-set
# đều rộng hơn nhiều so với cả 3 mức thử). KHÔNG NHẦM tham số này với "cửa sổ
# đáp án TRAKE thật <10 frame" (reports/slot_tuning.md) — đó là ĐỘ RỘNG cửa sổ
# [s,e] BTC chấm, do BTC quyết định, không phải tham số DP này (min_gap chỉ
# chặn 2 VỊ TRÍ SỰ KIỆN chọn trùng 1 khoảnh khắc do CLIP nhầm lẫn — 2 khái
# niệm khác nhau, dễ nhầm vì cùng đơn vị "frame"). Vẫn là ước lượng, không có
# bằng chứng để đổi — cần dev-set có video kèm timestamp thật để đối chiếu.
TRAKE_MIN_FRAME_GAP = 30

# Trộn "vị trí sự kiện yếu nhất" vào tổng điểm khi xếp hạng video ứng viên
# (backend/tasks/trake.py::_localize_in_video): score = (Σ điểm vị trí + λ ×
# min điểm vị trí) × bonus. λ=0 = công thức gốc (chỉ tổng).
#
# Đo thật 20/08 (sweep_trake_config.py): chẩn đoán TR02 (video đúng hạng 8/100)
# — 7 video SAI cũng khớp has_full_order=True/n_hit_events=3 nhưng TỔNG điểm
# thô cao hơn (1 vị trí khớp rất mạnh + các vị trí khác yếu, tổng vẫn thắng).
# Cộng thêm điểm-vị-trí-yếu-nhất phạt đúng kiểu video này (thắng 1 chỗ, yếu
# đều những chỗ còn lại) — quét λ ∈ {0.5,1,2} trên 8 câu (2 người viết + 6
# tổng hợp), λ=2.0 tốt nhất: avg Final tập người viết 0.450→0.517, tập gộp
# 0.172→0.209 (reports/trake_hardening.md có bảng đầy đủ).
#
# ⚠️ Kiểm lại 20/08 22:xx sau khi đổi RRF_K 60→7: quét λ ∈ {0,0.5,1,2,3,5} ×
# w ∈ {0,0.5,1,2,3,5} — dưới K=7, λ gần như KHÔNG còn ảnh hưởng rõ tới 8 câu
# dev-set (mọi λ ở cùng w cho số gần giống nhau). GIỮ NGUYÊN 2.0 — không có
# bằng chứng để đổi, và vô hại (không làm tệ đi tổ hợp nào đã quét).
TRAKE_MIN_BLEND_LAMBDA = 2.0

# Cộng thêm điểm ứng viên theo mức "cộng hưởng nội dung ASR" với CÁC SỰ KIỆN
# KHÁC (backend/tasks/trake.py::_apply_asr_context_bonus, chạy TRƯỚC DP).
# 0 = tắt hẳn (hành vi cũ, không tính gì thêm).
#
# ⚠️ Vì sao cần — đo thật 20/08 (câu TRAKE tin tức thật do người dùng cung
# cấp, reports/trake_hardening.md §6): TRAKE hiện tại về bản chất là N lần
# search() ĐỘC LẬP (y hệt KIS) + DP chỉ ép thứ tự/khoảng cách — không có khái
# niệm "cùng mạch nội dung". Video ĐÚNG (`L21_V024`, xác nhận bằng ASR khớp
# gần nguyên văn câu hỏi) vẫn chọn sai 1/4 frame vì sự kiện diễn đạt chung
# chung ("lực lượng chức năng có mặt tại hiện trường") lọt sang MỘT TIN KHÁC
# trong cùng video bản tin nhiều mục — đúng thứ tự, đúng khoảng cách, chỉ sai
# chuyện. Đã thử "phạt khoảng cách frame" trước — LOẠI BỎ vì khoảng cách
# "sai" (5.1% video) nhỏ hơn khoảng cách "đúng" hợp lệ của TR01 (22.5% video,
# video nấu ăn là 1 câu chuyện xuyên suốt) — không có ngưỡng khoảng cách nào
# phân biệt được. Đếm từ khoá chéo trong văn bản ASR là tín hiệu MẠCH NỘI
# DUNG thật, không phụ thuộc khoảng cách frame.
# Đo thật 20/08 (dev_set/tools/sweep_trake_asr_bonus.py, quét trên 8 câu dev-set
# + 1 câu tai nạn giao thông thật do người dùng cung cấp):
#   - Đếm thô (không IDF) làm SẬP điểm 8/8 câu (R@1 → 0.000) — từ vựng chung
#     chung (vd "cắt", "nước") lặp khắp video nấu ăn cùng thể loại, nhiễu bonus.
#     → PHẢI dùng trọng số IDF trên chính rổ ứng viên câu hỏi (_build_token_weight),
#     không phải đếm thô.
#   - Bonus CHỈ áp dụng cho bước DP chọn frame TRONG 1 video (`c["score"]`),
#     KHÔNG áp dụng cho điểm XẾP HẠNG GIỮA CÁC VIDEO (`c["_orig_score"]`, giữ
#     nguyên điểm gốc) — dùng chung cho cả hai làm TR02 dao động hạng qua
#     ranh giới R@5 (bonus tình cờ ưu ái video khác nhiều hơn).
#   - w=0.5 (lúc RRF_K=60): avg Final 8 câu 0.172→0.220, TR01/TR02 giữ 0.517.
#
# ⚠️ SỬA LẠI 20/08 22:xx — RRF_K vừa đổi 60→7 (xem RRF_K phía trên) làm
# c["score"] từ search() LỚN HƠN HẲN (1/(K+rank) với K nhỏ) → w=0.5 (tune
# khi K=60) không còn đủ mạnh để thắng chênh lệch điểm gốc mới: frame4 câu
# tai nạn giao thông QUAY LẠI sai (14760) ở w=0.5. Quét lại ĐỒNG THỜI với
# TRAKE_MIN_BLEND_LAMBDA dưới K=7 (sweep_trake_asr_bonus.py):
#   - RRF_K=7 MỘT MÌNH đã kéo Final TR01/TR02 lên 0.642 (từ 0.517) — cả 2
#     tham số dưới đây giờ ít ảnh hưởng tới TR01/TR02 hơn trước (bù đắp phần
#     lớn bởi chính K=7), NHƯNG câu tai nạn giao thông vẫn cần w>=1.0 mới
#     sửa được frame4 (w=0.5 không đủ nữa).
#   - w=1.0 (λ=2.0 giữ nguyên): 8 câu Final 0.217→0.197 (đánh đổi nhỏ, có
#     chủ đích — xem TRAKE_MIN_BLEND_LAMBDA), TR01/TR02 KHÔNG đổi (0.642 mọi
#     w), frame4 câu tai nạn ĐÚNG (13239) — giữ nguyên bug-fix quan trọng
#     nhất đêm nay.
TRAKE_ASR_CONTEXT_BONUS_WEIGHT = 1.0
