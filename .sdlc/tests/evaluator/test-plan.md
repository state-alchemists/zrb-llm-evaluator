# Test Plan: evaluator

> Generated from specs at `specs/evaluator/requirements.md` and `specs/evaluator/design.md`.
> Test naming convention: `test_<function>_<condition>` (pytest, Python >=3.11, async via `pytest-asyncio`).

## Existing Test Suite

The evaluator currently has **95 tests** across 12 test files in `tests/experiment-runner/`. This plan documents the existing mapping from REQ-* to tests, and flags remaining gaps.

## Unit Tests

| ID | Req | Test Name | File | Input | Expected |
|----|-----|-----------|------|-------|----------|
| UT-001 | REQ-001 | `test_session_name_generates_unique_per_trial` | `test_session.py` | model, case, trial index | 3 unique names containing model/case/trial |
| UT-001 | REQ-001 | `test_session_name_different_models` | `test_session.py` | two different models | different session names |
| UT-001 | REQ-001 | `test_session_name_is_filesystem_safe` | `test_session.py` | model with colon | name with no colons, safe chars only |
| UT-002 | REQ-002 | `test_semaphore_limits_concurrent_trials` | `test_semaphore.py` | semaphore(4), 8 workers | max running ≤ 4 |
| UT-012 | REQ-010 | `test_parallelism_1_sequential` | `test_semaphore.py` | semaphore(1), 3 workers | sequential execution |
| UT-003 | REQ-003 | `test_results_written_after_each_trial` | `test_runner.py` | 3 sequential `ResumeManager.append()` | results.json has N entries after N appends |
| UT-020 | REQ-003 | `test_results_json_atomic_write` | `test_runner.py` | 1 `ResumeManager.append()` | valid JSON with 1 entry |
| UT-052 | REQ-003, REQ-017 | `test_results_json_concurrent_append` | `test_runner.py` | 10 concurrent appends via `asyncio.gather` | valid JSON with 10 entries |
| UT-004 | REQ-004 | `test_iterates_all_combinations` | `test_runner.py` | 2 models × 2 cases × 2 trials | 8 cells, all combos present |
| UT-005 | REQ-005 | `test_timeout_kills_subprocess_and_records` | `test_runner.py` | timeout=1s, `asyncio.TimeoutError` | status=TIMEOUT, log_path non-empty |
| UT-043 | REQ-005 | `test_timeout_kills_whole_process_group` | `test_runner.py` | mock subprocess with pid=12345 | `os.killpg(12345, SIGKILL)`, `start_new_session=True` |
| UT-006 | REQ-006 | `test_resume_skips_terminal_cells` | `test_resume.py` | 3 terminal results in results.json | `is_completed()` true for all 3 |
| UT-006 | REQ-006 | `test_append_adds_result` | `test_resume.py` | 1 append | result visible, file written |
| UT-007 | REQ-007 | `test_nonzero_exit_records_error` | `test_runner.py` | exit_code=1 | status=ERROR |
| UT-008 | REQ-007 | `test_verification_marker_overrides_exit` | `test_runner.py` | exit_code=1 + `VERIFICATION_RESULT: PASS` | status=PASS |
| UT-008 | REQ-007 | `test_extract_verification_marker_found` | `test_runner.py` | stdout with PASS | returns "PASS" |
| UT-008 | REQ-007 | `test_extract_verification_marker_excellent` | `test_runner.py` | stdout with EXCELLENT | returns "EXCELLENT" |
| UT-008 | REQ-007 | `test_extract_verification_marker_not_found` | `test_runner.py` | stdout without marker | returns None |
| UT-008 | REQ-007 | `test_extract_verification_marker_invalid` | `test_runner.py` | stdout with UNKNOWN | returns None |
| UT-009 | REQ-008 | `test_timeout_result_references_log_file` | `test_runner.py` | timeout scenario | log_path ends with `.json`, contains "history" |
| UT-010 | REQ-009 | `test_validator_invoked_on_completion` | `test_runner.py` | clean trial exit | validator called 1 time |
| UT-011 | REQ-009 | `test_validator_receives_log_content` | `test_runner.py` | echo subprocess outputting "Hello" | captured_log contains "Hello" |
| UT-013 | REQ-011 | `test_validator_exception_records_error` | `test_runner.py` | validator raises ValueError | status=ERROR, detail="bad check" |
| UT-014 | REQ-014 | `test_cli_name_custom_binary` | `test_runner.py` | `cli_name="my-zrb"` | subprocess invoked as `my-zrb` |
| UT-016 | REQ-014 | `test_missing_required_args_exits` | `test_cli.py` | no args | non-zero exit |
| UT-016 | REQ-014 | `test_missing_models` | `test_cli.py` | missing `--models` | non-zero exit |
| UT-049 | REQ-014 | `test_cli_name_empty_rejected` | `test_models.py` | `cli_name=""` | `ValidationError` |
| UT-017 | REQ-015 | `test_model_format_provider_colon_name` | `test_models.py` | `"openai:gpt-4o"` | accepted |
| UT-018 | REQ-015 | `test_model_format_rejects_bare_name` | `test_models.py` | `"gpt-4o"` | `ValidationError` |
| UT-015 | REQ-013 | `test_missing_validator_rejected` | `test_validator.py` | directory without validator.py | `ValueError` |
| UT-015 | REQ-013 | `test_bad_validator_module_rejected` | `test_validator.py` | validator module without `validator` attr | `ValueError` |
| UT-015 | REQ-013 | `test_missing_instruction_rejected` | `test_validator.py` | directory without instruction.txt | `ValueError` |
| UT-015 | REQ-013 | `test_valid_case_loads_successfully` | `test_validator.py` | complete test case directory | valid TestCase |
| UT-015 | REQ-013 | `test_load_test_cases_batch_rejects` | `test_validator.py` | 1 valid + 1 invalid directory | `ValueError` |
| UT-019 | REQ-016 | `test_env_var_set_before_invocation` | `test_runner.py` | default prefix "ZRB" | `ZRB_LLM_HISTORY_DIR` and `ZRB_LLM_JOURNAL_DIR` set |
| UT-046 | REQ-016 | `test_journal_env_var_set` | `test_runner.py` | default prefix | journal_dir ends in `/notes`, sibling of history_dir |
| UT-047 | REQ-016 | `test_llm_notes_isolated_per_trial` | `test_runner.py` | 2 trials | different journal dirs, contain trial-1/trial-2 |
| UT-048 | REQ-016 | `test_env_prefix_custom` | `test_runner.py` | `env_prefix="MYAPP"` | `MYAPP_LLM_HISTORY_DIR` and `MYAPP_LLM_JOURNAL_DIR` set |
| UT-050 | REQ-017 | `test_report_command_corrupt_json` | `test_cli.py` | corrupt experiment.json | non-zero exit |
| UT-051 | REQ-003, REQ-017 | `test_load_or_init_experiment_corrupt_json` | `test_runner.py` | corrupt experiment.json | fresh experiment created (no crash) |
| UT-022 | REQ-019 | `test_cost_summary_parsed` | `test_runner.py` | full cost line | total=150, input=100, output=50, cache=0 |
| UT-044 | REQ-019 | `test_cost_summary_parsed_real_zrb_format` | `test_runner.py` | real zrb format + non-zero A/V | input != audio_input, output != audio_output |
| UT-045 | REQ-019 | `test_cost_summary_uses_last_line_when_multiple` | `test_runner.py` | 2 cost lines | only last line values, not sum |
| UT-023 | REQ-019 | `test_cost_summary_missing_defaults_zero` | `test_runner.py` | no cost line | all zero |
| UT-026 | REQ-019 | `test_missing_file_returns_empty` | `test_tool_calls.py` | missing history file | empty list, count 0 |
| UT-026 | REQ-019 | `test_malformed_json_returns_empty` | `test_tool_calls.py` | corrupt JSON | empty list |
| UT-026 | REQ-019 | `test_list_with_tool_name` | `test_tool_calls.py` | bare-list entries | tool names extracted |
| UT-026 | REQ-019 | `test_nested_tool_call` | `test_tool_calls.py` | tool_call.name entries | tool names extracted |
| UT-026 | REQ-019 | `test_history_wrapped_in_dict` | `test_tool_calls.py` | `{"history": [...]}` | tool names extracted |
| UT-026 | REQ-019 | `test_unexpected_shape_returns_empty` | `test_tool_calls.py` | scalar JSON | empty list |
| UT-026 | REQ-019 | `test_entries_without_tool_name_skipped` | `test_tool_calls.py` | user/assistant entries | empty list |
| UT-026 | REQ-019 | `test_role_tool_with_name` | `test_tool_calls.py` | `role=tool` with name | tool names extracted |
| UT-026 | REQ-019 | `test_pydantic_ai_parts_shape` | `test_tool_calls.py` | pydantic-ai parts[] shape | multiple parallel tool calls extracted |
| UT-021 | REQ-018 | `test_output_dir_structure` | `test_runner.py` | 2 models × 2 trials | `{out}/{model_safe}/{case}/trial-{N}/` |
| UT-024 | NFR-001 | `test_overhead_without_llm` | `test_runner.py` | mock fast subprocess | elapsed < 2s |
| UT-027 | REQ-020 | `test_subprocess_cwd_is_nested_workdir` | `test_workdir_isolation.py` | trial execution | cwd ends in `/workdir`, not cell_dir |
| UT-028 | REQ-021 | `test_evaluation_artifacts_outside_workdir` | `test_workdir_isolation.py` | trial execution | stdout.log + history/ in cell_dir, not workdir/ |
| UT-029 | REQ-022 | `test_empty_workdir_created_when_no_source` | `test_workdir_isolation.py` | no test-case workdir/ | nested workdir exists but empty |
| UT-030 | REQ-023 | `test_staged_files_land_in_nested_workdir` | `test_workdir_isolation.py` | test-case with workdir files | files in workdir/, not cell_dir |
| UT-031 | REQ-024 | `test_metadata_files_never_staged` | `test_workdir_isolation.py` | test-case with workdir/ | validator.py and instruction.txt absent from workdir |
| UT-032 | REQ-025 | `test_markdown_report_rows_sorted_by_model_case_trial` | `test_report_rendering.py` | scrambled trials | rows sorted (model, case, trial) ASC |
| UT-033 | REQ-026 | `test_markdown_report_excludes_failures_from_bold_scope` | `test_report_rendering.py` | FAIL + PASS trials | PASS bolded, FAIL not bolded |
| UT-034 | REQ-026 | `test_markdown_report_bold_scope_is_per_test_case` | `test_report_rendering.py` | 2 cases, 1 trial each | each case's best bolded independently |
| UT-035 | REQ-027 | `test_markdown_report_contains_no_html` | `test_report_rendering.py` | multi-status experiment | no HTML tags |
| UT-036 | REQ-028 | `test_markdown_report_bolds_best_duration` | `test_report_rendering.py` | 3 PASS trials, durations 1/2/3 | min duration bolded |
| UT-037 | REQ-028 | `test_markdown_report_bolds_best_score` | `test_report_rendering.py` | 3 PASS trials, scores 0.5/0.8/1.0 | max score bolded |
| UT-038 | REQ-028 | `test_markdown_report_bolds_best_total_tokens` | `test_report_rendering.py` | 3 PASS trials, tokens 100/200/300 | min tokens bolded |
| UT-039 | REQ-028 | `test_markdown_report_bolds_best_tool_call_count` | `test_report_rendering.py` | 3 PASS trials, tool calls 1/3/5 | min tool calls bolded |
| UT-040 | REQ-028 | `test_markdown_report_bolds_all_tied_cells` | `test_report_rendering.py` | 2 PASS trials, duration 1.0 each | both bolded |
| UT-041 | REQ-029 | `test_markdown_report_status_icons_mapped` | `test_report_rendering.py` | each status (EXCELLENT..ERROR) | correct icon prefix |
| UT-042 | REQ-031 | `test_markdown_report_deterministic_byte_identical` | `test_report_rendering.py` | same experiment, 2 renders | byte-identical output |
| UT-025 | RULE-005 | `test_no_zrb_import_in_runner` | `test_no_zrb_import.py` | import all runner modules | no zrb internal modules imported |
| — | REQ-010 | `test_min_trials_enforced` | `test_models.py` | trials=0 | `ValidationError` |
| — | REQ-010 | `test_min_parallelism_enforced` | `test_models.py` | parallelism=0 | `ValidationError` |
| — | REQ-010 | `test_min_timeout_enforced` | `test_models.py` | timeout=10 | `ValidationError` |
| — | REQ-017 | `test_token_fields_default_zero` | `test_models.py` | TrialResult without tokens | all token fields = 0 |
| — | REQ-003 | `test_round_trip_serialization` | `test_models.py` | TrialResult → dump → validate | restored matches original |
| — | REQ-009 | `test_with_verification_result` | `test_models.py` | TrialResult with ValidationResult | score=0.95 |
| UT-003 | REQ-003 | `test_results_json_atomic_write` | `test_runner.py` | 1 append | valid JSON with 1 entry |
| — | REQ-017 | `test_results_json_atomic_write` | `test_runner.py` | 1 append | data[0]["model"] == "openai:gpt-4o" |

