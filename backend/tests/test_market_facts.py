from app.models import MarketFactModel
from app.schemas import MarketFactResponse


def test_market_fact_model_and_response_fields():
    fact = MarketFactModel(
        id=1,
        workspace_id=1,
        company_id=2,
        ticker="600519",
        trade_date="2026-05-20",
        metric="close",
        label="收盘价",
        value=1688.0,
        unit="CNY",
        source="akshare",
        source_url="https://example.test",
        confidence=1.0,
        metadata_json={"market": "CN"},
    )

    response = MarketFactResponse.model_validate(fact)

    assert response.ticker == "600519"
    assert response.metric == "close"
    assert response.value == 1688.0
    assert response.metadata_json == {"market": "CN"}
