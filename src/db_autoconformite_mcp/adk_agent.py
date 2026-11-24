"""The compliance agent on Google ADK (Agent Development Kit), with Gemini on Vertex AI.

Same MCP server, same system prompt, same skills as the Claude agent: ADK connects to the
server through its McpToolset (stdio), so no tool is rewritten and the guard and audit log
stay in front of every call.

    uv sync --extra adk
    # Vertex AI: GOOGLE_GENAI_USE_VERTEXAI=TRUE, GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION

The evaluation on the demo fleet is adk_eval.py.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from mcp import StdioServerParameters

from db_autoconformite_mcp.agent_eval import SKILLS, SYSTEM_PROMPT

MODEL = os.environ.get("ADK_MODEL", "gemini-3.5-flash")
TOOLS = ["list_instances", "get_config", "check_compliance", "correlate_sources",
         "explain_rule", "propose_remediation"]


def instruction(skill: str | None = None) -> str:
    """The Claude agent's system prompt, plus the skill when the task calls for one."""
    text = SYSTEM_PROMPT.read_text(encoding="utf-8")
    if skill:
        text += ("\n\n# Skill chargé pour cette tâche\n\n"
                 + (SKILLS / skill / "SKILL.md").read_text(encoding="utf-8"))
    return text


def toolset(args: list[str], timeout: float = 30.0) -> McpToolset:
    """The MCP server's tools, started as `python -m <args>` with this interpreter."""
    params = StdioServerParameters(command=sys.executable, args=["-m", *args],
                                   env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    return McpToolset(connection_params=StdioConnectionParams(server_params=params,
                                                              timeout=timeout),
                      tool_filter=TOOLS)


def demo_toolset(variant: str = "standard", audit: Path | None = None) -> McpToolset:
    args = ["db_autoconformite_mcp.demo_server", "--variant", variant]
    if audit is not None:
        args += ["--audit", str(audit)]
    return toolset(args)


def build_agent(tools: McpToolset, model=MODEL, skill: str | None = None) -> LlmAgent:
    # A callable instruction is passed to the model as is: a string would go through ADK's
    # {state} templating, and the prompt or a skill could one day contain braces.
    text = instruction(skill)
    return LlmAgent(name="agent_conformite", model=model,
                    description="Agent de conformité d'un parc de bases (lecture seule).",
                    instruction=lambda _ctx: text, tools=[tools])


def production_toolset() -> McpToolset:
    """The real fleet (docker compose), through the production server."""
    return toolset(["db_autoconformite_mcp.server"])