## Integration Tests

| ID | Scope | Test Name | Setup | Assertion |
|----|-------|-----------|-------|-----------|
| IT-001 | Full pipeline | `test_run_command_full_pipeline` | 2 cases × 2 models × 2 trials, `cli_name="echo"` | 8 results, all terminal, results.json + experiment.json valid |
| IT-002 | Resume mid-experiment | `test_resume_mid_experiment` | 2 models × 1 case × 2 trials, run twice | 4 results total, id + started_at preserved |
| IT-003 | Parallel execution | `test_parallel_execution` | 4 models × 1 case × 2 trials, parallelism=4 | 8 results, elapsed < 5s |
| IT-004 | Custom validator | `test_custom_validator_executed` | 1 trial, validator returning EXCELLENT 0.95 | verification_result.status="EXCELLENT", score=0.95 |
| IT-005 | Workdir isolation | `test_isolation_end_to_end` | test-case with workdir/data.txt | LLM sees only data.txt; artifacts are siblings |
| IT-006 | Report pipeline | `test_report_md_full_pipeline_sort_bold_icons` | 8 trials with mixed statuses | sorted, bolded, icons, no HTML |

## End-to-End Tests

| ID | Story | Scenario | Steps | Expected |
|----|-------|----------|-------|----------|
| E2E-004 | User-scannable report | `test_user_scannable_report_after_run` | Build experiment with 8 trials across 5 statuses, render report | All 5 icons present, rows sorted, bold markers, no HTML |

