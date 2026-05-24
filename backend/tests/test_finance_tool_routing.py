from app.services.finance_agent import _analysis_node, _verifier_node, classify_finance_tool_groups


def test_finance_tool_groups_route_numeric_questions_to_structured_facts():
    groups = classify_finance_tool_groups("贵州茅台 2023 年营业收入和净利润率是多少？")

    assert "structured_facts" in groups
    assert "calculation" in groups


def test_finance_tool_groups_route_market_questions_to_market_facts():
    groups = classify_finance_tool_groups("600519 最近收盘价和市值是多少？")

    assert "market_facts" in groups


def test_finance_tool_groups_route_announcement_questions_to_announcement_search():
    groups = classify_finance_tool_groups("600519 最近有哪些年度报告公告？")

    assert "announcement_search" in groups


def test_verifier_accepts_structured_fact_answer_without_citations():
    state = {
        "company_ticker": "600519",
        "question": "贵州茅台 2023 年营业收入是多少？",
        "tool_groups": ["structured_facts"],
        "citations": [],
        "facts": [
            {
                "metric": "revenue",
                "canonical_metric": "Revenues",
                "label": "营业总收入",
                "value": 1500.0,
                "unit": "CNY",
                "source": "akshare",
            }
        ],
        "calculations": [],
        "answer": "600519 结构化指标：营业总收入=1500.0 CNY",
    }

    verified = _verifier_node(None, state)

    assert verified["verification"]["passed"] is True
    assert verified["verification"]["structured_facts_used"] == 1


def test_analysis_labels_akshare_as_structured_data_not_xbrl():
    state = {
        "company_ticker": "600519",
        "question": "贵州茅台营业收入是多少？",
        "citations": [],
        "facts": [
            {
                "metric": "revenue",
                "canonical_metric": "Revenues",
                "label": "营业总收入",
                "value": 1500.0,
                "unit": "CNY",
                "source": "akshare",
            }
        ],
        "calculations": [],
    }

    analyzed = _analysis_node(None, state)

    assert "结构化数据" in analyzed["answer"]
    assert "XBRL" not in analyzed["answer"]


def test_analysis_returns_controlled_answer_when_research_data_is_missing():
    state = {
        "company_ticker": "000725",
        "question": "结合公告、财务事实、行情热度和市场情绪，解释这家公司今天需要关注的变化。",
        "citations": [],
        "facts": [],
        "calculations": [],
        "research_summary": {
            "available_signals": {"heat_score": 88, "hot_rank": 1},
            "cannot_infer": [
                "缺少结构化财务事实，不能判断收入、利润、资产负债等基本面变化。",
                "缺少已导入公告/年报，不能确认今天是否存在可追溯披露变化。",
            ],
            "can_infer": ["当前可以把市场热度作为关注度变化的弱信号。"],
            "next_actions": [
                {"key": "import_annual_report", "label": "导入年报"},
                {"key": "sync_financial_facts", "label": "同步财务事实"},
            ],
        },
    }

    analyzed = _analysis_node(None, state)

    assert "今日结论" in analyzed["answer"]
    assert "只能基于热度" in analyzed["answer"]
    assert "不能判断收入、利润、资产负债" in analyzed["answer"]
    assert "导入年报" in analyzed["answer"]
