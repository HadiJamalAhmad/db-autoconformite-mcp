"""The MCP server, exercised through the real protocol with an in-process MCP client."""

import json

import pytest
from mcp import Client

from db_autoconformite_mcp.server import build_server

pytestmark = pytest.mark.anyio

EXPECTED_TOOLS = {"list_instances", "get_config", "check_compliance", "correlate_sources",
                  "explain_rule", "propose_remediation"}


@pytest.fixture
def anyio_backend():
    return "asyncio"


def text_of(result) -> str:
    return "".join(getattr(c, "text", "") for c in result.content)


def data_of(result):
    return result.structured_content if result.structured_content is not None \
        else json.loads(text_of(result))


async def test_the_server_exposes_exactly_the_documented_tools_all_read_only(fleet):
    async with Client(build_server(fleet)) as client:
        tools = (await client.list_tools()).tools
    assert {t.name for t in tools} == EXPECTED_TOOLS
    for t in tools:
        assert t.annotations.read_only_hint is True, t.name
        assert t.annotations.destructive_hint is False, t.name
        assert t.description, t.name


async def test_check_compliance_over_the_protocol(fleet):
    async with Client(build_server(fleet)) as client:
        result = await client.call_tool("check_compliance", {"instance": "pg-drift"})
    assert not result.is_error
    report = data_of(result)["instances"]["pg-drift"]
    assert report["summary"]["fail"] == 6 and report["summary"]["worst"] == "critical"


async def test_checking_all_covers_only_the_perimeter(fleet):
    async with Client(build_server(fleet)) as client:
        result = await client.call_tool("check_compliance", {"instance": "all"})
    assert set(data_of(result)["instances"]) == {"pg-ok", "pg-drift", "pg-recette", "ora-01"}


async def test_a_refused_call_is_a_tool_error_and_is_audited(fleet, tmp_path):
    async with Client(build_server(fleet)) as client:
        result = await client.call_tool("get_config", {"instance": "pg-cloud"})
    assert result.is_error and "out of scope" in text_of(result)
    last = json.loads((tmp_path / "audit.jsonl").read_text().splitlines()[-1])
    assert (last["tool"], last["outcome"]) == ("get_config", "refused")


async def test_correlation_and_remediation_over_the_protocol(fleet):
    async with Client(build_server(fleet)) as client:
        corr = data_of(await client.call_tool("correlate_sources", {}))
        plan = text_of(await client.call_tool("propose_remediation", {"instance": "pg-drift"}))
        rule = data_of(await client.call_tool("explain_rule", {"rule_id": "R02"}))
    assert {f["rule_id"] for f in corr["findings"]} >= {"C01", "C03", "C04"}
    assert "rien n'a été exécuté" in plan
    assert "V$DATABASE" in rule["source"]["oracle"]


async def test_the_baseline_is_readable_as_a_resource(fleet):
    async with Client(build_server(fleet)) as client:
        res = await client.read_resource("baseline://rules")
    assert "R01" in res.contents[0].text
