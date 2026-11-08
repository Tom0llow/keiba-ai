"""Repository documentation language contract."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
JAPANESE_CHARACTER = re.compile(
    r"[\u3000-\u303f\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uff00-\uffef]"
)


def _agent_facing_document_groups() -> dict[str, list[Path]]:
    agents_skills = REPOSITORY_ROOT / ".agents" / "skills"
    return {
        "AGENTS.md": [path for path in [REPOSITORY_ROOT / "AGENTS.md"] if path.is_file()],
        "CLAUDE.md": [path for path in [REPOSITORY_ROOT / "CLAUDE.md"] if path.is_file()],
        "docs/rules": sorted((REPOSITORY_ROOT / "docs" / "rules").rglob("*.md")),
        ".agents/skills/**/*.md": sorted(agents_skills.rglob("*.md")),
        ".agents/skills/**/*.yaml": sorted(agents_skills.rglob("*.yaml")),
        ".claude/skills/cc-*": sorted(
            path
            for skill_dir in (REPOSITORY_ROOT / ".claude" / "skills").glob("cc-*")
            for path in skill_dir.rglob("*.md")
        ),
        ".claude/agents": sorted((REPOSITORY_ROOT / ".claude" / "agents").glob("*.md")),
    }


def _agent_facing_documents() -> list[Path]:
    return sorted({path for paths in _agent_facing_document_groups().values() for path in paths})


def test_every_agent_facing_document_group_is_found() -> None:
    empty_groups = [name for name, paths in _agent_facing_document_groups().items() if not paths]

    assert empty_groups == []


def test_agent_facing_documents_contain_no_japanese_characters() -> None:
    failures = [
        f"{path.relative_to(REPOSITORY_ROOT)}:{line_number}: {line}"
        for path in _agent_facing_documents()
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if JAPANESE_CHARACTER.search(line)
    ]

    assert failures == [], "\n".join(failures)
