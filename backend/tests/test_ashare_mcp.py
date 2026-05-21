import importlib.util
import json
from pathlib import Path


def _load_mcp_server():
    server_path = Path(__file__).resolve().parents[2] / "mcp" / "server.py"
    spec = importlib.util.spec_from_file_location("mcp_server_under_test", server_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_mcp_lists_ashare_tools():
    server = _load_mcp_server()

    names = {tool["name"] for tool in server.TOOLS}

    assert "search_ashare_announcements" in names
    assert "get_ashare_annual_report" in names
    assert "list_ashare_market_facts" in names


def test_mcp_search_ashare_announcements_calls_connector(monkeypatch):
    server = _load_mcp_server()
    monkeypatch.setattr(
        server,
        "search_announcements",
        lambda **_kwargs: [{"ticker": "600519", "announcement_title": "贵州茅台2023年年度报告"}],
    )

    response = json.loads(server.handle_tool_call("search_ashare_announcements", {"ticker": "600519"}))

    assert response["ok"] is True
    assert response["data"][0]["ticker"] == "600519"
