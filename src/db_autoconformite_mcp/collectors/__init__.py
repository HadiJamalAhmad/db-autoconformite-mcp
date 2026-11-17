"""Read-only collectors: one per engine, all producing engine-neutral `Facts`.

Rules for every collector:
- read-only session, fixed queries (no SQL ever comes from the agent), short timeouts;
- a query that fails leaves its fact missing (the rule then reports UNKNOWN) and records the
  error, so a permission problem is visible instead of silently passing.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import datetime

from db_autoconformite_mcp.models import Facts, Instance

Collector = Callable[[Instance, datetime], Facts]


def credentials(engine: str) -> tuple[str, str]:
    """The monitoring account for an engine, from the environment (never from the repo)."""
    prefix = {"postgresql": "AUTOCONF_PG", "oracle": "AUTOCONF_ORA"}[engine]
    user = os.environ.get(f"{prefix}_USER", "autoconformite_ro")
    password = os.environ.get(f"{prefix}_PASSWORD", "")
    return user, password


def default_collectors() -> dict[str, Collector]:
    from db_autoconformite_mcp.collectors import oracle, postgres

    return {"postgresql": postgres.collect, "oracle": oracle.collect}
