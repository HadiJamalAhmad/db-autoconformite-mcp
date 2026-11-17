"""Skills and prompts: valid frontmatter, and they only name tools the server really has."""

import re
from pathlib import Path

import pytest
import yaml
from test_server import EXPECTED_TOOLS

ROOT = Path(__file__).resolve().parents[1]
SKILLS = sorted((ROOT / ".claude" / "skills").glob("*/SKILL.md"))
TOOL_LIKE = re.compile(r"`([a-z]+(?:_[a-z]+)+)`")


def frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), path
    return yaml.safe_load(text.split("---\n")[1])


def test_the_three_skills_exist():
    assert [p.parent.name for p in SKILLS] == ["analyse-ecart", "audit-parc", "plan-remediation"]


@pytest.mark.parametrize("path", SKILLS, ids=lambda p: p.parent.name)
def test_skill_frontmatter_names_the_folder_and_says_when_to_use_it(path):
    meta = frontmatter(path)
    assert meta["name"] == path.parent.name
    assert "Utiliser quand" in meta["description"]


@pytest.mark.parametrize("path", [*SKILLS, ROOT / "prompts" / "agent-conformite.md"],
                         ids=lambda p: p.parent.name if p.name == "SKILL.md" else p.name)
def test_skills_and_prompts_only_name_existing_tools(path):
    named = set(TOOL_LIKE.findall(path.read_text(encoding="utf-8")))
    allowed = EXPECTED_TOOLS | {"in_scope", "db_autoconformite", "db-autoconformite"}
    unknown = {n for n in named if n not in allowed and n not in {"in_scope"}}
    assert not unknown, f"{path.name} names tools the server does not have: {unknown}"
