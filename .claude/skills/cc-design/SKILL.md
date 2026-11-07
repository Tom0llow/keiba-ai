---
name: cc-design
description: Turn a requirement into an approved implementation plan at .handoff/<task-id>/plan.md for Codex to implement. Read-only for tracked files. Use as the design phase of cc-task or when the user asks for a plan only.
---

# Design an Implementation Plan

The plan is the contract Codex implements and Claude reviews against. Write it
so that a fresh agent with no chat history can implement it correctly.

## Workflow

1. Read `AGENTS.md`, `ARCHITECTURE.md`, `docs/rules/architecture.md`,
   `docs/rules/coding-style.md`, `docs/rules/testing.md`, and the ADRs in
   `docs/decisions/` that touch the affected area.
2. Inspect the current code, tests, and callers. Cite concrete `path:line`
   locations. Do not edit tracked files.
3. Choose the smallest coherent design. Decide whether an ADR is required
   (`docs/decisions/README.md`); if so, the ADR is part of the plan.
4. Write `.handoff/<task-id>/plan.md` with the template below. Every
   acceptance criterion must be checkable by a test or a command.
5. Optional second opinion - when the plan changes architecture, a public or
   persisted contract, or a security boundary, ask Codex for a read-only
   critique and fold in valid points (at most two rounds):

   ```bash
   codex exec -C "$ROOT" -s read-only -c 'windows.sandbox="unelevated"' \
     -o "$HANDOFF/codex-plan-review-<n>.md" \
     "Critique the implementation plan at $HANDOFF/plan.md against this repository. Read-only. Report gaps, wrong assumptions, missing tests, and simpler alternatives with file:line evidence." \
     < /dev/null
   ```

6. **GATE 1** - present a short summary and the plan path, list open
   questions, and wait for explicit approval. "Open questions" must be empty
   before approval. On approval set `Status: Approved (<date>, by human)`.

## Plan template

```markdown
# Plan: <title>

- Task ID: <task-id>
- Status: Draft
- Rules: docs/rules/agent-collaboration.md

## Goal
## Non-goals
## Current behavior
<facts with path:line references>
## Design
- Placement and responsibilities (per ARCHITECTURE.md):
- Public or persisted contract changes: none | <details>
- ADR: not needed | new ADR-NNN <title> | relevant: ADR-NNN
- Dependencies: no change | <change, requires human approval>
## Implementation steps
1. <step> - files: <paths>
## Acceptance criteria
- AC-1: <observable, testable criterion>
## Test plan
- <test file>: <cases>; unit or integration and why
## Validation
- uv run ruff format --check .
- uv run ruff check .
- uv run mypy src
- uv run pytest
## Risks
## Open questions
```
