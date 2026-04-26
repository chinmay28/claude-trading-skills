# Execution Protocol

Rules for placing, monitoring, and cancelling orders on Alpaca paper. The orchestrator must follow these strictly — execution mistakes corrupt the benchmark log and invalidate the trial.

## Pre-Execution Checks

Before submitting any order:

1. Confirm `ALPACA_PAPER=true` in environment. If unset or false, abort with explicit error. Live trading is never enabled by this skill.
2. Confirm Alpaca account `status = ACTIVE` and `trading_blocked = false` via `mcp__alpaca__get_account_info`.
3. Confirm market is open (in pre-market window 08:00–09:30 ET, queue orders for open; after 16:00 ET, abort).
4. Confirm sufficient buying power: `buying_power ≥ order_notional × 1.05` (5% headroom).

## Order Type by Instrument

| Instrument | Order type | Time in force | Limit price | Notes |
|-----------|-----------|---------------|-------------|-------|
| Stock entry | market | day | n/a | Submitted at 09:30 ET; accept open print |
| ETF entry | market | day | n/a | Same as stock |
| Long call entry | limit | day | bid + (ask-bid)/2 | Mid; cancel at 09:45 ET if unfilled |
| Long put entry | limit | day | bid + (ask-bid)/2 | Mid; cancel at 09:45 ET if unfilled |
| Stock/ETF exit | market | day | n/a | Speed > price for risk reduction |
| Long option exit | limit | day | bid + (ask-bid)/2 | Mid; if unfilled at 15:55 ET, market order |

## Slippage Caps

If the open print on a stock entry is > 1.5% above the prior close, **abort the entry** and log SLIPPAGE_REJECT in the manifest. The thesis is marked INVALIDATED with reason `gap_too_wide`. Do not chase.

For options, if the ask at 09:30 ET is > 10% above the recommended limit price, abort the entry similarly.

## Fill Confirmation

After submitting an order:

1. Poll `mcp__alpaca__get_order` every 5 seconds for up to 60 seconds.
2. On `filled` → record fill price + quantity in manifest, transition thesis to ACTIVE.
3. On `partial_fill` after 60 seconds → cancel remainder, transition thesis to ACTIVE with the partial qty (recalc risk).
4. On `canceled` (mid stale, no fill) → log CANCELED, mark thesis INVALIDATED with reason `unfilled_at_open`.
5. On `rejected` → log full rejection reason, mark thesis INVALIDATED with reason `broker_reject`.

## Order Sequencing

Process exits before entries within a single run. Reasoning:

- Exits free up buying power and risk budget for entries
- A failed exit (e.g., broker reject) means we're carrying more risk than expected — should reduce new entries
- Re-evaluate `open_risk_pct` between Step 2 (exits) and Step 3 (entries)

Within entries, order by descending conviction (top-1 first). If buying power is depleted before all entries are placed, log SKIPPED_INSUFFICIENT_BP and stop.

## Idempotency

Each order submission MUST include a `client_order_id` derived from the thesis_id and date:

```
client_order_id = f"{thesis_id}_{action}_{YYYYMMDD}"
# e.g., th_nvda_pvt_20260427_a3f1_entry_20260427
```

If a re-run on the same day attempts to resubmit, Alpaca rejects on duplicate client_order_id — this is the desired behavior. Log DUPLICATE_SKIPPED and continue.

## Rollback on Partial Failure

If during Step 5 (auto-execute) any order errors with a transient broker failure:

1. Do **not** attempt automatic rollback (we don't want to stack errors).
2. Mark all subsequent ENTRY_READY theses as DEFERRED (not INVALIDATED) with reason `prior_execution_failed`.
3. Surface the failure prominently in the daily report header with a "MANUAL REVIEW REQUIRED" banner.
4. Exit code 1 from the orchestrator so cron logs flag the run as failed.

## Position Limits (Alpaca-side hard caps)

These are enforced before submission, in addition to the skill's risk caps:

- Max 25 open positions across the account (configurable; defaults match Alpaca paper conventions)
- Max single-position notional: 25% of equity (additional safety beyond the 10% sizing rule)
- No fractional contracts (round down). No fractional shares for options-eligible names; whole shares for stocks/ETFs only

## Logging

Every order submission and fill is recorded in `run_manifest.json` under `executions`:

```json
{
  "executions": [
    {
      "ts": "2026-04-27T13:30:14Z",
      "thesis_id": "th_nvda_pvt_20260427_a3f1",
      "action": "entry",
      "instrument": "call",
      "symbol": "NVDA250530C00115000",
      "side": "buy_to_open",
      "qty": 2,
      "order_type": "limit",
      "limit_price": 4.85,
      "client_order_id": "th_nvda_pvt_20260427_a3f1_entry_20260427",
      "alpaca_order_id": "f3a91b4e-...",
      "status": "filled",
      "filled_qty": 2,
      "filled_avg_price": 4.85,
      "filled_at": "2026-04-27T13:30:21Z"
    }
  ]
}
```