*Note: Full E2E tests requiring actual `zrb chat` subprocess are not included — the runner always mocks the subprocess. The `cli_name="echo"` pattern in IT-001 provides the closest approximation.*

## Property-Based Tests

**N/A — no property-testing framework configured** (no `hypothesis`, `fast-check`, `proptest`, or `gopter` declared in `docs/tech.md` or `docs/test-strategy.md`).

If a property-testing framework is added later, recommend PBTs for:
- **Cost line parsing**: given any valid 💸 cost line, `parse_cost_summary` returns non-negative integers
- **Round-trip**: any `TrialResult` → `model_dump(mode="json")` → `model_validate()` → identical
- **Cell plan**: cartesian product size = len(models) × len(cases) × trials

## NFRs Validated Outside Code

| NFR | Validation Mechanism | Status |
|-----|---------------------|--------|
| NFR-001 (<2s overhead) | UT-024 (benchmark-like test) | ✅ Covered |
| NFR-002 (100+ cells) | IT NFR-002 (stress test with `@pytest.mark.slow`) | ✅ Covered |
| NFR-003 (atomic writes) | UT-020, UT-052 (tempfile+os.replace pattern) | ✅ Covered |
| NFR-004 (no HTML) | UT-035 (report must lack HTML tags) | ✅ Covered |

