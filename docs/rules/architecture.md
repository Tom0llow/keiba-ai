# Architecture Rules

`ARCHITECTURE.md` is the authoritative description of the system that currently
exists. This file defines how that architecture may evolve.

## 1. Preserve the bootstrap boundary

The current product-code boundary is intentionally small:

```text
src/keiba_ai/   # importable package skeleton
tests/          # automated tests
```

There is no product entry point, CLI, configuration layout, storage contract,
external integration, or domain-module decomposition yet. Do not recover or
infer one from an earlier prototype, ignored file, or stale document.

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

Keep product code under `src/keiba_ai/` unless an explicit requirement or ADR
establishes another top-level boundary. Each module should own one coherent
responsibility and have a name that describes that responsibility.

- Keep imports acyclic and free of runtime work.
- Higher-level orchestration may depend on lower-level calculations; lower-level
  code must not import an entry point merely to share behavior.
- Pass important dependencies explicitly instead of constructing hidden global
  clients deep in the package.
- Do not create an undifferentiated `utils` module for unrelated behavior.
- Keep public interfaces as small as the current callers require.

When an entry point is introduced, keep it responsible for boundary concerns and
delegation rather than product calculations. Its exact form must be selected by
the requirement, not by this bootstrap rule.

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
