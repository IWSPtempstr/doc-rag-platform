"""Image loader and PDF image extractor (v2.0)"""

import os
import base64
from pathlib import Path
from app.config import config


def extract_images_from_pdf(pdf_path: str, output_dir: str) -> list[dict]:
    """Extract embedded images from each page of a PDF.

    Returns list of dicts with keys: filename, stored_path, source_page, content_type, size_bytes
    """
    import fitz  # PyMuPDF

    os.makedirs(output_dir, exist_ok=True)
    doc = fitz.open(pdf_path)
    assets = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        image_list = page.get_images(full=True)
        for img_idx, img_info in enumerate(image_list):
            xref = img_info[0]
            try:
                base_image = doc.extract_image(xref)
            except Exception:
                continue
            image_bytes = base_image["image"]
            ext = base_image["ext"]
            filename = f"page_{page_num + 1}_img_{img_idx}.{ext}"
            stored_path = os.path.join(output_dir, filename)
            with open(stored_path, "wb") as f:
                f.write(image_bytes)
            assets.append({
                "filename": filename,
                "stored_path": stored_path,
                "source_page": page_num + 1,
                "content_type": f"image/{ext}",
                "size_bytes": len(image_bytes),
            })
    doc.close()
    return assets


def load_standalone_image(file_path: str) -> dict:
    """Validate and return metadata for a standalone image file."""
    path = Path(file_path)
    ext = path.suffix.lower()
    if ext not in config.ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError(f"Unsupported image format: {ext}")
    return {
        "filename": path.name,
        "stored_path": str(path),
        "source_page": None,
        "content_type": f"image/{ext.lstrip('.')}",
        "size_bytes": path.stat().st_size,
    }


def get_image_base64(file_path: str) -> str:
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def get_image_mime_type(file_path: str) -> str:
    ext = Path(file_path).suffix.lower()
    mime_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
    }
    return mime_map.get(ext, "image/png")
