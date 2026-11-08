# Documentation Language

This file defines the language of each document in the repository. The
language follows the document's purpose, not only who reads it.

## 1. Principle

- **English:** documents whose purpose is to instruct or configure agents.
- **Japanese:** documents whose purpose is to explain, record, or specify
  something for humans, even when agents also read them.

When the category of a new document is unclear, ask the human before writing
it.

## 2. Classification

| Language | Documents |
| --- | --- |
| English | `AGENTS.md`, `CLAUDE.md`, `docs/rules/`, `.agents/skills/`, `.claude/skills/`, `.claude/agents/` |
| English | Tool configuration and its comments: `.codex/`, `.claude/settings.json`, `.github/` except `pull_request_template.md`, `.vscode/`, `.gitignore`, `.pre-commit-config.yaml`, `pyproject.toml`, `configs/` |
| English | Handoff files in `.handoff/<task-id>/` other than `plan.md` and `pr-body.md` |
| English | Source code comments, docstrings, log and CLI messages, commit messages, and PR titles |
| Japanese | `README.md` and `ARCHITECTURE.md` |
| Japanese | Everything under `docs/` except `docs/rules/`: ADRs, table definitions, data assessments, preprocessing records, requirements, specifications, discussions, experiments, and design and refactoring records |
| Japanese | PR bodies (`.github/pull_request_template.md` and `.handoff/<task-id>/pr-body.md`) and `.handoff/<task-id>/plan.md` |

Test data and fixtures may contain Japanese values.

## 3. Writing Japanese documents

- Write prose, headings, list items, table cells, and the comments in
  directory-tree blocks in Japanese. Use the plain (non-polite) style that the
  existing documents use.
- Keep these in their original form: code, identifiers, paths, commands and
  options, configuration keys, table and column names, data values, quoted
  program output, URLs, product and standard names, and technical terms that
  existing Japanese documents already write in English, such as `snapshot`,
  `staging`, `archive`, and `manifest`.
- Translate ordinary words, such as repository, training, prediction,
  dependency, install, and permission, into the Japanese terms that existing
  documents use.
- Keep these defined terms in English: the DAMA-DMBOK data quality dimension
  and environmental element names used by the `data-assessment` skill, the
  status markers `To confirm` and `Not assessed`, the layer names `raw`,
  `processed`, and `datamart`, and ADR status values.
- In ADRs (`docs/decisions/ADR-000-template.md`), plan files, and PR bodies,
  keep the template headings and field names in English and write the content
  under them in Japanese.

## 4. Writing English documents

Write agent-facing documents only in English.

## 5. Translating an existing document

- Translate strictly. Keep the meaning, scope, order, and level of detail. Do
  not add, drop, summarize, or correct content; correct a factual error only in
  a separate change.
- Keep link targets, code spans, command and configuration blocks, numbers, and
  table structure unchanged.
- When a term or sentence has more than one plausible Japanese rendering with
  different meanings, or the source itself is ambiguous, ask the human instead
  of choosing.
