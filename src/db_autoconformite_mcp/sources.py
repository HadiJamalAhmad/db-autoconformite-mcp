"""The non-database sources the agent correlates: the inventory (CMDB) and the backup log.

Both are files here, as an export from a CMDB and from a backup tool would be. Readers are
strict: an inventory entry without an engine, host or port is an error, not a guess.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import yaml

from db_autoconformite_mcp.models import Instance

ROOT = Path(__file__).resolve().parents[2]
# Overridable, e.g. the CI's Oracle job points AUTOCONF_INVENTORY at its own inventory.
DEFAULT_INVENTORY = Path(os.environ.get("AUTOCONF_INVENTORY", ROOT / "fleet" / "inventory.yaml"))
DEFAULT_BACKUP_LOG = Path(os.environ.get("AUTOCONF_BACKUP_LOG", ROOT / "fleet" / "backups.jsonl"))

REQUIRED = ("id", "engine", "host", "port", "service", "environment", "hosting")


def load_inventory(path: Path = DEFAULT_INVENTORY) -> dict[str, Instance]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    out: dict[str, Instance] = {}
    for row in data["instances"]:
        missing = [k for k in REQUIRED if k not in row]
        if missing:
            raise ValueError(f"inventory entry {row.get('id', '?')}: missing {missing}")
        if row["id"] in out:
            raise ValueError(f"duplicate inventory id {row['id']}")
        out[row["id"]] = Instance(
            id=row["id"], engine=row["engine"], host=row["host"], port=int(row["port"]),
            service=row["service"], environment=row["environment"], hosting=row["hosting"],
            owner=row.get("owner") or "", criticality=row.get("criticality", "standard"),
            allowed_admins=tuple(row.get("allowed_admins", [])))
    return out


def load_backup_log(path: Path = DEFAULT_BACKUP_LOG) -> dict[str, datetime]:
    """Latest successful backup per instance, from a JSON-lines export of the backup tool."""
    latest: dict[str, datetime] = {}
    if not path.exists():
        return latest
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        if entry.get("status") != "success":
            continue  # a failed backup is no backup
        at = datetime.fromisoformat(entry["finished_at"])
        if entry["instance"] not in latest or at > latest[entry["instance"]]:
            latest[entry["instance"]] = at
    return latest
