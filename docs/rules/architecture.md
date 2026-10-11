# Architecture Rules

`ARCHITECTURE.md` is the authoritative description of the system that currently
exists. This file defines how that architecture may evolve.

## 1. Preserve the implemented boundaries

The repository contains a CLI, data acquisition and preprocessing, processed
data loading, feature generation, and ranking-model evaluation. Its current
source boundary is:

```text
src/main.py    # user-facing CLI
src/data/      # retrieval, preprocessing, and processed-data loading
src/features/  # feature generation
src/models/    # ranking and evaluation
src/tests/     # application and environment tests
```

`ARCHITECTURE.md` and Accepted ADRs describe implemented contracts. The project
remains uninstalled as a Python distribution. Do not recover or infer additional
contracts from an earlier prototype, ignored file, or stale document.

New product behavior must trace to an explicit requirement. A durable design
decision must also trace to an Accepted ADR when the decision warrants one.

## 2. Design only what the requirement needs

Before adding a module or boundary:

1. state the observable behavior being implemented;
2. identify the smallest responsibility needed for it;
3. inspect current code, tests, dependencies, and Accepted ADRs;
4. choose the simplest placement that keeps dependencies clear; and
5. avoid abstractions intended only for hypothetical future requirements.

Do not introduce generic framework layers, plugin systems, repositories,
service containers, or adapter hierarchies without a current requirement.

## 3. Module responsibilities and dependencies

Introduce product code under `src/` only when an explicit requirement or ADR
establishes its module and packaging boundary. Each module should own one
coherent responsibility and have a name that describes that responsibility.

- Keep imports acyclic and free of runtime work.
- Higher-level orchestration may depend on lower-level calculations; lower-level
  code must not import an entry point merely to share behavior.
- Pass important dependencies explicitly instead of constructing hidden global
  clients deep in the package.
- Do not create an undifferentiated `utils` module for unrelated behavior.
- Keep public interfaces as small as the current callers require.

Keep entry points responsible for boundary concerns and delegation rather than
product calculations. Changes to their contract must follow the requirement
and relevant Accepted ADRs.

### Cookiecutter Data Science reference layout

The table and tree below illustrate the template's separation of source code,
data stages, experiments, reference material, and outputs. They do not describe
the current repository or change the source boundary above. Adopt a part of
this layout only when an explicit requirement needs it:

| Content | Placement |
| --- | --- |
| Reusable Python behavior | `src/`; group implemented work by data creation, features, models, and visualization. |
| Automated behavior tests | `src/tests/`; group related tests so the source they cover is easy to find. |
| Datasets | `data/external/` and `data/raw/` for inputs; `data/interim/` and `data/processed/` for derived outputs. |
| Model and report artifacts | Root `models/` for trained models and predictions; `reports/figures/` for generated analysis. |
| Exploration and reference material | `notebooks/` for exploration; `references/` for data dictionaries and manuals. |
| Project documentation | `docs/` and the repository `README.md`, as appropriate. |

Within the example's `src/`, the `data/`, `features/`, `models/`, and
`visualization/` directories distinguish dataset creation, feature computation,
model code, and plotting. Root `models/` holds generated artifacts;
`src/models/` holds Python code. Keep I/O at explicit boundaries.

If notebooks are introduced for exploration or communication, call reusable
package code from them. Move repeated processing and model logic into importable
modules so experiments and later applications can share the same behavior.
Preserve raw inputs and write derived data to distinct outputs through
reproducible steps. Record the source data, code revision, configuration, and
evaluation metrics when experiments need to be reproduced. Do not copy a
template's full directory tree into this repository before those
responsibilities exist.

The following future layout follows the Cookiecutter Data Science v1 example
while retaining this repository's environment and test files. It is a reference
diagram, not a scaffold to create now or a specification of Python import paths:

