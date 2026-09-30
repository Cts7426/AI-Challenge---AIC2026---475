"""Kiểm bản nộp cuối theo claim ledger và yêu cầu form; không chạy hệ thống retrieval."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/pdf"
PDF = OUT / "FINAL_REPORT_SUBMISSION.pdf"
SOURCE = OUT / "FINAL_REPORT_SUBMISSION.md"
BEFORE_EDITORIAL = Path(__file__).resolve().parent / "FINAL_REPORT_SUBMISSION.before_editorial_upgrade.md"
DELIVERABLES = [
    SOURCE,
    PDF,
    OUT / "FINAL_BTC_CHECKLIST.md",
    OUT / "FINAL_CHANGELOG.md",
]


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


reader = PdfReader(PDF)
text = "\n".join(page.extract_text() or "" for page in reader.pages)
normalized = " ".join(text.split())
source = SOURCE.read_text(encoding="utf-8")
before_editorial = BEFORE_EDITORIAL.read_text(encoding="utf-8")
summary = (OUT / "FINAL_FORM_SUMMARY.md").read_text(encoding="utf-8")
summary_body = summary.split("\n\n", 1)[1]
summary_word_units = len(summary_body.split())
checklist = (OUT / "FINAL_BTC_CHECKLIST.md").read_text(encoding="utf-8")

expected = [
    "Đội Thanh Nghệ",
    "873 video",
    "177.321 keyframe",
    "0,4000",
    "0,3263",
    "0,5789",
    "0,5263",
    "8,6 / 13",
    "13,6 / 15",
    "11,8 / 17",
    "Kết quả các submission cuối tại ba đợt Vòng Sơ tuyển",
    "Tóm tắt. Đội Thanh Nghệ xây dựng hệ thống truy xuất khoảnh khắc video",
    "ChatGPT / Claude",
    "không phải benchmark truy xuất thuần tự động của engine",
    "bộ đánh giá mới chưa hoàn tất, chưa được dùng để đưa ra kết quả hiệu năng",
]
missing = [value for value in expected if value not in normalized]
forbidden = [
    r"\bH0[12]\b", r"\bE01\b", r"\bSTOP\b", r"selfcheck", r"API balance",
    r"0/44", r"23 cặp", r"129 records", r"READY FOR H03", r"NOT READY",
    r"state of the art", r"deserves to enter", r"significantly improves",
]
found_forbidden = [pattern for pattern in forbidden if re.search(pattern, normalized, re.I)]

a4 = (595.0, 842.0)
page_sizes = []
fonts = {}
for page in reader.pages:
    width, height = float(page.mediabox.width), float(page.mediabox.height)
    page_sizes.append([width, height])
    assert abs(width - a4[0]) < 1 and abs(height - a4[1]) < 1
    resources = page.get("/Resources") or {}
    for font_ref in (resources.get("/Font") or {}).values():
        font = font_ref.get_object()
        descriptor_ref = font.get("/FontDescriptor")
        descriptor = descriptor_ref.get_object() if descriptor_ref else None
        embedded = bool(
            descriptor
            and any(key in descriptor for key in ("/FontFile", "/FontFile2", "/FontFile3"))
        )
        fonts[str(font.get("/BaseFont"))] = {
            "subtype": str(font.get("/Subtype")),
            "embedded": embedded,
        }

assert len(reader.pages) == 4
assert PDF.stat().st_size < 100_000_000
assert not missing, missing
assert not found_forbidden, found_forbidden
assert 100 <= summary_word_units <= 200
assert source.count("| Đợt | Ngày thi | Điểm submission cuối |") == 1
assert source.count("không phải benchmark truy xuất thuần tự động của engine") == 1
assert source.count("Cải tiến sau Vòng Sơ tuyển") == 1
assert source.count("> **Tóm tắt.**") == 1
assert len(re.findall(r"^\*Bảng [12]\.", source, flags=re.M)) == 2
assert source.count("![Kiến trúc hệ thống") == 1
assert "4 truy vấn tăng, 5 giảm và 10 giữ nguyên" in source
assert all(path.is_file() for path in DELIVERABLES)
assert any(name.endswith("+ArialMT") and meta["embedded"] for name, meta in fonts.items())
assert any(name.endswith("+Arial-BoldMT") and meta["embedded"] for name, meta in fonts.items())
assert any(name.endswith("+Arial-ItalicMT") and meta["embedded"] for name, meta in fonts.items())
assert not any(char in text for char in ("\u2011", "\u2013", "\u2014"))
numeric_token = re.compile(r"\d+(?:[.,]\d+)*")
new_numeric_claims = sorted(set(numeric_token.findall(source)) - set(numeric_token.findall(before_editorial)))
assert not new_numeric_claims, new_numeric_claims
formatted_bytes = f"{PDF.stat().st_size:,}".replace(",", ".")
assert f"PDF {formatted_bytes} byte" in checklist
assert f"{summary_word_units} đơn vị tách bằng khoảng trắng" in checklist

checksums = {path.name: sha256(path) for path in DELIVERABLES}

report = {
    "status": "PASS",
    "pdf": PDF.as_posix(),
    "sha256": sha256(PDF),
    "bytes": PDF.stat().st_size,
    "pages": len(reader.pages),
    "page_sizes_points": page_sizes,
    "fonts": fonts,
    "summary_word_units": summary_word_units,
    "expected_claims_present": len(expected),
    "new_numeric_claims_vs_pre_upgrade": new_numeric_claims,
    "forbidden_internal_markers_found": [],
    "tables": 2,
    "architecture_figures": 1,
    "visual_pages_reviewed": 4,
    "submission_performed": False,
    "deliverable_sha256": checksums,
}
audit_dir = Path(__file__).resolve().parent
(audit_dir / "final_validation.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
)
(audit_dir / "delivery_checksums.json").write_text(
    json.dumps(checksums, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(json.dumps(report, ensure_ascii=False, indent=2))
