"""Optional structured A-share data provider adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class StructuredFact:
    metric: str
    label: str
    value: float | None
    unit: str
    period: str | None
    source: str
    evidence: str | None = None
    confidence: float = 1.0
    metadata: dict[str, Any] | None = None


@dataclass
class MarketFact:
    metric: str
    label: str
    value: float | None
    unit: str
    trade_date: str
    source: str
    source_url: str | None = None
    confidence: float = 1.0
    metadata: dict[str, Any] | None = None


def load_akshare_provider():
    try:
        import akshare as ak  # type: ignore
    except Exception as exc:
        raise RuntimeError("akshare 未安装，无法同步 A 股结构化事实") from exc
    return ak


def normalize_financial_value(value: Any) -> float | None:
    if value in (None, "", "--"):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace(",", "").strip()
    try:
        return float(text)
    except ValueError:
        return None
