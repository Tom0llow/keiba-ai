"""Filesystem contract for skills shared between Codex and Claude Code.

Codex reads `.agents/skills/` natively. Claude Code reads `.claude/skills/`,
where shared skills are per-skill symbolic links into `.agents/skills/` and
Claude-only skills are real directories.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
AGENTS_SKILLS = REPOSITORY_ROOT / ".agents" / "skills"
CLAUDE_SKILLS = REPOSITORY_ROOT / ".claude" / "skills"
SHARED_FRONTMATTER_KEYS = {"name", "description"}
SYMLINK_HELP = (
    "Shared skills must be checked out as symbolic links. On Windows enable Developer Mode, "
    "run `git config core.symlinks true`, and restore the links with "
    "`git checkout -- .claude/skills`."
)


def _frontmatter(skill_dir: Path) -> dict[str, str]:
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    match = re.match(r"---\r?\n(.*?)\r?\n---\r?\n", text, re.DOTALL)
    assert match is not None, f"{skill_dir / 'SKILL.md'} has no YAML frontmatter"
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        key_match = re.match(r"([A-Za-z][A-Za-z0-9_-]*):\s*(.*)", line)
        if key_match is not None:
            fields[key_match.group(1)] = key_match.group(2).strip()
    return fields


def _claude_entries() -> list[Path]:
    return sorted(CLAUDE_SKILLS.iterdir())


def _shared_links() -> list[Path]:
    return [entry for entry in _claude_entries() if entry.is_symlink()]


def test_claude_skills_contain_only_directories_and_links() -> None:
    plain_files = [
        entry.name
        for entry in _claude_entries()
        if not entry.is_symlink() and not entry.is_dir() and entry.name != "README.md"
    ]

    assert plain_files == [], SYMLINK_HELP


def test_at_least_one_skill_is_shared() -> None:
    assert _shared_links(), SYMLINK_HELP


def test_shared_links_resolve_to_the_same_skill_in_agents_skills() -> None:
    for link in _shared_links():
        target = link.resolve()

        assert target == (AGENTS_SKILLS / link.name).resolve(), link
        assert (target / "SKILL.md").is_file(), link


def test_shared_links_use_relative_targets() -> None:
    for link in _shared_links():
        target = Path(link.readlink().as_posix().replace("\\", "/"))

        assert not target.is_absolute(), link
        assert target.as_posix() == f"../../.agents/skills/{link.name}", link


def test_claude_only_skills_do_not_shadow_codex_skills() -> None:
    claude_only = [
        entry.name for entry in _claude_entries() if entry.is_dir() and not entry.is_symlink()
    ]

    assert claude_only, "expected at least one Claude-only skill"
    assert sorted(set(claude_only) & {path.name for path in AGENTS_SKILLS.iterdir()}) == []


@pytest.mark.parametrize("root", [AGENTS_SKILLS, CLAUDE_SKILLS], ids=["agents", "claude"])
def test_skill_frontmatter_name_matches_directory(root: Path) -> None:
    for skill_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        fields = _frontmatter(skill_dir)

        assert fields.get("name") == skill_dir.name, skill_dir
        assert fields.get("description"), skill_dir


def test_shared_skills_use_only_tool_neutral_frontmatter() -> None:
    for link in _shared_links():
        extra_keys = set(_frontmatter(link)) - SHARED_FRONTMATTER_KEYS

        assert extra_keys == set(), f"{link.name} uses tool-specific keys {sorted(extra_keys)}"
