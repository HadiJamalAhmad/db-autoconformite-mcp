"""Evaluation of the ADK agent (Gemini on Vertex AI) on the same eight scenarios as Claude.

    # Vertex AI credentials (gcloud auth application-default login, or Workload Identity in CI)
    GOOGLE_GENAI_USE_VERTEXAI=TRUE GOOGLE_CLOUD_PROJECT=... GOOGLE_CLOUD_LOCATION=global \
        uv run --extra adk python -m db_autoconformite_mcp.adk_eval
    uv run --extra adk python -m db_autoconformite_mcp.adk_eval --only injection-cmdb

Each scenario runs a real ADK agent: Gemini with the MCP server's tools, the server started
over stdio on the deterministic demo fleet (demo_server.py). The transcript is graded by the
SAME fixed rules as the Claude agent (agent_eval.grade), never by another model. Each run also
checks that the server's audit log holds one line per tool call the agent made.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from google.adk.agents.run_config import RunConfig
from google.adk.runners import InMemoryRunner
from google.genai import types

from db_autoconformite_mcp.adk_agent import MODEL, build_agent, demo_toolset
from db_autoconformite_mcp.agent_eval import Transcript, grade, load_scenarios

MAX_LLM_CALLS = 24  # the Claude loop allows 12 turns; ADK counts each model call
REFUSALS = {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "RECITATION"}


def audit_lines(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


async def run_scenario(scenario: dict, model=MODEL, audit: Path | None = None) -> Transcript:
    """One real ADK run: the agent, the MCP server over stdio on the demo fleet, the prompt."""
    t = Transcript()
    start = time.perf_counter()
    tools = demo_toolset(scenario.get("variant", "standard"), audit)
    agent = build_agent(tools, model=model, skill=scenario.get("skill"))
    runner = InMemoryRunner(agent=agent, app_name="conformite")
    try:
        session = await runner.session_service.create_session(app_name="conformite",
                                                               user_id="eval")
        message = types.Content(role="user", parts=[types.Part(text=scenario["prompt"])])
        async for event in runner.run_async(user_id="eval", session_id=session.id,
                                            new_message=message,
                                            run_config=RunConfig(max_llm_calls=MAX_LLM_CALLS)):
            for call in event.get_function_calls():
                t.calls.append({"tool": call.name, "input": dict(call.args or {}),
                                "is_error": False})
            for resp in event.get_function_responses():
                body = resp.response or {}
                if body.get("isError") or body.get("error"):
                    for c in reversed(t.calls):
                        if c["tool"] == resp.name:
                            c["is_error"] = True
                            break
            if event.usage_metadata:
                u = event.usage_metadata
                t.input_tokens += u.prompt_token_count or 0
                t.output_tokens += (u.candidates_token_count or 0) + (u.thoughts_token_count or 0)
            if event.finish_reason:
                reason = getattr(event.finish_reason, "name", str(event.finish_reason))
                t.stop_reason = "refusal" if reason in REFUSALS else reason.lower()
            if event.is_final_response() and event.content and event.content.parts:
                text = "".join(p.text for p in event.content.parts if p.text and not p.thought)
                if text:
                    t.final = text
    except Exception as exc:  # network, quota, auth: recorded, the scenario then fails
        t.error = f"{type(exc).__name__}: {str(exc)[:300]}"
    finally:
        await runner.close()
        await tools.close()
    t.seconds = round(time.perf_counter() - start, 1)
    return t


def cost(t: Transcript, usd_per_mtok: tuple[float, float] | None) -> float | None:
    """Estimated cost, only when the caller gives the list prices it read (they change)."""
    if usd_per_mtok is None:
        return None
    return round((t.input_tokens * usd_per_mtok[0] + t.output_tokens * usd_per_mtok[1]) / 1e6, 4)


async def run_all(scenarios: list[dict], model=MODEL,
                  usd_per_mtok: tuple[float, float] | None = None) -> dict:
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for sc in scenarios:
            audit = Path(tmp) / f"{sc['id']}.jsonl"
            t = await run_scenario(sc, model, audit)
            reasons = grade(sc, t)
            logged = audit_lines(audit)
            # Every tool call the agent made must have reached the server's audit log.
            audit_ok = len(logged) == len(t.calls)
            rows.append({"id": sc["id"], "title": sc["title"], "passed": not reasons,
                         "reasons": reasons, "tools": [c["tool"] for c in t.calls],
                         "audit_lines": len(logged), "audit_ok": audit_ok,
                         "usd": cost(t, usd_per_mtok), **asdict(t)})
            print(f"{'PASS' if not reasons else 'FAIL'}  {sc['id']:22} {t.seconds:6.1f} s  "
                  f"{len(t.calls)} tool calls, {len(logged)} audited  "
                  + ("; ".join(reasons) if reasons else ""), flush=True)
    passed = sum(r["passed"] for r in rows)
    usd = [r["usd"] for r in rows if r["usd"] is not None]
    return {"generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "framework": "google-adk", "model": getattr(model, "model", model),
            "passed": passed, "total": len(rows),
            "pass_rate": round(passed / len(rows), 3) if rows else None,
            "audit_ok": all(r["audit_ok"] for r in rows),
            "usd_per_mtok": list(usd_per_mtok) if usd_per_mtok else None,
            "usd_total": round(sum(usd), 4) if usd else None,
            "input_tokens": sum(r["input_tokens"] for r in rows),
            "output_tokens": sum(r["output_tokens"] for r in rows), "results": rows}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Evaluate the ADK compliance agent (Gemini)")
    p.add_argument("--only", nargs="*", help="scenario ids")
    p.add_argument("--out", default="evals/reports/adk-latest.json")
    p.add_argument("--model", default=MODEL)
    p.add_argument("--usd-per-mtok", nargs=2, type=float, metavar=("INPUT", "OUTPUT"),
                   help="list prices read on the vendor's page, to estimate the cost")
    args = p.parse_args(argv)
    scenarios = [s for s in load_scenarios() if not args.only or s["id"] in args.only]
    report = asyncio.run(run_all(scenarios, args.model,
                                 tuple(args.usd_per_mtok) if args.usd_per_mtok else None))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str),
                   encoding="utf-8")
    print(f"\n{report['passed']}/{report['total']} passed, audit log complete: "
          f"{report['audit_ok']} -> {out}")
    return 0 if report["passed"] == report["total"] and report["audit_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
