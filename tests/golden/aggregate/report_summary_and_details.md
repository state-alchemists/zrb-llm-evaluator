## Summary

| Model | Test Case | Trial | Status | Duration (s) | Score | Total Tokens | Input | Output | Cache | Tool Calls |
|-------|-----------|-------|--------|-------------|-------|--------------|-------|--------|-------|------------|
| alpha:a | case-a | 1 | 👍 EXCELLENT | **1.00** | **0.80** | **0** | 0 | 0 | 0 | **0** |
| alpha:a | case-a | 2 | ✅ PASS | 2.00 | **0.80** | **0** | 0 | 0 | 0 | **0** |
| alpha:a | case-b | 1 | ❌ FAIL | 0.50 | 0.80 | 0 | 0 | 0 | 0 | 0 |
| alpha:a | case-b | 2 | ⏱️ TIMEOUT | 30.00 | 0.80 | 0 | 0 | 0 | 0 | 0 |
| beta:b | case-a | 1 | ⚠️ ERROR | 0.10 | 0.80 | 0 | 0 | 0 | 0 | 0 |
| beta:b | case-a | 2 | ✅ PASS | 1.50 | **0.80** | **0** | 0 | 0 | 0 | **0** |
| beta:b | case-b | 1 | ✅ PASS | 3.00 | **0.80** | **0** | 0 | 0 | 0 | **0** |
| beta:b | case-b | 2 | 👍 EXCELLENT | **2.50** | **0.80** | **0** | 0 | 0 | 0 | **0** |
## Per-Trial Details

### alpha:a / case-a / Trial 1

- **Status**: 👍 EXCELLENT
- **Duration**: 1.00s
- **Exit code**: 0
- **History path**: /tmp/fake.log
- **Tokens**: total=0, input=0, output=0, cache=0
- **Validation score**: 0.8

### alpha:a / case-a / Trial 2

- **Status**: ✅ PASS
- **Duration**: 2.00s
- **Exit code**: 0
- **History path**: /tmp/fake.log
- **Tokens**: total=0, input=0, output=0, cache=0
- **Validation score**: 0.8

### alpha:a / case-b / Trial 1

- **Status**: ❌ FAIL
- **Duration**: 0.50s
- **Exit code**: 0
- **History path**: /tmp/fake.log
- **Tokens**: total=0, input=0, output=0, cache=0
- **Validation score**: 0.8

### alpha:a / case-b / Trial 2

- **Status**: ⏱️ TIMEOUT
- **Duration**: 30.00s
- **Exit code**: 0
- **History path**: /tmp/fake.log
- **Tokens**: total=0, input=0, output=0, cache=0
- **Validation score**: 0.8

### beta:b / case-a / Trial 1

- **Status**: ⚠️ ERROR
- **Duration**: 0.10s
- **Exit code**: 0
- **History path**: /tmp/fake.log
- **Tokens**: total=0, input=0, output=0, cache=0
- **Validation score**: 0.8

### beta:b / case-a / Trial 2

- **Status**: ✅ PASS
- **Duration**: 1.50s
- **Exit code**: 0
- **History path**: /tmp/fake.log
- **Tokens**: total=0, input=0, output=0, cache=0
- **Validation score**: 0.8

### beta:b / case-b / Trial 1

- **Status**: ✅ PASS
- **Duration**: 3.00s
- **Exit code**: 0
- **History path**: /tmp/fake.log
- **Tokens**: total=0, input=0, output=0, cache=0
- **Validation score**: 0.8

### beta:b / case-b / Trial 2

- **Status**: 👍 EXCELLENT
- **Duration**: 2.50s
- **Exit code**: 0
- **History path**: /tmp/fake.log
- **Tokens**: total=0, input=0, output=0, cache=0
- **Validation score**: 0.8

