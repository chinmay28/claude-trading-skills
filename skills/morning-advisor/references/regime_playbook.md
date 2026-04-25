# Regime Playbook

Decision matrix for routing the morning routine based on market regime. Inputs come from no-cost macro skills (no FMP usage in this stage).

## Regime Inputs

| Source | Output | API cost |
|--------|--------|----------|
| `macro-regime-detector` | `RISK_ON | NEUTRAL | RISK_OFF` label, ratio scores | none |
| `market-breadth-analyzer` | breadth score 0–100 | none (public CSV) |
| `uptrend-analyzer` | uptrend ratio score 0–100, late-cycle / high-selectivity flags | none (public CSV) |
| `ftd-detector` | FTD active? days since FTD | none |
| `market-top-detector` | top signal active? confidence | none |

## Regime Decision Rules

Apply in order. First match wins.

1. **HARD RISK_OFF** if any of:
   - `market-top-detector` confidence ≥ 0.7
   - Breadth score < 30
   - SPY closed below 200-day MA AND breadth < 50
2. **RISK_OFF** if breadth < 40 OR `uptrend-analyzer` late-cycle flag set
3. **RISK_ON** if breadth ≥ 60 AND `macro-regime-detector` label is RISK_ON AND no top signal
4. **NEUTRAL** otherwise

## Screener Routing

| Regime | Primary screener | Secondary fallback | Allowed instruments |
|--------|------------------|--------------------|---------------------|
| RISK_ON | `vcp-screener` | `breakout-trade-planner`, `earnings-trade-analyzer` | stock, ETF, long call |
| NEUTRAL | `dividend-growth-pullback-screener` | `pead-screener` | stock, ETF, selective long call |
| RISK_OFF | none (manage existing only) | manual put scan on SPY/QQQ | long put only, max 1 entry |
| HARD RISK_OFF | none | none | no new entries; close at-risk positions |

## Position-Management Triggers (apply every day)

For each open thesis, EXIT if any:

- Price ≤ `entry.stop` (intraday; use prior close + ATR buffer if pre-market)
- Today ≥ `entry.time_stop_date`
- Price ≥ `entry.target` and thesis is not designated for trailing
- **Regime flip:** thesis was opened in RISK_ON and current regime is HARD RISK_OFF
- **Catalyst gone:** earnings-driven thesis past earnings date by > 5 trading days with no follow-through
- **Volatility crush:** long option thesis with IV percentile dropped > 20 points and underlying flat (delta on premium > underlying gain)

ROLL (long options only) if all:

- Days-to-expiry ≤ 7
- Original thesis intact (no exit trigger above)
- Remaining intrinsic value ≥ 30% of premium paid
- Liquidity at next expiry acceptable (bid-ask spread < 5% of mid)

HOLD otherwise.

## New-Entry Gating

Skip the new-idea stage entirely if any:

- Total open risk (sum of `(entry - stop) × shares` or option max-loss) ≥ 5% of equity
- Account equity dropped > 5% peak-to-trough in last 10 trading days (drawdown circuit breaker)
- > 3 consecutive losing trades in last 10 closed theses (cool-off period of 1 week)
- Today is FOMC day, NFP morning, or CPI morning — let the print clear before entering

## Notes

- The cool-off and drawdown circuit breakers protect against tilt during bad streaks.
- The FOMC/NFP/CPI gate avoids entering immediately before known volatility events. Re-enable next session.
- Regime is recomputed daily; do not cache across runs.
