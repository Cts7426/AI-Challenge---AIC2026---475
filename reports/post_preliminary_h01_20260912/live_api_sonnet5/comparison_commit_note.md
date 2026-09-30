# Khóa lại commit trước đối chiếu

Lượt on đầu ghi commit 704bb09; trước lượt off workspace đã có commit bàn giao 2354147 do thao tác ngoài lượt này. So manifest cho thấy chỉ field git khác, source/config bytes không đổi. Không ghép hai ID khác nhau thành paired identity. Chạy thêm on_current sau off với cùng query/cache dưới commit hiện tại; giữ nguyên mọi output cũ. Không đổi gate hoặc chọn subset theo kết quả.
