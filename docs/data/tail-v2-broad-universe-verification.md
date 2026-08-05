# Tail v2 Broad-Universe Verification

Date: 2026-08-05

## Scope and safety

- Verification ran in the linked `tail-v2-broad-universe` worktree. No Windows scheduled task, external automation, broker, or order endpoint was created, changed, or invoked.
- Each no-token command cleared the token only from its child PowerShell process. The production path continues to reject UZI cache files whose modification timestamp is later than `--as-of`.
- The local archives were read only. Inventory after verification: `D:\work\gupiao\data\tushare` has 229 files / 70,693,668 bytes and `D:\work\gupiao\data\tushare_calendar` has 500,354 files / 7,791,876,789 bytes. The Tushare inventory matches the pre-verification read-only inventory.

## Test evidence

| Command | Result |
| --- | --- |
| `python -m pytest skills/deep-analysis/scripts/tests/tail_decision/test_recorder.py skills/deep-analysis/scripts/tests/tail_decision/test_no_token_e2e.py skills/deep-analysis/scripts/tests/tail_decision/test_production_no_token_e2e.py skills/deep-analysis/scripts/tests/tail_decision/test_research_evidence.py skills/deep-analysis/scripts/tests/tail_decision/test_scheduler_script.py -q` before production changes | RED: 7 failed, 14 passed. Failures proved missing audit summary/multi-allocation rejection, future-mtime helper instability, and hardcoded scheduler root rejection. |
| same focused command after production changes | GREEN: 21 passed. |
| `python -m pytest skills/deep-analysis/scripts/tests/tail_decision -q` | GREEN: 169 passed (169 collected). |

The UZI test helper pins every valid fixture timestamp to `2026-08-05T12:00:00+08:00`; mutations in malformed-state tests reset that same timestamp. The explicit future timestamp regression remains unchanged and continues to produce `uzi_future`.

## Isolated no-token E2E

Output root: `D:\work\gupiao\data\tail_v2_broad_verification_task7`

| Phase | Fixed aware timestamp | Run ID | Status | Allocations | Exposure | Artifacts |
| --- | --- | --- | --- | ---: | ---: | --- |
| preview | `2026-08-05T14:10:00+08:00` | `20260805T141000_preview` | `watch_only` | 0 | 0.00 | JSON and Markdown written |
| final | `2026-08-05T14:30:00+08:00` | `20260805T143000_final` | `recommended` | 1 | 11,924.06 | JSON and Markdown written |

Both commands used `--offline-fixture --position-cap 12000 --available-cash 12000`. The effective cap was 12,000.00 in each run. The preview report has two finalist summaries and no allocation; the final report has two finalist summaries and one allocation. The Markdown renderer presents only the final selected `Buy plan` or an explicit non-actionable state.

## Broad-funnel fixture

The credential-free broad fixture was run with the token removed from the child process.

| Fixture | Research stocks | Observation stocks | Research ETFs | Observation ETFs |
| --- | ---: | ---: | ---: | ---: |
| 320-stock fixture | 300 | 30 | 1 | 1 |
| 320-stock / 12-ETF fixture | 300 | 30 | 12 | 10 |

The result satisfies the 300 / 30 / 10 funnel limits. Finalists remain capped at five by the rankers; the isolated final E2E produced two finalists and one allocation.

## Artifact and scheduler checks

The JSON/Markdown artifact scan found zero occurrences of each marker: token environment variable name, `.env`, `broker`, `auto-order`, `NaN`, and `Infinity`. No credential values were printed or recorded.

Scheduler `-WhatIf` tests cover all seven unchanged phase times and verify the hidden-window task action includes exactly `--position-cap 12000 --available-cash 12000`. Root validation now derives the normalized root from the script path, requires its `.git` marker, and verifies contained CLI/log paths; this supports both the primary checkout and an actual linked worktree without accepting escaped paths.

## Delivered audit fields

Recorded JSON now contains `audit.funnel` (base/research/observation counts, finalists, allocations, and funnel reasons), `audit.evidence` (source dates and ignored reason codes), and `audit.cash` (configured, available, and effective CNY caps). Recorder writes fail closed for more than one allocation or a non-finite number.
