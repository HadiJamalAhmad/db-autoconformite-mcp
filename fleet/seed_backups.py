"""Write fleet/backups.jsonl: the backup tool's export for the demo fleet, relative to now.

    uv run python fleet/seed_backups.py

pg-prod-01: last success 3 h ago (compliant).
pg-prod-02: last success 50 h ago, and a FAILED run 2 h ago, which must not count.
pg-recette-01: no backup at all.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

OUT = Path(__file__).with_name("backups.jsonl")


def entries(now: datetime) -> list[dict]:
    def run(instance: str, hours_ago: float, status: str) -> dict:
        end = now - timedelta(hours=hours_ago)
        return {"instance": instance, "tool": "pgbackrest", "type": "full",
                "started_at": (end - timedelta(minutes=12)).isoformat(timespec="seconds"),
                "finished_at": end.isoformat(timespec="seconds"), "status": status}

    return [run("pg-prod-01", 27, "success"), run("pg-prod-01", 3, "success"),
            run("pg-prod-02", 50, "success"), run("pg-prod-02", 2, "failed")]


if __name__ == "__main__":
    OUT.write_text("".join(json.dumps(e) + "\n" for e in entries(datetime.now(UTC))),
                   encoding="utf-8")
    print(f"wrote {OUT}")
