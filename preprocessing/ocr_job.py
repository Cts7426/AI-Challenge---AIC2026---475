# preprocessing/ocr_job.py — Task 4.1: OCR tiếng Việt trên keyframe
#
# ⚠️ JOB NẶNG — THIẾT KẾ ĐỂ CHẠY TRÊN COLAB/KAGGLE (GPU free), KHÔNG chạy máy dev:
#   - PaddleOCR + paddlepaddle-gpu ~vài GB, cần GPU mới nhanh (1000h video
#     = hàng trăm nghìn keyframe).
#   - Máy dev 16GB/Python 3.14 thậm chí không có wheel paddle để cài.
#
# Cách chạy trên Colab (Runtime → GPU):
#   !git clone <repo_url> aic && %cd aic
#   !pip install paddlepaddle-gpu paddleocr
#   # upload/mount thư mục keyframes (cấu trúc <video_id>/<keyframe_id>.jpg)
#   !python preprocessing/ocr_job.py --images /content/keyframes --out data/ocr/ocr_results.jsonl
#   # muốn sửa lỗi tiếng Việt qua LLM: set ANTHROPIC_API_KEY trước, bỏ --no-llm
#
# 3 quyết định thiết kế cho môi trường Colab "chết bất tử":
# 1. Output JSONL append từng dòng + flush — Colab rớt giữa chừng thì kết quả
#    đã xử lý vẫn còn nguyên trên đĩa.
# 2. RESUME: chạy lại đúng lệnh cũ → tự đọc file out, bỏ qua keyframe đã làm.
# 3. Sửa lỗi LLM theo LÔ 20 text/lần gọi (rẻ hơn 20 lần so với gọi lẻ);
#    lô nào parse lỗi → giữ text gốc của lô đó, KHÔNG chết job.
#
# Output mỗi dòng: {"keyframe_id", "video_id", "text", "raw_text"}
#   text     = bản đã sửa lỗi qua llm() (hoặc = raw_text nếu --no-llm)
#   raw_text = bản OCR thô — giữ lại để đối chiếu/tái xử lý không cần OCR lại

import argparse
import json
import os
import sys
from pathlib import Path

# Chạy trực tiếp `python preprocessing/ocr_job.py` → sys.path[0] là preprocessing/,
# phải thêm gốc repo mới import được backend.llm
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
LLM_BATCH = 20      # số text sửa chung 1 lần gọi llm()
MIN_CONF = 0.5      # bỏ box OCR có confidence thấp hơn (thường là rác/nhiễu)


def iter_keyframes(images_dir: Path):
    """Duyệt ảnh keyframe → (keyframe_id, video_id, path).

    Quy ước: <images_dir>/<video_id>/<keyframe_id>.jpg (khớp thumbnail_url
    của API). Ảnh nằm phẳng không có thư mục video → suy video_id từ tên file
    ("L03_V001_0007" → "L03_V001"). TODO: BTC — chỉnh khi biết cấu trúc thật.
    """
    for p in sorted(images_dir.rglob("*")):
        if p.suffix.lower() not in IMG_EXTS:
            continue
        keyframe_id = p.stem
        video_id = p.parent.name if p.parent != images_dir else keyframe_id.rsplit("_", 1)[0]
        yield keyframe_id, video_id, p


def load_done(out_path: Path) -> set[str]:
    """Đọc file out cũ → tập keyframe_id đã xử lý (cơ chế resume)."""
    done = set()
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            try:
                done.add(json.loads(line)["keyframe_id"])
            except (json.JSONDecodeError, KeyError):
                pass  # dòng hỏng (Colab rớt giữa lúc ghi) — bỏ qua, sẽ OCR lại
    return done


def make_ocr():
    """Khởi tạo PaddleOCR tiếng Việt. Import lười — máy không có paddle vẫn
    import được module này (để test các hàm thuần logic)."""
    from paddleocr import PaddleOCR

    # use_angle_cls: tự xoay text nghiêng (chữ chạy góc màn hình tin tức)
    return PaddleOCR(use_angle_cls=True, lang="vi", show_log=False)


