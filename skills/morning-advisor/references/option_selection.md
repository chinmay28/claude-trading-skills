# Option Selection Rules

Decision rules for choosing instrument (stock vs ETF vs long call vs long put) and selecting strike + expiry. Long-only — no spreads, no short premium.

## Instrument Decision Tree

```
1. Is the thesis bearish?
   ├── YES → long PUT only (regime must be RISK_OFF; otherwise skip)
   └── NO  → continue

2. Is there an earnings event inside the holding window?
   ├── YES, and thesis is event-driven → consider stock or call (see #4)
   ├── YES, and thesis is NOT event-driven → drop the candidate
   └── NO  → continue

3. Is IV percentile (52-week) ≥ 50?
   ├── YES → STOCK / ETF (long premium too expensive)
   └── NO  → continue

4. Is options liquidity acceptable?
       (open interest ≥ 500 at chosen strike, bid-ask spread ≤ 5% of mid)
   ├── NO  → STOCK / ETF
   └── YES → continue

5. Is account equity ≥ $25k AND single-contract premium ≤ 1% of equity?
   ├── NO  → STOCK / ETF (option contract size mismatch)
   └── YES → LONG CALL (or LONG PUT if Step 1 was YES)
```

## Strike Selection (long calls and puts)

Target delta: **0.30 to 0.50**.

- 0.30–0.35: cheaper, higher leverage, lower probability — use when conviction is moderate and target is far
- 0.40–0.45: balanced — default choice
- 0.45–0.50: closer to ATM, behaves more like stock — use when conviction high and want lower theta drag

Pick the listed strike whose delta is closest to 0.40 unless a specific reason suggests otherwise.

## Expiry Selection (DTE)

Target: **30–45 days to expiry**.

- < 30 DTE: theta drag accelerates; avoid unless thesis is < 2 weeks
- 30–45 DTE: sweet spot for 1w–1mo holding horizons
- 45–60 DTE: acceptable if 30-DTE liquidity is poor
- > 60 DTE: too much premium for the holding horizon

If today is mid-month and the next monthly expiry is < 25 DTE, skip to the following monthly.

## IV Percentile Heuristics

- **IV percentile < 30:** options cheap → favor calls/puts over stock
- **IV percentile 30–50:** neutral → defer to liquidity and account-size rules
- **IV percentile 50–70:** options expensive → prefer stock unless conviction is very high
- **IV percentile > 70:** options very expensive → stock only; long premium is a poor bet here

When IV percentile data is unavailable from FMP, fall back to comparing current ATM IV against trailing 60-day mean: if current > 1.2× mean, treat as "expensive".

## Sizing for Options

Max loss = `premium_paid × contracts × 100`. Size so max loss ≤ 1% of account equity.

```
max_contracts = floor( (equity × 0.01) / (premium × 100) )
```

If `max_contracts < 1`, skip — the contract is too expensive for the account.

For stocks/ETFs, use `position-sizer` with `--risk-pct 1.0` and stop-loss based sizing.

## Order Type at Entry

- **Stocks/ETFs:** market order at the open (acceptable slippage on liquid names)
- **Options:** limit at mid of bid-ask. If unfilled by 9:45 ET, cancel — do not chase. The bot is not allowed to lift the offer.

## Roll Rules

When a long option position is rolled (see `regime_playbook.md` ROLL conditions):

1. Close the existing contract at mid (limit order).
2. Open the next monthly expiry at the same delta target (0.40 default).
3. The roll is recorded as CLOSE + new ENTRY in the benchmark log (two events), not a synthetic continuation.
4. The new thesis_id has its own time_stop_date = roll_date + 25 trading days.

## Anti-Patterns (Never Do)

- Buying < 14 DTE on a thesis that needs > 1 week to play out
- Selecting strikes with delta < 0.20 (lottery tickets)
- Holding through earnings on a non-event-driven thesis
- "Rolling for credit" or any short-premium leg (we are long-only)
- Averaging down on a losing option (the time stop and stop-loss are non-negotiable)
