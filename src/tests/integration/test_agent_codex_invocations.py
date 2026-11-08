"""Filesystem contract for Claude-only Codex invocations."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CLAUDE_SKILLS = REPOSITORY_ROOT / ".claude" / "skills"
MODEL_FLAG = '-m "$CODEX_MODEL"'
EFFORT_FLAG = '-c "model_reasoning_effort=\\"$CODEX_EFFORT\\""'
MODEL_SLUG_PATTERN = re.compile(r"\bgpt-\d")
CODEX_EXEC_PATTERN = re.compile(r"\bcodex\b.*\bexec\b")


def _claude_only_skill_files() -> list[Path]:
    """Return skill files in Claude-only skill directories."""
    return sorted(
        skill_dir / "SKILL.md"
        for skill_dir in CLAUDE_SKILLS.iterdir()
        if skill_dir.is_dir() and not skill_dir.is_symlink()
    )


def _codex_exec_commands(skill_file: Path) -> list[tuple[int, str]]:
    """Return fenced, continued Codex commands with their starting lines."""
    return _codex_exec_commands_from_lines(
        skill_file.read_text(encoding="utf-8").splitlines(), str(skill_file)
    )


def _codex_exec_commands_from_lines(lines: list[str], source: str) -> list[tuple[int, str]]:
    """Return fenced, continued Codex commands from one skill's lines."""
    commands: list[tuple[int, str]] = []
    in_code_block = False
    line_index = 0

    while line_index < len(lines):
        line = lines[line_index]
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            line_index += 1
            continue

        if not in_code_block:
            line_index += 1
            continue

        start_line_number = line_index + 1
        command_lines = [line]
        while command_lines[-1].rstrip().endswith("\\"):
            command_lines[-1] = command_lines[-1].rstrip()[:-1]
            line_index += 1
            assert line_index < len(lines), f"unterminated command in {source}:{start_line_number}"
            next_line = lines[line_index]
            if next_line.strip().startswith("```"):
                in_code_block = False
                break
            command_lines.append(next_line)

        command = " ".join(part.strip() for part in command_lines)
        if CODEX_EXEC_PATTERN.search(command):
            commands.append((start_line_number, command))
        line_index += 1

    return commands


def _commands_by_skill() -> dict[str, list[tuple[int, str]]]:
    """Return Codex invocations grouped by the owning Claude-only skill."""
    commands_by_skill: dict[str, list[tuple[int, str]]] = {}
    for skill_file in _claude_only_skill_files():
        commands = _codex_exec_commands(skill_file)
        if commands:
            commands_by_skill[skill_file.parent.name] = commands

    return commands_by_skill


def test_codex_exec_commands_only_use_fenced_code_blocks() -> None:
    assert _codex_exec_commands_from_lines(
        [
            "A prose mention of codex exec must not count.",
            "```bash",
            "codex --profile deep exec \\",
            '  -m "$CODEX_MODEL"',
            "```",
            "```text",
            'codex exec -m "$CODEX_MODEL"',
            "```",
        ],
        "example/SKILL.md",
    ) == [
        (3, 'codex --profile deep exec -m "$CODEX_MODEL"'),
        (7, 'codex exec -m "$CODEX_MODEL"'),
    ]


def test_codex_exec_continuation_stops_at_closing_fence() -> None:
    assert _codex_exec_commands_from_lines(
        [
            "```bash",
            "codex --profile deep exec \\",
            '  -m "$CODEX_MODEL" \\',
            "```",
            "A prose mention of codex exec must not count.",
            "```text",
            'codex exec -m "$CODEX_MODEL"',
            "```",
        ],
        "example/SKILL.md",
    ) == [
        (2, 'codex --profile deep exec -m "$CODEX_MODEL"'),
        (7, 'codex exec -m "$CODEX_MODEL"'),
    ]


def test_codex_exec_runs_are_found() -> None:
    commands_by_skill = _commands_by_skill()

    assert {"cc-design", "cc-implement", "cc-review"} <= set(commands_by_skill)


def test_every_codex_exec_sets_model_and_effort() -> None:
    for skill_name, commands in _commands_by_skill().items():
        for line_number, command in commands:
            location = f"{skill_name}:{line_number}"
            assert MODEL_FLAG in command, f"{location} is missing {MODEL_FLAG}"
            assert EFFORT_FLAG in command, f"{location} is missing {EFFORT_FLAG}"


def test_claude_skills_do_not_hardcode_codex_models() -> None:
    hardcoded_models: list[str] = []
    for skill_file in _claude_only_skill_files():
        for line_number, line in enumerate(
            skill_file.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if MODEL_SLUG_PATTERN.search(line):
                hardcoded_models.append(f"{skill_file.parent.name}:{line_number}")

    assert hardcoded_models == [], f"hard-coded Codex model(s): {hardcoded_models}"
