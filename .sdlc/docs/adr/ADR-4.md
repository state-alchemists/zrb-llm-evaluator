# ADR-4: Result Models with Pydantic v2

## Status
Accepted

## Context
Trial results, validation results, and experiment configs need structured, typed, serializable models. The existing zrb runner uses `@dataclass` with manual `asdict()` serialization. This works but lacks validation (e.g., nothing prevents `status="INVALID"`) and has no built-in schema enforcement.

## Decision
All domain models — `TrialResult`, `ValidationResult`, `ValidationCheck`, `ExperimentConfig`, `Report` — are defined as **Pydantic v2 BaseModel** subclasses. Serialization uses `.model_dump()`; deserialization uses `.model_validate()`.

## Consequences
### Positive
- Automatic validation on construction (bad status values are rejected at the boundary)
- Native JSON serialization/deserialization — no manual `asdict()` / `**item` round-trip
- Schema doubles as documentation (RULE-002 compliments this)

### Negative
- Pydantic adds ~15MB to the dependency tree
- Existing runner's JSON persistence uses `asdict()` — migration needed

## Implements Rules
- RULE-003 — Pydantic for Result Models
- RULE-002 — Type annotations (Pydantic models are fully typed by design)

## Verification
- All model classes in `src/zrb_llm_evaluator/models.py` inherit from `pydantic.BaseModel`
- No `@dataclass` used for domain entities
- `model_dump()` is the only serialization path

## References
- Pydantic v2 docs: https://docs.pydantic.dev/latest/
