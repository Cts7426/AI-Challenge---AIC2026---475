"""Probe token HIẾM — kéo lại tín hiệu OCR/ASR bị cả câu tiếng Việt làm loãng.

===== Vì sao cần =====
Nhánh OCR hiện hành ném NGUYÊN CÂU đề vào BM25. Một từ khoá cực đặc trưng nằm
lẫn trong 40 từ tiếng Việt thì bị điểm của phần còn lại nhấn chìm. Đo được trên
p1 (03/09):

    câu     từ khoá     OCR cả câu    OCR chỉ từ khoá
    p1-22   remember    hạng 52       hạng 2   (chỉ 18 dòng khớp)
    p1-12   mazut       hạng 57       hạng 1   (chỉ 14 dòng khớp)

===== Vì sao KHÔNG cần từ điển =====
Không phải đoán từ nào "quan trọng". Độ hiếm TỰ ĐO ĐƯỢC: ném token vào OCR, nếu
nó chỉ khớp vài chục dòng trong 160.393 dòng OCR thì chính nó là bằng chứng
phân biệt. Từ tiếng Việt thông thường trả về hàng nghìn dòng và bị loại ngay.
Quy tắc này không có tham số ngôn ngữ nào, nên không hỏng khi đề đổi chủ đề.

===== Vì sao chỉ bỏ phiếu MỨC VIDEO =====
Cùng lý do với `video_prior`: cộng thẳng vào điểm keyframe thì một video ngập
đầu bảng. Probe trả lời câu hỏi "video nào", không phải "khung hình nào".

===== Nút quay đầu =====
    ENABLED = False  -> tắt hẳn, không chạy thêm truy vấn ES nào
"""
from __future__ import annotations

ENABLED = True

# Token khớp <= ngưỡng này mới được coi là hiếm/phân biệt. 160k dòng OCR nên
# vài trăm đã là rất hiếm. Đặt quá cao thì từ thường lọt vào và probe thành nhiễu.
MAX_HITS = 400

# Không probe token quá ngắn: "cho", "cái", số 1-2 chữ số khớp lung tung.
MIN_TOKEN_LEN = 4

# Trần số truy vấn ES thêm cho mỗi câu hỏi — giữ độ trễ trong ngân sách 30s.
MAX_PROBES = 24

# Trọng số phiếu bầu của probe, so với các nhánh thường (vector = 1.0).
# Đặt cao vì token hiếm khớp là bằng chứng gần như chắc chắn, nhưng KHÔNG đặt
# vô hạn: OCR vẫn đọc sai chữ, và một probe sai không được quyền một mình quyết.
PROBE_WEIGHT = 2.0

# Trọng số của tín hiệu probe SAU KHI đã chuẩn hoá riêng, cộng vào phiếu mức
# video (phiếu nhánh cũng đã chuẩn hoá về [0,1]). 1.0 = một video đứng đầu bảng
# probe được cộng đúng bằng video được bầu cao nhất ở các nhánh thường.
PROBE_MIX = 1.0
