# Task 6 Report: Cash-Aware Single Allocation and CLI Migration

## TDD record

- RED: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_portfolio.py skills/deep-analysis/scripts/tests/tail_decision/test_workflow.py skills/deep-analysis/scripts/tests/tail_decision/test_cli.py -q` produced four expected failures. The allocator still constrained purchases by legacy `account_assets`, and the CLI lacked `--position-cap`, `--available-cash`, and the cash-cap JSON fields. The preview and final-missing-cash workflow checks were already GREEN safety invariants.
- GREEN: allocation now derives its sole legal-lot budget directly from `effective_position_cap_cny`; it returns `available_cash_missing` with no allocation when the cap is unavailable. The CLI defaults both new cash fields to CNY 12,000, maps the deprecated `--max-exposure` alias to the configured cap, rejects an explicit alias/new-cap conflict, and emits configured, available, and effective caps without credential values.
- Focused regression: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_portfolio.py skills/deep-analysis/scripts/tests/tail_decision/test_workflow.py skills/deep-analysis/scripts/tests/tail_decision/test_cli.py -q` passed with 23 tests.
- Adjacent configuration/no-token regression: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_config.py skills/deep-analysis/scripts/tests/tail_decision/test_no_token_e2e.py -q` passed with 7 tests.

## Self-review

- A CNY 79.50 stock buys exactly one 100-share lot under the CNY 12,000 effective cap even when legacy `account_assets` is CNY 4,000.
- The deterministic cross-asset sort and first-feasible break remain unchanged, so an allocation list has at most one item and no exposure exceeds the effective cap.
- Lower supplied cash (CNY 7,600) wins over the configured CNY 12,000 cap. Preview never allocates; final missing cash remains blocked with the stable `available_cash_missing` reason.
- Nonpositive cash is rejected through the existing validated `DecisionConfig` path. The legacy alias is supported for one release but cannot be combined with an explicit `--position-cap`.

## Concerns

- `workflow.py` already implemented the specified final missing-cash block before this task; its regression coverage was expanded, but no production workflow change was needed.

## Review remediation: finite cash inputs and legal lots

- RED: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_config.py skills/deep-analysis/scripts/tests/tail_decision/test_portfolio.py skills/deep-analysis/scripts/tests/tail_decision/test_cli.py -q` produced 23 expected failures. NaN, positive infinity, and `True` passed the comparison-only configuration checks; the allocator created illegal quantities from `100.5` and `True`; and CLI `nan`/`inf` runs completed and could expose non-standard JSON values. A separately-tokenized `-inf` produced an existing argparse error; the regression uses `--flag=-inf` to cover the validated configuration path.
- GREEN: finite non-boolean real-number guards now protect all cash/exposure and monetary configuration values used by this flow, including account assets, configured and available cash, liquidity amounts, and minimum commission. Existing non-negative rate/threshold validation now also rejects NaN, infinities, and booleans. The allocator requires a positive non-boolean integral candidate lot size before Decimal arithmetic; invalid lots use the stable `skipped_invalid_candidate:<id>` reason.
- Task 6 plus adjacent regression: `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_portfolio.py skills/deep-analysis/scripts/tests/tail_decision/test_workflow.py skills/deep-analysis/scripts/tests/tail_decision/test_cli.py skills/deep-analysis/scripts/tests/tail_decision/test_config.py skills/deep-analysis/scripts/tests/tail_decision/test_no_token_e2e.py -q` passed with 61 tests. `git diff --check` was clean.
