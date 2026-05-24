from pathlib import Path


def test_key_frontend_pages_are_ashare_only_in_user_facing_copy():
    root = Path("/home/work/worktowork/workspace/frontend")
    files = [
        root / "app/page.tsx",
        root / "app/finance/page.tsx",
        root / "app/finance/evaluations/page.tsx",
        root / "components/AppShell.tsx",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in files)

    for forbidden in ["SEC", "FinQA", "TAT-QA", "FinanceBench", "10-K"]:
        assert forbidden not in combined
    assert "A 股公告与情绪分析工作台" in combined


def test_user_callable_finance_routes_do_not_expose_legacy_public_datasets():
    route_file = Path("/home/work/worktowork/workspace/backend/app/routers/finance.py")
    text = route_file.read_text(encoding="utf-8")

    for forbidden in [
        "/datasets/build/sec-10k",
        "/datasets/import/financebench",
        "/datasets/import/finqa",
        "/datasets/import/tatqa",
        "/datasets/build/custom-10k",
        "/connectors/status",
        "/connectors/{name}/test",
        "SEC EDGAR 导入失败",
    ]:
        assert forbidden not in text