```text
.
├── README.md
├── pyproject.toml
├── uv.lock
├── data/
│   ├── external/                 # Inputs from third parties
│   ├── raw/                      # Original, immutable inputs
│   ├── interim/                  # Intermediate transformed data
│   └── processed/                # Final data prepared for modeling
├── docs/                         # Project documentation and decisions
├── models/                       # Trained models, predictions, and summaries
├── notebooks/                    # Exploratory notebooks
├── references/                   # Data dictionaries and manuals
├── reports/                      # Generated analysis
│   └── figures/                  # Generated figures
└── src/
    ├── __init__.py
    ├── data/
    │   └── make_dataset.py       # Dataset creation code
    ├── features/
    │   └── build_features.py     # Feature computation code
    ├── models/
    │   ├── train_model.py        # Training code
    │   └── predict_model.py      # Inference code
    ├── visualization/
    │   └── visualize.py          # Plotting code
    └── tests/                    # Tests for implemented behavior
```

Name notebooks by order, author, and purpose when they are introduced, for
example, `1.0-ab-initial-data-exploration.ipynb`. The existing
`pyproject.toml` and `uv.lock` define this repository's environment; the
template's `requirements.txt`, `setup.py`, `tox.ini`, and `Makefile` are not
required to use its directory organization.

## 4. I/O and side-effect boundaries

Filesystem, database, network, subprocess, clock, environment, and randomness
access must be explicit and concentrated near an appropriate boundary.
Calculation code should be testable without real external services whenever
practical.

- Do not perform I/O at import time.
- Validate external input before using it.
- Keep input and generated-output ownership distinguishable.
- Use temporary locations for tests.
- Do not mutate source or user-owned data unless the contract explicitly allows
  it.
- Make retry, timeout, idempotency, and partial-failure behavior explicit when an
  external system is introduced.

## 5. Contracts and compatibility

Public APIs, persisted data, generated artifacts, configuration, and external
messages are contracts once consumers depend on them.

When changing a contract:

1. identify affected producers and consumers;
2. define validation and failure behavior;
3. preserve backward compatibility unless a breaking change is explicitly
   authorized;
4. update tests and documentation together; and
5. use an ADR when the format or compatibility policy has long-term impact.

Do not silently accept incompatible or partially understood data.

## 6. Determinism and reproducibility

Prefer deterministic behavior. If time, randomness, concurrency, or environment
state affects results, expose the dependency so tests can control it. Persist
enough metadata to reproduce a result when reproducibility is part of the
requirement.

Do not invent a seed, metadata, or artifact contract before the product requires
one; when introduced, document and test it as a public contract.

## 7. Configuration and dependencies

Introduce configuration only for behavior that must vary by environment or user
choice. Validate required values at the system boundary and keep ownership and
precedence explicit. Never use configuration as a substitute for a clear product
decision.

Before adding a dependency:

1. confirm that the standard library and current dependencies are insufficient;
2. assess maintenance, license, security, and runtime impact;
3. update `pyproject.toml` and `uv.lock` together; and
4. run the full repository validation suite.

An external platform, database, network service, or framework that shapes the
system normally requires an ADR.

## 8. Security and trust boundaries

- Never commit credentials or secrets.
- Treat external input and artifacts as untrusted until validated.
- Use parameterized interfaces instead of constructing commands or queries from
  untrusted text.
- Do not disable transport or certificate verification to make an integration
  work.
- Do not deserialize executable or unsafe formats from an untrusted source.
- Grant filesystem, network, and service permissions only at the narrowest
  boundary required by the feature.

Security-sensitive trust decisions require explicit review and normally an ADR.

## 9. Architecture decisions

Review `ARCHITECTURE.md` and `docs/decisions/` before making a durable change.
Create an ADR before broadly relying on a decision that establishes or changes:

- a public entry point or interface;
- top-level module responsibilities or dependency direction;
- a persisted format or compatibility policy;
- configuration ownership or precedence;
- an external system or long-running process;
- a security or trust boundary; or
- a foundational runtime dependency.

Never silently contradict an Accepted ADR. Replace one with a new ADR that marks
the previous decision as Superseded, then update `ARCHITECTURE.md` to describe
the implemented result.

## 10. Review checklist

- Does every new behavior trace to the requirement?
- Is each responsibility in the smallest coherent module?
- Are dependencies explicit, acyclic, and free of import-time work?
- Are I/O and external systems isolated at testable boundaries?
- Are public and persisted contracts validated and documented?
- Are security, compatibility, and failure behavior explicit?
- Is a long-lived decision recorded in an ADR where needed?
- Does `ARCHITECTURE.md` describe only what is actually implemented?
