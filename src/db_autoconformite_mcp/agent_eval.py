"""Evaluation of the compliance agent: does Claude use the tools well and answer safely?

    ANTHROPIC_API_KEY=... uv run python -m db_autoconformite_mcp.agent_eval
    uv run python -m db_autoconformite_mcp.agent_eval --only injection-cmdb

Each scenario of evals/scenarios.yaml runs a real agent loop: Claude (Messages API) with the
MCP server's tools, connected in-process to the deterministic demo fleet (demo.py). The
transcript is graded by fixed rules (tools called, order, required mentions, forbidden
claims), never by another model. The report gives the pass rate, the tool calls, tokens,
estimated cost and latency.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import yaml

from db_autoconformite_mcp import demo
from db_autoconformite_mcp.server import build_server

ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = ROOT / "evals" / "scenarios.yaml"
SKILLS = ROOT / ".claude" / "skills"
SYSTEM_PROMPT = ROOT / "prompts" / "agent-conformite.md"

MODEL = "claude-opus-5-5"
EFFORT = "medium"  # this model's default, set explicitly
MAX_TURNS = 12
USD_PER_MTOK = {"input": 4.00, "output": 20.00}  # claude-opus-5-5 list prices


# ---------------------------------------------------------------- grading (pure)
@dataclass
class Transcript:
    calls: list[dict] = field(default_factory=list)  # {"tool", "input", "is_error"}
    final: str = ""
    stop_reason: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0
    error: str = ""


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.replace("’", "'"))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text.lower())


def grade(scenario: dict, t: Transcript) -> list[str]:
    """Reasons the transcript fails the scenario; an empty list means it passes."""
    reasons: list[str] = []
    if t.error:
        return [f"run error: {t.error}"]
    if t.stop_reason == "refusal":
        reasons.append("the model refused")
    called = [c["tool"] for c in t.calls]
    for tool in scenario.get("tools_all", []):
        if tool not in called:
            reasons.append(f"tool never called: {tool}")
    any_of = scenario.get("tools_any", [])
    if any_of and not set(any_of) & set(called):
        reasons.append(f"none of these tools called: {any_of}")
    for a, b in scenario.get("order", []):
        if a in called and b in called and called.index(a) > called.index(b):
            reasons.append(f"{b} called before {a}")
    answer = norm(t.final)
    if not answer.strip():
        reasons.append("empty final answer")
    for item in scenario.get("must_mention", []):
        options = item if isinstance(item, list) else [item]
        if not any(norm(o) in answer for o in options):
            reasons.append(f"answer does not mention: {' | '.join(options)}")
    for pattern in scenario.get("forbidden", []):
        if re.search(pattern, answer):
            reasons.append(f"forbidden claim in answer: /{pattern}/")
    return reasons


def load_scenarios(path: Path = SCENARIOS) -> list[dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["scenarios"]


def system_prompt(scenario: dict) -> str:
    text = SYSTEM_PROMPT.read_text(encoding="utf-8")
    if scenario.get("skill"):  # as Claude Code would load the skill for this task
        skill = (SKILLS / scenario["skill"] / "SKILL.md").read_text(encoding="utf-8")
        text += "\n\n# Skill chargé pour cette tâche\n\n" + skill
    return text


# ---------------------------------------------------------------- the agent loop
async def run_scenario(scenario: dict, client, model: str = MODEL) -> Transcript:
    """One real agent loop: Claude + the MCP server's tools on the demo fleet."""
    import anthropic
    from mcp import Client

    t = Transcript()
    start = time.perf_counter()
    server = build_server(demo.fleet(scenario.get("variant", "standard")))
    try:
        async with Client(server) as mcp:
            tools = [{"name": tool.name, "description": tool.description or "",
                      "input_schema": tool.input_schema}
                     for tool in (await mcp.list_tools()).tools]
            messages: list[dict] = [{"role": "user", "content": scenario["prompt"]}]
            response = None
            for _ in range(MAX_TURNS):
                response = await client.beta.messages.create(
                    model=model, max_tokens=16000, system=system_prompt(scenario),
                    tools=tools, messages=messages,
                    output_config={"effort": EFFORT},
                    # Refusal fallback, routed by the server by refusal category.
                    betas=["server-side-fallback-2026-07-01"], fallbacks="default")
                t.input_tokens += response.usage.input_tokens or 0
                t.output_tokens += response.usage.output_tokens or 0
                t.stop_reason = response.stop_reason or ""
                if response.stop_reason == "refusal":
                    break
                messages.append({"role": "assistant", "content": response.content})
                if response.stop_reason == "pause_turn":
                    continue
                if response.stop_reason != "tool_use":
                    break
                results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue
                    result = await mcp.call_tool(block.name, block.input)
                    text = "".join(getattr(c, "text", "") for c in result.content)
                    if not text and result.structured_content is not None:
                        text = json.dumps(result.structured_content, ensure_ascii=False)
                    t.calls.append({"tool": block.name, "input": block.input,
                                    "is_error": bool(result.is_error)})
                    results.append({"type": "tool_result", "tool_use_id": block.id,
                                    "content": text, "is_error": bool(result.is_error)})
                messages.append({"role": "user", "content": results})
            if response is not None:
                t.final = "\n".join(b.text for b in response.content if b.type == "text")
    except anthropic.RateLimitError as exc:
        t.error = f"rate limited: {exc.message}"
    except anthropic.APIStatusError as exc:
        t.error = f"API error {exc.status_code}: {exc.message}"
    except anthropic.APIConnectionError:
        t.error = "network error"
    t.seconds = round(time.perf_counter() - start, 1)
    return t


def cost(t: Transcript) -> float:
    return (t.input_tokens * USD_PER_MTOK["input"]
            + t.output_tokens * USD_PER_MTOK["output"]) / 1e6


async def run_all(scenarios: list[dict], model: str = MODEL) -> dict:
    import anthropic

    client = anthropic.AsyncAnthropic()
    rows = []
    for sc in scenarios:
        t = await run_scenario(sc, client, model)
        reasons = grade(sc, t)
        rows.append({"id": sc["id"], "title": sc["title"], "passed": not reasons,
                     "reasons": reasons, "tools": [c["tool"] for c in t.calls],
                     "usd": round(cost(t), 4), **asdict(t)})
        print(f"{'PASS' if not reasons else 'FAIL'}  {sc['id']:22} {t.seconds:6.1f} s  "
              f"{len(t.calls)} tool calls  " + ("; ".join(reasons) if reasons else ""),
              flush=True)
    passed = sum(r["passed"] for r in rows)
    return {"generated_at": datetime.now(UTC).isoformat(timespec="seconds"), "model": model,
            "effort": EFFORT, "passed": passed, "total": len(rows),
            "pass_rate": round(passed / len(rows), 3) if rows else None,
            "usd_total": round(sum(r["usd"] for r in rows), 4), "results": rows}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Evaluate the compliance agent")
    p.add_argument("--only", nargs="*", help="scenario ids")
    p.add_argument("--out", default="evals/reports/latest.json")
    p.add_argument("--model", default=MODEL)
    args = p.parse_args(argv)
    scenarios = [s for s in load_scenarios() if not args.only or s["id"] in args.only]
    report = asyncio.run(run_all(scenarios, args.model))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str),
                   encoding="utf-8")
    print(f"\n{report['passed']}/{report['total']} passed, est. {report['usd_total']} USD "
          f"-> {out}")
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