## Design Property Coverage

| Property | Covered By | Notes |
|----------|------------|-------|
| Round-Trip | UT-022 (model dump/validate), IT-001, IT-002 | Pydantic v2 `model_dump(mode="json")` + `model_validate()` |
| Uniqueness | UT-001 (session names) | Partially enforced — UUIDs on TrialResult/Experiment but no dedup |
| Atomicity | UT-020, UT-052, UT-051 (tempfile + os.replace) | 3 write paths tested; subprocess level not enforced |
| Validation | UT-007, UT-013, UT-015, UT-016, UT-017, UT-018, UT-049 | Multi-layer: CLI, Pydantic, loader, runtime |
| Idempotency | UT-006, IT-002 (resume skips completed) | Resume path enforced; trial-level not enforced (safe) |

## Test Data Strategy

- **Fixtures**: Shared fixtures in `tests/experiment-runner/conftest.py`:
  - `sample_experiment_config` — minimal valid config
  - `sample_validation_result` — PASS with score 0.85, 2 checks
  - `sample_trial_result` — PASS with duration 1.23
  - `sample_test_case_dir` — directory with instruction.txt + validator.py
  - `sample_test_case` — loaded TestCase from sample directory
  - `sample_results_json` — pre-built results.json for resume tests
  - `mock_subprocess_factory` — async fixture for MockProcess instances
- **Synthetic data**: Created ad-hoc per test using `tmp_path`, pydantic model constructors, and string builders.
- **Cleanup**: `tmp_path` fixture (pytest built-in) scoped per test function — each test gets an isolated temp directory. No shared state between tests.
- **Async tests**: Use `@pytest.mark.asyncio` and `pytest_asyncio` fixtures.

## Coverage Gaps

| Area | Gap | Recommendation |
|------|-----|---------------|
| Parallel execution | UT-002/UT-012 test asyncio.Semaphore in isolation; IT-003 tests full pipeline with parallelism=4 | Add a test that verifies actual concurrency with real TrialRunner + mock subprocess to confirm semaphore limits work end-to-end under load |
| `report` CLI happy path | No test invokes `report` with a valid experiment.json and verifies markdown output | Add a test that writes a valid experiment.json, runs `report` CLI, checks report.md exists |
| `list` CLI subcommand | No tests for the `list` command at all | Add UT for `list` with valid results.json, and for missing results.json (non-zero exit) |
| Session name with special chars | No test for session names with characters that are both filesystem-safe and valid | Already partially covered by `test_session_name_is_filesystem_safe` |
| Config `test_case_dirs` path resolution | No test that relative paths are resolved to absolute before trial execution | Add a unit test for the path resolution in `cli.py` |

---
*Generated at 2026-05-27. Scope: evaluator module. Sources: specs/evaluator/requirements.md, specs/evaluator/design.md, tests/experiment-runner/.*
