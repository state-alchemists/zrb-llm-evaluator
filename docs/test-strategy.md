# zrb-llm-evaluator — Test Strategy

## Testing Levels
| Level | Scope | Tool | Target |
|-------|-------|------|--------|
| Unit | Runner logic, result models, report generator | pytest | >= 80% |
| Integration | Full experiment with mock test case | pytest | 1-2 smoke tests |

## CI Gates
| Gate | Trigger | Command | Blocking |
|------|---------|---------|----------|
| Lint | Pre-commit | ruff check | Yes |
| Type check | Pre-commit | mypy | Yes |
| Unit Tests | Every push | pytest | Yes |

## Environments
| Env | URL | Deploy | Data |
|-----|-----|--------|------|
| Local dev | — | Manual | Synthetic |

## Quality Goals
- **Unit coverage**: >= 80%
- **Integration**: 2 smoke tests (single model + single test case, parallel run)
- **Type safety**: mypy strict on all public APIs
