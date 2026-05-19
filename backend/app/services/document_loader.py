"""文档加载器 — 支持 PDF/DOCX/MD/TXT"""

import os
import re
from pathlib import Path


def load_document(file_path: str) -> str:
    """根据扩展名加载文档并返回纯文本"""
    ext = Path(file_path).suffix.lower()
    if ext == ".pdf":
        return _load_pdf(file_path)
    elif ext == ".docx":
        return _load_docx(file_path)
    elif ext in (".md", ".markdown"):
        return _load_text(file_path)
    elif ext == ".txt":
        return _load_text(file_path)
    else:
        raise ValueError(f"不支持的文件格式: {ext}")


def _load_pdf(file_path: str) -> str:
    try:
        import pdfplumber
    except ImportError:
        raise ImportError("请安装 pdfplumber: pip install pdfplumber")

    text_parts = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    return "\n\n".join(text_parts)


def _load_docx(file_path: str) -> str:
    try:
        from docx import Document
    except ImportError:
        raise ImportError("请安装 python-docx: pip install python-docx")

    doc = Document(file_path)
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paragraphs)


def _load_text(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


def load_document_v2(file_path: str) -> dict:
    """v2.0: Load document and return {"text": str, "images": [dict]}.

    For PDFs: extracts text AND embedded images.
    For images: empty text, single image entry.
    For DOCX/MD/TXT: extracts text only, empty images list.
    """
    import uuid

    ext = Path(file_path).suffix.lower()
    if ext == ".pdf":
        return _load_pdf_v2(file_path)
    elif ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"):
        return {
            "text": "",
            "images": [{
                "filename": Path(file_path).name,
                "stored_path": file_path,
                "source_page": None,
                "content_type": f"image/{ext.lstrip('.')}",
                "size_bytes": Path(file_path).stat().st_size,
            }],
        }
    elif ext == ".docx":
        return {"text": _load_docx(file_path), "images": []}
    elif ext in (".md", ".markdown", ".txt"):
        return {"text": _load_text(file_path), "images": []}
    else:
        raise ValueError(f"不支持的文件格式: {ext}")


def _load_pdf_v2(file_path: str) -> dict:
    """Extract text and images from PDF using PyMuPDF."""
    import uuid
    import fitz  # PyMuPDF

    from app.config import config
    os.makedirs(config.ASSETS_DIR, exist_ok=True)

    doc = fitz.open(file_path)
    text_parts = []
    image_assets = []

    subdir = os.path.join(config.ASSETS_DIR, str(uuid.uuid4())[:8])
    os.makedirs(subdir, exist_ok=True)

    for page_num in range(len(doc)):
        page = doc[page_num]
        text_parts.append(page.get_text())

        for img_idx, img_info in enumerate(page.get_images(full=True)):
            xref = img_info[0]
            try:
                base_image = doc.extract_image(xref)
            except Exception:
                continue
            image_bytes = base_image["image"]
            ext = base_image["ext"]
            fname = f"page_{page_num + 1}_img_{img_idx}.{ext}"
            fpath = os.path.join(subdir, fname)
            with open(fpath, "wb") as f:
                f.write(image_bytes)
            image_assets.append({
                "filename": fname,
                "stored_path": fpath,
                "source_page": page_num + 1,
                "content_type": f"image/{ext}",
                "size_bytes": len(image_bytes),
            })

    doc.close()
    return {"text": "\n\n".join(text_parts), "images": image_assets}
