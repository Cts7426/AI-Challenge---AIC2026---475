# backend/export/__main__.py — giữ nguyên lệnh `python -m backend.export --demo`
#
# Package không tự chạy được như file .py đơn lẻ; __main__.py là chỗ Python tìm
# khi gõ `-m <package>`. Tách ra đây để __init__.py chỉ còn việc export tên.

from backend.export.exporter import main

raise SystemExit(main())
