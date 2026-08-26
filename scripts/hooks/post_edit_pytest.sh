#!/usr/bin/env bash
# Hook PostToolUse: chạy pytest ngay sau mỗi lần Claude sửa file .py trong repo.
#
# Vì sao cần: repo này đầy "lỗi im lặng" (CLAUDE.md mục 12) — sửa sai không
# crash, chỉ trả kết quả sai. Đã có 810 test khoá các bất biến đó lại, nhưng
# test chỉ có giá trị nếu được chạy. Hook do HARNESS gọi, không phải do Claude
# tự nhớ, nên không thể "quên chạy test".
#
# Exit 2 = blocking error: nội dung stderr được đưa NGƯỢC lại cho Claude đọc,
# buộc phải sửa trước khi đi tiếp.

set -uo pipefail

# Tự suy repo từ vị trí script (scripts/hooks/x.sh -> lên 2 cấp) thay vì
# hardcode: AGENTS.md ghi teammate chạy Windows `C:\dev\aic2026`, path tuyệt
# đối của một máy sẽ làm hook chết câm trên máy khác.
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# venv khác nhau giữa macOS/Linux (bin/) và Windows (Scripts/); rơi về python3
# hệ thống nếu không có venv.
if [ -x "$REPO/.venv/bin/python3.14" ]; then
  PY="$REPO/.venv/bin/python3.14"
elif [ -x "$REPO/.venv/Scripts/python.exe" ]; then
  PY="$REPO/.venv/Scripts/python.exe"
elif [ -x "$REPO/.venv/bin/python" ]; then
  PY="$REPO/.venv/bin/python"
else
  PY="python3"
fi

payload="$(cat)"
file_path="$(printf '%s' "$payload" | jq -r '.tool_response.filePath // .tool_input.file_path // empty')"

# Chỉ quan tâm file .py NẰM TRONG repo. Sửa .md/.json/.html hay file ngoài repo
# thì không đụng tới hành vi code — chạy test chỉ tổ chậm.
case "$file_path" in
  "$REPO"/*.py) ;;
  *) exit 0 ;;
esac

# Bỏ qua script nháp ở gốc repo (scratch_*.py, test_*.py chạy tay) — pytest.ini
# đã loại chúng khỏi testpaths, sửa chúng không ảnh hưởng suite.
case "$file_path" in
  "$REPO"/scratch_*.py|"$REPO"/test_*.py) exit 0 ;;
esac

output="$(cd "$REPO" && "$PY" -m pytest tests dev_set/tests -q 2>&1)"
status=$?

if [ $status -ne 0 ]; then
  # Chỉ trả phần đuôi: đủ để biết test nào đỏ, không nhấn chìm context.
  echo "pytest ĐỎ sau khi sửa ${file_path#"$REPO"/} — phải sửa trước khi đi tiếp:" >&2
  printf '%s\n' "$output" | tail -40 >&2
  exit 2
fi

# Xanh thì im lặng, chỉ in một dòng tóm tắt để người dùng thấy test có chạy.
printf '%s\n' "$output" | grep -E '^[0-9]+ (passed|failed)' | tail -1
exit 0