def ocr_image(ocr, path: Path) -> str:
    """OCR 1 ảnh → chuỗi text (các box nối bằng khoảng trắng, theo thứ tự đọc)."""
    result = ocr.ocr(str(path), cls=True)
    lines = []
    for page in result or []:
        for item in page or []:
            # item = [box_4_điểm, (text, confidence)]
            text, conf = item[1]
            if conf >= MIN_CONF and text.strip():
                lines.append(text.strip())
    return " ".join(lines)


def correct_batch(texts: list[str]) -> list[str]:
    """Sửa lỗi OCR tiếng Việt cho 1 lô text bằng MỘT lần gọi llm().

    Format hỏi/đáp "số|text" từng dòng — dễ parse, dễ đối chiếu. Dòng nào
    LLM trả thiếu/lệch → giữ nguyên bản gốc dòng đó (an toàn hơn đoán mò).
    """
    from backend.llm.adapter import llm

    numbered = "\n".join(f"{i + 1}|{t}" for i, t in enumerate(texts))
    prompt = (
        "Sau đây là các dòng text OCR từ khung hình video tiếng Việt (bản tin, "
        "phụ đề, bảng tỉ số...), có thể sai dấu hoặc nhầm ký tự. Sửa lỗi hiển "
        "nhiên; GIỮ NGUYÊN số liệu, tên riêng, từ đúng sẵn; KHÔNG thêm bớt nội "
        f"dung. Trả về ĐÚNG {len(texts)} dòng, mỗi dòng dạng: số|text đã sửa. "
        "Không viết gì khác.\n\n" + numbered
    )
    fixed: dict[int, str] = {}
    try:
        for line in llm(prompt).splitlines():
            num, sep, txt = line.partition("|")
            if sep and num.strip().isdigit():
                fixed[int(num.strip()) - 1] = txt.strip()
    except Exception as e:
        print(f"  [cảnh báo] llm() lỗi, giữ text gốc cho lô này: {e}")
    return [fixed.get(i, t) for i, t in enumerate(texts)]


def main() -> None:
    parser = argparse.ArgumentParser(description="OCR tiếng Việt trên keyframe (chạy Colab/Kaggle)")
    parser.add_argument("--images", type=Path, required=True, help="thư mục ảnh keyframe")
    parser.add_argument("--out", type=Path, default=Path("data/ocr/ocr_results.jsonl"))
    parser.add_argument("--no-llm", action="store_true", help="bỏ bước sửa lỗi qua llm()")
    args = parser.parse_args()

    use_llm = not args.no_llm
    if use_llm and not os.environ.get("ANTHROPIC_API_KEY"):
        print("[cảnh báo] Không có ANTHROPIC_API_KEY → tự tắt bước sửa LLM (như --no-llm).")
        use_llm = False

    done = load_done(args.out)
    todo = [(k, v, p) for k, v, p in iter_keyframes(args.images) if k not in done]
    print(f"Keyframe cần OCR: {len(todo)} (đã có sẵn: {len(done)})")
    if not todo:
        return

    args.out.parent.mkdir(parents=True, exist_ok=True)
    ocr = make_ocr()

    # buffer gom đủ LLM_BATCH rồi mới sửa + ghi — cân giữa số lần gọi API
    # và lượng kết quả tối đa có thể mất khi Colab rớt (tối đa 1 lô)
    buffer: list[dict] = []
    with args.out.open("a", encoding="utf-8") as f:

        def flush() -> None:
            if not buffer:
                return
            texts = [r["raw_text"] for r in buffer]
            corrected = correct_batch(texts) if use_llm else texts
            for rec, fixed in zip(buffer, corrected):
                rec["text"] = fixed
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()  # ép xuống đĩa ngay — Colab rớt không mất lô đã xử lý
            buffer.clear()

        for idx, (keyframe_id, video_id, path) in enumerate(todo, 1):
            raw = ocr_image(ocr, path)
            if raw:  # frame không có chữ thì khỏi lưu — đỡ rác index
                buffer.append(
                    {"keyframe_id": keyframe_id, "video_id": video_id, "raw_text": raw}
                )
            if len(buffer) >= LLM_BATCH:
                flush()
            if idx % 50 == 0:
                print(f"  {idx}/{len(todo)} ảnh…")
        flush()

    print(f"Xong. Kết quả: {args.out} — nạp vào ES bằng:")
    print("  python -m backend.indexing.load_ocr --file", args.out)


if __name__ == "__main__":
    main()
