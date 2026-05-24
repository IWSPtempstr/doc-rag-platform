"""Utilities for parsing and binding financial report sections."""

from __future__ import annotations

import re

US_REPORT_ITEMS = {
    "1": "Business",
    "1A": "Risk Factors",
    "7": "Management Discussion and Analysis",
    "7A": "Market Risk",
    "8": "Financial Statements",
}

ASHARE_REPORT_SECTIONS = {
    "company_profile": "公司简介和主要财务指标",
    "management_discussion": "管理层讨论与分析",
    "risk": "可能面对的风险",
    "financial_statements": "财务报告",
    "important_events": "重要事项",
}


def parse_financial_report_sections(text: str) -> list[dict]:
    """Parse A-share annual report sections, falling back to English item sections."""
    sections = _parse_ashare_report_sections(text)
    if sections:
        return sections
    return _parse_us_report_sections(text)


def _parse_us_report_sections(text: str) -> list[dict]:
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
        if code not in US_REPORT_ITEMS:
            continue
        start = match.start()
        end = deduped[idx + 1].start() if idx + 1 < len(deduped) else len(text)
        if end - start < 500:
            continue
        title_tail = (match.group(2) or "").strip()
        title = title_tail or US_REPORT_ITEMS[code]
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


def _parse_ashare_report_sections(text: str) -> list[dict]:
    if not text:
        return []

    patterns = [
        ("company_profile", r"(?:第[一二]节\s*)?(?:公司简介和主要财务指标|公司基本情况|主要会计数据和财务指标)"),
        ("management_discussion", r"(?:第[三四]节\s*)?(?:管理层讨论与分析|董事会报告|经营情况讨论与分析)"),
        ("risk", r"(?:可能面对的风险|公司面临的风险和应对措施|风险因素)"),
        ("important_events", r"(?:第[五六]节\s*)?(?:重要事项|重大事项)"),
        ("financial_statements", r"(?:第[十十一二]+节\s*)?(?:财务报告|财务报表|审计报告)"),
    ]
    matches = []
    for code, pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            matches.append((match.start(), match.end(), code, match.group(0).strip()))
    matches.sort(key=lambda item: item[0])

    deduped = []
    seen: set[tuple[str, int]] = set()
    for start, end, code, title in matches:
        key = (code, start // 1000)
        if key in seen:
            continue
        seen.add(key)
        deduped.append((start, end, code, title))

    sections = []
    for idx, (start, _match_end, code, title) in enumerate(deduped):
        end = deduped[idx + 1][0] if idx + 1 < len(deduped) else len(text)
        if end - start < 300:
            continue
        content = text[start:end].strip()
        sections.append(
            {
                "item_code": code,
                "title": (title or ASHARE_REPORT_SECTIONS.get(code, code))[:300],
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
