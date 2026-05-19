"""文本切片器 — 固定大小切片 + 重叠"""

from app.config import config


def split_text(text: str, chunk_size: int | None = None, chunk_overlap: int | None = None) -> list[dict]:
    """将文本切分为 chunks，返回 [{chunk_id, content, metadata}]"""
    chunk_size = chunk_size or config.DEFAULT_CHUNK_SIZE
    chunk_overlap = chunk_overlap or config.DEFAULT_CHUNK_OVERLAP

    paragraphs = text.split("\n")
    chunks = []
    current = ""
    chunk_idx = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        if len(current) + len(para) + 1 <= chunk_size:
            current = (current + "\n" + para).strip()
        else:
            if current:
                chunks.append(_make_chunk(current, chunk_idx))
                chunk_idx += 1
            current = para

    if current.strip():
        chunks.append(_make_chunk(current.strip(), chunk_idx))

    return chunks


def _make_chunk(content: str, idx: int) -> dict:
    return {
        "chunk_id": f"chunk-{idx:04d}",
        "content": content,
        "metadata": {"chunk_index": idx, "char_count": len(content)},
    }


def split_text_v2(
    text: str,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    page_map: dict[int, int] | None = None,
) -> list[dict]:
    """v2.0 enhanced splitter — tracks character offsets and page ranges.

    page_map: dict mapping char_offset -> page_number (from PDF text extraction).
    """
    chunk_size = chunk_size or config.DEFAULT_CHUNK_SIZE
    chunk_overlap = chunk_overlap or config.DEFAULT_CHUNK_OVERLAP

    paragraphs = text.split("\n")
    chunks = []
    current = ""
    chunk_idx = 0
    offset = 0

    para_offsets = []
    for para in paragraphs:
        para_offsets.append(offset)
        offset += len(para) + 1  # +1 for \n

    para_idx = 0
    for pi, para in enumerate(paragraphs):
        para = para.strip()
        if not para:
            continue

        if len(current) + len(para) + 1 <= chunk_size:
            current = (current + "\n" + para).strip()
        else:
            if current:
                char_start = para_offsets[para_idx] if para_idx < len(para_offsets) else 0
                char_end = para_offsets[pi - 1] + len(paragraphs[pi - 1]) if pi > 0 else char_start + len(current)
                chunks.append(_make_chunk_v2(current, chunk_idx, char_start, char_end, page_map))
                chunk_idx += 1
                para_idx = pi
            current = para

    if current.strip():
        char_start = para_offsets[para_idx] if para_idx < len(para_offsets) else 0
        char_end = len(text)
        chunks.append(_make_chunk_v2(current.strip(), chunk_idx, char_start, char_end, page_map))

    return chunks


def _make_chunk_v2(
    content: str, idx: int, char_start: int, char_end: int, page_map: dict | None
) -> dict:
    page_range = _compute_page_range(char_start, char_end, page_map)
    return {
        "chunk_id": f"chunk-{idx:04d}",
        "content": content,
        "metadata": {
            "chunk_index": idx,
            "char_count": len(content),
            "char_offset_start": char_start,
            "char_offset_end": char_end,
            "page_range": page_range,
        },
    }


def _compute_page_range(start: int, end: int, page_map: dict | None) -> list[int] | None:
    """Determine which pages a character range spans."""
    if not page_map:
        return None
    pages = set()
    for offset, page in sorted(page_map.items()):
        if offset <= end:
            pages.add(page)
    return sorted(pages) if pages else None
