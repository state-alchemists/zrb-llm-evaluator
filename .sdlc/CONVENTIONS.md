# SDLC Conventions

Single source of truth for paths, the EARS dialect, the ID/traceability scheme, and approval tiers. Every `sdlc-*` skill reads this file.

## Artifact paths (canonical)
| Artifact | Path |
|----------|------|
| Steering docs | `.sdlc/docs/` |
| ADRs | `.sdlc/docs/adr/` |
| Architecture | `.sdlc/docs/architecture.md` |
| Requirements | `.sdlc/requirements/` |
| Specs | `.sdlc/specs/<slug>/spec.md` |
| Test plans | `.sdlc/tests/<slug>/test-plan.md` |
| Reviews | `.sdlc/reviews/<slug>/report-{YYYY-MM-DDTHH-MM-SS}.md` |
| Rules | `.sdlc/rules.md` |
| Validator | `.sdlc/tools/sdlc-validate.py` |

**Legacy fallback**: projects created before the `.sdlc/` consolidation keep steering docs at `docs/`, ADRs at `docs/adr/`, requirements at `requirements/`, rules at `rules.md`. Skills read legacy locations if the canonical one is absent, but never write a parallel tree. Run `/sdlc-migrate` to consolidate.

## Feature slugs
A feature directory name is the slug of the feature: lowercase; spaces/underscores → `-`; drop characters outside `[a-z0-9-]`; collapse repeated `-`; trim leading/trailing `-`. Slugs are stable — never renumber or rename once code references `.sdlc/specs/<slug>/`.

## Canonical EARS dialect
| Pattern | Template |
|---------|----------|
| Ubiquitous | The `<system>` SHALL `<response>`. |
| Event-driven | WHEN `<trigger>`, the `<system>` SHALL `<response>`. |
| State-driven | WHILE `<state>`, the `<system>` SHALL `<response>`. |
| Optional feature | WHERE `<feature is included>`, the `<system>` SHALL `<response>`. |
| Unwanted behaviour | IF `<condition>`, THEN the `<system>` SHALL `<response>`. |
| Complex | Combine, e.g. WHILE `<state>`, WHEN `<trigger>`, the `<system>` SHALL `<response>`. |

This is canonical EARS (Mavin et al.). Deprecated dialect found in old specs migrates as: `ALWAYS SHALL` → ubiquitous (drop ALWAYS); `AS <c> THEN SHALL` → `IF <c>, THEN … SHALL`; `UNLESS <b> THEN SHALL <d>` → `IF NOT <b>, THEN … SHALL <d>`; old `WHERE <state>` (state-driven) → `WHILE <state>`.

## ID & traceability scheme
- Each `spec.md` declares `**Feature Key:** <KEY>` — an uppercase token `[A-Z][A-Z0-9_-]*`, globally unique across all features. Default suggestion: the uppercased slug.
- Requirement IDs are per-feature (`REQ-001`, `NFR-001`, `UT-001`, `IT-001`, `E2E-001`, `PBT-001`) and disambiguated globally by the key.
- Source header: `IMPLEMENTS: <KEY>:REQ-001, <KEY>:NFR-002`
- Test header: `COVERS: <KEY>:REQ-002, <KEY>:UT-005, <KEY>:IT-001`
- Inline tag: `@sdlc <KEY>:REQ-003, <KEY>:REQ-004`
- IDs are immutable: never renumber or recycle. A removed requirement keeps its ID with a `REMOVED ({date}) — {reason}` note.
- An NFR validated outside application code is listed once in the NFR table **and** repeated under "NFRs Validated Outside Code"; the validator treats the repeat as the same NFR (not a duplicate) and exempts it from `IMPLEMENTS:`/`COVERS:`.
- Validate with `python3 .sdlc/tools/sdlc-validate.py [--feature <slug>] [--strict]` — exit 0 clean, 1 warnings (with `--strict`), 2 errors.

## Approval tiers
- **Tier 1 — explicit per-item approval**: global / hard-to-reverse writes — `rules.md` rule modifications, ADR supersessions, entity-dictionary conflict resolutions, overwriting an existing spec, file moves.
- **Tier 2 — one batched approval**: routine first-time generation (steering docs together; spec + test plan together).
- **Tier 3 — no approval**: read-only analysis, validator runs, and review reports (the report is the deliverable, not a source mutation).
Anything other than an affirmative is a change request, at any tier.
