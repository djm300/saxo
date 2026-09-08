---
name: saxo-investment-bot
description: Run a manually invoked autonomous Saxo SIM portfolio review with unrestricted global discovery, structured bull/bear research, deterministic risk validation, execution, and S&P 500 benchmarking.
---

# Saxo Investment Bot

Run only when the user explicitly requests a portfolio review. This skill authorizes autonomous orders in Saxo SIM, never live trading.

## Start and recover state

1. Read `agent/mandate.json`, `agent/state/theses.json`, `agent/state/watchlist.json`, `agent/state/signals.json`, `investbot.log` when present, this skill's `references/plan-schema.md` and `references/holdings-review.md`, and relevant prior `agent/runs/*` artifacts.
2. Create a unique UTC-based `run_id` and an append-only `agent/runs/<run_id>/` directory. Never overwrite a prior run.
3. Run `saxo-cli --env sim agent snapshot --json`, wait for it to finish, then run `saxo-cli --env sim agent performance --json`. Never run Saxo CLI processes concurrently because token refresh is serialized. Parse each command's JSON in memory; abort on a nonzero exit or an `error` object. Only after success, write the already-sanitized JSON to the run directory. Never redirect or save raw stdout/stderr, authentication errors, authorization URLs, or files named `*.raw.*`.
4. Stop if the environment is not SIM, identity is ambiguous, state cannot be reconciled, or the complete portfolio cannot be obtained.

## Research

Use `gpt-5.6-luna` with medium reasoning for the parent and every subagent. Read `references/alternative-signals.md` before discovery. Spawn at most three researchers simultaneously, using sequential waves when more lanes are warranted:

- `holdings_monitor` for every current position, active thesis, material filing/news, order, and price change. It must assess each snapshot position individually as add, hold, trim, or exit; portfolio-level commentary is not a substitute.
- `alternative_signals_scout` for unusual public web signals and less-obvious issuer mappings.
- `global_scout` for open-ended global equities and ETF discovery, emphasizing differentiated companies rather than defaulting to broad beta.
- `macro_scout` for macro, sector, catalyst, and momentum changes.

There is no portfolio-size, candidate, watchlist, sector, region, market-cap, or sequential-batch limit. Do not manufacture a quota. Run more discovery batches when they explore a genuinely different lead. Stop discovery when new searches repeat known evidence or no remaining idea plausibly displaces cash or a current holding.

For every promising candidate, separately use `bull_analyst` and `bear_analyst`. Ask follow-ups when their evidence conflicts. Prefer filings, issuer materials, regulators, exchanges, and other primary sources; date claims and preserve source links. Use `saxo-cli chart` for price history. Resolve every executable idea through Saxo and preserve its exact `uic`, `asset_type`, and `account_key` internally.

Do not select a broad index ETF merely because it is easy to validate. Before broad beta can win, complete and record an alternative-signal pass across multiple genuinely different signal families, identify the strongest company-specific mappings, and explain why none offers superior evidence-adjusted portfolio displacement. This is a research-quality gate, not a requirement to trade or to prefer novelty over risk-adjusted evidence.

## Decide and record

Act as portfolio manager. Hold, buy, trim, exit, or make no trade based on thesis quality and portfolio displacement—not a target position count or fixed holding period.

Before finalizing `plan.json`, write `holdings-review.json` according to `references/holdings-review.md`. It must contain exactly one assessment for every position in the current snapshot, including positions missing from the thesis ledger. Compare the current weight, profit/loss, price evidence, thesis evidence, contrary evidence, catalysts, concentration, and opportunity cost. Do not retain a position merely because it is small or already owned. An add decision must beat cash and new candidates; a trim or exit decision must identify what weakened, broke, became overvalued, or is better deployed elsewhere. Reconcile the artifact against the snapshot and plan with:

```console
python scripts/validate_holdings_review.py --snapshot agent/runs/<run_id>/snapshot.json --review agent/runs/<run_id>/holdings-review.json --plan agent/runs/<run_id>/plan.json
```

Do not validate or execute the plan unless this command succeeds. If coverage cannot be completed, stop the run as blocked instead of silently treating unreviewed positions as holds.

Every held or proposed position needs: summary, supporting and contrary evidence, bull/base/bear cases, catalysts, invalidation conditions, and a future review trigger. Bring every current position into the thesis ledger during its first complete review; do not leave untracked holdings implicit. Update the thesis ledger, signal ledger, and dynamic watchlist without truncating them. Archive weak ideas and expired signals instead of deleting their history.

Write research, decision rationale, source links, and risk review to the run directory. Produce `plan.json` exactly as specified in `references/plan-schema.md`. Before every artifact write, scan its content and refuse the write if it includes tokens, authorization URLs, client/account keys, or raw Saxo responses. Never commit artifacts automatically.

## Validate and execute

Run `saxo-cli --env sim agent validate agent/runs/<run_id>/plan.json --json`. Treat deterministic validation as authoritative. A zero-order plan is valid.

If validation succeeds, run `saxo-cli --env sim agent execute agent/runs/<run_id>/plan.json --execute --json`. The executor applies reductions first, refreshes state before each order, uses only market orders, and stops at the first failure or indeterminate response. Do not bypass or weaken a failed guardrail. Reconcile execution receipts, refresh the snapshot and performance, and update ledger state only from confirmed results.

## Conclude every run

After a completed, blocked, or failed run, append exactly one entry to the repository-root `investbot.log` with `scripts/append_investbot_log.py`. Supply a concise conclusion containing the portfolio decision and why, the strongest confirmed or rejected alternative signal, and the next review trigger. The helper derives the UTC timestamp, status, and order count from the run directory, rejects duplicate `run_id` entries, collapses the entry to one line, and refuses sensitive-looking content. If a run stops before normal artifacts exist, first write a sanitized `run-status.json` so its outcome can be logged. Never rewrite or truncate the log.

```console
python scripts/append_investbot_log.py --run-dir agent/runs/<run_id> --conclusion "No trade; candidate failed deterministic validation because the market was closed." --next-trigger "Revisit during the next open-market review."
```
