# ADR-5: Protocol-Based Validator Contract

## Status
Accepted

## Context
Users define their own test case validators. The framework must accept any validator as long as it exposes the correct interface. The existing zrb runner has no validator contract — verification is a `verify.sh` or `verify.py` script that communicates results via stdout parsing (`VERIFICATION_RESULT:` markers).

## Decision
Define the validator contract as a **typing.Protocol** with a single method:

```python
class ValidatorProtocol(Protocol):
    def validate(self, output_dir: Path, log_content: str) -> ValidationResult: ...
```

User-defined validators implement this protocol. The framework discovers validators by importing the module referenced in the test case directory (e.g., `cases/my-case/validator.py`), verifies it conforms to the protocol, and calls `validate()`.

## Consequences
### Positive
- Structural subtyping (Protocol) means users don't need to inherit from a framework base class
- Clear, type-checked contract — mypy ensures the validator matches
- Replaces fragile `VERIFICATION_RESULT:` string parsing with typed return values

### Negative
- Breaking change from the existing script-based verifier pattern
- Users must write Python code, not shell scripts, for validation

## Implements Rules
- RULE-004 — Protocol/ABC for Pluggable Validators

## Verification
- `ValidatorProtocol` is defined in `src/zrb_llm_evaluator/protocols.py`
- The runner rejects a test case whose validator module doesn't conform at import time
- Unit test: a minimal validator that returns `ValidationResult(status=EXCELLENT, score=1.0, details=[])`

## References
- Python typing.Protocol docs
