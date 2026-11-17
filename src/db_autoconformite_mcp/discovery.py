"""Network discovery: which databases actually answer, under which name.

Scans the inventory's endpoints plus the extra ranges in fleet/discovery.yaml, and asks each
PostgreSQL that answers for its own name (cluster_name). An instance that answers but is not
in the inventory is what correlation reports as C01.
"""

from __future__ import annotations

import os
import socket
from pathlib import Path

import yaml

from db_autoconformite_mcp.models import Instance

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCAN = Path(os.environ.get("AUTOCONF_DISCOVERY", ROOT / "fleet" / "discovery.yaml"))


def open_port(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def endpoints(inventory: dict[str, Instance], scan_file: Path = DEFAULT_SCAN):
    seen = set()
    for inst in inventory.values():
        if inst.in_scope:
            seen.add((inst.engine, inst.host, inst.port))
    if scan_file.exists():
        data = yaml.safe_load(scan_file.read_text(encoding="utf-8")) or {}
        for r in data.get("scan", []):
            for port in range(r["ports"][0], r["ports"][1] + 1):
                seen.add((r["engine"], r["host"], port))
    return sorted(seen)


def discover(inventory: dict[str, Instance], scan_file: Path = DEFAULT_SCAN) -> set[str]:
    from db_autoconformite_mcp.collectors import postgres

    found: set[str] = set()
    for engine, host, port in endpoints(inventory, scan_file):
        if not open_port(host, port):
            continue
        if engine == "postgresql":
            name = postgres.identify(host, port)
            if name:
                found.add(name)
        else:
            # Oracle: the inventory id stands for the endpoint once it answers.
            for inst in inventory.values():
                if (inst.engine, inst.host, inst.port) == (engine, host, port):
                    found.add(inst.id)
    return found
