# Repository Skills

Skills are split by the tool that runs them. Codex reads `.agents/skills/`;
Claude Code reads `.claude/skills/`. Roles and handoffs are defined in
`docs/rules/agent-collaboration.md`.

## Shared skills (canonical here, linked from `.claude/skills/`)

| Skill | Use |
| --- | --- |
| `implement-feature` | Code-and-test discipline for new behavior |
| `fix-bug` | Diagnosis, regression test, and fix discipline for defects |
| `review-rubric` | Read-only defect-first review rubric and severities |
| `data-assessment` | Assess data management against seven DMBOK environmental elements and nine data-quality dimensions |
| `data-preprocessing` | Preview and apply approved transformations from raw to processed or datamart |
| `table-definition` | Document existing or planned raw, processed, and datamart tables |

Shared skills must stay tool-neutral: frontmatter has only `name` and
`description`, and the body names no tool-specific commands. Codex display
metadata in `agents/openai.yaml` is allowed; Claude Code ignores it.

To share a new skill, create `.agents/skills/<name>/` and add the link:

```powershell
New-Item -ItemType SymbolicLink -Path .claude\skills\<name> -Target ..\..\.agents\skills\<name>
```

On Windows this needs Developer Mode and `git config core.symlinks true`.
`src/tests/integration/test_agent_skills_layout.py` checks the layout.

## Codex-only skills

| Skill | Use |
| --- | --- |
| `implement-plan` | Implement an approved `.handoff/<task-id>/plan.md` (and findings rounds) in the task worktree |

## Claude-only skills (`.claude/skills/`)

| Skill | Use |
| --- | --- |
| `cc-task` | Full lifecycle coordinator from requirement to a READY, App-authored PR |
| `cc-design` | Requirement to approved plan |
| `cc-implement` | Run Codex on the plan or findings in the worktree and verify the result |
| `cc-review` | Dual independent review (Claude subagent + Codex read-only) and adjudication |
| `cc-ship` | Commit, App push, App PR, and CI |

Keep skills focused. If a workflow becomes materially different, prefer a
separate skill rather than turning one skill into a catch-all process.
