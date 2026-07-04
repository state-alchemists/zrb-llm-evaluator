# Test Plan: experiment-runner

**Convention**: pytest — `test_<component>_<condition>_<expected>()`

## Unit Tests

| ID | Req | Test Name | Input | Expected |
|----|-----|-----------|-------|----------|
| UT-001 | REQ-001 | test_session_name_generates_unique_per_trial | model=m1, case=c1, trial=1,2,3 | Three unique session strings, each containing model/case/trial |
| UT-002 | REQ-002 | test_semaphore_limits_concurrent_trials | 8 tasks, parallelism=4 | At most 4 tasks running simultaneously at any point |
| UT-003 | REQ-003 | test_results_written_after_each_trial | 3 trials, results.json path | After each trial completes, results.json has exactly N entries |
| UT-004 | REQ-004 | test_iterates_all_combinations | 2 models × 2 cases × 2 trials | 8 cells generated in the cell plan |
| UT-005 | REQ-005 | test_timeout_kills_subprocess_and_records | mock subprocess that sleeps 60s, timeout=1s | TrialResult.status == "TIMEOUT" |
| UT-006 | REQ-006 | test_resume_skips_terminal_cells | results.json with 2 terminal + 1 pending | Only 1 cell executes; 2 are skipped |
| UT-007 | REQ-007 | test_nonzero_exit_records_error | mock subprocess returning exit_code=1 | TrialResult.status == "ERROR" |
| UT-008 | REQ-007 | test_verification_marker_overrides_exit | mock subprocess returning exit=1 with VERIFICATION_RESULT: PASS | TrialResult.status == "PASS" |
| UT-009 | REQ-008 | test_timeout_result_references_log_file | timed-out trial | TrialResult.log_path is a non-empty path to an existing file |
| UT-010 | REQ-009 | test_validator_invoked_on_completion | mock subprocess returning exit=0, valid validator | validator.validate() called once with output_dir and log_content |
| UT-011 | REQ-009 | test_validator_receives_log_content | mock subprocess writing known output | log_content argument contains the expected output text |
| UT-012 | REQ-010 | test_parallelism_1_sequential | parallelism=1, 3 trials | Trials execute one after another (start times are monotonic with gaps) |
| UT-013 | REQ-011 | test_validator_exception_records_error | validator that raises ValueError("bad check") | TrialResult.status == "ERROR", details contain "bad check" |
| UT-014 | REQ-012 | test_cli_name_custom_binary | --cli-name=my-zrb | Subprocess invoked as `my-zrb chat ...` instead of `zrb chat ...` |
| UT-015 | REQ-013 | test_missing_validator_rejected | test case dir without validator module | Runner exits with INVALID_CASE before any trial |
| UT-016 | REQ-014 | test_missing_required_args_exits | run command with no args | Non-zero exit, usage printed to stderr |
| UT-017 | REQ-015 | test_model_format_provider_colon_name | "openai:gpt-4o" | Accepted and stored as-is |
| UT-018 | REQ-015 | test_model_format_rejects_bare_name | "gpt-4o" | Rejected with validation error |
| UT-019 | REQ-016 | test_env_var_set_before_invocation | trial runner | ZRB_LLM_HISTORY_DIR and ZRB_LLM_JOURNAL_DIR both set to per-cell sibling dirs; --session passed to subprocess <!-- updated 2026-05-24 (quickfix-2026-05-24T23-45-24) --> |
| UT-020 | REQ-017 | test_results_json_atomic_write | 1 trial | results.json is valid JSON with exactly 1 TrialResult entry |
| UT-021 | REQ-018 | test_output_dir_structure | 2 models × 1 case × 2 trials | Dirs exist: {out}/model1/case1/trial-1/, {out}/model1/case1/trial-2/ etc. |
| UT-022 | REQ-019 | test_cost_summary_parsed | stdout containing real zrb line `💸 (Requests: 1 \| Tool Calls: 0 \| Total: 150) Input: 100 \| Audio Input: 0 \| Output: 50 \| Audio Output: 0 \| Cache Read: 0 \| Cache Write: 0 \| Details: {}` | TrialResult.total_tokens=150, input_tokens=100, output_tokens=50, cache_read_tokens=0 <!-- updated 2026-05-24 (quickfix-2026-05-24T23-45-24) --> |
| UT-023 | REQ-019 | test_cost_summary_missing_defaults_zero | stdout with no cost line | All token fields default to 0 |
| UT-024 | NFR-001 | test_overhead_without_llm | mock subprocess returning instantly | Wall-clock overhead < 2s |
| UT-025 | RULE-005 | test_no_zrb_import_in_runner | runner module | No `import zrb` or `from zrb` outside test fixtures |
| UT-026 | REQ-019 | test_tool_calls_extracted_from_history | zrb history JSON with tool-use entries | tool_calls list and tool_call_count populated; defensive on parse errors |
| UT-027 | REQ-020 | test_subprocess_cwd_is_nested_workdir | trial run with mock subprocess | `asyncio.create_subprocess_exec` called with `cwd` ending in `/workdir` (not the cell dir itself) |
| UT-028 | REQ-021 | test_evaluation_artifacts_outside_workdir | completed trial cell | `cell_dir/stdout.log` exists; `cell_dir/history/` exists; `cell_dir/workdir/stdout.log` does NOT exist; `cell_dir/workdir/history/` does NOT exist |
| UT-029 | REQ-022 | test_empty_workdir_created_when_no_source | test case with no `workdir/` to stage | `cell_dir/workdir/` exists and is an empty directory before subprocess launch |
| UT-030 | REQ-023 | test_staged_files_land_in_nested_workdir | test case with workdir containing `seed.txt`, `data/notes.md` | `cell_dir/workdir/seed.txt` and `cell_dir/workdir/data/notes.md` exist; `cell_dir/seed.txt` does NOT exist |
| UT-031 | REQ-024 | test_metadata_files_never_staged | test case directory containing `validator.py`, `instruction.txt`, and a `workdir/` with `foo.txt` | `cell_dir/workdir/foo.txt` exists; `cell_dir/workdir/validator.py` does NOT exist; `cell_dir/workdir/instruction.txt` does NOT exist |
| UT-032 | REQ-025 | test_markdown_report_rows_sorted_by_model_case_trial | Unsorted TrialResults across 2 models × 2 cases × 2 trials | Rows in report.md appear ordered `(model ASC, case ASC, trial_index ASC)` |
| UT-033 | REQ-026 | test_markdown_report_excludes_failures_from_bold_scope | One test case: a FAIL trial with duration=0.5s, a PASS trial with duration=1.0s (parametrized over FAIL/TIMEOUT/ERROR) | The 1.0s PASS cell is bold; the FAIL/TIMEOUT/ERROR rows have no bold cells |
| UT-034 | REQ-026 | test_markdown_report_bold_scope_is_per_test_case | Case A best PASS duration=1.0s; Case B best PASS duration=2.0s | Case B's 2.0s cell is bolded (best within its own test case) despite being slower than Case A's best |
| UT-035 | REQ-027 | test_markdown_report_contains_no_html | Any rendered report | Rendered text contains no `<b>`, `<span>`, or other HTML tags |
| UT-036 | REQ-028 | test_markdown_report_bolds_best_duration | 3 PASS trials with durations 1.0, 2.0, 3.0 in one case | Only the 1.0s cell wrapped in `**…**` |
| UT-037 | REQ-028 | test_markdown_report_bolds_best_score | 3 PASS trials with scores 0.5, 0.8, 1.0 in one case | Only the 1.0 score cell bold |
| UT-038 | REQ-028 | test_markdown_report_bolds_best_total_tokens | 3 PASS trials with total_tokens 100, 200, 300 in one case | Only the 100 cell bold |
| UT-039 | REQ-028 | test_markdown_report_bolds_best_tool_call_count | 3 PASS trials with tool_call_count 1, 3, 5 in one case | Only the 1 cell bold |
| UT-040 | REQ-028 | test_markdown_report_bolds_all_tied_cells | 2 PASS trials sharing min duration=1.0s | Both 1.0s cells bold |
| UT-041 | REQ-029 | test_markdown_report_status_icons_mapped | Parametrized: each of EXCELLENT/PASS/FAIL/TIMEOUT/ERROR | Status text begins with the icon: 👍/✅/❌/⏱️/⚠️ followed by the status name |
| UT-042 | REQ-025 | test_markdown_report_deterministic_byte_identical | Same `results.json` rendered twice | Both renderings produce byte-identical bytes |
| UT-043 | REQ-005 | test_timeout_kills_whole_process_group | mock subprocess that hits timeout; `os.getpgid`/`os.killpg` patched | `create_subprocess_exec` invoked with `start_new_session=True`; `os.killpg` called once with leader's pgid and `SIGKILL`; `TrialResult.status == "TIMEOUT"` <!-- added 2026-05-21 (quickfix-2026-05-21T15-03-46) --> |
| UT-044 | REQ-019 | test_cost_summary_parsed_real_zrb_format | stdout containing real `💸 (… Total: 1500) Input: 1000 \| Audio Input: 0 \| Output: 500 \| Audio Output: 0 \| Cache Read: 200 …` and a second case with non-zero `Audio Input`/`Audio Output` | total=1500, input=1000 (not 999), output=500 (not 888), cache_read=200 <!-- added 2026-05-24 (quickfix-2026-05-24T23-45-24) --> |
| UT-045 | REQ-019 | test_cost_summary_uses_last_line_when_multiple | stdout with two 💸 lines (Total: 100 then Total: 250) | total=250, input=150, output=100, cache_read=30; explicitly NOT the sum (350) <!-- added 2026-05-24 (quickfix-2026-05-24T23-45-24) --> |
| UT-046 | REQ-016 | test_journal_env_var_set | trial runner with mocked subprocess | env contains `ZRB_LLM_JOURNAL_DIR`; path ends with `/llm-notes` and shares the same parent as `ZRB_LLM_HISTORY_DIR` (sibling inside cell_dir) <!-- added 2026-05-24 (quickfix-2026-05-24T23-45-24) --> |
| UT-047 | REQ-016 | test_llm_notes_isolated_per_trial | two consecutive trials with trial_index=1 and trial_index=2 | the two captured `ZRB_LLM_JOURNAL_DIR` values differ and contain `trial-1` and `trial-2` respectively <!-- added 2026-05-24 (quickfix-2026-05-24T23-45-24) --> |
| UT-048 | REQ-016 | test_env_prefix_custom_sets_correct_env_vars | runner with `env_prefix="MYAPP"` | `MYAPP_LLM_HISTORY_DIR` and `MYAPP_LLM_JOURNAL_DIR` set; `ZRB_*` vars absent <!-- added 2026-06-24 (quickfix-2026-06-24T23-43-58) --> |
| UT-049 | REQ-015 | test_model_format_rejects_empty_cli_name | `ExperimentConfig(cli_name="")` | Pydantic validation error raised <!-- added 2026-06-24 (quickfix-2026-06-24T23-43-58) --> |
| UT-050 | REQ-033 | test_report_command_corrupt_experiment_json_exits_nonzero | corrupt `experiment.json` in `--dir` | `report` subcommand exits non-zero <!-- added 2026-06-24 (quickfix-2026-06-24T23-43-58) --> |
| UT-051 | REQ-030 | test_corrupt_experiment_json_creates_fresh_experiment | corrupt `experiment.json` on resume | `_load_or_init_experiment` returns a fresh `Experiment` with no crash <!-- added 2026-06-24 (quickfix-2026-06-24T23-43-58) --> |
| UT-052 | REQ-003 | test_concurrent_result_appends_produce_valid_json | concurrent appends to `results.json` | `results.json` is valid JSON with all entries and no corruption <!-- added 2026-06-24 (quickfix-2026-06-24T23-43-58) --> |
| UT-053 | REQ-033 | test_report_command_valid_experiment_json_exits_zero | valid `experiment.json` in `--dir` | `report` subcommand exits 0 and writes `report.md` <!-- added 2026-06-24 (quickfix-2026-06-24T23-43-58) --> |
| UT-054 | REQ-032 | test_list_command_valid_results_json_exits_zero | valid `results.json` in `--dir` | `list` subcommand exits 0 and prints model names <!-- added 2026-06-24 (quickfix-2026-06-24T23-43-58) --> |
| UT-055 | REQ-032 | test_list_command_no_results_json_exits_nonzero | no `results.json` in `--dir` | `list` subcommand exits non-zero <!-- added 2026-06-24 (quickfix-2026-06-24T23-43-58) --> |
| UT-056 | REQ-004 | test_cell_plan_3models_1case_2trials_equals_6_cells | 3 models × 1 case × 2 trials | 6 cells generated in the plan <!-- added 2026-06-24 (quickfix-2026-06-24T23-43-58) --> |
| UT-057 | REQ-013 | test_relative_test_case_dirs_resolved_to_absolute | `--test-cases ./cases/` (relative) | paths resolved to absolute before `load_test_cases` is called <!-- added 2026-06-24 (quickfix-2026-06-24T23-43-58) --> |
| UT-058 | REQ-034 | test_load_test_cases_aggregates_all_errors | two invalid test case dirs | single `ValueError` containing both error messages <!-- added 2026-06-24 (quickfix-2026-06-24T23-43-58) --> |
| UT-059 | REQ-031 | test_cell_dir_wiped_on_retry | cell_dir pre-created with stale-artifact.txt | stale file absent after run; cell_dir recreated <!-- added 2026-06-25 (quickfix-2026-06-24T23-43-58) --> |
| UT-060 | REQ-035 | test_adapter_selected_by_cli_template | `cli_template="zrb"` | `TrialRunner` resolves and uses a `ZrbCliAdapter` instance for `build_argv`/`build_env`/`parse_usage`/`extract_tool_calls` <!-- added 2026-07-03 (spec/cli-templates) --> |
| UT-061 | REQ-036 | test_default_cli_template_is_zrb | `ExperimentConfig()` with no `cli_template` given | `config.cli_template == "zrb"`; resulting argv/env/parsed usage identical to the pre-feature runner (same assertions as UT-014/UT-019/UT-022) <!-- added 2026-07-03 (spec/cli-templates) --> |
| UT-062 | REQ-037 | test_custom_adapter_loaded_from_dotted_path | `cli_template="tests.fixtures.custom_adapter.FakeAdapter"` | Runner imports and instantiates `FakeAdapter`; it is used to build the trial's argv/env and parse its output <!-- added 2026-07-03 (spec/cli-templates) --> |
| UT-063 | REQ-038 | test_unknown_cli_template_rejected | `cli_template="not-a-real-template"` | Runner exits non-zero with `INVALID_TEMPLATE` before any trial begins <!-- added 2026-07-03 (spec/cli-templates) --> |
| UT-064 | REQ-038 | test_dotted_path_not_implementing_protocol_rejected | `cli_template` resolves to a class missing one or more `CliAdapter` methods | Runner exits non-zero with `INVALID_TEMPLATE` before any trial begins <!-- added 2026-07-03 (spec/cli-templates) --> |
| UT-065 | REQ-039 | test_token_fields_from_adapter_parse_usage | Fake adapter whose `parse_usage` returns `UsageSummary(total_tokens=42, input_tokens=30, output_tokens=12, cache_read_tokens=0)` | `TrialResult.total_tokens==42`, `input_tokens==30`, `output_tokens==12`, `cache_read_tokens==0` <!-- added 2026-07-03 (spec/cli-templates) --> |
| UT-066 | REQ-039 | test_tool_calls_from_adapter_extract_tool_calls | Fake adapter whose `extract_tool_calls` returns `(["read", "write"], 2)` | `TrialResult.tool_calls == ["read", "write"]`, `tool_call_count == 2` <!-- added 2026-07-03 (spec/cli-templates) --> |
| UT-067 | REQ-039 | test_adapter_usage_defaults_when_unavailable | Fake adapter whose `parse_usage`/`extract_tool_calls` return all-zero/empty values | `TrialResult` token fields default to 0 and `tool_calls` defaults to `[]`, matching existing "missing" semantics (REQ-019's zero-default behavior) <!-- added 2026-07-03 (spec/cli-templates) --> |
| UT-068 | REQ-040 | test_claude_code_history_written_under_cell_history_dir | `cli_template="claude-code"`, mocked subprocess | `ClaudeCodeCliAdapter.history_log_path()` returns a path inside `cell_dir/history/` <!-- added 2026-07-03 (spec/cli-templates) --> |
| UT-069 | REQ-041 | test_claude_code_argv_uses_print_mode | `cli_template="claude-code"`, model, instruction | `build_argv` returns an argv beginning with `cli_name`, containing the non-interactive/print flag and the JSON-output flag <!-- added 2026-07-03 (spec/cli-templates) --> |
| UT-070 | REQ-041 | test_claude_code_parses_usage_from_json_output | Sample Claude Code JSON stdout containing a `usage` block | `UsageSummary` fields match the JSON's input/output/cache-read counts <!-- added 2026-07-03 (spec/cli-templates) --> |
| UT-071 | REQ-042 | test_opencode_argv_uses_run_mode | `cli_template="opencode"` | `build_argv` returns an argv beginning with `cli_name` and opencode's non-interactive run subcommand <!-- added 2026-07-03 (spec/cli-templates) --> |
| UT-072 | REQ-042 | test_opencode_parses_usage_from_output | Sample opencode stdout | `UsageSummary` fields populated by `OpencodeCliAdapter.parse_usage` <!-- added 2026-07-03 (spec/cli-templates) --> |

## Integration Tests

| ID | Scope | Test Name | Setup | Assertion |
|----|-------|-----------|-------|-----------|
| IT-001 | ExperimentConfig + CLI | test_run_command_full_pipeline | Create temp dirs with 2 mock test cases; run `zrb-llm-evaluator run --models openai:gpt-4o --test-cases ./cases/ --trials 2 --output-dir ./out` | results.json exists with 4 entries; all statuses are terminal |
| IT-002 | Resume | test_resume_mid_experiment | Run 2 models × 1 case × 2 trials; interrupt after cell 3; restart | Only cell 4 executes; results.json has 4 entries |
| IT-003 | Parallelism | test_parallel_execution | Run 8 cells with parallelism=4 | Total wall-clock < 3× single-trial latency (confirms concurrency) |
| IT-004 | Validator protocol | test_custom_validator_executed | Test case with validator.py returning ValidationResult(status=EXCELLENT, score=0.95, details=[]) | results.json has verification_result with score=0.95 |
| IT-005 | TrialRunner + filesystem | test_isolation_end_to_end | Real (mocked) subprocess that lists its `cwd` to stdout; test case has `workdir/data.txt` + `validator.py` + `instruction.txt` | Captured stdout reports `cwd` listing contains `data.txt` only; no `stdout.log`, no `history`, no `validator.py`, no `instruction.txt` |
| IT-006 | MarkdownReporter end-to-end | test_report_md_full_pipeline_sort_bold_icons | Run a small experiment (2 models × 2 cases × 2 trials, mix of statuses); inspect `report.md` | Rows sorted; best-PASS cells bold per test case; status column contains icons; no HTML present |
| IT-007 | CliAdapter + Runner | test_run_command_with_claude_code_template | Run `zrb-llm-evaluator run --cli-template claude-code ...` against a mocked `claude-code` binary | `results.json` has entries populated via `ClaudeCodeCliAdapter`; statuses terminal <!-- added 2026-07-03 (spec/cli-templates) --> |
| IT-008 | CliAdapter + Runner | test_run_command_with_opencode_template | Run `zrb-llm-evaluator run --cli-template opencode ...` against a mocked `opencode` binary | `results.json` has entries populated via `OpencodeCliAdapter`; statuses terminal <!-- added 2026-07-03 (spec/cli-templates) --> |

## End-to-End Tests

| ID | Story | Scenario | Steps | Expected |
|----|-------|----------|-------|----------|
| E2E-001 | US-001 | Full experiment run | 1. Create 2 test case dirs with validators; 2. Run `zrb-llm-evaluator run --models m1,m2 --test-cases ./cases/ --trials 2 --output-dir ./exp`; 3. Inspect ./exp | results.json has 8 entries; report.md and results.json exist; all entries have terminal status |
| E2E-002 | US-003 | Timeout preserves history | 1. Create a test case with a long-running instruction; 2. Run with --timeout 5; 3. Check logs | Trial has TIMEOUT status; history JSON file exists on disk |
| E2E-003 | US-007 | Resume after Ctrl+C | 1. Start experiment with 4 cells; 2. Kill after cell 2; 3. Re-run with same output dir | Cells 1-2 skipped; cells 3-4 execute; final results.json has 4 entries |
| E2E-004 | US-009 | Scannable report after a run | 1. Run a full experiment with mixed statuses; 2. Open `report.md` | Rows ordered by model→case→trial; per-test-case best `duration`/`score`/`total_tokens`/`tool_call_count` cells bold; status icons render for all five statuses |
| E2E-005 | US-011 | Evaluate a non-zrb CLI | 1. Create test case dirs with validators; 2. Run `zrb-llm-evaluator run --models m1 --test-cases ./cases/ --trials 2 --cli-template opencode --output-dir ./exp`; 3. Inspect `./exp` | `results.json`/`report.md` produced exactly as with the `zrb` template, using the opencode CLI <!-- added 2026-07-03 (spec/cli-templates) --> |

## Property-Based Tests

N/A — no property-testing framework configured.

## Design Property Coverage

| Property | Covered By | Notes |
|----------|------------|-------|
| Round-Trip | UT-020, UT-022, UT-023, UT-042, UT-065 | Pydantic serialization/deserialization verified via results.json write + token field defaults; report rendering is deterministic byte-identical across runs; `UsageSummary` round-trips into `TrialResult` token fields regardless of adapter |
| Uniqueness | UT-001, UT-018 | Session name uniqueness + output dir hierarchy enforcement |
| Atomicity | UT-020 | Atomic write via temp file + os.rename; results.json always valid JSON |
| Validation | UT-013, UT-015, UT-016, UT-017, UT-018, UT-029, UT-030, UT-031, UT-035, UT-063, UT-064 | Config validation (model format, required args, `cli_template`) + test case import rejection + per-trial filesystem layout invariants + report output is pure Markdown (no HTML) + adapter resolution failures rejected before any trial |
| Idempotency | UT-006, IT-002 | Resume skips terminal cells; re-run produces identical results |

## Test Data Strategy
- **Fixtures**: `tests/experiment-runner/conftest.py` — temp directories, mock subprocess factory, sample test case directories with validators, sample results.json files
- **Synthetic data**: Generated inline via pytest fixtures. Pydantic factories using `.model_validate()` for round-trip tests.
- **Cleanup**: `tmp_path` fixture (pytest built-in) for all filesystem operations. No global state between tests.
