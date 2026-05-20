"""Utilities for parsing and binding 10-K sections."""

from __future__ import annotations

import re

TARGET_ITEMS = {
    "1": "Business",
    "1A": "Risk Factors",
    "7": "Management Discussion and Analysis",
    "7A": "Market Risk",
    "8": "Financial Statements",
}


def parse_10k_sections(text: str) -> list[dict]:
    """Parse common 10-K Item sections from plain text or stripped HTML."""
    if not text:
        return []

    pattern = re.compile(
        r"(?im)^\s*item\s+(1a|7a|1|7|8)\.?\s*[-:–—]?\s*([^\n\r]{0,140})"
    )
    raw_matches = list(pattern.finditer(text))
    deduped = []
    seen_positions: set[tuple[str, int]] = set()
    for match in raw_matches:
        code = match.group(1).upper()
        # Ignore probable table-of-contents repeats by requiring a minimum body gap.
        key = (code, match.start() // 1000)
        if key in seen_positions:
            continue
        seen_positions.add(key)
        deduped.append(match)

    sections = []
    for idx, match in enumerate(deduped):
        code = match.group(1).upper()
        if code not in TARGET_ITEMS:
            continue
        start = match.start()
        end = deduped[idx + 1].start() if idx + 1 < len(deduped) else len(text)
        if end - start < 500:
            continue
        title_tail = (match.group(2) or "").strip()
        title = title_tail or TARGET_ITEMS[code]
        content = text[start:end].strip()
        sections.append(
            {
                "item_code": code,
                "title": title[:300],
                "char_start": start,
                "char_end": end,
                "content_preview": content[:1200],
            }
        )
    return sections


def attach_section_metadata(chunks: list[dict], sections: list[dict]) -> list[dict]:
    """Attach section item/title metadata to chunks by char offset overlap."""
    if not chunks or not sections:
        return chunks

    for chunk in chunks:
        meta = chunk.get("metadata", {})
        start = meta.get("char_offset_start", 0)
        end = meta.get("char_offset_end", start + meta.get("char_count", 0))
        best = None
        best_overlap = 0
        for section in sections:
            overlap = max(0, min(end, section["char_end"]) - max(start, section["char_start"]))
            if overlap > best_overlap:
                best = section
                best_overlap = overlap
        if best:
            meta["section_item"] = best["item_code"]
            meta["section_title"] = best["title"]
    return chunks

