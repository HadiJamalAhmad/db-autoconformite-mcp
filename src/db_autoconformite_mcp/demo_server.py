"""The MCP server on the deterministic demo fleet, over stdio.

The Claude evaluation (agent_eval.py) connects to the server in-process. Agent frameworks that
start MCP servers as a subprocess, such as Google ADK, need it as a command instead:

    uv run python -m db_autoconformite_mcp.demo_server --variant injection --audit audit.jsonl

Same tools, same guard and same audit log as the real server; only the fleet is the demo one.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from db_autoconformite_mcp import demo
from db_autoconformite_mcp.server import build_server


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="MCP server on the demo fleet (stdio)")
    p.add_argument("--variant", default="standard", choices=demo.VARIANTS)
    p.add_argument("--audit", type=Path, default=None, help="audit log (JSON lines)")
    args = p.parse_args(argv)
    build_server(demo.fleet(args.variant, audit_path=args.audit)).run()


if __name__ == "__main__":
    main()
