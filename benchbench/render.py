"""One canonical PNG per benchmark page. Every provider and the judge see these exact bytes."""

import io
import threading
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image

PDFIUM_LOCK = threading.Lock()  # pdfium is not thread-safe (heap corruption under the render pool)
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}


def render_page(path: Path, page_index: int = 0, dpi: int = 200, max_side: int = 4000) -> Image.Image:
    """PDF page -> RGB at `dpi`; image -> RGB (alpha flattened onto white). Longest side capped."""
    if path.suffix.lower() == ".pdf":
        with PDFIUM_LOCK:
            pdf = pdfium.PdfDocument(str(path))
            try:
                img = pdf[page_index].render(scale=dpi / 72, draw_annots=True).to_pil()
            finally:
                pdf.close()
    elif path.suffix.lower() in IMAGE_SUFFIXES:
        img = Image.open(path)
        img.load()
    else:
        raise ValueError(f"unsupported page source {path}")
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(bg, img)
    img = img.convert("RGB")
    if max(img.size) > max_side:
        img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    return img


def page_count(path: Path) -> int:
    if path.suffix.lower() != ".pdf":
        return 1
    with PDFIUM_LOCK:
        pdf = pdfium.PdfDocument(str(path))
        try:
            return len(pdf)
        finally:
            pdf.close()


def to_png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
